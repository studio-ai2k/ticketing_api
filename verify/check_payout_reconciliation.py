#!/usr/bin/env python3
"""
Hold the DICE side of `gross_price` to the payout statement it was proved against.

    python verify/check_payout_reconciliation.py

On 2026-08-08 Leo produced a *reddition de comptes* for `bordeaux_2026` (DICE,
11-13 June 2026). It reconciles against our stored CSV to **one ticket out of
9,327** - a single 55,28 ticket whose 59,00 gross the statement does not carry.
Every other figure agrees to the cent, and the statement's own worked tiers
match ours verbatim:

    PRIX HT      43,19    excluding VAT
    PRIX TTC     45,57    <- our `price`.  face value, VAT 5,5% included
    + commission  3,43    DICE booking fee
    buyer pays   49,00    <- our `gross_price`

That is an EXTERNAL confirmation of the arithmetic identity the field probe
found internally (`fullPrice + diceCommission = total`), which is a much stronger
claim than either on its own.

WHY PIN IT
----------
O1 - which Shotgun fee the buyer bears - is still open, and settling it will mean
editing `process_shotgun_ticket`, three lines from `process_dice_*`. The DICE
numbers are now the only figures in this project validated against a document
someone outside it produced. Losing them to a stray edit would be losing the
single fixed point we have.

So this asserts the reconciliation itself, not the formula. If someone changes
how DICE gross is computed, these totals move and this fails, and the failure
names the statement rather than the code.

The tolerance is the one known ticket and nothing else. It is not a fuzz factor:
a second unexplained ticket is a real finding and should stop the build.
"""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / 'data' / 'bordeaux_2026_merged.csv'

# Reddition de comptes, bordeaux_2026, DICE, 11-13 June 2026. Held by Leo.
STATEMENT = {
    'paid':        9327,
    'free':           2,
    'brut_ttc':  624936.39,
    'commissions': 38214.52,
    'total_ttc':  663150.91,
    'vat_rate':      0.055,
    'ht':        592356.77,
    'vat':        32579.62,
}

# The single ticket our CSV holds and the statement does not.
KNOWN_EXTRA = {'price': 55.28, 'commission': 3.72, 'gross': 59.00}

# Tiers printed on the statement: (TTC face, DICE commission, buyer total).
STATEMENT_TIERS = [
    (45.57, 3.43, 49.00),
    (50.42, 3.58, 54.00),
    (55.28, 3.72, 59.00),
    (60.13, 3.87, 64.00),
    (64.99, 4.01, 69.00),
]

FAILURES = []


def check(label, got, want, tol=0.005):
    ok = abs(got - want) <= tol if isinstance(want, float) else got == want
    print(f'  {"ok  " if ok else "FAIL"}  {label:34} {got!r}' + ('' if ok else f'  != {want!r}'))
    if not ok:
        FAILURES.append(label)


def main():
    if not CSV.exists():
        print(f'FAIL: {CSV} is missing - the reconciliation cannot be checked')
        return 1
    rows = [r for r in csv.DictReader(CSV.open(encoding='utf-8-sig'))
            if r['platform'] == 'DICE']
    paid = [r for r in rows if r['is_paid'] == '1']
    free = [r for r in rows if r['is_paid'] != '1']
    price = sum(float(r['price']) for r in paid)
    gross = sum(float(r['gross_price']) for r in paid)

    print('counts')
    check('paid participants', len(paid), STATEMENT['paid'])
    check('free participants', len(free), STATEMENT['free'])

    print('\ntotals, allowing exactly the one known ticket')
    check('sum(price)  - 55.28', price - KNOWN_EXTRA['price'], STATEMENT['brut_ttc'])
    check('sum(gross)  - 59.00', gross - KNOWN_EXTRA['gross'], STATEMENT['total_ttc'])
    check('commissions -  3.72', (gross - price) - KNOWN_EXTRA['commission'],
          STATEMENT['commissions'])

    print('\nthe gap is ONE ticket, not a rounding drift')
    # If the deltas were rounding they would not be equal to a listed tier
    # price to the cent, and they would not sum.
    check('price delta', round(price - STATEMENT['brut_ttc'], 2), KNOWN_EXTRA['price'])
    check('gross delta', round(gross - STATEMENT['total_ttc'], 2), KNOWN_EXTRA['gross'])
    check('face + commission = gross',
          round(KNOWN_EXTRA['price'] + KNOWN_EXTRA['commission'], 2), KNOWN_EXTRA['gross'])

    print('\nVAT: `price` is TTC, and 5.5% is deal_vat_rate on the Shotgun side')
    check('HT', round(STATEMENT['brut_ttc'] / (1 + STATEMENT['vat_rate']), 2), STATEMENT['ht'])
    check('VAT', round(STATEMENT['brut_ttc'] - STATEMENT['brut_ttc'] / (1 + STATEMENT['vat_rate']), 2),
          STATEMENT['vat'])

    print('\nthe statement tiers exist in our data, verbatim')
    have = {(round(float(r['price']), 2), round(float(r['gross_price']), 2)) for r in paid}
    for face, comm, total in STATEMENT_TIERS:
        present = (face, total) in have
        print(f'  {"ok  " if present else "FAIL"}  TTC {face:>6.2f} + {comm:.2f} = {total:>6.2f}')
        if not present:
            FAILURES.append(f'tier {face}')

    print()
    if FAILURES:
        print(f'FAILED: {len(FAILURES)} - {", ".join(map(str, FAILURES))}')
        print('The DICE numbers no longer match the payout statement they were')
        print('proved against. Either the formula moved or the CSV did.')
        return 1
    print('DICE reconciles to the payout statement, to one known ticket in 9,327')
    return 0


if __name__ == '__main__':
    sys.exit(main())
