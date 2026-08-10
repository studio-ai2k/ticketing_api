#!/usr/bin/env python3
"""
The anchoring enum, asserted rather than remembered.

    python verify/check_anchor_modes.py

WHY
---
`comparison_mode` has been in `event_config.csv` since long before the redesign,
with `run.py:3955` branching on it and `run.py:1426` holding the launch filter.
**All six pages are `j_minus` or empty.** So the other branch has never run in
anger, and an enum with one value in use is an enum whose other branch is
untested — the same situation as the login background, where five explicit
`upload.JPG` and one blank made a real defect invisible.

This flips a config row, asserts the change is followed, and puts it back. It is
the negative test the data will not provide on its own.

WHICH EVENT, AND WHY THAT MATTERS
---------------------------------
`epk_2026`, because its candidate's campaign is **105 days longer** than ours.
Run on `rennes_2026` (O = −2) the same test passes while showing nothing: 23
weekly rows before the flip and 23 after. On epk the table goes 38 → 23, so a
mode that was silently ignored would fail here and pass there. A negative test on
the pair where the effect is smallest is a negative test that cannot fail.

WHAT IS ASSERTED, AND WHAT IS ONLY READ
---------------------------------------
Asserted by running: the payload follows `comparison_mode`; the launch branch
reaches `run.py`'s OWN dsl filter (detected from that function's own banner, so
this cannot pass against a reimplementation); the three modes stand in the
arithmetic relationship they are specified to.

Read, not run: `run.py:3955`'s branch in the PRODUCTION pipeline. Exercising it
means a full `build_dashboard.py` run per mode, and production retires at cutover
(CUTOVER.md §8). Both halves read the same key with the same default — stated
here so the boundary is met rather than discovered.
"""

import contextlib
import io
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))

import dashboard_payload as dp  # noqa: E402

# The pair with the largest campaign-length difference, which is what makes the
# flip observable. `cut` is the shipped cutoff for this page.
EVENT = 'epk_2026'
REF = 'epk_2023'
REF_CSV = 'csv_database/epk_2023/epk_2023_merged.csv'
CUT = date(2026, 8, 9)


def build(mode=None, config=None):
    """(payload, whatever run.py printed while building it)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        D = dp.build(EVENT, str(ROOT / 'data' / f'{EVENT}_merged.csv'), CUT,
                     config or str(ROOT / 'event_config.csv'), REF,
                     str(ROOT / REF_CSV), mode=mode)
    return D, buf.getvalue()


def main():
    failures = []

    # ---- 1. the three modes stand in the specified relationship ----------
    print('1  the arithmetic, on the pair with the largest offset')
    out = {}
    for m in dp.MODES:
        D, log = build(mode=m)
        out[m] = (D, log)
        wk = D['weekly']
        print(f'   {m:20s} weekly rows {len(wk):3d}  max w {max(r["w"] for r in wk):3d}'
              f'  w<0 {sum(1 for r in wk if r["w"] < 0):2d}')

    jw = [(r['w'], r['b']) for r in out['j_minus'][0]['weekly']]
    xw = [(r['w'], r['b']) for r in out['exact_date'][0]['weekly']]
    lw = [(r['w'], r['b']) for r in out['days_since_launch'][0]['weekly']]
    jd = [(r['jx'], r['b']) for r in out['j_minus'][0]['daily']]
    xd = [(r['jx'], r['b']) for r in out['exact_date'][0]['daily']]

    if jw != xw:
        failures.append('exact_date weekly != j_minus weekly')
        print('   FAIL  exact_date and j_minus differ at the WEEKLY grain. They '
              'differ by')
        print('         the weekday snap alone, which cannot survive division by 7.')
    else:
        print('   ok    exact_date weekly == j_minus weekly (the snap rounds away)')

    if jd == xd:
        failures.append('exact_date daily == j_minus daily on a snapped pair')
        print('   FAIL  exact_date and j_minus render the same DAILY column on a '
              'pair whose')
        print('         snap is non-zero, so the mode is not reaching the offset.')
    else:
        print('   ok    exact_date daily != j_minus daily (the snap is what they '
              'differ by)')

    if lw == jw:
        failures.append('days_since_launch weekly == j_minus weekly')
        print('   FAIL  days_since_launch does not move the WEEKLY column. That is '
              'the whole')
        print('         ruling: the offset here is 105 days and the weekly must '
              'follow it.')
    else:
        print('   ok    days_since_launch weekly != j_minus weekly (the offset is '
              'fifteen weeks)')

    if any(r['w'] < 0 for _m, (D, _l) in out.items() for r in D['weekly']):
        failures.append('a negative week reached the payload')
        print('   FAIL  a week with w < 0 reached the payload. Under launch the '
              'candidate\'s')
        print('         event lands past ours in aligned time; those rows render '
              'as "S−−1".')
    else:
        print('   ok    no w < 0 in any mode')

    # ---- 2. the launch branch reaches run.py's own filter -----------------
    print('\n2  the launch branch uses run.py\'s own dsl filter')
    if 'days-since-launch' in out['days_since_launch'][1]:
        print('   ok    filter_tickets_to_same_point_dsl ran (its own banner)')
    else:
        failures.append('the dsl filter did not run under days_since_launch')
        print('   FAIL  no days-since-launch banner. Either the branch was not '
              'taken or the')
        print('         cut was reimplemented instead of calling run.py\'s '
              'function.')
    if 'days-since-launch' in out['j_minus'][1]:
        failures.append('the dsl filter ran under j_minus')
        print('   FAIL  the dsl banner appeared under j_minus')
    else:
        print('   ok    j_minus does not reach it')

    # ---- 3. the config row is followed, and is the only place -------------
    print('\n3  comparison_mode is followed, and there is one of it')
    before, _ = build()
    raw = (ROOT / 'event_config.csv').read_text(encoding='utf-8-sig')
    flipped, n = [], 0
    for line in raw.split('\n'):
        if line.startswith(f'{EVENT},') and 'j_minus' in line:
            line = line.replace('j_minus', 'days_since_launch')
            n += 1
        flipped.append(line)
    if not n:
        failures.append('no row to flip')
        print(f'   FAIL  no {EVENT} row carried j_minus - the flip is vacuous, '
              'which is')
        print('         itself the finding: this test asserts nothing until it is '
              'fixed.')
    else:
        tmp = Path(tempfile.mkdtemp()) / 'event_config.csv'
        shutil.copy(ROOT / 'event_config.csv', tmp.parent / 'orig.csv')
        tmp.write_text('\n'.join(flipped), encoding='utf-8')
        after, _ = build(config=str(tmp))
        restored, _ = build()
        ok = (before['amode'] == 'j_minus'
              and after['amode'] == 'days_since_launch'
              and restored['amode'] == 'j_minus')
        moved = len(before['weekly']) != len(after['weekly'])
        print(f"   before {before['amode']:20s} weekly {len(before['weekly'])}")
        print(f"   flipped{after['amode']:>21s} weekly {len(after['weekly'])}")
        print(f"   after  {restored['amode']:20s} weekly {len(restored['weekly'])}")
        if not ok:
            failures.append('the payload did not follow comparison_mode')
            print('   FAIL  the payload did not follow the config row')
        elif not moved:
            failures.append('the flip changed nothing observable')
            print('   FAIL  the flip changed no rendered quantity, so this test '
                  'would pass')
            print('         against a payload that ignored the mode entirely.')
        else:
            print('   ok    followed, and the change is observable')

    print()
    if failures:
        print(f'FAILED: {len(failures)}')
        for f in failures:
            print(f'  - {f}')
        return 1
    print('the anchoring enum behaves, and both of its branches have run')
    return 0


if __name__ == '__main__':
    sys.exit(main())
