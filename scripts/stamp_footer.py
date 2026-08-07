#!/usr/bin/env python3
"""
Rewrite the "Données API" footer stamp in an already-published dashboard,
without regenerating it.

WHY THIS EXISTS
---------------
The footer carries two facts that answer two different questions:

    🎟 Dernier billet vendu · DD/MM · HH:MM   how fresh is the DATA
    🔄 Données API · HH:MM                    how fresh is the CHECK

Before M1 they moved together, because every run regenerated the page. M1
skips the rebuild when the merged CSV is byte-identical, which is the right
call - a rebuild mints a fresh timestamp, which forces a commit, which fires a
Pages deploy, for numbers that did not move. But it froze the check stamp too,
so a quiet event's footer said "Données API · 16:50" at 21:00, which is
indistinguishable from a broken pipeline. That has been misdiagnosed twice on
this project already.

So on a quiet run the dashboard is not rebuilt - this patches the one line
that has to keep moving. A quiet run produces a one-line diff per file instead
of a full regeneration, and never touches run.py.

FINISHED EVENTS
---------------
Events past their grace period are not fetched at all (J3), so their check
stamp must NOT be bumped - nothing was checked. Left as-is it would recede
indefinitely and read as breakage, so those get a different label instead:

    🔒 Données figées · DD/MM

"figées" says the numbers will not move again, and the date says since when.
It reads as a deliberate end state rather than a stalled job. The alternatives
were rejected: "Données finales" describes the result rather than the pipeline,
and anything built on "dernière vérification" would be a claim that we checked,
which is exactly what we did not do.

USAGE
-----
    stamp_footer.py FILE --checked HH:MM   # bump the check time
    stamp_footer.py FILE --frozen DD/MM    # switch to the frozen label
    stamp_footer.py -    --read-frozen     # print the frozen date on stdin, if any

Exits non-zero if the footer is not found, so a template change fails the run
rather than silently publishing a stamp nobody updated.
"""

import argparse
import re
import sys
from pathlib import Path

CHECK_LABEL = '🔄 Données API'
FROZEN_LABEL = '🔒 Données figées'

# The value runs to the next entity or tag - the footer separates its fields
# with "&nbsp;·&nbsp;" and ends with "</div>". Matching either terminator keeps
# this working if the last field ever moves.
STAMP_RE = re.compile(
    r'(' + '|'.join(map(re.escape, (CHECK_LABEL, FROZEN_LABEL))) + r')'
    r'( · )([^&<]*?)(\s*(?:&nbsp;|<))'
)


def read_frozen(html):
    """The frozen date already on the page, or None."""
    for m in STAMP_RE.finditer(html):
        if m.group(1) == FROZEN_LABEL:
            return m.group(3).strip()
    return None


def restamp(html, label, value):
    """Rewrite every footer stamp. Returns (html, count)."""
    return STAMP_RE.subn(
        lambda m: f'{label}{m.group(2)}{value}{m.group(4)}', html)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('file', help="dashboard HTML, or - for stdin with --read-frozen")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--checked', metavar='HH:MM',
                      help='bump the check stamp to this time')
    mode.add_argument('--frozen', metavar='DD/MM',
                      help='switch to the frozen label with this date')
    mode.add_argument('--read-frozen', action='store_true',
                      help='print the frozen date already on the page, if any')
    args = ap.parse_args()

    if args.file == '-':
        html = sys.stdin.read()
    else:
        html = Path(args.file).read_text(encoding='utf-8')

    if args.read_frozen:
        found = read_frozen(html)
        if found:
            print(found)
        return 0

    label, value = ((CHECK_LABEL, args.checked) if args.checked
                    else (FROZEN_LABEL, args.frozen))
    out, count = restamp(html, label, value)

    # The footer is emitted once per page and the template has two pages. One
    # match means the template changed and half the dashboard would keep the
    # old stamp, which is worse than not stamping at all.
    if count != 2:
        print(f'{args.file}: footer stamp matched {count} time(s), expected 2',
              file=sys.stderr)
        return 1

    if out == html:
        print(f'{Path(args.file).name}: already {label} · {value}, not rewritten')
        return 0

    Path(args.file).write_text(out, encoding='utf-8')
    print(f'{Path(args.file).name}: {label} · {value}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
