#!/usr/bin/env python3
"""
The footer's last-ticket time must be Paris, not UTC.

    python verify/check_footer_tz.py

run.py:2048 renders it straight off `order_datetime`, which is UTC. The proof is
the DST offset, four campaigns across two seasons, all four on-sales at 19:00
Paris:

    paris_xxl_2026  stored 17:59  Dec  CET  +1  ->  18:59
    paris_xxl_2025  stored 18:01  Dec  CET  +1  ->  19:01
    epk_2026        stored 17:00  Apr  CEST +2  ->  19:00
    rennes_2026     stored 17:00  Jun  CEST +2  ->  19:00

The stored values differ ONLY by the seasonal offset. Nothing but UTC storage
produces that.

`postprocess_html._to_paris` fixes it on the way through §7. The reason this
file exists is that the failure is invisible: a footer an hour or two slow looks
completely normal, and it is wrong by a DIFFERENT amount in each season, so even
a side-by-side against a known sale time only disagrees half the year. Trap #5's
family - verify the output, and pick a case where being wrong is legible.

Four negative tests. Each is a way the conversion could stop happening while
apply_footer still reports the two footers it expects.
"""

import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
import postprocess_html as pp  # noqa: E402

FAILURES = []


def check(label, got, want):
    ok = got == want
    print(f'  {"ok  " if ok else "FAIL"}  {label}: {got!r}' + ('' if ok else f' != {want!r}'))
    if not ok:
        FAILURES.append(label)


def main():
    print('_to_paris - summer (CEST, +2)')
    # Rennes on-sale: 17:00 UTC is the 19:00 Paris everyone remembers.
    check('rennes on-sale', pp._to_paris('02/06 · 17:00', date(2026, 8, 8)),
          '02/06 · 19:00')

    print('_to_paris - winter (CET, +1)')
    # Same clock reading, four months earlier, must move by ONE hour not two.
    # A hardcoded +2 passes the summer case and fails here; that is the point.
    check('december evening', pp._to_paris('15/12 · 17:59', date(2026, 8, 8)),
          '15/12 · 18:59')

    print('_to_paris - crosses the day boundary')
    # 3.48% of our rows sit in this window. If the conversion is skipped the
    # date is wrong too, not just the time.
    check('23:30 rolls to tomorrow', pp._to_paris('07/08 · 23:30', date(2026, 8, 8)),
          '08/08 · 01:30')

    print('_to_paris - crosses the year boundary')
    check('new year', pp._to_paris('31/12 · 23:30', date(2026, 1, 1)),
          '01/01 · 00:30')

    print('_to_paris - leaves what it cannot parse alone')
    for junk in ('-', '', 'yesterday', '7/8 · 9:5'):
        check(f'passthrough {junk!r}', pp._to_paris(junk, date(2026, 8, 8)), junk)

    print('\napply_footer actually calls it')
    # The unit tests above all pass if _to_paris is correct and nobody calls it.
    # This is the wiring check: a real footer through the real pass.
    html = (
        '<div style="text-align:center;padding:10px">'
        '🎟 Dernier billet vendu · 02/06 · 17:00'
        '&nbsp;·&nbsp;🔄 Données API · 09:30'
        '&nbsp;·&nbsp;Festiflow Dashboard v7.0</div>'
        '<div class="det-footer">'
        '🎟 Dernier billet vendu · 02/06 · 17:00'
        '&nbsp;·&nbsp;🔄 Données API · 09:30'
        '&nbsp;·&nbsp;Festiflow Dashboard v7.0</div>'
    )
    out, problems, n = pp.apply_footer(html)
    check('both footers rebuilt', n, 2)
    check('no problems', problems, [])
    check('UTC 17:00 is gone', '17:00' in out, False)
    check('Paris 19:00 is there', out.count('02/06 · 19:00'), 2)

    print('\nthe workflow stamps in Paris too')
    # The runner is UTC. A bare `date +%H:%M` is the same bug from our own side.
    wf = Path('.github/workflows/daily-dashboards.yml').read_text(encoding='utf-8')
    import re
    bare = re.findall(r'(?<!TZ=Europe/Paris )date \+%[HMd]', wf)
    check('no bare date in the stamp step', bare, [])

    print()
    if FAILURES:
        print(f'FAILED: {len(FAILURES)} - {", ".join(FAILURES)}')
        return 1
    print('all footer-timezone checks pass')
    return 0


if __name__ == '__main__':
    sys.exit(main())
