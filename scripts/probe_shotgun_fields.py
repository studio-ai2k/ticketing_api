#!/usr/bin/env python3
"""
Is 44 the ceiling on a Shotgun ticket, or just what one ticket had?

    SHOTGUN_TOKEN_EPISODE=... SHOTGUN_TOKEN_SONORA=... \
        python scripts/probe_shotgun_fields.py

`shotgun_schema.json` records ONE ticket from ONE event. That proves those 44
fields exist; it does not prove they are all there is. A field that only
populates for a seated event, a table booking or a bundle would be absent from
that sample and invisible to us - `ticket_seating` is null there but is plainly
a real concept.

Shotgun is REST with no introspection, so the only way to widen the evidence is
to look at more tickets. This takes the first page from every configured
Shotgun event and reports:

  - the UNION of keys across every ticket seen (is anything beyond the 44?)
  - the INTERSECTION (is anything absent from some events?)
  - per-key null rate (which of the 44 are actually populated in practice)
  - whether any endpoint index or spec is served

Read-only, one page per event, no pagination. Prints key names and null RATES
only - never a value, because several of these keys are personal and this log
is public.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fetch_csv import (SHOTGUN_API, extract_shotgun_tickets,  # noqa: E402
                       resolve_shotgun_account)

# Fields we must never print a value for, even by accident.
PERSONAL = {k for k in (
    'contact_email', 'contact_first_name', 'contact_last_name', 'contact_phone',
    'contact_id', 'contact_gender', 'contact_birthday', 'contact_postal_code',
    'contact_locality', 'contact_company_name', 'user_id', 'ticket_scan_code',
)}

# X3: is any index, spec or doc served? Shotgun is REST with no introspection,
# so if one of these answers, the endpoint list stops being guesswork.
DISCOVERY_PATHS = [
    'https://api.shotgun.live/',
    'https://api.shotgun.live/openapi.json',
    'https://api.shotgun.live/swagger.json',
    'https://api.shotgun.live/.well-known/openapi.json',
    'https://api.shotgun.live/docs',
    'https://api.shotgun.live/v1/',
    'https://api.shotgun.live/events',
    'https://api.shotgun.live/orders',
    'https://api.shotgun.live/deals',
]


def redact(text):
    """The Shotgun token travels in the query string, so any exception that
    quotes the URL would print it into a public Actions log. Strip it from
    everything on its way to stdout rather than trusting each call site."""
    out = str(text)
    for env in ('SHOTGUN_TOKEN_EPISODE', 'SHOTGUN_TOKEN_SONORA'):
        secret = os.environ.get(env, '').strip()
        if len(secret) > 4:
            out = out.replace(secret, f'<{env}>')
    return re.sub(r'token=[^&\s]+', 'token=<redacted>', out)


def probe_discovery():
    print(f'\n{"=" * 68}\nX3a - is anything discoverable?\n{"=" * 68}')
    for url in DISCOVERY_PATHS:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'festiflow-probe'})
            with urllib.request.urlopen(req, timeout=15) as r:
                body = r.read(400)
                print(f'  {r.status}  {url}')
                print(f'        {body[:160]!r}')
        except urllib.error.HTTPError as e:
            print(f'  {e.code}  {url}')
        except Exception as e:  # noqa: BLE001
            print(f'  ---  {url}   ({type(e).__name__})')


def probe_fields(events):
    print(f'\n{"=" * 68}\nX3b - key union across events\n{"=" * 68}')
    union, per_event, nulls, seen = set(), {}, defaultdict(int), 0
    intersection = None

    for eid, sg_id in events:
        try:
            account, token, org = resolve_shotgun_account(eid)
        except Exception as e:  # noqa: BLE001
            print(f'  {eid}: no account ({redact(e)})')
            continue
        if not token:
            print(f'  {eid}: token missing for account {account}')
            continue
        url = (f'{SHOTGUN_API}?token={token}&organizer_id={org}'
               f'&event_id={sg_id}&include_cohosted_events=1')
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                payload = json.loads(r.read().decode('utf-8'))
        except Exception as e:  # noqa: BLE001
            print(f'  {eid}: fetch failed ({type(e).__name__}: {redact(e)})')
            continue

        # Same extractor the fetcher uses - the container key is not documented,
        # and a probe that guessed differently would be measuring its own guess.
        tickets = extract_shotgun_tickets(payload)
        keys = set()
        for t in tickets:
            if not isinstance(t, dict):
                continue
            seen += 1
            keys |= set(t)
            for k, v in t.items():
                if v is None:
                    nulls[k] += 1
        per_event[eid] = keys
        union |= keys
        intersection = keys if intersection is None else (intersection & keys)
        print(f'  {eid:20} {len(tickets):>4} tickets, {len(keys)} distinct keys')

    print(f'\n  tickets inspected      {seen}')
    print(f'  UNION of keys          {len(union)}')
    print(f'  INTERSECTION           {len(intersection or set())}')
    baseline = 44
    extra = len(union) - baseline
    if extra > 0:
        print(f'\n  *** {extra} key(s) BEYOND the 44 in shotgun_schema.json:')
        print(f'      44 is NOT the ceiling.')
    elif len(union) == baseline:
        print(f'\n  no key beyond the sampled 44 across {seen} tickets and '
              f'{len(per_event)} events.')
        print(f'      Evidence that 44 is the shape - not proof, since every '
              f'event here may be structurally alike.')
    if intersection and union - intersection:
        print(f'\n  keys NOT present on every event: {sorted(union - intersection)}')

    print(f'\n  null rate per key (populated fields are the usable ones):')
    for k in sorted(union):
        n = nulls.get(k, 0)
        pct = n / seen * 100 if seen else 0
        mark = '  [personal - value never printed]' if k in PERSONAL else ''
        print(f'      {k:30} {pct:5.1f}% null{mark}')


def main():
    # load_event_config takes one event id, so the list of candidates comes
    # from the CSV directly - same rule the workflow's plan job uses.
    import csv
    events, seen_ids = [], set()
    for row in csv.DictReader(open('event_config.csv', encoding='utf-8-sig')):
        eid = (row.get('event_id') or '').strip()
        sg = (row.get('shotgun_event_id') or '').strip()
        if (eid and eid not in seen_ids and sg
                and (row.get('status') or '').strip() == 'active'):
            seen_ids.add(eid)
            events.append((eid, sg))
    print(f'{len(events)} active event(s) with a Shotgun id')
    probe_discovery()
    probe_fields(events)
    return 0


if __name__ == '__main__':
    sys.exit(main())
