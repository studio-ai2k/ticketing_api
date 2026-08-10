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

import hashlib
import re
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# The footer markup and its matcher live in stamp_footer, because that script
# has to find them in published HTML long after this one ran. Importing rather
# than duplicating means the two cannot drift - and a drift here would not fail
# the build, it would fail hours later on a quiet run, silently.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import stamp_footer
import suivi_selector

# ============================================================================
# PASS TABLE - read this before adding or reordering a pass
# ============================================================================
#
# Every pass here matches on markup that another pass may have written or
# destroyed. Two bugs in Deploy 1 came from exactly that and neither was
# visible by reading the code:
#
#   - align_nav_shell guarded on the string "sw-wrap", which the redesign
#     stylesheet defines. Every file reported "already aligned" and silently
#     got no nav markup at all.
#   - apply_redesign rewrites font-size:10px inside the nav block that
#     align_nav_shell's session-switcher regex matches on, so that swap
#     stopped applying. The module dropdown landed, the session one did not.
#
# So: state what each pass CONSUMES (matches on) and EMITS (writes), and order
# them so no pass consumes something a later pass emits, or an earlier pass
# has destroyed. Guards must key on markup, never on a class name, because the
# stylesheet contains hundreds of class names.
#
# ---------------------------------------------------------------------------
# SCOPE - the dependency graph is wider than this file
# ---------------------------------------------------------------------------
# Anything that greps generated output is a consumer and belongs in the graph,
# even though it is not a pass and never appears in the table below:
#
#   verify/assert_redesign.sh + verify/check_*.py   assert on generated markup
#   scripts/stamp_footer.py                         REWRITES published markup,
#                                                   out of band, hours later
#
# Deploy 3 §7 broke two of these and neither was a pass. The verify script
# matched on "🎟 Dernier billet vendu" and on the literal "Festiflow Dashboard
# v6.7"; §7 deleted the first and split the second across a <span>, so both
# assertions read 0 on a correct file. stamp_footer.py would have silently
# stopped matching, which fails four hours later rather than at build time.
#
# Before restructuring any generated markup: grep verify/ and scripts/ for the
# strings you are about to destroy. The pass table is necessary, not
# sufficient.
#
# ---------------------------------------------------------------------------
# STANDING RULE - a correct match count does not mean a correct match
# ---------------------------------------------------------------------------
# stamp_footer.STAMP_ITEM_RE once matched exactly twice - the right number -
# while deleting four elements. Its icon body was `.*?` under DOTALL, so a
# match starting at the "Dernier billet" item expanded past that item's own
# </svg>, its label, its value and the separator, and landed on the next
# item's "Données API" label. Six .pgf-item became two.
#
# EVERY count-based assertion in this repo would have passed that. So:
#
#   assert the surrounding structure is UNCHANGED, not merely that your own
#   match count is right.
#
# In practice: dry-run the substitution and compare a count of the elements
# you did NOT intend to touch. postprocess and stamp_footer both do this now,
# and both refuse to write when it moves.
#
# ---------------------------------------------------------------------------
# STANDING RULE - every count says what it counts
# ---------------------------------------------------------------------------
# We have shipped this bug three times, each time by counting a stylesheet
# selector as if it were markup:
#
#   - Deploy 2's spec put the .ac-t baseline at 8. Four of those eight are
#     `.ac-t` selectors inside the CSS. The markup baseline is 4.
#   - Deploy 3's spec put .inset-divider at 3 per file. One of the three is
#     the `.inset-divider` rule. The markup count is 2.
#   - align_nav_shell's original guard tested `'sw-wrap' in html`, matched the
#     stylesheet, and skipped the nav on every single dashboard.
#
# So, without exception:
#
#   1. A markup count keys on `class="name"` (or `class="a name b"` when the
#      element carries several), never on the bare word.
#   2. Every assertion states in its message whether it is over MARKUP or over
#      the WHOLE FILE. "3 .inset-divider" is not a fact; "3 .inset-divider in
#      the whole file, 2 in markup" is.
#   3. A whole-file count is only correct for things the stylesheet cannot
#      contain - emoji, URLs, JS identifiers, colour literals inside
#      `borderColor:`.
#
# When a number in an incoming spec disagrees with generated output, assume the
# spec counted the stylesheet before assuming the generator changed.
#
#  # pass                consumes                        emits
#  - ------------------  ------------------------------  --------------------
#  1 upload link         <a class="nm" href="upload...   (removes it)
#  2 footer label        "Données uploadées" text        "Données API"
#  3 logo relocalise     madameloyal.github.io src       local src
#  4 apply_redesign      <style>, font <link>s,          new class names,
#                        class="...details-toggle...",   var(--fs-*) in
#                        quoted JS selectors, inline     style attrs, v6.6
#                        style="" px + Outfit, "v6"
#  5 add_shared_auth     the auth <script> IIFE          dbAuthGet/dbAuthSet
#  6 align_nav_shell     data-sw-trigger (guard),        session + module
#                        <div class="nav-sw">, the       dropdowns, avatar,
#                        Détails button, </body>         switcher JS
#
# Ordering constraints that actually bind:
#
#   4 before 5 and 6  - it replaces the whole <style> block, so anything
#                       injecting into that block must follow it.
#   4 before 6        - 6's session-switcher regex matches inline font-size
#                       values that 4 rewrites. 6 now matches them loosely,
#                       but the order is still the safer guarantee.
#   6 last            - it appends the account avatar as the final child of
#                       .nav-top, so the upload link (1) must already be gone.
#   1 before 6        - same reason.
#
# Deploy 2 (restructure_projection) is now pass 5, between apply_redesign and
# add_shared_auth:
#
#   consumes: #sec-projection, .proj-grid, .q-card, .chart-tabs, #proj-day{N},
#             #proj-logique, window._projBuilders['day{N}S1'], the Chart.js
#             rgba(96,165,250,.8) literal
#   emits:    .card wrappers, N+1 new .ac-t / .ac-body accordions, immediate
#             chart construction, #60a5fa
#
#   after 4  - required. It emits markup using the .ac-t / .ac-body names that
#              4 renames into existence, and its emitted style="" attributes
#              would otherwise be rewritten by 4's inline-style pass.
#   before 6 - not strictly required (6 touches only the nav), but it keeps
#              the two markup-emitting passes from interleaving, and 6 is the
#              one that must stay last.
#   note     - it emits .ac-t elements, so any count assertion on .ac-t has to
#              run after it. The markup baseline of 4 becomes 4 + N + 1: one
#              per day card, plus one for the methodology card. (The spec said
#              8 + N; 8 counts the four .ac-t selectors inside the stylesheet
#              as well, and it overlooked the methodology accordion.)
#
# Deploy 3 (apply_deploy3) is pass 6, after restructure_projection:
#
#   consumes: the #suivi-hidden-{days,weeks} toggles and containers, the
#             velocity grid anchored on grid-template-columns:1fr 50px 44px
#             44px, the .detail-inset whose label starts "vs ", .det-links
#             and its .det-link anchors
#   emits:    #sep-prev-{days,weeks}, scrollTop in two onclicks,
#             .vel-head / .vel-grid / .v-cur / .v-prev / .v-d,
#             .det-link-txt, <img> logos, smartboard/mio backend hrefs
#
#   after 4  - it emits style="" attributes that 4's inline-style rewriter
#              would otherwise rewrite. Same constraint Deploy 2 has.
#   after 5  - not a data dependency; it keeps the two markup-emitting passes
#              from interleaving, and 5's .ac-t output is part of the baseline
#              6's assertions count.
#   before 8 - the nav pass stays last.
#   scope    - 6 must not touch #sec-projection or .nav-top. Every selector it
#              uses is either an id or lives under #sec-suivi / .det-links.
#
# Deploy 3 §7 (apply_footer) is pass 7, after apply_deploy3:
#
#   consumes: the two generated footer <div>s, and specifically the string
#             "🔄 Données API" that PASS 2 emits - a producer/consumer pair
#             spanning five passes
#   emits:    .pg-footer / .pgf-item / .pgf-k / .pgf-v / .pgf-sep / .pgf-brand,
#             two inline SVG line icons
#
#   after 2  - it consumes pass 2's output. Trivially satisfied, but it is the
#             longest-range coupling in this file and belongs written down.
#   note     - the end-check `if FOOTER_OLD in html` does NOT need to move.
#             FOOTER_OLD is "📤 Données uploadées"; §7 destroys FOOTER_NEW.
#             (An earlier version of this table said otherwise. It was wrong.)
#   note     - "Festiflow Dashboard v6.7" stops being one string here: the
#             version moves into its own .pgf-ver span. Anything asserting the
#             old literal reads 0 on a correct file, including
#             verify/assert_redesign.sh, which was updated with it.
#
# OUT-OF-BAND CONSUMER - scripts/stamp_footer.py patches this same footer in
# published HTML, hours later, on a run where nothing sold. It is not a pass,
# it never sees this file, and a disagreement between the two fails silently:
# the stamp stops moving and the dashboard looks like a dead pipeline, which is
# the exact symptom N4 existed to remove. Two things keep them honest:
#
#   - the markup lives in stamp_footer.build_item(); this file imports it
#     rather than writing its own copy.
#   - postprocess dry-runs stamp_footer.restamp() against its own output and
#     requires two matches AND an unchanged item count. The second half is not
#     redundant: the first STAMP_ITEM_RE matched twice and still deleted a
#     neighbouring item, because a lazy dot let the icon body span an item
#     boundary.
#
# ============================================================================

UPLOAD_LINK_RE = re.compile(
    r'<a class="nm" href="upload\.html[^"]*">.*?Mettre à jour</a>',
    re.DOTALL,
)
FOOTER_OLD = '📤 Données uploadées'
FOOTER_NEW = '🔄 Données API'

# Login overlay subtitle. Middle dot, matching the platform cards
# ("Shotgun · Smartboard"); double-T "Billetterie", matching the nav.
SUBTITLE_OLD = 'Tableau de bord interne'
SUBTITLE_NEW = 'Festiflow · Billetterie'

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
DASHBOARD_VERSION = '6.8'
VERSION_OLD = 'Festiflow Dashboard v6'
VERSION_NEW = f'Festiflow Dashboard v{DASHBOARD_VERSION}'

# Vendored from the redesign package: the exact <style> contents and <link>
# tags of mock/epk_redesign_final.html. Kept as files rather than inlined
# because it is 41 KB, and because bumping the design is then a file swap.
STYLE_PATH = Path(__file__).resolve().parent.parent / 'style' / 'dashboard_v6_8.css'
FONT_LINKS_PATH = Path(__file__).resolve().parent.parent / 'style' / 'font_links.html'

STYLE_BLOCK_RE = re.compile(r'<style>.*?</style>', re.DOTALL)

# The template renders three per-event values INSIDE its <style> block:
# {{LOGIN_BG_IMAGE}}, {{DAY_TAB_ACTIVE_CSS}} and {{PROJ_GRID_COLS}}. Replacing
# that block wholesale throws all three away and substitutes whatever the mock
# was baked with - which is how paris_xxl lost its configured login background
# and silently fell back to epk's.
#
# The other two are dead: Deploy 2 removed .chart-tabs and .proj-grid from the
# markup, so nothing selects the rules they fed. This one is live, so it is
# carried across the swap.
#
# The general rule, which is what actually matters here: a wholesale <style>
# replacement destroys every templated value in it. Before adding a fourth,
# check this list.
OVERLAY_BG_RE = re.compile(r"(\.db-overlay \{[^}]*url\(')([^']*)('\)[^}]*\})")

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / 'dashboard_template.html'

# run.py defaults login_bg_image to this via .get(key, default) - which does
# NOT fire when the key exists and is empty, so clearing the config value in
# event_config.csv renders url('') rather than falling back. Clearing it is the
# documented way to say "use the standard image", so the fallback happens here.
DEFAULT_LOGIN_BG = 'upload.JPG'

# Every {{PLACEHOLDER}} the template renders inside its <style> block, and what
# this pass does about it. A placeholder present upstream but missing here
# fails the build - which is the whole point: a new one added to the template
# would otherwise vanish into the swap and the page would still look right,
# because a hardcoded value renders perfectly well.
STYLE_PLACEHOLDERS = {
    'LOGIN_BG_IMAGE': 'carried',   # re-injected after the swap, see below
    'DAY_TAB_ACTIVE_CSS': 'retired',   # Deploy 2 removed .chart-tabs markup
    'PROJ_GRID_COLS': 'retired',       # Deploy 2 removed .proj-grid markup
}

# Corrections to the vendored sheet that must SURVIVE a future sheet swap, so
# they live here rather than in the .css file. Each must match exactly once.
#
#   .pill          Deploy 1 renamed yoy-badge -> pill without checking what
#                  .pill already meant: the BudgetFlow nav badge. Two unrelated
#                  components ended up sharing a class, and the nav rule's
#                  margin-left:auto landed on the YoY badge. The nav keeps the
#                  name (it comes from the nav spec); the YoY family moves.
#   .scenario-btn  the later rule never set font-weight, so the earlier rule's
#                  600 applied to every button and .active's own font-weight:600
#                  was a measured no-op. Lighten the idle state instead of
#                  dropping the active one, so the weight difference does the
#                  work it was meant to.
CSS_FIXUPS = (
    ('.pill { display: inline-block;', '.yoy-pill { display: inline-block;'),
    ('.pill.positive {', '.yoy-pill.positive {'),
    ('.pill.green {', '.yoy-pill.green {'),
    ('.pill.red {', '.yoy-pill.red {'),
    ('.scenario-btn { flex: 1; padding: 7px 10px;',
     '.scenario-btn { flex: 1; font-weight: 500; padding: 7px 10px;'),
)
FONT_LINK_RE = re.compile(r'[ \t]*<link[^>]*fonts\.(?:googleapis|gstatic)\.com[^>]*>\n?')

# Attribute-scoped so a rename cannot hit the same word inside JS or text.
# The template hard-codes a few sizes and a dead font in style="..."
# attributes, which no stylesheet swap can reach. They are the same sub-14px
# declarations the scale was extended for, and left as literals they sit out
# the 720px rescale - the very thing being fixed on mobile.
#
# The overlay button is held at --fs-caption rather than --fs-micro: micro
# drops to 11px at 720px, which is under the size a primary call to action
# should be on a phone. Caption gives 16px/12px instead. That is 2px larger
# than today on desktop, on one full-width button.
INLINE_STYLE_FIXES = (
    ("font-size:10px", "font-size:var(--fs-nano)"),
    ("font-size:14px", "font-size:var(--fs-caption)"),
    ("'Outfit',sans-serif", "'DM Sans',sans-serif"),
    ("'Outfit',system-ui", "'DM Sans',system-ui"),
)

CLASS_RENAMES = (
    ('details-toggle', 'ac-t'),
    ('details-panel', 'ac-body'),
    ('yoy-badge', 'yoy-pill'),
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
    # The gate is a fixed full-screen overlay over a document that still
    # scrolls, so the dashboard slid past behind it. Nothing in the template
    # ever locked scroll - not a v2 regression, a defect in both heads, fixed
    # in the one place that feeds both.
    #
    # Driven off the ELEMENT rather than off the two code paths that hide it:
    # the load check and the correct-password branch both work, and so does
    # any third path added later, because the observer watches the thing whose
    # state actually decides the answer.
    "(function(){\n"
    "  var o = document.getElementById('db-overlay'); if(!o) return;\n"
    "  var sync = function(){\n"
    "    var up = o.style.display !== 'none';\n"
    "    document.documentElement.style.overflow = up ? 'hidden' : '';\n"
    "    if (document.body) document.body.style.overflow = up ? 'hidden' : '';\n"
    "  };\n"
    "  sync();\n"
    "  try{ new MutationObserver(sync).observe(o,{attributes:true,"
    "attributeFilter:['style']}); }catch(e){}\n"
    "})();\n"
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
    r'<span style="font-size:[^;]+;font-weight:600;color:#fff">(?P<name>.*?)</span>'
    r'<span style="[^"]*background:var\((?P<dot>--[a-z0-9-]+)\)[^"]*"></span></div>\s*'
    # font-size is matched loosely: the inline-style pass rewrites literal px
    # values to tokens before this runs, and pinning 10px here made the whole
    # switcher swap stop matching silently.
    r'<div style="font-size:[^;]+;color:var\(--text-dim\);margin-top:3px">(?P<sub>.*?)</div>\s*'
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
    # Markup-only form. The stylesheet defines .mod-trigger, so any check
    # keying on the bare class name would match CSS as well as markup - the
    # exact way the sw-wrap guard broke.
    if html.count('mod-trigger" data-sw-trigger') != 1:
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

    # Captured before the swap, restored after it.
    original_style = STYLE_BLOCK_RE.search(html)
    templated_bg = None
    if original_style:
        m = OVERLAY_BG_RE.search(original_style.group(0))
        if m:
            templated_bg = m.group(2)

    css = STYLE_PATH.read_text(encoding='utf-8')
    for old, new in CSS_FIXUPS:
        if css.count(old) != 1:
            problems.append(
                f'css fixup: {old!r} matched {css.count(old)} time(s), want 1 - '
                f'the vendored sheet changed shape')
        css = css.replace(old, new, 1)
    # The package's comment header names the old classes it has no rules for
    # (.details-toggle, .yoy-badge, .session-sw). Left in, those strings ship
    # in every dashboard and every "old class is gone" assertion counts them.
    css = re.sub(r'^/\*.*?\*/\s*', '', css, count=1, flags=re.DOTALL)
    html, style_count = STYLE_BLOCK_RE.subn(
        lambda m: '<style>\n' + css + '\n</style>', html, count=1)
    if style_count != 1:
        problems.append(f"stylesheet swap matched {style_count} <style> blocks (want 1)")

    if templated_bg is None:
        problems.append(
            'login background: no .db-overlay url() in the template <style> - '
            'the rule the swap has to restore has moved or gone')
    else:
        wanted = templated_bg or DEFAULT_LOGIN_BG
        html, bg_count = OVERLAY_BG_RE.subn(
            lambda m: m.group(1) + wanted + m.group(3), html, count=1)
        if bg_count != 1:
            problems.append(
                'login background: could not restore the per-event image after '
                'the stylesheet swap')

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

    # Only inside style="..." attributes - the stylesheet itself is already
    # tokenised, and the same strings elsewhere are not ours to touch.
    inline = 0

    def _fix_inline(m):
        nonlocal inline
        chunk = m.group(0)
        for old, new in INLINE_STYLE_FIXES:
            if old in chunk:
                chunk = chunk.replace(old, new)
                inline += 1
        return chunk

    html = re.sub(r'style="[^"]*"', _fix_inline, html)
    # Chart.js sets its default font in script, outside any style attribute.
    html = html.replace('Chart.defaults.font.family="\'Outfit\',system-ui"',
                        'Chart.defaults.font.family="\'DM Sans\',system-ui"')

    # V1: the template's <style> is not static - it carries per-event
    # placeholders, and replacing the block wholesale discards them silently.
    problems += _assert_style_placeholders(html)

    version_count = html.count(VERSION_OLD)
    html = html.replace(VERSION_OLD, VERSION_NEW)
    if version_count != 2:
        problems.append(
            f"footer version literal found {version_count} time(s), expected 2")

    return html, problems, renamed


# --------------------------------------------- redesign v6.6, deploy 2 --
# The projection block goes from "grid of day cards + a row of tabs switching
# between hidden chart panels" to "one self-contained card per day, each with
# its own Détails accordion", plus the methodology as a final card.
#
# Everything here is move-and-wrap. The .q-card and .q-chart-wrap contents are
# carried across byte-for-byte; nothing inside them is rewritten.

DIV_TAG_RE = re.compile(r'<div\b[^>]*>|</div>')

# Replaces the per-panel "<day name> - Courbe cumulative (% capacité)"
# subtitle. The day name is already the q-card's own header, and inside the
# card it would be said twice.
DAY_SUBTITLE = (
    '<div style="font-size:var(--fs-caption);color:var(--text-muted);'
    'margin-bottom:10px;font-weight:500">Courbe cumulative · % capacité</div>'
)

DAY_ACCORDION_HEAD = (
    '<div class="ac-t" onclick="toggleDetails(this)">'
    '<span>Détails</span><span class="arrow">▼</span></div>'
)

# --- the projection chart palette ---------------------------------------
# The mock's palette, ruled in by Leo: sales line white, projection solid
# blue, the prior-year reference unchanged (red dashed).
#
# #fbbf24 is NOT safe to replace globally. It also drives the day tag text
# colours, the hebdo bar chart, and the velocity and revenue charts - twelve
# occurrences outside the projection block on a two-day event. So both halves
# of this are doubly scoped: the markup swap runs only inside #sec-projection,
# and the dataset swaps run only inside the brace-matched config of a
# chartDay{N}S{1,2} chart, keyed on `borderColor:` rather than on the bare
# colour string.
SALES_LINE_OLD, SALES_LINE_NEW = '#fbbf24', '#ffffff'
PROJ_LINE_OLD, PROJ_LINE_NEW = 'rgba(251,191,36,.8)', '#60a5fa'

# rgba(96,165,250,.8) is the mock's own pre-recolour projection literal. This
# generator has never emitted it, so this entry is a no-op today; it is kept
# and counted so a future palette move cannot regress silently.
MOCK_PROJ_LINE_OLD = 'rgba(96,165,250,.8)'

CHART_DATASET_RECOLOUR = (
    (f"borderColor:'{SALES_LINE_OLD}'", f"borderColor:'{SALES_LINE_NEW}'"),
    (f"borderColor:'{PROJ_LINE_OLD}'", f"borderColor:'{PROJ_LINE_NEW}'"),
    (f"borderColor:'{MOCK_PROJ_LINE_OLD}'", f"borderColor:'{PROJ_LINE_NEW}'"),
)

# The swatches carry the same two colours in two different CSS properties -
# the sales key is a filled block, the projection key a dashed outline.
LEGEND_RECOLOUR = (
    (f'<div class="legend-swatch" style="background:{SALES_LINE_OLD}">',
     f'<div class="legend-swatch" style="background:{SALES_LINE_NEW}">'),
    (f'<div class="legend-swatch dashed" style="border-color:{SALES_LINE_OLD}">',
     f'<div class="legend-swatch dashed" style="border-color:{PROJ_LINE_NEW}">'),
)


def _match_div(html, start):
    """
    html[start] opens a <div. Return (start, end) of its matching </div>.
    Returns (-1, -1) if the document runs out first.

    Safe on these files because no <div appears inside a JS or CSS string -
    postprocess asserts that before calling anything that relies on it.
    """
    depth = 0
    for m in DIV_TAG_RE.finditer(html, start):
        if m.group(0)[1] == '/':
            depth -= 1
            if depth == 0:
                return m.start(), m.end()
        else:
            depth += 1
    return -1, -1


def _div_inner(html, start):
    """Contents of the <div at `start`, plus the index just past its </div>."""
    close_start, close_end = _match_div(html, start)
    if close_start < 0:
        return None, -1
    return html[html.index('>', start) + 1:close_start], close_end


def _js_match_brace(js, open_idx):
    """
    Index of the '}' matching js[open_idx] == '{', skipping quoted strings.
    Chart configs contain no regex literals, comments or template literals, so
    quote-awareness is enough. Returns -1 if unbalanced.
    """
    depth = 0
    quote = None
    i = open_idx
    while i < len(js):
        c = js[i]
        if quote:
            if c == '\\':
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in '\'"':
            quote = c
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _div_ancestor_classes(html, pos):
    """
    class attributes of every open <div> enclosing `pos`, outermost first.
    Used to prove the lazy chart loaders' canvas.closest('.ac-body') still
    resolves after the restructure - a broken closest() throws nothing and
    logs nothing, the chart just never draws.
    """
    stack = []
    for m in DIV_TAG_RE.finditer(html, 0):
        if m.start() >= pos:
            break
        if m.group(0)[1] == '/':
            if stack:
                stack.pop()
        else:
            cls = re.search(r'class="([^"]*)"', m.group(0))
            stack.append(cls.group(1) if cls else '')
    return stack


def _chart_config_span(html, canvas_id):
    """(start, end) of the Chart.js config object built onto `canvas_id`."""
    at = html.find(f"getElementById('{canvas_id}')")
    if at < 0:
        return None
    brace = html.find(',{', at)
    if brace < 0:
        return None
    close = _js_match_brace(html, brace + 1)
    if close < 0:
        return None
    return brace + 1, close + 1


def _recolour_projection(html, section_start, section_end, n):
    """
    Apply the mock's chart palette. Returns (html, counts, problems).

    Scoped twice over, because #fbbf24 is load-bearing elsewhere: the swatches
    only inside #sec-projection, the datasets only inside a chartDay* config.
    """
    counts = {'legend': 0, 'dataset': 0}
    problems = []

    section = html[section_start:section_end]
    for old, new in LEGEND_RECOLOUR:
        counts['legend'] += section.count(old)
        section = section.replace(old, new)
    html = html[:section_start] + section + html[section_end:]

    # Every S1 and S2 config, taken one at a time so a rename in one cannot
    # bleed into another chart's extent.
    for i in range(n):
        for scenario in ('S1', 'S2'):
            canvas = f'chartDay{i}{scenario}'
            span = _chart_config_span(html, canvas)
            if span is None:
                problems.append(f'projection: no Chart config found for {canvas}')
                continue
            start, end = span
            cfg = html[start:end]
            for old, new in CHART_DATASET_RECOLOUR:
                counts['dataset'] += cfg.count(old)
                cfg = cfg.replace(old, new)
            html = html[:start] + cfg + html[end:]
    return html, counts, problems


def restructure_projection(html):
    """
    Deploy 2 of redesign v6.6. Returns (html, problems, stats).

    Every anchor is looked up rather than assumed, and a missing one skips its
    own rewrite and records a problem instead of half-applying: a partial
    projection block is worse than an untouched one.
    """
    problems = []
    stats = {}

    open_re = re.compile(r'<div id="sec-projection"[^>]*>\s*<div class="card">')
    m = open_re.search(html)
    if not m:
        return html, ['projection: #sec-projection > .card opener not found'], stats
    sec_start = m.start()
    sec_close_start, sec_close_end = _match_div(html, sec_start)
    if sec_close_start < 0:
        return html, ['projection: #sec-projection is unbalanced'], stats

    card_start = html.index('<div class="card">', sec_start)
    body, _ = _div_inner(html, card_start)
    if body is None:
        return html, ['projection: the section .card is unbalanced'], stats

    title_m = re.search(r'<div class="section-title">.*?</div>', body, re.DOTALL)
    if not title_m:
        problems.append('projection: .section-title not found')
        return html, problems, stats
    title = title_m.group(0)

    # --- the day cards, in document order -------------------------------
    grid_at = body.find('<div class="proj-grid">')
    if grid_at < 0:
        problems.append('projection: .proj-grid not found')
        return html, problems, stats
    grid_inner, _ = _div_inner(body, grid_at)
    q_cards = []
    pos = 0
    while True:
        at = grid_inner.find('<div class="q-card">', pos)
        if at < 0:
            break
        close_start, close_end = _match_div(grid_inner, at)
        if close_start < 0:
            problems.append('projection: a .q-card is unbalanced')
            return html, problems, stats
        q_cards.append(grid_inner[at:close_end])
        pos = close_end

    # --- the two independent day counts, which must agree ----------------
    canvas_days = sorted(int(d) for d in
                         re.findall(r'canvas id="chartDay(\d+)S1"', html))
    n = len(q_cards)
    if canvas_days != list(range(n)):
        problems.append(
            f'projection: {n} .q-card(s) but chartDay*S1 canvases are '
            f'{canvas_days} - refusing to restructure')
        return html, problems, stats
    stats['days'] = n

    # --- each day's chart panel -----------------------------------------
    panels = []
    for i in range(n):
        at = body.find(f'<div id="proj-day{i}"')
        if at < 0:
            problems.append(f'projection: #proj-day{i} not found')
            return html, problems, stats
        inner, _ = _div_inner(body, at)
        if inner is None:
            problems.append(f'projection: #proj-day{i} is unbalanced')
            return html, problems, stats
        # Drop the panel's own subtitle; DAY_SUBTITLE replaces it. Everything
        # else moves across untouched, which keeps this working for the
        # {{#HAS_COMPARISON}}-absent branch too, where there are no
        # .q-chart-wrap elements at all - just a bare .chart-canvas-wrap.
        inner = inner.lstrip()
        if inner.startswith('<div class="chart-subtitle">'):
            _, after = _div_inner(inner, 0)
            inner = inner[after:]
        else:
            problems.append(f'projection: #proj-day{i} has no .chart-subtitle')
        panels.append(inner.strip())

    # --- the methodology block ------------------------------------------
    logique_at = body.find('<div id="proj-logique"')
    if logique_at < 0:
        problems.append('projection: #proj-logique not found')
        return html, problems, stats
    logique_inner, _ = _div_inner(body, logique_at)

    tabs_at = body.find('<div class="chart-tabs">')
    if tabs_at < 0:
        problems.append('projection: .chart-tabs not found')
        return html, problems, stats

    # --- rebuild ---------------------------------------------------------
    out = [f'<div id="sec-projection" class="section-gap">', title]
    for i in range(n):
        out.append(
            '<div class="card" style="margin-bottom:20px">\n'
            + q_cards[i] + '\n'
            + '<div class="divider" style="margin:16px 0 0"></div>\n'
            + DAY_ACCORDION_HEAD + '\n'
            + '<div class="ac-body"><div class="ac-inner">\n'
            + DAY_SUBTITLE + '\n'
            + panels[i] + '\n'
            + '</div></div></div>'
        )
    out.append(
        '<div class="card">\n'
        '<div class="ac-t" onclick="toggleDetails(this)" style="cursor:pointer">\n'
        '  <span style="font-size:var(--fs-caption);font-weight:600;'
        'color:var(--text-muted)">Logique de projection</span>\n'
        '  <span class="arrow">▼</span>\n'
        '</div>\n'
        '<div class="ac-body">\n'
        '  <div class="ac-inner" style="padding-top:12px">\n'
        f'    {logique_inner.strip()}\n'
        '  </div>\n'
        '</div>\n'
        '</div>'
    )
    out.append('</div>')
    html = html[:sec_start] + '\n'.join(out) + html[sec_close_end:]

    # --- JS: the tabs are gone, so nothing will trigger the lazy builds --
    built = []
    for i in range(1, n):
        prefix = f"window._projBuilders['day{i}S1'] = function(){{"
        at = html.find(prefix)
        if at < 0:
            problems.append(f"projection: no lazy builder for day{i}S1")
            continue
        open_brace = at + len(prefix) - 1
        close_brace = _js_match_brace(html, open_brace)
        if close_brace < 0 or html[close_brace + 1] != ';':
            problems.append(f"projection: could not delimit the day{i}S1 builder")
            continue
        html = (html[:at]
                + f'// Day {i} - built immediately (was lazy)\n(function(){{'
                + html[open_brace + 1:close_brace]
                + '})();'
                + html[close_brace + 2:])
        built.append(i)
    stats['built_immediately'] = [0] + built

    # day{N}S2 stays lazy on purpose: its .q-chart-wrap is display:none until
    # switchScenario reveals it, and a Chart built into a display:none parent
    # measures 0x0 and never recovers.

    # The section boundaries have to be re-found: the rebuild above moved them.
    new_start = html.index('<div id="sec-projection"')
    new_close, new_end = _match_div(html, new_start)
    html, counts, colour_problems = _recolour_projection(
        html, new_start, new_end, n)
    problems += colour_problems
    stats['recoloured'] = counts
    return html, problems, stats


# ---------------------------------------------- redesign v6.7, deploy 3 --
# Four unrelated fixes that share one property: each rewrites markup the
# generator emits, and none of them can be done in CSS alone.

SUIVI_GRAINS = (('days', 'suivi-hidden-days', 'sep-prev-days'),
                ('weeks', 'suivi-hidden-weeks', 'sep-prev-weeks'))

# Mirrors the generated "À venir" divider byte for byte, so it needs no CSS of
# its own. display:flex, not block - .dtl-cutoff is a flex row and `block`
# collapses the two hairlines onto the label.
SEP_TEMPLATE = (
    '<div class="dtl-cutoff" id="{sep}" style="display:none">'
    '<div class="dtl-cutoff-line"></div>'
    '<div class="dtl-cutoff-label">Précédent</div>'
    '<div class="dtl-cutoff-line"></div></div>'
)

VEL_GRID_ANCHOR = 'grid-template-columns:1fr 50px 44px 44px'

# The generator writes each velocity cell as an inline style. The stylesheet
# now has classes for all four, so the styles come off and the classes go on.
VEL_CELL_CLASSES = {
    'color:#fff;font-weight:500;text-align:right': 'v-cur',
    'color:rgba(255,255,255,0.55);text-align:right': 'v-prev',
    'color:var(--red);font-weight:500;text-align:right': 'v-d neg',
    'color:var(--green);font-weight:500;text-align:right': 'v-d pos',
}

# The four .det-link names are static template literals, which is why they are
# safe to classify on. The icon text is not: both public links render "www".
PLATFORM_CARDS = (
    ('Shotgun Dashboard', 'Shotgun · Smartboard', 'shotgun'),
    ('Page publique Shotgun', 'Shotgun · Page publique', 'shotgun'),
    ('DICE Dashboard', 'DICE · Mio', 'dice'),
    ('Page publique DICE', 'DICE · Page publique', 'dice'),
)
PLATFORM_LOGOS = {'shotgun': 'logo-shotgun.png', 'dice': 'logo-dice.png'}
PLATFORM_FALLBACK = {'shotgun': 'SG', 'dice': 'DICE'}

# Both backend links point somewhere wrong in generated output. run.py has no
# Shotgun dashboard URL at all, so that card falls back to shotgun_url - the
# public festival page - and the two Shotgun cards become the same destination.
# The DICE one is built as dice.fm/partner/events/{id}, but the backoffice in
# use is Mio, on another host. Renaming the cards without fixing the hrefs
# would turn a vague label into a specific false one.
SMARTBOARD_URL = 'https://smartboard.shotgun.live/events/{id}'
MIO_URL = 'https://mio.dice.fm/events/{relay}/overview'
DICE_DASHBOARD_PREFIX = 'https://dice.fm/partner/events/'


def _dice_relay_id(numeric_id):
    """
    DICE's GraphQL global id: base64 of the literal "Event:<id>".
    Generated, never tabulated - the same encoding fetch_csv.py uses.
    """
    import base64
    return base64.b64encode(f'Event:{numeric_id}'.encode()).decode()


def _suivi_toggles_and_separators(html):
    """
    §3 + §4. Expanding the past list lands on the oldest date, ~230 days back,
    and the past block has no closing boundary.

    Both are fixed in the same place: the toggle is an inline onclick, and the
    separator it drives has to be inserted immediately after the container's
    own </div> - it closes the past block rather than announcing it.
    """
    problems, made = [], []
    for label, container, sep in SUIVI_GRAINS:
        at = html.find(f'<div id="{container}"')
        if at < 0:
            problems.append(f'suivi: #{container} not found')
            continue

        # ~230 nested rows, so the close has to be found by depth, not search.
        close_start, close_end = _match_div(html, at)
        if close_start < 0:
            problems.append(f'suivi: #{container} is unbalanced')
            continue
        html = html[:close_end] + '\n' + SEP_TEMPLATE.format(sep=sep) + html[close_end:]

        # The toggle sits before the container, so the insert above did not
        # move it - but re-find it anyway rather than cache an index.
        m = re.search(r'onclick="([^"]*getElementById\(\'' + re.escape(container)
                      + r'\'\)[^"]*)"', html)
        if not m:
            problems.append(f'suivi: no toggle found for #{container}')
            continue
        js = m.group(1)
        # `h.style.display==='none'` has three = signs, so neither replacement
        # can match the condition it sits next to.
        show = ("h.style.display='block';h.scrollTop=h.scrollHeight;"
                f"var sp=document.getElementById('{sep}');if(sp)sp.style.display='flex';")
        hide = ("h.style.display='none';"
                f"var sp=document.getElementById('{sep}');if(sp)sp.style.display='none';")
        if js.count("h.style.display='block';") != 1 or js.count("h.style.display='none';") != 1:
            problems.append(f'suivi: unexpected toggle body for #{container}')
            continue
        new_js = (js.replace("h.style.display='block';", show, 1)
                    .replace("h.style.display='none';", hide, 1))
        html = html[:m.start(1)] + new_js + html[m.end(1):]
        made.append(label)
    return html, problems, made


def _velocity_table(html):
    """
    §5. The four column labels live inside the data grid, under a .divider, so
    they read as part of the block above them. Répartition puts its labels
    above their own border-bottom; this makes Vélocité match.
    """
    problems = []
    at = html.find(VEL_GRID_ANCHOR)
    if at < 0:
        return html, ['velocity: the 1fr 50px 44px 44px grid was not found'], 0
    if html.count(VEL_GRID_ANCHOR) != 1:
        return html, [f'velocity: grid anchor found {html.count(VEL_GRID_ANCHOR)} times, want 1'], 0

    start = html.rindex('<div', 0, at)
    inner, end = _div_inner(html, start)
    if inner is None:
        return html, ['velocity: the grid div is unbalanced'], 0

    spans = re.findall(r'<span[^>]*>.*?</span>', inner, re.DOTALL)
    if len(spans) < 8 or len(spans) % 4:
        return html, [f'velocity: {len(spans)} span(s), not a multiple of 4'], 0

    # First four are the header labels - and the second is the dynamic
    # comparison year, so they are taken by position, never by text.
    head = ''.join('<span>' + re.sub(r'^<span[^>]*>|</span>$', '', s) + '</span>'
                   for s in spans[:4])

    body = []
    for s in spans[4:]:
        m = re.match(r'<span style="([^"]*)">(.*)</span>$', s, re.DOTALL)
        if m and m.group(1) in VEL_CELL_CLASSES:
            body.append(f'<span class="{VEL_CELL_CLASSES[m.group(1)]}">{m.group(2)}</span>')
        elif 'class="meta-key"' in s:
            body.append(s)
        else:
            problems.append(f'velocity: unrecognised cell {s[:70]}')
            body.append(s)

    rows = len(spans) // 4 - 1
    new = (f'<div class="vel-head">{head}</div>\n'
           f'    <div class="vel-grid">\n        ' + ''.join(body) + '\n    </div>')
    html = html[:start] + new + html[end:]

    # The .divider above it is now redundant - .vel-head carries its own
    # border-bottom. Only the one immediately before the block, never a global
    # replace: .divider appears throughout, including in Deploy 2's day cards.
    before = html[:start]
    tail = re.search(r'<div class="divider"></div>\s*$', before)
    if tail:
        html = html[:tail.start()] + html[start:]
    else:
        problems.append('velocity: no .divider immediately above the grid')
    return html, problems, rows


def _drop_trailing_inset_divider(html):
    """
    §6b. The `vs {year} (même J-{n})` inset ends with a rule under its last
    row and nothing below it.

    Scoped to that one inset - the other .inset-divider in the file is
    legitimate - and only to the divider that is its last element. The year
    and J-number are dynamic, so the label is matched on the "vs " prefix.
    """
    for m in re.finditer(r'<div class="detail-inset">', html):
        label = re.search(r'class="inset-label">([^<]*)', html[m.start():m.start() + 300])
        if not label or not label.group(1).startswith('vs '):
            continue
        close_start, close_end = _match_div(html, m.start())
        if close_start < 0:
            return html, ['inset: the vs-inset is unbalanced'], 0
        block = html[m.start():close_start]
        trailing = re.search(r'\s*<div class="inset-divider"></div>\s*$', block)
        if not trailing:
            return html, ['inset: the vs-inset has no trailing .inset-divider'], 0
        cut = m.start() + trailing.start()
        return html[:cut] + '\n        ' + html[m.start() + trailing.end():], [], 1
    return html, ['inset: no .detail-inset labelled "vs ..." found'], 0


def _platform_cards(html):
    """
    §8 + the A-series amendment. Reorder, rename, fix both backend hrefs, wrap
    the text column so CSS can truncate it, and put the platform logo in the
    icon slot.

    Any of the four cards can be absent - 2, 3 and 4 are all live shapes - so
    everything here iterates over what exists. Nothing is synthesised that
    run.py did not emit.
    """
    problems = []
    at = html.find('<div class="det-links">')
    if at < 0:
        return html, ['platform: .det-links not found'], {}
    inner, end = _div_inner(html, at)
    if inner is None:
        return html, ['platform: .det-links is unbalanced'], {}

    found = {}
    for m in re.finditer(r'<a class="det-link" href="([^"]*)"[^>]*>(.*?)</a>', inner, re.DOTALL):
        name = re.search(r'class="det-link-name">([^<]*)</div>', m.group(2))
        url = re.search(r'class="det-link-url">([^<]*)</div>', m.group(2))
        if not name or not url:
            problems.append('platform: a .det-link has no name/url pair')
            continue
        found[name.group(1)] = {'href': m.group(1), 'sub': url.group(1)}

    unknown = set(found) - {old for old, _, _ in PLATFORM_CARDS}
    if unknown:
        problems.append(f'platform: unrecognised card name(s) {sorted(unknown)}')

    cards, stats = [], {'cards': 0, 'smartboard': 0, 'mio': 0}
    for old_name, new_name, platform in PLATFORM_CARDS:
        card = found.get(old_name)
        if not card:
            continue
        href, sub = card['href'], card['sub']

        if old_name.endswith('Dashboard'):
            # The event id is already in the subtext this rewrite replaces, so
            # it is read from there rather than from config - postprocess is
            # handed a file path, not an event, and stays config-free.
            eid = re.search(r'→\s*(\d+)', sub)
            if not eid:
                problems.append(f'platform: no event id in "{sub}"')
                continue
            eid = eid.group(1)
            if platform == 'shotgun':
                href = SMARTBOARD_URL.format(id=eid)
                stats['smartboard'] += 1
            else:
                # Two-direction check: the id parsed out of the display text
                # must be the one run.py built the old href from.
                in_href = re.search(re.escape(DICE_DASHBOARD_PREFIX) + r'(\d+)', href)
                if not in_href or in_href.group(1) != eid:
                    problems.append(
                        f'platform: DICE id disagrees - subtext {eid}, href {href}')
                href = MIO_URL.format(relay=_dice_relay_id(eid))
                stats['mio'] += 1
            sub = f'Event ID : {eid}'
        else:
            # The generator hard-truncates the public URL in the markup, so it
            # clips at the same character at any width. Give CSS the whole
            # string and let it ellipsise.
            sub = re.sub(r'^https?://', '', href)

        logo = PLATFORM_LOGOS[platform]
        cards.append(
            f'<a class="det-link" href="{href}" target="_blank">'
            f'<div class="det-link-icon" style="background:#000">'
            f'<img src="{logo}" alt="" onerror="this.remove()">'
            f'<span>{PLATFORM_FALLBACK[platform]}</span></div>'
            f'<div class="det-link-txt">'
            f'<div class="det-link-name">{new_name}</div>'
            f'<div class="det-link-url">{sub}</div></div></a>'
        )
        stats['cards'] += 1

    if stats['cards'] != len(found):
        problems.append(
            f'platform: rebuilt {stats["cards"]} card(s) from {len(found)} found')
    body = '\n        ' + '\n        '.join(cards) + '\n    '
    html = html[:at] + '<div class="det-links">' + body + '</div>' + html[end:]
    return html, problems, stats


def apply_deploy3(html):
    """Deploy 3 markup pass (3b). Returns (html, problems, stats)."""
    problems, stats = [], {}
    html, p, grains = _suivi_toggles_and_separators(html)
    problems += p
    stats['separators'] = grains
    html, p, rows = _velocity_table(html)
    problems += p
    stats['velocity_rows'] = rows
    html, p, dropped = _drop_trailing_inset_divider(html)
    problems += p
    stats['inset_dividers_dropped'] = dropped
    html, p, cards = _platform_cards(html)
    problems += p
    stats['platform'] = cards
    return html, problems, stats


# ------------------------------------------ redesign v6.7, deploy 3 §7 --
# The two footer emoji are full-colour raster glyphs: they render differently
# per OS and sit off the text baseline, next to a nav built from inline line
# icons. And the run-on "&nbsp;·&nbsp;" string reads as prose where it is
# three separate facts.
#
# Verbatim from mock/epk_redesign_final.html. 24 viewBox, currentColor, no
# fill, so they inherit --text-dim like the nav icons do.
PGF_ICON_TICKET = (
    '<svg class="pgf-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M3 8.5A1.5 1.5 0 0 1 4.5 7h15A1.5 1.5 0 0 1 21 8.5v1.7a1.8 1.8 0 0 0 0 '
    '3.6v1.7a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 15.5v-1.7a1.8 1.8 0 0 0 0-3.6z"/>'
    '<path d="M9.6 7v10" stroke-dasharray="1.8 2.2"/></svg>'
)

# The old footer, both occurrences: one bare <div style="...">, one
# .det-footer. Everything between the separators is dynamic, so the values are
# lifted out and re-emitted rather than reconstructed.
OLD_FOOTER_RE = re.compile(
    r'<div (class="det-footer"|style="text-align:center[^"]*")>'
    r'🎟 Dernier billet vendu · (.*?)\s*&nbsp;·&nbsp;\s*'
    r'🔄 Données API · (.*?)\s*&nbsp;·&nbsp;\s*'
    r'Festiflow Dashboard (v[\d.]+)</div>'
)


PARIS = ZoneInfo('Europe/Paris')
UTC = ZoneInfo('UTC')

# run.py:2048 renders the last ticket as last_ticket_dt.strftime('%d/%m · %H:%M')
# straight off order_datetime, with no conversion. order_datetime is UTC - proved
# from the DST offset across four campaigns in two seasons, all four on-sales at
# 19:00 Paris:
#
#   paris_xxl_2026  stored 17:59  Dec  CET  +1  ->  18:59
#   paris_xxl_2025  stored 18:01  Dec  CET  +1  ->  19:01
#   epk_2026        stored 17:00  Apr  CEST +2  ->  19:00
#   rennes_2026     stored 17:00  Jun  CEST +2  ->  19:00
#
# The stored values differ only by the seasonal offset, which no other
# explanation produces. So the published footer time is 1h slow in winter and 2h
# in summer - and being wrong by a DIFFERENT amount per season is why it never
# looked absurd enough to notice.
#
# run.py is do-not-modify, but §7 already lifts this value out and re-emits it,
# so the conversion goes here, on the way through.
LAST_TICKET_RE = re.compile(r'^\s*(\d{2})/(\d{2})\s*·\s*(\d{2}):(\d{2})\s*$')


def _to_paris(sold, today=None):
    """
    'DD/MM · HH:MM' in UTC -> the same format in Europe/Paris.

    Returns the input unchanged if it does not parse - a footer with an
    unexpected shape is the template having moved, which apply_footer's own
    count assertion reports; silently mangling it here would be worse.

    The string carries no year, and the year decides the offset, so it is
    inferred: the most recent year in which that DD/MM has already happened.
    Every last-ticket timestamp is by definition at or before the build, and the
    dashboards are rebuilt daily, so the candidate is this year or last.
    ZoneInfo does the offset, so the CET/CEST switch is real DST, not +1 or +2
    picked by hand.
    """
    m = LAST_TICKET_RE.match(sold or '')
    if not m:
        return sold
    dd, mm, hh, mi = (int(g) for g in m.groups())
    today = today or datetime.now(PARIS).date()
    for year in (today.year, today.year - 1):
        try:
            naive = datetime(year, mm, dd, hh, mi)
        except ValueError:
            continue  # 29/02 in a non-leap year
        # The value being compared is UTC and `today` is Paris, which is the
        # safe direction: Paris is ahead, so a UTC timestamp is never in the
        # future against a Paris date. Only the leap-year skip can fall through.
        if naive.date() <= today:
            return naive.replace(tzinfo=UTC).astimezone(PARIS).strftime('%d/%m · %H:%M')
    return sold


def apply_footer(html):
    """
    Deploy 3 §7. Returns (html, problems, count).

    Ships separately from the rest of Deploy 3 because it is the only change
    here that touches a runtime contract: scripts/stamp_footer.py patches this
    same markup in published HTML, out of band, hours later. A mismatch fails
    silently on a quiet run and looks exactly like the stale-stamp problem N4
    existed to remove - so postprocess asserts stamp-compatibility at build
    time, using the stamper's own matcher rather than a copy of it.
    """
    problems = []

    def _rebuild(m):
        holder, sold, checked, version = m.groups()
        sold = _to_paris(sold)
        cls = 'pg-footer det-footer' if 'det-footer' in holder else 'pg-footer'
        return (
            f'<div class="{cls}">'
            f'<span class="pgf-item">{PGF_ICON_TICKET}'
            f'<span class="pgf-k">Dernier billet</span>'
            f'<span class="pgf-v">{sold}</span></span>'
            f'<span class="pgf-sep"></span>'
            f'{stamp_footer.build_item(stamp_footer.CHECK_LABEL, checked)}'
            f'<span class="pgf-sep"></span>'
            f'<span class="pgf-item pgf-brand">Festiflow Dashboard'
            f'<span class="pgf-ver">{version}</span></span></div>'
        )

    html, n = OLD_FOOTER_RE.subn(_rebuild, html)
    # One page's footer restructured and the other's left behind is worse than
    # neither: the two would disagree, and the stamper would only patch one.
    if n != 2:
        problems.append(
            f'footer: rebuilt {n} footer(s), expected 2 - the template changed')
    return html, problems, n


def _assert_style_placeholders(html):
    """
    Every {{PLACEHOLDER}} in the template's <style> must be declared in
    STYLE_PLACEHOLDERS, and every 'carried' one must survive into the output.

    A wholesale <style> swap replaces a placeholder with whatever constant the
    vendored sheet was generated with, and the page still renders correctly -
    so nothing downstream can notice. That is how {{LOGIN_BG_IMAGE}} was dead
    from Deploy 1 until someone looked at paris_xxl's login screen.

    Note that our shipped stylesheet will KEEP containing a baked
    url('upload.JPG'), because it is extracted from a generated mock. A future
    sheet is not clean; the swap must re-inject every time.
    """
    problems = []
    if not TEMPLATE_PATH.exists():
        return ['style placeholders: dashboard_template.html not found']
    block = STYLE_BLOCK_RE.search(TEMPLATE_PATH.read_text(encoding='utf-8'))
    if not block:
        return ['style placeholders: no <style> block in the template']

    found = set(re.findall(r'\{\{([A-Z0-9_]+)\}\}', block.group(0)))
    for name in sorted(found - set(STYLE_PLACEHOLDERS)):
        problems.append(
            f'style placeholders: {{{{{name}}}}} is rendered inside the '
            f'template <style> but is not declared in STYLE_PLACEHOLDERS - the '
            f'stylesheet swap will discard it silently')
    for name in sorted(set(STYLE_PLACEHOLDERS) - found):
        problems.append(
            f'style placeholders: {name} is declared but no longer in the '
            f'template <style> - remove it from STYLE_PLACEHOLDERS')
    return problems


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


def _assert_projection(html, stats, div_balance_before, ac_t_before):
    """Post-conditions for restructure_projection. Returns a list of problems."""
    problems = []
    n = stats.get('days')
    if n is None:
        return problems  # the pass already reported why it bailed

    for marker, label in (('class="proj-grid"', '.proj-grid'),
                          ('class="chart-tabs"', '.chart-tabs'),
                          ('id="proj-day', '#proj-day{N}'),
                          ('id="proj-logique"', '#proj-logique')):
        left = html.count(marker)
        if left:
            problems.append(f'projection: {left} {label} survived the rewrite')

    q_cards = html.count('class="q-card"')
    if q_cards != n:
        problems.append(
            f'projection: {q_cards} .q-card(s) after the rewrite, expected {n}')

    # One new accordion per day card, plus one for the methodology card.
    want_ac_t = ac_t_before + n + 1
    ac_t = html.count('class="ac-t"')
    if ac_t != want_ac_t:
        problems.append(
            f'projection: {ac_t} .ac-t element(s), expected {want_ac_t}')

    # --- the palette ---------------------------------------------------
    # Two charts per day (S1 and S2), each carrying one sales line and one
    # projection line, and each with a legend repeating the same two colours.
    want = {'dataset': 4 * n, 'legend': 4 * n}
    got = stats.get('recoloured', {})
    for kind, expected in want.items():
        if got.get(kind) != expected:
            problems.append(
                f'projection: recoloured {got.get(kind)} {kind} colour(s), '
                f'expected {expected}')

    for literal in (PROJ_LINE_OLD, MOCK_PROJ_LINE_OLD):
        if literal in html:
            problems.append(f'projection: {literal} survived the recolour')

    at = html.find('<div id="sec-projection"')
    close, end = _match_div(html, at)
    if SALES_LINE_OLD in html[at:end]:
        problems.append(
            f'projection: {SALES_LINE_OLD} survived inside #sec-projection')

    # The other side of the same coin. #fbbf24 also drives the day tag text
    # colours, the hebdo bars and the velocity and revenue charts, so a zero
    # count document-wide means the replace reached outside the projection
    # block and repainted things nobody asked to change.
    if SALES_LINE_OLD not in html:
        problems.append(
            f'projection: {SALES_LINE_OLD} is gone from the whole document - '
            f'the recolour was too broad')

    for i in range(n):
        if f'canvas id="chartDay{i}S1"' not in html:
            problems.append(f'projection: canvas chartDay{i}S1 is gone')
        # With no tabs left, anything still parked in _projBuilders is a chart
        # that will never be built.
        if f"_projBuilders['day{i}S1']" in html:
            problems.append(f'projection: day{i}S1 is still lazy but nothing can trigger it')
        if f"_projBuilders['day{i}S2']" not in html:
            problems.append(f'projection: day{i}S2 lost its lazy builder')

    after = html.count('<div') - html.count('</div>')
    if after != div_balance_before:
        problems.append(
            f'projection: div balance moved from {div_balance_before} to {after}')

    # The Deploy 1 selectors. These canvases live outside the projection
    # block, but the restructure moves .ac-body elements around them, and a
    # closest() that stops resolving fails in total silence.
    for canvas_id in ('chartVelocity', 'chartVelocity14', 'chartRevenue'):
        at = html.find(f'<canvas id="{canvas_id}"')
        if at < 0:
            continue  # conditional section, genuinely absent on some events
        if not any('ac-body' in c.split()
                   for c in _div_ancestor_classes(html, at)):
            problems.append(
                f"projection: {canvas_id} has no .ac-body ancestor - its "
                f"canvas.closest('.ac-body') loader would never fire")
    return problems


def _assert_deploy3(html, stats, ac_t_before, cutoffs_before):
    """
    Post-conditions for apply_deploy3.

    Every count below states what it is over. Markup counts key on class="..."
    because the stylesheet still ships .dtl-cutoff, .vel-head, .det-link and
    .inset-divider rules - see the STANDING RULE at the top of this file.
    """
    problems = []

    # --- suivi (markup) ---
    for _, container, sep in SUIVI_GRAINS:
        n = html.count('id="%s"' % sep)
        if n != 1:
            problems.append(f'suivi: {n} #{sep} in markup, want 1')
    scrolls = html.count('h.scrollTop=h.scrollHeight')
    if scrolls != 2:
        problems.append(f'suivi: {scrolls} scroll-to-bottom call(s) in markup, want 2')

    # Derived, never hardcoded: parisxxl emits no "A venir" divider at all,
    # bordeaux emits one, the other four emit two.
    added = len(stats.get('separators', []))
    want_cutoffs = cutoffs_before + added
    got_cutoffs = html.count('class="dtl-cutoff"')
    if got_cutoffs != want_cutoffs:
        problems.append(
            f'suivi: {got_cutoffs} .dtl-cutoff in markup, want {want_cutoffs} '
            f'({cutoffs_before} pre-existing + {added} new)')

    # --- velocity ---
    # The old grid is an inline style, so the stylesheet cannot contain it and
    # a whole-file count is correct. The new names are classes, so those are
    # markup counts.
    if VEL_GRID_ANCHOR in html:
        problems.append('velocity: the old inline grid survived (whole file)')
    for cls in ('vel-head', 'vel-grid'):
        n = html.count('class="%s"' % cls)
        if n != 1:
            problems.append(f'velocity: {n} .{cls} in markup, want 1')

    # --- inset (markup) ---
    dividers = html.count('class="inset-divider"')
    if dividers != 1:
        problems.append(
            f'inset: {dividers} .inset-divider in markup, want 1 - the '
            f'generator emits 2 and this pass removes the trailing one. '
            f'(A whole-file count reads 3: the third is the stylesheet rule.)')

    # --- platform cards (markup) ---
    p = stats.get('platform', {})
    links = html.count('class="det-link"')
    txt = html.count('class="det-link-txt"')
    if links != p.get('cards'):
        problems.append(f'platform: {links} .det-link in markup, want {p.get("cards")}')
    if txt != links:
        problems.append(f'platform: {txt} .det-link-txt in markup, want {links}')
    imgs = html.count('<img src="logo-shotgun.png"') + html.count('<img src="logo-dice.png"')
    if imgs != links:
        problems.append(f'platform: {imgs} logo <img> in markup, want {links}')

    # Whole file: hostnames cannot appear in the stylesheet.
    if DICE_DASHBOARD_PREFIX in html:
        problems.append(f'platform: {DICE_DASHBOARD_PREFIX} survived (whole file)')
    for host, key in (('smartboard.shotgun.live/events/', 'smartboard'),
                      ('mio.dice.fm/events/', 'mio')):
        want, got = p.get(key, 0), html.count(host)
        if got != want:
            problems.append(f'platform: {got} {host} in the file, want {want}')

    # Both Shotgun cards pointed at the same URL before this pass. If they
    # still do, the Smartboard rewrite silently did nothing.
    hrefs = re.findall(r'<a class="det-link" href="([^"]*)"', html)
    if len(hrefs) != len(set(hrefs)):
        problems.append('platform: two platform cards share an href')

    # Order: canonical, over whichever subset exists.
    names = re.findall(r'class="det-link-name">([^<]*)</div>', html)
    canonical = [new for _, new, _ in PLATFORM_CARDS]
    if names != [n for n in canonical if n in names]:
        problems.append(f'platform: cards out of canonical order: {names}')

    # Deploy 2's accordions must be untouched.
    if html.count('class="ac-t"') < ac_t_before:
        problems.append('deploy3: .ac-t count fell - a Deploy 2 accordion was lost')
    return problems


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

    subtitle_count = html.count(SUBTITLE_OLD)
    html = html.replace(SUBTITLE_OLD, SUBTITLE_NEW)
    if subtitle_count != 1:
        problems_early = f'login subtitle found {subtitle_count} time(s), expected 1'
    else:
        problems_early = None

    html, redesign_problems, renamed = apply_redesign(html)
    problems = list(redesign_problems)
    if problems_early:
        problems.append(problems_early)

    # _match_div walks raw <div>/</div> tags, so a <div inside a JS or CSS
    # string would silently mis-nest the whole rebuild. Assert it, rather than
    # assume it - the generator is free to start emitting one.
    if re.search(r'''['"]<div''', html):
        problems.append('projection: a quoted "<div" exists - div matching is unsafe')
        proj_stats = {}
    else:
        div_balance_before = html.count('<div') - html.count('</div>')
        ac_t_before = html.count('class="ac-t"')
        html, proj_problems, proj_stats = restructure_projection(html)
        problems += proj_problems
        problems += _assert_projection(
            html, proj_stats, div_balance_before, ac_t_before)

        cutoffs_before = html.count('class="dtl-cutoff"')
        html, d3_problems, d3_stats = apply_deploy3(html)
        problems += d3_problems
        problems += _assert_deploy3(html, d3_stats, ac_t_before, cutoffs_before)

        html, footer_problems, footers = apply_footer(html)
        problems += footer_problems
        d3_stats['footers'] = footers

        sidecar = path.with_suffix(path.suffix + '.suivi.json')
        html, suivi_problems, suivi_stats = suivi_selector.apply(html, sidecar)
        problems += suivi_problems
        d3_stats['suivi'] = suivi_stats

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

    # The whole point of shipping §7 separately. stamp_footer.py patches the
    # footer in published HTML out of band; if this file is not stampable the
    # failure surfaces four hours later, on a quiet run, as a stale timestamp -
    # which is the exact symptom N4 existed to remove. Assert it here, with the
    # stamper's own matcher, so it is a failed build instead.
    stampable = len(stamp_footer.STAMP_ITEM_RE.findall(html))
    if stampable != 2:
        problems.append(
            f'footer: stamp_footer.py would match {stampable} item(s), needs '
            f'exactly 2 - a quiet run would stop updating the timestamp')
    # And that stamping is surgical: dry-run it and require the item count to
    # survive. Matching twice is not the same as matching only its own item.
    items = html.count('class="pgf-item')
    dry, _ = stamp_footer.restamp(html, stamp_footer.CHECK_LABEL, '00:00')
    dry_items = dry.count('class="pgf-item')
    if dry_items != items:
        problems.append(
            f'footer: a stamp would take the item count from {items} to '
            f'{dry_items} - the match is consuming its neighbours')
    for emoji in ('🎟', '🔄', '🔒'):
        if emoji in html:
            problems.append(f'footer: raster glyph {emoji} survived (whole file)')

    # Stamped LAST, so it covers the page as written rather than as
    # intended. Nothing reads it at runtime; it exists so a check can
    # ask whether this page was built from today's shared assets
    # WITHOUT knowing what changed in them.
    html = STAMP_RE.sub('', html)
    html = html.replace('</body>', f'<!-- shared:{shared_hash()} -->\n</body>', 1)
    path.write_text(html, encoding='utf-8')
    sw_items = html.count('class="sw-item')
    print(f"{path.name}: removed {link_count} upload link(s), "
          f"replaced {footer_count} footer label(s), "
          f"relocalised {logo_count} logo hotlink(s), "
          f"shared auth via {AUTH_KEY}, "
          f"nav shell aligned ({sw_items} session items), "
          f"projection restructured into {proj_stats.get('days', 0)} day card(s), "
          f"charts built immediately: {proj_stats.get('built_immediately', [])}, "
          f"palette: {proj_stats.get('recoloured', {})}, "
          f"deploy3: {d3_stats}")

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


# ---------------------------------------------------------- build stamp --
# THE SHARED SET, on the production side. Short and closed, and it is a
# statement about what a production page is MADE OF rather than about what has
# shipped: a page is built from dashboard_template.html through run.py and
# THIS file, with the vendored stylesheet and font links swapped in. The mock
# and dashboard_redesign.css are NOT in it - they reach v2 only, which is why
# the two frozen production pages could never have missed a mock deviation.
#
# Auditing an exemption from the CHANGELOG reaches for the wrong list. Auditing
# it from the artefact's ingredients gives this, and the check states it so the
# next reader does not have to remember.
BASE_DIR = Path(__file__).resolve().parent.parent
SHARED_ASSETS = (
    'style/dashboard_v6_8.css',
    'style/font_links.html',
    'dashboard_template.html',
    'scripts/postprocess_html.py',
    'scripts/build_dashboard.py',
    'run.py',
)
STAMP_RE = re.compile(r'<!-- shared:([0-9a-f]{12}) -->')


def shared_hash(root=None):
    """One hash over every shared asset, content not mtime.

    mtime moves on a checkout and says nothing; content is what the page was
    built from. Missing files hash as absent rather than raising, so a renamed
    asset changes the stamp instead of crashing the check.
    """
    root = Path(root or BASE_DIR)
    h = hashlib.sha256()
    for rel in SHARED_ASSETS:
        f = root / rel
        h.update(rel.encode())
        h.update(f.read_bytes() if f.exists() else b'<absent>')
    return h.hexdigest()[:12]


def main():
    if len(sys.argv) < 2:
        raise SystemExit('usage: postprocess_html.py <file.html> [<file.html> ...]')
    ok = True
    for arg in sys.argv[1:]:
        ok = postprocess(arg) and ok
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
