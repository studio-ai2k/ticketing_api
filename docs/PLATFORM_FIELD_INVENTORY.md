# Platform field inventory — Shotgun vs DICE

For the Campagne page, which is **PARKED** — see `HANDOFF_CC5.md` §2.3 for
the ruling and where it may go. Inventory only; nothing here has been built.

This document is not stale and is not orphaned: it is the evidence Campagne
would resume from, and it moves with the concept if the concept moves. Its
probe results are measurements of the live platforms and stay true whether or
not the page is ever built.

## How each claim below is evidenced

Three different strengths, marked throughout:

| mark | means |
| --- | --- |
| **[sample]** | observed on a real captured Shotgun ticket — `shotgun_schema.json`, one page of 100 from `bordeaux_2026` |
| **[schema]** | present in DICE's live introspection dump — `dice_schema.json` |
| **[measured]** | checked against our own committed data just now |
| **[probe]** | not answerable from either dump — needs a live call |

### Confidence, per platform — and neither is complete

**Shotgun: one sample, one endpoint, completeness UNKNOWN.**
44 fields observed on *one ticket* from *one event* via *one endpoint*. That
proves those 44 exist. It does not prove they are all there is. Fields that
only populate for a structurally different event — seated, tabled, bundled —
would not appear: `ticket_seating` is `null` in the sample but is plainly a
real concept. **Treat 44 as provisional.** See X3 below for what would settle
it.

**DICE: complete for object types and field names. NOT complete otherwise.**
This is a correction to the assumption that introspection is complete by
construction — it is complete for what the introspection *query* asked for, and
this one asked for one dimension out of four:

| dimension | in `dice_schema.json`? |
| --- | --- |
| object types and their field names/types | **yes** — 53 objects |
| enum **values** | **no** — 5 enums named, zero values |
| input-object **fields** | **no** — 15 inputs named, zero fields |
| field **arguments** | **no** |

The proof it matters: `viewer.orders(first:, after:, where: {eventId: {eq:}})`
runs in production every day, and **not one of those arguments appears in the
dump.** Reading the dump alone, you would conclude `viewer.orders` takes no
arguments and cannot be filtered.

Named but empty: `EventCostCurrency`, `EventImageType`, `EventState`,
`PriceTierTypes`, `TicketFeeCategory` (this one blocks Q4), and fifteen input
objects including `OrderWhereInput`, `ReturnWhereInput` and
`TicketTransferWhereInput`.

That last pair is load-bearing for X2: their existence is how we know
`viewer.returns` and `viewer.ticketTransfers` are event-scopeable the same way
orders is, even though the dump shows them taking no arguments.

### X3 — Shotgun endpoint enumeration: not discoverable from here

**This section is what we knew before the probe ran; the answers are in
"Probe results" immediately below. Kept because the reasoning about what each
outcome would license is what makes the result readable.**

The question is whether `/tickets` is the whole API or the only door we happen
to have a key to. Two ways to settle it, and the honest answer on both is
**no, not from this container.**

**1. Is anything served that lists the endpoints?** Unanswerable here.
`api.shotgun.live` and `developers.shotgun.live` are both blocked by this
environment's network policy — `curl` returns `000`, a connection that never
opened, not a 404 that would have told us something. So even a negative result
is unavailable: we cannot distinguish "Shotgun serves no index" from "we could
not ask". This is not a Shotgun property, it is ours, and it has one fix —
**ask from an Actions runner**, which is where every live fetch already runs.
`scripts/probe_shotgun_fields.py::probe_discovery` does exactly that against
nine candidate paths (`/`, `/openapi.json`, `/swagger.json`,
`/.well-known/openapi.json`, `/docs`, `/v1/`, `/events`, `/orders`, `/deals`)
and prints the status code for each. A 401 or 403 is the interesting answer: it
means the path exists and our token is merely not scoped for it. A 404 across
all nine means `/tickets` is very likely all there is.

**2. Is 44 the ceiling on a ticket?** Answerable, and cheaply — this is the
half that does not need Shotgun to volunteer anything. `shotgun_schema.json`
records one ticket from one event, which proves those 44 keys exist and proves
nothing about the rest. But we have **six active events across two organizer
accounts**, structurally unalike (multi-day festivals, a one-night event, two
countries). Taking the first page from each and unioning the keys turns one
sample into ~600 tickets from six events. `probe_fields` reports:

- the **union** — any key beyond the 44 means 44 was never the ceiling;
- the **intersection** — a key present on some events and absent from others is
  the more likely shape, and tells us which fields are conditional;
- the **null rate per key** — of the 44, which are actually populated. A field
  that is 100% null everywhere is documented, not available.

It prints key names and null *rates* only, never a value: eleven of the 44 are
personal and this log is public.

**What each outcome licenses.** If the union is 44, that is *evidence* the 44
are the shape — not proof, since six events of ours may all be structurally
alike in the way that matters (none is seated or tabled, which is precisely the
case `ticket_seating` hints at). If the union exceeds 44, the inventory below is
incomplete and needs rerunning before anything is built on it.

**Until that probe runs, treat 44 as provisional, not complete.** No claim in
the table below turns on a field we have not seen; the risk is entirely of
omission — a Campagne metric we could have built and did not know was there.

---

## Probe results — run 31235118312, 2026-08-08

Both jobs ran green. Everything below is **[probe]** promoted to **[measured]**,
and four claims in this document changed as a result. Marked **⚠** where a
probe contradicted what was written here before.

### X3a — Shotgun *does* have a second endpoint

Nine paths, and the interesting thing is that they did **not** all answer the
same way:

| path | status |
| --- | --- |
| `/events` | **400** |
| `/` | 429 |
| `/openapi.json`, `/swagger.json`, `/.well-known/openapi.json`, `/docs`, `/v1/`, `/orders`, `/deals` | 404 |

**⚠ `GET /events` returns 400, not 404.** A 400 is a route that exists and
rejected the request — almost certainly for the same missing
`token`/`organizer_id` that `/tickets` requires. Seven sibling paths return 404
from the same host in the same run, so this is not the host answering 400 to
everything. **`/tickets` is not the whole API.** Nothing was fetched from
`/events` — the probe sends no credentials to discovery paths — so what it
returns is unknown, but an event-level endpoint would plausibly carry capacity,
tier and phase metadata that the per-ticket payload does not, which is exactly
the gap Q1 describes on the Shotgun side.

The 429 on `/` is not evidence of anything; it is a rate limit, and the probe
made ten requests in a few seconds.

**No index, spec or documentation is served.** So the endpoint list stays
guesswork — but it is now guesswork with one confirmed hit.

### X3b — 44 is the shape, across 600 tickets

First page of all six active events, both organizer accounts:

```
paris_xxl_2026 / bordeaux_2026 / epk_2026 /
bordeaux_oct_2026 / geneve_2026 / rennes_2026 …… 100 tickets, 44 keys each
tickets inspected  600
UNION              44
INTERSECTION       44
```

Union equals intersection equals 44. **No event has a key another lacks, and
nothing appears beyond the sampled 44.** That is much stronger than one ticket
from one event — though still not proof, since none of our six is seated or
tabled, which is the case `ticket_seating` hints at. Combined with X3a it now
reads: *the ticket payload is fixed at 44; whatever else Shotgun knows lives at
another endpoint, not in a conditional field here.*

Five keys are 100% null across all 600: `ticket_seating`, `ticket_scanned_at`,
`ticket_canceled_at`, `event_canceled_at`, `contact_company_name`. Documented,
not available.

**One number that matters for the Campagne page:** `deal_sub_category` is
**13.5% null**, and it is the source of `product_name`. Any Shotgun
product-level breakdown silently drops an eighth of its rows unless it falls
back to `deal_title`.

### P1 / Q1 — ⚠ phases are allocation-driven, and `PriceTier.time` is not the boundary

`PriceTierTypes` has exactly two values: **`allocation`** and **`time`**. Every
tiered ticket type on `rennes_2026` is `priceTierType='allocation'`, and
`PriceTier.time` is `None` on all twelve tiers. So `time` is populated only for
time-scheduled ladders, which we do not use — **there is no phase boundary
datetime to read.** Q1 below said `time` was "probably when the tier
activates"; that is right about the field and wrong about its usefulness to us.

What we get instead is better. Allocations reproduce **exactly** in our own
committed CSV **[measured]**:

| ticket type | tier | DICE allocation | rows at that price | window |
| --- | --- | ---: | ---: | --- |
| PASS VENDREDI | PHASE 1 | 100 | **100** | 17:00:18 → 17:55:00 |
| PASS VENDREDI | PHASE 2 | 1000 | 557 | 17:55:00 → … |
| PASS SAMEDI | PHASE 1 | 100 | **100** | 17:00:17 → 20:57:08 |
| PASS SAMEDI | PHASE 2 | 1000 | 692 | 17:03:14 → … |
| PASS 2 JOURS | PHASE 1 | 300 | **300** | 17:00:14 → 13 Jul |
| PASS 2 JOURS | PHASE 2 | 1000 | 496 | 18:05:31 → … |

Three exact hits on three allocations. **Phase boundaries are computable
without any new field** — cut the per-ticket-type sales sequence at the
cumulative allocation.

Three cautions, all real:

1. **Ladders are per ticket type, and they do not run in step.** VENDREDI
   handed over cleanly at 17:55:00. SAMEDI's PHASE 2 opened at 17:03 while
   PHASE 1 still had four hours of sales left. Aggregate the six ladders into
   one "phase" axis and you get overlapping phases that never existed.
2. **PASS 2 JOURS PHASE 1 sold from 2 June to 13 July, alongside PHASE 2 from
   the first night.** A six-week overlap is far too long for a checkout hold.
   The likely explanation is returns — 28 on this event — freeing a PHASE 1
   slot that the next buyer takes at the old price. That the count is *exactly*
   300 rather than more suggests returned tickets are already netted out of
   `viewer.orders`, which would be good news, but it is inference: **the check
   is to reconcile `viewer.orders.totalCount` against the same event's
   returns.**
3. **THE LAST TIER NEVER CLOSES.** A routine expecting every phase to have an
   end will either wait forever or invent one. Every PHASE 2 window in the
   table above ends in an ellipsis, and that is the data rather than a
   formatting choice. *(Lifted from
   `redesign/DD4_DD5_DIAGNOSIS_309c118.md:44`, retired in the same commit once
   this was the only sentence in it that existed nowhere else in the tree.)*

Also worth recording: for a tiered ticket type, `faceValue`, `price` and
`totalTicketAllocationQty` on the **type** are all `0`. The real numbers live on
the tiers. Anything reading the type-level price for a tiered product reads
zero.

### P2 / Q4 — ⚠ DICE's fee arithmetic is exact, which moves O1 onto Shotgun

One real ticket, in cents:

```
fullPrice 8877   total 9350   commission 0   diceCommission 473
fees  [{BOOKING, dice 200, promoter 0}, {PROCESSING, dice 273, promoter 0}]
```

Two identities hold exactly: **`Σ fees.dice = diceCommission`** (200 + 273 =
473) and **`fullPrice + diceCommission = total`** (8877 + 473 = 9350). Every
`promoter` is 0, and `commission` is 0.

`TicketFeeCategory` has 18 values — `ADDITIONAL_PROMOTER`, `BOOKING`,
`BOX_OFFICE`, `CHARITY_DONATION`, `DEPOSIT`, `EXTRA_CHARGE`, `FACILITY`,
`FOOD_AND_BEVERAGE`, `MEET_AND_GREET`, `PAID_WAITING_LIST`, `FULFILMENT`,
`PRESALE`, `PROCESSING`, `SALES_TAX`, `TIER_DIFF`, `VENDOR`, `VENUE`,
`VENUE_LEVY` — of which only `BOOKING` and `PROCESSING` occur on our event
(50 of each across the sample).

**This closes half of Q4 and narrows O1.** The DICE side of `gross_price`
(`total / 100`) is now *proven* correct rather than assumed — the decomposition
is complete and adds up. Whatever the ~2% is, it is Shotgun-side. That is a
smaller search than "one of two platforms".

It also weakens my own earlier suspicion, in the direction nobody expected:
DICE's buyer-borne fee here is **5.33%** of face, while Shotgun's
`deal_user_service_fee` is **3.0%**. If Shotgun's buyer-borne fee were really
the larger `deal_service_fee` (10.0%), our Shotgun gross would be too *low*.
Which way the 2% runs therefore discriminates between the two hypotheses, and
that measurement should be step one on O1 — before anyone touches the formula.

### P2 follow-up — confirmed against a payout statement, 2026-08-08

Leo produced a *reddition de comptes* for `bordeaux_2026` (DICE). It reconciles
against our CSV to **one ticket out of 9,327**, and it names the semantics the
probe could only infer:

```
PRIX HT       43,19     excluding VAT
PRIX TTC      45,57     <- our `price`.  face value, VAT 5,5% INCLUDED
+ commission   3,43     DICE booking fee
buyer pays    49,00     <- our `gross_price`
```

All five tiers verbatim — 45,57 / 50,42 / 55,28 / 60,13 / 64,99 — and the VAT
split to the cent (624 936,39 / 1,055 = 592 356,77 HT + 32 579,62 VAT).

Three things this settles that the probe alone could not:

1. **`price` is TTC, not HT.** The probe showed `fullPrice` and `total` and
   their difference; it could not say which side of VAT `fullPrice` sits on.
   It is TTC. Anything computing a net-of-VAT figure must divide by 1,055.
2. **The promoter bears nothing.** `COMMISSION DU PROMOTEUR 0,00`,
   `RÉTROCESSION 0%`, `PAIEMENT AU PROMOTEUR` = the full TTC total. The
   `promoter: 0` the probe saw on every `TicketFee` is the real commercial
   arrangement, not an artefact of the sample.
3. **5,5% is the VAT rate**, and it equals Shotgun's `deal_vat_rate` — so if
   the Shotgun ~2% overshoot is VAT-related, this is the number.

Pinned by `verify/check_payout_reconciliation.py`.

### P1 follow-up — the phase taxonomy is real, and named

The statement carries the phase names we had been reconstructing from price
steps alone:

| tier | name |
| --- | --- |
| Phase 1 | Super Early Bird |
| Phase 2 | Early Bird |
| Phase 3 | Regular |
| Phase 4 | Advanced ticket |
| — | Derniers tickets |

This validates the derivation in P1. The ladders we infer by cutting the sales
sequence at the cumulative allocation are **real phases with real names**, not
an artefact of reading price changes as boundaries. A Campagne phases axis can
therefore carry these labels rather than "PHASE 1 / PHASE 2", and the two
sources agree on what they are.

**The general rule, worth stating so a future reader does not read it as a data
gap:** a numbered phase implies a capped allocation, because the number *is* the
position in a sequence of caps. An uncapped final tier has no boundary to number
— there is nothing after it for the count to run up against. So "Derniers
tickets" carrying no phase number is not missing metadata; it is the correct
representation of `allocation=None`, which is exactly what the probe found on
the last tier of every ladder.

Corollary for anything deriving phases: **the last tier will never close.** A
routine that expects every phase to have an end will either wait forever or
invent one.

### P3 — `salesChannel` is `INTERNET`, and it is not an enum

All 20 sampled orders: `{'INTERNET': 20}`. There is **no `SalesChannel` enum in
the schema** — the field is a plain `String`, so the value set is open and
cannot be enumerated. `INTERNET` is the only value we have ever seen. Fine as a
parity partner for `deal_channel`, but do not build a fixed set of channel
buckets from it.

### P4 / Q3 — the mapping is confirmed on both sides now

```
announceDatetime    2026-05-25T11:00:00Z
onSaleDatetime      2026-06-02T17:00:00Z   ← on sale
first DICE sale     2026-06-02 17:00:14      +14s   [measured]
first Shotgun sale  2026-06-02 17:00:25      +25s   [measured]
offSaleDatetime     2026-11-08T02:00:00Z
```

`event_launched_at` ↔ `onSaleDatetime` and `event_published_at` ↔
`announceDatetime` are now measured on both sides, not inferred from one.

**⚠ And this bears on O2, the suspected 2h DICE/Shotgun skew.** DICE's
`onSaleDatetime` is 17:00:00**Z**, and *both* platforms' first stored sale lands
within 25 seconds of it. An hour-of-day histogram over all 3,614 rows agrees:
both peak at hour 17 and trough at 01–06. **There is no cross-platform skew in
the stored data — the two streams share a clock.** What is true is that the
shared clock is UTC, so any hour-of-day reading on the dashboard is 2h early in
summer, for *both* platforms equally. That is a display/localisation bug, not a
parity break, and materially smaller than O2 currently claims.

### P5 / Q5 — readable, and 15%

`Fan { optInPartners }` is readable by the Collaborateur token. Tally over 20
orders: **3 true, 17 false**. The query selected `optInPartners` alone, in its
own query — no other `Fan` field was requested, and only the tally reached the
log. Q5 is therefore a genuine two-platform metric, subject to the caveat below
that the two consents are not the same consent.

### X2 — returns and transfers are real, and not small

| collection | totalCount on `rennes_2026` |
| --- | ---: |
| `viewer.returns` | **28** |
| `viewer.ticketTransfers` | **107** |
| `viewer.orders` | 1,634 |

`Return.reason` is a free string with observed values `accident` (9), `other`
(6), `wrong_tickets` (4), `event_rescheduled` (1). Three returns are timestamped
17:02:36 — **two and a half minutes after on-sale** — which is what a
launch-night misclick looks like.

`WhereInput` shapes, from the introspection the old dump was missing:

```
OrderWhereInput            [eventId, id, purchasedAt]
ReturnWhereInput           [eventId, id, returnedAt]
TicketTransferWhereInput   [eventId, id, transferredAt]
```

All three are event-scopeable, as predicted. **`OrderWhereInput.purchasedAt` is
an unexpected bonus:** DICE orders can be filtered server-side by purchase date,
which is the missing half of incremental fetching on the DICE side. Nothing has
been built on it — noting it where it will be found.

`api_output/dice_schema_full.json` (49 KB) now carries enum values, input fields
and field arguments, retiring the whole "the dump does not say" class. It is an
Actions artifact on run 31235118312, not committed.

### Still open after the probe

- **P6 / O1** — which Shotgun fee the buyer bears. Unchanged: not in the API.
  Now half-narrowed, since the DICE side is proven.
- **What `GET /events` returns.** Needs an authenticated call — a decision to
  make, not a probe to bolt on.
- **Whether `viewer.orders` excludes returned tickets.** Inference only.

---

## The table

FETCHED = in the 11-column merged CSV today. DROPPED = we receive it and throw
it away. NEVER-REQUESTED = available but our query does not ask for it.

| concept | Shotgun field | DICE field | status | parity | notes |
| --- | --- | --- | --- | --- | --- |
| purchase time | `ordered_at` **[sample]** | `Order.purchasedAt` **[schema]** | FETCHED both | both | Shotgun to the microsecond, DICE to the second. both stored on the same clock, and it is UTC — see P4 in the probe results; there is no cross-platform skew, but hour-of-day reads 2h early for both |
| ticket identity | `ticket_id` | `Ticket.id` | FETCHED (Shotgun only, for the cursor) | both | |
| order identity | `order_id` | `Order.id` | DROPPED / NEVER-REQUESTED | both | would give basket size; DICE also has `Order.quantity` |
| face value | `deal_price` (cents) | `Ticket.fullPrice` (cents) | FETCHED both | both | |
| buyer total | `deal_price + deal_user_service_fee` | `Ticket.total` | FETCHED both | both | **not the same decomposition** — see Q4 |
| product name | `deal_sub_category` | `TicketType.name` | FETCHED both | both | |
| **phase name** | `deal_title` = `"PHASE 1"` **[sample]** | `PriceTier.name` via `Ticket.priceTier` **[schema]** | DROPPED / NEVER-REQUESTED | both | see Q1 |
| **phase price** | `deal_price` per `deal_title` | `PriceTier.price`, `.faceValue` | DROPPED / NEVER-REQUESTED | both | |
| **phase allocation** | — | `PriceTier.allocation`, `TicketPool.allocation` | n/a / NEVER-REQUESTED | DICE-only | |
| **phase boundary time** | — | `PriceTier.time` **[schema]** | n/a / NEVER-REQUESTED | DICE-only? | semantics unconfirmed — **[probe]** |
| on-sale moment | `event_launched_at` **[sample]** | `Event.onSaleDatetime` **[schema]** | DROPPED / NEVER-REQUESTED | both | see Q3 — verified [measured] |
| announce/publish | `event_published_at` | `Event.announceDatetime` | DROPPED / NEVER-REQUESTED | both | |
| record created | `event_created_at` | — (`Event.updatedAt` only) | DROPPED | Shotgun-only | not useful |
| sale close | — | `Event.offSaleDatetime` | n/a | DICE-only | |
| event start/end | `event_start_time` / `event_end_time` | `Event.startDatetime` / `.endDatetime` | DROPPED / NEVER-REQUESTED | both | we use config instead, deliberately |
| **acquisition source** | `utm_source`, `utm_medium` **[sample]** | **none** | DROPPED | **Shotgun-only** | see Q2 |
| point of sale | `deal_channel` = `"online"` | `Order.salesChannel` **[schema]** | DROPPED / NEVER-REQUESTED | both, probably | **not** the same as UTM — see Q2 |
| visibility / presale gate | `deal_visibilities` = `['promoters','public','xpress_door']` | `Event.hidden`, `Event.state` | DROPPED / NEVER-REQUESTED | rough | Shotgun is per-deal, DICE per-event — different granularity |
| payment method | `payment_method` = `"card"` | — | DROPPED | Shotgun-only | |
| platform fee | `deal_service_fee` | `Ticket.commission`, `.diceCommission` | partly FETCHED | both, differently | see Q4 |
| buyer-borne fee | `deal_user_service_fee` | `TicketFee{category,dice,promoter}` | FETCHED / NEVER-REQUESTED | both, differently | |
| producer cost | `deal_producer_cost` = `0` | `TicketFee.promoter` | DROPPED / NEVER-REQUESTED | both, differently | |
| VAT | `deal_vat_rate` = `0.055` | — | DROPPED | **Shotgun-only** | no DICE equivalent in the dump |
| refund / cancel | `ticket_status`, `ticket_canceled_at` | `Return`, `Order.returns` | FETCHED (status) / NEVER-REQUESTED | both, **different shape** | Shotgun: a status change with no reason. DICE: an object — see the refund row below and X2 |
| **newsletter opt-in** | `contact_newsletter_optin` **[sample]** | `Fan.optInPartners` **[schema]** | DROPPED / NEVER-REQUESTED | both, **different consent** | see Q5 |
| attendance scan | `ticket_scanned_at` **[sample]**, `ticket_scan_code` | **no equivalent** | DROPPED | **Shotgun-only** | see Q6 — `claimedAt` is not this |
| ticket activation | — | `Ticket.claimedAt` | NEVER-REQUESTED | DICE-only | see Q6 |
| geography | `contact_country`, `contact_postal_code`, `contact_locality` | `Order.ipCity`, `Order.ipCountry` | DROPPED | both, **different meaning** | Shotgun = stated address (PII), DICE = IP geolocation |
| seating | `ticket_seating` | `Ticket.seat`, `Seat` | DROPPED | both | unused by us |
| add-ons / merch | — | `Extra`, `Product`, `Variant` | n/a | **DICE-only** | separate revenue line |
| survey answers | — | `Ticket.fanSurveyAnswers` | n/a | DICE-only | **do not fetch** — PII |
| currency | `currency` = `"eur"` | `Event.currency` | DROPPED | both | |
| capacity | — | `Event.totalTicketAllocationQty` | n/a | DICE-only | **stays from config**, per your constraint |
| **refund object** | — (only `ticket_status` + `ticket_canceled_at`) | `Return { id, order, ticket, ticketId, reason, returnedAt }` **[schema]** | NEVER-REQUESTED | **DICE-only as an object** | top-level `viewer.returns`; see X2 |
| **fee adjustment** | — | `Adjustment { feesChange: TicketFee, processedAt, reason, ticket }` **[schema]** | NEVER-REQUESTED | **DICE-only** | `feesChange` is a full `TicketFee`, so it decomposes dice/promoter — bears on Q4 |
| **ticket transfer** | — | `TicketTransfer { id, orders, tickets, transferredAt }` **[schema]** | NEVER-REQUESTED | **DICE-only** | top-level `viewer.ticketTransfers`. Resale/gifting between fans |
| **allocation pool** | — | `TicketPool { id, name, allocation }` **[schema]** | NEVER-REQUESTED | **DICE-only** | `TicketType.ticketPoolId` joins to it — shared allocation across ticket types |
| add-on product | — | `Product { id, name, description, faceValue, totalAllocationQty, ticketTypes, archived }` | NEVER-REQUESTED | DICE-only | |
| add-on variant | — | `Variant { id, name, size, sku }` | NEVER-REQUESTED | DICE-only | size/sku implies merch |
| add-on purchase | — | `Extra { id, code, product, variant, holder, fullPrice, total, commission, diceCommission, fees, ticket, hasSeparateAccessBarcode }` | NEVER-REQUESTED | DICE-only | top-level `viewer.extras`; **revenue we cannot currently see** |
| seat | `ticket_seating` (`null` in sample) | `Seat { name }` | DROPPED / NEVER-REQUESTED | both, thin | DICE's `Seat` is a single `name` string |

### X2 — what the four unopened types change

**`Return` is the one that matters, and it bears on the modification detector.**

The H9 detector exists because a Shotgun refund is an *absence*: the ticket
stops coming back, and nothing marks the event. There is no refund row to find,
so the detector compares `ordered_at` against a stored maximum to notice that
something behind the cursor moved.

On DICE a refund is neither an absence nor a marked row — it is a **first-class
object with its own timestamp and a reason**, in a top-level collection that can
be polled independently of the orders it refers to.

Whether that is worth acting on: **not for correctness.** DICE is refetched
wholesale every run, never incrementally, so nothing about DICE can drift the
way the Shotgun cursor can — H10 already asserts the merged DICE count equals
this run's fetch. The detector is a Shotgun problem and stays one.

It is worth it for **explanation**. `viewer.returns` scoped to an event gives a
refund curve with reasons, on the platform where we currently have neither.
Shotgun gives `ticket_canceled_at` and a status, and no reason at all. If the
Campagne page ever asks "why did week 3 stall", DICE can answer and Shotgun
cannot.

`Adjustment.feesChange` is a full `TicketFee`, so post-hoc fee corrections
decompose dice/promoter the same way the original fees do — directly relevant
to Q4, and a candidate explanation for revenue drift that currently looks like
our arithmetic.

`TicketTransfer` is resale/gifting between fans. No Shotgun equivalent
(`ticket_status: 'resold'` is a different thing — a returned ticket resold by
the platform, not a fan-to-fan transfer). Probably not a campaign metric, but
it is a population of tickets whose holder is not the buyer, which matters if
opt-in rate is ever computed per ticket rather than per order.

`TicketPool` explains shared allocation: several `TicketType`s can draw on one
pool via `ticketPoolId`, so summing per-type allocations would double-count.
Another reason capacity stays from config.

### X4 — the PII boundary, stated explicitly

`Fan` is `{ dob, email, firstName, lastName, phoneNumber, optInPartners }`.

**Exactly one of those six is wanted, and it sits beside five that must never
be persisted.** GraphQL returns only what is selected, so the rule is:

> Any query that reads opt-in must select `fan { optInPartners }` **alone** —
> never `fan { ... }` with a second field, never a fragment spread on `Fan`,
> not even `id`.

`id` matters as much as the rest: a stable per-fan identifier makes every
aggregate re-identifiable by joining across events, which is the whole thing
the aggregate-at-fetch-time rule exists to prevent.

`scripts/probe_dice_fields.py` follows this, and it is the reason the opt-in
query in that script is a separate query rather than another field on the
orders query — so no future edit can widen the `Fan` selection by accident
while adding something unrelated to the order.

The Shotgun side has no such control. It sends eleven personal fields on every
ticket whether asked or not; `assert_merged_schema()` is the only thing between
them and a committed file.

### PII, present and deliberately dropped

Shotgun sends these on **every ticket**, unrequested: `contact_email`,
`contact_first_name`, `contact_last_name`, `contact_phone`, `contact_id`,
`contact_gender`, `contact_birthday`, `contact_postal_code`,
`contact_locality`, `contact_company_name`, `user_id`.

`fetch_csv.py`'s `assert_merged_schema()` is what stops any of it reaching a
committed file. DICE is better here: GraphQL means we only receive what we
select, and `Fan` is never selected.

---

## Your questions

### Q1 — Phases. DICE is the better source, and Shotgun cannot give you boundaries directly.

**Shotgun [sample]:** `deal_title` carries the phase name (`"PHASE 1"`), and
`deal_price` its price. There is **no phase start/end datetime anywhere in the
44 fields.** You would derive boundaries as `min`/`max` of `ordered_at` per
`deal_title` — which is arguably the more honest definition anyway (when that
phase actually sold), but it is a derivation, not a field.

**DICE [schema]:** materially richer.
`Ticket.priceTier → PriceTier { name, price, faceValue, allocation,
doorSalesPrice, time }`, and `TicketType { priceTierType, priceTiers,
totalTicketAllocationQty, ticketPoolId }`.

So DICE gives phase name, price, **allocation**, and a `time` field per tier —
plus a per-ticket link to its tier. That is strictly more than Shotgun.

**The catch:** `PriceTier.time` is a `Datetime` with no documented semantics.
It is probably when the tier activates, but "probably" is how the `.ac-t`
baseline happened. **[probe]**

**Answered — and the answer changes the verdict below.** `PriceTierTypes` is
`{allocation, time}`; all our ladders are `allocation`, so `time` is null
everywhere and there is no boundary datetime to fetch. The boundaries are
instead *derivable*, and the allocations reproduce exactly in our own data. See
P1 in the probe results — including the two ways a naive phase axis goes wrong.

**Verdict:** worth widening the fetch, and DICE is where the value is. Two
fields on the existing DICE query (`priceTier { name price allocation time }`)
and one on Shotgun (`deal_title`) would replace the product-name-suffix
guesswork. Both are additive to queries we already make.

### Q2 — Attribution. Shotgun-only, and `salesChannel` is not the same thing.

`utm_source` / `utm_medium` **[sample]** are genuine acquisition attribution.
DICE has **nothing comparable** — there is no UTM field anywhere in the dump.

`Order.salesChannel` is a `String` on the *order*. Structurally that is
point-of-sale (app / web / box office), not where the buyer came from. Shotgun
has its own point-of-sale field, `deal_channel` (`"online"` in the sample), and
`utm_*` sits alongside it — the two coexist on Shotgun precisely because they
answer different questions.

**You are right to be suspicious.** Treat `deal_channel` ↔ `salesChannel` as
the parity pair, and `utm_*` as Shotgun-only. One honest column.

`salesChannel`'s actual value set is **`INTERNET` on all 20 sampled orders, and
the field is a plain `String` with no enum** — so the set is open and cannot be
enumerated. See P3.

**Coverage makes this worse than it looks — see the warning below.**

### Q3 — On-sale moment. `event_launched_at` ↔ `onSaleDatetime`. Verified, not inferred.

From the captured sample and our own committed CSV **[measured]**:

```
event_created_at     2025-12-24T09:19:59Z    record created
event_published_at   2025-12-29T16:30:00Z    page public, 8 days before sale
event_launched_at    2026-01-06T18:00:17Z    ← on sale
first sale           2026-01-06 18:00:18     0.8 seconds later
```

`event_launched_at` is the moment tickets became buyable, to within a second.

Mapping: `event_launched_at` ↔ `Event.onSaleDatetime`;
`event_published_at` ↔ `Event.announceDatetime`; `event_created_at` has no DICE
equivalent and you do not want it.

**The DICE side is now measured too** — `onSaleDatetime` 2026-06-02T17:00:00Z
against a first DICE sale 14 seconds later, on `rennes_2026`. Both halves of the
mapping are confirmed against real values. See P4.

### Q4 — Fees. They do **not** decompose the same way, and one side is incomplete.

**Shotgun [sample]**, cents: `deal_price` 9500, `deal_service_fee` 950,
`deal_user_service_fee` 287, `deal_producer_cost` 0, `deal_vat_rate` 0.055.

**DICE [schema]:** `fullPrice`, `total`, `commission`, `diceCommission`, and
`fees: [TicketFee{category, dice, promoter}]` — an **itemised** split, per
category, between what DICE takes and what the promoter bears.

Two problems for a comparable net-to-producer:

1. **Shotgun is not itemised.** `deal_service_fee` (950) and
   `deal_user_service_fee` (287) both exist and their relationship is not
   stated. `deal_service_fee` is 10.0% of face, `deal_user_service_fee` 3.0%.
   Which is borne by whom is an assumption right now — and it is very likely
   the same ambiguity behind the **~2% gross overshoot that has been open in
   the handoff since the start**. Those are probably the same bug.
2. **`TicketFeeCategory`'s enum values are missing from the dump.** Without
   them you cannot know which categories are promoter-borne. **[probe]**
   — **now recovered: 18 values, of which only `BOOKING` and `PROCESSING` occur
   on our events, both wholly DICE-borne. The DICE decomposition is exact and
   complete. See P2.**

**Verdict: do not drop the disclaimer yet.** A comparable net is *plausible* —
DICE clearly supports it, and Shotgun probably does — but it currently rests on
an assumption about `deal_service_fee` that is already suspected of being
wrong. Settling it would also close the 2% item, which makes it worth doing
properly rather than quickly.

### Q5 — Opt-in. Both have one, but they are not the same consent.

`contact_newsletter_optin` **[sample]** (Boolean, `True`) vs `Fan.optInPartners`
**[schema]** (Boolean).

The names say different things: a promoter newsletter versus partner
marketing. Presenting them as one "opt-in rate" would be the
channel-means-two-things error you flagged, in a field where getting it wrong
has consent implications.

**On PII:** GraphQL selects, so `Fan { optInPartners }` returns that boolean
and nothing else — no email, no dob, no name. Structurally safe. **The token can
read it** — 3 true / 17 false over 20 orders on `rennes_2026`. See P5.

Aggregate at fetch time to a single rate per event, exactly as you say.

### Q6 — Attendance. **Not the same thing**, and this is the sharpest false friend here.

`ticket_scanned_at` **[sample]** is a door scan. It is `null` on the sampled
ticket, and `ticket_scan_code` is populated, which is consistent with "scan
data exists but only after the event".

`Ticket.claimedAt` is **not** a scan. It is when the fan activated the ticket
into their DICE wallet. `fetch_csv.py:131` already records this from live
observation:

> *"it records when the fan activated the ticket — null until close to the
> event, so it is empty for every ticket of a future event (all 2215 Rennes
> 2026 tickets came back null)."*

So attendance is **Shotgun-only**, and `claimedAt` must not be used for it.

**Doc correction while I am here:** `HANDOFF.md`'s DICE field-mapping table
still says `claimedAt → order_date`. The code has used `Order.purchasedAt`
since the orders query replaced the tickets query; the handoff line is stale.
Worth fixing before it misleads the Campagne spec.

### Q7 — What I would want that you have not asked for

1. **`Return { returnedAt, reason }`** and `Order.returns` **[schema]** —
   refund *timing and reason*. Shotgun gives only `ticket_status` and
   `ticket_canceled_at`, no reason. A refund curve overlaid on the sales curve
   is a genuine campaign-health signal, and this is the only place either
   platform explains *why*.
2. **`Order.quantity` / `Order.id`** — basket size. Are launch-day buyers
   buying in groups? Available on both sides (`order_id` on Shotgun), currently
   thrown away, and cheap.
3. **`Adjustment { feesChange, processedAt, reason }`** — DICE-only. Post-hoc
   fee corrections. If these exist in volume they would explain revenue drift
   that currently looks like our arithmetic.
4. **`Extra` / `Product` / `Variant`** — DICE-only add-on revenue, entirely
   invisible to us today. If Madame Loyal sells anything beyond tickets on
   DICE, our revenue figures are understated and we would not know.
5. **`Order.ipCountry`** — geography without touching PII, unlike Shotgun's
   stated `contact_postal_code`. Aggregate-only, and the honest version of a
   question the Shotgun fields answer more invasively.

---

## The coverage warning, which changes one of your constraints

You said marketing-only metrics may be Shotgun-only provided we state the
coverage. Measured over paid tickets in our own CSVs **[measured]**:

| event | tickets | Shotgun share |
| --- | ---: | ---: |
| bordeaux_oct_2026 | 7,732 | 100% |
| epk_2026 | 10,039 | 77% |
| bordeaux_2026 | 26,736 | 65% |
| paris_xxl_2026 | 34,075 | 63% |
| rennes_2026 | 3,614 | 38% |
| geneve_2026 | 4,086 | 29% |
| — reference editions — | | |
| epk_2023 | 17,107 | 100% |
| halloween_2025 | 21,513 | 100% |
| geneve_2025 | 2,515 | 100% |
| bordeaux_2025 | 24,382 | 39% |
| rennes_2025 | 18,938 | 36% |
| **paris_xxl_2025** | **15,693** | **8%** |

Your three figures reproduce exactly. But the Campagne page is a *comparison*,
so what matters is the pair:

**`paris_xxl_2026` (63% Shotgun) compares against `paris_xxl_2025` (8%).** A
Shotgun-only metric there is 63% coverage on one side against 8% on the other —
not a comparison, and that is the exact pair your working mock uses.

`geneve_2026` (29%) vs `geneve_2025` (100%) is the same problem inverted.

So the constraint needs strengthening: **a Shotgun-only metric needs adequate
coverage on _both_ sides of the comparison, not just the current one.** Of six
pairs, only `epk` (77% vs 100%) and `bordeaux_oct` (100% vs 100%) clear that
bar comfortably. UTM attribution is therefore a two-event feature, not a
six-event one — worth knowing before it is specced as a headline card.

---

## What needed a live probe — status

All but one ran on 2026-08-08, run 31235118312. Answers are in "Probe results"
near the top of this document.

| # | question | status |
| --- | --- | --- |
| P1 | What does `PriceTier.time` mean, and are tiers populated for our events? | **answered** — `time` is null; our ladders are allocation-typed |
| P2 | `TicketFeeCategory` enum values, and a real `fees` array | **answered** — 18 values; `BOOKING` + `PROCESSING`; arithmetic exact |
| P3 | `Order.salesChannel` value set | **answered** — `INTERNET`; a `String`, not an enum, so the set is open |
| P4 | `Event.onSaleDatetime` / `announceDatetime` actual values | **answered** — Q3 mapping now measured on both sides |
| P5 | May the Collaborateur token read `Fan { optInPartners }`? | **answered** — yes; 3/20 true |
| P6 | Is `deal_service_fee` promoter-borne or buyer-borne? | **still open** — not a probe. Needs Shotgun's docs or a payout statement. Tracked as O1 in `HANDOFF.md` |
| X1 | The three introspection dimensions the dump is missing | **answered** — `api_output/dice_schema_full.json`, 49 KB, run artifact |
| X2 | Do `viewer.returns` / `viewer.ticketTransfers` return anything? | **answered** — 28 and 107 on `rennes_2026` |
| X3a | Does Shotgun serve any index, spec or second endpoint? | **answered, and it found something** — no index, but `GET /events` returns 400 where seven siblings return 404 |
| X3b | Is 44 the ceiling on a ticket? | **answered** — union = intersection = 44 across 600 tickets, 6 events |

Reproduce with `.github/workflows/probe-platform-fields.yml`
(`workflow_dispatch`, jobs `probe` and `shotgun`). Read-only; one page per
event; no value from a personal field ever reaches the log.

**What is left.** P6 needs Leo and a payout statement. Beyond it, the probe
opened two new questions worth a decision rather than a script: what `GET
/events` actually returns, and whether `viewer.orders` already nets out the 28
returns.
