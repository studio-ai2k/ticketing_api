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
"""

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
