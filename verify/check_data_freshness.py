#!/usr/bin/env python3
"""
The pipeline has stopped, and no page can say so.

    python3 verify/check_data_freshness.py [--max-age-hours N]

WHY THIS EXISTS
---------------
On 2026-08-10 the daily job stopped committing. Runs #36-#42 fired on schedule,
fetched correctly, built correctly, and failed at the commit gate. Nothing
reached main for ~28 hours and the only symptom on the page was a footer reading
`Données API 00:06` beside CSVs whose newest ticket was `10/08 14:43`.

**That stamp cannot report a freeze.** It is written when a page is rebuilt, so
it moves only when something else has already changed - and both failure modes
here produce the same frozen stamp:

    the FETCH stops      no new tickets  -> nothing rebuilds -> stamp frozen
    the COMMIT stops     new tickets     -> nothing lands    -> stamp frozen

A signal that only moves when something else moved cannot report a standstill.
This asserts the thing itself: the newest ticket we hold is recent.

WHY IT MUST NOT BE A BLOCKING GATE
----------------------------------
The outage it exists for was CAUSED by a check in the commit gate: three browser
checks were wired in with dev-container paths, failed 100% of the time, and took
the pipeline down with them. So this one runs AFTER the push in the workflow.
A stale-data alarm that also blocks the fix is the same mistake twice.

FINISHED EDITIONS ARE EXCLUDED, AND THAT IS NOT A CONVENIENCE
-------------------------------------------------------------
Their data is frozen by design, so they age without bound - paris_xxl_2026 shows
a 369-hour gap and bordeaux_2026 stopped in June. Including them would make this
fire permanently, which is the same "always fires, carries no information"
failure as never firing at all.

Liveness is the workflow's OWN rule, imported in spirit rather than restated:
last day_date plus a 30-day grace, because sales run through the event and
refunds land for weeks after. A second definition of "live" is a second thing to
keep in step.

CHOOSING N, FROM MEASUREMENT
----------------------------
Sales sleep. The threshold has to clear the quietest real night or it cries
wolf. Longest gap between consecutive tickets on each LIVE campaign, last 30
days:

    geneve_2026       16.1 h        <- the binding one
    rennes_2026       12.9 h
    bordeaux_oct_2026 10.2 h
    epk_2026           8.2 h

24 hours gives ~1.5x headroom over the worst observed quiet period and would
have caught the 28-hour outage. It is a deliberately slow signal: the fast one
is the job failing, which reaches Leo through the alert on the workflow itself.
This catches the case that has no alert - the job quietly not running at all.
"""

import argparse
import csv
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Same grace the matrix builder uses to decide whether to fetch at all. If that
# number moves, this one moves with it - they are the same rule.
GRACE_DAYS = 30
DEFAULT_MAX_AGE_H = 24


def live_events(config):
    """Event ids the pipeline still fetches: active, and within grace of their
    last day. Mirrors the workflow's matrix rule."""
    days, status = {}, {}
    for row in csv.DictReader(config.open(encoding='utf-8-sig')):
        eid = (row.get('event_id') or '').strip()
        if not eid:
            continue
        status.setdefault(eid, (row.get('status') or '').strip())
        raw = (row.get('day_date') or '').strip()
        if raw:
            try:
                days.setdefault(eid, []).append(
                    datetime.strptime(raw, '%Y-%m-%d').date())
            except ValueError:
                # Never let an unparseable date read as "past": that would drop
                # a live event out of this check silently, which is the failure
                # this check exists to catch.
                days.setdefault(eid, []).append(None)
    today = date.today()
    out = []
    for eid, dd in days.items():
        if status.get(eid) != 'active':
            continue
        if any(d is None for d in dd):
            out.append(eid)          # unknown date: treat as live, and say so
            continue
        if max(dd) + timedelta(days=GRACE_DAYS) >= today:
            out.append(eid)
    return sorted(out)


def newest_ticket(path):
    newest = None
    for r in csv.DictReader(path.open(encoding='utf-8-sig')):
        v = (r.get('order_datetime') or '').strip()
        if not v:
            continue
        try:
            t = datetime.fromisoformat(v)
        except ValueError:
            continue
        if newest is None or t > newest:
            newest = t
    return newest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-age-hours', type=float, default=DEFAULT_MAX_AGE_H)
    a = ap.parse_args()

    cfg = ROOT / 'event_config.csv'
    live = live_events(cfg)
    now = datetime.utcnow()
    print(f'{len(live)} live event(s), newest ticket must be under '
          f'{a.max_age_hours:g} h old (UTC now {now:%Y-%m-%d %H:%M})\n')

    if not live:
        # Every edition finished. Real, and not a failure - but it must not read
        # as "all clear", because a config mistake produces the same emptiness.
        print('  no live events - nothing to assert. If that is a surprise, it '
              'is the finding.')
        return 0

    failures = []
    print(f'{"event":<22}{"newest ticket":>21}{"age h":>9}')
    for eid in live:
        p = ROOT / 'data' / f'{eid}_merged.csv'
        if not p.exists():
            failures.append(f'{eid}: no merged CSV')
            print(f'{eid:<22}{"(no CSV)":>21}{"":>9}  FAIL')
            continue
        t = newest_ticket(p)
        if t is None:
            failures.append(f'{eid}: no parseable order_datetime')
            print(f'{eid:<22}{"(no timestamps)":>21}{"":>9}  FAIL')
            continue
        age = (now - t).total_seconds() / 3600
        bad = age > a.max_age_hours
        if bad:
            failures.append(f'{eid}: newest ticket {age:.1f} h old')
        print(f'{eid:<22}{str(t):>21}{age:>9.1f}{"  FAIL" if bad else ""}')

    print()
    if failures:
        print(f'STALE: {len(failures)}')
        for f in failures:
            print(f'  - {f}')
        print()
        print('The data this repo holds has stopped moving. Both failure modes')
        print('look identical from the page, so check which one it is:')
        print('  1. the workflow ran and FAILED   -> Actions, newest run')
        print('  2. the workflow did not run      -> Actions, schedule; GitHub')
        print('     disables cron on repos with no activity for 60 days')
        print('  3. the fetch ran and returned nothing -> the platform APIs')
        return 1
    print('the newest ticket on every live event is recent')
    return 0


if __name__ == '__main__':
    sys.exit(main())
