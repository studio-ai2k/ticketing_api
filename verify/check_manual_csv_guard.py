#!/usr/bin/env python3
"""
The DICE handover guard fires. Proven by firing it.

    python3 verify/check_manual_csv_guard.py

WHY THIS EXISTS
---------------
`fetch_csv.MANUAL_DICE_CSVS` maps an event to a hand-exported DICE CSV, for
events whose DICE account the token cannot reach. Genève 2026 is the only one:
2,912 tickets, ~186k EUR, MORE THAN ITS SHOTGUN SIDE.

When such an event later gets a `dice_mio_id`, the API becomes authoritative and
the file must stop being counted - otherwise every ticket is counted twice. That
handover is guarded twice over:

  1. `manual_dice_retired()` drops the file and SIZES it
  2. `dice_handover_problem()` refuses to publish an API result SMALLER than
     the file it replaced

**Neither branch has ever run.** `geneve_2026` is the only entry in
MANUAL_DICE_CSVS and its `dice_mio_id` is empty, so `manual_path and
dice_mio_id` has never both been true. The guard was ruled, written, and never
fired - and a guard nobody has seen fire is a guard nobody has tested. That is
the entire reason for this file.

WHY THE REFUSAL IS NOT A BLANKET ONE
------------------------------------
The obvious guard is "refuse when an event has both a manual CSV and a
dice_mio_id". That would block a LEGITIMATE handover - the one moment the two
must coexist, because the config gains the id before the file is removed.

The one that exists is better and worth keeping: it permits the handover and
refuses only the actual danger. **A valid token on the wrong account returns
HTTP 200 and an empty set**, which is indistinguishable from "no sales". So the
test is not "are both present" but "did the replacement come back smaller than
what it replaced" - and the message names which of the two to remove.

SIZED-UNKNOWN IS NOT ZERO
-------------------------
If the retired file cannot be read, `manual_dice_retired` returns -1 rather than
0. Returning 0 would make ANY api result pass the shrink test, including an
empty one - the precise failure the mechanism exists to prevent, reintroduced by
its own error handling.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import fetch_csv  # noqa: E402

GENEVE = 'geneve_2026'


def case(label, got, want):
    ok = got == want
    print(f'  {"ok  " if ok else "FAIL"} {label}')
    if not ok:
        print(f'         got  {got!r}')
        print(f'         want {want!r}')
    return [] if ok else [label]


def main():
    fails = []
    path = fetch_csv.MANUAL_DICE_CSVS[GENEVE]
    rows = sum(1 for _ in open(ROOT / path, encoding='utf-8-sig')) - 1

    print(f'the guard that has never fired: {GENEVE}, {rows} manual row(s)\n')
    print('1  manual_dice_retired - which source wins')

    # Today's state: a file and NO api id. The file is used, nothing retired.
    p, n = fetch_csv.manual_dice_retired(path, '')
    fails += case('no dice_mio_id: the file is used and nothing is retired',
                  (p, n), (path, None))

    # THE HANDOVER, which production has never reached.
    p, n = fetch_csv.manual_dice_retired(str(ROOT / path), '588085')
    fails += case('with a dice_mio_id: the file is dropped and sized',
                  (p, n), (None, rows))

    # Unreadable file: sized-unknown, NOT zero.
    p, n = fetch_csv.manual_dice_retired(str(ROOT / 'no-such-export.csv'), '588085')
    fails += case('unreadable export sizes to -1, not 0', (p, n), (None, -1))

    print('\n2  dice_handover_problem - the refusal')

    fails += case('no retirement in play: nothing to refuse',
                  fetch_csv.dice_handover_problem(0, None, False, GENEVE, '1'),
                  None)
    fails += case('api returns MORE than the file it replaced: publish',
                  fetch_csv.dice_handover_problem(rows + 1, rows, False, GENEVE, '1'),
                  None)
    fails += case('api returns EXACTLY as many: publish',
                  fetch_csv.dice_handover_problem(rows, rows, False, GENEVE, '1'),
                  None)

    # THE ONE THAT MATTERS. A wrong-account token looks like "no sales".
    problem = fetch_csv.dice_handover_problem(0, rows, False, GENEVE, '588085')
    if not problem:
        fails.append('an EMPTY api result did not refuse')
        print('  FAIL an empty api result against '
              f'{rows} retired rows did NOT refuse - this is the '
              'wrong-account case, and it publishes silently')
    else:
        print(f'  ok   an empty api result against {rows} retired rows REFUSES')
        for line in problem.splitlines()[:1]:
            print(f'         {line[:96]}')
        # The message must name the remedy, not just the symptom.
        for needle in ('remove dice_mio_id', '--allow-dice-shrink',
                       'MANUAL_DICE_CSVS'):
            if needle not in problem:
                fails.append(f'the refusal does not name {needle!r}')
                print(f'  FAIL the refusal never mentions {needle!r}')

    fails += case('one ticket short still refuses',
                  bool(fetch_csv.dice_handover_problem(rows - 1, rows, False,
                                                       GENEVE, '1')), True)
    fails += case('--allow-dice-shrink lets a real drop through',
                  fetch_csv.dice_handover_problem(0, rows, True, GENEVE, '1'),
                  None)
    fails += case('sized-unknown refuses rather than passing everything',
                  bool(fetch_csv.dice_handover_problem(99999, -1, False,
                                                       GENEVE, '1')), True)

    print()
    if fails:
        print(f'FAILED: {len(fails)}')
        for f in fails:
            print(f'  - {f}')
        return 1
    print('the handover guard fires where it must and stays quiet where it '
          'must not')
    return 0


if __name__ == '__main__':
    sys.exit(main())
