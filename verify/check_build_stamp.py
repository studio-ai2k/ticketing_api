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

SCOPE: PRODUCTION ONLY
----------------------
`build_v2.py` runs unconditionally in the workflow, so a v2 page cannot go
stale — the exemption is a production-only property. If that ever changes, this
check has to grow a v2 half, and the shared set for v2 is a different list.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

import postprocess_html as pp  # noqa: E402

PAGES = ('parisxxl.html', 'bordeaux.html', 'epk.html', 'bordeaux_oct.html',
         'geneve.html', 'rennes.html')


def main():
    want = pp.shared_hash(ROOT)
    print(f'shared assets hash to {want}')
    for rel in pp.SHARED_ASSETS:
        if not (ROOT / rel).exists():
            print(f'  warning: {rel} is in SHARED_ASSETS and does not exist')

    failures = []
    for name in PAGES:
        page = ROOT / name
        if not page.exists():
            print(f'  FAIL  {name}: missing')
            failures.append(name)
            continue
        m = pp.STAMP_RE.search(page.read_text(encoding='utf-8'))
        if not m:
            failures.append(name)
            print(f'  FAIL  {name}: no build stamp. It predates the stamp, so')
            print(f'        it also predates everything else since - rebuild it.')
        elif m.group(1) != want:
            failures.append(name)
            print(f'  FAIL  {name}: built from shared assets {m.group(1)}, not '
                  f'{want}.')
            print(f'        Something it renders with has changed since it was')
            print(f'        built. This page is frozen because its own CSV has')
            print(f'        not moved, which is the wrong trigger for a shared')
            print(f'        change. Rebuild it.')
        else:
            print(f'  ok    {name}')

    print()
    if failures:
        print(f'FAILED: {len(failures)} page(s) built from stale shared assets.')
        print('A change to shared code or shared CSS forces a FULL rebuild, not')
        print('an incremental one.')
        return 1
    print(f'all {len(PAGES)} production page(s) built from the current shared set')
    return 0


if __name__ == '__main__':
    sys.exit(main())
