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
OVERLAY_RE = re.compile(r"\.db-overlay \{[^}]*url\('([^']*)'\)")


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
            print((row.get('login_bg_image') or '').strip() or 'upload.JPG')
            return 0
    print('(no config row for ' + path.name + ')')
    return 0


if __name__ == '__main__':
    sys.exit(main())
