#!/usr/bin/env python3
"""
A @media rule that a later base rule outranks does not take.

    python3 verify/check_source_order.py

WHAT IS BEING ASSERTED, AND WHAT IS NOT
---------------------------------------
Media queries add NO specificity. So a base rule declared LATER in the file, at
equal specificity, beats an earlier `@media` rule that sets the same property on
the same selector. The media rule is still there, still correct-looking, and
does nothing.

**The failure this reports is "this rule does not take", NOT "the page is
wrong".** Those are different claims and only the first is provable from the
stylesheet. A defeated rule may render perfectly, because a LATER media rule can
re-supply the same value - and that case is reported separately, as MASKED, so
nobody reads it as a rendering bug and nobody deletes it as noise.

WHY IT EXISTS
-------------
D29: `overflow-x` was declared twice on `html`, one line apart, same
specificity, different values. `clip` won on SOURCE ORDER ALONE - so the sticky
nav worked, resting on the order of two adjacent lines. Reorder them, or insert
anything between, and it breaks with the correct declaration sitting right
there. That is a correct rule defeated at a distance, and nothing could see it.

NO ALLOWLIST, DELIBERATELY
--------------------------
An allowlist would make this check pass by growing rather than by the sheet
getting better, and the entries would outlive their reasons. The counts below
are the record instead: they move when the sheet moves, and a number that
changes is a number someone has to explain.

WHAT IT CANNOT DO
-----------------
Selectors are compared as NORMALISED TEXT, not as element sets. `.a .b` and
`.b` may match the same element on a real page; this will not notice. Deciding
that in general needs the DOM, and the DOM is what the browser checks are for.
So this is sound on what it flags and silent about a class it cannot see -
stated here rather than discovered later.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS = ROOT / 'redesign' / 'style' / 'dashboard_redesign.css'

COMMENT = re.compile(r'/\*.*?\*/', re.DOTALL)

# PINNED, exactly as check_spec_example pins O1: a real finding whose FIX needs
# a ruling, because both available fixes change what renders at <=720px.
#
# `.cmp-trigger`'s mobile padding and gap are declared at L143 inside
# @media (max-width:720px) and outranked by the base rule at L423, which comes
# later at equal specificity. So the tighter mobile sizing someone wrote has
# never applied. Deleting the declarations changes nothing on screen and makes
# the sheet honest; moving them below the base rule makes the intended design
# take effect and makes the controls tighter on a phone. Those are different
# products, so it is Leo's call and not the checker's.
#
# Pinned means: reported every run, exits 0, and ANY OTHER defeat fails. When
# the ruling lands, empty this and it becomes strict and stays strict.
PINNED = {('.cmp-trigger', 'padding'), ('.cmp-trigger', 'gap')}


def strip_comments(text):
    # Replace with spaces so byte offsets -> line numbers stay honest.
    return COMMENT.sub(lambda m: re.sub(r'[^\n]', ' ', m.group(0)), text)


def specificity(sel):
    """(ids, classes+attrs+pseudo-classes, elements). Good enough for this
    sheet: no :is()/:where()/:not() nesting games in it."""
    s = sel.strip()
    ids = len(re.findall(r'(?<![\w-])#[\w-]+', s))
    cls = len(re.findall(r'(?<![\w-])\.[\w-]+', s))
    cls += len(re.findall(r'\[[^\]]*\]', s))
    cls += len(re.findall(r'(?<!:):(?!:)(?!before|after|first-line|first-letter)'
                          r'[a-z-]+', s))
    els = len(re.findall(r'(?:^|[\s>+~])([a-z][\w-]*)', s))
    els += len(re.findall(r'::[a-z-]+', s))
    return (ids, cls, els)


def declarations(block):
    """{prop: value} for a declaration block, last wins as CSS does."""
    out = {}
    for part in block.split(';'):
        if ':' not in part:
            continue
        prop, _, val = part.partition(':')
        prop = prop.strip().lower()
        if prop and not prop.startswith('--'):
            out[prop] = val.strip()
    return out


def parse(text):
    """[(order, media_or_None, selector, {prop: val}, line)] in source order."""
    src = strip_comments(text)
    rules, order, i, n = [], 0, 0, len(src)

    def line_of(pos):
        return src.count('\n', 0, pos) + 1

    while i < n:
        brace = src.find('{', i)
        if brace == -1:
            break
        prelude = src[i:brace].strip()
        if prelude.startswith('@media'):
            depth, j = 1, brace + 1
            while j < n and depth:
                if src[j] == '{':
                    depth += 1
                elif src[j] == '}':
                    depth -= 1
                j += 1
            inner = src[brace + 1:j - 1]
            cond = prelude[len('@media'):].strip()
            base = brace + 1
            k = 0
            while k < len(inner):
                b2 = inner.find('{', k)
                if b2 == -1:
                    break
                e2 = inner.find('}', b2)
                if e2 == -1:
                    break
                sels = inner[k:b2].strip()
                decls = declarations(inner[b2 + 1:e2])
                for sel in filter(None, (s.strip() for s in sels.split(','))):
                    order += 1
                    rules.append((order, cond, sel, decls, line_of(base + k)))
                k = e2 + 1
            i = j
            continue
        if prelude.startswith('@'):
            # @keyframes / @supports / @font-face: skipped whole. None appear in
            # this sheet; if one does, it is skipped rather than mis-parsed.
            depth, j = 1, brace + 1
            while j < n and depth:
                if src[j] == '{':
                    depth += 1
                elif src[j] == '}':
                    depth -= 1
                j += 1
            i = j
            continue
        end = src.find('}', brace)
        if end == -1:
            break
        decls = declarations(src[brace + 1:end])
        for sel in filter(None, (s.strip() for s in prelude.split(','))):
            order += 1
            rules.append((order, None, sel, decls, line_of(brace)))
        i = end + 1
    return rules


def norm(sel):
    return re.sub(r'\s+', ' ', sel.strip()).lower()


def main():
    # A path argument, so the negative tests can point this at a constructed
    # sheet. A check that can only ever read one file cannot be made to fail on
    # demand, and one that cannot be made to fail is not yet trusted.
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else CSS
    text = target.read_text(encoding='utf-8')
    rules = parse(text)
    media = [r for r in rules if r[1]]
    base = [r for r in rules if not r[1]]
    try:
        shown = target.relative_to(ROOT)
    except ValueError:
        shown = target
    print(f'{shown}: {len(rules)} rule(s), '
          f'{len(media)} inside @media, {len(base)} base\n')

    defeated, masked = [], []
    for order, cond, sel, decls, line in media:
        spec = specificity(sel)
        for prop, val in decls.items():
            # A LATER base rule, same selector text, equal or higher
            # specificity, same property.
            beaten = [b for b in base
                      if b[0] > order and norm(b[2]) == norm(sel)
                      and prop in b[3] and specificity(b[2]) >= spec]
            if not beaten:
                continue
            b = beaten[0]
            # Does a LATER media rule put the mobile value back? Then nothing
            # renders wrong and this is not a rendering defect - but the rule
            # here still does not take, and saying so is the point.
            remask = [m for m in media
                      if m[0] > b[0] and norm(m[2]) == norm(sel) and prop in m[3]]
            entry = (sel, prop, line, val, b[4], b[3][prop], cond,
                     remask[0][4] if remask else None)
            (masked if remask else defeated).append(entry)

    for title, rows in (('DOES NOT TAKE', defeated), ('MASKED', masked)):
        if not rows:
            continue
        print(f'{title}: {len(rows)}')
        for sel, prop, line, val, bline, bval, cond, rline in rows:
            print(f'  L{line:<4} @media {cond}')
            print(f'        {sel} {{ {prop}: {val} }}')
            print(f'        outranked by the base rule at L{bline} '
                  f'({prop}: {bval}), which comes LATER at equal specificity')
            if rline:
                print(f'        a later @media at L{rline} re-supplies {prop}, '
                      f'so nothing renders wrong - but THIS rule still does '
                      f'not take')
        print()

    live = [d for d in defeated if (d[0], d[1]) not in PINNED]
    pinned = [d for d in defeated if (d[0], d[1]) in PINNED]
    if pinned:
        print(f'{len(pinned)} PINNED declaration(s), awaiting a ruling: '
              f'{", ".join(sorted(f"{a} {b}" for a, b, *_ in pinned))}')
        print('Both fixes change the sheet\'s meaning - one changes what '
              'renders at <=720px,')
        print('the other admits the rule never applied - so the choice is a '
              'ruling, not a tidy-up.')
        print()
    if live:
        print(f'{len(live)} @media declaration(s) do not take.')
        print('Move the base rule ABOVE the @media block, or delete the '
              'declaration that')
        print('cannot win. Both fix it; the check does not care which.')
        return 1
    if masked:
        print(f'{len(masked)} masked declaration(s): outranked, but a later '
              f'@media re-supplies the value.')
        print('Nothing renders wrong. Left as a finding rather than a failure, '
              'because the')
        print('rule that does not take is still a rule someone will read and '
              'believe.')
    if pinned:
        print(f'no UNPINNED @media declaration is defeated - {len(pinned)} '
              f'pinned, above, still awaiting their ruling')
    else:
        print('no @media declaration is defeated by a later base rule')
    return 0


if __name__ == '__main__':
    sys.exit(main())
