#!/usr/bin/env python3
"""
Does DICE_TOKEN have access to a given event?

DICE events can live under an account the token does not cover (Genève 2026 is
listed under "Collaborators", not Episode). A token without access does not
error - viewer.orders simply returns an empty connection, which reads exactly
like "no sales". This asks two independent questions so the two are told apart:

  1. Can the token resolve the event node at all (name, date)?
  2. How many orders/tickets does viewer.orders return when scoped to it?

Answering 1 but not 2 means the token sees the event but not its sales.
Answering neither means the event belongs to another account and needs its own
token. Read-only, first page only.

    DICE_TOKEN=... python scripts/probe_dice_event.py 588085 [...]
"""

import base64
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fetch_csv import dice_graphql, dice_relay_id  # noqa: E402

DEFAULT_EVENTS = ['588085']

EVENT_QUERY = """
query ProbeEvent($id: ID!) {
  node(id: $id) {
    id
    ... on Event {
      name
      updatedAt
      tickets(first: 1) { totalCount }
    }
  }
}
"""

ORDERS_QUERY = """
query ProbeOrders($eventId: ID!) {
  viewer {
    orders(first: 25, where: {eventId: {eq: $eventId}}) {
      totalCount
      pageInfo { hasNextPage }
      edges {
        node {
          id
          purchasedAt
          quantity
          tickets { id fullPrice total ticketType { name } }
        }
      }
    }
  }
}
"""


def probe(token, numeric_id):
    relay = dice_relay_id(numeric_id)
    print(f"\n=== DICE event {numeric_id} ===")
    print(f"  relay id : {relay}  (decodes to {base64.b64decode(relay).decode()!r})")

    reachable = False
    event_tickets = None
    try:
        node = (dice_graphql(token, EVENT_QUERY, {'id': relay}) or {}).get('node')
    except Exception as exc:
        print(f"  event    : ERROR {str(exc)[:200]}")
    else:
        if not node:
            print("  event    : not visible to this token (node resolved to null)")
        else:
            reachable = True
            event_tickets = ((node.get('tickets') or {}).get('totalCount'))
            print(f"  event    : name={node.get('name')!r} updatedAt={node.get('updatedAt')!r} "
                  f"Event.tickets.totalCount={event_tickets}")

    try:
        conn = ((dice_graphql(token, ORDERS_QUERY, {'eventId': relay}).get('viewer') or {})
                .get('orders') or {})
    except Exception as exc:
        print(f"  orders   : ERROR {str(exc)[:200]}")
        return reachable, 0, event_tickets

    edges = conn.get('edges') or []
    tickets = sum(len((e.get('node') or {}).get('tickets') or []) for e in edges)
    print(f"  orders   : totalCount={conn.get('totalCount')} "
          f"page1={len(edges)} orders / {tickets} tickets "
          f"(more pages: {(conn.get('pageInfo') or {}).get('hasNextPage')})")
    for edge in edges[:5]:
        n = edge.get('node') or {}
        first = (n.get('tickets') or [{}])[0]
        print(f"    purchasedAt={n.get('purchasedAt')!r} qty={n.get('quantity')} "
              f"tickets={len(n.get('tickets') or [])} "
              f"type={(first.get('ticketType') or {}).get('name')!r} "
              f"fullPrice={first.get('fullPrice')} total={first.get('total')}")

    return reachable, conn.get('totalCount') or 0, event_tickets


def main():
    token = os.environ.get('DICE_TOKEN', '').strip()
    if not token:
        raise SystemExit('DICE_TOKEN is not set')

    results = {}
    for numeric_id in (sys.argv[1:] or DEFAULT_EVENTS):
        results[numeric_id] = probe(token, numeric_id)

    print("\n=== verdict ===")
    for numeric_id, (reachable, orders, event_tickets) in results.items():
        if orders:
            print(f"  {numeric_id}: ACCESSIBLE - {orders} orders. Safe to set as dice_mio_id.")
        elif reachable and event_tickets:
            print(f"  {numeric_id}: event is visible and reports {event_tickets} tickets, but "
                  f"viewer.orders returns none - the orders belong to another DICE account. "
                  f"A separate token for that account is needed.")
        elif reachable:
            print(f"  {numeric_id}: event visible, Event.tickets.totalCount="
                  f"{event_tickets!r}, 0 orders. No sales visible to this token.")
        else:
            print(f"  {numeric_id}: NOT ACCESSIBLE with this token - a separate DICE token "
                  f"for that account is needed.")


if __name__ == '__main__':
    main()
