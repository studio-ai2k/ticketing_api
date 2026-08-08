#!/usr/bin/env python3
"""
Run the specification's own worked example through the code.

    python verify/check_spec_example.py

WHY THIS EXISTS
---------------
`HANDOFF.md` documents one Shotgun ticket and states what it should produce:

    price=95.0, gross_price=97.87, ticket_type=3-jours, access_level=regular

`fetch_csv.process_shotgun_ticket` produces `gross_price=107.37` for that exact
input, because it adds `deal_service_fee` as well and the spec's formula does
not. Both are internally consistent. Neither ever failed. Nothing in the test
suite compared them, so the disagreement survived the whole life of the project
and only surfaced when an unrelated question (why `product_name` is never blank)
was traced through the same function.

That is the trap, and it is not about fees:

    A specification and its implementation can BOTH be self-consistent and
    disagree with each other. Nothing fails. Assert the spec against the code,
    not just the code against itself.

HOW IT BEHAVES
--------------
The example is PARSED OUT OF `HANDOFF.md`, never copied here. A copy would be a
third statement of the same fact, free to drift from both - which is the bug
this file exists to prevent.

While O1 is undecided this script pins the disagreement rather than failing on
it: the exact known delta is allowed, and ANY other difference is an error. So
it cannot go quiet, and it cannot be satisfied by a new wrong answer.

When Leo settles the formula (see `docs/O1_FEE_DECISION.md`), set
KNOWN_CONFLICT = None below. From then on the spec and the code must agree
exactly, and whichever one was wrong has to be corrected rather than annotated.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fetch_csv import process_shotgun_ticket  # noqa: E402

# The one difference we have decided to carry, deliberately and visibly, until
# O1 is settled. Set to None the moment it is.
KNOWN_CONFLICT = {
    'gross_price': (97.87, 107.37),   # (what HANDOFF.md says, what the code does)
}

SAMPLE_RE = re.compile(
    r'\*\*Sample response\*\*.*?```json\n(.*?)\n```\s*\n'
    r'This ticket → (.*?)\n',
    re.DOTALL,
)


def parse_spec(handoff):
    """Pull the sample ticket and its stated outputs straight out of the doc."""
    m = SAMPLE_RE.search(handoff)
    if not m:
        raise SystemExit(
            'FAIL: could not find the worked example in HANDOFF.md.\n'
            '      Either it moved or it was deleted. Both mean this guard is\n'
            '      no longer guarding anything - fix the pattern, do not delete\n'
            '      the check.')
    raw = json.loads(m.group(1))
    expected = {}
    for k, v in re.findall(r'`(\w+)=([^`]+)`', m.group(2)):
        expected[k] = float(v) if re.fullmatch(r'-?\d+(\.\d+)?', v) else v
    return raw, expected


def main():
    raw, expected = parse_spec((ROOT / 'HANDOFF.md').read_text(encoding='utf-8'))
    print(f'HANDOFF.md documents {len(expected)} output(s) for its sample ticket')

    row, skip = process_shotgun_ticket(raw, event_days=None)
    if row is None:
        print(f'FAIL: the code SKIPS the documented sample ({skip}).')
        return 1

    failures, pinned = [], []
    for key, want in sorted(expected.items()):
        got = row.get(key)
        if isinstance(want, float) and isinstance(got, (int, float)):
            match = abs(float(got) - want) < 0.005
        else:
            match = str(got) == str(want)
        if match:
            print(f'  ok      {key:14} {got!r}')
        elif key in KNOWN_CONFLICT and (want, round(float(got), 2)) == KNOWN_CONFLICT[key]:
            pinned.append(key)
            print(f'  PINNED  {key:14} spec {want!r} vs code {got!r}  '
                  f'(O1, undecided - see docs/O1_FEE_DECISION.md)')
        else:
            failures.append(key)
            print(f'  FAIL    {key:14} spec {want!r} vs code {got!r}')

    print()
    if failures:
        print(f'FAILED on {len(failures)}: {", ".join(failures)}')
        print('The spec and the code disagree in a way nobody signed off on.')
        return 1
    if pinned:
        print(f'{len(pinned)} pinned conflict(s), unchanged: {", ".join(pinned)}')
        print('Not a pass. O1 is open, and this is the number waiting on Leo.')
        return 0
    print('spec and code agree on every documented output')
    if KNOWN_CONFLICT:
        print('\nNOTE: KNOWN_CONFLICT is still set but nothing is conflicting.')
        print('      O1 has been resolved - clear it so this becomes strict.')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
