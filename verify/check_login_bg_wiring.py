#!/usr/bin/env python3
"""
The login background is wired PER PAGE, not baked once — CUTOVER §5.7.

    python3 verify/check_login_bg_wiring.py

WHY A NEGATIVE TEST AND NOT AN OBSERVATION
-------------------------------------------
`check_pages` already asserts that each page's inlined stylesheet is the
redesign sheet through `build_v2.style_transforms(bg)`, per page, with the
background resolved from `event_config`. That reads like coverage and is not,
because of one measurement:

    all six active rows resolve to the SAME background, `upload.JPG`

and one of them, `parisxxl.html`, resolves to it while its `login_bg_image`
cell is **EMPTY** — `login_bg_by_page` falls back to `DEFAULT_LOGIN_BG`. So the
value every page carries is also the value a page carries when nothing is wired
at all. Every existing assertion passes if the per-page path is severed and
replaced by the constant.

That is exactly how `paris_xxl` lost `paris_login.jpg` in the first place, and
§5.7 says so: "Make it falsifiable in the negative test rather than waiting for
reality... uniform data is what made the bug invisible."

So this changes a real config row, rebuilds, and asserts the page FOLLOWED. The
row it changes is `parisxxl.html` deliberately — the empty one, where a page
that ignored the config would be indistinguishable from a page that read it.

`--config` DOES NOT WORK HERE, AND THAT IS ITS OWN FINDING
-----------------------------------------------------------
The obvious way to write this is against a temp config, the way
`check_anchor_modes.py` does. It was written that way first, and it reported
that the page did NOT follow the config — a false defect, and a loud one.

`build_v2.py --config` forwards to `build_dashboard.py --config`, which uses the
path for `read_warmup_flags`, `read_config_field` and `suivi_candidates` — and
then calls `run.main()` with **no arguments**. run.py reads `event_config.csv`
from its own hardcoded location, and run.py is what fills the template's
`.db-overlay url()`. `postprocess_html` only preserves what it finds there
(`wanted = templated_bg or DEFAULT_LOGIN_BG`).

So `--config` is a PARTIAL override. Measured: with `paris_login.jpg` in a temp
config the built page's overlay url is `''`, exactly as with the real config.
`check_anchor_modes` gets away with it because it calls
`dashboard_payload.build(..., config, ...)` directly, passing the path — a
different route that does honour it.

Any future test that assumes `--config` isolates the config will silently
exercise the real one instead. That is the probe-states-a-different-claim class,
and it is why this file edits the real config rather than pretending to.

HOW THE REAL FILE IS PROTECTED
-------------------------------
The original bytes are read first, restored in a `finally`, and the sha256 is
compared afterwards — because "I restored it" and "it is byte-identical" are
different claims and only the second is checkable. A mismatch FAILS.

The edit is at BYTE level, one cell, never through `csv.DictWriter`: the file
has CRLF endings and no BOM, and a DictWriter round trip rewrites every line and
breaks every build. See verify/CHECKLIST.md.
"""

import hashlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import build_v2                          # noqa: E402

CONFIG = ROOT / 'event_config.csv'
PAGE, EVENT, PROBE = 'parisxxl.html', 'paris_xxl_2026', 'paris_login.jpg'
OVERLAY_RE = re.compile(r"\.db-overlay\{[^}]*url\('([^']*)'\)")


def built_background(out):
    """The background the BUILT page actually carries. The artefact, not the config.

    No `--config`: see the module docstring. It would not reach this value, and
    passing it would make the test look isolated while exercising the real file
    anyway.
    """
    subprocess.run(
        [sys.executable, str(ROOT / 'scripts' / 'build_v2.py'),
         '--event', EVENT, '--csv', str(ROOT / 'data' / f'{EVENT}_merged.csv'),
         '--out', str(out)],
        capture_output=True, text=True, check=True)
    m = OVERLAY_RE.search(out.read_text(encoding='utf-8'))
    return m.group(1) if m else '(no .db-overlay url)'


def repoint(raw, page, value):
    """One cell of one row, at byte level. Returns the edited bytes."""
    lines = raw.split(b'\r\n')
    header = lines[0].decode('utf-8').split(',')
    i_name, i_bg = (header.index('output_filename'),
                    header.index('login_bg_image'))
    hits = 0
    for n, line in enumerate(lines):
        if n == 0 or not line:
            continue
        cells = line.decode('utf-8').split(',')
        if len(cells) > max(i_name, i_bg) and cells[i_name].strip() == page:
            cells[i_bg] = value
            lines[n] = ','.join(cells).encode('utf-8')
            hits += 1
    if hits != 1:
        raise SystemExit(f'check_login_bg_wiring: {hits} row(s) named {page}, '
                         f'want exactly 1 - the edit site is not unambiguous.')
    return b'\r\n'.join(lines)


def main():
    raw = CONFIG.read_bytes()
    before_hash = hashlib.sha256(raw).hexdigest()
    failures = []

    if CONFIG.read_bytes().count(b'\r\n') == 0:
        raise SystemExit('check_login_bg_wiring: event_config.csv has no CRLF '
                         'endings - it has been reformatted, and that breaks '
                         'every build. Fix that before running this.')

    tmpdir = Path(tempfile.mkdtemp(prefix='login_bg_'))

    try:
        declared = build_v2.login_bg_by_page()[PAGE]
        baseline = built_background(tmpdir / 'before.html')
        print(f'{PAGE}: config resolves to {declared!r} '
              f'(DEFAULT_LOGIN_BG is {build_v2.DEFAULT_LOGIN_BG!r})')
        print(f'  built page carries {baseline!r}')

        CONFIG.write_bytes(repoint(raw, PAGE, PROBE))
        flipped = built_background(tmpdir / 'after.html')
        print(f'\nrow repointed at {PROBE!r}:')
        print(f'  built page carries {flipped!r}')

        if PROBE not in flipped:
            failures.append('the page did not follow the config row')
            print(f'  FAIL  the page still shows {flipped!r}. The login '
                  f'background is not wired per page - it is baked, and every '
                  f'other assertion about it passes anyway because all six rows '
                  f'agree on the same value.')
        elif flipped == baseline:
            # The check_anchor_modes lesson: a flip that changes nothing
            # observable would pass against a build that ignored the config.
            failures.append('the flip changed nothing observable')
            print('  FAIL  the flip produced an identical page, so this test '
                  'would pass against a build that ignored the config.')
        else:
            print(f'  ok    followed: {baseline!r} -> {flipped!r}')
    finally:
        CONFIG.write_bytes(raw)

    restored = built_background(tmpdir / 'restored.html')
    print(f'\nrebuilt after restoring the config: {restored!r}')
    if restored != baseline:
        failures.append('the page did not return to its configured background')
        print(f'  FAIL  expected {baseline!r} back')
    else:
        print('  ok    back to the configured value')

    after_hash = hashlib.sha256(CONFIG.read_bytes()).hexdigest()
    if after_hash != before_hash:
        failures.append('event_config.csv was modified')
        print(f'\n  FAIL  event_config.csv did NOT restore: {before_hash[:16]} '
              f'-> {after_hash[:16]}. Restore it from git before doing '
              f'anything else - every build reads this file.')
    else:
        print(f'\nok    event_config.csv untouched ({after_hash[:16]})')

    print()
    if failures:
        print(f'FAILED: {len(failures)}')
        for f in failures:
            print(f'  - {f}')
        return 1
    print('the login background is wired per page, and the wiring is falsifiable')
    return 0


if __name__ == '__main__':
    sys.exit(main())
