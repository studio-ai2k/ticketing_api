# Platform field inventory — Shotgun vs DICE

For the Campagne page. Inventory only; nothing here has been built or fetched.

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

## The table

FETCHED = in the 11-column merged CSV today. DROPPED = we receive it and throw
it away. NEVER-REQUESTED = available but our query does not ask for it.

| concept | Shotgun field | DICE field | status | parity | notes |
| --- | --- | --- | --- | --- | --- |
| purchase time | `ordered_at` **[sample]** | `Order.purchasedAt` **[schema]** | FETCHED both | both | Shotgun to the microsecond, DICE to the second. Shotgun naive Paris, DICE UTC — the 2h skew is a known open item |
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

`salesChannel`'s actual value set is unknown **[probe]**.

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

The DICE side of that mapping is by name and type only — no value observed
**[probe]** — but the Shotgun half is now nailed down, and it is the half that
carries the on-sale anchor for 5 of 6 live events.

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
and nothing else — no email, no dob, no name. Structurally safe. Whether the
Collaborateur token may read `Fan` at all is **[probe]**.

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

## What needs a live probe

None of these are answerable from the dumps. All are additive to queries we
already make; none touch PII.

| # | question | probe |
| --- | --- | --- |
| P1 | What does `PriceTier.time` mean, and are tiers populated for our events? | `probe-dice-event.yml`, add `ticketTypes { name priceTiers { name price allocation time } }` |
| P2 | `TicketFeeCategory` enum values, and a real `fees` array | `probe-dice-event.yml`, add `tickets { fees { category dice promoter } commission diceCommission }` on one order |
| P3 | `Order.salesChannel` value set | same probe, add `salesChannel` |
| P4 | `Event.onSaleDatetime` / `announceDatetime` actual values | same probe, add both — settles the Q3 mapping |
| P5 | May the Collaborateur token read `Fan { optInPartners }`? | same probe; if it errors, Q5 is Shotgun-only |
| P6 | Is `deal_service_fee` promoter-borne or buyer-borne? | **not a probe** — Shotgun's REST payload has no more to give. Needs Shotgun's docs or a reconciliation against a payout statement |
| X2 | Do `viewer.returns` / `viewer.ticketTransfers` return anything, and what does a `Return.reason` look like? | same probe run — `scripts/probe_dice_fields.py` |
| X1 | The three introspection dimensions the dump is missing (enum values, input fields, field args) | same probe, `--introspect`; writes `api_output/dice_schema_full.json` |
| X3a | Does Shotgun serve any index, spec or second endpoint? | `scripts/probe_shotgun_fields.py` — **must run in Actions**, the host is blocked from the dev container |
| X3b | Is 44 the ceiling on a ticket? | same script — key union/intersection + null rates across all six active events |

P1–P5, X1 and X2 are one DICE probe run against one event. X3a/X3b are a
separate Shotgun job in the same workflow, read-only, one page per event. P6 is
the one that matters most for Q4 and cannot be answered from either API.

Both live in `.github/workflows/probe-platform-fields.yml`
(`workflow_dispatch`, jobs `probe` and `shotgun`).

**Recommendation:** authorise the probe run on `rennes_2026` (live,
DICE-majority, 2,245 DICE tickets). P6 needs Leo and a payout statement, and it
closes the 2% item as a side effect.
