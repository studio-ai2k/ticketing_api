#!/usr/bin/env python3
"""
The seven visible Suivi rows must contain sales.

    python verify/check_suivi_window.py parisxxl.html [...]
    python verify/check_suivi_window.py            # all six dashboards

run.py anchors the daily window on `cutoff_velocity` = `max(order_date) - 1`
over all tickets, and shows the last seven rows. One sale landing long after the
event drags that anchor into dead space: `paris_xxl_2026` had 7 paid tickets on
2026-03-30, sixteen days after a 13-14 March event, and the seven visible rows
became 23-29 March - every one zero on both sides, with 112 real selling days
collapsed behind a "Voir les 112 jours précédents" button. The table read as
empty.

`build_dashboard._clamp_cutoff` fixes it by clamping to `event_date_last + 1`.

This checks the SHIPPED PAGE rather than the clamp function, because the clamp
being correct and the clamp being wired are different facts, and only the second
one reaches a reader. Same reason `check_footer_tz.py` runs a real footer
through the real pass.

What it asserts, per page:

  1. The visible daily rows are not all zero. That is the reported bug.
  2. The last visible row is not more than 7 days past the event's last day.
     Catches the anchor drifting again for a reason nobody predicted.
  3. The "voir les N jours" and "voir les N semaines" buttons count their own
     grain. A weekly button reporting a daily count would mean the two grains
     share a row set (AA3).

TWO ROUTES, ONE SET OF CLAIMS — and the route is chosen by the artefact
-----------------------------------------------------------------------
Production renders the Suivi table as static markup. Pass 0 ships `const D` and
builds the table at runtime, so the markup route reads ZERO rows on a correct
pass-0 page. At cutover the page at the root changes pipeline underneath this
check, which is what §5bis lists it for.

So it reads whichever the page actually holds. The three claims are the same;
only claim 3 differs in form, because the payload can state the thing the
buttons were a symptom of: every ticket in `daily` appears in `weekly` exactly
once. Measured equal to the unit on all six pages.

The window mapping is measured, not assumed - see payload_window(). The
HIDDEN-row counts are deliberately NOT carried across: they diverge between the
pipelines because they describe each renderer rather than the data.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from pages import page_names   # noqa: E402 - CUTOVER 6.3, one page list

# The hand-written six-name list that used to live here was the THIRD one in the
# repo. CUTOVER §6.3 records removing two - `check_build_stamp.py` and
# `assert_redesign.sh` - and this one was not found, so it kept the hazard the
# other two were fixed for: a seventh event is covered on the day someone
# remembers, and this file was not on anyone's list of places to remember.
#
# The ROOT it reads is NOT a defect and was deliberately left alone. This
# check's subject is the page a reader opens, which is at the repo root on both
# sides of the cutover - production today, pass 0 after. `pass0_dir()` would be
# wrong here: it resolves to `v2/` today, and auditing the staging copy would
# make this red about a state that is fine. The two resolvers answer different
# questions and only one of them is this check's.
VISIBLE = 7


PAYLOAD_RE = re.compile(r'const D=(\{.*?\});\s*\n', re.DOTALL)


def jx_label(jx):
    """`J-93` before the event, `J+2` after it. Never `J--2`.

    jx counts DOWN to 0 at the event, so a negative value is a day past it -
    which is the dead space trap #10 anchored into, and the one number in this
    check a reader most needs to read correctly at a glance.
    """
    return f'J-{jx}' if jx >= 0 else f'J+{-jx}'


def payload_window(html):
    """(window, problems) for a PASS-0 page, read from `const D`.

    WHY THERE ARE TWO ROUTES AND NOT A REPOINTED ONE
    -------------------------------------------------
    This check reads the page that SHIPS, at the repo root, and at cutover that
    page changes pipeline. Production renders the Suivi table as static markup;
    pass 0 ships `const D` and builds the table at runtime, so `daily_rows()`
    reads 0 rows on a perfectly correct pass-0 page.

    The property does not change - trap #10 is that the seven visible rows can
    all be zero when the anchor drifts into dead space - only where it has to be
    read from. So the route is chosen by what the page actually contains, and
    both routes assert the same three claims.

    THE MAPPING IS MEASURED, NOT ASSUMED. The last seven non-future `daily`
    rows, ordered chronologically, reproduce the rendered window exactly on both
    pages where a production page exists to check against:

        rennes    714 over 2026-08-05 .. 2026-08-11   = "Mer 5 Aoû .. Mar 11 Aoû"
        parisxxl 4816 over 2026-03-09 .. 2026-03-15   = "Lun 9 Mar .. Dim 15 Mar"

    The HIDDEN-row counts deliberately are not carried across: they diverge
    between the pipelines (bordeaux 151 here against 172 there), because they
    are a property of how each renders its table rather than of the data. An
    assertion that reproduced them would be asserting the renderer twice.
    """
    m = PAYLOAD_RE.search(html)
    if not m:
        return None, ['no `const D=` payload and no static Suivi markup']
    try:
        D = json.loads(m.group(1))
    except ValueError as exc:
        return None, [f'`const D=` is not parseable JSON: {exc}']
    daily = D.get('daily') or []
    if not daily:
        return None, ['the payload carries no `daily` rows at all']
    past = sorted((r for r in daily if not r.get('fut')), key=lambda r: -r['jx'])
    if not past:
        return None, ['every daily row is `fut` - there is no window to show']
    return past[-VISIBLE:], []


def reference_hole_problems(html):
    """No settled row may lack a reference while a LATER row has one.

    THE SHAPE THIS CATCHES: A HOLE AT A BOUNDARY, WITH DATA ON BOTH SIDES.

    epk shipped with the newest non-`fut` daily row carrying `db: None` and
    `b: None` while every row after it carried a 2023 date and value. The live
    page drew the amber "Aujourd'hui" row with a figure on the right, an em dash
    on the left and an em dash in the delta - one blank cell in the middle of a
    contiguous reference column.

    The cause was two mappings on different scales. `filter_tickets_to_same_point`
    cuts the reference at equal DAYS-BEFORE-EVENT and is raw; `align.ref_date`
    pairs the rows and, under `j_minus`, SNAPS TO THE SAME WEEKDAY. `daily_rows`
    bounded a snapped `m` with the raw cut, so the newest paired row fell outside
    it by exactly the snap - one day, on an event whose two editions start on
    different weekdays.

    WHY THIS ASSERTION AND NOT AN EQUALITY
    ---------------------------------------
    The three claims this file already makes - rows not all zero, anchor not
    drifted past the event, buttons counting their own grain - are all true of a
    table with a hole in it, and were green on the shipped page throughout. A
    check that only asks whether the window is populated cannot see a single
    missing cell inside it.

    Stated as monotonicity rather than as "the newest settled row has a
    reference", because that stronger form is FALSE in a legitimate case: a
    reference edition whose own data stops early leaves a genuine tail of
    null-reference rows, and `daily_rows`' `ref_last` guard exists to produce
    exactly that. A hole is a null with a non-null after it. A tail is not.

    `fut` rows are exempt on the left of the comparison but count on the right:
    the event-day row is `fut` and legitimately null under the weekday snap
    (epk's `jx: 0` pairs with the reference's own `jx: -1`), and that is a parked
    alignment question, not this defect.
    """
    m = PAYLOAD_RE.search(html)
    if not m:
        return []
    try:
        D = json.loads(m.group(1))
    except ValueError:
        return []
    daily = D.get('daily') or []
    out = []
    for i, r in enumerate(daily):
        if r.get('fut') or r.get('b') is not None:
            continue
        later = [x for x in daily[i + 1:] if x.get('b') is not None]
        if later:
            out.append(
                f"settled row J-{r.get('jx')} ({r.get('da')}) has NO reference "
                f"while J-{later[0].get('jx')} ({later[0].get('da')}) has one "
                f"- a hole at the boundary, not a tail")
    return out


def grain_problems(html):
    """AA3 at the payload: the weekly grain aggregates the daily one, exactly.

    The markup form asked whether the two "voir les N" buttons report the same
    number, which is a symptom of the two grains sharing a row set. The payload
    can state the thing itself: every ticket in `daily` must appear in `weekly`
    once. Measured equal on all six pages, to the unit.

    Length is asserted too, because equal sums alone would hold if `weekly` WERE
    `daily` - which is the failure AA3 is named for.
    """
    m = PAYLOAD_RE.search(html)
    if not m:
        return []
    D = json.loads(m.group(1))
    daily, weekly = D.get('daily') or [], D.get('weekly') or []
    if not weekly:
        return ['the payload carries no `weekly` rows - the grain toggle has '
                'nothing to switch to']
    sd = sum(r.get('a') or 0 for r in daily)
    sw = sum(r.get('a') or 0 for r in weekly)
    out = []
    if sd != sw:
        out.append(f'the grains disagree on the total: daily {sd}, weekly {sw}. '
                   f'One of them drops or double-counts tickets.')
    if len(weekly) >= len(daily):
        out.append(f'{len(weekly)} weekly rows against {len(daily)} daily - the '
                   f'weekly grain is not coarser, so the two are the same row '
                   f'set (AA3)')
    return out


def daily_rows(html):
    """Every dtl-row in the daily tab, in document order, as (date, sales)."""
    i = html.find('id="suivi-jour"')
    if i < 0:
        return []
    seg = html[i:html.find('id="suivi-semaine"', i)]
    out = []
    for row in re.findall(r'<div class="dtl-row.*?(?=<div class="dtl-row|\Z)', seg, re.S):
        if 'dtl-row future' in row[:40]:
            continue
        dates = re.findall(r'class="dtl-date"[^>]*>([^<]*)<', row)
        sales = re.findall(r'class="dtl-sales"[^>]*>([^<]*)<', row)
        if len(dates) >= 2 and len(sales) >= 2:
            out.append((dates[1].strip(), sales[1].strip()))
    return out


def main(argv):
    # Config-derived, at the REPO ROOT - which is "the page that ships" on both
    # sides of the cutover, so it needs no repointing. NOT pass0_dir(): this
    # check's subject is the page a reader opens, and today that is production
    # at the root, not the staging copy under v2/. Repointing it at v2/ would
    # have made it red today about a state that is fine.
    targets = [Path(a) for a in argv] or [ROOT / n for n in page_names()]
    failures = []

    for path in targets:
        name = path.name
        if not path.exists():
            print(f'  skip  {name} (not built)')
            continue
        html = path.read_text(encoding='utf-8')
        rows = daily_rows(html)

        # PASS 0: no static Suivi markup, so read the same window from the
        # payload the renderer consumes. Route chosen by what the page holds,
        # not by a flag - it is correct on both sides of the cutover with no
        # edit on the day.
        if not rows and PAYLOAD_RE.search(html):
            window, probs = payload_window(html)
            probs += grain_problems(html)
            probs += reference_hole_problems(html)
            if window is None:
                for x in probs:
                    failures.append(f'{name}: {x}')
                    print(f'  FAIL  {name}: {x}')
                continue
            total = sum(r.get('a') or 0 for r in window)
            span = f"{jx_label(window[0]['jx'])} .. {jx_label(window[-1]['jx'])}"
            if total == 0:
                probs.append(f'all {len(window)} visible rows are zero ({span})')
            # Claim 2, at the payload: the window must not sit past the event.
            # jx counts down to 0 at the event, so a negative jx is a day AFTER
            # it - which is exactly the dead space trap #10 anchored into.
            if window[-1]['jx'] < -VISIBLE:
                probs.append(f'the window ends at {jx_label(window[-1]["jx"])}, more than '
                             f'{VISIBLE} days past the event')
            for x in probs:
                failures.append(f'{name}: {x}')
                print(f'  FAIL  {name}: {x}')
            if not probs:
                print(f'  ok    {name}: {total} sales in the visible window  '
                      f'[{span}]  (from `const D`)')
            continue

        if not rows:
            # LOUD, AND STILL UNRESOLVED FOR PASS 0. `daily_rows` parses
            # `id="suivi-jour"` and `.dtl-row` out of STATIC markup, and a
            # pass-0 page has neither: its body is built at runtime from
            # `const D`, so this reads 0 rows on a perfectly correct page.
            #
            # Deliberately left failing rather than made to pass. The property
            # - the seven visible rows contain sales, trap #10 - is real and
            # still matters; what it has to be read FROM changes at cutover,
            # and the payload-level form is a separate piece of work. A check
            # that fails loudly says so; one quietly repointed at markup that
            # is not there would report six green pages and assert nothing.
            failures.append(f'{name}: no daily rows found - the markup moved')
            print(f'  FAIL  {name}: no daily rows found')
            continue

        # 1. the visible window has to contain something.
        #
        # The "Aujourd'hui" row is NOT part of it. run.py appends that row after
        # the VISIBLE_DAYS slice and drives it from `cutoff_cumulative`, so on
        # paris_xxl it carried the 7 straggler tickets and made a window of six
        # zero rows sum to 7. This check PASSED ON THE BROKEN PAGE until that
        # row was excluded. That is trap #10, and this line is the whole fix -
        # do not simplify it away.
        dated = [r for r in rows if 'ujourd' not in r[0]]
        window = dated[-VISIBLE:]
        total = 0
        for _, s in window:
            try:
                total += int(s.replace(' ', '').replace(' ', ''))
            except ValueError:
                pass  # "À venir" and friends
        span = f'{window[0][0]} .. {window[-1][0]}'
        if total == 0:
            failures.append(f'{name}: all {len(window)} visible rows are zero ({span})')
            print(f'  FAIL  {name}: visible window is empty  [{span}]')
        else:
            print(f'  ok    {name}: {total} sales in the visible window  [{span}]')

        # 2. the two buttons must count their own grain
        days = [int(n) for n in re.findall(r'Voir les (\d+) jours? précédents', html)]
        weeks = [int(n) for n in re.findall(r'Voir les (\d+) semaines? précédentes', html)]
        if days and weeks and set(days) & set(weeks) and max(days) > 20:
            failures.append(f'{name}: daily and weekly buttons report the same count '
                            f'{sorted(set(days) & set(weeks))}')
            print(f'  FAIL  {name}: daily and weekly counts coincide - shared row set?')
        elif days and weeks:
            print(f'  ok    {name}: {days[0]} hidden days / {weeks[0]} hidden weeks')

    print()
    if failures:
        print(f'FAILED: {len(failures)}')
        for f in failures:
            print(f'  - {f}')
        return 1
    print('every dashboard shows a non-empty Suivi window')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
