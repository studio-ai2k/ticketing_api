#!/usr/bin/env python3
"""
Every difference between the working mock and the LOCKED one must be authorised.

    python verify/check_mock_deviations.py

WHY THIS EXISTS
---------------
`redesign/mock/dashboard_v3.39.html` is no longer v3.39. Same filename,
different file — six authorised changes were applied to it, and "the mock is
absolute" stopped naming a specific artefact the moment the name drifted. That
is how a correct finding got overturned: the badge was searched for in the
WORKING mock, found, and concluded to have always been there. It had not.

So the locked upload is pinned byte-identical at `redesign/locked/`, never
edited, and this asserts that the working copy differs from it in exactly the
authorised ways — no more and **no fewer**.

Both directions matter:

  - an UNAUTHORISED hunk is an invention, and goes back to Leo
  - a MISSING authorised deviation means an approved change was reverted, which
    is just as wrong and much quieter

The stylesheet carries no authorised deviations at all: after the `.pill-warm`
deletion the redesign adds zero CSS, so `dashboard_redesign.css` must be
byte-identical to the locked copy. That is the strongest form this check takes,
and it is why the CSS is checked separately rather than by signature.
"""

import difflib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK_HTML = ROOT / 'redesign' / 'locked' / 'dashboard_v3.39.LOCKED.html'
WORK_HTML = ROOT / 'redesign' / 'mock' / 'dashboard_v3.39.html'
LOCK_CSS = ROOT / 'redesign' / 'locked' / 'dashboard_redesign.LOCKED.css'
WORK_CSS = ROOT / 'redesign' / 'style' / 'dashboard_redesign.css'

# (id, ruling, signature that must appear on the WORKING side of its hunk)
AUTHORISED = [
    ('D1', 'P4.1 — old commission disclaimer deleted from the Revenus tooltip',
     'Les frais de réservation payés par l’acheteur'),
    ('D2', 'EE1 — default view honours the configured warm-up mark',
     'on[d.k] = !d.warmup'),
    ('D3', 'EE2 + ruling §1 — warmup badge, .badge.amber, English label',
     '<span class="badge amber" style="margin-left:8px">warmup</span>'),
    ('D4', 'FF1 — over-capacity states the overshoot instead of claiming complet',
     'au-delà de la jauge'),
    ('D5', 'FF1 — Places libres reads "jauge dépassée" when over',
     "jauge dépassée"),
    ('D6', 'FF1 — bar fill turns amber when over capacity',
     "d.now>d.cap?'var(--amber)'"),
    ('D7', 'FF2 — gratuits share under the count, amber at >= 50%',
     "pc>=50?'var(--amber)'"),
]


def main():
    for p in (LOCK_HTML, WORK_HTML, LOCK_CSS, WORK_CSS):
        if not p.exists():
            print(f'FAIL: {p.relative_to(ROOT)} is missing.')
            if 'locked' in str(p):
                print('      The locked copy is the reference. Without it nothing')
                print('      here can be checked - restore it from the original upload.')
            return 1

    failures = []

    # ---- the stylesheet must not deviate at all ----
    lock_css, work_css = LOCK_CSS.read_text(encoding='utf-8'), WORK_CSS.read_text(encoding='utf-8')
    if lock_css == work_css:
        print('ok    stylesheet: byte-identical to locked (zero new CSS)')
    else:
        d = list(difflib.unified_diff(lock_css.split('\n'), work_css.split('\n'), lineterm='', n=0))
        failures.append(f'stylesheet deviates from locked ({len(d)} diff lines)')
        print('FAIL  stylesheet deviates from locked. The redesign adds no CSS;')
        print('      anything here is an invention. First lines:')
        for line in d[:6]:
            print(f'        {line[:110]}')

    # ---- the mock's hunks must each be authorised ----
    lock = LOCK_HTML.read_text(encoding='utf-8').split('\n')
    work = WORK_HTML.read_text(encoding='utf-8').split('\n')
    hunks = [op for op in difflib.SequenceMatcher(None, lock, work).get_opcodes()
             if op[0] != 'equal']
    print(f'\n{len(hunks)} hunk(s) between locked and working mock:')

    matched = {}
    for tag, i1, i2, j1, j2 in hunks:
        added = '\n'.join(work[j1:j2])
        hit = next((a for a in AUTHORISED if a[2] in added), None)
        if hit:
            matched.setdefault(hit[0], 0)
            matched[hit[0]] += 1
            print(f'  ok    {hit[0]}  {hit[1]}')
        else:
            failures.append(f'unauthorised hunk at working line {j1 + 1}')
            print(f'  FAIL  UNAUTHORISED hunk at working line {j1 + 1}:')
            for line in work[j1:j2][:3]:
                print(f'          + {line.strip()[:104]}')

    missing = [a for a in AUTHORISED if a[0] not in matched]
    if missing:
        print('\nauthorised deviations NOT present — an approved change was reverted:')
        for mid, why, _ in missing:
            failures.append(f'{mid} missing')
            print(f'  FAIL  {mid}  {why}')

    print()
    if failures:
        print(f'FAILED: {len(failures)}')
        print('An unauthorised hunk is an invention and goes back to Leo. A missing')
        print('one is an approved change that was reverted. Neither is a detail.')
        return 1
    print(f'working mock differs from locked in exactly the {len(AUTHORISED)} '
          f'authorised ways')
    return 0


if __name__ == '__main__':
    sys.exit(main())
