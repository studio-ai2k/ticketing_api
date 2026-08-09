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
        ("let CSEL = 'Elektric Park 2023'",
         "let CSEL = " + repr(ref_label or '—')),
        ("{g:'Éditions Elektric Park', items:[{n:'Elektric Park 2023', d:'252 j', ref:true}]}",
         "{g:'Édition de référence', items:[{n:" + repr(ref_label or '—') + ", d:'', ref:true}]}"),
    ]


# §3: root-relative assets inherited from PRODUCTION chrome, which lives outside
# the replaced region - so these are applied to the whole page, not the region.
# /v2/ is one directory deeper, so every relative path resolves one level wrong.
# The nav logo works only because it happens to be an absolute URL.
PAGE_PATHS = [
    ('src="LOGO_ROND_JAUNE.png"', 'src="../LOGO_ROND_JAUNE.png"'),
    ("url('upload.JPG')", "url('../upload.JPG')"),
]


def strip_placeholders(region):
    """Remove what must never reach a reader: the mock filename (§4) and the
    upload link, which points at a page that does not exist under /v2/."""
    out = region
    out = re.sub(r'<a[^>]*upload\.html[^>]*>.*?</a>', '', out, flags=re.DOTALL)
    out = re.sub(r'\s*Voir\s*<code[^>]*>campagne_mock\.html</code>\s*\.?', '', out)
    out = out.replace('campagne_mock.html', '')
    return out


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

    pi, pj = body_of(page)
    out = page[:pi] + region + page[pj:]

    # The upload link lives in the NAV, outside the replaced region, so the
    # region-level strip cannot see it. Production removes it in postprocess
    # pass 1; v2 does not run postprocess, so it must be removed here - and with
    # postprocess's own matcher, not a second one that can drift from it.
    out, ln = postprocess_html.UPLOAD_LINK_RE.subn('', out)
    if ln != 1:
        raise SystemExit(
            f'pass 0: upload link matched {ln} time(s), want 1. It points at '
            'v2/upload.html, which does not exist.')

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
    D = dashboard_payload.build(a.event, a.csv,
                                datetime.strptime(cutoff, '%Y-%m-%d').date(),
                                a.config, ref or None,
                                str(ref_csv) if ref_csv else None)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cfg_all = run.load_event_config(a.config)
    ident = event_identity(cfg_all[a.event], cfg_all.get(ref),
                           (cfg_all.get(ref) or {}).get('event_name', ref))
    out.write_text(apply_v2_body(base.read_text(encoding='utf-8'), D, ident),
                   encoding='utf-8')
    print(f'{out}: {out.stat().st_size / 1024:.0f} KB  (cutoff {cutoff}, ref {ref or "none"})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
