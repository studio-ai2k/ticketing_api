#!/usr/bin/env python3
"""
Rewrite the "Données API" footer stamp in an already-published dashboard,
without regenerating it.

WHY THIS EXISTS
---------------
The footer carries two facts that answer two different questions:

    [ticket] Dernier billet   07/08 · 14:37     how fresh is the DATA
    [sync]   Données API      21:42             how fresh is the CHECK

Before M1 they moved together, because every run regenerated the page. M1
skips the rebuild when the merged CSV is byte-identical, which is the right
call - a rebuild mints a fresh timestamp, which forces a commit, which fires a
Pages deploy, for numbers that did not move. But it froze the check stamp too,
so a quiet event's footer said "Données API · 16:50" at 21:00, which is
indistinguishable from a broken pipeline. That has been misdiagnosed twice on
this project already.

So on a quiet run the dashboard is not rebuilt - this patches the one item
that has to keep moving.

FINISHED EVENTS
---------------
Events past their grace period are not fetched at all (J3), so their check
stamp must NOT be bumped - nothing was checked. Left as-is it would recede
indefinitely and read as breakage, so those get a different item instead:

    [lock]   Données figées   07/08

"figées" says the numbers will not move again, and the date says since when.
It reads as a deliberate end state rather than a stalled job. The alternatives
were rejected: "Données finales" describes the result rather than the pipeline,
and anything built on "dernière vérification" would be a claim that we checked,
which is exactly what we did not do.

THE SHARED CONTRACT
-------------------
Deploy 3 §7 replaced the emoji footer with a structured one, and this file
matches on that structure. So the markup lives HERE, and
scripts/postprocess_html.py imports build_item() to emit it and STAMP_ITEM_RE
to assert its own output is still stampable. One definition, not two that can
drift - a drift would not fail the build, it would fail four hours later on a
quiet run, in silence.

USAGE
-----
    stamp_footer.py FILE --checked HH:MM   # bump the check time
    stamp_footer.py FILE --frozen DD/MM    # switch to the frozen item
    stamp_footer.py -    --read-frozen     # print the frozen date on stdin, if any

Exits non-zero if the footer is not found, so a template change fails the run
rather than silently publishing a stamp nobody updated.
"""

import argparse
import re
import sys
from pathlib import Path

CHECK_LABEL = 'Données API'
FROZEN_LABEL = 'Données figées'

# Same family as the two icons Deploy 3 §7 put in the footer: 24 viewBox, no
# fill, currentColor, 1.8 stroke. A sync arrow would be wrong on an event that
# will never sync again, so the frozen item gets a padlock.
ICON_SYNC = (
    '<svg class="pgf-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M20.5 12a8.5 8.5 0 1 1-2.5-6"/><path d="M20.5 3.5V9H15"/></svg>'
)
ICON_LOCK = (
    '<svg class="pgf-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
    '<rect x="4" y="10.5" width="16" height="10" rx="2"/>'
    '<path d="M8 10.5V7a4 4 0 0 1 8 0v3.5"/></svg>'
)
ICONS = {CHECK_LABEL: ICON_SYNC, FROZEN_LABEL: ICON_LOCK}

# Icon, label and value are rewritten together as one substitution. Doing them
# as three edits would allow a half-applied state - a padlock beside "Données
# API", or a sync arrow beside a date - and nothing downstream would catch it.
#
# The icon body is `(?:(?!</svg>).)*`, not `.*?`. With a lazy dot the engine
# starting at the *Dernier billet* item happily expands past that item's own
# </svg>, its label, its value and the separator, and lands on the next item's
# "Données API" label - matching, and deleting the whole first item on
# substitution. That is exactly what happened the first time this was run:
# three items per footer became one. Refusing to cross a </svg> confines the
# match to a single item.
STAMP_ITEM_RE = re.compile(
    r'<span class="pgf-item"><svg class="pgf-ico"(?:(?!</svg>).)*</svg>'
    r'<span class="pgf-k">(' + '|'.join(map(re.escape, ICONS)) + r')</span>'
    r'<span class="pgf-v">([^<]*)</span></span>',
    re.DOTALL,
)


def build_item(label, value):
    """The footer item for `label`. The one place this markup is written."""
    return (f'<span class="pgf-item">{ICONS[label]}'
            f'<span class="pgf-k">{label}</span>'
            f'<span class="pgf-v">{value}</span></span>')


def read_frozen(html):
    """The frozen date already on the page, or None."""
    for m in STAMP_ITEM_RE.finditer(html):
        if m.group(1) == FROZEN_LABEL:
            return m.group(2).strip()
    return None


def restamp(html, label, value):
    """Rewrite every footer stamp item. Returns (html, count)."""
    return STAMP_ITEM_RE.subn(lambda m: build_item(label, value), html)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('file', help="dashboard HTML, or - for stdin with --read-frozen")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--checked', metavar='HH:MM',
                      help='bump the check stamp to this time')
    mode.add_argument('--frozen', metavar='DD/MM',
                      help='switch to the frozen item with this date')
    mode.add_argument('--read-frozen', action='store_true',
                      help='print the frozen date already on the page, if any')
    args = ap.parse_args()

    html = sys.stdin.read() if args.file == '-' else Path(args.file).read_text(encoding='utf-8')

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

    # A match count of 2 does not prove the substitution was surgical. The
    # first version of STAMP_ITEM_RE matched twice and still ate the "Dernier
    # billet" item either side of it, because the icon body was lazy and could
    # span an item boundary. Count what is left instead of trusting the match.
    before, after = html.count('class="pgf-item'), out.count('class="pgf-item')
    if before != after:
        print(f'{args.file}: footer went from {before} to {after} items - the '
              f'stamp is consuming its neighbours, refusing to write',
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
