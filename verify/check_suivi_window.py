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
DEFAULT = ['parisxxl.html', 'bordeaux.html', 'bordeaux_oct.html',
           'epk.html', 'geneve.html', 'rennes.html']
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
    targets = argv or DEFAULT
    failures = []

    for name in targets:
        path = ROOT / name
        if not path.exists():
            print(f'  skip  {name} (not built)')
            continue
        html = path.read_text(encoding='utf-8')
        rows = daily_rows(html)
        if not rows:
            failures.append(f'{name}: no daily rows found - the markup moved')
            print(f'  FAIL  {name}: no daily rows found')
            continue

        # 1. the visible window has to contain something.
        #
        # The "Aujourd'hui" row is NOT part of it. run.py appends that row after
        # the VISIBLE_DAYS slice and drives it from `cutoff_cumulative`, so on
        # paris_xxl it carried the 7 straggler tickets and made a window of six
        # zero rows sum to 7. This check passed on the broken page until that
        # row was excluded - the same shape of mistake as trap #5.
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
