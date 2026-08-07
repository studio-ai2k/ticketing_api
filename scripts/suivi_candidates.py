#!/usr/bin/env python3
"""
Build the comparison-candidate payload for the Suivi des ventes selector.

Emits, per dashboard, one entry per event the table can be compared against:
its name, its daily series, and the two anchors the client needs to line that
series up with the rows on screen.

    python scripts/suivi_candidates.py --event epk_2026 --out payload.json

WHY THIS DOES NOT TOUCH run.py
------------------------------
Two things are needed and neither requires it.

The **series** is `is_paid == 1` grouped by `order_date`, split by platform,
with revenue summed from `price`. All four are literal columns of the
11-column merged CSV; run.py's ticket classification never enters. Revenue is
`price`, the net figure, because that is what run.py's own weekly rows sum -
using `gross_price` would produce numbers that disagree with the € figures
already on the page.

The **daily offset** is a closed form over `event_date_first`, proven equal to
run.py's `_prev_match_dow` rather than reimplementing its traversal, and
checked against it exhaustively by verify/check_offset.py. See the handoff for
the derivation.

TWO GRAINS, TWO MAPPINGS - this is the part the spec did not have
----------------------------------------------------------------
The daily and weekly tables line up their two columns by different rules, so a
candidate needs two anchors, not one:

  daily   run.py's _prev_match_dow: same J-X, then snapped to the same weekday.
          Collapses to  matched = row_date - offset  with offset constant.

  weekly  no weekday snap and no offset at all. Each side buckets its own
          tickets by `(its own event_date_first - order_date).days // 7`, so
          week N on the left is week N of the candidate's campaign. The client
          re-buckets the candidate series by `first` rather than shifting it.

So every candidate carries BOTH `offset` (daily) and `first` (weekly). Using
the offset for the weekly grain would silently mis-align every row.
"""

import argparse
import base64  # noqa: F401  (kept: DICE relay ids elsewhere use the same import list)
import csv
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LIVE_DIR = REPO / 'data'
ARCHIVE_DIR = REPO / 'csv_database'


def signed_mod7(gap):
    """The signed representative of `gap` mod 7, in [-3, 3]."""
    r = gap % 7
    return r if r <= 3 else r - 7


def daily_offset(current_first, candidate_first):
    """
    Days to subtract from a current-side row date to reach the candidate's
    matched date. Constant per pair - see the handoff for why.
    """
    gap = (current_first - candidate_first).days
    return gap - signed_mod7(gap)


def load_config(path):
    """event_id -> {name, days, capacity, status, compare_to} from the config."""
    events = {}
    for row in csv.DictReader(open(path, encoding='utf-8-sig')):
        eid = (row.get('event_id') or '').strip()
        if not eid:
            continue
        e = events.setdefault(eid, {
            'name': (row.get('event_name') or '').strip(),
            'days': [], 'capacity': 0,
            'status': (row.get('status') or '').strip(),
            'compare_to': (row.get('compare_to') or '').strip(),
        })
        if not e['name']:
            e['name'] = (row.get('event_name') or '').strip()
        day = (row.get('day_date') or '').strip()
        if day:
            try:
                e['days'].append(date.fromisoformat(day))
            except ValueError:
                # A day_date that will not parse is a config error, not a
                # reason to silently drop the event from the dropdown.
                raise SystemExit(f'{eid}: unparseable day_date {day!r}')
        try:
            e['capacity'] += int((row.get('day_capacity') or '0').strip() or 0)
        except ValueError:
            pass
    for e in events.values():
        e['first'] = min(e['days']) if e['days'] else None
        e['last'] = max(e['days']) if e['days'] else None
    return events


def series_path(event_id):
    """Where this event's merged CSV lives, or None if it has no data."""
    live = LIVE_DIR / f'{event_id}_merged.csv'
    if live.exists():
        return live
    archive = ARCHIVE_DIR / event_id / f'{event_id}_merged.csv'
    if archive.exists():
        return archive
    return None


def aggregate(path):
    """
    {'YYYY-MM-DD': {'n', 'sg', 'dice', 'rev'}} over paid tickets.

    Mirrors _generate_suivi_v3's own accounting: is_paid == 1 only, one row per
    ticket, revenue from `price`.
    """
    by_date = defaultdict(lambda: {'n': 0, 'sg': 0, 'dice': 0, 'rev': 0.0})
    with open(path, newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            if (row.get('is_paid') or '').strip() != '1':
                continue
            day = (row.get('order_date') or '').strip()[:10]
            if not day:
                continue
            e = by_date[day]
            e['n'] += 1
            if row.get('platform') == 'Shotgun':
                e['sg'] += 1
            elif row.get('platform') == 'DICE':
                e['dice'] += 1
            try:
                # `price`, NOT `gross_price`. run.py's weekly rows sum
                # t['price'], so gross would put figures on the page that
                # disagree with the € column already rendered beside them.
                # Cross-checked: 17 of 18 weekly rows on epk reproduce both
                # columns exactly with `price`. gross_price is the obvious
                # wrong choice for whoever touches this next.
                e['rev'] += float(row.get('price') or 0)
            except ValueError:
                pass
    return {d: {**v, 'rev': round(v['rev'], 2)} for d, v in sorted(by_date.items())}


def family(event_id):
    """`epk_2026` -> `epk`, `bordeaux_oct_2026` -> `bordeaux_oct`."""
    parts = event_id.rsplit('_', 1)
    return parts[0] if len(parts) == 2 and parts[1].isdigit() else event_id


def build(event_id, config_path, today=None):
    """The payload for one dashboard. Returns a JSON-ready dict."""
    events = load_config(config_path)
    if event_id not in events:
        raise SystemExit(f'{event_id} not in {config_path}')
    me = events[event_id]
    if not me['first']:
        raise SystemExit(f'{event_id} has no day_date rows, so no anchor')

    today = today or date.today()
    reference = me['compare_to']
    mine = family(event_id)

    candidates = []
    for cid, e in sorted(events.items()):
        if cid == event_id or not e['first']:
            continue
        path = series_path(cid)
        if not path:
            # ~34 config rows are placeholders with no data. A greyed-out
            # option is noise; the gap belongs in a data inventory.
            continue
        s = aggregate(path)
        if not s:
            continue
        if family(cid) == mine:
            group = 'edition'
        elif e['last'] and e['last'] >= today:
            group = 'live'
        else:
            group = 'past'
        candidates.append({
            'id': cid,
            'name': e['name'] or cid,
            'group': group,
            'reference': cid == reference,
            # Daily grain: shift the row date by this.
            'offset': daily_offset(me['first'], e['first']),
            # Weekly grain: re-bucket by weeks before THIS date. Not derivable
            # from `offset` - the two grains align differently.
            'first': e['first'].isoformat(),
            'capacity': e['capacity'],
            'days': len(s),
            'series': s,
        })

    # The viewed event's own series ships too. The right-hand column needs it
    # for the revenue figures, and it is never a candidate - you cannot compare
    # an event against itself.
    own_path = series_path(event_id)
    own = aggregate(own_path) if own_path else {}

    return {
        'event': event_id,
        'name': me['name'],
        'first': me['first'].isoformat(),
        'capacity': me['capacity'],
        'reference': reference,
        'own_series': own,
        'candidates': candidates,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--event', required=True)
    ap.add_argument('--config', default=str(REPO / 'event_config.csv'))
    ap.add_argument('--out', default=None, help='write JSON here (default stdout)')
    args = ap.parse_args()

    payload = build(args.event, args.config)
    text = json.dumps(payload, separators=(',', ':'), ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text, encoding='utf-8')
        print(f'{args.event}: {len(payload["candidates"])} candidate(s), '
              f'{len(text) / 1024:.1f} KB', file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
