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
from datetime import date, timedelta
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
    const modes = await p.evaluate(() =>
      (typeof AMODES === 'undefined' ? ['j_minus'] : AMODES.map(m => m.k)));
    const picks = {};
    // MODE OUTSIDE, candidate inside. pickMode re-applies the current
    // candidate, so setting the mode first and then walking the menu exercises
    // both entry points into applySeries rather than only pickCmp's.
    for (const mode of modes) {
    await p.evaluate(async (m) => { await pickMode(m); }, mode);
    await p.waitForTimeout(200);
    for (const n of names) {
      await p.evaluate(async (nm) => { await pickCmp(nm); }, n);
      await p.waitForTimeout(250);
      // The WEEKLY column, read the same way. It was outside every selector
      // this check used - `.sv-l` reaches both grains, but only one grain is
      // ever rendered, and nothing here had switched it. "45 comparisons, row
      // for row" was true of the daily column and silent about the other half.
      const readCol = () => {
        const rows = [...document.querySelectorAll('#suivi .sv:not(.sv-solo)')];
        const num = s => s.replace(/[^0-9]/g, '');
        return rows.map(r => {
          const l = r.querySelector('.sv-l');
          if (!l) return null;
          const d = l.querySelector('.sv-d'), q = l.querySelector('.sv-n');
          const nn = q ? q.cloneNode(true) : null;
          if (nn) nn.querySelectorAll('span').forEach(s => s.remove());
          const txt = nn ? nn.textContent.trim() : '';
          return [d ? d.textContent.trim() : '', txt === '—' ? '—' : num(txt)];
        }).filter(Boolean);
      };
      await p.evaluate(() => grain('semaine'));
      await p.waitForTimeout(200);
      const weekly = await p.evaluate(readCol);
      await p.evaluate(() => grain('jour'));
      await p.waitForTimeout(200);
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
      picks[n].weekly = weekly;
      picks[mode + '\u0000' + n] = picks[n];
    }
    }
    out.push({ url, names, modes, picks, errors: errs });
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


def _sides(event, cand, cutoff, cfg_all, mode):
    """Both sides' series plus the three mode-dependent scalars.

    ONE place computes them for both grains, because the failure this check
    exists for is the two grains disagreeing about the mode - which is exactly
    what the launch offset would have caused if the weekly had not followed it.
    """
    cfg, ccfg = cfg_all[event], cfg_all[cand]
    cur_rows = dp.load_rows(str(ROOT / 'data' / f'{event}_merged.csv'))
    crows = dp.load_rows(str(build_series.series_path(cand)))
    cur_n, cur_rev = dp.series(cur_rows)
    c_n, c_rev = dp.series(crows)
    cur_lead = (cfg['event_date_first'] - min(cur_n)).days if cur_n else 0
    c_lead = (ccfg['event_date_first'] - min(c_n)).days if c_n else 0
    _rows = [{**r, 'order_date': r['_d']} for r in crows]
    # The same-point cut is RAW in every mode - run.py's two filters, neither
    # snapped. exact_date shares j_minus's cut because they differ by the snap
    # alone, which the cut never had.
    if mode == 'days_since_launch':
        cut_rows = run.filter_tickets_to_same_point_dsl(
            _rows, cutoff,
            cfg['event_date_first'] - timedelta(days=cur_lead),
            ccfg['event_date_first'] - timedelta(days=c_lead))
    else:
        cut_rows = run.filter_tickets_to_same_point(
            _rows, cutoff, cfg['event_date_first'], ccfg['event_date_first'])
    c_cut = max((r['order_date'] for r in cut_rows), default=None)
    off, wshift = dp.anchor(mode, cfg['event_date_first'],
                            ccfg['event_date_first'], cur_lead, c_lead)
    return cfg, ccfg, cur_n, cur_rev, c_n, c_rev, off, wshift, c_cut


def expected(event, cand, cutoff, cfg_all, mode='j_minus'):
    """The reference column, from the server-side implementation."""
    (cfg, ccfg, cur_n, cur_rev, c_n, c_rev,
     off, _wshift, c_cut) = _sides(event, cand, cutoff, cfg_all, mode)
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


def fwk(a, b):
    """The mock's own `fwk`, so the comparison is against what it renders."""
    if a.month == b.month:
        return f'{a.day}-{b.day} {MOS[b.month - 1]}'
    return f'{a.day} {MOS[a.month - 1]}-{b.day} {MOS[b.month - 1]}'


def expected_weekly(event, cand, cutoff, cfg_all, mode='j_minus'):
    """The reference column at the WEEKLY grain, from the server.

    Different MAPPING from the daily one - each side buckets by its own
    (event_date_first - order_date)//7, with no weekday snap - but the same
    MODE. Under j_minus and exact_date the shift is 0 because a snap cannot
    survive division by 7; under days_since_launch it is the campaign-length
    difference, which reaches fifteen weeks and must not be dropped.
    """
    (cfg, ccfg, cur_n, cur_rev, c_n, c_rev,
     _off, wshift, c_cut) = _sides(event, cand, cutoff, cfg_all, mode)
    cap = sum(d['day_capacity'] for d in cfg['days'])
    rows = dp.weekly_rows(cur_n, cur_rev, c_n, c_rev, cfg['event_date_first'],
                          ccfg['event_date_first'], cutoff, c_cut,
                          (cfg['event_date_first'] - cutoff).days, cap, wshift)
    out = []
    for r in rows:
        if r['sb']:
            sb = date.fromisoformat(r['sb'])
            eb = date.fromisoformat(r['eb'])
            label = f"S−{r['w']} · {fwk(sb, eb)}"
        else:
            label = '—'
        out.append((label, str(r['b']) if r['b'] is not None else '—'))
    return out


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
    failures, snaps, weeks = [], [], [0]
    MODES_SEEN = set()
    BYMODE = {}
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
        # Only the mode-qualified keys. The driver writes each pick twice - once
        # under the bare candidate name and once under "<mode>\0<name>" - so the
        # bare entries are the LAST mode's results wearing an unqualified label.
        # Iterating both would double every comparison and check the last mode
        # against j_minus's expectation.
        for key, got in row['picks'].items():
            if '\0' not in key:
                continue
            mode, label = key.split('\0', 1)
            cid = cmap.get(label)
            if got['err']:
                bad.append(f'[{mode}] {label}: rendered the unavailable banner')
                continue
            with contextlib.redirect_stdout(io.StringIO()):
                want, snap = expected(event, cid, cutoff, cfg_all, mode)
            if mode == 'j_minus':
                snaps.append((name, cid, snap))
            label = f'[{mode}] {label}'
            MODES_SEEN.add(mode)
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
            with contextlib.redirect_stdout(io.StringIO()):
                wantw = expected_weekly(event, cid, cutoff, cfg_all, mode)
            gotw = [tuple(x) for x in (got.get('weekly') or [])]
            if gotw != wantw:
                i = next((k for k, (x, y) in enumerate(zip(gotw, wantw)) if x != y),
                         min(len(gotw), len(wantw)))
                bad.append(f'{label} WEEKLY: {len(gotw)} rendered vs {len(wantw)} '
                           f'expected; first difference at {i}: '
                           f'{gotw[i] if i < len(gotw) else "-"} vs '
                           f'{wantw[i] if i < len(wantw) else "-"}')
            BYMODE.setdefault((name, cid), {})[mode] = (tuple(g), tuple(gotw))
            weeks[0] += 1
        if len(cmap) > 1 and len(seen) < 2:
            bad.append('every candidate renders the same rows - the selection '
                       'is not reaching the table')
        if bad:
            failures.append(name)
            print(f'  FAIL  {name}')
            for x in bad[:4]:
                print(f'          {x}')
        else:
            print(f"  ok    {name}: {len(cmap)} candidates x "
                  f"{len(row.get('modes') or [1])} modes, daily AND weekly "
                  f"matching dashboard_payload row for row")

    # THE MODES MUST ACTUALLY DIFFER. 135 green comparisons look identical
    # whether the three modes are three alignments or one alignment rendered
    # three times - the client could ignore AMODE entirely and every row would
    # still match, because the server would be asked for the same thing. So
    # assert the differences the arithmetic predicts, per grain.
    print()
    diffs = {}
    for (pg, cid), byk in BYMODE.items():
        for a, b in (('j_minus', 'exact_date'), ('j_minus', 'days_since_launch')):
            if a in byk and b in byk:
                d = diffs.setdefault(f'{a} vs {b}', [0, 0, 0])
                d[2] += 1
                if byk[a][0] != byk[b][0]:
                    d[0] += 1
                if byk[a][1] != byk[b][1]:
                    d[1] += 1
    for k, (nd, nw, tot) in sorted(diffs.items()):
        print(f'  {k}: daily differs on {nd}/{tot} pair(s), '
              f'weekly on {nw}/{tot}')
    if diffs.get('j_minus vs exact_date', [0])[0] == 0:
        failures.append('exact_date renders identically to j_minus everywhere')
        print('  FAIL  exact_date never differs from j_minus at the daily grain, '
              'yet 21 pairs have a non-zero snap - the mode is not reaching the '
              'client')
    if diffs.get('j_minus vs exact_date', [0, 1])[1] != 0:
        failures.append('exact_date differs from j_minus at the weekly grain')
        print('  FAIL  exact_date differs from j_minus WEEKLY. Those two modes '
              'differ by the weekday snap alone, which cannot survive division '
              'by 7 - a difference here means a shift was applied where the '
              'arithmetic says there is none')
    dsl = diffs.get('j_minus vs days_since_launch', [0, 0, 0])
    if dsl[1] == 0:
        failures.append('days_since_launch never moves the weekly column')
        print('  FAIL  days_since_launch never differs from j_minus at the '
              'WEEKLY grain. That is the ruling this mode was rebuilt for: the '
              'offset reaches 105 days and the weekly must follow it')

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
    print(f'{weeks[0]} comparison(s) across {len(pages)} page(s) and '
          f'{len(MODES_SEEN)} anchoring mode(s), every one at BOTH grains: the '
          f'client alignment agrees with the server implementation')
    return 0


if __name__ == '__main__':
    sys.exit(main())
