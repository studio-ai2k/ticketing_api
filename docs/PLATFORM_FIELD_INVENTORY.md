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

The Shotgun sample is 44 fields on one ticket. The DICE dump gives types and
field names but **no values and no semantics** — which is exactly the gap that
makes several answers below "probe" rather than "yes".

---

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
| refund / cancel | `ticket_status`, `ticket_canceled_at` | `Return{returnedAt, reason}`, `Order.returns` | FETCHED (status) / NEVER-REQUESTED | both | DICE gives a **reason**; Shotgun does not |
| fee adjustment | — | `Adjustment{feesChange, processedAt, reason}` | n/a | DICE-only | |
| **newsletter opt-in** | `contact_newsletter_optin` **[sample]** | `Fan.optInPartners` **[schema]** | DROPPED / NEVER-REQUESTED | both, **different consent** | see Q5 |
| attendance scan | `ticket_scanned_at` **[sample]**, `ticket_scan_code` | **no equivalent** | DROPPED | **Shotgun-only** | see Q6 — `claimedAt` is not this |
| ticket activation | — | `Ticket.claimedAt` | NEVER-REQUESTED | DICE-only | see Q6 |
| geography | `contact_country`, `contact_postal_code`, `contact_locality` | `Order.ipCity`, `Order.ipCountry` | DROPPED | both, **different meaning** | Shotgun = stated address (PII), DICE = IP geolocation |
| seating | `ticket_seating` | `Ticket.seat`, `Seat` | DROPPED | both | unused by us |
| add-ons / merch | — | `Extra`, `Product`, `Variant` | n/a | **DICE-only** | separate revenue line |
| survey answers | — | `Ticket.fanSurveyAnswers` | n/a | DICE-only | **do not fetch** — PII |
| currency | `currency` = `"eur"` | `Event.currency` | DROPPED | both | |
| capacity | — | `Event.totalTicketAllocationQty` | n/a | DICE-only | **stays from config**, per your constraint |

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

P1–P5 are one probe run against one event. P6 is the one that matters most for
Q4 and cannot be answered from the API at all.

**Recommendation:** authorise a single DICE probe covering P1–P5, on
`rennes_2026` (live, DICE-majority, 2,245 DICE tickets). P6 needs Leo and a
payout statement, and it closes the 2% item as a side effect.
