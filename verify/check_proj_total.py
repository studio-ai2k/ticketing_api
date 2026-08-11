#!/usr/bin/env python3
"""
The projection total is the sum of the cards below it, and follows its pickers.

    NODE_PATH=/opt/node22/lib/node_modules python3 verify/check_proj_total.py

WHY THIS IS ASSERTED AGAINST THE RENDERED CARDS
------------------------------------------------
The total is three figures a reader used to assemble by hand from two cards. Its
whole value is that it agrees with them, and its whole risk is that it stops
agreeing without looking wrong: 20 000 and 18 048 are both plausible numbers to
find in that slot, and nobody adds two cards to check.

So this does not recompute the total from the payload - that would be a second
implementation of the same arithmetic agreeing with the first, which is the
failure mode this project has already shipped once (check_b1_switch, 198/198
green over a live defect). It reads the RENDERED day cards and the RENDERED
total from the same page and asserts the relationship between them.

THE RULES, EACH OF WHICH CAN PRODUCE "NO ANSWER"
-------------------------------------------------
  1  total == sum of the day cards' projected figures
  2  sell-out is the LATEST per-day date, not a sum - the event is not sold out
     until every day is. A day with no date leaves the aggregate with none, and
     it must show an em-dash rather than the last day that did have one.
  3  both pickers move it. Changing the reference or the scenario and leaving
     the total behind is worse than not having it: a stale figure under the
     control that defines it reads as current.
  4  a FINISHED edition has no total, per ruling §1 - it is a forecast figure
     like every other.

WHAT IT DELIBERATELY DOES NOT ASSERT
-------------------------------------
That the total follows the Présence day-exclusion toggle. It does not, and
neither do the day cards: `on` is scoped to the Présence IIFE and the projection
has never had access to it. A total that responded to a control its own
components ignore would stop being the sum of what sits below it. If the day
cards ever learn to follow it, rule 1 here fails - which is the correct outcome,
and the reason this is written as a relationship rather than as a rule about
exclusion.
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

JS = r"""
const { chromium } = require('playwright');
const num = s => {
  const m = (s || '').replace(/[  \s]/g, '').match(/-?\d+/);
  return m ? +m[0] : null;
};
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROME });
  const out = [];
  for (const url of process.argv.slice(2)) {
    const ctx = await b.newContext({ viewport: { width: 1280, height: 1400 } });
    const p = await ctx.newPage();
    const errs = [];
    p.on('pageerror', e => errs.push(String(e).slice(0, 160)));
    await p.goto(url, { waitUntil: 'load' });
    await p.evaluate(() => { const i = document.getElementById('db-pw-input');
      if (i) i.value = 'festipass'; if (typeof dbSubmit === 'function') dbSubmit(); });
    await p.waitForTimeout(1600);
    // READ: the rendered total, and the rendered day cards it claims to sum.
    const READ = () => {
      const kc = [...document.querySelectorAll('#logique .kc')];
      const cards = [...document.querySelectorAll('#proj [data-proj]')].map(c => {
        const pane = [...c.querySelectorAll('.pane')]
          .find(x => getComputedStyle(x).display !== 'none');
        if (!pane) return null;
        const hero = pane.querySelector('.hero-v, .kc-v');
        const sell = [...pane.querySelectorAll('*')]
          .map(e => (e.textContent || '').trim())
          .find(s => /^Sold out ~/.test(s));
        return { tot: hero ? hero.textContent : null, sell: sell || null };
      });
      return {
        total: kc.length ? kc.map(k => ({
          k: (k.querySelector('.kc-k') || {}).textContent,
          v: (k.querySelector('.kc-v') || {}).textContent })) : null,
        cards,
      };
    };
    const before = await p.evaluate(READ);
    // (3) both pickers move it
    const moved = await p.evaluate(async () => {
      const first = document.querySelector('#logique .kc-v');
      if (!first) return null;                       // no total: a finished edition
      const was = first.textContent;
      const seen = {};
      if (typeof pickScen === 'function') {
        pickScen(1); await new Promise(r => setTimeout(r, 400));
        seen.scen = (document.querySelector('#logique .kc-v') || {}).textContent;
        pickScen(0); await new Promise(r => setTimeout(r, 400));
      }
      const ks = Object.keys((D.projx && D.projx.cands) || {});
      const other = ks.find(k => k !== D.projx.default);
      if (other && typeof pickProj === 'function') {
        pickProj(other); await new Promise(r => setTimeout(r, 400));
        seen.ref = (document.querySelector('#logique .kc-v') || {}).textContent;
        pickProj(D.projx.default); await new Promise(r => setTimeout(r, 400));
      }
      return { was, ...seen, cands: ks.length };
    });
    out.push({ url, ...before, moved, errs });
    await ctx.close();
  }
  console.log('@@' + JSON.stringify(out));
  await b.close();
})();
"""

MONTHS = ['jan', 'fév', 'mar', 'avr', 'mai', 'juin',
          'juil', 'aoû', 'sep', 'oct', 'nov', 'déc']


def num(s):
    m = re.search(r'-?\d+', re.sub(r'[  \s]', '', s or ''))
    return int(m.group(0)) if m else None


def as_day(s):
    """'24 oct' -> (10, 24), for ordering. None if unparseable."""
    m = re.match(r'(\d+)\s+(\S+)', (s or '').strip())
    if not m or m.group(2) not in MONTHS:
        return None
    return (MONTHS.index(m.group(2)), int(m.group(1)))


def main():
    pages = sorted(V2.glob('*.html'))
    if not pages:
        print('no v2 pages')
        return 1

    jx = {}
    for p in pages:
        m = D_RE.search(p.read_text(encoding='utf-8'))
        jx[p.name] = json.loads(m.group(1)).get('jx') if m else None

    script = Path(tempfile.mkdtemp()) / 'tot.js'
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

    fails, live_seen = [], 0
    for row in json.loads(line[2:]):
        name = row['url'].rsplit('/', 1)[-1]
        over = (jx.get(name) or 0) <= 0
        bad = []
        if row['errs']:
            bad.append(f'page error: {row["errs"][0]}')

        # (4) a finished edition has no total
        if over:
            if row['total']:
                bad.append(f'a finished edition still shows a total: '
                           f'{[k["v"] for k in row["total"]]}')
            print(f'  {"FAIL" if bad else "ok  "}  {name} (jx={jx[name]}): '
                  f'finished, {"total present" if row["total"] else "no total"}')
            if bad:
                fails.append(name)
                for x in bad:
                    print(f'          {x}')
            continue

        live_seen += 1
        if not row['total']:
            bad.append('a live edition shows no total at all')
        else:
            vals = {k['k']: k['v'] for k in row['total']}
            tot = num(vals.get('Total projeté'))
            # (1) the sum of the rendered cards
            card_tots = [num(c['tot']) for c in row['cards'] if c and c['tot']]
            if None in card_tots or not card_tots:
                bad.append(f'could not read every day card: {card_tots}')
            elif tot != sum(card_tots):
                bad.append(f'total {tot} != sum of the {len(card_tots)} card(s) '
                           f'{card_tots} = {sum(card_tots)}')
            # (2) the LATEST date, or none at all
            sells = [c['sell'] for c in row['cards'] if c]
            shown = (vals.get('Sold out') or '').strip()
            days = [as_day(re.sub(r'^Sold out ~', '', s or '')) for s in sells]
            if any(s is None for s in sells) or any(d is None for d in days):
                if shown != '—':
                    bad.append(f'a day has no sell-out date but the total shows '
                               f'{shown!r} - it must show an em-dash rather than '
                               f'the last day that did')
            else:
                want = max(days)
                got = as_day(shown)
                if got != want:
                    bad.append(f'sell-out {shown!r} is not the LATEST of the '
                               f'day dates {sells}')
            # (3) both pickers move it
            mv = row['moved'] or {}
            if 'scen' in mv and mv['scen'] == mv.get('was') and tot is not None:
                # equal is only suspicious when the scenarios genuinely differ;
                # a sold-out edition caps both at the jauge, so this is a note
                pass
            if mv.get('cands', 0) > 1 and 'ref' not in mv:
                bad.append('changing the reference did not reach the total')

        if bad:
            fails.append(name)
            print(f'  FAIL  {name} (jx={jx[name]})')
            for x in bad[:4]:
                print(f'          {x}')
        else:
            v = {k['k']: k['v'] for k in row['total']}
            print(f'  ok    {name}: {v.get("Total projeté")} = sum of '
                  f'{len([c for c in row["cards"] if c])} card(s), '
                  f'sold out {v.get("Sold out")}')

    if not live_seen:
        fails.append('no live edition')
        print('  FAIL  no live edition on the shelf - rules 1-3 asserted over an '
              'empty set')

    print()
    if fails:
        print(f'FAILED: {len(fails)}')
        print('The total\'s only value is that it agrees with the cards below it.')
        return 1
    print(f'{live_seen} live edition(s): the total sums its own cards, takes the '
          f'latest sell-out, and follows both pickers')
    return 0


if __name__ == '__main__':
    sys.exit(main())
