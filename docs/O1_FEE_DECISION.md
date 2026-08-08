# O1 — half closed. The remaining ask is Shotgun's.

> **UPDATE 2026-08-08 — the DICE side is settled against an external document.**
> Leo produced a *reddition de comptes* for `bordeaux_2026` (DICE, 11-13 June
> 2026). It reconciles against our stored CSV to **one ticket out of 9,327**.
> The ask below is therefore no longer "three numbers for one ticket" in
> general — **it is specifically a SHOTGUN payout statement.** Skip to
> "What is still needed".

## What the DICE statement proved

| | statement | our CSV | delta |
| --- | ---: | ---: | ---: |
| participants payants | 9 327 | 9 327 | — |
| participants gratuits | 2 | 2 | — |
| total brut TTC | 624 936,39 | 624 991,67 | **+55,28** |
| commissions DICE TTC | 38 214,52 | 38 218,24 | **+3,72** |
| TTC + commissions | 663 150,91 | 663 209,91 | **+59,00** |

All three deltas are the same single ticket: 55,28 + 3,72 = 59,00, a listed
tier price to the cent. Not a rounding drift — a rounding drift would not land
exactly on a tier and would not sum.

**The semantics, verbatim from the statement:**

```
PRIX HT       43,19     excluding VAT
PRIX TTC      45,57     <- our `price`.  face value, VAT 5,5% included
+ commission   3,43     DICE booking fee
buyer pays    49,00     <- our `gross_price`
```

All five tiers match ours verbatim — 45,57 / 50,42 / 55,28 / 60,13 / 64,99 —
and the VAT split reconciles to the cent: 624 936,39 / 1,055 = **592 356,77 HT**
and **32 579,62 VAT**, both exactly as printed.

This is an **external** confirmation of the identity the field probe found
internally (`fullPrice + diceCommission = total`). Two independent routes to the
same arithmetic is a much stronger claim than either alone.

`verify/check_payout_reconciliation.py` pins it. The tolerance is that one known
ticket and nothing else — a second unexplained ticket is a finding, not noise.

## What is still needed

**A Shotgun payout statement**, for any Shotgun-majority event. The question is
now narrow and precise:

> Is Shotgun's 13,03% multiplier — `deal_price` + `deal_service_fee` (10%) +
> `deal_user_service_fee` (3%) — a **buyer-facing total**, the way DICE's
> `fullPrice + commission` turned out to be? Or is `deal_service_fee` deducted
> from the promoter, as DICE's `commission` field would have been if it were
> non-zero?

Leo does not have access to Shotgun's payment structure, so this likely has to
come from **Episode or Sonora**, who hold the two organizer accounts.

The decision table below is unchanged and still applies — to Shotgun only.

---

# The original ask, now Shotgun-only

**One line of ground truth settles a formula that touches every revenue figure
in the product.** This document is the ask, and the decision table.

Nothing here is an engineering question. The code is unambiguous, the data is
consistent, and both candidate formulas are defensible. What is missing is a
fact about what Shotgun actually charges a buyer, and only a payout statement
or Shotgun themselves can supply it.

---

## The ask, in one paragraph

> For **one** Shotgun ticket on any of our events (DICE is settled), we need three numbers from a
> payout statement or the Shotgun back office: the **face price**, the **total
> the buyer was actually charged**, and the **amount we were paid** for it.
> Ideally a €95 or €100 face ticket, because the arithmetic is then legible by
> eye. One ticket is enough. One line.

That is the whole request. It does not need a data export, a report, or
anything containing personal data — just three figures for a single known
ticket.

---

## Why it cannot be answered from the API

The Shotgun `/tickets` payload carries both fees and does not say who bears
either **[measured, 600 tickets, 6 events]**:

```
deal_price             9500     face
deal_service_fee        950     10.0% of face
deal_user_service_fee   287      3.0% of face
deal_producer_cost        0
deal_vat_rate         0.055
```

There is no field stating which is added to the buyer's total and which is
deducted from ours. The 44 keys are now known to be the whole ticket payload,
so no additional field is coming. DICE, by contrast, decomposes exactly —
`fullPrice + Σ fees.dice = total`, to the cent — which is how we know the
question is Shotgun-specific and not a general modelling gap.

---

## The candidates, on a €100 face ticket

| formula | buyer pays | ratio | who says so |
| --- | ---: | ---: | --- |
| face only | €100.00 | 1.000 | nobody |
| face + user service fee (3%) | €103.00 | 1.030 | **`HANDOFF.md`'s column spec, and its worked example** |
| face + service fee (10%) | €110.00 | 1.100 | nobody yet — but closest to the residual |
| **face + both (13%)** | **€113.00** | **1.130** | **`fetch_csv.py`, i.e. what we actually ship** |
| face + both + VAT 5.5% on the fees | €113.71 | 1.137 | untested — but **5,5% is confirmed** as the rate, printed on the DICE statement and equal to Shotgun's `deal_vat_rate` |

**The spec and the code have disagreed for the life of the project**, both
internally consistent, neither ever failing. See "the two-document trap" in
`HANDOFF.md`.

What we ship today, measured over 56,785 paid Shotgun rows across all six
events, is **1.1302–1.1303** — uniform, with no event deviating. That is
10.0% + 3.0%, confirming the code does what it appears to do.

---

## The decision table

Let **R** = (what the buyer was charged) ÷ (face price), from Leo's one ticket.

| if R ≈ | then the buyer bears | formula | what changes |
| ---: | --- | --- | --- |
| **1.03** | `deal_user_service_fee` only | `deal_price + deal_user_service_fee` | The code is wrong. Every Shotgun revenue figure we have ever published is **~9.7% too high**. The spec was right all along. |
| **1.10** | `deal_service_fee` only | `deal_price + deal_service_fee` | Both documents are wrong. Revenue **~2.7% too high**. This is the value the standing ~2% overshoot points at. |
| **1.13** | both | *unchanged* | The code is right, the spec's example is wrong, and the ~2% overshoot has a **different cause** that stays open. |
| **1.137** | both, plus VAT on the fees | `+ (fees × deal_vat_rate)` | Code is nearly right and slightly low. |
| anything else | — | — | Stop and bring the number back; none of our models fit. |

**The ~2% overshoot is the reason 1.10 is the live hypothesis.** We ship
1.1303. If we are ~2% high, the truth is near 1.108 — which is
`deal_service_fee` alone, or `deal_user_service_fee` plus something we have not
identified. It is not 1.03; that would make us ~9.7% high, and we would have
noticed.

**Caveat on that reasoning:** the ~2% figure predates this investigation and
nobody has restated what it was measured against. Confirm the baseline is a
buyer-facing gross total and not a net-to-producer figure before leaning on it
— a net figure would invert the whole argument.

---

## Rules while this is open

1. **Do not change the formula.** A wrong correction is worse than a
   known-wrong constant, because the known-wrong one is documented and this one
   now is. Nothing about the current behaviour is secret.
2. **`verify/check_spec_example.py` pins the conflict.** It runs `HANDOFF.md`'s
   own worked example through `fetch_csv.process_shotgun_ticket` and allows
   exactly the recorded delta (97.87 vs 107.37). Any *other* disagreement fails,
   including someone editing the spec to match the code, or the code drifting to
   a third value.
3. **When the answer lands:** correct whichever of the two is wrong — spec or
   code — then set `KNOWN_CONFLICT = None` in that script. It becomes a strict
   equality check and stays one.
4. **A change to the formula is a change to history.** Every committed merged
   CSV carries the current `gross_price`. Decide separately whether to refetch
   and rewrite, or to apply the new formula going forward and mark the seam.
   Comparison views span both sides of it.


---

## CC2 — the revenue disclaimer is wrong for DICE. Raised, not changed.

`dashboard_template.html:506` currently reads:

> Revenu = valeur faciale (prix affiché au client). Les commissions prélevées
> par les plateformes (DICE, Shotgun) ne sont pas déduites.

**Two problems, and the statement settles both for DICE.**

**1. It implies a deduction that does not exist.** The statement shows
`COMMISSION DU PROMOTEUR 0,00`, `RÉTROCESSION 0%`, and `PAIEMENT AU PROMOTEUR`
equal to the full TTC total. DICE deducts **nothing** from the promoter — the
fee is entirely buyer-borne, added on top. "Les commissions ... ne sont pas
déduites" describes a subtraction that never happens, so a reader corrects for
it mentally and lands lower than the truth.

**2. OPEN AMBIGUITY — "prix affiché au client" has two defensible readings and
the data cannot choose.** I previously called this a second error. That was an
over-claim; it is unresolved, not wrong.

`run.py:1243` does `total_revenue += t['price']`, so the card sums the 45,57
TTC face. Whether that matches "le prix affiché au client" depends on *where*
the client sees a price:

| reading | value | is the card right? |
| --- | ---: | --- |
| advertised on the event listing | 45,57 | **yes** — DICE shows the face and adds the booking fee as a separate line at checkout |
| total at the payment step | 49,00 | **no** — that is `gross_price` |

Both are ordinary meanings of *affiché*. Settling it needs someone to look at
what DICE and Shotgun actually render at each step of the funnel — a Leo
question, not a code question, and not answerable from any field we hold.

**Keep it separate from problem 1.** The deduction error is established; this is
not. Folding them into one rewrite would ship an unverified claim under cover of
a verified one.

**Whatever it resolves to, two artefacts change together:** this template string
and the dashboard mock's "prix affiché à l'acheteur".

**What is genuinely not deducted is VAT.** On `bordeaux_2026` that is
**32 579,62** of 624 936,39, leaving 592 356,77 HT. The promoter remits it. A
sentence that named VAT would be true and useful; the current one names
commissions and is neither.

**Not changed, for two reasons.** It is a copy decision, not an engineering one.
And the sentence may be **right for Shotgun and wrong for DICE** — that is
exactly the open half of O1. Rewriting it now risks making it wrong for both.

**When it is decided:** `dashboard_template.html` is do-not-modify, so the new
copy ships as a postprocess pass, like every other markup change here.
