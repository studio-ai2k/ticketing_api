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

WHICH BUILDER, AND WHY THE PATH DECIDES
---------------------------------------
`v2/rennes.html` and `rennes.html` are DIFFERENT PAGES BUILT BY DIFFERENT
PIPELINES that happen to share a basename. The first version of this file keyed
its lookup on the basename alone and ran `build_v2.py` for whatever it was
handed, so `rebuild_pages.py rennes.html` wrote a REDESIGN page over the
PRODUCTION one - measured, not reasoned: the file's hash moved and
`dashboard_redesign.css` and `dept-tabs-bg` were in it afterwards.

That is reachable from the workflow, which passes every conflicted `*.html`
path straight through. So the recovery path for a push race could publish a v2
page to a production URL - strictly worse than the text merge it replaced, and
during cutover it would land in the exact window where someone is watching the
production page to decide whether cutover worked.

The parent directory now picks the builder:

    v2/<name>   pass 0            build_v2.py
    <name>      production        build_dashboard.py then postprocess_html.py

Anything else is refused, for the same reason an unmapped basename is refused.
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
        rel = Path(p)
        eid = pages.get(rel.name)
        parent = rel.parent.as_posix()
        # The BASENAME says which event; the PARENT says which pipeline. Both
        # have to resolve, and an unrecognised parent is refused rather than
        # defaulted - defaulting is what wrote a v2 page over production.
        kind = {'v2': 'v2', '.': 'prod'}.get(parent)
        if not eid or not kind:
            unknown.append((p, 'no active event owns this filename' if not eid
                            else f'unrecognised location {parent!r}'))
            continue
        jobs.append((eid, p, kind))

    if unknown:
        # NOT a warning. An unmapped path means the caller is asking to rebuild
        # something this script cannot generate, and the caller's fallback is a
        # text merge. Refusing loudly is the point.
        print('cannot rebuild - these paths do not name a page this can build:')
        for p, why in unknown:
            print(f'  {p}  ({why})')
        return 2

    rc = 0
    for eid, path, kind in jobs:
        csv_path = ROOT / 'data' / f'{eid}_merged.csv'
        if not csv_path.exists():
            print(f'FAIL {path}: no {csv_path.relative_to(ROOT)} to build from')
            rc = 1
            continue
        target = ROOT / path
        builder = 'build_v2.py' if kind == 'v2' else 'build_dashboard.py'
        print(f'rebuilding {path} from {eid} ({csv_path.name}) via {builder}')
        r = subprocess.run(
            [sys.executable, str(ROOT / 'scripts' / builder),
             '--event', eid, '--csv', str(csv_path), '--out', str(target),
             '--config', a.config],
            capture_output=True, text=True)
        if r.returncode:
            print(f'FAIL {path}: {builder} exited {r.returncode}')
            print((r.stderr or r.stdout)[-800:])
            rc = 1
            continue
        if kind == 'prod':
            # build_v2 runs postprocess itself, on its temporary base. The
            # production path has to run it here or the page ships without the
            # nav shell, the vendored stylesheet and the build stamp.
            r = subprocess.run(
                [sys.executable, str(ROOT / 'scripts' / 'postprocess_html.py'),
                 str(target)],
                capture_output=True, text=True)
            if r.returncode:
                print(f'FAIL {path}: postprocess_html exited {r.returncode}')
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
        # The marker has to be one THIS pipeline emits. `const D=` is pass 0's
        # payload and a production page has never carried it (0 in rennes.html,
        # 1 in v2/rennes.html), so checking it on both would have passed v2 and
        # failed every production rebuild - the check reporting on a page shape
        # it was not looking at.
        want = 'const D=' if kind == 'v2' else '<!-- shared:'
        if '<<<<<<<' in text or '>>>>>>>' in text:
            print(f'FAIL {path}: conflict markers survived the rebuild')
            rc = 1
        elif want not in text:
            print(f'FAIL {path}: rebuilt file carries no {want!r} - the '
                  f'{kind} build did not produce a complete page')
            rc = 1
    return rc


if __name__ == '__main__':
    sys.exit(main())
