# Audit scope — one event, API to rendered page

**Status: a scope, not a run.** Nothing here has been executed. It says what can
be verified against something outside this project, what cannot, and what the
gap costs in figures.

The headline, stated first because it is the finding rather than the preamble:

> **Two of the four links in the chain have an external reference. The other two
> have none, and one of them carries 80% of a figure that is on every page.**

An audit that came back "everything checks out" would be worse than no audit,
because most of this chain cannot be checked from outside and saying otherwise
converts an unknown into an assurance.

---

## 0. What is already covered, and what that is worth

Sixteen checks run on every change. They have caught real defects — a live
edition's future rendering `0` instead of an em-dash, four of ten menus off a
393px screen, a section bar that never reached the page, eleven readouts on a
finished edition. That is not in question and is not re-litigated here.

What they cover is **internal consistency**: two implementations of the same
rule agreeing, or a rendered page matching its own payload. `check_b1_switch`
reported 198/198 green over a shipped defect because both sides carried the same
error. That is the exact limit of the suite, and it is why this document exists.

The one check that is different in kind is `check_payout_reconciliation`: it
holds our DICE figures to a *reddition de comptes* Leo obtained, agreeing to
**one ticket in 9 327**. That is the model for everything below — an external
document, compared to pipeline output, with the residual named.

---

## 1. The chain, link by link

| # | link | external reference available? |
|---|---|---|
| A | platform API → raw fetch | **no** — nothing outside our own call |
| B | raw fetch → merged CSV | **partial** — DICE only, via the payout statement |
| C | merged CSV → payload arithmetic | **no external** — strongest substitute below |
| D | payload → rendered page | covered, and appropriately so |

### A. Platform API → raw fetch

Nobody has verified that what DICE and Shotgun return matches what we store.
There is no way to do this from outside the API: the API *is* the source. What
can be done is bound the failure modes that would be silent:

- **pagination loss** — Paris XXL is ~220 pages at 0.8s pacing. A truncated
  fetch produces a smaller, entirely plausible number. Verifiable *internally*
  against the platform's own reported total, if it reports one.
- **filter drift** — `is_paid`, refunds, cancellations. A ticket that changes
  state after we stored it is not re-read.
- **duplicate or dropped orders across pages.**

None of these is currently asserted. All three would render as a believable
figure.

### B. Raw fetch → merged CSV

**DICE: proved.** 9 327 paid, 624 936,39 brut TTC, 38 214,52 commissions,
reconciling to one 55,28 ticket whose 59,00 gross the statement does not carry.
The statement's worked tiers match ours verbatim.

**Shotgun: nothing.** No statement, no back-office export, no independent
figure. This is the gap the 13,03% multiplier stands in for.

### C. Merged CSV → payload arithmetic

No external reference exists for the *derived* quantities — velocity, the
projection replay, the anchoring snap, presence. There cannot be one: nobody
outside this project computes them.

The strongest available substitutes, in descending order, and none of them is an
external reference:

1. **Contractual terms from `api.shotgun.live/deals`** — `deal_service_fee`,
   `deal_user_service_fee`, `deal_vat_rate`. Same vendor and same credential as
   the ticket fetch, so *not* independent of the API — but independent of our
   arithmetic, and it is the only statement of the fee structure we can read
   without Leo obtaining a document. **This is the highest-value unexplored
   item in this document and it is a day's work, not a chase.**
2. **A finished edition's own final numbers**, compared to what we projected for
   it at J−30. Retrospective rather than external, but the outcome is not
   something our code chose.
3. **Two of our components agreeing** — explicitly *not* a reference. Labelled
   as such wherever it appears.

### D. Payload → rendered page

Covered by the suite, and this is the one link where internal consistency is the
*right* standard: the payload is the source of truth for the page by definition.

---

## 2. (c) What the missing Shotgun payout statement costs — in figures

The exposure is narrower than "it is under every Shotgun figure", and narrower
than we have been saying. **The multiplier does not touch revenue.**

`dashboard_payload.totals()` computes `rev` and `avg` from `price` — face value
TTC. `gross_price` reaches the payload only as the third element of `plat`, and
only two things read it: `moneyBar()` per platform, and the "Prix affiché → net
encaissé" bar. Both use it for one derived quantity, `fee = paid − face`.

**So the unverifiable surface is: the booking-fee segment of two bars on the
Revenus card. Every other figure on every page — revenue, net HT, TVA, all
ticket counts, velocity, presence, suivi, projections — is face-value or
count-based and is unaffected.**

That is the good news. Here is the size of what remains, measured over all six
stored events (87 523 paid tickets):

| page | Shotgun face TTC | fee shown now | if 1.030 | overstated by | if ~1.110 | overstated by |
|---|---:|---:|---:|---:|---:|---:|
| parisxxl | 1 416 586 | 184 531 | 42 498 | **142 033** | 155 824 | 28 706 |
| bordeaux | 1 171 874 | 152 605 | 35 156 | **117 449** | 128 906 | 23 699 |
| bordeaux_oct | 612 638 | 79 277 | 18 379 | **60 898** | 67 390 | 11 887 |
| epk | 454 576 | 59 211 | 13 637 | **45 573** | 50 003 | 9 207 |
| rennes | 112 670 | 14 671 | 3 380 | **11 291** | 12 394 | 2 277 |
| geneve | 76 158 | 9 916 | 2 285 | **7 631** | 8 377 | 1 539 |
| **total** | **3 844 502** | **500 210** | 115 335 | **384 875** | 422 895 | 77 315 |

Read that as a range, because the two rival formulas are a document conflict
rather than a measurement:

- if the **spec** is right (1.030), the fee segment is **4,3× too large** and
  overstates by **384 875 €**
- if the **~11% hypothesis** is right, it overstates by **77 315 €**
- if the **code** is right (1.1303), it is correct and the cost is zero

The displayed fee segment across all six pages totals **623 092 €**, of which
**122 882 € is DICE and proved**, and **500 210 € is Shotgun and unverified** —
**80,3%** of that bar is resting on the disputed number.

**Per-page, the number to quote to Leo is Paris XXL: a single bar segment that
could be wrong by 142 033 €.**

Two things that make this worse than the arithmetic suggests, and one that makes
it better:

- worse: the ratio is *uniform* at 1.1302–1.1303 across six events and 57 951
  tickets. Uniformity reads as correctness and is not — it only says the code
  applies one formula consistently.
- worse: `moneyBar` derives its multiplier from the data rather than hardcoding
  it, which was the right call and means a wrong `gross_price` propagates
  silently instead of failing.
- better: **the error is confined to one visual element.** No decision anyone
  makes from these dashboards — pace, sell-out date, capacity — moves at all.

---

## 3. (d) What it would cost, and what should be standing

| item | one-off cost | should it be standing? |
|---|---|---|
| **Shotgun `deals` probe** — read the contractual fee terms and compare to the 1,1303 the data shows | ~½ day | **yes, weekly.** Terms change per deal; a renegotiated fee would silently change every future figure |
| **Pagination completeness** — assert stored ticket count against the platform's own reported total | ~½ day, if either API reports a total | **yes, per fetch.** This is the one that fails silently and the cheapest to catch |
| **DICE reconciliation** — already built | done | **already standing.** Extend to a second statement when one exists |
| **Shotgun reconciliation** — blocked | — | blocked on a document only Episode or Sonora can produce |
| **Projection retrospective** — how the forecast did against a finished edition | already specified, ~1 C3 | **yes**, and it doubles as the only outside-ish check on link C |
| **Refund/state drift** — re-read a sample of old orders and compare | ~1 day | probably not; low value against cost |

A reconciliation that runs once tells you about today. The two marked "yes,
weekly/per fetch" are the ones where a break would otherwise be invisible until
someone questioned a number — which, on the evidence of this project, is how
every defect here has been found.

---

## 4. What Leo has to decide

1. **How much runs before cutover.** The recommendation is the two cheap
   standing checks (deals probe, pagination completeness) and nothing else.
   Neither depends on anyone outside the project.
2. **Whether the 142 033 € figure is worth another approach to Episode or
   Sonora.** Three weeks of "it is under every Shotgun figure" has not moved it.
   A number on one page might.
3. **Whether shipping a knowingly-unverified fee segment is acceptable at
   cutover.** It is acceptable to us if it is *stated* — the honest option is
   the Revenus tooltip saying the Shotgun fee is derived and unconfirmed, which
   costs one sentence and converts a silent unknown into a declared one.

Nothing in this document blocks cutover. The gap has been there for the life of
the project; what is new is that it now has a size.
