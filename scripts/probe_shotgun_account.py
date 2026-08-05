#!/usr/bin/env python3
"""
Which Shotgun organizer account owns an event?

bordeaux_2026 (505434) and epk_2026 (535882) both returned zero tickets under
the account they are mapped to, while the same tokens worked for other events.
A valid token with the wrong organizer_id appears to return an empty set rather
than an error, so a wrong mapping looks identical to "no sales".

This tries every (token, organizer_id) combination against each event and
reports which one actually returns tickets. Read-only, first page only.

    python scripts/probe_shotgun_account.py [event_id ...]
"""

import os
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fetch_csv import SHOTGUN_API, extract_shotgun_tickets, http_json, redact  # noqa: E402

DEFAULT_EVENTS = ['505434', '535882']

ACCOUNTS = [
    ('episode', 'SHOTGUN_TOKEN_EPISODE', '171835'),
    ('sonora', 'SHOTGUN_TOKEN_SONORA', '207784'),
]


def probe(event_id, account, token, organizer_id):
    query = urllib.parse.urlencode({
        'token': token,
        'organizer_id': organizer_id,
        'event_id': event_id,
    })
    url = f"{SHOTGUN_API}?{query}"
    try:
        payload = http_json(url)
    except Exception as exc:
        return f"ERROR: {str(exc)[:160]}"

    tickets = extract_shotgun_tickets(payload)
    if not tickets:
        return "0 tickets"

    first = tickets[0] if isinstance(tickets[0], dict) else {}
    name = first.get('event_name', '?')
    has_next = bool((payload.get('pagination') or {}).get('next')) if isinstance(payload, dict) else False
    return f"{len(tickets)} tickets on page 1 (more pages: {has_next}) — event_name={name!r}"


def main():
    events = sys.argv[1:] or DEFAULT_EVENTS

    tokens = {}
    for account, env_name, _ in ACCOUNTS:
        value = os.environ.get(env_name, '').strip()
        if not value:
            print(f"⚠ {env_name} is not set — skipping the {account} account")
        tokens[account] = value

    for event_id in events:
        print(f"\n=== event {event_id} ===")
        for account, env_name, organizer_id in ACCOUNTS:
            token = tokens.get(account)
            if not token:
                print(f"  {account:8} (org {organizer_id}): SKIPPED (no token)")
                continue
            result = probe(event_id, account, token, organizer_id)
            print(f"  {account:8} (org {organizer_id}): {result}")


if __name__ == '__main__':
    main()
