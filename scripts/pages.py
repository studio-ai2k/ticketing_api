#!/usr/bin/env python3
"""
The one list of pages this repo builds. Derived from `event_config.csv`.

    python3 scripts/pages.py            # one output_filename per line
    python3 scripts/pages.py v2         # the same names under v2/

WHY THIS EXISTS (CUTOVER.md 6.3)
---------------------------------
Every check that touches pages enumerated them itself, three different ways:
six `(ROOT/'v2').glob('*.html')`, and two HAND-WRITTEN six-name lists in
`check_build_stamp.py` and `assert_redesign.sh`.

At cutover `v2/` stops existing, so all six globs break at once. The obvious
repair is to point them at the new directory and add an exclusion for
`legacy/` - and **an exclusion by glob is coverage lost without a decision**.
The pattern says what a path looks like; it cannot say whether anyone meant it.

Enumerating from the config says the thing that is actually true:

  - `legacy/` is out BECAUSE NO CONFIG ROW POINTS AT IT. That is a property of
    what the repo builds, recorded where the decision lives, rather than a
    property of a path pattern that happens to exclude it today.
  - the two hand-written lists disappear. They are the same hazard as the
    page->event map that was wrong in all six rows, sitting in the layer whose
    job is to catch that.
  - a seventh event is covered by every check on the day it is added to the
    config, not on the day someone remembers to add it in nine places.

WHAT THE SELECTOR EXCLUDES, AND WHO DECIDED
--------------------------------------------
Trap #18's question, asked of this file. `status == 'active'`, and that is
load-bearing rather than tidy: **22 archived rows carry PROSE in
`output_filename`** - one says `Presale - Shotgun only - merge into main` and
twenty-one say `Capacity TBD`. The column is reused as a note on rows nothing
builds.

Every one of those rows is `status='archive'`, so the status filter alone is
exact. The `.html` check below is therefore NOT what excludes them - it is a
guard that RAISES if an ACTIVE row ever grows a name like that, because at that
point the config means something this cannot represent and skipping the row
silently would drop a real page from every check at once.

Measured 2026-08-12: 6 active rows, 6 names, identical to what the globs found
and to what is on disk.
"""

import csv
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG = BASE_DIR / 'event_config.csv'


def page_names(config=None):
    """Ordered, de-duplicated `output_filename` for every ACTIVE event.

    Order is the config's own, so page listings stay stable and reviewable
    rather than reordering whenever a row moves.
    """
    names, seen = [], set()
    path = Path(config or CONFIG)
    with path.open(encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            if (row.get('status') or '').strip() != 'active':
                continue
            name = (row.get('output_filename') or '').strip()
            if not name or name in seen:
                continue
            if not name.endswith('.html'):
                raise SystemExit(
                    f"event_config.csv: active event {row.get('event_id')!r} has "
                    f"output_filename={name!r}, which is not a page name. "
                    f"Archived rows use that column for notes; an ACTIVE row "
                    f"doing so would silently drop a page from every check.")
            seen.add(name)
            names.append(name)
    if not names:
        raise SystemExit('event_config.csv: no active event has an '
                         'output_filename - every page check would silently '
                         'pass on an empty list.')
    return tuple(names)


def pages_in(directory='', root=None, config=None):
    """(present, missing) Paths for the config's pages under `directory`.

    TWO lists, not a filtered one. A glob answers "what is here"; the config
    answers "what should be". Those differ exactly when something is wrong, so
    the caller is handed the difference instead of a list that quietly lost a
    page. Callers that treat `missing` as a failure get the stronger check;
    callers that cannot yet can at least say so.
    """
    base = Path(root or BASE_DIR) / directory if directory else Path(root or BASE_DIR)
    present, missing = [], []
    for name in page_names(config):
        p = base / name
        (present if p.exists() else missing).append(p)
    return present, missing


def v2_pages(root=None, config=None):
    """Sorted Paths for every config page under `v2/`. RAISES if one is absent.

    Raising rather than returning what happens to be there is the whole point of
    replacing the globs. `glob('*.html')` on a directory missing a page returns
    five instead of six and every assertion downstream passes on five - coverage
    lost with nothing said. The config declares six; if the build produced five,
    that is the finding, and it belongs before the assertions rather than
    hidden among them.
    """
    present, missing = pages_in('v2', root, config)
    if missing:
        raise SystemExit(
            'v2/ is missing ' + ', '.join(p.name for p in missing) +
            ' - event_config declares ' + str(len(present) + len(missing)) +
            ' active page(s) and only ' + str(len(present)) + ' were built. '
            'Every page assertion would otherwise pass on the smaller set.')
    return sorted(present)


def main():
    where = sys.argv[1] if len(sys.argv) > 1 else ''
    for name in page_names():
        print(f'{where}/{name}' if where else name)
    return 0


if __name__ == '__main__':
    sys.exit(main())
