#!/usr/bin/env python3
"""
Diagnostic: why do Rennes 2026 DICE tickets all have claimedAt = null, and what
date field could stand in for the purchase date?

Read-only. Runs live introspection against the DICE partners endpoint and prints
what it finds. Not part of the fetch pipeline.

    DICE_TOKEN=... python scripts/dice_diagnose.py
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fetch_csv import DICE_API, dice_graphql, dice_relay_id  # noqa: E402

EVENT_NUMERIC_ID = '600413'

FIELD_ARGS_QUERY = """
query TypeArgs($name: String!) {
  __type(name: $name) {
    name
    fields {
      name
      args { name type { kind name ofType { kind name ofType { kind name } } } }
      type { kind name ofType { kind name } }
    }
    inputFields {
      name
      type { kind name ofType { kind name ofType { kind name } } }
    }
  }
}
"""


def type_name(t):
    while t and not t.get('name'):
        t = t.get('ofType')
    return (t or {}).get('name', '?')


def describe(token, name):
    data = dice_graphql(token, FIELD_ARGS_QUERY, {'name': name})
    t = data.get('__type')
    if not t:
        print(f"\n=== {name}: NOT IN SCHEMA ===")
        return None
    print(f"\n=== {name} ===")
    for f in (t.get('fields') or []):
        args = ', '.join(f"{a['name']}: {type_name(a['type'])}" for a in (f.get('args') or []))
        print(f"  {f['name']}({args}) -> {type_name(f['type'])}")
    for f in (t.get('inputFields') or []):
        print(f"  input {f['name']}: {type_name(f['type'])}")
    return t


def main():
    token = os.environ.get('DICE_TOKEN', '').strip()
    if not token:
        raise SystemExit('DICE_TOKEN is not set')

    print(f"endpoint: {DICE_API}")
    print(f"event   : {EVENT_NUMERIC_ID} -> {dice_relay_id(EVENT_NUMERIC_ID)}")

    for name in ('Viewer', 'OrderWhereInput', 'TicketWhereInput', 'Ticket', 'Order', 'Event'):
        describe(token, name)

    # How many tickets actually carry a claimedAt? Sample the first page.
    print("\n=== claimedAt sample (first 20 tickets) ===")
    sample = dice_graphql(token, """
      query Sample($eventId: ID!) {
        node(id: $eventId) {
          ... on Event {
            tickets(first: 20) {
              totalCount
              edges { node { id claimedAt ticketType { name } } }
            }
          }
        }
      }
    """, {'eventId': dice_relay_id(EVENT_NUMERIC_ID)})
    conn = ((sample.get('node') or {}).get('tickets') or {})
    print(f"totalCount: {conn.get('totalCount')}")
    claimed = 0
    for edge in (conn.get('edges') or []):
        node = edge.get('node') or {}
        if node.get('claimedAt'):
            claimed += 1
        print(f"  {node.get('id')}  claimedAt={node.get('claimedAt')!r}  {(node.get('ticketType') or {}).get('name')}")
    print(f"claimed in sample: {claimed}/20")


if __name__ == '__main__':
    main()
