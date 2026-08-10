#!/usr/bin/env python3
"""
The two eligibility rules, asserted in both directions.

    python verify/check_eligibility.py

WHY THERE ARE TWO RULES
-----------------------
One rule served three consumers — this repo's series files, the projection
candidate set, and B1's comparison menu — and that single rule made emitting a
series for a LIVE edition impossible without also offering that edition as a
projection source, where it cannot work. A projection replays a reference's
REMAINING curve; a live edition has not run one yet. So:

  projection_eligible  finished, and with data.  The original rule, keeping the
                       original name because the projection is what it was
                       always right for.
  comparison_eligible  any edition with data.    Strictly wider.

BOTH DIRECTIONS, AND WHY EACH IS A DIFFERENT KIND OF WRONG
----------------------------------------------------------
A one-directional check on a pair of nested sets is nearly free to satisfy and
catches almost nothing — `projection ⊆ comparison` is true of the empty set.
The two failures are not symmetric, so they are asserted separately:

  P1  NO LIVE EDITION IN THE PROJECTION MENU.  The dangerous direction. A live
      candidate in the projection selector renders a curve; it does not error.
      Its "remaining" shape is the part of its campaign that has not happened,
      so the projection is a replay of nothing, drawn as an ordinary line.
      Asserted against the SHIPPED PAGE, not the rule — `D.projx.cands` is the
      artefact a reader picks from, and it is what the rule is for.

  P2  EVERY EDITION WITH A FILE IS COMPARISON-ELIGIBLE.  The quiet direction. A
      series file on disk that no rule admits is a fetchable URL nobody can
      reach through the UI: wasted build time, and a menu that is narrower than
      the data without anyone deciding it should be.

  P3  THE MENU IS A SUBSET OF THE COMPARISON RULE, AND EVERY ENTRY HAS A FILE.
      Holds today and must keep holding after the widening. An entry the reader
      can pick but not fetch is the exact failure Option 2 was priced to avoid.

P4 — THE TRIPWIRE FIRED, AND `days_since_launch` IS WHAT RETIRED IT
-------------------------------------------------------------------
P4 used to pin the menu to the PROJECTION rule, because a live candidate had no
anchor that made it meaningful: an event-date anchor maps a live edition's recent
rows into its own future. It was written to fail the day that stopped being true.

**It fired.** `days_since_launch` shipped, checked at both grains and at 135/135,
and the menu widened to `comparison_eligible` — so a live edition can be compared
against another live one, which is what the anchoring work was for.

P4 is REPLACED rather than deleted: the slot now asserts the menu IS the
comparison rule, which is the invariant the widening created, and reports how
many of each menu's candidates are live. A tripwire removed with no successor
looks like a check someone got tired of.

One prediction worth recording as WRONG: the earlier negative test expected P3 to
fail alongside P4 with "no file: geneve_2026". It does not. Live editions got
series files when `comparison_eligible` started driving the EMITTER, two commits
before it drove the menu — so by the time the tripwire fired, the files it would
have complained about were already there.

WHAT THIS CHECK EXCLUDES
------------------------
#18's question, pointed at itself: the page half reads `v2/*.html`. Production
pages have no candidate menu at all, so they are out of scope by construction
rather than by omission. If a production page ever grows one, this check does
not cover it and its PAGES tuple has to grow.
"""

import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))

import run  # noqa: E402
import build_series  # noqa: E402

D_RE = re.compile(r'const D=(\{.*?\});\s*\n', re.DOTALL)
V2_DIR = ROOT / 'v2'
SERIES_DIR = ROOT / 'series'


def pages():
    for p in sorted(V2_DIR.glob('*.html')):
        m = D_RE.search(p.read_text(encoding='utf-8'))
        if m:
            yield p.name, json.loads(m.group(1))


def main():
    cfg_all = run.load_event_config(str(ROOT / 'event_config.csv'))
    comparison = set(build_series.comparison_eligible(cfg_all))
    on_disk = {f.stem for f in SERIES_DIR.glob('*.json')}

    last_day = {cid: max(d['day_date'] for d in cfg['days'])
                for cid, cfg in cfg_all.items() if cfg.get('days')}

    fails = []
    seen = 0

    # ---- P1: no live edition in the projection menu -----------------------
    # The page's own cutoff, derived from the page: today's row is J-jx, so
    # cutoff = ev - jx. Nothing is passed in, so this cannot be checked against
    # a date the page was not built at.
    print('P1  no live edition in any projection menu')
    for name, D in pages():
        seen += 1
        from datetime import date, timedelta
        cut = date.fromisoformat(D['ev']) - timedelta(days=D['jx'])
        live = [c for c in D['projx']['cands']
                if c in last_day and last_day[c] >= cut]
        unknown = [c for c in D['projx']['cands'] if c not in last_day]
        if live:
            fails.append(f'{name}: projection offers LIVE {", ".join(live)}')
            print(f'  FAIL  {name}  (cutoff {cut}) live: {", ".join(live)}')
        elif unknown:
            fails.append(f'{name}: projection offers unconfigured '
                         f'{", ".join(unknown)}')
            print(f'  FAIL  {name}  not in config: {", ".join(unknown)}')
        else:
            print(f'  ok    {name}  (cutoff {cut}) '
                  f'{len(D["projx"]["cands"])} candidate(s), all finished')
    if not seen:
        print('  FAIL  no v2 page carried a payload')
        fails.append('no v2 pages')

    # ---- P2: every edition with a file is comparison-eligible -------------
    print('\nP2  every series file on disk is comparison-eligible')
    orphans = sorted(on_disk - comparison)
    if orphans:
        fails.append(f'series files no rule admits: {", ".join(orphans)}')
        print(f'  FAIL  {len(orphans)} file(s) no rule admits: '
              f'{", ".join(orphans)}')
        print('        Built, published, and unreachable from any menu.')
    else:
        print(f'  ok    {len(on_disk)} file(s), all admitted by '
              f'comparison_eligible')

    # ---- P3: the menu is inside the rule, and every entry is fetchable ----
    print('\nP3  every menu entry is comparison-eligible and has a file')
    for name, D in pages():
        ids = [c['id'] for c in D.get('cands', [])]
        outside = [c for c in ids if c not in comparison]
        missing = [c for c in ids if c not in on_disk]
        if outside or missing:
            fails.append(f'{name}: menu outside={outside} missing={missing}')
            print(f'  FAIL  {name}  outside the rule: {outside or "-"}  '
                  f'no file: {missing or "-"}')
        else:
            print(f'  ok    {name}  {len(ids)} entr(y/ies)')

    # ---- P4: the menu IS the comparison rule (the tripwire, fired) --------
    # Was "the menu is still the PROJECTION rule". `days_since_launch` retired
    # that, so the slot asserts the invariant the widening created rather than
    # being deleted - a tripwire removed with no successor looks like a check
    # someone got tired of.
    print('\nP4  the menu IS the comparison rule (widened by days_since_launch)')
    for name, D in pages():
        cut = date.fromisoformat(D['ev']) - timedelta(days=D['jx'])
        want = {c for c in comparison if c != D['id']} & on_disk
        got = {c['id'] for c in D.get('cands', [])}
        live = {c for c in got if c in last_day and last_day[c] >= cut}
        if got == want:
            print(f'  ok    {name}  {len(got)} candidate(s), {len(live)} live')
        else:
            fails.append(f'{name}: menu is not the comparison rule')
            print(f'  FAIL  {name}  menu != comparison rule')
            print(f'        extra: {sorted(got - want) or "-"}   '
                  f'absent: {sorted(want - got) or "-"}')
            print('        A candidate in the rule with no file cannot be')
            print('        fetched; one outside the rule should not be offered.')
    if not any(c in last_day and last_day[c] >= date.today()
               for _n, D in pages() for c in {x['id'] for x in D.get('cands', [])}):
        fails.append('no live candidate in any menu')
        print('  FAIL  not one menu offers a LIVE edition, which is the whole')
        print('        point of the widening - the rule moved and the data did not')

    print()
    if fails:
        print(f'FAILED: {len(fails)}')
        for f in fails:
            print(f'  - {f}')
        return 1
    print('all four directions hold')
    return 0


if __name__ == '__main__':
    sys.exit(main())
