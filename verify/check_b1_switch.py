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

NEGATIVE TEST for the diff-absence assertion (CHECKLIST step 2)
--------------------------------------------------------------
Restoring `dif` in the mock to the null-coercing `r => r.a - r.b` and rebuilding
makes this fail, exit 1:

    [j_minus] Elektric Park 2023: 1 row(s) with no counterpart render a Diff
              anyway, e.g. "+134" against an em-dash
    [j_minus] Bordeaux Juin 2026: 2 row(s) ... e.g. "+175"

Restoring the fix clears every one of them. Both halves were run scoped to
epk.html alone — the other five pages moved aside — because the whole-set
assertions (64/66 daily and weekly) are properties of all six pages and cannot
hold on one. That scoping is stated rather than hidden: under it the mode
difference reports 11/11 of 11 and fails, which is the check being right about
a set it was not given.
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
from pages import pass0_pages, pass0_dir   # noqa: E402 - CUTOVER 6.3, one page list
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))
CHROME = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

import run  # noqa: E402
import dashboard_payload as dp  # noqa: E402
import build_series  # noqa: E402

# DERIVED, NOT LISTED. This was a hardcoded six-entry dict, and it went stale
# the moment a seventh event was added: `PAGE_EVENT.get('sonora_impact.html')`
# returned None and the check died with
#     KeyError: None   at  cfg, ccfg = cfg_all[event], cfg_all[cand]
# after passing all six pages it did know about. A crash rather than a reported
# failure, so it read as "the check is broken" rather than "the check has never
# heard of this page" - and it would have read the same way for every event
# added from now on.
#
# `rebuild_pages.page_map` is already the definition of "output filename ->
# event id", built from event_config's active rows. Reusing it means this check
# cannot fall behind the config, and a page with no owning event now raises
# where it is read rather than resolving to None and travelling.
import rebuild_pages  # noqa: E402

PAGE_EVENT = rebuild_pages.page_map(Path(run.__file__).resolve().parent /
                                    'event_config.csv')

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
          const df = r.querySelector('.sv-c .sv-df');
          return [d ? d.textContent.trim() : '', txt === '—' ? '—' : num(txt),
                  df ? df.textContent.trim() : null];
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
          err: (document.querySelector('#suivi .empty-t') || {}).textContent || null,
          rows: rows.map(r => {
            const l = r.querySelector('.sv-l');
            if (!l) return null;
            const d = l.querySelector('.sv-d'), n = l.querySelector('.sv-n');
            const nn = n ? n.cloneNode(true) : null;
            if (nn) nn.querySelectorAll('span').forEach(s => s.remove());
            const txt = nn ? nn.textContent.trim() : '';
            const df = r.querySelector('.sv-c .sv-df');
            return [d ? d.textContent.trim() : '', txt === '—' ? '—' : num(txt),
                    df ? df.textContent.trim() : null];
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
    align = dp.anchor(mode, cfg['event_date_first'],
                      ccfg['event_date_first'], cur_lead, c_lead)
    # The same-point cut is RAW in every mode - run.py's two filters, neither
    # snapped. `exact_date` used to share j_minus's cut on the reasoning that
    # they differ by the snap alone, which the cut never had. They no longer do:
    # the same point in a calendar comparison is the reference's counterpart of
    # our cutoff DATE, so it takes its own cut, mirroring dashboard_payload.
    if mode == 'days_since_launch':
        cut_rows = run.filter_tickets_to_same_point_dsl(
            _rows, cutoff,
            cfg['event_date_first'] - timedelta(days=cur_lead),
            ccfg['event_date_first'] - timedelta(days=c_lead))
    elif mode == 'exact_date':
        _m = align.ref_date(cutoff)
        cut_rows = [r for r in _rows if r['order_date'] <= _m]
    else:
        cut_rows = run.filter_tickets_to_same_point(
            _rows, cutoff, cfg['event_date_first'], ccfg['event_date_first'])
    c_cut = max((r['order_date'] for r in cut_rows), default=None)
    return cfg, ccfg, cur_n, cur_rev, c_n, c_rev, align, c_cut


def expected(event, cand, cutoff, cfg_all, mode='j_minus'):
    """The reference column, from the server-side implementation."""
    (cfg, ccfg, cur_n, cur_rev, c_n, c_rev,
     align, c_cut) = _sides(event, cand, cutoff, cfg_all, mode)
    first = min(cur_n) if cur_n else cutoff
    rows = dp.daily_rows(cur_n, cur_rev, c_n, c_rev, cutoff, first, align, c_cut,
                         cfg['event_date_first'], ccfg['event_date_first'],
                         max(c_n) if c_n else None)
    # EVERY row, with the same em-dash sentinel the template now renders for
    # a missing counterpart. Filtering the blanks out of one side and not the
    # other is how the first version of this compared 155 rows against 157 and
    # reported a difference that was its own.
    pairs = [(fday(date.fromisoformat(r['db'])) if r['db'] else '—',
              str(r['b']) if r['b'] is not None else '—')
             for r in rows]
    snap = signed_mod7((cfg['event_date_first'] - ccfg['event_date_first']).days)
    return pairs, snap, rows, (max(c_n) if c_n else None)


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
     align, c_cut) = _sides(event, cand, cutoff, cfg_all, mode)
    cap = sum(d['day_capacity'] for d in cfg['days'])
    rows = dp.weekly_rows(cur_n, cur_rev, c_n, c_rev, cfg['event_date_first'],
                          ccfg['event_date_first'], cutoff, c_cut,
                          (cfg['event_date_first'] - cutoff).days, cap, align)
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
    pages = pass0_pages()
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
            # The URL path is DERIVED from where the page actually is, relative
            # to the directory being served. A literal `/v2/` here was a THIRD
            # hardcoded location in this file, after the payload read and the
            # dead `V2` constant - and it is the one that survived fixing the
            # other two, because `pass0_dir()` made the payload read correct
            # while the browser kept fetching a path that no longer exists.
            # Post-cutover it 404s: "could not drive the pages", then node dies
            # on `pickMode is not defined` because the 404 body has no page in
            # it. Loud, but it names the symptom and not the cause.
            [f'http://127.0.0.1:{port}/{p.relative_to(ROOT).as_posix()}'
             for p in pages],
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
    # `live` as the CLIENT sees it: the series file's own flag, which is what
    # the live-edition sentence branches on.
    SERIES_LIVE = {}
    for f in (ROOT / 'series').glob('*.json'):
        SERIES_LIVE[f.stem] = json.loads(f.read_text(encoding='utf-8')).get('live')
    failures, snaps, weeks, empties = [], [], [0], [0]
    MODES_SEEN = set()
    BYMODE = {}
    import io
    import contextlib
    for row in json.loads(line[2:]):
        name = row['url'].rsplit('/', 1)[-1]
        event = PAGE_EVENT.get(name)
        # pass0_dir(), not a literal `v2/`. The browser half above already
        # drives whatever pass0_pages() resolves, so a hardcoded payload read
        # meant the two halves could address DIFFERENT FILES the moment the
        # pages moved - and post-cutover it is a FileNotFoundError rather than
        # a disagreement, which is the only reason it was not worse.
        src = (pass0_dir() / name).read_text(encoding='utf-8')
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
            if got['err'] and 'indisponible' in got['err']:
                bad.append(f'[{mode}] {label}: rendered the unavailable banner')
                continue
            with contextlib.redirect_stdout(io.StringIO()):
                want, snap, srv_rows, c_last = expected(event, cid, cutoff,
                                                        cfg_all, mode)
            # THE NO-OVERLAP EMPTY STATE, HELD TO THE SERVER'S OWN ANSWER.
            # Reachable only under `exact_date`, where two campaigns lined up by
            # calendar date can miss each other entirely. It must appear when
            # the server finds no matched row and must NOT appear when it finds
            # one - a banner that says "aucune date commune" over a table that
            # has rows is worse than either failure alone, and a table of
            # em-dashes with no banner is the plausible-empty-table shape this
            # project keeps finding.
            # RULED: the banner fires on what the READER CAN SEE, so the
            # expectation is the VISIBLE window, not the whole table. Those are
            # different conditions and the difference is the point - rennes vs
            # bordeaux_2026 has twelve matched rows, every one behind "Voir les
            # 60 jours precedents", so a whole-table rule leaves the visible
            # em-dashes unexplained. The window is the renderer's own split:
            # not fut, and jx <= D.jx + 8.
            #
            # SUPPRESSED where the live-edition sentence already explains the
            # same em-dashes. Two rules correct alone are wrong where they meet.
            vis = [r for r in srv_rows
                   if not r['fut'] and r['jx'] <= D['jx'] + 8]
            # j_minus ONLY. The live sentence also shows under exact_date,
            # where its reason - the candidate's J-x not having arrived - is
            # not why a CALENDAR alignment misses, so the banner stays there.
            live_noted = bool(SERIES_LIVE.get(cid)) and mode == 'j_minus'
            # Launch alignment is out of scope: blank rows at the bottom are
            # what that mode DOES, and its own sentence says so. 18 of the 45
            # pairs the first version fired on were launch, every one correct.
            if mode == 'days_since_launch':
                live_noted = True
            want_banner = (not any(r['b'] is not None for r in vis)
                           and not live_noted)
            shown = bool(got['err'] and 'commune' in got['err'])
            if shown != want_banner:
                bad.append(
                    f'[{mode}] {label}: the no-overlap banner is '
                    f'{"shown" if shown else "absent"} but the visible window '
                    f'has {"no" if not any(r["b"] is not None for r in vis) else "a"} '
                    f'matched row (live-edition note '
                    f'{"showing" if live_noted else "not showing"})')
            elif shown:
                empties[0] += 1
            if mode == 'j_minus':
                snaps.append((name, cid, snap))
            label = f'[{mode}] {label}'
            MODES_SEEN.add(mode)
            cells = [tuple(x) for x in got['rows']]
            g = [c[:2] for c in cells]
            w = list(want)
            # NO COUNTERPART, NO DIFF - asserted on the RENDERED cell.
            # `r.a - r.b` coerced null to 0, so a row with no reference showed
            # a green "+134": a number that looks like a comparison and is a
            # restatement of one side. The arithmetic was internally consistent,
            # which is why an assertion of the form "diff == right - left"
            # passes it - 0 is a legal value for the reference. So this asserts
            # ABSENCE where the operand is absent, not correctness of the
            # subtraction. Third instance of null coercing to zero in a rendered
            # figure on this project; the other two were ruled fixes.
            stray_diff = [c for c in cells if c[0] == '—' and c[1] == '—'
                          and c[2] not in (None, '—')]
            if stray_diff:
                bad.append(
                    f'{label}: {len(stray_diff)} row(s) with no counterpart '
                    f'render a Diff anyway, e.g. "{stray_diff[0][2]}" against '
                    f'an em-dash - that is one side restated, not a comparison')
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
            wcells = [tuple(x) for x in (got.get('weekly') or [])]
            gotw = [c[:2] for c in wcells]
            stray_w = [c for c in wcells if c[0] == '—' and c[1] == '—'
                       and c[2] not in (None, '—')]
            if stray_w:
                bad.append(f'{label} WEEKLY: {len(stray_w)} row(s) with no '
                           f'counterpart render a Diff anyway, e.g. '
                           f'"{stray_w[0][2]}"')
            if gotw != wantw:
                i = next((k for k, (x, y) in enumerate(zip(gotw, wantw)) if x != y),
                         min(len(gotw), len(wantw)))
                bad.append(f'{label} WEEKLY: {len(gotw)} rendered vs {len(wantw)} '
                           f'expected; first difference at {i}: '
                           f'{gotw[i] if i < len(gotw) else "-"} vs '
                           f'{wantw[i] if i < len(wantw) else "-"}')
            BYMODE.setdefault((name, cid), {})[mode] = (tuple(g), tuple(gotw))
            # ABSENCE, NOT ZERO - and an agreement check cannot see it, because
            # client and server shared the error. Past the candidate's last day
            # WITH DATA the reference column must be null: `ref_n.get(m, 0)` and
            # `day[jr] || 0` cannot tell "quiet day" from "day that has not
            # happened for them". Inert for a finished edition.
            if c_last is not None:
                stray = [r for r in srv_rows
                         if r.get('fut') and r.get('b') is not None
                         and r.get('db') and date.fromisoformat(r['db']) > c_last]
                if stray:
                    bad.append(f'{label}: {len(stray)} future row(s) carry a '
                               f'NUMBER past {cid} own last data day {c_last} - '
                               f'0 is a claim, absence is the truth')
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
    # ---- exact_date, RE-DERIVED FROM THE CALENDAR RULE -------------------
    # These two numbers used to be 21/45 daily and 0/45 weekly. BOTH were
    # properties of the BROKEN mode: 21 was the non-zero-snap count, because
    # `exact_date` was j_minus with the snap turned off, and 0 was what you get
    # when the weekly shift is zero on both sides. They could not have been
    # adjusted into correctness - the rule underneath them changed.
    #
    # Derived independently from the four formulas, before this check was run:
    #
    #   daily   a pair differs unless the calendar drift Y equals the weekday
    #           snap smod7(G) on every row of the pair
    #   weekly  a pair differs unless Y is a multiple of 7
    #
    # over all 66 reachable page x candidate pairs that gives 64 daily and 64
    # weekly. The two that do not differ are the pairs whose drift happens to
    # coincide with their snap. Predicted 64/64; observed below.
    XD, XW = 64, 64
    xd, xw, xt = diffs.get('j_minus vs exact_date', [0, 0, 0])
    if (xd, xw) != (XD, XW):
        failures.append(f'exact_date differs on {xd}/{xw}, want {XD}/{XW}')
        print(f'  FAIL  exact_date vs j_minus differs on {xd} daily and {xw} '
              f'weekly of {xt} pair(s);')
        print(f'        the calendar rule predicts {XD} and {XW}.')
        print('        DO NOT edit these two numbers to match. They are derived '
              'from the')
        print('        four formulas, and a number nudged until the check goes '
              'green is')
        print('        exactly what let the broken mode ship green for weeks.')
    else:
        print(f'  ok    exact_date differs from j_minus on {xd}/{xt} daily and '
              f'{xw}/{xt} weekly, as the calendar drift predicts')
    if empties[0]:
        print(f'  ok    the no-overlap empty state agreed with the server on '
              f'{empties[0]} pair(s) where the two campaigns share no date')
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
