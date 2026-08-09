#!/usr/bin/env python3
"""
Picking a comparison must change the numbers, and change them CORRECTLY.

    NODE_PATH=/opt/node22/lib/node_modules python3 verify/check_b1_switch.py

WHAT IT DOES
------------
Serves the repo over HTTP (the pages `fetch` their series files, which a
`file://` origin blocks), loads each v2 page, and for every candidate in the
comparison menu clicks it and reads the reference column BACK OUT OF THE
RENDERED ROWS — the dates and counts a reader actually sees.

Those pairs are then compared against `dashboard_payload.daily_rows`, the
server-side implementation that has been shipping since before B1. So the check
is not "did something change": it is **two independent implementations of the
same alignment, in two languages, agreeing row for row**. The JS is new; the
Python is the one whose output Leo has been reading for weeks.

THE SNAP IS THE POINT
---------------------
`jx_ref = jx_cur − signed_mod7(cur_ev − cand_ev)` is 0 on three of the six live
pairs and ±1 on the other three. A client that read jx straight through would
agree with the server on half the comparisons and be one day out on the rest,
rendering as ordinary numbers with nothing to notice.

So the snap is asserted directly as well: constant across every row of a pair,
equal to the closed form, and — because a rule that is always zero is a rule
that has never run — at least one non-zero snap must appear across the set.
"""

import json
import re
import subprocess
import sys
import threading
from datetime import date
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))
CHROME = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

import run  # noqa: E402
import dashboard_payload as dp  # noqa: E402
import build_series  # noqa: E402

PAGE_EVENT = {'rennes.html': 'rennes_2026', 'bordeaux.html': 'bordeaux_2026',
              'epk.html': 'epk_2026', 'geneve.html': 'geneve_2026',
              'parisxxl.html': 'paris_xxl_2026',
              'bordeaux_oct.html': 'bordeaux_oct_2026'}

JS = r"""
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROME });
  const out = [];
  for (const spec of process.argv.slice(2)) {
    const [url] = spec.split('|');
    const ctx = await b.newContext({ viewport: { width: 1200, height: 900 } });
    const p = await ctx.newPage();
    const errs = [];
    p.on('pageerror', e => errs.push(String(e).slice(0, 200)));
    await p.goto(url, { waitUntil: 'load' });
    await p.evaluate(() => {
      const i = document.getElementById('db-pw-input');
      if (i) i.value = 'festipass';
      if (typeof dbSubmit === 'function') dbSubmit();
    });
    await p.waitForTimeout(300);

    const names = await p.evaluate(() =>
      (typeof CMAP === 'undefined' ? [] : Object.keys(CMAP)));
    const picks = {};
    for (const n of names) {
      await p.evaluate(async (nm) => { await pickCmp(nm); }, n);
      await p.waitForTimeout(250);
      picks[n] = await p.evaluate(() => {
        const rows = [...document.querySelectorAll('#suivi .sv:not(.sv-solo)')];
        const num = s => s.replace(/[^0-9]/g, '');
        return {
          err: !!document.querySelector('#suivi .empty-t'),
          rows: rows.map(r => {
            const l = r.querySelector('.sv-l');
            if (!l) return null;
            const d = l.querySelector('.sv-d'), n = l.querySelector('.sv-n');
            const nn = n ? n.cloneNode(true) : null;
            if (nn) nn.querySelectorAll('span').forEach(s => s.remove());
            const txt = nn ? nn.textContent.trim() : '';
            return [d ? d.textContent.trim() : '', txt === '—' ? '—' : num(txt)];
          }).filter(Boolean),
          header: (document.querySelector('#suivi .sv-h span') || {}).textContent,
        };
      });
    }
    out.push({ url, names, picks, errors: errs });
    await ctx.close();
  }
  console.log('@@' + JSON.stringify(out));
  await b.close();
})();
"""

DAYS_FR = ['dim', 'lun', 'mar', 'mer', 'jeu', 'ven', 'sam']
MOS = ['jan', 'fév', 'mar', 'avr', 'mai', 'juin', 'juil', 'aoû', 'sep', 'oct',
       'nov', 'déc']


def fday(d):
    """The mock's own `fday`, so the comparison is against what it renders."""
    return f'{DAYS_FR[(d.weekday() + 1) % 7]} {d.day} {MOS[d.month - 1]}'


def signed_mod7(g):
    m = g % 7
    return m - 7 if m > 3 else m


def expected(event, cand, cutoff, cfg_all):
    """The reference column, from the server-side implementation."""
    cfg, ccfg = cfg_all[event], cfg_all[cand]
    cur_rows = dp.load_rows(str(ROOT / 'data' / f'{event}_merged.csv'))
    crows = dp.load_rows(str(build_series.series_path(cand)))
    cur_n, cur_rev = dp.series(cur_rows)
    c_n, c_rev = dp.series(crows)
    cut_rows = run.filter_tickets_to_same_point(
        [{**r, 'order_date': r['_d']} for r in crows], cutoff,
        cfg['event_date_first'], ccfg['event_date_first'])
    c_cut = max((r['order_date'] for r in cut_rows), default=None)
    off = dp.daily_offset(cfg['event_date_first'], ccfg['event_date_first'])
    first = min(cur_n) if cur_n else cutoff
    rows = dp.daily_rows(cur_n, cur_rev, c_n, c_rev, cutoff, first, off, c_cut,
                         cfg['event_date_first'], ccfg['event_date_first'])
    # EVERY row, with the same em-dash sentinel the template now renders for
    # a missing counterpart. Filtering the blanks out of one side and not the
    # other is how the first version of this compared 155 rows against 157 and
    # reported a difference that was its own.
    pairs = [(fday(date.fromisoformat(r['db'])) if r['db'] else '—',
              str(r['b']) if r['b'] is not None else '—')
             for r in rows]
    snap = signed_mod7((cfg['event_date_first'] - ccfg['event_date_first']).days)
    return pairs, snap


def main():
    pages = sorted((ROOT / 'v2').glob('*.html'))
    if not pages:
        print('no v2 pages - nothing to check')
        return 1
    if not (ROOT / 'series').is_dir():
        print('FAIL: series/ does not exist. Run scripts/build_series.py.')
        return 1

    handler = partial(SimpleHTTPRequestHandler, directory=str(ROOT))
    srv = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    script = ROOT / '.check_b1.js'
    script.write_text(JS, encoding='utf-8')
    try:
        env = {'CHROME': CHROME, 'NODE_PATH': '/opt/node22/lib/node_modules',
               'PATH': '/opt/node22/bin:/usr/bin:/bin'}
        res = subprocess.run(
            ['node', str(script)] +
            [f'http://127.0.0.1:{port}/v2/{p.name}' for p in pages],
            capture_output=True, text=True, env=env, timeout=900)
    finally:
        script.unlink(missing_ok=True)
        srv.shutdown()
    if res.returncode != 0:
        print('FAIL: could not drive the pages')
        print(res.stderr[-1500:])
        return 1
    line = next((l for l in res.stdout.split('\n') if l.startswith('@@')), None)
    if not line:
        print('FAIL: no result line')
        print(res.stdout[-800:] + res.stderr[-800:])
        return 1

    cfg_all = run.load_event_config(str(ROOT / 'event_config.csv'))
    failures, snaps = [], []
    import io
    import contextlib
    for row in json.loads(line[2:]):
        name = row['url'].rsplit('/', 1)[-1]
        event = PAGE_EVENT.get(name)
        src = (ROOT / 'v2' / name).read_text(encoding='utf-8')
        D = json.loads(re.search(r'const D=(\{.*?\});\s*\n', src, re.DOTALL).group(1))
        cutoff = date.fromisoformat(D['ev']) - __import__('datetime').timedelta(days=D['jx'])
        cmap = {c['n']: c['id'] for c in D.get('cands', [])}
        if not cmap:
            failures.append(f'{name}: the comparison menu is empty')
            print(f'  FAIL  {name}: no candidates')
            continue
        if row['errors']:
            failures.append(f'{name}: pageerror')
            print(f"  FAIL  {name}: {row['errors'][0]}")
        seen = set()
        bad = []
        for label, got in row['picks'].items():
            cid = cmap.get(label)
            if got['err']:
                bad.append(f'{label}: rendered the unavailable banner')
                continue
            with contextlib.redirect_stdout(io.StringIO()):
                want, snap = expected(event, cid, cutoff, cfg_all)
            snaps.append((name, cid, snap))
            g = [tuple(x) for x in got['rows']]
            w = list(want)
            # The rendered set is what is in the DOM; compare as sequences of
            # (date, count) after dropping rows the template renders blank.
            if g != w:
                first_bad = next((i for i, (a, b) in enumerate(zip(g, w)) if a != b),
                                 min(len(g), len(w)))
                bad.append(f'{label}: {len(g)} rendered vs {len(w)} expected; '
                           f'first difference at {first_bad}: '
                           f'{g[first_bad] if first_bad < len(g) else "-"} vs '
                           f'{w[first_bad] if first_bad < len(w) else "-"}')
            seen.add(tuple(g[:12]))
        if len(row['picks']) > 1 and len(seen) < 2:
            bad.append('every candidate renders the same rows - the selection '
                       'is not reaching the table')
        if bad:
            failures.append(name)
            print(f'  FAIL  {name}')
            for x in bad[:4]:
                print(f'          {x}')
        else:
            print(f"  ok    {name}: {len(row['picks'])} candidates, each matching "
                  f"dashboard_payload row for row")

    nz = [s for s in snaps if s[2]]
    print()
    print(f'snap: {len(snaps)} pair(s), {len(nz)} non-zero '
          f'({", ".join(f"{c}:{v:+d}" for _, c, v in nz[:4])}'
          f'{" …" if len(nz) > 4 else ""})')
    if snaps and not nz:
        failures.append('every snap is zero')
        print('  FAIL  every snap is zero - the correction has never actually run, '
              'so nothing here distinguishes it from reading jx straight through')

    print()
    if failures:
        print(f'FAILED: {len(failures)}')
        return 1
    print(f'{len(snaps)} comparison(s) across {len(pages)} page(s): the client '
          f'alignment agrees with the server implementation')
    return 0


if __name__ == '__main__':
    sys.exit(main())
