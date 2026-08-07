#!/usr/bin/env python3
"""
Generate the HTML dashboard from an API-fetched merged CSV.

run.py's current-year path expects raw platform exports (a DICE zip plus a
Shotgun CSV) and has no option for a pre-merged CSV, so this shim feeds the
merged rows in by replacing run.py's two file-loading functions at import time,
then calls run.main() unchanged. run.py itself is never modified.

Everything downstream - merge, metrics, comparison, template rendering - is
run.py's own code, so the dashboard is exactly what the production pipeline
would produce from the same tickets.

Mirrors the environment main.py sets up for its subprocess call (see
main.py:233-247): FESTIFLOW_RAW_DIR, FESTIFLOW_HISTORICAL_DIR,
FESTIFLOW_OUTPUT_DIR, and the historical merged CSV copied in from
csv_database/<compare_to>/.

    python scripts/build_dashboard.py --event rennes_2026 \
        --csv api_output/rennes_2026_merged.csv \
        --out api_output/rennes_2026.html
"""

import argparse
import csv
import inspect
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import suivi_candidates

BASE_DIR = Path(__file__).resolve().parent.parent


def _iso(value):
    """date -> 'YYYY-MM-DD', anything else -> None."""
    return value.isoformat() if hasattr(value, 'isoformat') else None


def read_config_field(config_path, event_id, field):
    """Read one event-level field for an event from event_config.csv."""
    with open(config_path, 'r', encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            if (row.get('event_id') or '').strip() == event_id and (row.get('event_name') or '').strip():
                return (row.get(field) or '').strip()
    return ''


def main():
    parser = argparse.ArgumentParser(description='Build the HTML dashboard from a merged CSV.')
    parser.add_argument('--event', default='rennes_2026')
    parser.add_argument('--csv', required=True, help='merged CSV produced by fetch_csv.py')
    parser.add_argument('--out', required=True, help='where to write the dashboard HTML')
    parser.add_argument('--config', default=str(BASE_DIR / 'event_config.csv'))
    args = parser.parse_args()

    merged_csv = Path(args.csv)
    if not merged_csv.exists():
        raise SystemExit(f"Merged CSV not found: {merged_csv}")

    with open(merged_csv, 'r', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit(f"Merged CSV is empty: {merged_csv}")
    print(f"Loaded {len(rows)} tickets from {merged_csv}")

    tmp = Path(tempfile.mkdtemp(prefix='festiflow_'))
    raw_dir = tmp / 'raw'
    historical_dir = tmp / 'historical'
    output_dir = tmp / 'output'
    for d in (raw_dir, historical_dir, output_dir):
        d.mkdir(parents=True)

    # Historical comparison reads the pre-merged, PII-free CSV for compare_to.
    # Raw exports are never copied here - same rule main.py follows.
    compare_to = read_config_field(args.config, args.event, 'compare_to')
    if compare_to:
        ref_folder = BASE_DIR / 'csv_database' / compare_to
        copied = 0
        if ref_folder.is_dir():
            for ref_file in ref_folder.iterdir():
                if ref_file.name.endswith('_merged.csv'):
                    shutil.copy(ref_file, historical_dir / ref_file.name)
                    copied += 1
        print(f"compare_to={compare_to}: copied {copied} historical merged CSV(s)")

    os.environ['FESTIFLOW_RAW_DIR'] = str(raw_dir)
    os.environ['FESTIFLOW_HISTORICAL_DIR'] = str(historical_dir)
    os.environ['FESTIFLOW_OUTPUT_DIR'] = str(output_dir)

    sys.path.insert(0, str(BASE_DIR))
    import run  # imported after the env vars above: run.py reads them at import

    # Feed the merged rows in place of raw-export parsing. run.py's merge step
    # calls process_shotgun_csv() for the current year and skips DICE when the
    # match has no zip; the rows already carry their own 'platform' column, so
    # the DICE/Shotgun split survives intact.
    run.auto_match_files = lambda raw: {
        'current': {'dice': None, 'shotgun': merged_csv},
        'previous': {'dice': None, 'shotgun': None},
    }
    run.process_shotgun_csv = lambda path: rows
    run.find_merge_into_files = lambda raw_dir_, config_path, event_id: []

    # The Suivi selector needs the anchors the Suivi table was built from:
    # which day the last complete row is, and the two event_date_first values
    # the comparison is aligned on. All three are arguments run.py already
    # passes to _generate_suivi_v3.
    #
    # So OBSERVE rather than change. The wrapper calls through untouched and
    # records what it saw. Nothing is re-derived, and the alternative - parsing
    # the rendered French dates back out of the HTML - is not merely fragile:
    # "Jeu 15 Déc" carries no year, and the daily table spans 232 rows across a
    # year boundary.
    #
    # Bound through the real signature rather than by position, so a new
    # argument in run.py cannot silently shift what gets captured.
    anchors = {}
    _suivi = run._generate_suivi_v3

    def _observe_suivi(*a, **kw):
        bound = inspect.signature(_suivi).bind(*a, **kw)
        bound.apply_defaults()
        arg = bound.arguments
        cfg, prev = arg.get('event_config') or {}, arg.get('event_config_prev') or {}
        anchors.update({
            'cutoff_date': _iso(arg.get('cutoff_date')),
            'cutoff_cumulative': _iso(arg.get('cutoff_cumulative')),
            'event_first': _iso(cfg.get('event_date_first')),
            'prev_first': _iso(prev.get('event_date_first')),
            'prev_event': prev.get('event_id'),
        })
        return _suivi(*a, **kw)

    run._generate_suivi_v3 = _observe_suivi

    sys.argv = ['run.py', '--event', args.event]
    run.main()

    if not anchors.get('cutoff_date'):
        raise SystemExit(
            '_generate_suivi_v3 was never called, or called without a '
            'cutoff_date - the Suivi anchors are the one thing that cannot be '
            'recovered afterwards, so this is a hard failure rather than a '
            'dashboard with a silently inert selector.')

    produced = output_dir / 'dashboard_FINAL.html'
    if not produced.exists():
        raise SystemExit(f"run.py finished but {produced} was not created")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(produced, out_path)

    # Sidecar for postprocess_html.py: the observed anchors plus the comparison
    # candidates. Written beside the HTML and consumed in the same build, so it
    # never needs committing.
    sidecar = out_path.with_suffix(out_path.suffix + '.suivi.json')
    try:
        payload = suivi_candidates.build(args.event, args.config)
    except SystemExit as exc:
        print(f"   ⚠ no comparison candidates: {exc}")
        payload = {'event': args.event, 'candidates': []}
    payload['anchors'] = anchors
    sidecar.write_text(json.dumps(payload, separators=(',', ':'),
                                  ensure_ascii=False), encoding='utf-8')
    print(f"   ↳ suivi sidecar: {len(payload['candidates'])} candidate(s), "
          f"{sidecar.stat().st_size / 1024:.0f} KB")

    print(f"\n✅ Dashboard written to {out_path} ({out_path.stat().st_size:,} bytes)")

    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
