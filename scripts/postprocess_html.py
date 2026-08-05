#!/usr/bin/env python3
"""
Post-process a generated dashboard HTML before it is published.

Two edits, applied to the generated file only - dashboard_template.html and
run.py are never touched:

  1. Remove the "Mettre à jour" upload link. The API pipeline replaces the
     manual upload flow, so the link would lead somewhere that no longer
     applies.
  2. Footer "📤 Données uploadées" -> "🔄 Données API" (both occurrences).
     The timestamp beside it is left alone.

Exits non-zero if either marker survives, so a template change that breaks
these rules fails the run instead of silently publishing the upload button.

    python scripts/postprocess_html.py api_output/rennes_2026.html
"""

import re
import sys
from pathlib import Path

UPLOAD_LINK_RE = re.compile(
    r'<a class="nm" href="upload\.html[^"]*">.*?Mettre à jour</a>',
    re.DOTALL,
)
FOOTER_OLD = '📤 Données uploadées'
FOOTER_NEW = '🔄 Données API'


def postprocess(path):
    path = Path(path)
    html = path.read_text(encoding='utf-8')

    html, link_count = UPLOAD_LINK_RE.subn('', html)
    footer_count = html.count(FOOTER_OLD)
    html = html.replace(FOOTER_OLD, FOOTER_NEW)

    problems = []
    if 'Mettre à jour' in html:
        problems.append('"Mettre à jour" still present after removing the upload link')
    if FOOTER_OLD in html:
        problems.append(f'"{FOOTER_OLD}" still present after footer replacement')

    path.write_text(html, encoding='utf-8')
    print(f"{path.name}: removed {link_count} upload link(s), "
          f"replaced {footer_count} footer label(s)")

    if problems:
        for p in problems:
            print(f"  ❌ {p}")
        return False
    if link_count == 0:
        print("  ⚠ no upload link found - template may have changed")
    if footer_count == 0:
        print("  ⚠ no footer label found - template may have changed")
    return True


def main():
    if len(sys.argv) < 2:
        raise SystemExit('usage: postprocess_html.py <file.html> [<file.html> ...]')
    ok = True
    for arg in sys.argv[1:]:
        ok = postprocess(arg) and ok
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
