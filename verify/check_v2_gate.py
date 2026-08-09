#!/usr/bin/env python3
"""
A v2 page must not be readable without authentication.

    NODE_PATH=/opt/node22/lib/node_modules python3 verify/check_v2_gate.py v2/*.html

WHY
---
v2 shipped with the password modal rendering as unstyled text at the top of the
page and the whole dashboard visible beneath it. Internal revenue data on a
public URL, for as long as it was live.

The cause was one absent rule. Pass 0 keeps the overlay markup — it sits before
`<nav>`, outside the replaced region — but the redesign stylesheet had no
`.db-overlay` rule at all, so nothing produced the fixed full-screen backdrop.
The markup was there. The JS was there. Only the CSS that makes it *cover*
anything was missing.

**Nothing errored and nothing looked wrong.** Every §7 assertion passed on that
page: no NaN, no undefined, no console error, no horizontal scroll. Trap #12 in
the one place where the wrong answer is a data leak — and trap #13's other half,
because a check suite that is all green while the gate is open is worse than no
suite.

WHAT IT ASSERTS
---------------
Loaded with NO auth token, on a real browser:

  1. an element matching `.db-overlay` exists, and
  2. it is `position: fixed`, covers the viewport, and is opaque enough to
     hide what is behind it, and
  3. the dashboard's own text is NOT reachable — no revenue figure, no ticket
     count, nothing from the page body is readable by a script that ignores the
     overlay the way a curious reader would with devtools open... which it can
     always do. So the real assertion is (3') the body's rendered text does not
     contain the dashboard's numbers ABOVE the overlay in paint order.

Point 3 is worth being honest about: this gate is client-side only, on a public
repo, with the password in plaintext. It stops a casual reader, not an
adversary. That was already true of production and is Leo's deferred decision —
see HANDOFF. What this check enforces is that v2 is no *weaker* than production,
which is a real property and the one that broke.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHROME = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

JS = r"""
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROME });
  const out = [];
  for (const f of process.argv.slice(2)) {
    const p = await b.newPage({ viewport: { width: 1100, height: 900 } });
    // NO auth token is set. This is a first-time visitor.
    await p.goto('file://' + f, { waitUntil: 'load' });
    await p.waitForTimeout(400);
    const r = await p.evaluate(() => {
      const o = document.querySelector('.db-overlay');
      if (!o) return { file: '', overlay: false };
      const cs = getComputedStyle(o), rc = o.getBoundingClientRect();
      // What can a reader actually see? Sample the point at the centre of the
      // viewport and ask which element paints there.
      const top = document.elementFromPoint(window.innerWidth / 2, window.innerHeight / 2);
      const covered = !!(top && (top === o || o.contains(top)));
      return {
        overlay: true,
        position: cs.position,
        display: cs.display,
        zIndex: cs.zIndex,
        opaque: cs.backgroundColor !== 'rgba(0, 0, 0, 0)' || cs.backgroundImage !== 'none',
        coversViewport: rc.width >= window.innerWidth - 1 && rc.height >= window.innerHeight - 1,
        centreCovered: covered,
        topTag: top ? (top.className || top.tagName).toString().slice(0, 60) : null,
      };
    });
    out.push({ file: f.split('/').pop(), ...r });
    await p.close();
  }
  console.log(JSON.stringify(out));
  await b.close();
})();
"""


def main(argv):
    targets = [str(Path(t).resolve()) for t in argv] or \
        sorted(str(p) for p in (ROOT / 'v2').glob('*.html'))
    if not targets:
        print('no v2 pages found - nothing to check')
        print('(that is a pass only because nothing is published)')
        return 0
    script = ROOT / '.check_v2_gate.js'
    script.write_text(JS, encoding='utf-8')
    try:
        env = {'CHROME': CHROME, 'NODE_PATH': '/opt/node22/lib/node_modules',
               'PATH': '/opt/node22/bin:/usr/bin:/bin'}
        res = subprocess.run(['node', str(script)] + targets,
                             capture_output=True, text=True, env=env, timeout=180)
    finally:
        script.unlink(missing_ok=True)
    if res.returncode != 0:
        print('FAIL: could not render the pages')
        print(res.stderr[-600:])
        return 1

    rows = json.loads(res.stdout.strip().split('\n')[-1])
    failures = []
    for r in rows:
        why = []
        if not r.get('overlay'):
            why.append('no .db-overlay element')
        else:
            if r['position'] != 'fixed':
                why.append(f"position:{r['position']} (want fixed)")
            if r['display'] == 'none':
                why.append('display:none')
            if not r['coversViewport']:
                why.append('does not cover the viewport')
            if not r['opaque']:
                why.append('transparent - the page shows through')
            if not r['centreCovered']:
                why.append(f"page centre paints {r['topTag']!r}, not the overlay")
        if why:
            failures.append((r['file'], why))
            print(f"  FAIL  {r['file']}: " + '; '.join(why))
        else:
            print(f"  ok    {r['file']}: gated (fixed, opaque, covers, paints on top)")

    print()
    if failures:
        print(f'FAILED: {len(failures)} page(s) READABLE WITHOUT AUTH.')
        print('Do not publish v2/ until this passes. Internal revenue data on a')
        print('public URL is not a rendering bug.')
        return 1
    print(f'all {len(rows)} v2 page(s) gated')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
