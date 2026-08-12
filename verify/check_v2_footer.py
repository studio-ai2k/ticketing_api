#!/usr/bin/env python3
"""
Every v2 page has production's footer, and it is still stampable and still fresh.

    python3 verify/check_v2_footer.py

WHAT WAS WRONG, AND WHY THE DIAGNOSIS WAS WORSE THAN THE BUG
--------------------------------------------------------------
We believed for weeks that a stray `</div>` had put `#foot` inside
`page-details`, so v2's freshness stamp rendered on a page nobody reads. That
was beside the point. Read properly:

    production has NO `#foot` at all - it has a structured `.pgf-*` footer
    v2 has `#foot`, and nothing has ever written to it

So v2's footer was never misplaced. It was never there. `stamp_footer.py` exited
1 on every v2 page, and that exit was the assertion working - there was nothing
to stamp - not a wrong path.

CAUSE: pass 0's seam is `</nav>`..`</body>` and production's footers live inside
it, so they went with the body. Fifth component lost to that seam, after the nav
markup, the sw-block export, the section bar and the finished-edition guard.

WHY THE STAMP IS THE POINT AND PRESENCE IS NOT
-----------------------------------------------
A footer that exists and never refreshes is worse than no footer: it asserts a
sync time that stopped being true. That is the class this project keeps finding,
and it has been misdiagnosed twice on production alone - "Données API · 16:50"
at 21:00 reads as a broken pipeline when it only means the page was not rebuilt.

Presence is easy to assert and easy to keep true by accident. Freshness is the
thing that goes quietly wrong, so it needs a referent that is known to be
maintained. THE WORKFLOW IS THAT REFERENT, asserted statically in (5): its
restamp step stamps `$OUT` and `v2/$OUT` in one loop from one clock. Assert the
step and the freshness follows; assert only the pages and you are reading a
snapshot of whenever someone last built them.

Both directions, and a reality anchor, because comparing two artefacts to each
other certifies consistency and nothing else:

  1  every v2 page carries TWO `.pg-footer` blocks, one per page div, matching
     production's shape
  2  `stamp_footer.STAMP_ITEM_RE` - the shared contract, imported, never
     restated - matches exactly twice per page, so the restamp can still find
     them. This is the assertion `stamp_footer.py` makes at runtime, made here
     before the run rather than four hours into a quiet one.
  3  the stamp PARSES as a real time or a real freeze date. Against reality, not
     against production: two pages can agree on the same nonsense.
  4  v2's DATA-DERIVED footer items equal production's for the same event -
     last-ticket time and version. NOT the sync stamp: build_v2 regenerates the
     page, so a locally rebuilt v2 legitimately carries a newer stamp than the
     committed production page, and an earlier draft of this check failed all
     six on a correct state. A check that fails on correct states gets
     disabled, and a disabled check is not a check.
  5  the WORKFLOW's restamp step names v2/$OUT and loops stamp_footer over both.
     That is what actually keeps the stamp fresh, and it is the only clause that
     says anything about a QUIET day - the only day the stamp matters, because
     a busy one rebuilds the page and mints a new stamp anyway.

ON THE VERSION
--------------
v2 shows the SAME version as production and does not invent a suffix. It is
built on the same pipeline until cutover, so inheriting the number asserts
nothing false. At cutover it goes to 7.0 - a deliberate break rather than an
increment, 6.x being the pipeline where run.py's body reaches the page and 7.0
where pass 0's does. That bump is one constant, `postprocess_html.DASHBOARD_VERSION`,
which this reads rather than restates.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from pages import v2_pages   # noqa: E402 - CUTOVER 6.3, one page list

import postprocess_html as pp          # noqa: E402
import stamp_footer as sf              # noqa: E402

V2 = ROOT / 'v2'
FOOTER_RE = re.compile(r'<div class="pg-footer[^"]*">.*?</div>', re.DOTALL)
VALUE_RE = re.compile(r'<span class="pgf-k">([^<]*)</span>'
                      r'<span class="pgf-v">([^<]*)</span>')
TIME_RE = re.compile(r'^\d{2}:\d{2}$')
DATE_RE = re.compile(r'^\d{2}/\d{2}$')
TICKET_RE = re.compile(r'^\d{2}/\d{2} · \d{2}:\d{2}$')


def items(html):
    """[(label, value), ...] for every footer item, in document order."""
    return [(k.strip(), v.strip())
            for foot in FOOTER_RE.findall(html)
            for k, v in VALUE_RE.findall(foot)]


def main():
    pages = v2_pages()
    if not pages:
        print('no v2 pages')
        return 1

    fails = []
    print(f'0  the version is one constant, read not restated: '
          f'v{pp.DASHBOARD_VERSION}')

    # WHICH FOOTER VARIANT, not just whether one exists. A FINISHED edition must
    # carry "Données figées · DD/MM" and a live one "Données API · HH:MM".
    #
    # THIS EXISTS BECAUSE IT HAPPENED TWICE IN ONE SESSION, both times the same
    # way: rebuilding a v2 page regenerates the footer as the LIVE variant,
    # because the frozen one is applied out of band by the workflow's restamp
    # step. The workflow never rebuilds finished events, so the hazard only
    # appears when a human rebuilds all six - which the P1/P2 and P3 commits both
    # did. P3 shipped v2/bordeaux.html and v2/parisxxl.html carrying a live clock
    # over data frozen on 11/08.
    #
    # Every check in this file passed on those pages, because they all asked
    # whether a footer EXISTS and is STAMPABLE. A page asserting a sync time that
    # stopped being true is the exact defect this file's own failure message
    # names, and nothing here could see it.
    #
    # Liveness comes from the SERIES FILE, which is where build_series recorded
    # it once per event - not from a date comparison here, which would make
    # liveness a property of whoever is looking.
    live = {}
    for f in sorted((ROOT / 'series').glob('*.json')):
        try:
            live[f.stem] = bool(json.loads(f.read_text(encoding='utf-8'))['live'])
        except (ValueError, KeyError):
            continue
    import csv as _csv
    owner = {}
    with (ROOT / 'event_config.csv').open(encoding='utf-8-sig') as f:
        for row in _csv.DictReader(f):
            n = (row.get('output_filename') or '').strip()
            if n and (row.get('status') or '').strip() == 'active' and n not in owner:
                owner[n] = (row.get('event_id') or '').strip()

    for p in pages:
        name = p.name
        prod = ROOT / name
        html = p.read_text(encoding='utf-8')
        bad = []

        eid = owner.get(name)
        if eid in live:
            want_frozen = not live[eid]
            has_frozen = 'Données figées' in html
            has_api = 'Données API' in html
            if want_frozen and not has_frozen:
                bad.append('finished edition carries the LIVE footer')
                print(f'  FAIL  {name}: {eid} is finished, so its footer must '
                      f'read "Données figées · DD/MM".')
                print('        It carries "Données API" - a live sync clock over '
                      'frozen data,')
                print('        which is the one thing this footer exists to '
                      'prevent. Rebuilding')
                print('        a v2 page regenerates the live variant; restamp '
                      'it with')
                print('        scripts/stamp_footer.py --frozen "$(python3 '
                      'scripts/stamp_footer.py')
                print(f'        --read-frozen {name})".')
            elif not want_frozen and not has_api:
                bad.append('live edition carries the FROZEN footer')
                print(f'  FAIL  {name}: {eid} is live, so its footer must read '
                      f'"Données API · HH:MM", not a frozen date.')
            elif want_frozen and has_api:
                bad.append('both footer variants present')
                print(f'  FAIL  {name}: carries BOTH footer variants')
            else:
                print(f'  ok    {name}: {"frozen" if want_frozen else "live"} '
                      f'footer, matching {eid}')

        # (1) shape
        feet = FOOTER_RE.findall(html)
        if len(feet) != 2:
            bad.append(f'{len(feet)} .pg-footer block(s), want 2 (one per page div)')

        # (2) the shared contract still matches - imported, never restated
        n_stamp = len(sf.STAMP_ITEM_RE.findall(html))
        if n_stamp != 2:
            bad.append(f'stamp_footer.STAMP_ITEM_RE matches {n_stamp} time(s), '
                       f'want 2 - the restamp would exit 1 on this page')

        # (3) the values are real, asserted against reality rather than production
        got = items(html)
        if not got:
            bad.append('no footer items at all')
        for label, value in got:
            if label.startswith('Données API'):
                if not TIME_RE.match(value):
                    bad.append(f'sync stamp {value!r} is not HH:MM')
            elif label.startswith('Données figées'):
                if not DATE_RE.match(value):
                    bad.append(f'freeze date {value!r} is not DD/MM')
            elif label.startswith('Dernier billet'):
                if not TICKET_RE.match(value):
                    bad.append(f'last-ticket {value!r} is not DD/MM · HH:MM')
        kinds = {l for l, _ in got}
        if not any(k.startswith(('Données API', 'Données figées')) for k in kinds):
            bad.append('no freshness item at all - nothing here answers "how '
                       'fresh is the check"')

        # (4) the DATA-DERIVED items match production's for the same event.
        #     NOT the sync stamp: build_v2 regenerates the page, so a locally
        #     rebuilt v2 legitimately carries a newer stamp than the committed
        #     production page. An earlier draft compared the whole footer and
        #     failed all six on a correct state - a check that fails on correct
        #     states gets disabled, and then it is not a check.
        #
        #     "Dernier billet" comes from the merged CSV, so it must agree
        #     whenever the two were built from the same data; a divergence there
        #     means the transplant took a footer from somewhere else.
        if not prod.exists():
            bad.append(f'no production page {name} to compare against')
        else:
            fixed = lambda rows: [(l, v) for l, v in rows
                                  if not l.startswith(('Données API', 'Données figées'))]
            if fixed(got) != fixed(prod.read_text(encoding='utf-8') and
                                   items(prod.read_text(encoding='utf-8'))):
                bad.append('data-derived footer items differ from production\'s:')
                for a, b in zip(fixed(got) + [None] * 9,
                                fixed(items(prod.read_text(encoding='utf-8'))) + [None] * 9):
                    if a != b and (a or b):
                        bad.append(f'    v2 {a}  vs  prod {b}')
                bad = bad[:8]

        # the version, from the constant rather than a literal
        if f'Festiflow Dashboard' in html:
            vers = re.findall(r'<span class="pgf-ver">([^<]*)</span>', html)
            wrong = [v for v in vers if v != f'v{pp.DASHBOARD_VERSION}']
            if wrong:
                bad.append(f'version {wrong} != v{pp.DASHBOARD_VERSION}')
        else:
            bad.append('no brand item')

        if bad:
            fails.append(name)
            print(f'  FAIL  {name}')
            for x in bad[:8]:
                print(f'          {x}')
        else:
            stamp = next((v for l, v in got
                          if l.startswith(('Données API', 'Données figées'))), '?')
            print(f'  ok    {name}: 2 footer(s), stampable, {stamp}, '
                  f'data items match production')

    # ---- (5) the WORKFLOW restamps v2, not just production -------------
    # This is what actually keeps the stamp fresh. The pages above can only
    # show what a build produced; this shows what the scheduled run will do on
    # a QUIET day, which is the only day the stamp matters - a busy day
    # rebuilds the page and mints a new one anyway.
    print('\n5  the scheduled restamp reaches v2, not only production')
    wf = ROOT / '.github' / 'workflows' / 'daily-dashboards.yml'
    if not wf.exists():
        fails.append('no workflow')
        print('  FAIL  no daily-dashboards.yml')
    else:
        y = wf.read_text(encoding='utf-8')
        step = y.split('name: Restamp the footer', 1)
        if len(step) != 2:
            fails.append('no restamp step')
            print('  FAIL  no "Restamp the footer" step')
        else:
            body = step[1].split('\n      - name:', 1)[0]
            if 'v2/$OUT' not in body:
                fails.append('restamp skips v2')
                print('  FAIL  the restamp step never names v2/$OUT, so a quiet')
                print('        run refreshes production and leaves v2 asserting')
                print('        a sync time that stopped being true')
            elif 'stamp_footer.py "$f"' not in body:
                fails.append('restamp does not loop')
                print('  FAIL  v2/$OUT is named but stamp_footer is not called '
                      'over the list')
            else:
                print('  ok    restamps $OUT and v2/$OUT in one loop')

    print()
    if fails:
        print(f'FAILED: {len(fails)} page(s)')
        print('A footer that exists and never refreshes is worse than none - it')
        print('asserts a sync time that stopped being true. The workflow restamps')
        print('$OUT and v2/$OUT in one loop; if they disagree, one did not run.')
        return 1
    print(f'all {len(pages)} v2 page(s): production\'s footer, still stampable, '
          f'and the scheduled run keeps it fresh')
    return 0


if __name__ == '__main__':
    sys.exit(main())
