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

WHAT THE RUNS RETURNED (2026-08-23)
------------------------------------
DICE, `viewer.events` -> EventConnection, 200 requested and **85 returned**, so
the whole catalogue and not a page cap. Ids run 91459 (2022) to 600413 (Rennes,
Nov 2026). **No event matches croisi/cruise/bateau/boat.** EPK is one event,
573271 'MADAME LOYAL x ELEKTRIC PARK : XXL EDITION', not two. Crazy Carnaval is
591517 'Madame Loyal Paris : Crazy Carnaval Edition', which agrees with the
fiche's mio URL. Genève and every Sonora event are ABSENT from this list, which
is the documented Collaborators/second-org split - so "not here" means "not under
this token", never "does not exist".

Shotgun could not be enumerated at all; see `shotgun_events` below.

The 74 combo tickets are **all Shotgun**, under epk_2026's own 535882, still
selling (last order 2026-08-23), 57.26-98.09 EUR. `resolve_attendance` maps them
onto festival days - 49 dimanche, 25 2-jours - so they already count toward
epk.html's Sunday présence.
"""

import base64
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

MAX_PAGES = 60


def shotgun_events(account, token, organizer_id):
    """Distinct (event_id, event_name) the endpoint returns with NO event filter.

    THIS DOES NOT ENUMERATE, AND THE FIRST RUN PROVED IT. Dropping `event_id`
    does not turn `/tickets` into an event list - it returns the organizer's
    TICKETS, ordered by ticket_updated_at (see fetch_shotgun_pages). Eight pages
    at 100/page returned 800 tickets and ONE distinct event name per account,
    because 800 tickets is not enough to leave the first event.

    "1 distinct event" was a page cap, not a finding, and reporting it as one
    would have been the exact silent-truncation shape fetch_shotgun_pages
    raises on: a smaller, entirely plausible number with nothing marking it
    short. So the caller is told how far it got and whether it finished, and an
    unfinished read is never evidence that something is absent.
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
    exhausted = False
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
            exhausted = True
            break
        url = f'{SHOTGUN_API}?{urllib.parse.urlencode(params)}&' + \
              urllib.parse.urlencode({'after': nxt})
    else:
        exhausted = False
    tot = sum(seen.values())
    note = (f'{pages} page(s), {tot} ticket(s), '
            + ('reached the end of the feed'
               if exhausted else
               f'STOPPED AT THE {MAX_PAGES}-PAGE CAP - the feed continues, so '
               'this list is PARTIAL and an absence here proves nothing'))
    return [(n, ids.get(n, '?'), c) for n, c in seen.most_common()], note


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


# `viewer.events` EXISTS - the first run of this probe printed it, and the note
# that used to be here said the opposite. The shape is not guessed: the first
# DICE probe died on `Cannot query field "date" on type "Event"`, so the
# connection type is introspected and the selection built from what it reports.
EVENTS_TYPE = """
query EventsType {
  __type(name: "Viewer") {
    fields { name type { name kind ofType { name kind ofType { name } } } }
  }
}
"""

CONN_FIELDS = """
query ConnFields($name: String!) {
  __type(name: $name) { fields { name } }
}
"""

EVENTS_LIST = """
query ListEvents($n: Int!) {
  viewer { events(first: $n) { edges { node { id name } } } }
}
"""


def dice_events(token, want=200):
    """Names of the events this token can see. Returns (rows, note)."""
    from fetch_csv import dice_graphql
    try:
        data = dice_graphql(token, EVENTS_TYPE, {})
    except Exception as exc:
        return None, f'ERROR introspecting Viewer: {str(exc)[:200]}'
    fields = {f['name']: f for f in ((data.get('__type') or {}).get('fields') or [])}
    if 'events' not in fields:
        return None, 'Viewer has no `events` field on this schema'

    def unwrap(t):
        while t and not t.get('name'):
            t = t.get('ofType')
        return (t or {}).get('name')
    conn = unwrap(fields['events'].get('type'))
    note = f'Viewer.events -> {conn}'
    try:
        cf = dice_graphql(token, CONN_FIELDS, {'name': conn}) if conn else {}
        note += ' {' + ', '.join(
            f['name'] for f in ((cf.get('__type') or {}).get('fields') or [])) + '}'
    except Exception as exc:
        note += f' (field list unavailable: {str(exc)[:80]})'

    try:
        data = dice_graphql(token, EVENTS_LIST, {'n': want})
    except Exception as exc:
        return None, f'{note}; ERROR listing: {str(exc)[:200]}'
    edges = (((data.get('viewer') or {}).get('events') or {}).get('edges')) or []
    rows = []
    for e in edges:
        n = (e or {}).get('node') or {}
        rows.append((n.get('name') or '?', n.get('id') or '?'))
    return rows, f'{note}; {len(rows)} event(s) returned'


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
        rows, note = dice_events(token)
        print(f'  {note}')
        if rows:
            for name, eid in rows:
                mark = '  <== MATCH' if any(x in name.lower() for x in NEEDLES) else ''
                try:
                    num = base64.b64decode(eid).decode().split(':')[-1]
                except Exception:
                    num = '?'
                print(f'      id={num:9} {name!r}{mark}')

    print('\nDone. Report these numbers; do not infer a ruling from them.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
