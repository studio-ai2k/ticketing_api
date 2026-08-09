#!/usr/bin/env python3
"""
The v2 pages must DO the things the mock does, not merely contain them.

    NODE_PATH=/opt/node22/lib/node_modules python3 verify/check_v2_behaviour.py

WHY THIS EXISTS
---------------
Leo's review found six bugs. Four were one root cause and none of them were
visible in the markup: the template was byte-identical to the mock, every
assertion passed, and the page was wrong anyway.

  A0  the payload carried no forward-looking data. `fut` was false on every
      row of every page, so the "À venir" block, the "Précédent" block and
      BOTH separators were skipped - four missing features, one missing flag.
  A3  the projection scenarios were a two-point flat line, identical to each
      other, so the toggle swapped panes correctly and showed the same picture.
  A4  the projection selector had one candidate, because one was ever built.
  A5  `window.swCloseAll` went with the nav block that was replaced, and both
      call sites are guarded - so the dropdown stopped closing on select and
      nothing errored.
  A6  the gate is a fixed overlay over a document that still scrolled.

Every one of those is a page that renders cleanly while doing the wrong thing,
which is the failure mode this repo keeps meeting (traps #10-#13). So these
assertions are made against a REAL BROWSER with the payload the page ships, not
against the file.

The specific coverage gap this closes: the fixture and the §7 target figures
are all as-of-today numbers, so an assertion set built from them passes
against a payload with no future data at all. `fut` and the two scenarios have
to be asserted directly or nothing notices.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHROME = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

D_RE = re.compile(r'const D=(\{.*?\});\s*\n', re.DOTALL)
LG_RE = re.compile(r'const LG\s*=\s*(\{.*?\});\s*\n', re.DOTALL)


def payload_problems(path):
    """The payload half. Asserted against the FILE, deliberately.

    `const D` is script-scoped, so the browser cannot read it - and that is the
    right split anyway: this half says the data is there, the browser half says
    the page used it. Either alone can pass while the page is wrong.
    """
    src = path.read_text(encoding='utf-8')
    m = D_RE.search(src)
    if not m:
        return ['no `const D={…}` payload in the page'], {'live': False}
    D = json.loads(m.group(1))
    out = []
    # A finished event has no future, and demanding one of it would be the
    # inverse mistake: an assertion that cannot hold, disabled by whoever meets
    # it first. Everything forward-looking below is gated on D.jx > 0.
    live = D.get('jx', 0) > 0
    info = {'live': live, 'jx': D.get('jx')}

    daily, weekly = D.get('daily') or [], D.get('weekly') or []
    today = [r for r in daily if r['jx'] == D['jx']]
    if len(today) != 1:
        out.append(f"A0 {len(today)} daily row(s) match jx === D.jx (want 1). The "
                   f"row scale is anchored on the cutoff, not on the event, so "
                   f"there is no 'Aujourd'hui' and nothing is ever future")
    if live:
        if not any(r['fut'] for r in daily):
            out.append(f"A0 none of {len(daily)} daily rows carries fut:true")
        if weekly and not any(r['fut'] for r in weekly):
            out.append(f"A0 none of {len(weekly)} weekly rows carries fut:true")
        if daily and min(r['jx'] for r in daily) != 0:
            out.append(f"A0 the daily rows stop at J−{min(r['jx'] for r in daily)}, "
                       f"not at the event")

    # D0: the card and the chart must be the same quantity. The card showed
    # window TOTALS with "/jour" after them, beside "Rythme requis", which is a
    # true daily rate - so 1 350 sat next to 346 and read as four times the
    # pace needed when the truth was 56% of it. Same shape as p1 == p2: two
    # figures that must share a scale, with nothing asserting it.
    #
    # Derived from the chart's own cumulative series, which was right all along.
    cum = {p['jx']: p['v'] for p in (D.get('cumA') or [])}
    for w, got in sorted((D.get('cur') or {}).get('vel', {}).items()):
        if not cum:
            break
        want = (cum.get(D['jx'], 0) - cum.get(D['jx'] + int(w), 0)) / int(w)
        if abs(got - want) > 0.05:
            out.append(f"D0 vel[{w}] is {got}, but the chart's cumulative gives "
                       f"{want:.1f}/day over the same window. The card and the "
                       f"chart are not the same quantity")

    px = D.get('projx') or {}
    cands = px.get('cands') or {}
    if len(cands) < 2:
        out.append(f"A4 projx.cands has {len(cands)} candidate(s) - the menu is "
                   f"a dropdown over a single entry")
    cand = cands.get(px.get('default')) or {}
    for day in (cand.get('days') or []) if live else []:
        ch = day.get('chart')
        if not ch or not ch.get('p1'):
            continue
        if ch['p1'] == ch['p2']:
            out.append(f"A3 {day['day']}: the two scenarios are identical")
        if len(ch['p1']) < 3:
            out.append(f"A3 {day['day']}: p1 has {len(ch['p1'])} point(s) - a flat "
                       f"segment, not a curve")

    lg = LG_RE.search(src)
    if lg:
        lg_days = set(json.loads(lg.group(1)))
        mine = set(px.get('curdays') or [])
        if mine and not lg_days <= mine:
            out.append(f"LG carries {sorted(lg_days - mine)}, which this event does "
                       f"not have - it is another edition's payload, verbatim")
    return out, info

JS = r"""
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROME });
  const out = [];
  for (const f of process.argv.slice(2)) {
    const ctx = await b.newContext({ viewport: { width: 1100, height: 900 } });
    const p = await ctx.newPage();
    const errs = [];
    p.on('pageerror', e => errs.push(String(e).slice(0, 160)));
    await p.goto('file://' + f, { waitUntil: 'load' });
    await p.waitForTimeout(400);

    // A6 - the gate is up and the document must not scroll behind it.
    const gated = await p.evaluate(() => {
      const o = document.querySelector('.db-overlay');
      const before = window.scrollY;
      window.scrollTo(0, 4000);
      const moved = window.scrollY !== before;
      window.scrollTo(0, before);
      return {
        overlayUp: !!o && getComputedStyle(o).display !== 'none',
        htmlOverflow: getComputedStyle(document.documentElement).overflow,
        scrolled: moved,
      };
    });

    // Past the gate, the way a reader gets past it.
    await p.evaluate(() => {
      const i = document.getElementById('db-pw-input');
      if (i) { i.value = 'festipass'; }
      if (typeof dbSubmit === 'function') dbSubmit();
    });
    await p.waitForTimeout(500);

    // Everything below is about what RENDERS. `const D` is script-scoped and
    // deliberately not reachable from here - the payload is asserted in Python,
    // against the file, and this half asserts the page built from it. Reading
    // the payload here would let a correct payload vouch for a page that never
    // used it, which is the whole class of failure being chased.
    const r = await p.evaluate(() => {
      // A3: the two scenario panes of one card must not draw the same curve.
      // The projected series is the dashed path in each pane.
      const scen = [];
      document.querySelectorAll('[data-proj]').forEach(card => {
        const panes = [...card.querySelectorAll('.pane')].map(pane => {
          const d = [...pane.querySelectorAll('path[stroke-dasharray="5 4"]')]
            .map(x => x.getAttribute('d')).join('|');
          return d;
        });
        const pts = (panes[0] || '').split(/[ML]/).length - 1;
        scen.push({ id: card.dataset.proj, same: panes.length === 2 && panes[0] === panes[1],
                    drawn: panes.filter(Boolean).length, pts });
      });
      return {
        // innerText would be empty here: Suivi lives on a page that is
        // display:none until you navigate to it. These are the elements the
        // blocks are MADE of, which is also a sharper assertion than the words.
        hasAvenir: !!document.getElementById('b-fut'),
        hasPrecedent: !!document.getElementById('b-past')
                   && !!document.getElementById('sep-past'),
        cuts: document.querySelectorAll('#suivi .cut, #sep-past .cut').length,
        scen,
        projItems: (() => {
          const t = [...document.querySelectorAll('.cmp-trigger')].find(
            x => (x.querySelector('.cmp-eyebrow') || {}).textContent === 'réf.');
          const wrap = t && t.closest('.sw-wrap');
          return wrap ? wrap.querySelectorAll('.sw-item').length : 0;
        })(),
        hasCloseAll: typeof window.swCloseAll === 'function',
        // SHAPE, not a blacklist. "593 421 €593k" contains no NaN, no
        // undefined and no stray ${ - it is a well-formed string that every
        // existing assertion had an opinion about only by accident. A tick or
        // a hover value is ONE number, optionally one magnitude suffix and one
        // currency symbol. Two numbers in one label is the defect.
        badTicks: (() => {
          const out = [];
          const seen = new Set();
          const test = s => {
            if (!s || seen.has(s)) return;
            seen.add(s);
            // thousands separators join their digits; everything else splits
            const n = s.replace(/(\d)[\u202f\u00a0 ](?=\d)/g, '$1');
            const runs = n.match(/[\d]+(?:[.,]\d+)?/g) || [];
            const syms = (n.match(/€/g) || []).length;
            if (runs.length > 1 || syms > 1) out.push(s);
          };
          document.querySelectorAll('.ck text').forEach(e => test(e.textContent.trim()));
          document.querySelectorAll('.ck [data-va]').forEach(e => {
            test(e.getAttribute('data-va')); test(e.getAttribute('data-vb'));
          });
          return out.slice(0, 4);
        })(),

        htmlOverflowAfter: getComputedStyle(document.documentElement).overflow,
      };
    });

    // D6 - the nav must STICK, not merely carry position:sticky. The rule was
    // present and correct in both sheets and inert in both, because
    // body{overflow-x:hidden} made body a scroll container. Reading the rule
    // tells you it is right; only scrolling tells you it is not.
    //
    // Measured across an await, not inside one evaluate: html carries
    // scroll-behavior:smooth, so scrollTo ANIMATES and a same-tick read gets
    // the pre-scroll position - which passed on a nav that does not stick.
    await p.evaluate(() => window.scrollTo({ top: 1500, behavior: 'instant' }));
    await p.waitForTimeout(250);
    const navTop = await p.evaluate(() => {
      const n = document.querySelector('.nav');
      return n ? Math.round(n.getBoundingClientRect().top) : null;
    });
    await p.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    await p.waitForTimeout(150);

    // A5 for real: open the comparison menu, click an item, is it closed?
    const menu = await p.evaluate(async () => {
      const trig = document.querySelector('.cmp-trigger[data-sw-trigger]');
      if (!trig) return { ran: false };
      trig.click();
      await new Promise(r => setTimeout(r, 150));
      const opened = !!document.querySelector('.sw-wrap.open');
      const item = document.querySelector('.sw-wrap.open .sw-item:not(.active)')
                || document.querySelector('.sw-menu.sw-float .sw-item:not(.active)');
      if (item) item.click();
      await new Promise(r => setTimeout(r, 200));
      return { ran: true, opened, closed: !document.querySelector('.sw-wrap.open') };
    });

    out.push({ file: f.split('/').pop(), gated, ...r, navTop, menu, errors: errs });
    await ctx.close();
  }
  console.log('@@' + JSON.stringify(out));
  await b.close();
})();
"""


def main(argv):
    targets = [str(Path(t).resolve()) for t in argv] or \
        sorted(str(p) for p in (ROOT / 'v2').glob('*.html'))
    if not targets:
        print('no v2 pages found - nothing to check')
        return 0
    script = ROOT / '.check_v2_behaviour.js'
    script.write_text(JS, encoding='utf-8')
    try:
        env = {'CHROME': CHROME, 'NODE_PATH': '/opt/node22/lib/node_modules',
               'PATH': '/opt/node22/bin:/usr/bin:/bin'}
        res = subprocess.run(['node', str(script)] + targets,
                             capture_output=True, text=True, env=env, timeout=420)
    finally:
        script.unlink(missing_ok=True)
    if res.returncode != 0:
        print('FAIL: could not render the pages')
        print(res.stderr[-1200:])
        return 1

    line = next((l for l in res.stdout.split('\n') if l.startswith('@@')), None)
    if not line:
        print('FAIL: no result line')
        print(res.stdout[-800:])
        return 1
    rows = json.loads(line[2:])

    failures = []
    for r in rows:
        why, info = payload_problems(ROOT / 'v2' / r['file'])
        live = info['live']
        g = r['gated']
        if g['overlayUp'] and g['scrolled']:
            why.append('A6 the page scrolls behind the gate')
        if g['overlayUp'] and g['htmlOverflow'] != 'hidden':
            why.append(f"A6 html overflow is {g['htmlOverflow']!r} while gated")
        if r['htmlOverflowAfter'] == 'hidden':
            why.append('A6 scroll is still locked AFTER unlocking - worse than the bug')

        if live and not r['hasAvenir']:
            why.append('A1 no "À venir" block: #b-fut is absent, so the future '
                       'rows and their separator never render')
        if not r['hasPrecedent']:
            why.append('A2 no "Précédent" block: #b-past / #sep-past are absent')

        same = [s['id'] for s in r['scen'] if s['same']] if live else []
        flat = ([s['id'] for s in r['scen'] if s['drawn'] and s['pts'] < 3]
                if live else [])
        if same:
            why.append(f"A3 the two scenario panes draw the same curve on "
                       f"card(s) {', '.join(same)}")
        if flat:
            why.append(f"A3 the projected curve is a {r['scen'][0]['pts']}-point "
                       f"line on card(s) {', '.join(flat)}")
        if r['projItems'] < 2:
            why.append(f"A4 the projection selector renders {r['projItems']} item(s)")
        if r['cuts'] < (2 if live else 1):
            why.append(f"A2 {r['cuts']} separator(s) in Suivi")
        if r['navTop'] is not None and abs(r['navTop']) > 2:
            why.append(f"D6 the nav is at {r['navTop']}px after scrolling - it "
                       f"carries position:sticky and does not stick. Check what "
                       f"made an ancestor a scroll container")
        if r['badTicks']:
            why.append('a chart label carries two numbers: '
                       + ', '.join(repr(x) for x in r['badTicks'])
                       + '. A tick is one value, one optional magnitude suffix, '
                         'one currency symbol')
        if not r['hasCloseAll']:
            why.append('A5 window.swCloseAll is not defined - menus never close on select')
        if r['menu'].get('ran') and r['menu'].get('opened') and not r['menu'].get('closed'):
            why.append('A5 the comparison menu stayed open after a selection')

        if r['errors']:
            why.append(f"{len(r['errors'])} pageerror(s): {r['errors'][0]}")

        if why:
            failures.append((r['file'], why))
            print(f"  FAIL  {r['file']}")
            for w in why:
                print(f'          {w}')
        else:
            print(f"  ok    {r['file']}: À venir + Précédent · "
                  f"{r['projItems']} candidates · scenarios differ · "
                  f"menus close · gate locks scroll")

    print()
    if failures:
        print(f'FAILED: {len(failures)} page(s)')
        print('These are behaviours, not markup. A page can contain every element')
        print('the mock contains and still do none of this.')
        return 1
    print(f'all {len(rows)} v2 page(s) behave')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
