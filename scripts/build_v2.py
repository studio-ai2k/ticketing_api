#!/usr/bin/env python3
"""
Pass 0: replace the page body with the redesign's, and publish to v2/.

    python scripts/build_v2.py --event bordeaux_2026 \
        --csv data/bordeaux_2026_merged.csv --out v2/bordeaux.html

Every earlier deploy patched REGIONS of run.py's markup and asserted the
surroundings were unchanged. This replaces the body outright, so "assert the
surroundings" has to mean something narrower: the surroundings are the auth
overlay and the nav, and they are exactly what this does not touch.

THE SEAM IS `</nav>` .. `</body>`.

  <body> … db-overlay …        kept — the festipass gate, untouched
  <nav> … </nav>               kept — production's nav is the real one
  </nav> …………… </body>         REPLACED with the mock's wrap + scripts

That boundary settles the dropdown problem by construction. Production's
`.sw-*` machinery lives *inside* the replaced region, and so does the mock's, so
exactly one copy survives. Injecting the mock's JS on top of production's would
have left two `document`-level click handlers: the first opens the wrap, the
second sees `wasOpen === true` and closes it, and `stopPropagation` does not
stop a sibling listener on the same element — the dropdown would never open.
Replacing the whole region removes the need to strip anything.

The stylesheet is swapped here too, to `redesign/style/dashboard_redesign.css`.
`apply_redesign` installs the PRODUCTION sheet, which has no rules for the
redesign's markup; v2 needs the redesign one. When v2 becomes production the two
converge and this stops being a separate step.
"""

import argparse
import json
import re
import subprocess
import sys

MONTHS_FR = ('janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet',
             'août', 'septembre', 'octobre', 'novembre', 'décembre')
import tempfile
from pathlib import Path

import postprocess_html  # noqa: E402 - for its upload-link matcher

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / 'scripts'))

MOCK = BASE_DIR / 'redesign' / 'mock' / 'dashboard_v3.39.html'
SHEET = BASE_DIR / 'redesign' / 'style' / 'dashboard_redesign.css'

STYLE_RE = re.compile(r'<style>.*?</style>', re.DOTALL)
PAYLOAD_RE = re.compile(r'(const D=)(\{.*?\})(;\s*\n)', re.DOTALL)
# `const D` was not the only payload in the mock. `LG` drove the "Logique de
# projection" accordion and shipped epk's samedi 8 083 / dimanche 4 513 under
# every other event's name. D21 removed it: the block now reads the SELECTED
# projection candidate, which the payload already carries, so the second copy
# had no reason to exist. Kept in the ledger because the substitution being
# gone is only correct while the literal is also gone - check_mock_literals
# asserts that pairing.


# The mock's own copy of the session-switcher IIFE. It is a SNAPSHOT of a live
# nav that has since moved on, so it is replaced with production's rather than
# kept - see swap_nav_script.
MOCK_SW_HEAD = '/* Session switcher toggle — from BudgetFlow, hardcoded for billetterie */'
# Production's copy: the one script block after </nav> that drives the nav.
PROD_SW_MARKS = ('openWrap', 'closeAll', 'data-sw-trigger')


def prod_nav_script(page):
    """Production's nav-switcher <script> block, verbatim.

    The nav's MARKUP is before `</nav>` and its BEHAVIOUR is after, so the seam
    splits them: pass 0 preserves the markup and deletes the code that animates
    it. dee55c4 concluded the seam settled the double-handler problem "by
    construction - exactly one copy survives", which is true and incomplete: the
    surviving copy was the MOCK's, and the mock's nav is a lossy snapshot.
    Anything production's nav has gained since then had markup and no handler.

    So the surviving copy must be PRODUCTION's. That also keeps the property
    that made the seam attractive - still exactly one copy - while fixing which
    one it is.
    """
    i = page.find('</nav>')
    for m in re.finditer(r'<script[^>]*>', page[i:]):
        s = i + m.start()
        e = page.find('</script>', s) + len('</script>')
        block = page[s:e]
        if all(k in block for k in PROD_SW_MARKS):
            return _reexport_close_all(block)
    raise SystemExit(
        'pass 0: production\'s nav-switcher script not found after </nav>. '
        'Without it the nav renders as inert markup - the switcher opens '
        'nothing and the controls do not respond.')


# The mock's nav block exported exactly ONE symbol to the page: `swCloseAll`.
# Grepped both blocks for `window.` assignments to be sure it is one and not
# "the one I happened to notice" - production's has none.
CLOSE_ALL_DEF = 'function closeAll(){ document.querySelectorAll(\'.sw-wrap.open\').forEach(closeWrap); }'
CLOSE_ALL_EXPORT = (
    '\n  /* Re-rendering a control destroys the wrap that owns its floated menu,\n'
    '     which would strand the menu in <body> forever. Handlers must close\n'
    '     first. Carried from the mock\'s block: production defines closeAll but\n'
    '     never exported it, and pickCmp/pickProj call it through a `if\n'
    '     (window.swCloseAll)` guard - so the menu stayed open on select and\n'
    '     nothing errored. */\n'
    '  window.swCloseAll = closeAll;')


def _reexport_close_all(block):
    """Production's nav script defines `closeAll` and keeps it private.

    The mock's copy ended `window.swCloseAll = closeAll;`, and `pickCmp` /
    `pickProj` both call it. Replacing the block with production's took the
    export with it, and because both call sites are guarded the dropdown simply
    stopped closing on select - no error, no console, nothing to notice.

    THE SEAM, ONE LAYER UP: markup and behaviour were reconciled and the
    INTERFACE between them was not. Asserted rather than best-effort - a silent
    miss here reproduces the exact defect.
    """
    if 'window.swCloseAll' in block:
        return block
    if block.count(CLOSE_ALL_DEF) != 1:
        raise SystemExit(
            'pass 0: production\'s nav script does not define closeAll in the '
            'shape this expects, so swCloseAll cannot be re-exported. The '
            'comparison and projection menus need it or they never close on '
            'select. Find the new definition; do not drop the export.')
    return block.replace(CLOSE_ALL_DEF, CLOSE_ALL_DEF + CLOSE_ALL_EXPORT, 1)


def swap_nav_script(region, prod_block):
    """Drop the mock's snapshot of the nav JS; production's is carried instead."""
    i = region.find(MOCK_SW_HEAD)
    if i < 0:
        raise SystemExit(
            'pass 0: the mock\'s session-switcher block was not found. If it '
            'moved, find it - leaving it in alongside production\'s gives two '
            'document-level click handlers and the dropdown never opens.')
    j = region.find('(function(){', i)
    depth, k = 0, j
    while k < len(region):
        if region[k] == '(':
            depth += 1
        elif region[k] == ')':
            depth -= 1
            if depth == 0:
                break
        k += 1
    end = region.find(';', k) + 1
    return region[:i] + region[end:]


def body_of(html):
    """Everything between `</nav>` and `</body>` — the page and its scripts."""
    i = html.find('</nav>')
    j = html.rfind('</body>')
    if i < 0 or j < 0 or j <= i:
        raise SystemExit(
            'pass 0: could not find the </nav> .. </body> seam. The template '
            'moved; do not guess a new boundary — the nav and the auth overlay '
            'must stay on the outside of it.')
    return i + len('</nav>'), j


def event_identity(cfg, ref_cfg, ref_label):
    """Literals the mock hardcodes because it is a SINGLE-EVENT artefact.

    Pass 0 splices the mock's structure and its IDENTITY with it. bordeaux_oct
    shipped reading "événement les 5-6 septembre 2026" (epk's dates) and
    "Elektric Park 2026" (epk's name) - ordinary sentences, no error, nothing to
    notice. The payload was right; the markup around it was not.

    Every entry is asserted to match exactly once. A miss puts another event's
    identity on the page, which is the failure this exists to stop, so it must
    fail the build rather than pass silently.
    """
    days = sorted(cfg['days'], key=lambda x: x['day_date'])
    first, last = days[0]['day_date'], days[-1]['day_date']
    if first == last:
        span = f"le {first.day} {MONTHS_FR[first.month - 1]}"
    elif first.month == last.month:
        span = f"les {first.day}\u2013{last.day} {MONTHS_FR[first.month - 1]}"
    else:
        span = (f"les {first.day} {MONTHS_FR[first.month - 1]}\u2013"
                f"{last.day} {MONTHS_FR[last.month - 1]}")
    def _span(c):
        if not c or not c.get('days'):
            return '—'
        dd = sorted(c['days'], key=lambda x: x['day_date'])
        a, b = dd[0]['day_date'], dd[-1]['day_date']
        if a == b:
            return f'{a.day} {MONTHS_FR[a.month - 1]}'
        if a.month == b.month:
            return f'{a.day}\u2013{b.day} {MONTHS_FR[a.month - 1]}'
        return f'{a.day} {MONTHS_FR[a.month - 1]}\u2013{b.day} {MONTHS_FR[b.month - 1]}'

    ref_span = _span(ref_cfg)
    ref_venue = (ref_cfg or {}).get('venue') or '—'
    ref_city = (ref_cfg or {}).get('city') or ''
    ref_cap = f"{(ref_cfg or {}).get('total_capacity', 0):,}".replace(',', '\u202f') or '—'
    name = cfg.get('event_name', '').strip()
    brand = (cfg.get('brand') or name).strip()
    base = name.split(' 20')[0].strip() or name
    return [
        ('événement les 5\u20136 septembre ${YC}', f'événement {span} ${{YC}}'),
        ('Elektric Park ${YC}', f'{base} ${{YC}}'),
        ('Elektric Park ${YR}', f'{(ref_label or base).split(" 20")[0]} ${{YR}}'),
        ("'comparaison à jour de semaine identique · vs Elektric Park 2023'",
         f"'comparaison à jour de semaine identique · vs {ref_label or '—'}'"),
        # The selected candidate, not just the menu. Replacing the menu alone
        # left the Suivi selector defaulting to epk's label on every event.
        # The Détails "Lieu et dates" row - venue, city AND a second, differently
        # shaped date literal. Substituting only the vélocité sentence left epk's
        # venue on every page. Enumerating by eye missed it; the residual-leak
        # scan below is what found it.
        ("${row('Lieu','Île des Impressionnistes','Chatou')}\n        "
         "${row('Dates','5\u20136 septembre ' + YC)}",
         "${row('Lieu'," + repr(cfg.get('venue', '—') or '—') + ","
         + repr(cfg.get('city', '') or '') + ")}\n        "
         "${row('Dates'," + repr(span.replace('les ', '').replace('le ', '')) + " + ' ' + YC)}"),
        # The REFERENCE edition's Détails block - its own dates, venue and
        # capacity, all epk_2023's. Three separate hardcoded blocks carry event
        # identity in this mock; finding them took a residual-leak scan, not
        # reading. That scan is now verify/check_v2_identity.py.
        ("${row('Dates','1\u20132 septembre ' + YR)}\n        "
         "${row('Lieu','Île de Chatou','Chatou')}\n        "
         "${row('Jauge','35 000')}",
         "${row('Dates'," + repr(ref_span) + " + ' ' + YR)}\n        "
         "${row('Lieu'," + repr(ref_venue) + "," + repr(ref_city) + ")}\n        "
         "${row('Jauge'," + repr(ref_cap) + ")}"),
        # The Suivi column headers. The mock defines YC/YR from the payload and
        # uses them in 19 places - and hardcodes the years in these two. So the
        # rennes page (2026 vs 2025) headed its reference column "2023 (même
        # jour)". Found while rendering the weekly table for a different
        # question, and invisible to check_v2_identity for the reason that scan
        # cannot fix: a bare year is a NUMBER, and numbers have no fingerprint.
        # CYR, not YR: the header year follows the SELECTED comparison, which
        # B1 made mutable. YR is the configured reference and stops being the
        # right answer the moment someone picks another edition.
        ("${HAS_CMP ? H('2023 (même jour)','Diff','2026 (actuel)') "
         ": H('','','2026 (actuel)')}",
         "${HAS_CMP ? H(CYR + ' (même jour)','Diff',YC + ' (actuel)') "
         ": H('','',YC + ' (actuel)')}"),
        ("H('2023 (référence)','J−X','2026 (à venir)')",
         "H(CYR + ' (référence)','J−X',YC + ' (à venir)')"),
        ("let CSEL = 'Elektric Park 2023'",
         "let CSEL = " + repr(ref_label or '—')),
        # The CANDS group literal used to be substituted here. D12 replaced the
        # hardcoded menu with one built from D.cands, so there is no literal
        # left to fix - the identity it carried is now data.
    ]


# §3: root-relative assets inherited from PRODUCTION chrome, which lives outside
# the replaced region - so these are applied to the whole page, not the region.
# /v2/ is one directory deeper, so every relative path resolves one level wrong.
# The nav logo works only because it happens to be an absolute URL.
PAGE_PATHS = [
    ('src="LOGO_ROND_JAUNE.png"', 'src="../LOGO_ROND_JAUNE.png"'),
    ("url('upload.JPG')", "url('../upload.JPG')"),
    # B1's series files. Third asset class to go one directory deep, and the
    # only one that would fail at RUNTIME rather than at first paint - a broken
    # image is obvious, a fetch that 404s renders as "comparaison indisponible"
    # on every pick. Emitted as a root-relative template and rewritten here.
    ('"series/{id}.json"', '"../series/{id}.json"'),
]


def strip_placeholders(region):
    """Remove what must never reach a reader: the mock filename (§4) and the
    upload link, which points at a page that does not exist under /v2/."""
    out = region
    out = re.sub(r'<a[^>]*upload\.html[^>]*>.*?</a>', '', out, flags=re.DOTALL)
    out = re.sub(r'\s*Voir\s*<code[^>]*>campagne_mock\.html</code>\s*\.?', '', out)
    out = out.replace('campagne_mock.html', '')
    return out


def _family(event_id):
    """`epk_2026` -> `epk`, `bordeaux_oct_2026` -> `bordeaux_oct`.
    Same rule as suivi_candidates.family, so the two menus group alike."""
    parts = event_id.rsplit('_', 1)
    return parts[0] if len(parts) == 2 and parts[1].isdigit() else event_id


TABS_RE = re.compile(r'<div class="dept-tabs-bg"[^>]*>.*?</div>\s*</div>', re.DOTALL)


def transplant_tabs(page, mock):
    """Give the page the MOCK's section bar, buttons and all.

    Asserted once on each side, like every other substitution in pass 0: the
    tab bar is the one piece of nav markup the redesign owns, and a silent miss
    here ships production's four tabs under the redesign's handlers - which is
    what happened, and which rendered as a working page with the wrong labels.
    """
    m = TABS_RE.search(mock)
    if not m:
        raise SystemExit('pass 0: the mock has no .dept-tabs-bg block to transplant')
    if len(TABS_RE.findall(mock)) != 1 or len(TABS_RE.findall(page)) != 1:
        raise SystemExit(
            f'pass 0: .dept-tabs-bg matched {len(TABS_RE.findall(mock))} time(s) in '
            f'the mock and {len(TABS_RE.findall(page))} in the page, want 1 and 1')
    return TABS_RE.sub(lambda _: m.group(0), page, count=1)


def apply_v2_body(page, payload, identity=()):
    """Splice the mock's body into a run.py page, carrying the real payload."""
    mock = MOCK.read_text(encoding='utf-8')
    mi, mj = body_of(mock)
    region = mock[mi:mj]

    blob = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    region, n = PAYLOAD_RE.subn(lambda m: m.group(1) + blob + m.group(3), region, count=1)
    if n != 1:
        raise SystemExit(
            f'pass 0: the mock\'s `const D={{…}}` matched {n} time(s), want 1. '
            'The payload is the one thing that must be replaced; a miss here '
            'ships the mock\'s epk figures under another event\'s name.')

    for old, new in identity:
        if region.count(old) != 1:
            raise SystemExit(
                f'pass 0: identity literal {old[:60]!r} matched '
                f'{region.count(old)} time(s), want 1. The mock is a '
                'single-event artefact; a miss here ships another event\'s '
                'name or dates as an ordinary sentence.')
        region = region.replace(old, new, 1)
    region = strip_placeholders(region)

    region = swap_nav_script(region, None)

    pi, pj = body_of(page)
    # Production's nav script is carried across the seam with the nav it drives.
    out = page[:pi] + prod_nav_script(page) + '\n' + region + page[pj:]

    # The upload link lives in the NAV, outside the replaced region, so the
    # region-level strip cannot see it. Production removes it in postprocess
    # pass 1; v2 does not run postprocess, so it must be removed here - and with
    # postprocess's own matcher, not a second one that can drift from it.
    # Postprocess pass 1 already removes this, in production and here alike -
    # the link is not a v2 concern and never was. Kept as a belt-and-braces
    # removal that tolerates zero, because asserting exactly one would fail the
    # moment pass 1 does its job, and because at CUTOVER this must not turn into
    # a feature the redesign silently dropped.
    out, _ = postprocess_html.UPLOAD_LINK_RE.subn('', out)

    # C1/C2 - THE SECTION BAR IS NAV MARKUP, SO THE SEAM LEAVES IT BEHIND.
    #
    # `prod_nav_script` already records the halves: "the nav's MARKUP is before
    # `</nav>` and its BEHAVIOUR is after, so the seam splits them". The bar is
    # both. Its handlers (goPage, scrollToSection, the scroll-spy) live at the
    # end of the mock's body and arrive with the region; its BUTTONS live in
    # `<div class="dept-tabs-bg">` inside the nav and do not. Rebuilding the
    # mock with six tabs changed the behaviour on every page and none of the
    # labels - caught by measuring the SHIPPED page, which still read four.
    #
    # The bar is emitted by `dashboard_template.html`, which must not be
    # modified, and editing it would change the production pages too - they
    # retire at cutover and their tab bar is not ours to move. So the markup is
    # transplanted here, v2-only, exactly as the body is.
    out = transplant_tabs(out, mock)

    css = SHEET.read_text(encoding='utf-8')
    out, sn = STYLE_RE.subn(lambda m: '<style>\n' + css + '\n</style>', out, count=1)
    if sn != 1:
        raise SystemExit(f'pass 0: stylesheet swap matched {sn} <style> blocks (want 1)')

    # AFTER the style swap, not before: the swap re-introduces url('upload.JPG')
    # from the .db-overlay rule carried across for the gate. Rewriting paths
    # first left the login background pointing one directory up from nothing.
    for old, new in PAGE_PATHS:
        if old in out:
            out = out.replace(old, new)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--event', required=True)
    ap.add_argument('--csv', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--config', default=str(BASE_DIR / 'event_config.csv'))
    a = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix='v2_'))
    base = tmp / 'base.html'

    # run.py's own output, via the existing shim - which is also what observes
    # and clamps the cutoff, and writes it to the sidecar this reads.
    subprocess.run([sys.executable, str(BASE_DIR / 'scripts' / 'build_dashboard.py'),
                    '--event', a.event, '--csv', a.csv, '--out', str(base),
                    '--config', a.config], check=True, stdout=subprocess.DEVNULL)

    # POSTPROCESS FIRST. `align_nav_shell` (pass 9) is what builds the nav v2
    # needs: the dropdown switcher, the section pill, the account avatar.
    # Building on run.py's raw output gave v2 the old hidden <select> - which
    # looked like a CSS or seam problem and was neither.
    subprocess.run([sys.executable, str(BASE_DIR / 'scripts' / 'postprocess_html.py'),
                    str(base)], check=True, stdout=subprocess.DEVNULL)

    sidecar = json.loads(base.with_suffix('.html.suivi.json').read_text(encoding='utf-8'))
    anchors = sidecar.get('anchors') or {}
    cutoff = anchors.get('cutoff_date')
    if not cutoff:
        raise SystemExit('pass 0: no cutoff in the sidecar - it is OBSERVED, never '
                         'recomputed, so there is nothing to fall back to.')

    import csv as _csv
    ref = ''
    with open(a.config, encoding='utf-8-sig') as f:
        for row in _csv.DictReader(f):
            if (row.get('event_id') or '').strip() == a.event and (row.get('compare_to') or '').strip():
                ref = row['compare_to'].strip()
                break
    ref_csv = next((BASE_DIR / 'csv_database' / ref).glob('*_merged.csv'), None) if ref else None

    import dashboard_payload
    import run
    from datetime import datetime
    cut = datetime.strptime(cutoff, '%Y-%m-%d').date()

    # A4: every FINISHED edition with data is a projection candidate, not just
    # the configured comparison. Finished is the operative word - a projection
    # replays a reference's remaining curve, and a live edition has not run one
    # yet. Discovered here rather than in the payload so the payload keeps
    # taking explicit paths and stays testable from a fixture.
    #
    # TWO rules now, both from build_series so nothing here restates one. The
    # projection rule is the original and keeps the original name; the wider
    # comparison rule exists but the menu below does not use it yet, because a
    # live candidate is only meaningful once the LAUNCH anchoring mode ships.
    # Named separately here so widening is a one-line change and so the
    # difference is visible at the call site rather than only in build_series.
    import build_series
    cfg_all = run.load_event_config(a.config)
    proj = [c for c in build_series.projection_eligible(cfg_all, cut)
            if c != a.event]
    # THE MENU WIDENS. It ran on the projection rule while a live candidate had
    # no correct anchor; `days_since_launch` is that anchor and it is built,
    # checked at both grains and at 135/135. Comparing a live edition against
    # another live one is what the anchoring work was for, and the menu was the
    # last thing between the feature and a reader.
    menu = [c for c in build_series.comparison_eligible(cfg_all) if c != a.event]
    extra = [(cid, str(build_series.series_path(cid)))
             for cid in proj if cid != ref]

    D = dashboard_payload.build(a.event, a.csv, cut,
                                a.config, ref or None,
                                str(ref_csv) if ref_csv else None,
                                extra_refs=extra)

    # B1's menu. Built from the SERIES FILES that exist, not from the config:
    # an entry the reader can pick but not fetch is the failure mode the whole
    # option was priced to avoid.
    series_dir = BASE_DIR / 'series'
    mine = build_series.family(a.event) if hasattr(build_series, 'family') else None
    cands = []
    for cid in menu:
        f = series_dir / f'{cid}.json'
        if not f.exists():
            continue
        head = json.loads(f.read_text(encoding='utf-8'))
        cands.append({'id': cid, 'n': head['name'], 'lead': head['lead'],
                      # THREE groups, not two. `suivi_candidates.py:216` has
                      # emitted 'live' since it was written and
                      # `suivi_selector.GROUP_TITLES` has carried "Événements en
                      # cours" beside it - the design was complete and THIS was
                      # the one place that stopped at two. Sufficient while every
                      # candidate was finished; the moment the menu widened, live
                      # editions filed under "Autres éditions passées", which is
                      # wrong on its face. Same class as `jr >= 0` and the weekly
                      # `w >= 0`: a rule that was correct by accident until the
                      # data it described changed.
                      #
                      # Family takes precedence over status, matching
                      # suivi_candidates' own order. A same-family live edition
                      # therefore files under "Éditions <family>" - stated here
                      # because the mock's data has no such case to settle it.
                      #
                      # Liveness comes from the SERIES FILE, not from a test
                      # against this page's `cut`. A cut-relative test makes
                      # liveness a property of the page doing the looking: the
                      # first draft of this line tagged bordeaux_2026 `live` on
                      # parisxxl.html and `past` on the four other pages that
                      # offer it, because those pages cut earlier. An event is
                      # live or it is not. build_series already decided, once,
                      # per event - and `head` is the file it wrote.
                      'g': ('edition' if _family(cid) == _family(a.event)
                            else ('live' if head['live'] else 'past')),
                      'ref': cid == ref})
    _order = {'edition': 0, 'past': 1, 'live': 2}    # suivi_selector's own order
    cands.sort(key=lambda c: (_order.get(c['g'], 9), not c['ref'], c['n']))
    D['cands'] = cands
    D['family'] = _family(a.event).replace('_', ' ').title()
    D['series_path'] = 'series/{id}.json'
    if not cands:
        print('  warning: no series files - the comparison menu will be empty. '
              'Run scripts/build_series.py first.', file=sys.stderr)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    ident = event_identity(cfg_all[a.event], cfg_all.get(ref),
                           (cfg_all.get(ref) or {}).get('event_name', ref))
    out.write_text(apply_v2_body(base.read_text(encoding='utf-8'), D, ident),
                   encoding='utf-8')
    print(f'{out}: {out.stat().st_size / 1024:.0f} KB  (cutoff {cutoff}, ref {ref or "none"})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
