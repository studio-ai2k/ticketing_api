#!/usr/bin/env python3
"""
Prove the Suivi selector's closed-form offset equals run.py's own matcher.

    python verify/check_offset.py            # every configured event pair
    python verify/check_offset.py --fuzz     # plus 400 random pairs

The selector shifts a row date by a single constant per candidate instead of
calling run.py's `_prev_match_dow`. That is an identity, not an approximation:

    offset = G - signed_mod7(G),  where G = (cur_first - cand_first).days

but an identity nobody re-checks is an assumption. `_prev_match_dow` is a
nested function inside `_generate_suivi_v3`, so it cannot be imported; it is
transcribed here VERBATIM and the transcription is itself asserted against the
source text, so a change to run.py fails this check rather than silently
diverging.

Exits non-zero on any mismatch.
"""

import argparse
import csv
import random
import re
import sys
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'scripts'))
from suivi_candidates import daily_offset, load_config  # noqa: E402


def prev_match_dow(current_date, event_date_cur, prev_event_date):
    """Verbatim transcription of run.py's _prev_match_dow body."""
    j_x = (event_date_cur - current_date).days
    candidate = prev_event_date - timedelta(days=j_x)
    wd_diff = current_date.weekday() - candidate.weekday()
    if wd_diff > 3:
        wd_diff -= 7
    if wd_diff < -3:
        wd_diff += 7
    return candidate + timedelta(days=wd_diff)


# The transcription above is only worth anything if it still matches run.py.
# These are the four lines that do the work; if any of them changes, this
# check must be revisited rather than quietly passing on a stale copy.
SOURCE_MARKERS = (
    'candidate = prev_event_date - timedelta(days=j_x)',
    'wd_diff = current_date.weekday() - candidate.weekday()',
    'if wd_diff > 3: wd_diff -= 7',
    'if wd_diff < -3: wd_diff += 7',
)

# Scoped to _prev_match_dow's own body, NOT to run.py at large. The two clamp
# lines are byte-identical in _prev_match_dsl a few lines below, so a
# whole-file search finds them there and passes even after _prev_match_dow has
# been changed - which is exactly what happened the first time this guard was
# tested against a mutated copy. Same trap as the sw-wrap guard matching the
# stylesheet: a marker that is not unique is not a guard.
FUNC_RE = re.compile(r'def _prev_match_dow\(.*?(?=\n    def |\n\ndef )', re.DOTALL)


def check_transcription():
    src = (REPO / 'run.py').read_text(encoding='utf-8')
    m = FUNC_RE.search(src)
    if not m:
        print('run.py._prev_match_dow not found - cannot verify the '
              'transcription', file=sys.stderr)
        return False
    body = m.group(0)
    missing = [s for s in SOURCE_MARKERS if s not in body]
    if missing:
        print('run.py._prev_match_dow has changed - this transcription is stale:',
              file=sys.stderr)
        for s in missing:
            print(f'  no longer present: {s}', file=sys.stderr)
        return False
    return True


def check_pair(cur_first, cand_first, span=600, label=''):
    """Every row date in `span` days must agree. Returns a failure count."""
    off = daily_offset(cur_first, cand_first)
    bad = 0
    for k in range(span):
        d = cur_first - timedelta(days=k)
        if prev_match_dow(d, cur_first, cand_first) != d - timedelta(days=off):
            bad += 1
            if bad == 1:
                print(f'  MISMATCH {label} on {d}: run.py says '
                      f'{prev_match_dow(d, cur_first, cand_first)}, closed form '
                      f'says {d - timedelta(days=off)}', file=sys.stderr)
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default=str(REPO / 'event_config.csv'))
    ap.add_argument('--fuzz', action='store_true',
                    help='also check 400 random event-date pairs')
    args = ap.parse_args()

    if not check_transcription():
        return 1

    events = load_config(args.config)
    dated = {k: v for k, v in events.items() if v['first']}
    pairs = 0
    failures = 0

    # Every real pair the dropdown can produce: each event against every other
    # candidate, not just its configured compare_to.
    for cur, ce in sorted(dated.items()):
        for cand, de in sorted(dated.items()):
            if cur == cand:
                continue
            failures += check_pair(ce['first'], de['first'],
                                   label=f'{cur} vs {cand}')
            pairs += 1
    print(f'configured pairs: {pairs}, mismatches: {failures}')

    # ---- AND ONE PROPERTY ASSERTED AGAINST REALITY ------------------------
    # Everything above compares two IMPLEMENTATIONS: the closed form against a
    # verbatim transcription of `_prev_match_dow`, with the transcription pinned
    # to run.py's source text. That is a strong chain and it has one gap - if
    # `_prev_match_dow` were itself wrong, both sides would agree and this would
    # pass. An equivalence check is blind to a shared premise.
    #
    # Learned the hard way elsewhere: check_b1_switch reported 198/198 green over
    # a shipped defect because client and server made the same mistake. So state
    # what the offset is FOR, independently of either implementation:
    #
    #   a matched date must fall on the SAME WEEKDAY as the row it matches,
    #   and must be the NEAREST such date at or before the naive gap.
    #
    # Neither implementation is consulted - the dates are checked directly.
    prop_bad = 0
    for cur, ce in sorted(dated.items()):
        for cand, de in sorted(dated.items()):
            if cur == cand:
                continue
            # daily_offset IS one of the two implementations, but here it is
            # only being used to produce a date to test - the assertion below
            # consults the calendar, not either implementation.
            off = daily_offset(ce['first'], de['first'])
            gap = (ce['first'] - de['first']).days
            for step in (0, 37, 111, 260):
                row = ce['first'] - timedelta(days=step)
                got = row - timedelta(days=off)
                if got.weekday() != row.weekday():
                    print(f'  FAIL  {cur} vs {cand}: {row} -> {got} is a '
                          f'different weekday')
                    prop_bad += 1
                elif abs(gap - off) > 3:
                    print(f'  FAIL  {cur} vs {cand}: the correction is '
                          f'{gap - off} days, more than the +/-3 a weekday '
                          f'snap can need')
                    prop_bad += 1
    failures += prop_bad
    print(f'weekday property: {"ok" if not prop_bad else str(prop_bad) + " FAILURES"}'
          f' - matched dates share the row\'s weekday, correction within +/-3')

    if args.fuzz:
        random.seed(20260807)
        fuzz_bad = 0
        for _ in range(400):
            cur = date(2026, 1, 1) + timedelta(days=random.randrange(365))
            cand = cur - timedelta(days=random.randrange(30, 2000))
            fuzz_bad += check_pair(cur, cand, span=500, label='fuzz')
        print(f'fuzz pairs: 400, mismatches: {fuzz_bad}')
        failures += fuzz_bad

    if failures:
        print('OFFSET CHECK FAILED', file=sys.stderr)
        return 1
    print('OFFSET CHECK PASSED - the closed form is exact')
    return 0


if __name__ == '__main__':
    sys.exit(main())
