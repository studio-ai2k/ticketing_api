#!/usr/bin/env python3
"""
Compare a dashboard's login background against event_config.csv.

    check_login_bg.py FILE expected|actual

`apply_redesign` replaces the template's whole <style> block, and
{{LOGIN_BG_IMAGE}} is rendered inside it - so without carrying the value
across, every event inherits whatever image the mock was baked with. That is
exactly what happened: paris_xxl is configured for paris_login.jpg and shipped
requesting upload.JPG from Deploy 1 until this check existed.

It fails silently in the browser too - a missing background just falls back to
the solid colour, with nothing in the console.
"""

import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# `\s*` before the brace, and it is load-bearing rather than defensive. The
# production TEMPLATE writes `.db-overlay {` and the redesign sheet writes
# `.db-overlay{`, so the original single-space pattern matched production and
# could not match a v2 page at all - `actual` returned "(no .db-overlay url)"
# for all six. Today that is invisible because assert_redesign only walks the
# root pages; at cutover this check runs on a v2 page and would have failed
# every one of them, on a formatting difference, while reporting a missing
# login background. Found while making P3's negative test real.
OVERLAY_RE = re.compile(r"\.db-overlay\s*\{[^}]*url\('([^']*)'\)")


def main():
    path, which = Path(sys.argv[1]), sys.argv[2]
    if which == 'actual':
        m = OVERLAY_RE.search(path.read_text(encoding='utf-8'))
        print(m.group(1) if m else '(no .db-overlay url)')
        return 0

    # Which event produced this file, via output_filename - postprocess is
    # handed a path, not an event id.
    for row in csv.DictReader(open(REPO / 'event_config.csv', encoding='utf-8-sig')):
        if (row.get('output_filename') or '').strip() == path.name:
            bg = (row.get('login_bg_image') or '').strip() or 'upload.JPG'
            print(as_written(bg, path))
            return 0
    print('(no config row for ' + path.name + ')')
    return 0


def as_written(bg, path):
    """The url() a page at THIS location should carry.

    A v2 page is one directory deeper, so it carries `../<bg>` where a root page
    carries `<bg>`. The prefix is not spelled here: it comes from
    `build_v2.style_transforms`, the same declaration pass 0 builds with and
    `check_pages` replays. Location-dependence is exactly what PAGE_PATHS'
    docstring warns a second copy gets wrong.
    """
    if path.parent.name != 'v2':
        return bg
    sys.path.insert(0, str(REPO / 'scripts'))
    from build_v2 import style_transforms
    (_, new), = style_transforms(bg)
    return re.search(r"url\('([^']*)'\)", new).group(1)


if __name__ == '__main__':
    sys.exit(main())
