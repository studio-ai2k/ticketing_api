#!/usr/bin/env python3
"""
The archive is what it says it is.

    python3 verify/check_archive_provenance.py

WHY THIS EXISTS, AND WHY IT IS LATE
-----------------------------------
`legacy/*.html` are the six production pages frozen at the cutover. Their
provenance is a table of sha256 hashes in `legacy/README.md`, recorded as each
page shipped BEFORE the archive banner was inserted.

**That table was documented and unasserted.** Nothing in `verify/` read
`legacy/` at all, so a rebuild that touched an archived page would have shipped
and the suite would have been green. The hashes were verified only by hand, by
pasting the command written in the README - which is a provenance RECORD, not a
guarantee.

Worse than the gap: `check_archive_provenance` had been named TWICE in briefs as
the thing that would catch exactly this. Two seats reasoned about `legacy/` as
protected. **Closing the gap removes a wrong premise, not just a missing check** -
the danger was never that the archive was unguarded, it was that everyone
believed it was not.

Real guards do exist either side of it: `rebuild_pages.py` refuses `legacy/`
explicitly, and the workflow's rebase handler refuses it before that. Neither
looks at the FILES.

ONE DEFINITION OF THE STRIP, IMPORTED
-------------------------------------
The banner is removed by `cutover.strip_banner`, imported rather than restated.
The span is exact and not guessable from a description - everything from
`<div id="cutover-archive-banner"` through the first `</div>` after it, plus the
next 3 bytes - and the review seat needed three attempts to reproduce the hashes
before deriving it from the file.

The README's pasteable snippet is generated from the same `BANNER_STRIP_RE`, so
this check, that snippet and `cutover.py` all strip the same bytes. Two copies of
an exact span drift, and only one of them is right with no way to tell which
from either side.

THE HASHES ARE READ FROM THE README, NOT COPIED
-----------------------------------------------
The table in `legacy/README.md` IS the record. Restating it here would make this
check agree with itself while the published record said something else - the
shape this project keeps deleting. If the README and the files disagree, that is
the finding, and it is reported either way round.

NEGATIVE TEST (CHECKLIST step 2)
--------------------------------
Flipping ONE BYTE in `legacy/rennes.html` - a single digit inside a figure, far
from the banner - makes this exit 1:

    FAIL  rennes.html  recorded 96bfc9b8a77b… but the file hashes 3f2c…

and restoring it clears. Run with `--selftest` to do that automatically against
a temporary copy, which is the same assertion without touching the archive.
"""

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import cutover  # noqa: E402  - strip_banner, so the span is defined once

LEGACY = ROOT / 'legacy'
README = LEGACY / 'README.md'
ROW = re.compile(r'^\|\s*`([^`]+\.html)`\s*\|\s*`([0-9a-f]{64})`\s*\|', re.M)


def recorded():
    """{page: sha256} from the README's provenance table - the record itself."""
    if not README.exists():
        raise SystemExit(f'{README} is missing - the archive has no provenance '
                         f'record to check against')
    rows = ROW.findall(README.read_text(encoding='utf-8'))
    if not rows:
        raise SystemExit(
            f'{README} has no provenance rows. The table is the record; an '
            f'empty one would make this check pass on any archive at all, '
            f'which is worse than no check.')
    return dict(rows)


def actual(path):
    return hashlib.sha256(cutover.strip_banner(path.read_bytes())).hexdigest()


def audit():
    want = recorded()
    have = {p.name for p in LEGACY.glob('*.html')}
    fails = []

    for name in sorted(set(want) | have):
        if name not in have:
            fails.append(f'{name}: recorded in the README but NOT IN legacy/ - '
                         f'an archived page has been deleted')
            print(f'  FAIL  {name}: recorded but missing from legacy/')
            continue
        if name not in want:
            fails.append(f'{name}: in legacy/ but NOT RECORDED - an archived '
                         f'page with no provenance is not an archive')
            print(f'  FAIL  {name}: present but not in the README table')
            continue
        got = actual(LEGACY / name)
        if got != want[name]:
            fails.append(f'{name}: hash mismatch')
            print(f'  FAIL  {name}')
            print(f'          recorded {want[name]}')
            print(f'          actual   {got}')
            print(f'        The archive is frozen. Either a page changed - which '
                  f'a rebuild must never do - or the record is wrong.')
            continue
        print(f'  ok    {name}  {got[:16]}…')
    return fails


def selftest():
    """One byte, far from the banner, must break it. Against a copy."""
    import shutil, tempfile
    src = LEGACY / 'rennes.html'
    tmp = Path(tempfile.mkdtemp())
    try:
        cp = tmp / 'rennes.html'
        shutil.copy2(src, cp)
        clean = actual(cp)
        raw = cp.read_bytes()
        d = bytearray(raw)
        # A digit deliberately OUTSIDE the stripped span. Inside it the strip
        # would hide the change, and a check that only notices edits it removes
        # is not checking the page - so the offset is chosen against the span
        # the strip actually matches, not against a landmark near it.
        m = cutover.BANNER_STRIP_RE.search(raw)
        lo, hi = (m.span() if m else (0, 0))
        j = next(k for k in range(hi, len(d)) if chr(d[k]).isdigit())
        d[j] = ord('9') if chr(d[j]) != '9' else ord('8')
        cp.write_bytes(bytes(d))
        broken = actual(cp)
        print(f'  selftest: banner span {lo}..{hi}, one byte flipped at '
              f'offset {j} - outside it, so the strip cannot hide it')
        print(f'    before {clean}')
        print(f'    after  {broken}')
        if clean == broken:
            print('  FAIL  the hash did not move - this check cannot see a '
                  'changed page')
            return 1
        print('  ok    a one-byte change moves the hash, so a changed archive '
              'page fails')
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    if '--selftest' in sys.argv:
        return selftest()
    print(f'archive provenance: {len(list(LEGACY.glob("*.html")))} page(s), '
          f'hashes read from {README.relative_to(ROOT)}')
    fails = audit()
    if fails:
        print(f'\nFAILED: {len(fails)}')
        print('legacy/ is a FROZEN ARCHIVE. Its hashes are the provenance')
        print('record for what the old pipeline shipped, and they are')
        print('meaningful only if nothing rewrites the files.')
        return 1
    print(f'\nall {len(fails) or len(recorded())} page(s) match the recorded '
          f'provenance')
    return 0


if __name__ == '__main__':
    sys.exit(main())
