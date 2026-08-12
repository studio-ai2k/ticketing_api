#!/usr/bin/env python3
"""
Trap #14's structural half: no unsubstituted data in the mock.

    python verify/check_mock_literals.py

WHY, AND WHY IT IS TWO CHECKS AND NOT ONE
------------------------------------------
`const LG` shipped epk's 8 083 / 4 513 on every page, and the Suivi headers
shipped "2023 (même jour)" on a page comparing against 2025. Both rendered
cleanly. Both were found by looking at a page for an unrelated reason. Trap #14
says why no identity scan can catch them: a number has no fingerprint.

The instinct is a scan for numeric literals in the template. That was PRICED
before being built, and most of it is not worth having:

  · multi-digit literals in reader-facing text: **42 hits, ~0 real.** SVG
    viewBoxes (`0 0 24 24`), rgba components (`255`), stroke-dasharray (`5 4`),
    percentages. The allow-list would be longer than the check and would need
    editing every time a path changes. AND IT WOULD NOT HAVE CAUGHT LG, which
    is the case that motivated it: LG is syntactically an object literal, i.e.
    data, and the scan skips data by construction.

  · YEAR literals in reader-facing text: **11 hits, 6 real**, all of them the
    ones that mattered. Cheap, stable, and it would have caught A7.

So this is two narrow assertions instead of one broad one:

  1. NO FOREIGN YEAR in text a reader sees ON A BUILT PAGE. Scanned on the
     PAGE and not on the mock, and that distinction is the whole check: the
     mock is a single-event artefact and its literal years are legitimate
     there — `event_identity` replaces them. What must not survive is a year
     that is neither this event's nor any edition it names. (The file-is-not-
     the-page lesson again, third time.)

  2. EVERY top-level data literal is substituted by the build. `const D` and
     `const LG` were the only two, and one of them was missed for weeks. This
     is the assertion that actually covers LG's class: not "does this number
     look wrong" — you cannot tell — but "is this object one the build
     replaces", which is decidable.

(2) is the structural rule stated as a check: every displayed figure has a
traceable source in the payload.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from pages import v2_pages   # noqa: E402 - CUTOVER 6.3, one page list
sys.path.insert(0, str(ROOT / 'scripts'))
MOCK = ROOT / 'redesign' / 'mock' / 'dashboard_v3.39.html'

# Substituted wholesale by pass 0. Anything else at top level with an object or
# array body is data the build does not touch, and therefore the mock's own.
SUBSTITUTED = {'D'}
# Structure rather than event data: menus, colour maps, month names. Each is
# listed by NAME so that adding one is a deliberate act.
STRUCTURAL = {
    'CANDS',      # D11 - now derived from D.cands at runtime
    'CMAP',       # D11 - label -> candidate, derived
    'SERIES',     # D12 - the fetch cache, starts empty
    'MOS', 'DYS', 'COL', 'MO',
    # Full French month names, for the Suivi alignment sentence. Same class as
    # MOS beside it: the CALENDAR, not the edition, so it is identical on every
    # page by construction rather than by luck. MOS is the abbreviated set the
    # table cells use ("9 aoû"); this is the prose set ("9 août 2026"), and the
    # sentence is prose.
    'MOSL',
    'PCOL', 'PRGB',   # platform colour maps: DICE purple, Shotgun green
    # The anchoring modes: three keys and their French labels, identical on
    # every page because they describe the CONTROL, not the edition. The keys
    # are event_config.csv's own comparison_mode values. Which mode a page
    # starts on IS per-event and is not here - it arrives as D.amode, through
    # the payload, like every other per-event fact.
    'AMODES',
    # C3 - the ten section heads: title, tooltip and note. Labels, not figures,
    # and identical on every page because they describe the SECTION rather than
    # the edition. The one per-page note names the picked candidate and travels
    # as SUIVINOTE, a value, precisely so it is not in here.
    'HEADS', 'SUIVINOTE',
}

# Reader-facing text where a year is a FACT about a specific edition rather
# than a stand-in for this page's own. One entry, and it earns its place: the
# fee identity was reconciled against a real DICE payout statement for
# Bordeaux Juin 2026, and that provenance is true on every page.
YEAR_OK = ('reddition Bordeaux Juin 2026',)

YEAR = re.compile(r'\b(?:19|20)\d{2}\b')


def _strip_interp(s):
    """Remove `${…}` with BALANCED braces.

    A regex cannot: the mock nests template literals inside interpolations
    three deep. An unbalanced strip merges the text either side of a `${}`
    and reports years that are already `${YR}` - three of the eleven hits the
    first version produced were its own.
    """
    out, i = [], 0
    while i < len(s):
        j = s.find('${', i)
        if j < 0:
            out.append(s[i:])
            break
        out.append(s[i:j])
        depth, k = 1, j + 2
        while k < len(s) and depth:
            if s[k] == '{':
                depth += 1
            elif s[k] == '}':
                depth -= 1
            k += 1
        out.append(' ')
        i = k
    return ''.join(out)
# Top-level `const NAME = {` / `= [` at column 0, i.e. not inside a function.
TOP_DATA = re.compile(r'^const ([A-Za-z_]\w*)\s*=\s*[\[{]', re.MULTILINE)


def reader_text(body):
    """Template-literal and quoted spans, with every `${…}` removed.

    Crude on purpose: it over-reports rather than under-reports, and the
    allow-list is the six literals that are genuinely structural.
    """
    out = []
    for m in re.finditer(r'`([^`]*)`', body, re.DOTALL):
        yield m.start(), _strip_interp(m.group(1))
    for m in re.finditer(r"'([^'\n]*)'", body):
        yield m.start(), m.group(1)
    return out


def main():
    src = MOCK.read_text(encoding='utf-8')
    failures = []

    # ---- 1. no top-level data literal the build does not replace ----------
    found = set(TOP_DATA.findall(src))
    # SUBSTITUTED is a claim about build_v2, so check it against build_v2
    # rather than trusting the list. A name here whose substitution has been
    # deleted is precisely the LG situation with a comment saying otherwise.
    # Not "does build_v2 mention it" - an error message mentions it. The
    # property is that the BUILT PAGE's copy is not the mock's copy.
    for n in sorted(SUBSTITUTED):
        pat = re.compile(r'const ' + n + r'\s*=\s*(\{.*?\});\s*\n', re.DOTALL)
        mine = pat.search(src)
        if not mine:
            continue
        for page in v2_pages():
            got = pat.search(page.read_text(encoding='utf-8'))
            if got and got.group(1) == mine.group(1):
                failures.append(f'{page.name}: {n} not substituted')
                print(f'  FAIL  {page.name} carries the MOCK\'s `const {n}` verbatim.')
                print(f'        Every figure in it belongs to another event and')
                print(f'        renders cleanly. This is exactly what LG did.')
    stray = sorted(found - SUBSTITUTED - STRUCTURAL)
    if stray:
        for n in stray:
            failures.append(f'const {n}')
            print(f'  FAIL  `const {n} = …` is a top-level data literal that pass 0')
            print(f'        does not substitute. If it carries figures they are the')
            print(f'        MOCK\'s, on every page, rendering cleanly - which is')
            print(f'        exactly what const LG did. Substitute it, or add it to')
            print(f'        STRUCTURAL with a reason.')
    else:
        print(f'  ok    top-level data: {sorted(found & SUBSTITUTED)} substituted, '
              f'{len(found & STRUCTURAL)} structural, none stray')

    # ---- 2. no FOREIGN year on any built page ---------------------------
    for page in v2_pages():
        raw = page.read_text(encoding='utf-8')
        m = re.search(r'const D=(\{.*?\});\s*\n', raw, re.DOTALL)
        if not m:
            continue
        D = json.loads(m.group(1))
        # Years this page may legitimately say: its own, its reference's, and
        # every edition it offers as a comparison or a projection.
        ok = {str(D.get('cur_year')), str(D.get('ref_year'))}
        # Candidate labels are NOT added: they reach the page through `${…}`
        # interpolation, so the scan never sees them. Adding them would have
        # admitted almost every year and made the check unable to fail - it
        # passed on an injected "Trajectoire 2023" the first time for exactly
        # that reason.
        # The payload is data and the <nav> lists every event by name; both are
        # excluded for the same reason they are in check_v2_identity.
        body = re.sub(r'const (?:D=|LG\s*=\s*)[\[{].*?;\s*\n', '', raw, flags=re.DOTALL)
        i, j = body.find('<nav'), body.find('</nav>')
        body = (body[:i] + body[j:]) if 0 <= i < j else body
        body = body[body.find('</nav>'):]
        # WHAT THIS DOES NOT SEE, stated so the blind spot is legible:
        # `reader_text` yields only template-literal and quoted spans. Numbers
        # in ATTRIBUTE values written outside a string - SVG `viewBox`, path
        # `d`, inline `style` pixel values - are not scanned, and rennes.html
        # carries 2001, 2006, 2014, 2027, 2029, 2035 and a dozen more of them.
        # The exclusion is doing real work rather than the scan being trivially
        # clean; the cost is that a genuine stray year sitting inside a path or
        # a viewBox would hide behind exactly the same rule.
        bad = []
        for pos, text in reader_text(body):
            if any(a in text for a in YEAR_OK):
                continue
            for y in YEAR.findall(text):
                if y not in ok:
                    bad.append((y, ' '.join(text.split())[:70]))
        seen, uniq = set(), []
        for h in bad:
            if h[0] in seen:
                continue
            seen.add(h[0])
            uniq.append(h)
        if uniq:
            for y, ctx in uniq:
                failures.append(f'{page.name}: year {y}')
                print(f'  FAIL  {page.name} says {y}, which is not its own year, its')
                print(f'        reference\'s, or any edition it lists: {ctx!r}')
        else:
            print(f'  ok    {page.name}: no foreign year in reader-facing text')

    print()
    if failures:
        print(f'FAILED: {len(failures)}')
        return 1
    print('the mock carries no unsubstituted data and no literal year')
    return 0


if __name__ == '__main__':
    sys.exit(main())
