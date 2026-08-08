#!/usr/bin/env python3
"""
Field-level probe for the Campagne inventory. Read-only, one event, first page.

    DICE_TOKEN=... python scripts/probe_dice_fields.py 600413

Answers the six things `dice_schema.json` cannot, because that dump records
object types and field NAMES only - it has no enum values, no input-object
fields and no field arguments, so three of introspection's four dimensions are
missing from it:

  P1  what PriceTier.time means, and whether tiers are populated
  P2  the TicketFeeCategory enum values, and a real fees array
  P3  the Order.salesChannel value set
  P4  Event.onSaleDatetime / announceDatetime / offSaleDatetime actual values
  P5  whether the token may read Fan { optInPartners } at all
  X2  Return, Adjustment, TicketTransfer, TicketPool - four types nobody opened

PII RULE, and it is not negotiable here
---------------------------------------
Fan is {dob, email, firstName, lastName, phoneNumber, optInPartners}. Exactly
one of those six is wanted. GraphQL returns only what is selected, so the query
below selects `optInPartners` ALONE - never `Fan { ... }` with anything else,
never a spread, never `id`.

This script also prints no ticket codes, no addresses, no order ids that could
be joined back, and no field values from Fan beyond a true/false tally. Every
personal-scale figure is reduced to a count before it reaches stdout, because
probe output lands in a public Actions log.
"""

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fetch_csv import dice_graphql, dice_relay_id  # noqa: E402

# P1 + P4 + X2(TicketPool): everything that hangs off the event itself.
EVENT_QUERY = """
query ProbeEventFields($id: ID!) {
  node(id: $id) {
    ... on Event {
      name
      state
      onSaleDatetime
      announceDatetime
      offSaleDatetime
      startDatetime
      endDatetime
      updatedAt
      ticketPools { id name allocation }
      ticketTypes {
        name
        priceTierType
        faceValue
        price
        doorSalesPrice
        ticketPoolId
        totalTicketAllocationQty
        priceTiers { id name price faceValue allocation doorSalesPrice time }
      }
    }
  }
}
"""

# P2 + P3: one page of orders, with the fee decomposition and the channel.
ORDERS_QUERY = """
query ProbeOrderFields($eventId: ID!) {
  viewer {
    orders(first: 20, where: {eventId: {eq: $eventId}}) {
      totalCount
      edges {
        node {
          purchasedAt
          quantity
          salesChannel
          fullPrice
          total
          commission
          diceCommission
          fees { category dice promoter }
          ipCountry
          tickets {
            fullPrice
            total
            commission
            diceCommission
            fees { category dice promoter }
            ticketType { name }
            priceTier { name price allocation time }
            claimedAt
          }
        }
      }
    }
  }
}
"""

# P5. Selected alone, deliberately - see the PII rule in the docstring.
OPTIN_QUERY = """
query ProbeOptIn($eventId: ID!) {
  viewer {
    orders(first: 20, where: {eventId: {eq: $eventId}}) {
      edges { node { fan { optInPartners } } }
    }
  }
}
"""

# X2: two top-level collections nobody has opened. ReturnWhereInput and
# TicketTransferWhereInput both exist in the dump, so both are event-scopeable
# the same way orders is.
RETURNS_QUERY = """
query ProbeReturns($eventId: ID!) {
  viewer {
    returns(first: 20, where: {eventId: {eq: $eventId}}) {
      totalCount
      edges { node { id reason returnedAt } }
    }
  }
}
"""

TRANSFERS_QUERY = """
query ProbeTransfers($eventId: ID!) {
  viewer {
    ticketTransfers(first: 20, where: {eventId: {eq: $eventId}}) {
      totalCount
      edges { node { id transferredAt } }
    }
  }
}
"""

# The three dimensions dice_schema.json is missing. Cheap, and it retires the
# whole class of "the dump does not say".
INTROSPECT_QUERY = """
query FullIntrospection {
  __schema {
    types {
      name
      kind
      enumValues { name }
      inputFields { name type { name kind ofType { name kind } } }
      fields {
        name
        args { name type { name kind ofType { name kind } } }
      }
    }
  }
}
"""


def run(label, query, variables=None):
    """Run one query; report the error rather than dying, so one denial does
    not hide the other five answers."""
    print(f'\n{"=" * 68}\n{label}\n{"=" * 68}')
    try:
        # dice_graphql(token, query, variables) - token first.
        return dice_graphql(os.environ['DICE_TOKEN'], query, variables or {})
    except Exception as exc:  # noqa: BLE001 - a probe reports, it does not raise
        print(f'  ERROR: {exc}')
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('event', nargs='?', default='600413',
                    help='numeric DICE event id (default rennes_2026)')
    ap.add_argument('--introspect', action='store_true',
                    help='also dump enum values, input fields and field args')
    args = ap.parse_args()

    if not os.environ.get('DICE_TOKEN'):
        raise SystemExit('DICE_TOKEN not set')
    relay = dice_relay_id(args.event)
    print(f'event {args.event} -> {relay}')

    # ---- P1, P4, X2(TicketPool) ----
    d = run('P1 / P4 - event dates, ticket types, price tiers, pools',
            EVENT_QUERY, {'id': relay})
    if d:
        ev = (d.get('node') or {})
        for k in ('name', 'state', 'onSaleDatetime', 'announceDatetime',
                  'offSaleDatetime', 'startDatetime', 'endDatetime'):
            print(f'  {k:20} {ev.get(k)!r}')
        pools = ev.get('ticketPools') or []
        print(f'  ticketPools          {len(pools)}')
        for p in pools:
            print(f'      {p.get("name")!r} allocation={p.get("allocation")}')
        tts = ev.get('ticketTypes') or []
        print(f'  ticketTypes          {len(tts)}')
        for t in tts:
            tiers = t.get('priceTiers') or []
            print(f'      {t.get("name")!r}  priceTierType={t.get("priceTierType")!r} '
                  f'face={t.get("faceValue")} price={t.get("price")} '
                  f'alloc={t.get("totalTicketAllocationQty")} tiers={len(tiers)}')
            for tier in tiers:
                print(f'          tier {tier.get("name")!r} price={tier.get("price")} '
                      f'face={tier.get("faceValue")} alloc={tier.get("allocation")} '
                      f'time={tier.get("time")!r}')

    # ---- P2, P3 ----
    d = run('P2 / P3 - fee decomposition and sales channel', ORDERS_QUERY,
            {'eventId': relay})
    if d:
        edges = ((d.get('viewer') or {}).get('orders') or {}).get('edges') or []
        total = ((d.get('viewer') or {}).get('orders') or {}).get('totalCount')
        print(f'  orders totalCount    {total}, sampled {len(edges)}')
        channels, cats, claimed = Counter(), Counter(), Counter()
        shown = 0
        for e in edges:
            n = e.get('node') or {}
            channels[n.get('salesChannel')] += 1
            for f in (n.get('fees') or []):
                cats[f.get('category')] += 1
            for t in (n.get('tickets') or []):
                claimed['null' if t.get('claimedAt') is None else 'set'] += 1
                for f in (t.get('fees') or []):
                    cats[f.get('category')] += 1
                if shown < 2:
                    shown += 1
                    print(f'  ticket: full={t.get("fullPrice")} total={t.get("total")} '
                          f'commission={t.get("commission")} dice={t.get("diceCommission")}')
                    print(f'      fees={t.get("fees")}')
                    print(f'      priceTier={t.get("priceTier")}')
        print(f'  salesChannel values  {dict(channels)}')
        print(f'  fee categories seen  {dict(cats)}')
        print(f'  ticket.claimedAt     {dict(claimed)}  (Q6: expected all null pre-event)')
        print(f'  ipCountry present    {sum(1 for e in edges if (e.get("node") or {}).get("ipCountry"))}/{len(edges)}')

    # ---- P5 ----
    d = run('P5 - Fan.optInPartners, selected alone (no other Fan field)',
            OPTIN_QUERY, {'eventId': relay})
    if d:
        edges = ((d.get('viewer') or {}).get('orders') or {}).get('edges') or []
        tally = Counter((e.get('node') or {}).get('fan', {}).get('optInPartners')
                        if (e.get('node') or {}).get('fan') else 'no fan'
                        for e in edges)
        print(f'  readable, tally over {len(edges)} order(s): {dict(tally)}')
        print('  (a tally only - no Fan field other than optInPartners was requested)')

    # ---- X2 ----
    d = run('X2 - viewer.returns', RETURNS_QUERY, {'eventId': relay})
    if d:
        r = (d.get('viewer') or {}).get('returns') or {}
        edges = r.get('edges') or []
        print(f'  totalCount           {r.get("totalCount")}, sampled {len(edges)}')
        print(f'  reasons seen         {dict(Counter((e.get("node") or {}).get("reason") for e in edges))}')
        for e in edges[:3]:
            n = e.get('node') or {}
            print(f'      returnedAt={n.get("returnedAt")!r} reason={n.get("reason")!r}')

    d = run('X2 - viewer.ticketTransfers', TRANSFERS_QUERY, {'eventId': relay})
    if d:
        t = (d.get('viewer') or {}).get('ticketTransfers') or {}
        edges = t.get('edges') or []
        print(f'  totalCount           {t.get("totalCount")}, sampled {len(edges)}')
        for e in edges[:3]:
            print(f'      transferredAt={(e.get("node") or {}).get("transferredAt")!r}')

    # ---- the missing introspection dimensions ----
    if args.introspect:
        d = run('X1 - enum values, input fields and field args', INTROSPECT_QUERY)
        if d:
            types = ((d.get('__schema') or {}).get('types')) or []
            out = Path('api_output/dice_schema_full.json')
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(d, indent=1), encoding='utf-8')
            print(f'  written {out} ({out.stat().st_size / 1024:.0f} KB)')
            for t in types:
                if t.get('enumValues') and not t['name'].startswith('__'):
                    print(f"  ENUM {t['name']}: {[v['name'] for v in t['enumValues']]}")
            for t in types:
                if t['name'] in ('ReturnWhereInput', 'TicketTransferWhereInput',
                                 'OrderWhereInput') and t.get('inputFields'):
                    print(f"  INPUT {t['name']}: {[f['name'] for f in t['inputFields']]}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
