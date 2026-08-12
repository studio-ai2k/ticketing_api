#!/usr/bin/env python3
"""
Hold Shotgun's `gross_price` to the fee schedule the back-office export witnessed.

    python3 verify/check_shotgun_fee_table.py [merged.csv]

WHAT THE EXPORT SETTLED, AND WHY THIS IS A TABLE RATHER THAN A TOTAL
--------------------------------------------------------------------
On 2026-08-12 Leo produced a Shotgun back-office export for epk (8 392 valid
orders, PRICE and CLIENT PRICE). It agrees with our merged CSV on face and gross
with a gap of exactly one identifiable ticket - +1 order, +52,27 face, +59,08
gross, landing on a real price tier on all three components.

The obvious check to write from that is the DICE one's shape: pin the totals.
**It would die within a day.** `check_payout_reconciliation` pins
`bordeaux_2026`, which is FINISHED, so its CSV is frozen and a hardcoded total
stays true forever. `epk_2026` is LIVE - 155 Shotgun orders landed on
2026-08-11 alone - so `8391 / 469 296,88 / 530 425,53` stops being true before
anyone reads it.

So this pins the SCHEDULE instead. It survives the CSV growing, and it is a
stronger claim than any total: a total is one number that many wrong row sets
produce, where this fails if the arithmetic moves for a single tier.

WHY A TOTAL IS WEAK HERE, MEASURED
-----------------------------------
The ratio 1,130256 that the export confirms is nearly scale-free. Dropping
random orders from our own set and recomputing:

        1 dropped -> 1.130256      250 dropped -> 1.130256
      100 dropped -> 1.130256     1000 dropped -> 1.130255

Twelve percent of the rows can vanish and the ratio still matches to five
decimals, because the fee is near-proportional at every tier so every subset
inherits it. That makes the ratio decisive for the question O1 asked (13,03%
against 3,00% - a difference it discriminates overwhelmingly) and silent on
whether two row sets hold the same tickets. This check reads the per-row values
the ratio averages away.

WHAT IS ASSERTED
----------------
1. **Every witnessed tier still carries its witnessed gross**, as the tier's
   MODAL value. This is the real target: `process_shotgun_ticket` builds gross
   as `deal_price + deal_service_fee + deal_user_service_fee`, so dropping or
   double-counting a component moves EVERY row at EVERY tier, and the mode moves
   with them. FAILS.

2. **No witnessed tier has disappeared.** The merged CSV is append-only history,
   so a tier that sold cannot stop having sold. A vanished tier means rows were
   lost or rewritten, not that sales changed. FAILS.

3. Rows at an unwitnessed face, or at a witnessed face with an unwitnessed
   gross, are REPORTED with counts and never fail. See below.

WHAT HAPPENS WHEN SHOTGUN ADDS A TIER - AND IT HAS ALREADY HAPPENED
-------------------------------------------------------------------
A new price tier is new information, not a defect: our arithmetic is unchanged
and the new fee is simply unwitnessed by the export. Failing the build for it
would block a legitimate sale, and it is the false-defect direction - a check
that names data loss while the data is fine is the kind that gets acted on
fastest.

So a new tier prints as UNWITNESSED, with its count, its implied fee, and the
line to paste into `WITNESSED` once someone has decided the fee is right. The
count is the record: it moves when the schedule moves, and a number that changes
is a number someone has to explain.

**A tier carrying TWO different fees is not hypothetical.** `bordeaux_oct_2026`
has it today: 3 728 rows at face 95,00, of which 3 711 carry fee 12,37 and
**17 carry 0,50** - same product, same ticket type, all paid. So "face
determines fee" is false in the wild, on real data, at 0,2% of one event. That
is precisely why claim 1 is written on the MODE rather than on every row: a
systematic change moves the mode, and a handful of differently-priced rows does
not. Asserting every row would have failed on those 17 and called a fee
arrangement a code defect.

SCOPE: epk_2026, BECAUSE THAT IS WHAT THE EXPORT WITNESSES
----------------------------------------------------------
Each event negotiates its own prices, so the tiers are not shared - and a table
copied to an event no document covers would be an assumption wearing a check's
clothing. Other events get the same treatment when someone produces an export
for them.
"""

import collections
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / 'data' / 'epk_2026_merged.csv'

# (face, gross) as at the 2026-08-12 export. Fee and volume in the comment are
# the record, not the assertion - only the pair is asserted.
WITNESSED = (
    (0.00, 0.00),        # free            n=    4
    (38.64, 43.67),      # fee  5.03       n=  296
    (39.09, 44.18),      # fee  5.09       n=  671
    (43.18, 48.81),      # fee  5.63       n= 1620
    (47.73, 53.94),      # fee  6.21       n= 1763
    (50.00, 56.51),      # fee  6.51       n=   24
    (52.27, 59.08),      # fee  6.81       n= 1578  <- the export's extra ticket
    (57.26, 64.72),      # fee  7.46       n=   20
    (60.00, 67.82),      # fee  7.82       n=   69
    (65.00, 73.47),      # fee  8.47       n=   89
    (75.91, 85.80),      # fee  9.89       n=  925
    (80.00, 90.42),      # fee 10.42       n=  139
    (80.91, 91.45),      # fee 10.54       n=  696
    (85.91, 97.10),      # fee 11.19       n=  419
    (98.09, 110.87),     # fee 12.78       n=   20
    (105.00, 118.68),    # fee 13.68       n=   22
    (135.00, 152.58),    # fee 17.58       n=   36
)


def tiers(path):
    """{face: Counter({gross: n})} over the Shotgun rows of a merged CSV."""
    out = collections.defaultdict(collections.Counter)
    with open(path, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            if r.get('platform') != 'Shotgun':
                continue
            out[round(float(r['price']), 2)][round(float(r['gross_price']), 2)] += 1
    return out


def main():
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else CSV
    if not target.exists():
        print(f'{target}: missing')
        return 1
    seen = tiers(target)
    want = dict(WITNESSED)
    total = sum(sum(c.values()) for c in seen.values())
    try:
        shown = target.relative_to(ROOT)
    except ValueError:
        shown = target
    print(f'{shown}: {total} Shotgun row(s), {len(seen)} face value(s), '
          f'{len(want)} witnessed tier(s)\n')

    moved, gone, exceptions, unwitnessed = [], [], [], []
    for face, gross in WITNESSED:
        got = seen.get(face)
        if not got:
            gone.append(face)
            continue
        mode, n = got.most_common(1)[0]
        if mode != gross:
            moved.append((face, gross, mode, n, sum(got.values())))
        for g, k in got.items():
            if g != gross:
                exceptions.append((face, gross, g, k))
    for face, got in sorted(seen.items()):
        if face not in want:
            for g, k in got.most_common():
                unwitnessed.append((face, g, k))

    if exceptions:
        print(f'EXCEPTIONS - a witnessed tier with a different gross on some '
              f'rows: {len(exceptions)}')
        for face, gross, g, k in sorted(exceptions):
            print(f'  face {face:8.2f}  witnessed gross {gross:8.2f}, but '
                  f'{k} row(s) carry {g:8.2f} (fee {g - face:.2f})')
        print('  Reported, not failed. bordeaux_oct_2026 has 17 such rows at face')
        print('  95,00 today, so this is a real shape and not a code defect.')
        print()

    if unwitnessed:
        rows = sum(k for _, _, k in unwitnessed)
        print(f'UNWITNESSED - face values the export does not cover: '
              f'{len(unwitnessed)} ({rows} row(s), '
              f'{rows / total * 100:.2f}% of Shotgun volume)')
        for face, g, k in unwitnessed:
            print(f'  ({face:.2f}, {g:.2f}),'.ljust(28)
                  + f'# fee {g - face:6.2f}       n={k:5}')
        print('  A new tier is new information, not a defect - our arithmetic is')
        print('  unchanged and the fee is simply unwitnessed. Check the fee is')
        print('  right, then paste the line above into WITNESSED.')
        print()

    if gone:
        print(f'MISSING: {len(gone)} witnessed tier(s) no longer appear at all')
        for face in gone:
            print(f'  face {face:.2f} sold {dict(WITNESSED)[face]:.2f} and now '
                  f'has no rows')
        print('The merged CSV is append-only history, so a tier that sold cannot')
        print('stop having sold. Rows were lost or rewritten.')
        print()

    if moved:
        print(f'FAILED: {len(moved)} witnessed tier(s) no longer carry their '
              f'witnessed gross')
        for face, gross, mode, n, tot in moved:
            print(f'  face {face:8.2f}  witnessed {gross:8.2f}  now {mode:8.2f} '
                  f'on {n}/{tot} row(s)  (fee {gross - face:.2f} -> {mode - face:.2f})')
        print('The MODE moved, which a handful of odd rows cannot do - this is a')
        print('systematic change. gross_price is deal_price + deal_service_fee +')
        print('deal_user_service_fee; if one of those stopped being summed, every')
        print('tier moves together. Check process_shotgun_ticket against the')
        print('export before changing this table.')
        print()

    if moved or gone:
        return 1
    print(f'all {len(want)} witnessed tier(s) still carry their witnessed gross')
    return 0


if __name__ == '__main__':
    sys.exit(main())
