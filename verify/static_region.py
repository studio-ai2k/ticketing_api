#!/usr/bin/env python3
"""
A page with its `<script>` and `<style>` elements removed. Prints to stdout.

    python3 verify/static_region.py v2/rennes.html

WHY THIS EXISTS
---------------
A grep on a built page counts the stylesheet and the JavaScript as readily as
the markup, and this repo has now been caught by that three times:

  - `align_nav_shell`'s `sw-wrap` guard matched the stylesheet and silently
    skipped every dashboard.
  - `grep -c chart-tabs` read 5 on a correctly-restructured page, because the
    v6.6 sheet still shipped `.chart-tabs` rules. The repair then was to key on
    `class="…"` instead of the bare name.
  - That repair stops working on pass-0 pages. Their body is built at runtime
    from `const D`, so the markup lives in JS TEMPLATE STRINGS - which contain
    the `class="…"` form too. Measured: `class="ac-t"` reads 5 on
    `v2/rennes.html` and every one of the five is inside `<script>`. Zero
    rendered markup, five matches, assertion green.

So the third repair is not another pattern. It is to grep the region the
assertion is actually about. `<style>` belongs to `check_mock_deviations`,
which asserts it byte-for-byte; `<script>` belongs to the browser-driven
checks, which run it. What is left is the markup, and that is what a markup
gate should count.

Measured on v2/rennes.html: 350004 bytes whole, 13670 bytes here.
"""

import re
import sys
from pathlib import Path

SCRIPT_RE = re.compile(r'<script\b[^>]*>.*?</script>', re.DOTALL)
STYLE_RE = re.compile(r'<style\b[^>]*>.*?</style>', re.DOTALL)


def static_region(html):
    return SCRIPT_RE.sub('', STYLE_RE.sub('', html))


def main():
    if len(sys.argv) != 2:
        print(__doc__.strip().split('\n')[2], file=sys.stderr)
        return 2
    sys.stdout.write(static_region(
        Path(sys.argv[1]).read_text(encoding='utf-8')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
