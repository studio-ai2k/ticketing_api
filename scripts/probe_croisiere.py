#!/usr/bin/env python3
"""
Is "Croisière Madame Loyal x Elektric Park" reachable on either platform?

    python scripts/probe_croisiere.py

WHY A DISCOVERY PROBE RATHER THAN `probe_shotgun_account.py`
------------------------------------------------------------
Every probe this repo has takes an event id and asks "who owns it". The
croisière appears on the Festiflow fiche - 6 September 2026, Paris, 5,000 - and
has no config row, no Shotgun id and no DICE id. There is nothing to hand the
existing probes. So this one goes the other way: it asks each account what
events it can see at all, and prints the names.

WHAT IT REPORTS, AND WHAT IT DELIBERATELY DOES NOT
---------------------------------------------------
Numbers and names, per account, verbatim. It does NOT decide whether the
croisière deserves a dashboard, and it writes no config row. There are at least
three answers the numbers could carry and only Leo picks between them:

  * a separate Shotgun/DICE event with its own sales     -> it could have a page
  * no separate event, sales inside EPK's feed           -> a page would double-count
  * an event that exists with zero sales                 -> indistinguishable, by
    construction, from an account this token cannot reach. That ambiguity is the
    reason `probe_shotgun_account.py` exists and it applies here unchanged.

ALREADY KNOWN LOCALLY, BEFORE ANY TOKEN
----------------------------------------
`data/epk_2026_merged.csv` carries a product named **'Pass Festival + Croisiere'**
- 74 tickets of 13,481. So the croisière is at least partly sold THROUGH epk_2026
and already counted on epk.html. Whether that is all of it is what this asks.
"""

import collections
import os
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fetch_csv import SHOTGUN_API, extract_shotgun_tickets, http_json  # noqa: E402

ACCOUNTS = [
    ('episode', 'SHOTGUN_TOKEN_EPISODE', '171835'),
    ('sonora', 'SHOTGUN_TOKEN_SONORA', '207784'),
]

# What we are looking for. Matched loosely because the fiche's spelling and the
# platform's need not agree - "ELECTRICK" is already misspelled on the bank side
# and is the account's real name.
NEEDLES = ('croisi', 'cruise', 'bateau', 'boat')

MAX_PAGES = 8


def shotgun_events(account, token, organizer_id):
    """Distinct (event_id, event_name) the endpoint returns with NO event filter.

    The tickets endpoint takes `event_id` as a FILTER. Omitting it is not a
    documented listing mode, so this reports whatever comes back - including an
    error - rather than assuming it enumerates.
    """
    params = {
        'token': token,
        'organizer_id': organizer_id,
        'include_cohosted_events': '1',
    }
    url = f'{SHOTGUN_API}?{urllib.parse.urlencode(params)}'
    seen = collections.Counter()
    ids = {}
    pages = 0
    while url and pages < MAX_PAGES:
        try:
            payload = http_json(url)
        except Exception as exc:
            return None, f'ERROR: {str(exc)[:200]}'
        tickets = extract_shotgun_tickets(payload)
        if not tickets:
            break
        for t in tickets:
            if not isinstance(t, dict):
                continue
            name = t.get('event_name') or '?'
            seen[name] += 1
            ids.setdefault(name, t.get('event_id') or t.get('eventId') or '?')
        pages += 1
        nxt = (payload.get('pagination') or {}).get('next') if isinstance(payload, dict) else None
        if not nxt:
            break
        url = f'{SHOTGUN_API}?{urllib.parse.urlencode(params)}&' + \
              urllib.parse.urlencode({'after': nxt})
    return [(n, ids.get(n, '?'), c) for n, c in seen.most_common()], \
           f'{pages} page(s) read'


VIEWER_FIELDS = """
query ViewerFields {
  __type(name: "Viewer") {
    fields { name type { name kind ofType { name kind } } }
  }
}
"""


def dice_viewer_fields(token):
    from fetch_csv import dice_graphql
    try:
        # fetch_csv.dice_graphql takes the TOKEN FIRST, not the query.
        data = dice_graphql(token, VIEWER_FIELDS, {})
    except Exception as exc:
        return None, f'ERROR: {str(exc)[:200]}'
    t = (data or {}).get('__type') or {}
    return [f['name'] for f in (t.get('fields') or [])], 'ok'


def main():
    print('=' * 72)
    print('CROISIERE DISCOVERY - numbers only, no conclusion, no config row')
    print('=' * 72)

    print('\nLOCAL, no token needed: is it already inside epk_2026?')
    import csv
    p = ROOT / 'data' / 'epk_2026_merged.csv'
    if p.exists():
        rows = list(csv.DictReader(p.open(encoding='utf-8-sig')))
        hits = collections.Counter(
            (r.get('product_name') or '').strip() for r in rows
            if any(n in (r.get('product_name') or '').lower() for n in NEEDLES))
        print(f'  {len(rows):,} rows in epk_2026_merged.csv')
        for k, v in hits.most_common():
            print(f'    {v:6}  {k!r}')
        if not hits:
            print('    no product name matches croisi/cruise/bateau/boat')
    else:
        print('  epk_2026_merged.csv not present')

    print('\nSHOTGUN - what each account can see with no event filter')
    for account, env, org in ACCOUNTS:
        token = os.environ.get(env, '').strip()
        if not token:
            print(f'  {account:8} (org {org}): {env} not set - SKIPPED, not "none found"')
            continue
        events, note = shotgun_events(account, token, org)
        if events is None:
            print(f'  {account:8} (org {org}): {note}')
            continue
        print(f'  {account:8} (org {org}): {len(events)} distinct event(s), {note}')
        for name, eid, n in events:
            mark = '  <== MATCH' if any(x in name.lower() for x in NEEDLES) else ''
            print(f'      {n:7} tickets  id={eid!s:10} {name!r}{mark}')

    print('\nDICE - which fields the viewer exposes (an events list may not exist)')
    token = os.environ.get('DICE_TOKEN', '').strip()
    if not token:
        print('  DICE_TOKEN not set - SKIPPED, not "none found"')
    else:
        fields, note = dice_viewer_fields(token)
        if fields is None:
            print(f'  {note}')
        else:
            print(f'  Viewer fields: {", ".join(fields)}')
            print('  (no events connection here means DICE cannot be enumerated '
                  'by this token and needs an id, same as every other DICE probe)')

    print('\nDone. Report these numbers; do not infer a ruling from them.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
