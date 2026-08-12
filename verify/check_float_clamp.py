#!/usr/bin/env python3
"""
Every floating box positioned from an anchor stays inside the viewport.

    NODE_PATH=/opt/node22/lib/node_modules python3 verify/check_float_clamp.py

WHY, AND WHY IT IS A CHECK RATHER THAN THREE FIXES
---------------------------------------------------
Third viewport-edge defect on this project:

  C7    the projection readout, clipped at the card edge
  C3    the `.info` tooltip, `left:50%; translateX(-50%)` on a 15px glyph
  this  `.sw-menu`, `placeFloat` setting --sw-left from the trigger and nothing
        else — 4 of 10 menus off-screen at 393px, measured

All three positioned a floating box from an ANCHOR and trusted the anchor to be
far enough from the edge. The general form is worth more than the three fixes:

  **any element positioned from an anchor rather than from the viewport needs a
  clamp, and the absence is invisible until the anchor is near an edge.**

Invisible is the operative word. Every one of these rendered perfectly at desktop
width and on the pages someone happened to open. This check opens them.

WHAT IT DRIVES, AND WHY THE WIDTH IS READ
------------------------------------------
Every `[data-sw-trigger]` on the page — the nav session switcher, the comparison
picker, the projection picker, the anchoring mode picker. Four call sites through
one function, which is why the fix went in `placeFloat` and not in the picker
that surfaced it: the NAV SWITCHER was off-screen too, and a fix in the picker
would have left three.

The menu is portalled to `<body>` and `position:fixed`, so its rect is already in
viewport coordinates. Its width is READ from the rect rather than taken from
`min-width:230px` — content can exceed the minimum, and a clamp computed from the
constant would pass this check and still clip.

The menu is found via `wrap._swMenu`, the property `openWrap` sets, rather than
by querying for a visible `.sw-menu`. An earlier version of this probe took the
first visible menu it found and reported the SAME box five times — five identical
`left`/`right` readings that looked like five passes.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from pages import v2_pages   # noqa: E402 - CUTOVER 6.3, one page list
CHROME = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
WIDTHS = (393, 360, 320)
MARGIN = 1          # a pixel of tolerance for sub-pixel layout

JS = r"""
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROME });
  const out = [];
  for (const spec of process.argv.slice(2)) {
    const [url, vw] = spec.split('|');
    const ctx = await b.newContext({ viewport: { width: +vw, height: 900 } });
    const p = await ctx.newPage();
    await p.goto(url, { waitUntil: 'load' });
    await p.evaluate(() => { const i = document.getElementById('db-pw-input');
      if (i) i.value = 'festipass'; if (typeof dbSubmit === 'function') dbSubmit(); });
    await p.waitForTimeout(1400);
    const n = await p.evaluate(() => document.querySelectorAll('[data-sw-trigger]').length);
    const rows = [];
    for (let i = 0; i < n; i++) {
      rows.push(await p.evaluate(async (idx) => {
        if (window.swCloseAll) window.swCloseAll();
        await new Promise(r => setTimeout(r, 80));
        const t = document.querySelectorAll('[data-sw-trigger]')[idx];
        const wrap = t.closest('.sw-wrap');
        // SCROLL IT INTO VIEW FIRST. placeFloat reads a VIEWPORT-relative rect,
        // so a trigger below the fold puts the menu below the fold with it -
        // and the first version of this probe reported that as 18 failures.
        // A reader cannot click a control they cannot see; scrolling to it is
        // part of reproducing the situation, not part of working around it.
        // behavior:'instant'. `html{scroll-behavior:smooth}` makes a plain
        // scrollIntoView an ANIMATION, so the rect is still the pre-scroll one
        // when the click lands - the trigger reads y=4275 in a 900px viewport
        // and every menu looks off-screen. Same trap the D6 nav-sticky
        // assertion recorded, hit again here by the probe rather than the page.
        t.scrollIntoView({ block: 'center', behavior: 'instant' });
        await new Promise(r => setTimeout(r, 150));
        t.click();
        await new Promise(r => setTimeout(r, 220));
        // the menu THIS wrap owns, wherever openWrap portalled it to
        const m = (wrap && wrap._swMenu) || (wrap && wrap.querySelector('.sw-menu'));
        if (!m || getComputedStyle(m).display === 'none') return { skip: true };
        const b = m.getBoundingClientRect();
        return { label: (t.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 24),
                 l: Math.round(b.left), r: Math.round(b.right),
                 top: Math.round(b.top), bot: Math.round(b.bottom),
                 w: Math.round(b.width),
                 vw: document.documentElement.clientWidth,
                 vh: document.documentElement.clientHeight };
      }, i));
    }
    out.push({ url, vw: +vw, rows: rows.filter(r => r && !r.skip) });
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
    script = Path(tempfile.mkdtemp()) / 'float.js'
    script.write_text(JS, encoding='utf-8')
    specs = [f'file://{p}|{w}' for p in pages for w in WIDTHS]
    env = {'CHROME': CHROME,
           'NODE_PATH': os.environ.get('NODE_PATH', '/opt/node22/lib/node_modules'),
           'PATH': '/opt/node22/bin:/usr/bin:/bin'}
    res = subprocess.run(['node', str(script)] + specs,
                         capture_output=True, text=True, env=env, timeout=1800)
    line = next((x for x in res.stdout.split('\n') if x.startswith('@@')), None)
    if not line:
        print('FAIL  could not drive the pages')
        print(res.stderr[-1500:])
        return 1

    fails, total = [], 0
    for row in json.loads(line[2:]):
        name = row['url'].rsplit('/', 1)[-1]
        bad = []
        if not row['rows']:
            bad.append('no menu opened at all - the probe found no trigger, or '
                       'openWrap stopped portalling')
        for r in row['rows']:
            total += 1
            if r['l'] < -MARGIN or r['r'] > r['vw'] + MARGIN:
                bad.append(f'{r["label"]!r}: left {r["l"]}, right {r["r"]} '
                           f'against viewport {r["vw"]} (menu {r["w"]}px wide)')
            elif r['top'] < -MARGIN or r['bot'] > r['vh'] + MARGIN:
                bad.append(f'{r["label"]!r}: top {r["top"]}, bottom {r["bot"]} '
                           f'against viewport height {r["vh"]}')
        if bad:
            fails.append(f'{name}@{row["vw"]}')
            print(f'  FAIL  {name} at {row["vw"]}px')
            for x in bad[:4]:
                print(f'          {x}')
        else:
            print(f'  ok    {name} at {row["vw"]}px: {len(row["rows"])} menu(s) inside')

    print()
    if fails:
        print(f'FAILED: {len(fails)}')
        print('A menu positioned from its trigger has run off the screen. The')
        print('clamp lives in postprocess_html.placeFloat and serves every')
        print('[data-sw-trigger] on the page - fix it there, not in one picker.')
        return 1
    print(f'{total} opened menu(s) across {len(pages)} page(s) x {len(WIDTHS)} '
          f'widths, all inside the viewport')
    return 0


if __name__ == '__main__':
    sys.exit(main())
