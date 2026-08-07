#!/usr/bin/env python3
"""
Two platform-card checks that need more than a grep, for assert_redesign.sh.
Prints a count of violations - 0 means the check passed.

    check_platform_cards.py FILE dupes   duplicate hrefs across the cards
    check_platform_cards.py FILE order   cards out of canonical order

Kept out of the shell script because both need to compare elements against
each other, and because the card set is variable: 2, 3 and 4 cards are all
live shapes, so the order check runs over whichever subset exists rather than
against a fixed list.
"""

import re
import sys

CANONICAL = [
    'Shotgun · Smartboard',
    'Shotgun · Page publique',
    'DICE · Mio',
    'DICE · Page publique',
]


def main():
    path, check = sys.argv[1], sys.argv[2]
    html = open(path, encoding='utf-8').read()

    if check == 'dupes':
        # Before Deploy 3 the two Shotgun cards carried the same href, because
        # run.py has no Shotgun dashboard URL and falls back to shotgun_url.
        hrefs = re.findall(r'<a class="det-link" href="([^"]*)"', html)
        print(len(hrefs) - len(set(hrefs)))
    elif check == 'order':
        names = re.findall(r'class="det-link-name">([^<]*)</div>', html)
        print(0 if names == [n for n in CANONICAL if n in names] else 1)
    else:
        raise SystemExit(f'unknown check: {check}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
