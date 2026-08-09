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
import tempfile
from pathlib import Path

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


def apply_v2_body(page, payload):
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

    pi, pj = body_of(page)
    out = page[:pi] + region + page[pj:]

    css = SHEET.read_text(encoding='utf-8')
    out, sn = STYLE_RE.subn(lambda m: '<style>\n' + css + '\n</style>', out, count=1)
    if sn != 1:
        raise SystemExit(f'pass 0: stylesheet swap matched {sn} <style> blocks (want 1)')
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
    from datetime import datetime
    D = dashboard_payload.build(a.event, a.csv,
                                datetime.strptime(cutoff, '%Y-%m-%d').date(),
                                a.config, ref or None,
                                str(ref_csv) if ref_csv else None)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(apply_v2_body(base.read_text(encoding='utf-8'), D), encoding='utf-8')
    print(f'{out}: {out.stat().st_size / 1024:.0f} KB  (cutoff {cutoff}, ref {ref or "none"})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
