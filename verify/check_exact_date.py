#!/usr/bin/env python3
"""
`exact_date` must do date-to-date matching, on the page where it did not.

    python3 verify/check_exact_date.py

WHY THIS PAGE
-------------
`bordeaux_oct`'s gaps against five of its six candidates are exact multiples of
seven — 350, 490, 1141, 343, 581 — so `smod7(G) == 0` and the weekday snap is a
no-op there. `exact_date` shipped as raw J−X with the snap turned off, which on
that page is *identical to `j_minus`*: same offset, same rows, same numbers.

That was reported to Leo as a coincidence of dates. It was not a coincidence. It
was the mode not doing anything, and this is the page where that hid, so this is
where the test belongs. A negative test on the pair where the effect is largest
would have passed against the broken code.

WHAT IS ASSERTED
----------------
1. On every candidate whose snap is zero AND whose calendar drift is not,
   `exact_date` and `j_minus` render DIFFERENT daily columns. Under the defect
   they were byte-identical. This is the assertion the defect fails.
   The converse is asserted too: where the drift is also zero the two modes MUST
   agree. `geneve_2026` shares this page's event date to the day, so the same
   calendar date is the same J−x and a difference there would be the bug.
2. The reference date a row reads is the same calendar day as the row itself,
   N years back — which is what `Date exacte, même J−x, date à date` says on the
   tin, and what nothing checked for the life of the mode.
3. The two grains agree: the reference date a daily row reads falls in that
   row's own weekly bucket.
4. N >= 0 is refused rather than computed.

NEGATIVE TESTS (CHECKLIST step 2), run before this was trusted. Each claim was
broken SEPARATELY, because a check can be right about three things and blind on
the fourth:

  claims 1+2  restoring `anchor()`'s `exact_date` branch to the old `(gap, 0)`:
              15 failures, exit 1. Six of the seven zero-snap candidates go
              identical to `j_minus` and every pair has 107 of 107 rows reading
              the wrong calendar day.
  claim 3     pointing `Align.week_of` back at the reference's OWN event, and
              nothing else: 5 failures, exit 1, up to 107 rows per pair.
              It does NOT fire under the claims 1+2 break, because that breaks
              both grains the same way and they go on agreeing with each other
              while both are wrong. That is the whole reason it is broken
              separately, and it was measured rather than assumed - the first
              version of this note claimed the first break exercised claim 3
              too, and it does not.
  claim 4     removing the `N < 0` raise: reported, exit 1.

Restoring the fix passes all four.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))

import run  # noqa: E402
import build_series  # noqa: E402
import dashboard_payload as dp  # noqa: E402

EVENT = 'bordeaux_oct_2026'
CUT = date(2026, 8, 9)


def smod7(g):
    m = g % 7
    return m - 7 if m > 3 else m


def sides(cfg_all, cand):
    cfg, ccfg = cfg_all[EVENT], cfg_all[cand]
    cur = dp.load_rows(str(ROOT / 'data' / f'{EVENT}_merged.csv'))
    ref = dp.load_rows(str(build_series.series_path(cand)))
    cur_n, cur_rev = dp.series(cur)
    c_n, c_rev = dp.series(ref)
    return cfg, ccfg, cur_n, cur_rev, c_n, c_rev


def column(cfg, ccfg, cur_n, cur_rev, c_n, c_rev, mode):
    al = dp.anchor(mode, cfg['event_date_first'], ccfg['event_date_first'],
                   (cfg['event_date_first'] - min(cur_n)).days,
                   (ccfg['event_date_first'] - min(c_n)).days)
    ref_cut = max((d for d in c_n if d <= al.ref_date(CUT)), default=None)
    rows = dp.daily_rows(cur_n, cur_rev, c_n, c_rev, CUT, min(cur_n), al,
                         ref_cut, cfg['event_date_first'],
                         ccfg['event_date_first'], max(c_n) if c_n else None)
    return al, rows


def main():
    cfg_all = run.load_event_config(str(ROOT / 'event_config.csv'))
    cands = [c for c in cfg_all
             if c != EVENT and build_series.series_path(c)]
    failures = []

    cur_ev = cfg_all[EVENT]['event_date_first']
    print(f'{EVENT}, event {cur_ev}, cutoff {CUT}\n')
    print(f'{"candidate":<22}{"G":>6}{"snap":>6}{"N":>3}{"drift":>6}  '
          f'{"exact != j_minus":<18}rows')

    zero_snap = 0
    for cand in sorted(cands):
        ccfg = cfg_all[cand]
        G = (cur_ev - ccfg['event_date_first']).days
        if G < 0:
            continue
        snap = smod7(G)
        args = sides(cfg_all, cand)
        alx, xr = column(*args, 'exact_date')
        _, jr = column(*args, 'j_minus')
        xcol = [(r['db'], r['b']) for r in xr]
        jcol = [(r['db'], r['b']) for r in jr]
        differ = xcol != jcol
        N = cur_ev.year - ccfg['event_date_first'].year
        Yv = (cur_ev - dp.cal_shift(ccfg['event_date_first'], N)).days
        print(f'{cand:<22}{G:>6}{snap:>+6}{N:>3}{Yv:>6}  '
              f'{"yes" if differ else "no":<18}{len(xr)}')

        # ---- 1. the snap-zero candidates are where the defect hid --------
        # The two modes coincide exactly when the calendar drift equals the
        # snap: `j_minus` shifts our row by `snap` days, `exact_date` by `Y`.
        # So a zero snap only forces a difference when Y is non-zero.
        #
        # DERIVED, not excused. `geneve_2026` shares this page's event date to
        # the day, so G = 0, N = 0 and Y = 0: the same calendar date IS the same
        # J−x, and all three modes agree by arithmetic rather than by neglect.
        # Asserting a difference there would be asserting a bug.
        Y = Yv
        if snap == 0:
            zero_snap += 1
            if Y and not differ:
                failures.append(f'{cand}: exact_date == j_minus at zero snap')
                print(f'        FAIL  the snap is 0, so `j_minus` applies no '
                      f'offset at all, and the two')
                print(f'              editions sit {Y} day(s) apart in the '
                      f'calendar year. An `exact_date`')
                print(f'              identical to it is the mode doing nothing '
                      f'- which is the defect,')
                print(f'              not a coincidence of dates.')
            elif not Y and differ:
                failures.append(f'{cand}: exact_date != j_minus at zero drift')
                print(f'        FAIL  the two editions share an event date, so '
                      f'the same calendar day IS')
                print(f'              the same J−x. The modes must agree here.')

        # ---- 2. the reference date IS the same calendar day -------------
        bad = [r for r in xr if r['db'] and
               dp.cal_shift(date.fromisoformat(r['da']), -N)
               != date.fromisoformat(r['db'])]
        if bad:
            failures.append(f'{cand}: not date-to-date')
            print(f'        FAIL  {len(bad)} row(s) do not read the same '
                  f'calendar day N years back, e.g.')
            print(f'              our {bad[0]["da"]} reads {bad[0]["db"]}, '
                  f'want {dp.cal_shift(date.fromisoformat(bad[0]["da"]), -N)}')

        # ---- 3. the two grains agree -------------------------------------
        off = [r for r in xr if r['db'] and
               alx.week_of(date.fromisoformat(r['db'])) != r['jx'] // 7]
        if off:
            failures.append(f'{cand}: grains disagree')
            print(f'        FAIL  {len(off)} row(s) read a reference date the '
                  f'weekly grain buckets elsewhere')

    print(f'\n{zero_snap} candidate(s) with a zero snap - the ones the broken '
          f'mode rendered identically to Jour J')
    if not zero_snap:
        failures.append('no zero-snap candidate on this page')
        print('  FAIL  this check is pointed at the wrong page: with no '
              'zero-snap candidate it')
        print('        cannot see the defect it was written for.')

    # ---- 4. N >= 0 is bounded, not computed ------------------------------
    try:
        dp.anchor('exact_date', date(2025, 6, 1), date(2026, 6, 1), 0, 0)
        failures.append('N < 0 accepted')
        print('\n  FAIL  a reference edition NEWER than the page was accepted. '
              'Unreachable today,')
        print('        which is exactly the profile of `jr >= 0` and the weekly '
              '`w >= 0`.')
    except ValueError:
        print('\nok    N < 0 is refused rather than computed')

    print()
    if failures:
        print(f'FAILED: {len(failures)}')
        return 1
    print('exact_date does date-to-date matching, on the page where it did not')
    return 0


if __name__ == '__main__':
    sys.exit(main())
