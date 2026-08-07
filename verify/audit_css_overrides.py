#!/usr/bin/env python3
"""
Find selectors declared more than once in the stylesheet, and report which
properties the EARLIER declaration leaves in force.

    python verify/audit_css_overrides.py [style/dashboard_v6_8.css]

Three real bugs came from this pattern, each visible only by looking at the
page: .hero-unit (a duplicate pair), .det-link-icon (an !important collision),
and .scenario-toggle (a later rule redesigned the buttons as standalone
controls but left the earlier rule's pill-track background, padding and radius
drawing behind them).

A duplicate is not automatically wrong - a media query legitimately overrides,
and a later rule may mean to inherit. What is worth a look is a later rule that
redesigns a component while silently keeping properties from the earlier one.
So the output is ranked by how many properties survive, not by duplication.
"""

import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RULE_RE = re.compile(r'([^{}@]+)\{([^{}]*)\}')

# A shorthand in the later rule resets its longhands, so `border-bottom: 2px
# solid #fff` does override an earlier `border-bottom-color`. Without this the
# audit reports survivors that are not survivors - which would make it noise,
# and a noisy audit gets ignored, which is the only way this pattern keeps
# shipping.
SHORTHANDS = {
    'background': ('background-color', 'background-image', 'background-position',
                   'background-size', 'background-repeat', 'background-attachment'),
    'border': ('border-width', 'border-style', 'border-color', 'border-top',
               'border-right', 'border-bottom', 'border-left', 'border-top-color',
               'border-right-color', 'border-bottom-color', 'border-left-color'),
    'border-top': ('border-top-color', 'border-top-width', 'border-top-style'),
    'border-right': ('border-right-color', 'border-right-width', 'border-right-style'),
    'border-bottom': ('border-bottom-color', 'border-bottom-width', 'border-bottom-style'),
    'border-left': ('border-left-color', 'border-left-width', 'border-left-style'),
    'margin': ('margin-top', 'margin-right', 'margin-bottom', 'margin-left'),
    'padding': ('padding-top', 'padding-right', 'padding-bottom', 'padding-left'),
    'font': ('font-family', 'font-size', 'font-weight', 'font-style', 'line-height'),
    'flex': ('flex-grow', 'flex-shrink', 'flex-basis'),
    'grid-template': ('grid-template-columns', 'grid-template-rows'),
    'gap': ('row-gap', 'column-gap'),
    'overflow': ('overflow-x', 'overflow-y'),
}


def overridden_by(prop, later):
    """True if `prop` is reset by anything the later rule declares."""
    if prop in later:
        return True
    return any(prop in SHORTHANDS.get(k, ()) for k in later)


def main():
    css = Path(sys.argv[1] if len(sys.argv) > 1
               else REPO / 'style' / 'dashboard_v6_8.css').read_text(encoding='utf-8')
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.DOTALL)

    # Track nesting so @media blocks can be reported separately: a media
    # override is expected, a same-scope one is what this audit is for.
    depth, out, i, media = 0, [], 0, []
    for m in re.finditer(r'@media[^{]*\{|\{|\}', css):
        pass

    top_level, inside_media = [], []
    pos, brace, at_start = 0, 0, None
    for m in re.finditer(r'@media[^{]*\{|\}|\{', css):
        tok = m.group(0)
        if tok.startswith('@media'):
            brace += 1
            if brace == 1:
                at_start = m.end()
        elif tok == '{':
            brace += 1
        else:
            brace -= 1
            if brace == 0 and at_start is not None:
                inside_media.append((at_start, m.start()))
                at_start = None

    def in_media(idx):
        return any(a <= idx < b for a, b in inside_media)

    decls = defaultdict(list)
    for m in RULE_RE.finditer(css):
        sel = ' '.join(m.group(1).split())
        if not sel or sel.startswith('@'):
            continue
        props = {}
        for part in m.group(2).split(';'):
            if ':' in part:
                k, v = part.split(':', 1)
                props[k.strip()] = v.strip()
        for one in [s.strip() for s in sel.split(',') if s.strip()]:
            decls[one].append((m.start(), props, in_media(m.start())))

    findings = []
    for sel, entries in decls.items():
        same = [e for e in entries if not e[2]]
        if len(same) < 2:
            continue
        earlier = {}
        for _, props, _ in same[:-1]:
            earlier.update(props)
        latest = same[-1][1]
        survivors = {k: v for k, v in earlier.items()
                     if not overridden_by(k, latest)}
        if survivors:
            # How much of the earlier rule the later one replaces. Near 0 means
            # the later rule is ADDITIVE - layering a property on, which is
            # fine and is most of this list. High means it is a REDESIGN, and
            # anything it forgot to reset is the latent surprise.
            replaced = len(earlier) - len(survivors)
            ratio = replaced / len(earlier) if earlier else 0
            findings.append((ratio, len(survivors), sel, len(same), survivors, latest))

    findings.sort(reverse=True)
    print(f'{len(decls)} selectors, '
          f'{sum(1 for e in decls.values() if len([x for x in e if not x[2]]) > 1)} '
          f'declared more than once at top level, '
          f'{len(findings)} where the earlier declaration leaves properties in force\n')
    for ratio, n, sel, times, survivors, latest in findings:
        kind = ('REDESIGN - check these' if ratio >= 0.4
                else 'additive' if ratio == 0 else 'partial')
        print(f'  {sel}   ({times} declarations, {n} surviving, '
              f'{ratio:.0%} of the earlier rule replaced -> {kind})')
        for k, v in sorted(survivors.items()):
            print(f'      survives from earlier:  {k}: {v}')
        print(f'      later rule sets:        {", ".join(sorted(latest)) or "(nothing)"}')
        print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
