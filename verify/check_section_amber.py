#!/usr/bin/env python3
"""
Count #fbbf24 inside #sec-projection, for assert_redesign.sh. Prints the count.

The Deploy 2 palette pass replaced amber with white and blue inside the
projection block only - #fbbf24 still drives the day tag text colours, the
hebdo bars and the velocity and revenue charts, so a document-wide replace
would repaint half the dashboard. The assertion therefore runs in both
directions: zero here, non-zero in the file at large.

The section is bounded by walking div depth. The first version sliced from
#sec-projection up to the "🎟 Dernier billet vendu" footer string, which
Deploy 3 §7 then deleted - so the check began raising on correct files. A
verify script consuming markup a later pass destroys is the same coupling the
pass table exists to prevent.
"""

import re
import sys
from pathlib import Path

DIV_TAG_RE = re.compile(r'<div\b[^>]*>|</div>')


def main():
    html = Path(sys.argv[1]).read_text(encoding='utf-8')
    start = html.find('<div id="sec-projection"')
    if start < 0:
        print('-1')
        print('#sec-projection not found', file=sys.stderr)
        return 0

    depth = 0
    end = len(html)
    for m in DIV_TAG_RE.finditer(html, start):
        depth += -1 if m.group(0)[1] == '/' else 1
        if depth == 0:
            end = m.end()
            break

    print(html[start:end].count('#fbbf24'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
