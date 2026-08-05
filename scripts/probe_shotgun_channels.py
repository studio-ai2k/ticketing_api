#!/usr/bin/env python3
"""
Break Shotgun tickets down by deal_channel (and other provenance fields) to
find DICE-imported tickets.

Bordeaux Jun 2026 is co-hosted and its Shotgun back-office shows 17,409
tickets, but the API returned 26,984 - a ~9,575 gap that closely matches the
9,329 tickets we also fetch straight from DICE. If Shotgun's API surfaces
DICE-imported tickets under a distinct channel, we are counting those twice
whenever an event has both a shotgun_event_id and a dice_mio_id.

This is read-only. It counts every ticket by deal_channel, cross-tabbed against
ticket_status, and also reports utm_source / payment_method / deal_visibilities
so an import channel is identifiable even if it is not named "distributor".

    python scripts/probe_shotgun_channels.py bordeaux_2026 rennes_2026
"""

import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fetch_csv import (  # noqa: E402
    SHOTGUN_VALID_STATUSES,
    fetch_shotgun_pages,
    load_event_config,
    log,
    resolve_shotgun_account,
)

DEFAULT_EVENTS = ['bordeaux_2026', 'rennes_2026']
CONFIG = str(Path(__file__).resolve().parent.parent / 'event_config.csv')


def summarise(event_id):
    cfg = load_event_config(CONFIG, event_id)
    sg_id = cfg['shotgun_event_id']
    if not sg_id:
        log(f"\n### {event_id}: no shotgun_event_id, skipping")
        return

    account, token, organizer_id = resolve_shotgun_account(event_id)
    if not token:
        log(f"\n### {event_id}: no token for account '{account}', skipping")
        return

    log(f"\n### {event_id} (shotgun {sg_id}, {account}/{organizer_id}, dice={cfg['dice_mio_id'] or 'none'})")

    total = 0
    by_channel = Counter()
    by_channel_valid = Counter()
    status_by_channel = defaultdict(Counter)
    utm_by_channel = defaultdict(Counter)
    pay_by_channel = defaultdict(Counter)
    vis_by_channel = defaultdict(Counter)

    for raw in fetch_shotgun_pages(token, organizer_id, sg_id):
        total += 1
        channel = str(raw.get('deal_channel') or '(none)')
        status = str(raw.get('ticket_status') or '(none)').lower()
        by_channel[channel] += 1
        status_by_channel[channel][status] += 1
        if status in SHOTGUN_VALID_STATUSES:
            by_channel_valid[channel] += 1
        utm_by_channel[channel][str(raw.get('utm_source') or '(none)')] += 1
        pay_by_channel[channel][str(raw.get('payment_method') or '(none)')] += 1
        vis = raw.get('deal_visibilities')
        vis_by_channel[channel][','.join(vis) if isinstance(vis, list) else str(vis)] += 1

    log(f"\n  raw tickets: {total}")
    log(f"  {'deal_channel':<22} {'all':>8} {'valid/resold':>13}")
    log(f"  {'-' * 22} {'-' * 8} {'-' * 13}")
    for channel, count in by_channel.most_common():
        log(f"  {channel:<22} {count:>8} {by_channel_valid[channel]:>13}")
    log(f"  {'TOTAL':<22} {total:>8} {sum(by_channel_valid.values()):>13}")

    log("\n  provenance per channel:")
    for channel, _ in by_channel.most_common():
        log(f"    {channel}:")
        log(f"      status:       {dict(status_by_channel[channel].most_common(6))}")
        log(f"      utm_source:   {dict(utm_by_channel[channel].most_common(6))}")
        log(f"      payment:      {dict(pay_by_channel[channel].most_common(6))}")
        log(f"      visibilities: {dict(vis_by_channel[channel].most_common(4))}")


def main():
    for event_id in (sys.argv[1:] or DEFAULT_EVENTS):
        summarise(event_id)


if __name__ == '__main__':
    main()
