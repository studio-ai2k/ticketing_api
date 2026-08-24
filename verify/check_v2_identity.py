#!/usr/bin/env python3
"""
No v2 page may carry another event's identity.

    python verify/check_v2_identity.py

bordeaux_oct shipped reading "événement les 5-6 septembre 2026" and
"Elektric Park 2026" — epk's dates and epk's name, on a Bordeaux page. The
payload was correct throughout. The MOCK is a single-event artefact, and pass 0
splices its identity along with its structure.

Three separate hardcoded blocks carry event identity, and enumerating them by
eye missed two of the three. This scan is what found them, so it is the check:
grep every built page for the mock's own event's literals, and fail on any that
is not that page's own event.

The `<option>` elements of the nav's session switcher are excluded — that
switcher legitimately lists every event by name, and its relative hrefs resolve
correctly from /v2/.

THE PAYLOAD IS DATA, AND IT IS CHECKED DIFFERENTLY
--------------------------------------------------
Since A4, `const D` carries one projection candidate per finished edition, and
every candidate carries its `label`. So "Elektric Park 2023" now appears on the
Bordeaux page LEGITIMATELY, as the name of a comparison you can pick.

The `const D={…}` and `const LG={…}` literals are therefore excluded from the
prose scan — and, so that this is a narrowing rather than a hole, the labels
inside the payload are checked against `event_config.csv` instead: every one
must be a real event's `event_name`. A mock literal cannot hide in the payload
without also being a configured event.

That is the same move as the `<nav>` exclusion, and it is the second time a
correct scan has had to learn the difference between prose and data. Weakening
it generically would have been the third.
"""

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from pages import pass0_pages, pass0_dir   # noqa: E402 - CUTOVER 6.3, one page list
PAYLOAD_RE = re.compile(r'const (?:D=|LG\s*=\s*)\{.*?\};\s*\n', re.DOTALL)

# Literals belonging to the mock's own event (epk_2026) and its reference.
MOCK_IDENTITY = ['Elektric Park', 'Île des Impressionnistes', 'Île de Chatou',
                 'campagne_mock', '5–6 septembre', '1–2 septembre',
                 '35 000']
# Paths that break one directory deeper, and a link to a page v2/ has no copy of.
#
# LOCATION-DEPENDENT, AND THE DEPENDENCE INVERTS AT CUTOVER. These forms are
# wrong under `/v2/`, where the page needs `../`. At the repo ROOT they are the
# CORRECT forms - `to_root()` strips exactly these prefixes, and §5 asserts zero
# `../` in a built root page. Measured on a real post-cutover build: 2 of the 3
# match, so asserting them absent would fail all six pages precisely when all
# six are right.
#
# So the check is not "these strings are absent". It is "the asset paths suit
# the directory the page is in", and which half applies is resolved from
# `pages.pass0_dir()` at call time - the same rule as CUTOVER §6.3, rather than a
# flag-day edit on the morning. (This cited check_login_bg.py:61 as the other
# instance of the rule; that file has since been deleted as a check that ran
# nowhere, so the citation would dangle.)
BAD_PATHS = [r'src="LOGO_ROND_JAUNE\.png"', r"url\('upload\.JPG'\)",
             r'href="upload\.html']
# The one page allowed to say "Elektric Park": epk's own.
# epk is the mock's own event, so its name, both venues and both date
# spans are legitimately its own. Everything else must still be absent.
OWN = {'epk.html': ['Elektric Park', 'Île des Impressionnistes',
                    'Île de Chatou', '5–6 septembre', '1–2 septembre']}


def real_event_names():
    """Every `event_name` in the config. The payload's labels must be a subset."""
    names = set()
    with open(ROOT / 'event_config.csv', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            n = (row.get('event_name') or '').strip()
            if n:
                names.add(n)
    return names


def payload_labels(raw):
    """The candidate labels the page offers, from `const D` itself."""
    m = re.search(r'const D=(\{.*?\});\s*\n', raw, re.DOTALL)
    if not m:
        return []
    try:
        cands = (json.loads(m.group(1)).get('projx') or {}).get('cands') or {}
    except ValueError:
        return []
    return [c.get('label') for c in cands.values() if c.get('label')]


def main():
    pages = pass0_pages()
    if not pages:
        print('no v2 pages built - nothing to scan')
        return 0
    names = real_event_names()
    # WHERE pass 0 publishes, resolved now rather than assumed. `../` is
    # right under v2/ and wrong at root, and this is the switch.
    at_root = pass0_dir() == ROOT
    print(f'paths asserted for: {"the repo root" if at_root else "v2/"}')
    failures = []
    for p in pages:
        # The whole <nav> is excluded, not just its <option> elements. The
        # session switcher legitimately lists EVERY event by name, and since v2
        # is built on the postprocessed page it renders as `.sw-item` links
        # rather than `<option>`s - so an exclusion written for the old markup
        # silently stopped excluding anything. Scope to the element, not to the
        # shape it happened to have.
        raw = p.read_text(encoding='utf-8')
        i, j = raw.find('<nav'), raw.find('</nav>')
        html = (raw[:i] + raw[j:]) if 0 <= i < j else raw
        html = PAYLOAD_RE.sub('', html)
        allowed = OWN.get(p.name, [])
        hits = [t for t in MOCK_IDENTITY if t not in allowed and t in html]
        if at_root:
            # Post-cutover the page IS at the root, so the un-prefixed forms are
            # correct and the defect is the opposite one: a `../` that survived
            # the move. Same property - "the paths suit the location" - read
            # from the other end.
            paths = ['../ survived the move to root'] if '../' in html else []
        else:
            paths = [b for b in BAD_PATHS if re.search(b, html)]
        # What the exclusion above gives up, this takes back: a label in the
        # payload must name a configured event.
        labels = payload_labels(raw)
        bogus = [l for l in labels if l not in names]
        if hits or paths or bogus:
            failures.append(p.name)
            print(f'  FAIL  {p.name}: ' +
                  '; '.join([f'foreign identity {h!r}' for h in hits] +
                            [f'unfixed path {b!r}' for b in paths] +
                            [f'payload label {b!r} is not a configured event'
                             for b in bogus]))
        else:
            print(f'  ok    {p.name}: {len(labels)} candidate label(s), all real')
    print()
    if failures:
        print(f'FAILED: {len(failures)} page(s) carry another event\'s identity '
              'or a path that breaks under /v2/.')
        return 1
    print(f'{len(pages)} page(s) carry only their own event')
    return 0


if __name__ == '__main__':
    sys.exit(main())
