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

P4 — THE TRIPWIRE, EXPECTED TO FAIL ON PURPOSE
----------------------------------------------
Today the comparison menu is still built from the PROJECTION rule. That is
deliberate and temporary: `suivi_candidates` rules that a live candidate must
be anchored on LAUNCH rather than on its event date, because an event-date
anchor maps a live edition's recent rows into its own future. Until that
anchoring mode ships, a live candidate would be pickable and silently wrong.

So P4 pins the current narrowness. When the launch mode lands and the menu
widens, P4 fails — by design, and with the reason printed next to it. It is not
a claim that the menu SHOULD be narrow; it is a claim that the menu is narrow
FOR A REASON THAT IS WRITTEN DOWN, and that removing the narrowness has to be
an act rather than a drift.

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

    # ---- P4: the tripwire -------------------------------------------------
    print('\nP4  the menu is still the PROJECTION rule (temporary, on purpose)')
    for name, D in pages():
        from datetime import date, timedelta
        cut = date.fromisoformat(D['ev']) - timedelta(days=D['jx'])
        want = {c for c in build_series.projection_eligible(cfg_all, cut)
                if c != D['id']} & on_disk
        got = {c['id'] for c in D.get('cands', [])}
        if got == want:
            print(f'  ok    {name}  menu == projection rule ({len(got)})')
        else:
            fails.append(f'{name}: menu has widened past the projection rule')
            print(f'  FAIL  {name}  menu != projection rule')
            print(f'        extra: {sorted(got - want) or "-"}   '
                  f'absent: {sorted(want - got) or "-"}')
            print('        IF THE LAUNCH ANCHORING MODE HAS JUST LANDED, THIS')
            print('        IS THE EXPECTED FAILURE. The menu was narrowed to')
            print('        the projection rule only because a live candidate')
            print('        had no correct anchor. Once it does, widen the menu')
            print('        to comparison_eligible and retire P4 with a note')
            print('        saying which mode retired it.')

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
