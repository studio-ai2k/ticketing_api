#!/usr/bin/env python3
"""
One declaration per selector, per property, per condition.

    python3 verify/check_duplicate_decls.py [stylesheet]

WHAT IS ASSERTED, AND WHAT IS ONLY REPORTED
-------------------------------------------
Two rules setting the SAME property on the SAME selector under the SAME
condition are a duplicate. The later one wins and the earlier is dead code.

**A duplicate is only a DEFECT when the two declarations DISAGREE.** Two
identical ones are redundant and harmless: nothing is defeated, nothing renders
differently, and deleting one changes nothing. So identical duplicates are
REPORTED and never fail - the same distinction `check_source_order` draws
between a rule that does not take and one that is masked, and the thing that
keeps both checks honest. A check that failed on all 29 would be demanding
tidiness; this one demands only that no declaration is silently dead.

WHY IT EXISTS, AND WHY IT IS A RULE RATHER THAN THREE FINDINGS
--------------------------------------------------------------
Measured before it was built, because the count is what decides. Across 1497
selector/property/condition keys the sheet had 29 duplicates: 14 disagreeing
across 6 sites, and 15 identical. Six sites is a rule. Fifty would have meant
the assertion was wrong about the sheet rather than the sheet wrong about
itself.

The six, all now deleted, all verified invisible by comparing computed styles at
1180/720/640/480/393 before and after - no difference at any width:

    .grp-h,.kid,.tot,.thead  1fr 58px 44px 46px  ->  1fr 52px 40px 52px 52px
    .card @720               padding 18px        ->  16px 15px
    .nav-top @480            mask 85%            ->  86%
    .dgrid                   gap 12px            ->  26px 34px
    .mb-key @640             gap 8px 18px        ->  9px 12px
    body                     font-family:var()   ->  'DM Sans', sans-serif

THE GRID ONE IS WHY THIS IS WORTH HAVING. Someone wrote a FOUR-column mobile
layout for the group rows and a later block at the same breakpoint replaced it
with five. The four-column version had never rendered once. That is not a tidy-
up: it is a whole layout that lost silently, and nothing in the repo could see
it.

`body`'s is the small one worth knowing: `--ff-body` carries an `-apple-system`
fallback that the later literal drops, so the variable was dead on `body`
specifically.

WHAT IT CANNOT DO
-----------------
Same blind spot as check_source_order, and stated for the same reason:
selectors are compared as NORMALISED TEXT, not as element sets. `.a .b` and
`.b` may hit the same element on a real page and this will not notice. That
needs the DOM, which is what the browser checks are for.
"""

import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'verify'))

from check_source_order import CSS, norm, parse  # noqa: E402


def main():
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else CSS
    rules = parse(target.read_text(encoding='utf-8'))

    seen = collections.defaultdict(list)
    for order, cond, sel, decls, line in rules:
        for prop, val in decls.items():
            seen[(cond or '', norm(sel), prop)].append((line, val))

    disagree, identical = [], []
    for (cond, sel, prop), hits in seen.items():
        if len(hits) < 2:
            continue
        (disagree if len({v for _, v in hits}) > 1 else identical).append(
            (cond, sel, prop, hits))

    try:
        shown = target.relative_to(ROOT)
    except ValueError:
        shown = target
    print(f'{shown}: {len(seen)} selector/property/condition key(s)\n')

    if identical:
        print(f'IDENTICAL - redundant, harmless, not a failure: {len(identical)}')
        for cond, sel, prop, hits in sorted(identical, key=lambda r: r[3][0][0]):
            where = f'@media {cond}' if cond else 'base'
            lines = ', '.join(f'L{l}' for l, _ in hits)
            print(f'  {sel} {{{prop}}} [{where}] at {lines} - same value, so '
                  f'nothing is dead')
        print()

    if disagree:
        print(f'DISAGREEING - the earlier declaration is DEAD: {len(disagree)}')
        for cond, sel, prop, hits in sorted(disagree, key=lambda r: r[3][0][0]):
            where = f'@media {cond}' if cond else 'base'
            print(f'  {sel} {{{prop}}} [{where}]')
            for i, (line, val) in enumerate(hits):
                tag = 'WINS' if i == len(hits) - 1 else 'dead'
                print(f'      L{line:<4} {tag}  {prop}: {val}')
        print()
        print(f'{len(disagree)} declaration(s) are overwritten by a later one on '
              f'the same selector')
        print('and condition. Delete the dead one, or change it to the value it '
              'was meant')
        print('to have. Deleting is invisible by definition - the later one is '
              'already what')
        print('renders - so it is the cheap half of the fix, not the risky one.')
        return 1

    print('no declaration is silently overwritten by a later one')
    return 0


if __name__ == '__main__':
    sys.exit(main())
