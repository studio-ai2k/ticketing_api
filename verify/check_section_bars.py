#!/usr/bin/env python3
"""
The section bars, in the SHIPPED pages, at the width they are judged at.

    NODE_PATH=/opt/node22/lib/node_modules python3 verify/check_section_bars.py

WHY THIS EXISTS AND NOT JUST A MEASUREMENT IN THE PROPOSAL
-----------------------------------------------------------
C1/C2 were measured, ruled, built in the mock — and the shipped pages still read
four tabs. `prod_nav_script` had already written down why: *"the nav's MARKUP is
before `</nav>` and its BEHAVIOUR is after, so the seam splits them."* The bar is
both. Its handlers arrive with the mock's region; its buttons live inside `<nav>`
and are production's, emitted by `dashboard_template.html`.

So rebuilding the mock changed every handler and no label, and the page looked
completely fine. Pass 0 now transplants the bar markup — and this asserts the
transplant, because the failure mode is a page that renders perfectly with the
wrong bar.

TWO HALVES, AND THE FIRST IS THE ONE THAT GENERALISES
------------------------------------------------------
  (1) THE SHIPPED BAR EQUALS THE MOCK'S BAR. Not "has six tabs" — equals. A
      count assertion passes against any six tabs, including production's four
      plus two, and the whole defect was a bar that was plausibly right. This
      one fails the day the mock moves and the transplant does not, whatever
      the change was.

  (2) IT FITS AT 393px. Leo's phone, and the width every mobile item on this
      project has been judged at. Ruled option B (`.dt` padding 12→10) was
      chosen over shipping the scroll, so the fit is now a requirement rather
      than a happy result: if a seventh tab is ever added, this is what says so
      before he does.

Width is measured in a real browser rather than estimated, because the labels
are proportional text and the bar is a flex row - the arithmetic that says
"six short labels are narrower than four long ones" was right and was still
worth checking, since it was right by 19px out of 401.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from pages import v2_pages   # noqa: E402 - CUTOVER 6.3, one page list
MOCK = ROOT / 'redesign' / 'mock' / 'dashboard_v3.39.html'
V2 = ROOT / 'v2'
CHROME = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

# The width the redesign's mobile decisions are made at. Not a guess and not the
# narrowest phone in the world: it is the device the rulings have been made on,
# so it is the one a regression has to be caught at.
JUDGED_AT = 393

TABS_RE = re.compile(r'<div class="dept-tabs-bg"[^>]*>.*?</div>\s*</div>', re.DOTALL)

JS = r"""
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROME });
  const out = [];
  for (const url of process.argv.slice(2)) {
    const ctx = await b.newContext({ viewport: { width: +process.env.W, height: 800 } });
    const p = await ctx.newPage();
    await p.goto(url, { waitUntil: 'load' });
    await p.evaluate(() => { const i = document.getElementById('db-pw-input');
      if (i) i.value = 'festipass'; if (typeof dbSubmit === 'function') dbSubmit(); });
    await p.waitForTimeout(300);
    const read = () => {
      const bars = [...document.querySelectorAll('.dept-tabs')];
      const vis = bars.filter(x => getComputedStyle(x).display !== 'none');
      if (vis.length !== 1) return { bars: bars.length, visible: vis.length };
      const t = vis[0], bs = [...t.querySelectorAll('.dt')], cs = getComputedStyle(t);
      return {
        bars: bars.length, visible: 1, which: t.dataset.bar || null,
        labels: bs.map(x => x.textContent.trim()),
        on: bs.filter(x => x.classList.contains('on')).length,
        need: Math.round(bs.reduce((a, x) => a + x.getBoundingClientRect().width, 0)
              + parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight)),
        avail: t.clientWidth,
        missing: bs.map(x => {
          const m = /scrollToSection\('([^']+)'/.exec(x.getAttribute('onclick') || '');
          return (m && document.getElementById(m[1])) ? null : (m ? m[1] : 'no-target');
        }).filter(Boolean),
      };
    };
    const billetterie = await p.evaluate(read);
    await p.evaluate(() => { const b = document.getElementById('btn-details'); if (b) b.click(); });
    await p.waitForTimeout(300);
    const details = await p.evaluate(read);
    out.push({ url, billetterie, details });
    await ctx.close();
  }
  console.log('@@' + JSON.stringify(out));
  await b.close();
})();
"""


def main():
    pages = v2_pages()
    if not pages:
        print('no v2 pages')
        return 1

    fails = []

    # ---- (1) the shipped bar IS the mock's bar ---------------------------
    print('1  the shipped section bars are the mock\'s, byte for byte')
    m = TABS_RE.search(MOCK.read_text(encoding='utf-8'))
    if not m:
        print('  FAIL  the mock has no .dept-tabs-bg block')
        return 1
    want = m.group(0)
    for p in pages:
        got = TABS_RE.search(p.read_text(encoding='utf-8'))
        if not got:
            fails.append(f'{p.name}: no section bar')
            print(f'  FAIL  {p.name}: no .dept-tabs-bg at all')
        elif got.group(0) != want:
            fails.append(f'{p.name}: bar differs from the mock')
            print(f'  FAIL  {p.name}: the shipped bar is not the mock\'s.')
            print(f'        Pass 0 transplants it because the bar is nav markup and')
            print(f'        the seam leaves nav markup behind. A mock change that')
            print(f'        does not reach the page renders as a correct-looking')
            print(f'        page with the wrong labels.')
        else:
            print(f'  ok    {p.name}')

    # (1b) - every candidate group has a heading - LIVED HERE and has moved to
    # verify/check_cand_groups.py. It was written against the page's `gs` title
    # map, which was a real assertion while the CANDS loop iterated a hardcoded
    # ['edition','past']. Once that loop began deriving its groups from the
    # values present in the payload, a static check that the groups have titles
    # could no longer fail - it passed by construction. The replacement drives
    # the menu open and partitions it at its own headings, and adds the
    # direction this one never had: no candidate the series file calls live may
    # be tagged past. Both directions, because a live event under the wrong
    # heading renders as a perfectly plausible menu.

    # ---- (2) both bars behave, and fit, at the judged width --------------
    print(f'\n2  both bars at {JUDGED_AT}px')
    script = Path(tempfile.mkdtemp()) / 'bars.js'
    script.write_text(JS, encoding='utf-8')
    env = {'CHROME': CHROME, 'W': str(JUDGED_AT),
           'NODE_PATH': os.environ.get('NODE_PATH', '/opt/node22/lib/node_modules'),
           'PATH': '/opt/node22/bin:/usr/bin:/bin'}
    res = subprocess.run(['node', str(script)] + [f'file://{p}' for p in pages],
                         capture_output=True, text=True, env=env, timeout=900)
    line = next((x for x in res.stdout.split('\n') if x.startswith('@@')), None)
    if not line:
        print('  FAIL  could not drive the pages')
        print(res.stderr[-1200:])
        return 1

    for row in json.loads(line[2:]):
        name = row['url'].rsplit('/', 1)[-1]
        for page in ('billetterie', 'details'):
            r = row[page]
            tag = f'{name} · {page}'
            if r.get('visible') != 1:
                fails.append(f'{tag}: {r.get("visible")} visible bars')
                print(f'  FAIL  {tag}: {r.get("visible")} bars visible of '
                      f'{r.get("bars")}, want exactly 1')
                continue
            if r.get('which') != page:
                fails.append(f'{tag}: wrong bar shown')
                print(f'  FAIL  {tag}: the visible bar is data-bar='
                      f'{r.get("which")!r}')
            if r['missing']:
                fails.append(f'{tag}: dead targets')
                print(f'  FAIL  {tag}: targets with no element: '
                      f'{", ".join(r["missing"])}')
            if r['on'] != 1:
                fails.append(f'{tag}: {r["on"]} active tabs')
                print(f'  FAIL  {tag}: {r["on"]} tabs marked active, want 1')
            if r['need'] > r['avail']:
                fails.append(f'{tag}: overflows at {JUDGED_AT}px')
                print(f'  FAIL  {tag}: needs {r["need"]}px, has {r["avail"]}. '
                      f'The bar scrolls,')
                print(f'        so the last tab sits under the fade on the phone '
                      f'these are judged on.')
                print(f'        Ruled option B chose the fit over the scroll; a '
                      f'tab added since has spent it.')
            elif not r['missing'] and r['on'] == 1:
                print(f'  ok    {tag}: {len(r["labels"])} tabs, needs '
                      f'{r["need"]}px of {r["avail"]} (+{r["avail"] - r["need"]})')

    print()
    if fails:
        print(f'FAILED: {len(fails)}')
        return 1
    print(f'every shipped bar is the mock\'s and fits at {JUDGED_AT}px')
    return 0


if __name__ == '__main__':
    sys.exit(main())
