#!/usr/bin/env python3
"""
Prove a published dashboard can still be re-stamped, for assert_redesign.sh.
Prints 0 if it can, non-zero if it cannot.

    check_stampable.py FILE

`scripts/stamp_footer.py` patches the "Données API" timestamp in published
HTML, out of band, on a run where nothing sold. If Deploy 3 §7's footer and
that script ever disagree, nothing fails at build time - the stamp just stops
moving, and four hours later the dashboard looks like a dead pipeline. Which
is the exact symptom N4 existed to remove.

So this runs the stamper's own matcher, not a copy of one, against the real
published file. Two things are checked, because the first alone is not enough:

  1. exactly two items match (one footer per page)
  2. a dry-run substitution leaves the item count unchanged

The first version of STAMP_ITEM_RE passed (1) and failed (2): its icon body
was a lazy dot, so a match starting at the "Dernier billet" item ran past that
item's own </svg> and landed on the next item's label, deleting a whole item
on substitution. Six items became two.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
import stamp_footer  # noqa: E402


def main():
    html = Path(sys.argv[1]).read_text(encoding='utf-8')

    matches = len(stamp_footer.STAMP_ITEM_RE.findall(html))
    if matches != 2:
        print(1)
        print(f'{sys.argv[1]}: stamp_footer would match {matches} item(s), want 2',
              file=sys.stderr)
        return 0

    before = html.count('class="pgf-item')
    dry, _ = stamp_footer.restamp(html, stamp_footer.CHECK_LABEL, '00:00')
    after = dry.count('class="pgf-item')
    if before != after:
        print(2)
        print(f'{sys.argv[1]}: a stamp takes the footer from {before} to {after} '
              f'items - it is consuming its neighbours', file=sys.stderr)
        return 0

    print(0)
    return 0


if __name__ == '__main__':
    sys.exit(main())
