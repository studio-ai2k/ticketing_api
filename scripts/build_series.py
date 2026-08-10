#!/usr/bin/env python3
"""
One JSON per edition, keyed by that edition's OWN J−x. B1's data half.

    python scripts/build_series.py --out series/

WHY A FILE PER EDITION AND NOT A BLOCK PER PAGE
-----------------------------------------------
Priced three ways before building. Inlining every candidate in every page costs
+216 KB across six pages and +9s of build, because each edition's history gets
written six times and the alignment runs once per PAIR. A file per edition
costs 64.5 KB total, 25 KB gzipped, +2.1s once per run, and the reader
downloads 1.4–5.6 KB only when they actually pick a comparison.

That only works if the file is EVENT-AGNOSTIC — usable by any dashboard without
knowing which one will read it. It is, and the reason is worth stating exactly,
because the obvious version of it is wrong:

  `run.filter_tickets_to_same_point` reduces to `keep the reference's tickets
  where jx_ref >= D.jx`. Purely the consumer's own D.jx against this edition's
  own jx. Nothing crosses.

  BUT THE DAILY ROW PAIRING IS NOT jx-TO-jx. It goes through `daily_offset`,
  and the identity is

      jx_ref = jx_cur − signed_mod7(G),    G = (cur_ev − cand_ev).days

  a constant in [−3, +3] per pair. Derived, then checked against all six
  shipped pairs: three are 0 and three are ±1. "Our J−69 against their J−69"
  would have been a silent one-day skew on half the comparisons, rendering as
  ordinary numbers.

  The snap is a pure function of the two event dates, so it survives into a
  generic file: this one carries `ev`, the consumer knows its own, and the
  correction is computed client-side. Two scalars from the consumer, and no
  per-pair work on the server.

WHAT IS IN IT
-------------
Measured, not guessed: a bare daily count series is ~8 KB and is NOT enough.
The reference side of a dashboard also needs per-day cumulative presence (the
projection curves and the presence rollups), per-type and per-platform daily
counts (so a breakdown can be rebuilt at any J−x), and the free/invitation
series. That is what the 64.5 KB buys.

Every series is `[[jx, …], …]`, descending jx, and omits days with no activity.

PUBLIC
------
These land next to the dashboards on a public repo, so every edition's daily
sales and revenue history sits at a guessable URL with no gate in front of it.
That is not new in kind — the HTML already carries the same figures and the
password is client-side — but it is new in FORM: machine-readable, one fetch,
no page to find first. Ruled knowingly.
"""

import argparse
import json
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / 'scripts'))
sys.path.insert(0, str(BASE_DIR))

import run  # noqa: E402
import dashboard_payload as dp  # noqa: E402

LIVE_DIR = BASE_DIR / 'data'
ARCHIVE_DIR = BASE_DIR / 'csv_database'


def series_path(event_id):
    """Where this edition's merged CSV lives, or None. Same order as
    suivi_candidates.series_path — live directory first, then the archive."""
    live = LIVE_DIR / f'{event_id}_merged.csv'
    if live.exists():
        return live
    archive = ARCHIVE_DIR / event_id / f'{event_id}_merged.csv'
    if archive.exists():
        return archive
    hit = next((ARCHIVE_DIR / event_id).glob('*_merged.csv'), None) \
        if (ARCHIVE_DIR / event_id).is_dir() else None
    return hit


def build_one(event_id, cfg, today):
    rows = dp.load_rows(str(series_path(event_id)))
    if not rows:
        return None
    ev = cfg['event_date_first']
    live = max(d['day_date'] for d in cfg['days']) >= today
    days = dp._ordered_days(cfg)
    jx = lambda d: (ev - d).days                                  # noqa: E731

    paid = [r for r in rows if r['_paid']]
    n, rev = Counter(), Counter()
    for r in paid:
        n[jx(r['_d'])] += 1
        rev[jx(r['_d'])] += r['_price']
    free = Counter(jx(r['_d']) for r in rows if not r['_paid'])

    # Per-day cumulative presence, by this edition's own jx. Needs
    # run.resolve_attendance per ticket, which is exactly why it cannot be
    # derived by a consumer from the daily counts.
    per = {d: Counter() for d in days}
    for r in rows:
        pres = run.resolve_attendance(r.get('ticket_type'), dp.attendance(r), days)
        for d in days:
            if pres.get(d, 0):
                per[d][jx(r['_d'])] += 1
    presence = {}
    for d in days:
        tot, out = 0, []
        for k in sorted(per[d], reverse=True):
            tot += per[d][k]
            out.append([k, tot])
        presence[d] = out

    types, plat = {}, {}
    for r in paid:
        types.setdefault(r['ticket_type'], Counter())[jx(r['_d'])] += 1
        plat.setdefault(r['platform'], Counter())[jx(r['_d'])] += 1

    # The campaign LENGTH: the largest jx with a sale, i.e. how many days
    # before its own event this edition opened. `min` would give the jx closest
    # to the event - often negative, since editions keep selling after the
    # doors open - and the menu would read "−1 j".
    first = max(n) if n else 0
    return {
        'id': event_id,
        'name': cfg.get('event_name', event_id),
        'ev': ev.isoformat(),
        # A LIVE edition's series stops at today, not at its event. Everything
        # below is therefore PARTIAL, and `final` is the trap: the key is named
        # for what it means on the eight finished editions, and on a live one it
        # is a running subtotal that will render as an ordinary number in a
        # column headed "Réalisé final". Emitted as a flag rather than left to
        # each consumer to re-derive from `ev` and the clock, because a consumer
        # that forgets produces a plausible figure and no error.
        'live': live,
        'days': days,
        'cap': sum(d['day_capacity'] for d in cfg['days']),
        'daycap': {d['day_name'].strip().lower(): d['day_capacity']
                   for d in cfg['days']},
        'lead': first,
        'final': {'n': len(paid), 'free': len(rows) - len(paid),
                  'rev': round(sum(r['_price'] for r in paid))},
        'daily': [[k, n[k], round(rev[k])] for k in sorted(n, reverse=True)],
        'free': [[k, free[k]] for k in sorted(free, reverse=True)],
        'pres': presence,
        'types': {t: [[k, c[k]] for k in sorted(c, reverse=True)]
                  for t, c in types.items()},
        'plat': {p: [[k, c[k]] for k in sorted(c, reverse=True)]
                 for p, c in plat.items()},
    }


def projection_eligible(cfg_all, today):
    """Editions a dashboard may PROJECT from: FINISHED, and with data.

    One rule used to serve three consumers - this script, the projection
    candidates and the comparison menu - and that made emitting live series
    impossible without also putting live editions in the projection menu,
    where they cannot work: a projection replays a REMAINING curve and a live
    edition has not run one. So the rule splits, and the existing one keeps
    the projection name because the projection is what it was always right for.

    Live editions are deliberately absent. `suivi_candidates` already ruled
    that a live candidate must be anchored on LAUNCH rather than on its event
    date, because an event-date anchor maps recent rows into its future. That
    is a SECOND alignment mode, and it would need a third input from the
    consumer (its own launch date) — the condition that says stop and re-price
    rather than quietly implement it. So they are omitted, visibly, and the
    hardcoded mock menu that used to list them is gone with it.
    """
    return [c for c in comparison_eligible(cfg_all)
            if max(d['day_date'] for d in cfg_all[c]['days']) < today]


def comparison_eligible(cfg_all):
    """Editions a dashboard may COMPARE against: any edition with data.

    Wider than the projection rule and deliberately so - a live edition has a
    campaign to compare against even though it has no remaining curve to
    replay. What it does NOT yet have is an anchoring mode that makes the
    comparison meaningful: `suivi_candidates` rules that a live candidate must
    be anchored on LAUNCH, and until that mode exists a live candidate would
    be pickable and silently wrong.

    So this is the rule; the menu does not use it yet. The split lands first
    because it is verifiable on its own, and widening the menu lands with the
    modes.
    """
    return [cid for cid, cfg in sorted(cfg_all.items())
            if cfg.get('days') and series_path(cid)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(BASE_DIR / 'series'))
    ap.add_argument('--config', default=str(BASE_DIR / 'event_config.csv'))
    ap.add_argument('--today', help='YYYY-MM-DD; defaults to today')
    a = ap.parse_args()

    today = date.fromisoformat(a.today) if a.today else date.today()
    cfg_all = run.load_event_config(a.config)
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # COMPARISON-eligible, not projection-eligible: every anchoring mode needs
    # a live edition's history, and a file is the only way it can have one. The
    # projection SELECTOR stays narrow - the split exists precisely so these two
    # can differ - so writing a live file adds no page a reader can pick yet.
    #
    # THE CHURN, WHICH IS WHY THIS IS NOT JUST A WIDER LOOP
    # A finished edition's file is immutable: same input, same bytes, forever.
    # A live one is rewritten every run - four of the twelve today - so
    # `series/` stops being an append-only directory and starts producing a diff
    # on every daily commit. Two consequences, both accepted here rather than
    # discovered later:
    #   1. Bandwidth and history. ~5 KB x 4 rewritten daily is noise next to the
    #      merged CSVs the same job commits.
    #   2. STALENESS AT THE READER. The page fetches these at runtime, so a
    #      cached copy is a comparison drawn from yesterday against a page built
    #      today - two vintages in one chart, rendering as ordinary numbers. The
    #      fetch already passes {cache:'no-cache'}; from here on that flag is
    #      load-bearing rather than belt-and-braces, which is why the reason is
    #      recorded at the fetch and not only here.
    total = 0
    written = []
    for cid in comparison_eligible(cfg_all):
        blob = build_one(cid, cfg_all[cid], today)
        if not blob:
            continue
        text = json.dumps(blob, ensure_ascii=False, separators=(',', ':'))
        (out_dir / f'{cid}.json').write_text(text, encoding='utf-8')
        total += len(text)
        written.append((cid, len(text), blob['live']))
    for cid, size, live in written:
        print(f'  {cid:24s} {size / 1024:6.1f} KB  {"LIVE" if live else ""}')
    print(f'{len(written)} series -> {out_dir}  ({total / 1024:.1f} KB total)')
    # An empty run is not a quiet success: the pages fetch these by name, and
    # a missing file is a comparison that cannot be picked.
    return 0 if written else 1


if __name__ == '__main__':
    sys.exit(main())
