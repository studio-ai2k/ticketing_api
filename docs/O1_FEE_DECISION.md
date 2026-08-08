# O1 — what to ask Leo, and what each answer means

**One line of ground truth settles a formula that touches every revenue figure
in the product.** This document is the ask, and the decision table.

Nothing here is an engineering question. The code is unambiguous, the data is
consistent, and both candidate formulas are defensible. What is missing is a
fact about what Shotgun actually charges a buyer, and only a payout statement
or Shotgun themselves can supply it.

---

## The ask, in one paragraph

> For **one** Shotgun ticket on any of our events, we need three numbers from a
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
| face + both + VAT 5.5% on the fees | €113.71 | 1.137 | untested |

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
