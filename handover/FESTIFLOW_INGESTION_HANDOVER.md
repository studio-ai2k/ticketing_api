# Ticketing ingestion — handover to Festiflow

**From `studio-ai2k/ticketing_api`, written 2026-10-05 against commit `79490c8`.**

**How to read the confidence markers.** There is no blanket disclaimer at the
top, because a disclaimer that covers everything marks nothing. Instead, every
claim carries its basis in its own sentence:

- **verified today** — I read it in the code or measured it on this tree today.
- **recorded** — the repo records it against a dated probe run; I did not re-run
  the probe.
- **believed, not re-checked** — stated so you can decide whether to re-check.
- **unknown** — with one line on what would settle it.

Companion files in this directory:

| file | what it is |
|---|---|
| `shotgun_tickets_response.redacted.json` | a **real** `GET /tickets` response, one ticket, every field present, PII values removed and field names kept |
| `dice_schema.json` (repo root, unchanged) | a **real** GraphQL introspection dump of the DICE partners API — types, enums, input fields. Not response data, and contains no values |

**There is no captured DICE *response* in this handover, and I did not invent
one.** The repo has the introspection dump and the exact query but no committed
sample of what comes back, and this session has no DICE credential, so I could
not capture one. §3 below gives the exact selection set instead. A constructed
sample would have looked like evidence and been a guess.

---

## 1 · Auth and accounts

### Shotgun

| | |
|---|---|
| credential | **a per-account token, passed as a QUERY PARAMETER** — `?token=…` — not a header. *Verified today*, `fetch_csv.py:742`. |
| also required | `organizer_id`, a numeric id per account, also a query parameter. |
| scope | **per promoter account, not global.** *Verified today.* |
| obtained how | **unknown.** The repo documents the shape, never the issuance. One line would settle it: ask whoever created the Episode token which back-office screen produced it. |
| expiry / rotation | **unknown.** No refresh logic exists anywhere in `fetch_csv.py` — *verified today* — which is consistent with non-expiring but does not prove it. |

**⛔ The multi-account answer, and it is the one that will bite you.** You asked
whether one credential sees several promoters. It does not. `SHOTGUN_ACCOUNTS`
(`fetch_csv.py:90`) holds two separate accounts — *verified today*:

```
episode   token env SHOTGUN_TOKEN_EPISODE   organizer_id 171835
sonora    token env SHOTGUN_TOKEN_SONORA    organizer_id 207784
```

Each event is assigned to an account by a **hard-coded list of event ids**, with
`DEFAULT_SHOTGUN_ACCOUNT = 'episode'` as the fallback. *Verified today*,
`resolve_shotgun_account()` at `:512`.

**And the failure mode is silent.** The code's own comment records it from probe
run `32146511963`: `sonora_impact_2026` under the Episode account returned
**0 tickets, not an error**; under Sonora it returned 100 on page 1. The comment
states the consequence plainly, and it is the single most important sentence in
this document for you:

> An event left out of both lists is therefore indistinguishable from an event
> that has sold nothing, on a page that renders perfectly.

With EPISODE, SAGREGA and GGS you will have **three or more** of these. A wrong
or missing account mapping does not raise — it returns an empty success. Build
the "which account owns this event" mapping as data you can assert on, not as a
fallback.

**Brand does not predict account.** `bordeaux_2026` is branded "MADAME LOYAL x
SONORA" and lives on the **Episode** account; the comment says it was confirmed
by probe and warns against "correcting" it back by brand. *Recorded.*

### DICE

| | |
|---|---|
| credential | **a bearer token in the `Authorization` header** — `Authorization: Bearer <token>`. *Verified today*, `dice_graphql()` at `:970`. |
| env var | one, `DICE_TOKEN` — a single promoter token, not per-event. *Verified today.* |
| scope | **per DICE account.** *Recorded, from a probe:* `geneve_2026` (DICE id 588085) returned `node -> null` and 0 orders on the same token that fully resolved Rennes and Paris XXL, which the code calls "an account boundary rather than a bad id" (`fetch_csv.py:140`). |
| obtained how | **unknown** — the repo calls it a "DICE MIO promoter token" and never records who issued it. |
| expiry / rotation | **unknown**, same basis as Shotgun. |
| approval step | **unknown.** Nothing in the repo records an allow-listing or sales-contact step or how long it took. |

**The DICE failure mode is silent too, and the code says so** (`:184`): *"A valid
token on the wrong account returns HTTP 200 and an empty set, which is
indistinguishable from 'no sales'."* That is why the fetcher refuses to publish a
DICE result smaller than the manual export it replaced.

### ⛔ Secrets — what I did and did not find

I checked the two sample files the brief's §3 asks for, because they are the
likeliest leak. **Neither leaks a credential**, *verified today*:

- `shotgun_schema.json`'s `pagination.next` **does** contain a `token=`
  parameter — Shotgun's own pagination cursor carries the credential — but the
  committed value is the literal string `REDACTED`. Someone sanitised it. Worth
  knowing because **any Shotgun URL you log, cache or store includes the token**
  unless you strip it; the repo has a `redact()` helper for exactly this
  (`:581`).
- `dice_schema.json` is introspection only. Its `email` / `firstName` /
  `phoneNumber` hits are **type names, not values**.

**But two PII fields in the Shotgun sample were missed by that sanitisation**,
*measured today*: `contact_gender` (a real 4-character value) and
`ticket_scan_code` (a real 14-character scannable entry barcode). They are still
live in the public repo. See §5 for the recommendation.

---

## 2 · The endpoints actually called

Two. That is the whole integration.

### Shotgun — `GET https://api.shotgun.live/tickets`

One ticket per row, for one event. *Verified today.*

| parameter | required? | notes |
|---|---|---|
| `token` | yes | the account credential, in the URL |
| `organizer_id` | yes | numeric, per account |
| `event_id` | yes | the Shotgun event id |
| `include_cohosted_events` | **yes in practice** | **learned the hard way.** The code comment records that EPK 2026 (535882) "returned nothing under either account until this was set", because co-hosted events can be owned by the partner organizer and are excluded by default — again an empty set, not an error. *Recorded.* |
| `after` | optional | keyset cursor for resume |

**Pagination.** Follow `pagination.next` until absent. *Verified today.* The
cursor shape is `{ticket_updated_at}_{ticket_id}`, e.g.
`2026-01-06T18:01:05.041Z_89328982`, **so the ordering is by `ticket_updated_at`,
not by `ordered_at`**. The docstring at `:728` calls that "the useful ordering:
it surfaces modifications (refunds, cancellations, the resale flip) as well as
new sales." For an incremental ingestion that distinction is the whole game.

**Page size: 100.** *Recorded* — stated in a code comment, `SHOTGUN_PAGE_SIZE`.

**There is no total count.** The code tried to discover one and recorded "total
field not exposed, every run" (`:56`). So **you cannot verify completeness on the
Shotgun side** the way you can on DICE. The fetcher instead raises if
`pagination.next` points at a URL it already fetched, rather than returning a
short read as if it were whole.

**Filtering by date: none used.** No `since`-style server-side filter is sent.
Whether one exists is **unknown**.

**Rate limit — and here the honest answer matters.** The code comment says
"~100 requests/minute" and paces at `0.8s` per page. **I could not find a probe
that measured that limit.** One 429 is recorded in
`docs/PLATFORM_FIELD_INVENTORY.md`, and it was on `/` during endpoint discovery
after ten requests in a few seconds — the document itself says *"The 429 on `/`
is not evidence of anything."* So:

> **The pacing is a chosen value, not a measured ceiling. We paced to avoid
> finding out.** The 429 handling exists (`RATE_LIMIT_BACKOFF_S = 60`, 6 retries,
> waiting out the minute rather than backing off in seconds, because it is a
> per-minute quota) but I have no record of it firing on `/tickets`.

**Webhooks: unknown.** None used; none looked for, as far as the repo records.

**`/tickets` is not the whole API.** *Recorded:* `GET /events` returns **400**,
while seven sibling paths return 404 from the same host in the same run — so the
route exists and rejected the request. Nothing was ever fetched from it. An
event-level endpoint would plausibly carry capacity and tier metadata the
per-ticket payload lacks. **Worth your probing before you design around its
absence.**

### DICE — `POST https://partners-endpoint.dice.fm/graphql`

One query, `FetchOrders`. *Verified today*, `fetch_csv.py:221`:

```graphql
query FetchOrders($eventId: ID!, $first: Int!, $after: String) {
  viewer {
    orders(first: $first, after: $after, where: {eventId: {eq: $eventId}}) {
      totalCount
      pageInfo { endCursor hasNextPage }
      edges {
        node {
          id
          purchasedAt
          quantity
          tickets { id fullPrice total ticketType { name } }
        }
      }
    }
  }
}
```

**`$eventId` is a Relay global id**, not the numeric one: base64 of the literal
`Event:<numeric>`. *Verified today* by round-tripping it —
`526535 → RXZlbnQ6NTI2NTM1 → "Event:526535" → 526535`.

**Pagination:** Relay cursors, `first` = 100, follow `pageInfo.endCursor` while
`hasNextPage`. *Verified today.*

**Completeness is checkable here and the fetcher checks it**: `totalCount` is
read from page 1 and compared against orders processed. The comparison is
**deliberately one-sided** — only `processed < reported` raises. The reasoning,
which you will want if you copy it: `totalCount` is read from page 1 and a fetch
takes ~8s over 17 pages, so an order placed mid-fetch lands in `edges` without
being in the total; asserting equality would fail a *complete* fetch on a busy
event.

**Date filtering exists and we do not use it.** *Recorded:*
`OrderWhereInput` accepts `[eventId, id, purchasedAt]`, which the inventory calls
"an unexpected bonus… the missing half of incremental fetching on the DICE
side. Nothing has been built on it." **If you are designing incremental
ingestion, start here.**

**Rate limits on DICE: unknown.** No pacing, no 429 handling specific to DICE,
nothing recorded.

**Other collections exist and we do not read them.** *Recorded, on
`rennes_2026`:* `viewer.returns` totalCount **28**, `viewer.ticketTransfers`
**107**, against `viewer.orders` 1,634. Both are event-scopeable
(`ReturnWhereInput`, `TicketTransferWhereInput`). **Whether `viewer.orders`
excludes returned tickets is listed as "Inference only" — still open.** That is
a direct risk to any revenue figure you build from orders alone.

---

## 3 · The data

### What we treat as "sold" and "revenue"

| | Shotgun | DICE |
|---|---|---|
| one row = | one ticket | one ticket (inside an order) |
| **tickets sold** | count of rows with `ticket_status == 'valid'` | count of ticket nodes |
| **`price`** (our net) | `deal_price` | `fullPrice` |
| **`gross_price`** (our gross) | `deal_price + deal_service_fee + deal_user_service_fee` | `total` |
| units | **integer cents** on both — divide by 100 | **integer cents** |

*All verified today* in `process_shotgun_ticket()` (`:821`) and
`process_dice_ticket()` (`:1003`).

**What those two numbers mean, precisely.** From an external *reddition de
comptes* for `bordeaux_2026`, quoted verbatim in `docs/O1_FEE_DECISION.md` —
*recorded, and reconciled to one ticket in 9,327*:

```
PRIX HT       43,19     excluding VAT
PRIX TTC      45,57     <- our `price`.  face value, VAT 5,5% included
+ commission   3,43     DICE booking fee
buyer pays    49,00     <- our `gross_price`
```

So **`price` is face value INCLUDING VAT and EXCLUDING platform fees**, and
**`gross_price` is what the buyer paid**. Neither is net-to-promoter.

**⚠ The Shotgun side of that is not settled, and you should not assume it
matches.** *Recorded:* `deal_service_fee` is 10.0% of face and
`deal_user_service_fee` is 3.0%, **and which is borne by whom is an assumption**.
The inventory says that assumption "is already suspected of being wrong" and is
"very likely the same ambiguity behind the ~2% gross overshoot that has been open
in the handoff since the start." **Do not port a net-to-promoter calculation from
us on the Shotgun side.** The DICE side is exact; the Shotgun side is not.

### Currency

`currency` comes back as **`eur`, lower-case**, on the Shotgun ticket — *verified
today* in the sample. Our config defaults to `EUR` and **we have never handled a
second currency**; there is no conversion anywhere. If Festiflow has non-EUR
events, this codebase answers nothing for you.

### Time zones — ⚠ a real gap

- Shotgun `ordered_at` arrives as `2026-01-06 18:00:18.038852` — **no offset**.
  *Verified today.*
- Shotgun's pagination cursor carries `ticket_updated_at` with a `Z`, i.e. UTC.
  **So the same payload mixes an offset-free timestamp with a UTC one.**
- DICE `purchasedAt` is ISO 8601 possibly with an offset, and
  `parse_dice_datetime()` **strips the offset and returns a naive datetime**
  (`.replace(tzinfo=None)`) — *verified today*.

**We therefore store naive local-ish datetimes and never convert.** What zone
Shotgun's `ordered_at` is actually in is **unknown to me** — I did not find it
recorded, and one line would settle it: compare a known order's `ordered_at`
against the same order in the Shotgun back office. **Our day boundaries are
whatever the platforms hand us, and a day-level KPI inherits that.** For
Festiflow on Postgres I would store `timestamptz` and resolve this before
ingesting, not after.

### Ticket types / tiers

- Shotgun: `deal_sub_category` and `deal_title`. We use `deal_sub_category` as
  the display name when present.
- DICE: `ticketType { name }`.
- Both are then title-cased by `normalize_product_name()` so the same product
  from both platforms collapses to one line — **that is a presentation choice of
  ours, not a platform fact.**

**Phases/tiers: DICE is the better source.** *Recorded:* the inventory's §P1/Q1
is titled "phases are allocation-driven, and `PriceTier.time` is not the
boundary" — a tier changes when an allocation sells out, not at a timestamp. If
you want phase analytics, read that section before modelling it.

### ⛔ What counts and what does not

| | Shotgun | DICE | whose decision |
|---|---|---|---|
| **refunds / cancellations** | excluded — only `ticket_status == 'valid'` survives | the row **disappears from `viewer.orders`** (believed; see below) | platform shapes it, our filter is ours |
| **resales** | **excluded, deliberately.** Shotgun marks the original `resold` and issues a fresh `valid` row to the buyer; counting both double-counts one physical ticket. Bordeaux Jun 2026 carried **4,217** such rows | not modelled | **ours** |
| **imports from other platforms** | **excluded when the event also has DICE**, via `deal_channel` — keeping only `online, onsite, invitation` and dropping `distributor, offline, reseller, duplicata`. Counting both inflated Bordeaux Jun 2026 to **36,313** against a real ~26,738 | n/a | **ours** |
| **guest lists / comps / invitations** | **included as rows**, flagged `is_paid = 0` via `deal_channel == 'invitation'` | **included**, flagged `is_paid = 0` when the classified access level is `invitation` or `jeu_concours` | ours |
| **pending / failed payments** | **unknown** — we filter on `ticket_status == 'valid'` and never enumerated the other statuses | **unknown** | — |
| **test orders** | **unknown** — never looked for | **unknown** | — |
| **holds** | **unknown** | **unknown** | — |

The three "ours" rows are the ones to copy with care: they are **de-duplication
decisions driven by our two-platform merge**, not platform semantics. If
Festiflow ingests each platform into its own table it may want the raw rows and
the dedupe at query time instead.

### ⛔⛔ Does a figure ever go DOWN? **Yes. Append-only is wrong.**

This is the sharpest question in your brief and the answer is unambiguous.
**Measured today** on `sonora_impact_2026`'s merged file, a cancelled event:

| date | data rows |
|---|---|
| 2026-09-15 | **4,452** |
| 2026-09-16 | **1,708** |
| today (2026-10-05) | **1,269** |

**2,744 rows disappeared in a single day**, and it has kept shrinking since —
another 439 over the following three weeks. These are refunds on a cancelled
event: the tickets stop being `valid` and leave the result set entirely.

Two consequences for your table design:

1. **An append-only ingestion is wrong.** A ticket that existed yesterday may
   not exist today, and nothing in the payload announces its departure — it is
   simply absent from the next full read.
2. **Deletion and new sales happen simultaneously.** On the same event, while
   rows were being removed, the newest `order_datetime` advanced
   09-01 → 09-05 → 09-08 → 09-15 — *measured today*. So "the file shrank" does
   **not** mean "the feed is dead", and you cannot infer either from the other.

**What this costs you if you get it wrong:** a cumulative KPI built by summing
daily deltas will drift permanently, because the deltas never go negative — the
rows just stop being returned.

---

## 4 · Identity

### Mapping our event to theirs

We store **ids, not URLs**. `event_config.csv` carries, per event — *verified
today*: `shotgun_event_id`, `dice_mio_id`, `dice_public_id`, `dice_url`,
`shotgun_url`. The fetcher calls with `shotgun_event_id` and `dice_mio_id`; the
other three are display links.

### ⛔ Are your four URL fields enough? Mostly — with one gap that matters

I re-derived this today rather than taking it on report.

| your field | yields | verdict |
|---|---|---|
| `shotgun_backend_url` = `smartboard.shotgun.live/events/<id>` | `<id>` **is** `shotgun_event_id` | **derivable** |
| `dice_backend_url` = `mio.dice.fm/events/<base64>` | base64 decodes to `Event:<numeric>`; that numeric **is** `dice_mio_id` | **derivable** — round-tripped today: `526535 → RXZlbnQ6NTI2NTM1 → "Event:526535" → 526535` |
| the two public buy links | nothing the API needs | **not derivable, in either direction** |

**The gap: the URL gives you the event id but NOT which credential can see it.**
Shotgun needs `organizer_id` **and** the matching account token, and neither is
in the URL. With three or more promoter companies you must store **account
ownership per event** as a fourth thing. Getting it wrong returns an empty
success, not an error (§1).

**And a missing public link means nothing.** *Verified today:* `rennes_2026` has
`dice_mio_id = 600413` set, and `dice_public_id` and `dice_url` **both empty**.
DICE sells that event, the backend link works, and the public URL is stored
nowhere. A constructed one 404s. **Do not infer "not sold on this platform" from
a missing public URL.**

**Recommendation: store the ids, do not re-parse the URLs each time.** The
derivation is stable but it is a parse against a URL format you do not control.

### Sold on BOTH platforms

Yes, and it is the single largest correctness trap in this codebase. We add the
numbers, and **we must first stop Shotgun reporting DICE's tickets back to us** —
Shotgun surfaces tickets imported from other platforms alongside its own. The
rule (`fetch_csv.py:79`, *verified today*): **when an event has both a
`shotgun_event_id` and a `dice_mio_id`, keep only Shotgun's organic channels and
let the DICE feed supply the rest.** Shotgun-only events keep every channel,
because there is no second source to double with.

Unchecked, Bordeaux Jun 2026 read **36,313** against a real ~26,738.

### Multi-day events

One row per ticket per platform; the day is derived from the product name by
`classify_ticket()` / `resolve_attendance()`, against the event's configured
days. **This is string classification over product names, and it is ours, not
the platform's.** A "Pass 2 Jours" is one ticket row attributed to both days.
I would not port this; see §7.

---

## 5 · Special cases and scars

**The empty success is the recurring one.** Three distinct causes, all returning
HTTP 200 with zero rows and no error: wrong Shotgun account; missing
`include_cohosted_events`; DICE token on the wrong account. **Every one was found
by someone noticing a number was too round, not by an exception.**

**What we check before trusting a number.** On DICE, `totalCount` against orders
processed (one-sided). On Shotgun, a pagination loop guard that raises rather
than returning a short read. On the manual-export handover path, a refusal to
publish a DICE result smaller than the file it replaces. **A pull returning zero
is not trusted anywhere** — the design assumption throughout is that zero is more
likely a failure than a fact.

**`deal_channel` is not an enum and `salesChannel` is not either.** *Recorded,
§P3:* DICE's `salesChannel` is `INTERNET` and "it is not an enum". Our Shotgun
channel lists are observed values with a `SHOTGUN_KNOWN_IMPORT_CHANNELS`
alongside, so an unrecognised channel is reported rather than silently dropped.
**Expect new channel values to appear without warning.**

**PII arrives unrequested on Shotgun.** Eleven fields — `contact_email`,
`contact_first_name`, `contact_last_name`, `contact_phone`, `contact_id`,
`contact_gender`, `contact_birthday`, `contact_postal_code`, `contact_locality`,
`contact_company_name`, `user_id` — **on every ticket, whether asked or not**
(*recorded*). DICE is better by construction: GraphQL returns only what you
select. The repo's rule for DICE is worth copying verbatim:

> Any query that reads opt-in must select `fan { optInPartners }` **alone** —
> never `fan { ... }` with a second field, never a fragment spread on `Fan`, not
> even `id`.

`id` matters as much as the rest: a stable per-fan identifier makes every
aggregate re-identifiable by joining across events.

**⚠ Two PII values are live in our public repo right now** — *measured today*:
`contact_gender` and `ticket_scan_code` in `shotgun_schema.json`. The
sanitisation pass that redacted the other ten missed these. **This is ours to
fix, not yours** — flagged here because it is the kind of thing a second reader
finds, and because it tells you the redaction needs to be a checked list rather
than a careful read.

**What did NOT work.** *Recorded:* endpoint discovery on Shotgun — no index, no
OpenAPI spec, no docs served; nine paths probed, seven 404. The endpoint list is
"guesswork with one confirmed hit". If Festiflow needs anything beyond
`/tickets`, **ask Shotgun rather than probing**; we spent a run proving it is not
discoverable.

**The assumption nobody has tested, and you will hit it first.**
`AUDIT_SCOPE.md` records it: **nobody has ever verified that what the platforms
return matches what we store.** The API is treated as the source because it *is*
the source. The DICE side now has one external confirmation (the *reddition de
comptes*, to one ticket in 9,327) — **the Shotgun side has none.** You are about
to build a second independent consumer of the same APIs, which makes you the
first real cross-check this integration has ever had. **If your numbers disagree
with ours, we are not automatically right.**

---

## 6 · Our ingestion shape

**Cadence: every 4 hours**, six runs a day — *verified today*, `cron: '0 */4 * * *'`.
The reason is recorded in the workflow and is **not** cost: *"Actions minutes are
free here because the repo is public, so cadence is not a cost question — it is
about churn and queue exposure."* Each run commits, so each run is churn.

**Full refresh, with an unused incremental path.** Each run re-fetches each live
event in full. A sidecar `{event_id}_state.json` stores `cursor`, `rows`,
`max_ordered_at`, `shotgun_event_id` for a keyset resume — *verified today* —
deliberately a sidecar rather than CSV columns, because the merged CSV is
aggregate-only by contract and a per-ticket id column would break that.

**Where it is stored: a CSV per event**, 11 columns, committed to git —
*verified today*:

| column | type |
|---|---|
| `order_date` | date |
| `order_datetime` | naive datetime, second precision |
| `ticket_type`, `access_level`, `attendance_days`, `product_name` | text |
| `platform` | text — `Shotgun` or `DICE` |
| `price`, `gross_price` | decimal, currency units |
| `quantity` | int — **always 1**; one row per ticket |
| `is_paid` | 0/1 |

**An event whose history changed** is handled by full re-fetch: the file is
rewritten, and rows that no longer exist simply are not written. That is why §3's
shrink works at all — and it is exactly what an append-only store cannot do.

### ⛔ What I would do differently

1. **Store raw platform rows, then derive.** We classify and collapse at fetch
   time — product-name string matching, day attribution, channel filtering — so
   the raw payload is gone by the time anything is queryable. Every rule change
   since has needed a re-fetch. **On Postgres: one raw table per platform with
   the payload, and views for the semantics.**
2. **Use DICE's `purchasedAt` filter.** It is there, it is the missing half of
   incremental ingestion, and we never built on it.
3. **Make the account→event mapping data, with an assertion.** Ours is a
   hard-coded list with a silent default. The first thing I would add is a check
   that every configured event resolves to an account that actually returns
   tickets for it — which is precisely the test that would have caught
   `sonora_impact_2026` immediately.
4. **Resolve the timestamp zones before ingesting, not after.** We store naive
   datetimes from two platforms with different conventions and have never
   reconciled them.
5. **Keep a tickets-count history per event.** Our shrink was discovered by
   someone reading a dashboard. A table that records "this event reported N
   tickets at time T" makes a 2,744-row drop a row in a table instead of a
   discovery.

---

## 7 · What Festiflow should NOT copy

**Anything that exists because the output is static HTML on GitHub Pages.** You
have a Postgres. Specifically do not copy: the CSV-as-table, the merged-file-as-
state, the commit-per-run cadence, the rebuild-everything-on-any-change shape,
or the sidecar JSON state files. All of those are our constraint, not a design.

**`classify_ticket()` and `normalize_product_name()`.** String classification
over product names into type / access level / attendance days, plus title-casing
so two platforms' spellings collapse. It is tuned to our seven events' naming and
has an acronym exception list (`VIP`, `VVIP`, `PMR`, `XXL`, `EPK`…). **On another
promoter's catalogue it will mis-classify silently.**

**The two-platform channel dedupe, as written.** The *rule* is essential (§4) but
ours is conditional on an event having both ids in one config file. On a
multi-tenant schema that condition belongs somewhere else entirely.

**Known fragile, and we have been meaning to replace it:**

- **`MANUAL_DICE_CSVS`** — `geneve_2026`'s DICE sales are a **hand export from
  the back office**, committed as a CSV, because the token cannot reach that
  account. The code calls it "a stopgap". It also guards a handover path that
  **has never run in production** — the comment says so: *"A guard nobody has
  ever seen fire is a guard nobody has tested."*
- **The hard-coded `SHOTGUN_ACCOUNTS` event lists** — see §1 and §6.
- **The Shotgun fee split** — §3. Do not port a net-to-promoter number from us.

---

## Gaps, collected

Stated rather than filled, with what would settle each:

| gap | what would settle it |
|---|---|
| How either token is issued, by whom, from which account type | ask whoever created them |
| Whether either token expires or rotates | ask, or watch one for a year |
| Any approval / allow-listing step, and how long it took | ask Leo |
| Shotgun's real rate limit | deliberately hammer a test event and record the 429 |
| DICE's rate limit | same |
| Whether webhooks exist on either platform | their docs or their support |
| What `GET /events` returns on Shotgun | one authenticated call |
| Whether `viewer.orders` excludes returned tickets on DICE | compare `orders` against `returns` on one event |
| Pending / failed / test orders on both | enumerate the status values on a busy event |
| The zone of Shotgun's `ordered_at` | compare one order against the back office |
| Non-EUR events | we have none |
| **Whether what the platforms return matches what we store** | your rebuild is the first real cross-check |
