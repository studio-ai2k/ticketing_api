#!/usr/bin/env python3
"""
Every production page must have been built from TODAY's shared assets.

    python verify/check_build_stamp.py

WHY
---
The daily job rebuilds only pages whose CSV changed. That is right for DATA — a
finished event's numbers genuinely cannot move — and wrong for PRESENTATION,
because presentation is shared. The trigger asks *"did this event's data
change"* when the question is *"did anything this page renders with change"*.

So `bordeaux.html` and `parisxxl.html` sat frozen at the build of the day their
events concluded, structurally exempt from every later change to shared code or
shared CSS. They missed the scroll lock (the page scrolled behind the gate) and
`overflow-x: clip` (the nav never stuck) — measured, not guessed: a diff against
a freshly-built pair showed 20 differing lines and exactly those two changes.

THE POINT: IT MUST CATCH A CHANGE NOBODY HAS THOUGHT OF YET
-----------------------------------------------------------
Which is why this compares a HASH and greps for nothing.

The previous version of this class of assertion demanded
`html,body{overflow-x:hidden` — the value D24 had removed by ruling — and kept
passing, because the pages it read still had it. "ALL ASSERTIONS PASSED" was a
true statement about the wrong expectation.

An assertion written in terms of a change we already know about catches that
change and nothing after it. This one knows only the SET of shared assets, not
their contents, so the next shared fix is covered the day it lands.

WHAT IS SHARED, AND WHY THAT LIST
---------------------------------
`postprocess_html.SHARED_ASSETS`, imported rather than restated. It is a
statement about what a production page is MADE OF — template, run.py,
postprocess, the vendored stylesheet and font links — and not about what has
shipped. The mock and `dashboard_redesign.css` are deliberately absent: they
reach v2 only. Auditing an exemption from the changelog reaches for the wrong
list; auditing it from the artefact's ingredients gives this one.

THE BLIND SPOT, NAMED RATHER THAN DISCOVERED
--------------------------------------------
The hash covers what is IN `SHARED_ASSETS`. **Nothing detects what is missing
from it.** A shared surface left out of that tuple moves no hash and fails no
page, and the failure state is indistinguishable from everything being fine.

That is #18's question pointed at this check: *what does this selector exclude,
and did anyone decide that?* Here the selector is a hand-maintained list, and
the evidence that the list is the fragile part rather than the hashing is in
this file's own history — the first proposed set had three entries and was
missing `dashboard_template.html`, `run.py` and `build_dashboard.py`. The hash
is mechanical and cannot be wrong; the list is a judgement and was.

Two mitigations, both priced and neither built:

  (a) DERIVE RATHER THAN DECLARE. Assert that every file `postprocess_html.py`
      and `build_dashboard.py` open or read appears in `SHARED_ASSETS`. That
      turns an omission from invisible into a failing test, and it is the same
      move as importing `PAGE_PATHS` rather than restating it: the check
      follows the code instead of agreeing with a copy of it.

  (b) REFERENCED BUT NOT READ AT BUILD TIME — `LOGO_ROND_JAUNE.png`,
      `upload.JPG`, the login background images. A page points at them, they
      are not in the set, and replacing one changes what a reader sees with no
      stamp movement. **That is a decision, not a gap:** they are content, not
      code, and a content swap is a deliberate act by whoever swaps the file,
      where a shared-code change is a side effect nobody is watching for. If
      that ever stops being true — an asset pipeline, a CDN, a generated image
      — they belong in the set.

SCOPE: THE SETS THAT EXIST — TWO NOW, ONE AFTER CUTOVER
--------------------------------------------------------
While `v2/` exists there are genuinely two page sets and both are audited.
After cutover the pages at root ARE pass 0's, production's set has no members,
and **the production half is not skipped — it is not constructed.** A clause
reporting "nothing to check, by design" is indistinguishable from one that is
working, which is the PINNED-when-empty shape this project has now found three
times: `CHECKLIST` saying PINNED with `PINNED = set()`, a `v2_pages` function
reading the repo root, and this.

AND THE NOTE THAT USED TO BE HERE WAS FALSE
--------------------------------------------
This said: *"`build_v2.py` runs unconditionally in the workflow, so a v2 page
cannot go stale — the exemption is a production-only property."* It was wrong
when written and wrong in exactly the way this check exists to catch — a
true-sounding statement about the wrong mechanism.

`build_v2.py` runs INSIDE the conditional step:

    .github/workflows/daily-dashboards.yml:239   - name: Build dashboard
                                          240     if: steps.change.outputs.changed == 'true'

So Trap #17 was live in v2, and worse than in production, because **v2 pages
carried no stamp at all**: `postprocess_html` writes it immediately before
`</body>`, which falls inside pass 0's `</nav>`..`</body>` seam and was spliced
away. There was nothing for a check to read, so the gap could not be seen from
the artefact — only from the workflow.

`v2/bordeaux.html` and `v2/parisxxl.html` are the two finished events. Their
CSVs never move, so the conditional never fires for them, and every shared
change between the redesign starting and now missed those two files.

The v2 set is a SUPERSET, not a different list: pass 0 builds on a
postprocessed page, so everything production is made of still applies, plus the
mock, the redesign sheet, and `build_v2` / `build_series` / `dashboard_payload`.
It is imported from `build_v2.V2_SHARED_ASSETS` for the same reason the
production one is imported rather than restated.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

import build_v2  # noqa: E402
import postprocess_html as pp  # noqa: E402
import pages  # noqa: E402 - CUTOVER 6.3
from pages import page_names  # noqa: E402

# CUTOVER 6.3. This was a hand-written six-name tuple - the same hazard as the
# page->event map that was wrong in all six rows, sitting in the layer whose job
# is to catch that. It now comes from event_config's active rows, so a seventh
# event is covered the day it is configured rather than the day someone
# remembers this file.
#
# LEGACY PAGES ARE OUT, AND NOT BECAUSE THEY ARE OLD. After cutover, `legacy/`
# will hold frozen copies carrying a stamp over a shared set that no longer
# exists. They are excluded because NO CONFIG ROW POINTS AT THEM - they are not
# built. That is a property of what the repo produces, not of a path pattern,
# and it is the distinction that keeps an exclusion from being coverage lost
# without a decision.
PAGES = page_names()


def audit(label, pages, prefix, want, assets, stamp_re):
    print(f'{label}: {len(assets)} shared asset(s) hash to {want}')
    for rel in assets:
        if not (ROOT / rel).exists():
            print(f'  warning: {rel} is in the {label} set and does not exist')

    failures = []
    for name in pages:
        rel = f'{prefix}{name}'
        page = ROOT / rel
        if not page.exists():
            print(f'  FAIL  {rel}: missing')
            failures.append(rel)
            continue
        m = stamp_re.search(page.read_text(encoding='utf-8'))
        if not m:
            failures.append(rel)
            print(f'  FAIL  {rel}: no build stamp. It predates the stamp, so')
            print(f'        it also predates everything else since - rebuild it.')
        elif m.group(1) != want:
            failures.append(rel)
            print(f'  FAIL  {rel}: built from shared assets {m.group(1)}, not '
                  f'{want}.')
            print(f'        Something it renders with has changed since it was')
            print(f'        built. This page is frozen because its own CSV has')
            print(f'        not moved, which is the wrong trigger for a shared')
            print(f'        change. Rebuild it.')
        else:
            print(f'  ok    {rel}')
    print()
    return failures


def main():
    # ONE SET AFTER CUTOVER, and the production half does not survive as a
    # branch reporting "nothing to check, by design". A half that can never fire
    # is the PINNED-when-empty shape, and this project has now found it three
    # times: CHECKLIST saying PINNED with `PINNED = set()`, a v2-named function
    # reading the repo root, and this. A clause that always passes is
    # indistinguishable from one that is working.
    #
    # So the sets are derived from what EXISTS. While `v2/` is there, both are
    # real and both are audited: production pages built by run.py + postprocess,
    # carrying `shared:`, and pass 0's carrying `shared-v2:`. Once `v2/` is gone
    # the pages at root ARE pass 0's, production's set has no members, and the
    # production half is not skipped - it is not constructed.
    sets = []
    if pages.pass0_dir(ROOT) != ROOT:
        sets.append(('production', '', pp.shared_hash(ROOT),
                     pp.SHARED_ASSETS, pp.STAMP_RE))
        sets.append(('pass 0', 'v2/', build_v2.v2_shared_hash(ROOT),
                     build_v2.V2_SHARED_ASSETS, build_v2.V2_STAMP_RE))
    else:
        sets.append(('pass 0', '', build_v2.v2_shared_hash(ROOT),
                     build_v2.V2_SHARED_ASSETS, build_v2.V2_STAMP_RE))

    failures = []
    for label, prefix, want, assets, rx in sets:
        failures += audit(label, PAGES, prefix, want, assets, rx)

    if failures:
        print(f'FAILED: {len(failures)} page(s) built from stale shared assets.')
        print('A change to shared code or shared CSS forces a FULL rebuild, not')
        print('an incremental one. Both builds run inside the workflow\'s')
        print('`if: changed == true` step, so an event whose CSV did not move is')
        print('skipped on BOTH sides - which is the exemption this catches.')
        return 1
    print(f'all {len(sets) * len(PAGES)} page(s) built from their current shared set')
    return 0


if __name__ == '__main__':
    sys.exit(main())
