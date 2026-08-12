#!/usr/bin/env python3
"""
The comparison menu files every candidate under the right heading.

    NODE_PATH=/opt/node22/lib/node_modules python3 verify/check_cand_groups.py

WHAT WENT WRONG, AND WHY IT NEEDED TWO CHECKS RATHER THAN ONE
--------------------------------------------------------------
`suivi_candidates.py` has emitted three groups since it was written, and
`suivi_selector.GROUP_TITLES` has carried three titles beside it. Two later
places stopped at two:

  the emitter   build_v2 tagged every non-family candidate 'past'
  the client    the mock's CANDS loop read a hardcoded ['edition','past']

Both were sufficient while every candidate was a finished edition. B1 widened
the menu to live editions and neither noticed, so Elektric Park 2026, Genève
2026 and Bordeaux Octobre 2026 - all in progress - were offered under "Autres
éditions passées", and "Événements en cours" became a heading the locked mock
carried but no page could reach.

Fixing one alone achieves nothing, and that is the whole reason this file
exists rather than a single assertion. With only the client fixed there is no
third group in the data to render. With only the emitter fixed the third group
exists and the loop drops it on the floor. So this checks BOTH ENDS:

  (1) the emitter    no candidate the series file calls live is tagged past,
                     and none it calls finished is tagged live
  (2) the client     the menu actually renders one heading per group present,
                     with every candidate under its own group's heading

AND WHY (1) IS ASSERTED AGAINST THE SERIES FILES
-------------------------------------------------
Not against a rule re-derived here. The first draft of the emitter fix computed
liveness as `last_day >= cut`, which reads as obviously right and is not:
`cut` is the PAGE's comparison cut, so liveness became a property of the page
doing the looking. bordeaux_2026 came out 'live' on parisxxl.html and 'past' on
the four other pages that offer it. A check that re-derived the same rule would
have agreed with it. The series file's `live` is one decision made once per
event, by the script that fetched it - so that is the thing to compare to.

A reality anchor guards the degenerate pass: if every series file carried the
same `live` value, direction (1) would hold vacuously and certify nothing. Four
are true and eight are false, and this asserts that both exist. Same lesson as
the live-menu defect that made check_b1_switch report 198/198 over a shipped
bug: a check comparing two implementations needs at least one property pinned
to reality, or it certifies consistency and nothing else.

WHY (2) IS DRIVEN IN A BROWSER
-------------------------------
The client loop now derives its groups from the values present in the payload,
so a STATIC check that the groups have titles cannot fail any more - it passes
by construction. What can still fail is the rendering: the loop breaking, a
group whose items land under the previous heading, a candidate dropped. That is
readable only from the built menu, so this opens it and partitions it at its
own headings.

The failure this catches renders as a perfectly plausible menu. Nothing about
"Genève 2026" under "Autres éditions passées" looks broken; you have to know
the edition is running to see it. That is why it is an assertion and not a
reading.
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
V2 = ROOT / 'v2'
SERIES = ROOT / 'series'
CHROME = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

D_RE = re.compile(r'const D=(\{.*?\});\s*\n', re.DOTALL)

# what a candidate's group may be, given what the series file says
ALLOWED = {True: {'live', 'edition'},      # running: never filed under past
           False: {'past', 'edition'}}     # finished: never filed under live

JS = r"""
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROME });
  const out = [];
  for (const url of process.argv.slice(2)) {
    const ctx = await b.newContext({ viewport: { width: 1280, height: 900 } });
    const p = await ctx.newPage();
    await p.goto(url, { waitUntil: 'load' });
    await p.evaluate(() => { const i = document.getElementById('db-pw-input');
      if (i) i.value = 'festipass'; if (typeof dbSubmit === 'function') dbSubmit(); });
    await p.waitForTimeout(1400);
    const r = await p.evaluate(async () => {
      // Find it by the MENU it owns, not by `.cmp-trigger` - the anchoring
      // mode picker wears the same class, sits next to it in the same
      // `.svctl-p` group, and comes first in the DOM. The first draft of this
      // probe took `.cmp-trigger` and measured the mode menu on all six pages:
      // one heading, "Alignement des deux éditions", reported as six failures
      // of the comparison menu.
      const menu = document.querySelector('.sw-menu[aria-label="Changer de comparaison"]');
      const t = menu && menu.closest('.sw-wrap')
                ? menu.closest('.sw-wrap').querySelector('[data-sw-trigger]') : null;
      if (!t) return { err: 'no comparison trigger on the page' };
      t.scrollIntoView({ block: 'center', behavior: 'instant' });
      await new Promise(r => setTimeout(r, 150));
      t.click();
      await new Promise(r => setTimeout(r, 250));
      const wrap = t.closest('.sw-wrap');
      const m = (wrap && wrap._swMenu) || (wrap && wrap.querySelector('.sw-menu'));
      if (!m || getComputedStyle(m).display === 'none') return { err: 'menu did not open' };
      // Walk the menu IN DOM ORDER. The blocks are flat - a .sw-group heading
      // followed by its .sw-item buttons - so an item's heading is simply the
      // last .sw-group seen before it. This is what makes the check positional
      // rather than a comparison of two title lists.
      const blocks = [];
      for (const el of m.children) {
        if (el.classList.contains('sw-group')) {
          blocks.push({ head: (el.textContent || '').trim(), items: [] });
        } else if (el.classList.contains('sw-item')) {
          const lab = el.querySelector('.sw-label');
          let n = '';
          if (lab) { const c = lab.cloneNode(true);
                     c.querySelectorAll('.sw-sub').forEach(s => s.remove());
                     n = (c.textContent || '').trim(); }
          if (!blocks.length) blocks.push({ head: '(no heading)', items: [] });
          blocks[blocks.length - 1].items.push(n);
        }
      }
      // `typeof D`, not `window.D`. The payload is a top-level `const`, which
      // creates a global LEXICAL binding - reachable by name, absent from
      // `window`. The first draft read `window.D`, got undefined, and reported
      // "0 groups in the payload" on pages carrying eleven candidates.
      const cands = (typeof D !== 'undefined' && D.cands) ? D.cands : null;
      if (!cands) return { err: 'the payload is not reachable from the page' };
      return { blocks, cands: cands.map(c => ({ n: c.n, g: c.g })) };
    });
    out.push({ url, ...r });
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

    live = {}
    for f in sorted(SERIES.glob('*.json')):
        live[f.stem] = bool(json.loads(f.read_text(encoding='utf-8')).get('live'))
    if not live:
        print('FAIL  no series files - nothing to assert liveness against')
        return 1

    fails = []

    # ---- reality anchor --------------------------------------------------
    print('0  the series files distinguish live from finished at all')
    n_live = sum(1 for v in live.values() if v)
    if n_live == 0 or n_live == len(live):
        fails.append('series liveness is constant')
        print(f'  FAIL  all {len(live)} series files say live={n_live > 0}.')
        print('        Direction 1 would hold vacuously against a constant, so')
        print('        it would certify nothing. Either the fetch stopped')
        print('        setting `live` or there is genuinely nothing running -')
        print('        both need a human, not a green check.')
    else:
        print(f'  ok    {n_live} live, {len(live) - n_live} finished, '
              f'{len(live)} series files')

    # ---- (1) the emitter -------------------------------------------------
    print('\n1  no running edition is tagged past, and no finished one live')
    checked = 0
    for p in pages:
        m = D_RE.search(p.read_text(encoding='utf-8'))
        if not m:
            fails.append(f'{p.name}: no payload')
            print(f'  FAIL  {p.name}: no payload to read')
            continue
        D = json.loads(m.group(1))
        bad = []
        for c in D.get('cands', []):
            cid, g = c.get('id'), c.get('g')
            if cid not in live:
                bad.append(f'{cid}: offered in the menu with no series file')
                continue
            checked += 1
            if g not in ALLOWED[live[cid]]:
                bad.append(f'{cid}: series says live={live[cid]}, menu tags it '
                           f'{g!r} (allowed: {sorted(ALLOWED[live[cid]])})')
        if bad:
            fails.append(f'{p.name}: {len(bad)} miscategorised')
            print(f'  FAIL  {p.name}')
            for x in bad[:5]:
                print(f'          {x}')
        else:
            print(f'  ok    {p.name}: {len(D.get("cands", []))} candidate(s)')
    print(f'        {checked} candidate/page pairs checked against the series files')

    # ---- (2) the client --------------------------------------------------
    print('\n2  the rendered menu has one heading per group, each holding its own')
    script = Path(tempfile.mkdtemp()) / 'cands.js'
    script.write_text(JS, encoding='utf-8')
    env = {'CHROME': CHROME,
           'NODE_PATH': os.environ.get('NODE_PATH', '/opt/node22/lib/node_modules'),
           'PATH': '/opt/node22/bin:/usr/bin:/bin'}
    res = subprocess.run(['node', str(script)] + [f'file://{p}' for p in pages],
                         capture_output=True, text=True, env=env, timeout=1800)
    line = next((x for x in res.stdout.split('\n') if x.startswith('@@')), None)
    if not line:
        print('  FAIL  could not drive the pages')
        print(res.stderr[-1500:])
        return 1

    for row in json.loads(line[2:]):
        name = row['url'].rsplit('/', 1)[-1]
        if row.get('err'):
            fails.append(f'{name}: {row["err"]}')
            print(f'  FAIL  {name}: {row["err"]}')
            continue
        byname = {c['n']: c['g'] for c in row.get('cands', [])}
        want = {g for g in byname.values() if g}
        blocks = row.get('blocks', [])
        bad = []

        # a) one heading per group present, no more
        if len(blocks) != len(want):
            bad.append(f'{len(want)} group(s) in the payload {sorted(want)}, '
                       f'{len(blocks)} heading(s) rendered '
                       f'{[b["head"] for b in blocks]}')

        # b) every block is pure - all its items share one group
        seen_groups = set()
        for blk in blocks:
            gs = {byname.get(n) for n in blk['items']}
            if len(gs) > 1:
                bad.append(f'heading {blk["head"]!r} mixes groups {sorted(g or "?" for g in gs)}')
            seen_groups |= {g for g in gs if g}
        missing = sorted(want - seen_groups)
        if missing:
            bad.append(f'groups with no heading of their own: {missing} - their '
                       f'candidates are filed under a neighbour')

        # c) nothing dropped. A group the loop does not know about vanishing
        #    silently is the exact shape of the bug this file is about.
        shown = [n for b in blocks for n in b['items']]
        lost = sorted(set(byname) - set(shown))
        if lost:
            bad.append(f'{len(lost)} candidate(s) in the payload but not in the '
                       f'menu: {lost[:4]}')
        if len(shown) != len(set(shown)):
            bad.append('a candidate is rendered more than once')

        if bad:
            fails.append(f'{name}: menu')
            print(f'  FAIL  {name}')
            for x in bad[:5]:
                print(f'          {x}')
        else:
            print(f'  ok    {name}: {len(blocks)} heading(s) '
                  f'{[b["head"] for b in blocks]}, {len(shown)} candidate(s), '
                  f'each under its own')

    print()
    if fails:
        print(f'FAILED: {len(fails)}')
        print('Both ends have to agree. build_v2 sets c.g from the series file\'s')
        print('own `live`; the mock\'s CANDS loop renders one heading per value')
        print('of c.g present rather than a hardcoded list. Fixing one alone')
        print('leaves either a group with no data or data with no group.')
        return 1
    print('the emitter and the menu agree, and both agree with the series files')
    return 0


if __name__ == '__main__':
    sys.exit(main())
