#!/usr/bin/env python3
"""
Post-process a generated dashboard HTML before it is published.

Three edits, applied to the generated file only - dashboard_template.html and
run.py are never touched:

  1. Remove the "Mettre à jour" upload link. The API pipeline replaces the
     manual upload flow, so the link would lead somewhere that no longer
     applies.
  2. Footer "📤 Données uploadées" -> "🔄 Données API" (both occurrences).
     The timestamp beside it is left alone.
  3. Remember the password across dashboards.

The template gates each dashboard on sessionStorage under a per-event key
(db_auth_geneve_2026, db_auth_epk_2026, ...), so switching events asks for the
password again even though every dashboard takes the same one, and closing the
browser forgets it entirely. Adding one shared localStorage key on top fixes
both: same origin, so it is visible to every event page, and localStorage
outlives the session. The stored value is a timestamp so an expiry can be added
later without another format change.

The per-event sessionStorage write is left in place - it costs nothing and
keeps the pages working if the shared key is ever cleared.

Exits non-zero if any marker survives, so a template change that breaks these
rules fails the run instead of silently publishing the upload button or a
dashboard that no longer remembers its login.

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

AUTH_KEY = 'festiflow_auth'

# On load the template reads its per-event key and hides the overlay. Widen the
# condition to the shared key as well.
AUTH_CHECK_RE = re.compile(
    r"(var stored = sessionStorage\.getItem\('db_auth_[^']+'\);\s*\n\s*if\()"
    r"(stored === 'ok')(\))"
)

# On a correct password the template records the per-event key. Record the
# shared one alongside it.
AUTH_SET_RE = re.compile(
    r"(sessionStorage\.setItem\('db_auth_[^']+','ok'\);)"
)

# getItem/setItem throw rather than return null when storage is blocked (Safari
# private browsing, cookies-disabled). Unguarded, that exception would abort the
# load-time IIFE before it binds the focus handler and leave a password field
# nobody can type into - so every access is wrapped.
AUTH_CHECK_JS = "dbAuthGet()"
AUTH_SET_JS = "dbAuthSet();"
AUTH_HELPERS_JS = (
    "\nfunction dbAuthGet(){"
    f"try{{return !!localStorage.getItem('{AUTH_KEY}');}}catch(e){{return false;}}"
    "}\n"
    "function dbAuthSet(){"
    f"try{{localStorage.setItem('{AUTH_KEY}', Date.now().toString());}}catch(e){{}}"
    "}\n"
)


IIFE_ANCHOR_RE = re.compile(r"(<script>\s*\n)(\(function\(\)\{\s*\n\s*var stored = sessionStorage)")


def add_shared_auth(html):
    """Make one successful login unlock every dashboard. Returns (html, problems)."""
    problems = []

    # Re-running on an already-patched file would append a second dbAuthSet()
    # call before the mismatch check caught it. Refuse up front instead.
    if AUTH_KEY in html:
        return html, [f"{AUTH_KEY} already present - file has been post-processed already"]

    html, helper_count = IIFE_ANCHOR_RE.subn(
        lambda m: m.group(1) + AUTH_HELPERS_JS + m.group(2), html, count=1
    )
    html, check_count = AUTH_CHECK_RE.subn(
        lambda m: f"{m.group(1)}{m.group(2)} || {AUTH_CHECK_JS}{m.group(3)}", html, count=1
    )
    html, set_count = AUTH_SET_RE.subn(
        lambda m: f"{m.group(1)}{AUTH_SET_JS}", html, count=1
    )

    # All three have to land together: the helpers without the call sites change
    # nothing, and either call site without the helpers is a ReferenceError that
    # would lock people out of the dashboard entirely.
    if (helper_count, check_count, set_count) != (1, 1, 1):
        problems.append(
            f"shared-auth patch did not apply cleanly "
            f"(helpers={helper_count}, load-check={check_count}, on-success={set_count}) "
            f"- the template's password block has changed"
        )
    return html, problems


def postprocess(path):
    path = Path(path)
    html = path.read_text(encoding='utf-8')

    html, link_count = UPLOAD_LINK_RE.subn('', html)
    footer_count = html.count(FOOTER_OLD)
    html = html.replace(FOOTER_OLD, FOOTER_NEW)
    html, problems = add_shared_auth(html)

    if 'Mettre à jour' in html:
        problems.append('"Mettre à jour" still present after removing the upload link')
    if FOOTER_OLD in html:
        problems.append(f'"{FOOTER_OLD}" still present after footer replacement')

    path.write_text(html, encoding='utf-8')
    print(f"{path.name}: removed {link_count} upload link(s), "
          f"replaced {footer_count} footer label(s), "
          f"shared auth via {AUTH_KEY}")

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
