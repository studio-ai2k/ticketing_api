#!/usr/bin/env python3
"""
C3: every section has exactly one heading row, inside its card, AFTER the
renderers run — and no section-level subtext survives outside a tooltip.

    NODE_PATH=/opt/node22/lib/node_modules python3 verify/check_section_heads.py

WHY BOTH HALVES, AND WHY "AFTER THE RENDERERS"
-----------------------------------------------
The first attempt at C3 moved the heads in the MARKUP. Every card on this page
has its `innerHTML` replaced at runtime, so the renderers wiped them — and the
page rendered perfectly, with no headings at all. Trap #20 in a lifecycle rather
than a position: build-time markup and runtime markup are two halves, and the
half that loses is the one nobody looks at, because nothing errors.

So this drives a browser. A static read of the file would pass on a page whose
headings never survive to a reader.

The second half is not decoration. "Exactly one heading row" passes on a card
whose subtext never moved — the note would simply still be sitting there beside
the title, which is the arrangement C3 replaced. Both directions, or neither.

THE SELECTOR IS THE WHOLE DIFFICULTY
------------------------------------
`.sec-note` is NOT only the section subtext. The renderers use the same class
inside card CONTENT — four of them in `sec-presence` alone, and one in
`sec-velocite`, `sec-donnees` and others. An assertion written as "no `.sec-note`
anywhere" fails on cards that are entirely correct.

Scoped to `.sec-head > .sec-note`: the section-level one, in the row it used to
live in. That is #18's question answered in advance — this check excludes
`.sec-note` inside card bodies, and that exclusion is a decision, stated here.

SCOPE
-----
NO EXEMPTIONS. `sec-projection` used to hold the only one: it was not a card at
all, being `#projctl` + `#proj` + a trailing `#logique` card, and the note here
said to delete the exemption when C4 landed rather than widen the selector
around it. C4/E landed and it was deleted. The section leads with a header card
that carries the title, its tooltip and the three controls, and it passes the
same assertion as the other nine.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / 'v2'
CHROME = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

# EMPTY, and deliberately. `sec-projection` was the one section that was not
# a card at all - `#projctl` + `#proj` + a trailing `#logique` card - and it
# was exempt BY NAME with the instruction to DELETE the exemption when C4
# landed rather than widen the selector around it. C4/E landed: the section
# now leads with a header card carrying the title, the tooltip and all three
# controls, so it satisfies the same rule as the other nine with nothing
# special written for it. An exemption that outlives its cause becomes a rule
# nobody can explain - which is why `EXEMPT_PAGES` below is empty too.
EXEMPT = set()
NO_TOOLTIP = {'sec-velocite'}        # has no note; ruled to gain no copy.

# No page exemptions. `page-campagne` used to need one: an empty-state
# placeholder for a page nothing navigates to, nested inside `page-details` by an
# unclosed </div> in the LOCKED mock, so it rendered at the foot of the Détails
# page. Ruled OUT of v2 rather than fixed - a correctly-scoped page nothing
# navigates to is dead markup with a longer life expectancy.
#
# The exemption goes with it. An exemption that exists because of a defect must
# not outlive the defect, or it becomes a rule nobody can explain.
EXEMPT_PAGES = set()

JS = r"""
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROME });
  const out = [];
  for (const url of process.argv.slice(2)) {
    const ctx = await b.newContext({ viewport: { width: 1200, height: 900 } });
    const p = await ctx.newPage();
    const errs = [];
    p.on('pageerror', e => errs.push(String(e).slice(0, 180)));
    await p.goto(url, { waitUntil: 'load' });
    await p.evaluate(() => { const i = document.getElementById('db-pw-input');
      if (i) i.value = 'festipass'; if (typeof dbSubmit === 'function') dbSubmit(); });
    await p.waitForTimeout(1500);
    // Runs INSIDE the page. Declared as a string so the same body serves both
    // pages without a second copy drifting from the first.
    const READ = () => [...document.querySelectorAll('.page.on .sec')].map(s => ({
      id: s.id || '(none)',
      page: (s.closest('.page') || {}).id || '(no page)',
      heads: s.querySelectorAll('.sec-head').length,
      headsInCard: s.querySelectorAll(':scope > .card .sec-head').length,
      // THE SCOPED SELECTOR. Not `.sec-note` — the renderers use that class
      // inside card content and those are correct.
      strayNote: s.querySelectorAll('.sec-head > .sec-note').length,
      tip: s.querySelectorAll('.sec-head .info').length,
      title: (() => { const t = s.querySelector('.sec-head .sec-title');
        return t && t.childNodes[0] ? t.childNodes[0].textContent.trim() : ''; })(),
    }));
    const rows = await p.evaluate(READ);
    await p.evaluate(() => { const b = document.getElementById('btn-details'); if (b) b.click(); });
    await p.waitForTimeout(600);
    rows.push(...await p.evaluate(READ));
    out.push({ url, rows, errs });
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
    script = Path(tempfile.mkdtemp()) / 'heads.js'
    script.write_text(JS, encoding='utf-8')
    env = {'CHROME': CHROME,
           'NODE_PATH': os.environ.get('NODE_PATH', '/opt/node22/lib/node_modules'),
           'PATH': '/opt/node22/bin:/usr/bin:/bin'}
    res = subprocess.run(['node', str(script)] + [f'file://{p}' for p in pages],
                         capture_output=True, text=True, env=env, timeout=900)
    line = next((x for x in res.stdout.split('\n') if x.startswith('@@')), None)
    if not line:
        print('FAIL  could not drive the pages')
        print(res.stderr[-1500:])
        return 1

    fails = []
    for row in json.loads(line[2:]):
        name = row['url'].rsplit('/', 1)[-1]
        bad = []
        if row['errs']:
            bad.append(f'page error: {row["errs"][0]}')
        seen = set()
        for s in row['rows']:
            sid = s['id']
            if sid in seen:
                continue
            seen.add(sid)
            if sid in EXEMPT or s.get('page') in EXEMPT_PAGES:
                continue
            if s['heads'] != 1:
                bad.append(f'{sid}: {s["heads"]} heading rows, want 1')
                continue
            if s['headsInCard'] != 1:
                bad.append(f'{sid}: its heading row is not inside the card - '
                           f'a renderer wiped it or never emitted it')
            if s['strayNote']:
                bad.append(f'{sid}: {s["strayNote"]} section-level .sec-note '
                           f'still beside the title; the subtext belongs in the '
                           f'tooltip')
            want_tip = 0 if sid in NO_TOOLTIP else 1
            if s['tip'] != want_tip:
                bad.append(f'{sid}: {s["tip"]} tooltip(s), want {want_tip}')
            if not s['title']:
                bad.append(f'{sid}: heading row has no title')
        if bad:
            fails.append(name)
            print(f'  FAIL  {name}')
            for x in bad[:5]:
                print(f'          {x}')
        else:
            n = len([s for s in row['rows']
                     if s['id'] not in EXEMPT and s.get('page') not in EXEMPT_PAGES])
            print(f'  ok    {name}: {n} section(s), one heading row each, in '
                  f'their card, no stray subtext')

    print()
    if fails:
        print(f'FAILED: {len(fails)} page(s)')
        return 1
    print(f'all {len(pages)} page(s): every section heads its own card, and the '
          f'subtext lives in the tooltip')
    return 0


if __name__ == '__main__':
    sys.exit(main())
