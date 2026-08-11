#!/usr/bin/env python3
"""
A finished edition says so, and projects nothing.

    NODE_PATH=/opt/node22/lib/node_modules python3 verify/check_finished_edition.py

WHAT WAS ON THE PAGE
--------------------
Two live pages had `D.jx < 0` - bordeaux at -1, parisxxl at -2 - and every
component that derived a label or a rate from it printed nonsense with a
straight face:

  badge            "J−-1"                    and "En vente · J−-1" on Détails
  hero-sub         "vs 2025 au même J−-1"
  Vélocité         "Rythme requis -17 802 / jour"
  Vélocité         "À ce rythme, 26 130 billets le jour J"   (26 698 already sold)
  Projection       "sur -1 jours", "de J−-1 à J−0"
  Projection       "15 390 projetés · 86%"   against 15 416 actual
  Projection       "Rythme requis 0 /j"
  méthodologie     "sur les J−-1 restants"

Eleven readouts, five components. Only four were Projection Finale, which is why
this is a check over the whole page rather than one renderer's unit test.

THE ONE THAT MATTERS MOST IS THE QUIETEST
------------------------------------------
"Rythme requis 0 /j" came from `Math.max(Math.ceil((cap-now)/jx), 0)`. The clamp
was doing its job - it turned a negative into zero - and in doing so it turned a
visibly wrong number into a plausible one. "0 /j" reads as "nothing more needed".
The projection under-shooting actual sales is the same shape: a forecast of
15 390 against 15 416 sold is not obviously broken unless you compare two cards.

So this asserts the ABSENCE of forecast figures on a finished edition, not the
absence of minus signs. A future clamp that hides the sign again would pass a
string check and fail this one.

`<= 0`, NOT `< 0`
-----------------
At `jx === 0` the same division yields Infinity and renders "∞ /j". No page sits
at zero today; every edition passes through it for exactly one day, so the defect
is latent rather than absent. `run.py` has drawn the boundary at `<= 0` since
before the redesign existed ("'Terminé' if days_remaining_display <= 0"), and
that is the boundary used here - the same rule, asserted rather than re-derived.

The redesign's components never inherited it, which produced the tell that
started the audit: parisxxl's nav read "PARIS 130326 · Terminé" - transplanted
production markup - while the badge two inches below read "En vente · J−-2".
One page, two components, opposite answers.

BOTH DIRECTIONS
---------------
A check that only asserts suppression passes if the section renders nothing at
all, on every page. So the live editions are asserted to still carry their
forecast. And a reality anchor: at least one page of each kind must exist, or
one half of this certifies nothing against an empty set.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / 'v2'
CHROME = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
D_RE = re.compile(r'const D=(\{.*?\});\s*\n', re.DOTALL)

# A negative or absent day-count, however it reaches the glass.
BAD_TEXT = [
    (r'J[−-]\s*[−-]\d', 'a negative J−x'),
    (r'sur\s+[−-]\d+\s*jours?', 'a negative day span'),
    (r'[−-]\d+\s*jours?\s+restants?', 'negative days remaining'),
    (r'[−-]\s?\d[\d   ]*\s*/\s*jour', 'a negative daily rate'),
    (r'∞', 'an infinite rate (jx === 0)'),
]

JS = r"""
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROME });
  const out = [];
  for (const url of process.argv.slice(2)) {
    const ctx = await b.newContext({ viewport: { width: 1280, height: 1000 } });
    const p = await ctx.newPage();
    await p.goto(url, { waitUntil: 'load' });
    await p.evaluate(() => { const i = document.getElementById('db-pw-input');
      if (i) i.value = 'festipass'; if (typeof dbSubmit === 'function') dbSubmit(); });
    await p.waitForTimeout(1500);
    const READ = () => {
      const vis = [];
      const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      let n; while ((n = w.nextNode())) {
        const el = n.parentElement;
        if (!el || !el.offsetParent) continue;
        const s = (n.textContent || '').replace(/\s+/g, ' ').trim();
        if (s) vis.push(s);
      }
      return vis;
    };
    const billet = await READ ? await p.evaluate(READ) : [];
    // the projection section's own state, read structurally rather than by text
    const proj = await p.evaluate(() => {
      const s = document.getElementById('proj');
      if (!s) return null;
      return {
        cards: s.querySelectorAll(':scope > .card').length,
        finished: s.querySelectorAll('.empty-t').length,
        // a forecast figure is a scenario pane; none of them survive OVER
        panes: s.querySelectorAll('.pane').length,
        scen: s.querySelectorAll('.scen-b').length,
      };
    });
    await p.evaluate(() => { const b = document.getElementById('btn-details'); if (b) b.click(); });
    await p.waitForTimeout(600);
    const det = await p.evaluate(READ);
    out.push({ url, texts: billet.concat(det), proj });
    await ctx.close();
  }
  console.log('@@' + JSON.stringify(out));
  await b.close();
})();
"""


def main():
    pages = sorted(V2.glob('*.html'))
    if not pages:
        print('no v2 pages')
        return 1

    jx = {}
    for p in pages:
        m = D_RE.search(p.read_text(encoding='utf-8'))
        if not m:
            print(f'FAIL  {p.name}: no payload')
            return 1
        jx[p.name] = json.loads(m.group(1)).get('jx')

    over = [n for n, v in jx.items() if v is not None and v <= 0]
    live = [n for n, v in jx.items() if v is not None and v > 0]

    fails = []
    print('0  both kinds of edition are on the shelf')
    print(f'     finished (jx <= 0): {sorted(over) or "NONE"}')
    print(f'     live     (jx  > 0): {sorted(live) or "NONE"}')
    if not over or not live:
        fails.append('one kind of edition is absent')
        print('  FAIL  half of this check would assert over an empty set. That is')
        print('        not a pass - it is the check going quiet. If every edition')
        print('        has genuinely finished, this needs a human, not a green.')
    else:
        print(f'  ok    {len(over)} finished, {len(live)} live')

    script = Path(tempfile.mkdtemp()) / 'fin.js'
    script.write_text(JS, encoding='utf-8')
    env = {'CHROME': CHROME,
           'NODE_PATH': os.environ.get('NODE_PATH', '/opt/node22/lib/node_modules'),
           'PATH': '/opt/node22/bin:/usr/bin:/bin'}
    res = subprocess.run(['node', str(script)] + [f'file://{p}' for p in pages],
                         capture_output=True, text=True, env=env, timeout=1800)
    line = next((x for x in res.stdout.split('\n') if x.startswith('@@')), None)
    if not line:
        print('FAIL  could not drive the pages')
        print(res.stderr[-1500:])
        return 1
    rows = {r['url'].rsplit('/', 1)[-1]: r for r in json.loads(line[2:])}

    # ---- (1) no page prints a negative or infinite day-count, anywhere -----
    print('\n1  no page prints a negative or infinite day-count')
    for name in sorted(rows):
        hits = []
        for t in rows[name]['texts']:
            for rx, why in BAD_TEXT:
                if re.search(rx, t):
                    hits.append(f'{why}: {t[:90]!r}')
                    break
        if hits:
            fails.append(f'{name}: {len(hits)} bad readout(s)')
            print(f'  FAIL  {name} (jx={jx[name]})')
            for h in hits[:6]:
                print(f'          {h}')
        else:
            print(f'  ok    {name} (jx={jx[name]})')

    # ---- (2) a finished edition projects NOTHING ---------------------------
    print('\n2  a finished edition shows no forecast, and says it is finished')
    for name in sorted(over):
        pr = rows[name]['proj']
        bad = []
        if not pr:
            bad.append('no projection section at all')
        else:
            if pr['panes'] or pr['scen']:
                bad.append(f'{pr["panes"]} scenario pane(s) and {pr["scen"]} '
                           f'toggle(s) still rendered - it is still projecting')
            if pr['finished'] != pr['cards']:
                bad.append(f'{pr["finished"]} of {pr["cards"]} card(s) state the '
                           f'edition is finished')
        if bad:
            fails.append(f'{name}: still projecting')
            print(f'  FAIL  {name} (jx={jx[name]})')
            for x in bad:
                print(f'          {x}')
        else:
            print(f'  ok    {name} (jx={jx[name]}): {pr["cards"]} card(s), no forecast')

    # ---- (3) a live edition STILL projects --------------------------------
    # Without this, suppressing the section on every page would pass (2).
    print('\n3  a live edition still projects')
    for name in sorted(live):
        pr = rows[name]['proj']
        if not pr or not pr['panes'] or not pr['scen']:
            fails.append(f'{name}: forecast missing')
            print(f'  FAIL  {name} (jx={jx[name]}): the forecast is gone from a '
                  f'live edition - the guard is too wide')
        else:
            print(f'  ok    {name} (jx={jx[name]}): {pr["panes"]} pane(s), '
                  f'{pr["scen"]} toggle(s)')

    print()
    if fails:
        print(f'FAILED: {len(fails)}')
        print('The boundary is `jx <= 0`, matching run.py. Past the event there is')
        print('nothing to project onto; at exactly 0 the rate divides by zero.')
        return 1
    print(f'{len(over)} finished and {len(live)} live edition(s): each says which '
          f'it is, and only the live ones forecast')
    return 0


if __name__ == '__main__':
    sys.exit(main())
