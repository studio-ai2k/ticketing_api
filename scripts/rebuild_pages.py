#!/usr/bin/env python3
"""
Rebuild generated pages by NAME, for the one place git cannot be trusted.

    python3 scripts/rebuild_pages.py v2/rennes.html v2/geneve.html

WHY THIS EXISTS
---------------
The daily job's push can race the same job's previous run, or a human. Its retry
did a plain `git rebase`, which asks git to reconcile two INDEPENDENTLY
GENERATED 250 KB HTML pages by text. Git loses: run #46 hit content conflicts in
v2/bordeaux_oct.html, v2/geneve.html and v2/rennes.html, retried three times and
exited 1. Every check in that run had passed - it failed at the push.

The rule this project already states is "conflicts in generated pages are
resolved by REBUILDING from the mock, never hand-merged", and the workflow was
the one place that could not follow it. A text-merged page is a file no
generator produced, which is the same class of object as a hand-built preview.

WHICH CSV, AND WHY IT MATTERS
-----------------------------
Rebuilds read `data/<event>_merged.csv`. In the commit job that file is the
FRESHLY FETCHED one, carried in the build job's artifact - not the committed
copy. That distinction is the whole of a bug fixed one step earlier in this same
workflow: `build_series.py` read the committed CSV while `build_v2.py` got the
fetched one, and every commit shipped a series one fetch cycle behind its own
page. A rebase overwrites `data/` with origin's copies, so the caller must
restore the fetched CSVs BEFORE calling this. It refuses to guess.
"""

import argparse
import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def page_map(config):
    """{output filename: event_id} for every active event that has one."""
    out = {}
    for row in csv.DictReader(config.open(encoding='utf-8-sig')):
        eid = (row.get('event_id') or '').strip()
        name = (row.get('output_filename') or '').strip()
        if not eid or not name:
            continue
        if (row.get('status') or '').strip() != 'active':
            continue
        out.setdefault(name, eid)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('paths', nargs='+')
    ap.add_argument('--config', default=str(ROOT / 'event_config.csv'))
    a = ap.parse_args()

    pages = page_map(Path(a.config))
    jobs, unknown = [], []
    for p in a.paths:
        name = Path(p).name
        eid = pages.get(name)
        if not eid:
            unknown.append(p)
            continue
        jobs.append((eid, p, name))

    if unknown:
        # NOT a warning. An unmapped path means the caller is asking to rebuild
        # something this script cannot generate, and the caller's fallback is a
        # text merge. Refusing loudly is the point.
        print('cannot rebuild - no active event owns these paths:')
        for p in unknown:
            print(f'  {p}')
        return 2

    rc = 0
    for eid, path, name in jobs:
        csv_path = ROOT / 'data' / f'{eid}_merged.csv'
        if not csv_path.exists():
            print(f'FAIL {path}: no {csv_path.relative_to(ROOT)} to build from')
            rc = 1
            continue
        target = ROOT / path
        print(f'rebuilding {path} from {eid} ({csv_path.name})')
        r = subprocess.run(
            [sys.executable, str(ROOT / 'scripts' / 'build_v2.py'),
             '--event', eid, '--csv', str(csv_path), '--out', str(target),
             '--config', a.config],
            capture_output=True, text=True)
        if r.returncode:
            print(f'FAIL {path}: build_v2 exited {r.returncode}')
            print((r.stderr or r.stdout)[-800:])
            rc = 1
            continue
        # THE TOOL VERIFIES ITS OWN OUTPUT, because the caller cannot.
        # The workflow's other guard - "is anything still unresolved?" - is
        # nearly decorative here: `git checkout --ours` alone clears git's
        # conflict state, so that check passes even if this script never ran.
        # Found by running the simulation with this file missing: the sequence
        # reported "resolved" and completed the rebase having rebuilt nothing.
        # So exit status is the real guard, and it has to mean something.
        text = target.read_text(encoding='utf-8', errors='replace')
        if '<<<<<<<' in text or '>>>>>>>' in text:
            print(f'FAIL {path}: conflict markers survived the rebuild')
            rc = 1
        elif 'const D=' not in text:
            print(f'FAIL {path}: rebuilt file carries no payload')
            rc = 1
    return rc


if __name__ == '__main__':
    sys.exit(main())
