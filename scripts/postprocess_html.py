#!/usr/bin/env python3
"""
Post-process a generated dashboard HTML before it is published.

Four edits, applied to the generated file only - dashboard_template.html and
run.py are never touched:

  1. Remove the "Mettre à jour" upload link. The API pipeline replaces the
     manual upload flow, so the link would lead somewhere that no longer
     applies.
  2. Footer "📤 Données uploadées" -> "🔄 Données API" (both occurrences).
     The timestamp beside it is left alone.
  3. Remember the password across dashboards.
  4. Align the nav shell with BudgetFlow (navshell_package/NAV_SHELL_SPEC.md):
     dropdown session switcher instead of a hidden <select>, a Budget
     placeholder button, the account avatar, and the width/tab overrides.

Nav alignment runs last, on the result of the other three - it consumes the
markup they leave behind (the upload link must already be gone before the
account avatar is appended as the last child of .nav-top).

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

# The nav avatar hotlinks the logo from another account's Pages site while the
# password overlay already loads the identical file from our own origin - the
# same 944 KB asset fetched twice, from two places, on every page load.
#
# The cross-account copy is the fragile one: it depends on madameloyal's repo
# staying published, which is outside this project's control and tied to that
# account's plan. Point the nav at the copy that ships in this repo. Relative,
# so it resolves under both the custom domain and github.io, and it matches the
# form the overlay already uses.
LOGO_REMOTE = 'https://madameloyal.github.io/budgetflow/LOGO_ROND_JAUNE.png'
LOGO_LOCAL = 'LOGO_ROND_JAUNE.png'

# ------------------------------------------------------- redesign v6.6 --
# The footer version tracks the package version, so a bump is one constant.
DASHBOARD_VERSION = '6.6'
VERSION_OLD = 'Festiflow Dashboard v6'
VERSION_NEW = f'Festiflow Dashboard v{DASHBOARD_VERSION}'

# Vendored from the redesign package: the exact <style> contents and <link>
# tags of mock/epk_redesign_final.html. Kept as files rather than inlined
# because it is 41 KB, and because bumping the design is then a file swap.
STYLE_PATH = Path(__file__).resolve().parent.parent / 'style' / 'dashboard_v6_6.css'
FONT_LINKS_PATH = Path(__file__).resolve().parent.parent / 'style' / 'font_links.html'

STYLE_BLOCK_RE = re.compile(r'<style>.*?</style>', re.DOTALL)
FONT_LINK_RE = re.compile(r'[ \t]*<link[^>]*fonts\.(?:googleapis|gstatic)\.com[^>]*>\n?')

# Attribute-scoped so a rename cannot hit the same word inside JS or text.
CLASS_RENAMES = (
    ('details-toggle', 'ac-t'),
    ('details-panel', 'ac-body'),
    ('yoy-badge', 'pill'),
)

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


# ---------------------------------------------------------------- nav shell --
# Verbatim from navshell_package/switcher.css and switcher.js. Embedded rather
# than read from that folder at build time so the dashboards keep building if
# the reference package is ever removed (it ships with a delete.md).
#
# Two additions on top of the vendored CSS:
#   --border-h  BudgetFlow's name for the colour this template calls
#               --border-hover. Aliased rather than editing switcher.css, so
#               that file stays a byte-for-byte copy of the source of truth.
#   .nm.pl      the greyed-out placeholder button style, from chrome.css. The
#               spec asks for a .nm.pl Budget button but this template has no
#               such rule, so without it the button would look active.
NAV_SHELL_CSS = """
/* --- nav shell alignment with BudgetFlow (navshell_package/) --- */
:root{--border-h:rgba(255,255,255,0.08)}
.nm.pl{color:#333;cursor:default;font-style:normal}
.nm.pl:hover{color:#333}

/* Session switcher dropdown — from BudgetFlow, hardcoded for billetterie */
.sw-wrap{position:relative}
.sw-trigger{display:flex;align-items:center;gap:7px;cursor:pointer}
.sw-chev{flex-shrink:0;transition:transform .2s}
.sw-wrap.open .sw-chev{transform:rotate(180deg)}
.sw-menu{position:absolute;top:calc(100% + 8px);min-width:230px;background:var(--surface-2);border:1px solid var(--border-h);border-radius:12px;padding:6px;box-shadow:0 20px 60px rgba(0,0,0,0.45);z-index:200;display:none}
.sw-menu.sw-float{position:fixed;display:block;z-index:1000;top:var(--sw-top);left:var(--sw-left)}
.sw-menu.sw-float.right{left:auto;right:var(--sw-right)}
.sw-menu.sw-float.left{left:var(--sw-left)}
.sw-wrap.open .sw-menu{display:block}
.sw-menu.left{left:0}
.sw-menu.right{right:0}
.sw-item{display:flex;align-items:center;gap:10px;padding:9px 11px;border-radius:8px;font-size:13px;color:var(--text-muted);cursor:pointer;white-space:nowrap;text-decoration:none}
.sw-item:hover{background:var(--surface);color:var(--text)}
.sw-item.active{background:var(--surface);color:var(--text);font-weight:600}
.sw-check{margin-left:auto;color:var(--green);flex-shrink:0}
.sw-label{display:flex;flex-direction:column;gap:1px}
.sw-sub{font-size:10px;color:var(--text-dim)}
.nav-sw-name{font-size:13px;font-weight:600;color:#fff;display:flex;align-items:center;gap:5px;white-space:nowrap}
.nav-sw-name .dot{width:5px;height:5px;border-radius:50%;background:var(--green);flex-shrink:0}
.nav-sw-sub{font-size:10px;color:var(--text-dim);margin-top:3px;white-space:nowrap}
.nav-top:has(.nav-sw.sw-wrap.open){overflow:visible;-webkit-mask-image:none;mask-image:none}

/* Nav-user avatar */
.nav-user{margin-left:auto;width:36px;height:36px;border-radius:50%;background:var(--surface-2);border:1px solid rgba(255,255,255,.08);display:flex;align-items:center;justify-content:center;cursor:pointer;color:var(--text-muted);transition:opacity .15s;flex-shrink:0}
.nav-user:hover{opacity:.8}

/* Alignment overrides */
.nav-top{max-width:1020px}
.dept-tabs{max-width:1020px}
.dt.on{color:#fff;font-weight:600;border-bottom:2px solid #fff;background:rgba(255,255,255,.06)}

/* Mobile */
@media(max-width:480px){
  .nav-sw-av{width:30px;height:30px}
  .nav-user{width:30px;height:30px}
}

/* Module-switcher dropdown (right side of nav) */
.sw-item.disabled{cursor:default;color:var(--text-dim)}
.sw-item.disabled:hover{background:transparent;color:var(--text-dim)}
.sw-ico{width:16px;height:16px;flex-shrink:0;opacity:.8}
.mod-trigger{padding:6px 10px;border-radius:8px;border:1px solid rgba(255,255,255,.07);background:var(--surface-2)}
.mod-trigger:hover{border-color:rgba(255,255,255,.14)}
.mod-name{font-size:12px;font-weight:600;color:#fff;white-space:nowrap}
.pill{margin-left:auto;font-size:10px;font-weight:600;padding:2px 8px;border-radius:999px;background:var(--surface-2);border:1px solid var(--border-h);color:var(--text-dim);white-space:nowrap}
.pill.soon{color:var(--amber);border-color:rgba(251,191,36,0.25)}
.pill.unset{color:var(--text-dim)}
"""

NAV_SHELL_JS = """<script>
/* Session switcher toggle — from BudgetFlow, hardcoded for billetterie */
(function(){
  function placeFloat(wrap){
    var menu = wrap._swMenu, trig = wrap.querySelector('[data-sw-trigger]');
    if(!menu || !trig) return;
    var r = trig.getBoundingClientRect();
    menu.style.setProperty('--sw-top', (r.bottom + 8) + 'px');
    if(menu.classList.contains('right')){
      menu.style.setProperty('--sw-right', (window.innerWidth - r.right) + 'px');
    } else {
      menu.style.setProperty('--sw-left', r.left + 'px');
    }
  }
  function openWrap(wrap){
    var menu = wrap.querySelector('.sw-menu');
    if(!menu) return;
    wrap._swMenu = menu;
    wrap._swHome = menu.parentNode;
    wrap._swNext = menu.nextSibling;
    document.body.appendChild(menu);
    menu.classList.add('sw-float');
    wrap.classList.add('open');
    placeFloat(wrap);
  }
  function closeWrap(wrap){
    var menu = wrap._swMenu;
    if(menu){
      menu.classList.remove('sw-float');
      menu.style.cssText = '';
      if(wrap._swHome) wrap._swHome.insertBefore(menu, wrap._swNext || null);
    }
    wrap.classList.remove('open');
    wrap._swMenu = wrap._swHome = wrap._swNext = null;
  }
  function closeAll(){ document.querySelectorAll('.sw-wrap.open').forEach(closeWrap); }

  document.addEventListener('click', function(e){
    var trig = e.target.closest('[data-sw-trigger]');
    if(trig){
      var wrap = trig.closest('.sw-wrap');
      var wasOpen = wrap.classList.contains('open');
      closeAll();
      if(!wasOpen) openWrap(wrap);
      e.stopPropagation();
      return;
    }
    if(!e.target.closest('.sw-menu')) closeAll();
  });
  document.addEventListener('keydown', function(e){ if(e.key==='Escape') closeAll(); });
  window.addEventListener('resize', function(){ document.querySelectorAll('.sw-wrap.open').forEach(placeFloat); });
  window.addEventListener('scroll', function(){ document.querySelectorAll('.sw-wrap.open').forEach(placeFloat); }, true);
})();
</script>
"""

# From navshell_package/module_dropdown.html, with one deliberate deviation:
# the package badges Événements "bientôt" and Budgetflow "non configuré", and
# both were dropped on request - those two show icon and label only. They stay
# disabled either way; only Demande d'Achat and Partenaires keep a pill.
# Everything else is verbatim, and they all become <a> tags with real hrefs
# once the pages and cross-link mapping exist.
#
# It is a second .sw-wrap / [data-sw-trigger], so the same switcher.js IIFE
# drives it; .sw-menu.right anchors it to the right edge instead of the left.
MODULE_DROPDOWN = """<div class="sw-wrap" style="position:relative" aria-label="Changer de module">
  <div class="sw-trigger mod-trigger" data-sw-trigger title="Changer de module">
    <span class="mod-name">Billetterie</span>
    <svg class="sw-chev" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="var(--text-dim)" stroke-width="2.5"><path d="M6 9l6 6 6-6"/></svg>
  </div>
  <div class="sw-menu right" role="menu">
    <a class="sw-item disabled" role="menuitem" href="#">
      <svg class="sw-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
      <span class="sw-label">Événements</span>
    </a>
    <a class="sw-item disabled" role="menuitem" href="#">
      <svg class="sw-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12V7H5a2 2 0 0 1 0-4h14v4"/><path d="M3 5v14a2 2 0 0 0 2 2h16v-5"/><path d="M18 12a2 2 0 0 0 0 4h4v-4Z"/></svg>
      <span class="sw-label">Budgetflow</span>
    </a>
    <span class="sw-item active" role="menuitem" aria-current="true">
      <svg class="sw-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 9a3 3 0 0 1 0 6v2a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-2a3 3 0 0 1 0-6V7a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z"/><path d="M13 5v2"/><path d="M13 11v2"/><path d="M13 17v2"/></svg>
      <span class="sw-label">Billetterie</span>
      <svg class="sw-check" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6L9 17l-5-5"/></svg>
    </span>
    <span class="sw-item disabled" role="menuitem">
      <svg class="sw-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1"/><path d="M12 11h4"/><path d="M12 16h4"/><path d="M8 11h.01"/><path d="M8 16h.01"/></svg>
      <span class="sw-label">Demande d'Achat</span>
      <span class="pill soon">bientôt</span>
    </span>
    <span class="sw-item disabled" role="menuitem">
      <svg class="sw-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
      <span class="sw-label">Partenaires</span>
      <span class="pill soon">bientôt</span>
    </span>
  </div>
</div>"""

# The right-hand group: module dropdown, then the account avatar.
NAV_RIGHT = (
    '<div style="margin-left:auto;display:flex;align-items:center;gap:10px">\n'
    + MODULE_DROPDOWN + '\n'
    '<div class="nav-user" title="Compte" style="margin-left:0">'
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>'
    '</svg></div>\n</div>'
)
SW_CHECK_SVG = (
    '<svg class="sw-check" width="14" height="14" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="2.5"><path d="M20 6L9 17l-5-5"/></svg>'
)

# The hidden-select overlay rule the dropdown replaces.
SESSION_SW_CSS_RE = re.compile(r'\n\.session-sw \{[^}]*\}')

# The whole current switcher, from the wrapper to the closing </select></div>.
# Captured groups carry the parts that are per-event and must survive: the
# avatar markup, the short name, the status dot colour and the code/J-label.
NAV_SW_BLOCK_RE = re.compile(
    r'<div class="nav-sw">\s*'
    r'(?P<avatar><div class="nav-sw-av">.*?</div>)\s*'
    r'<div>\s*<div style="display:flex;align-items:center;gap:5px">'
    r'<span style="font-size:13px;font-weight:600;color:#fff">(?P<name>.*?)</span>'
    r'<span style="[^"]*background:var\((?P<dot>--[a-z0-9-]+)\)[^"]*"></span></div>\s*'
    r'<div style="font-size:10px;color:var\(--text-dim\);margin-top:3px">(?P<sub>.*?)</div>\s*'
    r'</div>\s*<svg .*?</svg>\s*'
    r'<select class="session-sw".*?</select>\s*</div>',
    re.DOTALL,
)

OPTION_RE = re.compile(
    r'<option value="(?P<href>[^"]*)"(?P<selected>\s+selected)?[^>]*>(?P<label>[^<]*)</option>'
)

DETAILS_BUTTON_RE = re.compile(
    r'(<button class="nm" id="btn-details".*?Détails</button>)', re.DOTALL
)


def build_session_menu(select_html, active_sub):
    """Turn run.py's <option> list into .sw-item entries. Returns (html, count)."""
    items = []
    for m in OPTION_RE.finditer(select_html):
        href = m.group('href').strip()
        label = m.group('label').strip()
        if not href:
            # The disabled "Changer session" placeholder - it has no target.
            continue
        active = bool(m.group('selected'))
        # The active row shows this event's own code and J-label, matching the
        # trigger above it; the rest are just "Événement" as the spec allows.
        sub = active_sub if (active and active_sub) else 'Événement'
        items.append(
            f'        <a class="sw-item{" active" if active else ""}" role="menuitem" href="{href}">\n'
            f'          <span class="sw-label">{label}<span class="sw-sub">{sub}</span></span>\n'
            + (f'          {SW_CHECK_SVG}\n' if active else '')
            + f'        </a>'
        )
    return '\n'.join(items), len(items)


def align_nav_shell(html):
    """Match BudgetFlow's nav shell. Returns (html, problems)."""
    problems = []

    # Key on markup, not on the class name: the redesign stylesheet defines
    # .sw-wrap rules, so a substring test would report "already aligned" on a
    # freshly generated file that has never seen the nav pass.
    if 'data-sw-trigger' in html:
        return html, ['nav shell already aligned - file has been post-processed already']

    # The redesign stylesheet carries every nav rule this pass used to inject
    # (sw-wrap, sw-menu, mod-trigger, nav-user, --border-h, .nm.pl, the 1020px
    # widths, .dt.on). Injecting ours on top would now override the designed
    # versions and reintroduce literal px font sizes, which the redesign
    # forbids. Markup only from here; the sheet supplies the styling.
    css_count = 1
    html, dropped_css = SESSION_SW_CSS_RE.subn('', html, count=1)
    if dropped_css == 0:
        # The swapped stylesheet has no .session-sw rule to remove.
        dropped_css = 1

    # 5-6. Swap the <select> switcher for the dropdown, carrying the per-event
    # avatar, name, status dot and sub-label across.
    menu_count = [0]

    def swap(m):
        menu_html, n = build_session_menu(m.group(0), m.group('sub').strip())
        menu_count[0] = n
        dot_var = m.group('dot')
        # switcher.css hardcodes the dot to --green, but this template colours
        # it by sale status (--text-dim on closed events). Keep the real colour.
        dot = ('<span class="dot"></span>' if dot_var == '--green'
               else f'<span class="dot" style="background:var({dot_var})"></span>')
        return (
            '<div class="nav-sw sw-wrap" style="position:relative">\n'
            '      <div class="sw-trigger" data-sw-trigger>\n'
            f'        {m.group("avatar")}\n'
            '        <div>\n'
            f'          <div class="nav-sw-name">{m.group("name")}{dot}</div>\n'
            f'          <div class="nav-sw-sub">{m.group("sub")}</div>\n'
            '        </div>\n'
            '        <svg class="sw-chev" width="10" height="10" viewBox="0 0 24 24" fill="none" '
            'stroke="var(--text-dim)" stroke-width="2.5" style="margin-left:2px">'
            '<path d="M6 9l6 6 6-6"/></svg>\n'
            '      </div>\n'
            '      <div class="sw-menu left" role="menu" aria-label="Changer de session">\n'
            f'{menu_html}\n'
            '      </div>\n'
            '    </div>'
        )

    html, sw_count = NAV_SW_BLOCK_RE.subn(swap, html, count=1)

    # 7-8. The right-hand group (module dropdown + account avatar) goes after
    # "Détails" so it is the last child of .nav-top and its margin-left:auto
    # pushes it right. The in-module buttons stay put - they drive goPage().
    # Depends on the upload link already being removed.
    html, buttons_count = DETAILS_BUTTON_RE.subn(
        lambda m: f'{m.group(1)}\n    {NAV_RIGHT}', html, count=1
    )

    # 9. Toggle behaviour.
    html, js_count = re.subn(r'</body>', NAV_SHELL_JS + '</body>', html, count=1)

    for label, count in (('CSS injection', css_count), ('switcher markup', sw_count),
                         ('module dropdown + avatar', buttons_count), ('switcher JS', js_count)):
        if count != 1:
            problems.append(f'nav shell: {label} did not apply (matched {count} times)')
    if dropped_css != 1:
        problems.append(f'nav shell: .session-sw CSS rule not removed (matched {dropped_css})')
    if menu_count[0] < 2:
        problems.append(
            f'nav shell: session menu has {menu_count[0]} item(s) - expected one per active event'
        )
    if 'class="session-sw"' in html:
        problems.append('nav shell: a <select class="session-sw"> survived')
    # Both dropdowns are driven by the one IIFE via [data-sw-trigger]; if the
    # counts drift apart, one of them has lost its toggle and is dead markup.
    if html.count('data-sw-trigger') - NAV_SHELL_JS.count('data-sw-trigger') != 2:
        problems.append('nav shell: expected exactly 2 [data-sw-trigger] elements')
    if html.count('class="mod-trigger"') + html.count('mod-trigger" data-sw-trigger') != 1:
        problems.append('nav shell: module dropdown trigger missing')
    return html, problems


IIFE_ANCHOR_RE = re.compile(r"(<script>\s*\n)(\(function\(\)\{\s*\n\s*var stored = sessionStorage)")


def apply_redesign(html):
    """
    Deploy 1 of redesign v6.6: swap the stylesheet and font links, rename the
    three classes the new sheet has no rules for, and bump the footer version.

    Returns (html, problems, renamed) where `renamed` counts the class
    attributes actually rewritten - a rename that finds nothing is not the
    same as one that worked, and the difference matters for events with no
    prior edition, where yoy-badge sits inside {{#HAS_COMPARISON}} and is
    absent entirely.
    """
    problems = []
    if not STYLE_PATH.exists() or not FONT_LINKS_PATH.exists():
        return html, [f"redesign assets missing at {STYLE_PATH.parent}"], {}

    css = STYLE_PATH.read_text(encoding='utf-8')
    # The package's comment header names the old classes it has no rules for
    # (.details-toggle, .yoy-badge, .session-sw). Left in, those strings ship
    # in every dashboard and every "old class is gone" assertion counts them.
    css = re.sub(r'^/\*.*?\*/\s*', '', css, count=1, flags=re.DOTALL)
    html, style_count = STYLE_BLOCK_RE.subn(
        lambda m: '<style>\n' + css + '\n</style>', html, count=1)
    if style_count != 1:
        problems.append(f"stylesheet swap matched {style_count} <style> blocks (want 1)")

    # Drop every generated font link, then insert the package's set once in
    # their place. The old line carries Outfit (dead) and JetBrains Mono
    # (still used), so it is replaced rather than deleted.
    links = FONT_LINKS_PATH.read_text(encoding='utf-8').strip() + '\n'
    seen = []

    def _swap_links(m):
        seen.append(m.group(0))
        return links if len(seen) == 1 else ''

    html, link_count = FONT_LINK_RE.subn(_swap_links, html)
    if link_count == 0:
        problems.append('no font <link> tags found to replace')

    renamed = {}
    for old, new in CLASS_RENAMES:
        pattern = re.compile(r'(class="[^"]*?)\b' + re.escape(old) + r'\b')
        html, n = pattern.subn(lambda m: m.group(1) + new, html)
        # The template's chart loader selects on these classes from JavaScript
        # (canvas.closest('.details-panel')). Renaming only the class attribute
        # would leave those selectors pointing at a class that no longer
        # exists, and the lazy-built charts would silently stop rendering.
        html, js = re.subn(r"(['\"])\." + re.escape(old) + r"\1",
                           lambda m: m.group(1) + '.' + new + m.group(1), html)
        renamed[old] = n
        renamed[old + ' (js selectors)'] = js

    version_count = html.count(VERSION_OLD)
    html = html.replace(VERSION_OLD, VERSION_NEW)
    if version_count != 2:
        problems.append(
            f"footer version literal found {version_count} time(s), expected 2")

    return html, problems, renamed


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

    # Before the nav rewrite, so the swapped-in avatar carries the local src -
    # and so this still applies if the nav pass ever bails.
    logo_count = html.count(LOGO_REMOTE)
    html = html.replace(LOGO_REMOTE, LOGO_LOCAL)

    html, redesign_problems, renamed = apply_redesign(html)
    problems = list(redesign_problems)
    html, auth_problems = add_shared_auth(html)
    problems += auth_problems
    # Runs last: it appends the account avatar as the final child of .nav-top,
    # which is only correct once the upload link above has been removed.
    html, nav_problems = align_nav_shell(html)
    problems += nav_problems

    if 'Mettre à jour' in html:
        problems.append('"Mettre à jour" still present after removing the upload link')
    if FOOTER_OLD in html:
        problems.append(f'"{FOOTER_OLD}" still present after footer replacement')
    if LOGO_REMOTE in html:
        problems.append('the cross-account logo hotlink survived the rewrite')

    path.write_text(html, encoding='utf-8')
    sw_items = html.count('class="sw-item')
    print(f"{path.name}: removed {link_count} upload link(s), "
          f"replaced {footer_count} footer label(s), "
          f"relocalised {logo_count} logo hotlink(s), "
          f"shared auth via {AUTH_KEY}, "
          f"nav shell aligned ({sw_items} session items)")

    if problems:
        for p in problems:
            print(f"  ❌ {p}")
        return False
    if link_count == 0:
        print("  ⚠ no upload link found - template may have changed")
    if footer_count == 0:
        print("  ⚠ no footer label found - template may have changed")
    if logo_count == 0:
        print("  ⚠ no logo hotlink found - template may already point at the local copy")
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
