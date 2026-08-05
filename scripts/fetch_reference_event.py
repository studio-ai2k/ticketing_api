#!/usr/bin/env python3
"""
Fetch a past event into csv_database/ as a historical baseline, folding in any
presale/child events that point at it via merge_into.

run.py merges merge_into children into their parent when building the current
year; a reference CSV has to be assembled the same way or the year-over-year
comparison comes up short by the presale.

    python scripts/fetch_reference_event.py paris_xxl_2025

Writes csv_database/<event_id>/<event_id>_merged.csv.
"""

import csv
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import fetch_csv as F  # noqa: E402

CONFIG = BASE_DIR / 'event_config.csv'


def merge_into_children(parent_id):
    """event_ids whose merge_into points at parent_id."""
    children = []
    with open(CONFIG, 'r', encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            eid = (row.get('event_id') or '').strip()
            if not eid or not (row.get('event_name') or '').strip():
                continue
            if (row.get('merge_into') or '').strip() == parent_id:
                children.append(eid)
    return children


def fetch_one(event_id, out_path):
    """Run the normal fetch for one event; returns its rows (empty on failure)."""
    F.log(f"\n{'=' * 62}\nFETCHING {event_id}\n{'=' * 62}")
    try:
        F.main(['--event', event_id, '--config', str(CONFIG), '--out', str(out_path)])
    except SystemExit as exc:
        if exc.code not in (0, None):
            F.log(f"   ⚠ {event_id} failed: {exc}")
            return []
    except Exception as exc:
        F.log(f"   ⚠ {event_id} failed: {type(exc).__name__}: {exc}")
        return []

    if not Path(out_path).exists():
        return []
    with open(out_path, 'r', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def main():
    if len(sys.argv) < 2:
        raise SystemExit('usage: fetch_reference_event.py <event_id>')
    parent = sys.argv[1]

    children = merge_into_children(parent)
    F.log(f"Reference event: {parent}")
    F.log(f"merge_into children: {', '.join(children) if children else '(none)'}")

    tmp = Path(tempfile.mkdtemp(prefix='ref_'))
    all_rows = []
    per_event = {}
    for event_id in [parent] + children:
        rows = fetch_one(event_id, tmp / f'{event_id}.csv')
        per_event[event_id] = len(rows)
        all_rows.extend(rows)

    if not all_rows:
        raise SystemExit(f"No tickets fetched for {parent} - refusing to write an empty reference")

    all_rows.sort(key=lambda r: (r.get('order_date') or '', r.get('order_datetime') or ''))

    out_dir = BASE_DIR / 'csv_database' / parent
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f'{parent}_merged.csv'
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=F.CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(all_rows)

    F.log(f"\n{'=' * 62}")
    for event_id, count in per_event.items():
        F.log(f"  {event_id:<28} {count:>7} tickets")
    F.log(f"  {'TOTAL':<28} {len(all_rows):>7} tickets")
    F.log(f"✅ Wrote {out_path}")


if __name__ == '__main__':
    main()
