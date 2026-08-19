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

REACHED, ON 2026-08-18, IN THE OPPOSITE DIRECTION
--------------------------------------------------
The paragraph below was true when written and the CUTOVER inverted it. It is
kept rather than rewritten because the reasoning is still the reasoning; only
which pipeline owns which directory changed.

Run 32166756184 took the path. The commit job's new "a new event widens every
other page's menu" step handed this script six ROOT pages, the `'.' -> prod`
mapping rebuilt them with `build_dashboard.py`, and `check_build_stamp` failed
all six with "no build stamp. It predates the stamp". Same defect, same
detection, opposite direction - production over pass 0 rather than pass 0 over
production. Nothing shipped: the gate runs before `git commit`, so the run
failed with the branch untouched.

The mapping is now derived from `pages.pass0_dir()` instead of restated, so it
follows the cutover instead of having to be remembered.

WHAT THE ORIGINAL PARAGRAPH SAID, AND WHY IT STOPPED BEING TRUE
----------------------------------------------------------------
**No bad page ever shipped.** All six root pages carry `const D=` 0 times and a
`<!-- shared: -->` stamp exactly once, which is the production shape; a v2 build
is the reverse. The bug needs a push race whose conflict lands in a ROOT `.html`,
and every race so far conflicted only in `v2/`. The path existed and was never
taken.

Those counts are the PRE-CUTOVER root pages. Post-cutover they are exactly
reversed - a root page now carries `const D=` once and `<!-- shared-v2: -->`
once - which is what makes the same two markers still the right measurement,
read the other way round. Measured on the fix:

    before   rebuilding geneve.html ... via build_dashboard.py
             const D= 0   shared-v2 0   shared 1
    after    rebuilding geneve.html ... via build_v2.py
             const D= 1   shared-v2 1   shared 0

Worth stating because "fixed" does not answer the question the next reader
actually has, which is whether anything downstream is holding bad data.

And it would not have survived long: a v2 build of a production page LOSES the
build stamp, because pass 0's `</nav>`..`</body>` seam splices away the comment
`postprocess_html` writes just before `</body>`. `check_build_stamp.py` runs in
the workflow and fails on a page with no stamp - measured, by running the
pre-fix script and then the check:

    FAIL  rennes.html: no build stamp.  ->  exit 1

So the blast radius was a failed build, not a silently wrong dashboard. That is
luck rather than design - the stamp exists to catch stale shared assets, not
this - but it is the difference between an incident and an inconvenience.

A CORRECTION TO THIS FILE'S OWN FIRST EVIDENCE
-----------------------------------------------
The commit that fixed this cited "dashboard_redesign.css and dept-tabs-bg were
in it afterwards". **Both markers were wrong**, and the bug is real anyway:

  - `dept-tabs-bg` appears TWICE in a correct production page. It is not a v2
    marker at all, so counting it proves nothing.
  - `dashboard_redesign.css` appears ZERO times in a v2 build, because pass 0
    INLINES the sheet's contents rather than linking it.

The sound markers are the two above: `const D=` goes 0 -> 1 and the build stamp
goes 1 -> 0. Same conclusion, honest evidence. Third time in one session that a
predicate sitting next to a claim reported on something adjacent to it - see
HANDOFF_CC3 section 6 - and the first where it did not change the verdict, only
the proof. A right conclusion resting on a wrong measurement is still a thing to
correct, because the measurement is what the next person will re-run.
"""

import argparse
import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import pages as pages_mod  # noqa: E402  - `pages` is a local name in main()


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
        #
        # THE MAPPING WAS A CONSTANT AND THE CUTOVER MOVED WHAT IT POINTED AT.
        # `{'v2': 'v2', '.': 'prod'}` was right while pass 0 published to `v2/`
        # and production owned the root. CUTOVER §3(a) moved pass 0 TO THE ROOT
        # and retired the production pages into `legacy/`, which inverts the
        # second entry: a root page is now a PASS 0 page, and rebuilding one
        # with build_dashboard.py writes the retired design over the live URL.
        #
        # This is the same defect this file was written to fix, pointing the
        # other way, and the docstring above predicted its own symptom in the
        # opposite direction: "a v2 build of a production page LOSES the build
        # stamp". A production build of a v2 page loses the V2 stamp, and
        # check_build_stamp reports it identically -
        #   FAIL  rennes.html: no build stamp. It predates the stamp
        # - which is exactly what run 32166756184 printed for all six pages.
        #
        # So the location is derived rather than restated. `pages.pass0_dir()`
        # is the one definition of where pass 0 publishes, and it is what every
        # other check already asks.
        pass0 = pages_mod.pass0_dir().relative_to(ROOT).as_posix()
        kind = {'v2': 'v2', pass0: 'v2'}.get(parent)
        # `legacy/` is the frozen archive. It has no builder and must never get
        # one: rebuilding it from live data would restate today's numbers under
        # a banner saying they stopped moving. The workflow's rebase handler
        # already refuses `legacy/*` before it reaches this script; refusing
        # here too means the guarantee does not depend on that caller.
        if parent == 'legacy':
            unknown.append((p, 'legacy/ is a frozen archive, not a rebuildable '
                               'artefact - it has no builder by design'))
            continue
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
            # CURRENTLY UNREACHABLE, and deliberately kept. Since the cutover no
            # parent maps to 'prod': pass 0 owns the root and `legacy/` is
            # refused above, so there is no location a production build belongs
            # to. Left in place because the branch is correct for the pipeline
            # it describes and reconstructing it would be the expensive way to
            # get it back - the same reasoning check_cutover_write.py records
            # for keeping its T1/T2 body. It belongs in cleanup, not here.
            #
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
