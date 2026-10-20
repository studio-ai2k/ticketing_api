# RETURN · XR2 — what it takes to pull Shotgun and DICE into Festiflow's database

**Seat:** Claude Code, measurement seat, 2026-10-20 (UTC evening).
**Against:** `studio-ai2k/ticketing_api` main `1665be5` · `studio-ai2k/Festiflow-V1` main `1b25da7` (read-only).
**Package:** `XR2_PACKAGE.zip`, MANIFEST.md5 checked: 11/11 OK. The brief and every corpus file were read before any call.
**Branch:** `probe/xr2` in ticketing_api. New files only: `.github/workflows/xr2-probe.yml`, `guide/xr2/probe_xr2.py`,
`guide/xr2/RUN`, `guide/xr2/out/*`, and this file. Never merged, no PR, main untouched, no existing file edited.
**Festiflow-V1:** read only. No branch, no commit.

**Runs.**

| run | trigger | what it did | result |
|---|---|---|---|
| [`39500965966`](https://github.com/studio-ai2k/ticketing_api/actions/runs/39500965966) | push | run 1: M1 M3 M4 M5 M6 M7 on Shotgun; M2 M3 M4 on DICE | success · outputs `ff91eb8` |
| [`39500976586`](https://github.com/studio-ai2k/ticketing_api/actions/runs/39500976586) | dispatch | a duplicate I started by testing the dispatch; **cancelled before it ran a step** | cancelled |
| [`39507722288`](https://github.com/studio-ai2k/ticketing_api/actions/runs/39507722288) | push | run 2: `/events` auth variants, the `/tickets` envelope, DICE follow-ups | success · outputs `d9fd6b1` |

Outputs: `guide/xr2/out/xr2_shotgun.{json,log}` · `xr2_dice.{json,log}` · `xr2_followup.{json,log}`.

Calls made: Shotgun **1 987** HTTP 200 + 38 non-200 (6 + 8 × 400, 2 × 401, 8 × 404, 14 × 429 challenge on `/`), plus 4 unauthenticated GETs on the public developer pages (3 × 404, 1 × 429). DICE **357**, all 200. No mutation was ever sent.

Markers: **measured** = this round's runs · **recorded** = the repo or corpus says so; I did not re-run it · **unknown** = nobody can say yet, with what would settle it.

---

## 0 · Corrections to the corpus, at source (read these first)

| # | the corpus / brief says | measured or found | source |
|---|---|---|---|
| C1 | DICE `Viewer.events` is "introspection only, never called" | It **was called** on 2026-08-23 (85 events), and again today: 85 of `totalCount` 85 | `ticketing_api/scripts/probe_croisiere.py` docstring · `HANDOFF_CC5.md` §2.2 · run 1 |
| C2 | `Viewer.events` "exists with no arguments" | It takes `first · after · last · before · where: EventWhereInput` (`startDatetime · endDatetime · onSaleDatetime · offSaleDatetime · state · updatedAt · id · genre`). The "no arguments" reading came from a dump that omits **every** argument (`PLATFORM_FIELD_INVENTORY.md`: "field arguments: no") | run 1 |
| C3 | `evt-cc` has no DICE id, and nobody holds one | **DICE 591517**, `Madame Loyal Paris : Crazy Carnaval Edition`, on the token's account: 1 139 orders, 1 546 tickets | `probe_croisiere.py` · run 1 |
| C4 | Shotgun `GET /events` answers 400 "because the token is missing"; one authenticated call settles it | With the token it still answers **400 `Missing API key`**. With `?key=<token>` it answers **401 `Invalid credentials`**. `/events` reads a *different* credential, and our ticket tokens are not one. ⇒ **neither token can list events** | runs 1 + 2 |
| C5 | The 429 on `/` is a rate limit | It is a **bot "challenge"** (`code: challenge`): 429 on every try, with no Retry-After. It is not a quota, and the standalone's recorded 429 on `/` was this | run 1 |
| C6 | `deal_channel`'s import values "never appeared"; the dedupe "never removed a ticket" (XR1 §4.1) | On other events they do appear: **`duplicata`** on Paris XXL (544 valid + 248 resold), Crazy Carnaval, Sonora Impact, Sonora Bordeaux Oct · **`distributor`** 1 473 on Crazy Carnaval · and **`pass_culture`, a channel nobody has listed**, on Rennes (26 valid), Sonora Impact and Sonora Bordeaux Oct | run 1 |
| C7 | Shotgun's "30-day grace" makes aged-out events un-refetchable (FINDINGS, "the backfill") | That is the standalone's **own** aging window. Shotgun answered full pulls today for Paris XXL (Mar) and Bordeaux (Jun), 27 844 and 27 217 rows. Only `epk_2023` is recorded as empty | run 1 · matrix 2026-10-06 |
| C8 | XR1 §1b: DICE Bordeaux is +59.00 against the reddition, and the cause is open | **Settled.** Exactly **one returned ticket is still listed** in `viewer.orders` for 540197: `fullPrice` 55.28 + `diceCommission` 3.72 = **59.00**, `returnedAt` 2026-05-28, reason `partner_issue`. The statement nets it; `orders` does not | run 2 |
| C9 | Genève's amounts may be in CHF (XR1 §4.4) | On Shotgun, every one of 8 624 Genève tickets says `currency = eur` | run 1 |
| C10 | `ordered_at`'s time zone is unknown | `ticket_updated_at` (UTC, `Z`) minus `ordered_at` is **+0 h** on the bulk of never-modified rows of every event (20 514 of 22 813 valid on Paris XXL), and is never negative ⇒ `ordered_at` is **UTC without a suffix**. Confidence high, not proven (a back-office comparison would prove it) | run 1 |
| C11 | (my own state-back) "a workflow only on a branch cannot be dispatched" | **Wrong.** Dispatch on `probe/xr2` was accepted (204). The duplicate run it created was cancelled before it ran a step | run 39500976586 |

---

## M1 · Can Shotgun list its own events? — **No, not with the tokens we have.**

**Calls (redacted).** `GET api.shotgun.live/events` with each token, in three variants: organizer id + co-host flag · organizer id only · co-host flag without organizer id. Run 2 added `?key=` · `?api_key=` · `Authorization` header (bearer scheme) · `x-api-key` header · token + header. Siblings with credentials: `/orders` · `/deals` · `/events/505434` · `/organizers` · `/`.

**Answers.**

| call | episode | sonora |
|---|---|---|
| `/events` + `token=` (all 3 variants) | 400 `Missing API key` | 400 `Missing API key` |
| `/events` + `key=<token>` | **401 `Invalid credentials`** | **401 `Invalid credentials`** |
| `/events` + `api_key=` / both headers / token + header | 400 `Missing API key` | 400 `Missing API key` |
| `/orders` · `/deals` · `/events/505434` · `/organizers` | 404 (an HTML page) | 404 |
| `/` | 429 `challenge` | 429 `challenge` |

So `/events` is a real route. It reads an API key from `key=`, and our ticket JWTs are not accepted as one.

**What it changes for Festiflow.** Shotgun events **cannot be listed** with what Festiflow can hold today. So for now Festiflow **stores the Shotgun event id per event**, plus the account (M3), and probes each new id once. One route stays open: a Shotgun API key of another kind (a "Smartboard API key"?). Leo may be able to issue one in the back office. **Unknown** whether one exists. Ask Shotgun, or look in Smartboard's settings.

A slow fallback is recorded: `/tickets` without `event_id` walks the whole organizer feed (`probe_croisiere.py`). At 100 tickets a page that is hundreds of pages. That is a discovery tool, not a design.

**Confidence:** high for "our tokens cannot list events". Unknown whether any credential can.

---

## M2 · DICE `Viewer.events`, live — **yes: one token lists its whole account.**

**Calls.** Live introspection of `Viewer`, every where-input, `EventState`, the root query and mutation types. `viewer { id name }` (booleans only). `viewer.events(first:100)` paged to the end. `node(id: Event:588085)`.

**Answers.**
- **85 events returned, `totalCount` 85, one page, 0.6 s.** By state: APPROVED 76 · CANCELLED 7 · DRAFT 2. Currency EUR on all 85. By start year: 2021 8 · 2022 20 · 2023 12 · 2024 26 · 2025 12 · 2026 7.
- Fields fetched: `id name startDatetime endDatetime state currency totalTicketAllocationQty`. `Event` has 27 fields in all.
- **Known ids present:** 526535 · 540197 · 573271 · 600413 · 591517 · 345933 · 395695 · 462095. **Absent: 588085 (Genève)**, and `node(Event:588085)` is null. The account boundary is confirmed live.
- 2026 on the token: Paris XXL **526535** (+ **525263 CANCELLED, same name, same date**) · Bordeaux **540197** (+ **525264 DRAFT**, "13 & 14 Juin") · Crazy Carnaval **591517** · Elektric Park **573271** · Rennes **600413**. No Sonora event, no Genève, no Halloween.
- Viewer identity: an id, and a name of 8 characters containing "episode". ⇒ **the DICE token is the EPISODE promoter account.**
- `Viewer` also exposes `tickets(where: TicketWhereInput)`. Its filters include `fanPhoneNumber` and `fanSecureToken`, which are personal. Festiflow must never use them.
- `EventWhereInput.updatedAt` exists: 1 event changed in the last 30 days. It works as an event-level change cursor.

**What it changes.** On DICE, Festiflow can **store the account and match events by name + date**. But the match **must filter `state = APPROVED`**: Paris XXL and Bordeaux each have a cancelled or draft twin with the same name and date. Storing the DICE id once the match is confirmed is still the safe end state. Genève and every SAGREGA event need another DICE account (§ Leo).

**Confidence:** high.

---

## M3 · Coverage matrix — every Festiflow event × platform × token

A full pull of all statuses, with `include_cohosted_events=1`, on **both** Shotgun tokens. Ticket-id overlap is computed between the two tokens.

### Shotgun

| Festiflow | Shotgun id | episode raw | sonora raw | same ticket ids | valid | resold | refunded | canceled | pp_pending | answers under |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| evt-px Paris XXL | 494642 | 27 844 | 27 844 | **27 844** | 22 813 | 5 008 | 3 | 6 | 14 | **both (co-host)** |
| evt-sb Bordeaux | 505434 | 27 217 | 27 217 | **27 217** | 22 767 | 4 217 | 9 | 204 | 20 | **both (co-host)** |
| evt-cc Crazy Carnaval | 549064 | 4 555 | **0** | 0 | 4 094 | 450 | — | 11 | — | episode |
| evt-ep Elektric Park | 535882 | 22 141 | **0** | 0 | 19 725 | 2 250 | — | 166 | — | episode |
| evt-si Sonora Impact | 544355 | **0** | 5 132 | 0 | 322 | 641 | **3 840** | 315 | 14 | sonora |
| evt-gv Genève | 546274 | 8 624 | **0** | 0 | 7 695 | 897 | — | 4 | 28 | episode |
| evt-rn Rennes | 557151 | 9 366 | **0** | 0 | 8 823 | 495 | — | 25 | 23 | episode |
| evt-croisiere | 553118 | 242 | **0** | 0 | 180 | 62 | — | — | — | episode |
| evt-sh Halloween XXL | **no id anywhere** | — | — | — | — | — | — | — | — | **unknown** |
| *(not in Festiflow)* Sonora Bordeaux 16–17 Oct | 565846 | **0** | 27 888 | 0 | 24 243 | 3 433 | — | 134 | 78 | sonora |

- **Every zero is a zero from the account that does not own the event.** All were HTTP 200, with no error. Probable cause: not owner and not an accepted co-host.
- **The double count is exact and total.** On both co-hosted Festiflow events, the two tokens return the **same** ticket ids: 27 844 = 27 844 and 27 217 = 27 217. A pull per account doubles 55 061 rows.
- `565846` is *SONORA BORDEAUX : 16-17 OCTOBRE*, not `evt-sh`. Festiflow does not hold it at all. `evt-sh` (31 Oct) is on neither DICE list and cannot be searched on Shotgun (M1).
- `evt-croisiere` (553118) is a **real Shotgun event**: 242 tickets, `Croisière Madame Loyal x Elektric Park 2026`. It is separate from the 74 combo tickets inside 535882 (recorded).
- No event answered for an id other than its own (`event_id_mismatch` 0 everywhere).

### DICE (one token, the EPISODE account)

| Festiflow | DICE id | orders = totalCount | tickets | empty orders | returns | transfers | returned ids still in `orders` |
|---|---|---:|---:|---:|---:|---:|---:|
| evt-px | 526535 | 9 967 | 12 679 | 427 | 563 | 2 444 | 0 |
| evt-sb | 540197 | 7 158 | 9 329 | 138 | 179 | 1 751 | **1** (the 59.00, C8) |
| evt-ep | 573271 | 1 845 | 2 555 | 28 | 46 | 371 | 0 |
| evt-rn | 600413 | 2 109 | 2 832 | 39 | 52 | 175 | 0 |
| evt-cc | 591517 | 1 139 | 1 546 | 21 | 27 | 137 | 0 |
| evt-gv | 588085 | **0** | **0** | — | 0 | 0 | — · cause: **account boundary** (C1/M2) |
| evt-si · evt-sh · evt-croisiere | — | not on this token | | | | | |

- DICE carries **no status** on orders or tickets. A return **removes the ticket** from `orders.tickets` (0 of 563, 46, 52 and 27 returned ids still listed; 1 of 179). `Order.quantity` keeps the original count: on Bordeaux, Σ quantity 9 508 − tickets listed 9 329 = **179 = returns**.
- The open question "does `viewer.orders` exclude returns?" is **answered: yes**, with one exception, the C8 ticket.
- `viewer.tickets(where eventId)` totalCount equals the ticket count read through orders: 2 832 and 9 329.
- Bordeaux reconciles: 9 327 paid + 2 free = 9 329, and `fullPrice` 624 991.67 = the standalone's figure to the cent. The statement's 624 936.39 differs by the C8 ticket.

**What it changes.** The account belongs to the **event**, never to a pull, and an event that starts answering on a second token is the double-count alarm. This is measured on the two largest events.

**Confidence:** high (full pulls, today).

---

## M4 · Incremental — Shotgun `after` cursor · DICE `purchasedAt` + `returnedAt`

**Shotgun.** `GET /tickets … after={ISO}_0`, a cursor synthesised 7 days and 1 day back:

| event | window | rows | ordered before the window (= modifications) | by status | new sales |
|---|---|---:|---:|---|---:|
| 557151 Rennes | 7 d | 1 103 | 87 | resold 80 · valid 5 · canceled 2 | 1 016 |
| 557151 Rennes | 1 d | 164 | 17 | resold 14 · canceled 2 · valid 1 | 147 |
| 565846 Sonora Bdx Oct | 7 d | 3 776 | 705 | resold 546 · valid 145 · canceled 13 · pp_pending 1 | 3 071 |
| 544355 Sonora Impact (cancelled event) | 7 d | 956 | **956** | **refunded 888** · canceled 59 · resold 9 | 0 |
| 546274 Genève | 7 d | 2 359 | 835 | valid 472 · resold 361 · canceled 2 | 1 524 |
| 535882 EPK | 7 d | 2 | 2 | resold 1 · valid 1 | 0 |

- **Refunds, cancellations and the resale flip all surface through the cursor**, as rows with their new status (888 refunds in one week on Sonora Impact).
- 0 rows came back with `ticket_updated_at` before the cursor, and a cursor at "now" returns 0 rows. The cursor is keyed on `ticket_updated_at`, as recorded.
- Cost: 12 pages instead of 94 for Rennes over 7 days, and 2 pages for a day. No other "since" parameter exists or is needed.
- The standalone's verify-incremental (run 31182334225, recorded) proved the positioning. What it cannot do is *apply* a modification: its CSV is aggregate. An upsert keyed on `ticket_id` can.

**DICE.**
- `orders(where:{eventId, purchasedAt:{gte}})` matches a full scan exactly: Rennes 46 = 46 over 7 days.
- `returns(where:{eventId, returnedAt:{gte}})`: Rennes 8 over 7 days.
- `Order` has **no `updatedAt`**, and `Adjustment` is 0 on every event.
- ⇒ **a refund does NOT surface through the `purchasedAt` filter.** The order is old; its ticket simply leaves the list. Removals come from **`returns` since the cursor** (each one carries a `ticketId`), or from a full re-pull.
- `ticketTransfers(where transferredAt)` is filterable the same way. Whether a transfer changes a ticket id is **unknown**.

**Confidence:** high on both.

---

## M5 · Volume

| | Festiflow's 8 Shotgun events | DICE (5 events with data) |
|---|---:|---:|
| rows, all statuses (raw) | **105 121** | 28 941 tickets / 22 218 orders |
| `valid` only | **86 419** (82 %) · Sonora Impact 6 % | n/a (returned tickets are already gone) |
| one raw row, full JSON | **≈ 1 340 B** (44 keys, max 1 445) | ≈ 280 B per ticket node, ≈ 590 B per order node (our selection) |
| one raw row, the 15 personal / ticket-identity keys dropped | **≈ 915 B** | — (DICE returns only what is selected) |
| a full pull, response bytes | ≈ 141 MB of rows | 13.4 MB |

Shotgun's key set is fixed at 44 on all 9 events (union = intersection). Always null: `ticket_seating`, and on most events `event_canceled_at`, `contact_company_name`, `ticket_scanned_at`.

**A year, raw rows kept.** Today's Festiflow calendar comes to ≈ 105 k Shotgun + 29 k DICE ≈ **135 k rows**. Adding the Sonora events Festiflow does not hold yet (565846 alone is 27.9 k) and `evt-sh` gives **≈ 170–200 k rows a year**. As `jsonb` without the PII keys that is ≈ **100–180 MB a year**, indexes included. Typed columns only (≈ 20 fields) would be ≈ 20–40 MB. A small table for Postgres on Railway either way.

**Confidence:** medium. The row counts are measured; the year is an extrapolation from one season.

---

## M6 · Limits

- **Shotgun:** 1 986 `/tickets` pages at 0.8 s pacing, **0 × 429 on `/tickets`**. ≈ 1.12 s per page with latency.
  - A full pull of the largest events: **≈ 310 s** (279 pages). Festiflow's 8 events on their owning token: 1 056 pages, **≈ 20 min**.
  - **No rate-limit header is sent** (header names: `age, cache-control, server, shotgun-domain-error, x-matched-path, x-vercel-cache, x-vercel-id`…). The ~100/min quota is still **unmeasured**: I did not hammer a shared token that the standalone's 4-hourly cron also uses.
- **DICE:** 357 queries, 0 × 429, no rate-limit header. 100 orders per page ≈ 1.4 s. Paris XXL in full ≈ 141 s; all five ≈ 316 s.
- Page sizes: Shotgun 100 (fixed). DICE `first:100` (larger not tested).

**Confidence:** high on what was seen. Unknown ceilings.

---

## M7 · Tokens

| | Shotgun EPISODE | Shotgun SONORA | DICE |
|---|---|---|---|
| shape | JWT HS256, 185 chars | JWT HS256, 215 chars | opaque, 48 chars `[A-Za-z0-9-]` |
| claims (names only) | `organizerId · memberId · forestUserEmail (null) · iat` | `organizerId · memberId · forestUserEmail (a string) · iat` | — |
| issued | iat 2026-02-25 | iat 2026-06-12 | unknown |
| expiry | **no `exp` claim** | **no `exp` claim** | unknown |
| whose | an organizer **member**: `memberId`; the `/tickets` envelope's `auth` echoes `{organizer_id, member_id}` | the same, and it carries a person's e-mail claim (value not printed) | the **EPISODE account** (viewer name) |
| scope | no scope claim; `/tickets` read works; write endpoints unknown | same | the schema has **one mutation, `claimTickets`** (never called). Whether this token may call it: unknown |
| fits Festiflow's `validate()` | yes (no `:`, no whitespace) | yes | yes |

- The Sonora organizer secret equals the code's default, is numeric, and fits Festiflow's `LOGIN_RX`.
- **The organizer id is inside the token** (`organizerId` = 171835 on Episode's; Sonora's matches its secret). Festiflow can store the token alone and read the organizer from it, but must not trust it without a test call.

**Separate tokens for Festiflow?** The claims say a token is **(organizer, member)**. *Recommend, do not do:* have each Shotgun organizer issue a token **from a dedicated member** (a "Festiflow" user), so revoking it never breaks the standalone. Then do the same on DICE if MIO allows a second token. **Where** each back office issues them, and whether issuing a new one revokes the old, is **not measurable from the API** (§ Leo).

**Does it fit `shim/integrations_store.js` as is?**
- **The storage shape fits:** provider (`shotgun` / `dice`) ‖ login (organizer id or account slug) ‖ secret.
- **The accessor does not.** `Credential.authorization()` returns `login:secret`, which is Qonto's header. Shotgun needs the secret in a *query string*, and DICE needs `Bearer <secret>`. Each needs its own accessor that keeps the secret private.
- Shotgun's also needs a **URL scrubber**: its `pagination.next` carries the token.
- **`scope` is unusable today.** `live()`, `logins()` and `storeCredential()` all hard-code `scope IS NULL`. A coproducer's token cannot be stored until those paths take a scope.

**Confidence:** high on the shapes. Unknown on issuance.

---

## M8 · Money fields — and what a KPI card can honestly show today

| | gross (buyer paid) | fees | VAT | face | net to promoter |
|---|---|---|---|---|---|
| **Shotgun** | `deal_price + deal_service_fee + deal_user_service_fee` (the standalone's `gross_price`) | `deal_service_fee` = **10.0 %** of face · `deal_user_service_fee` ≈ **3.02 %** (every event) · `deal_producer_cost` **0 on every row** | `deal_vat_rate` per ticket: 0.055, plus **0.2 on 114 tickets** of 565846 | `deal_price` (TTC) | **not derivable. O1 is still open on the Shotgun side** (`docs/O1_FEE_DECISION.md`: which fee the buyer bears is unknown; a Shotgun payout statement is needed) |
| **DICE** | `total` | `diceCommission` = Σ `fees[].dice`; categories **BOOKING · PROCESSING**, plus **PAID_WAITING_LIST** (176 + 59 + 1) and **TIER_DIFF** (163 + 12), never seen before · `fees[].promoter` **0** · `commission` **0** | none in the API; 5.5 % per the reddition (recorded) | `fullPrice` (**TTC**, recorded O1) | **= `fullPrice`.** The identity `fullPrice + diceCommission = total` holds on **28 941 / 28 941** tickets |

- Valid Shotgun face, measured: Paris XXL 1 416 585.82 € · Bordeaux **1 171 873.94 €** (= the standalone's stored figure, to the cent) · EPK 937 949.67 € · Genève 454 859.26 € · Rennes 553 296.41 €.
- **The KPI card can honestly show today:** tickets by status and channel on both platforms, and **face value TTC** on both (`deal_price` / `fullPrice`), with HT computed from the per-ticket VAT rate.
- It can show **DICE net** exactly.
- It **must not show a Shotgun net**, and must not add both platforms' "gross" into one net. That stays behind O1.
- Pending instalments (`payment_plan_pending`, 14–78 per event) remain E63's ruling.

**Confidence:** high on the fields and the DICE identity. The Shotgun split is unknown by construction.

---

## M9 · 505434 after a MADAMELOYAL acceptance — **not run.**

Nothing tells me Leo accepted the invitation before the run, and **no MADAMELOYAL token exists** among the four secrets. What I did re-measure: 505434 answers in full on **both** known tokens, with identical ticket ids (27 217 = 27 217).

---

## What Festiflow already has — read against it (§3)

- **The credential store** fits the storage shape; the accessor and `scope` paths need work (M7).
- **`apiReelFor` returns null** ("no ticketing bridge exists yet"), and the KPI standing warning applies: the zone has never seen non-zero data.
- **`dice_backend_url` / `shotgun_backend_url`** yield the ids (recorded) but not the account. This round shows that is a missing field, not a missing parse.
- **Admin → Intégrations.**
  - The locked S3 design (`tests/fixtures/qr3b/S3_integrations.html`) shows a server-key state, a credential per company (EPISODE · SAGREGA), a check of the key on save, the "Relier les comptes" step, and a sync report.
  - The code comment's `design/locked/S3_integrations.html` **does not exist** (confirmed).
  - **A Shotgun page and a DICE page need, beyond Qonto's:**
    1. **accounts per organisation**: Shotgun = organizer + member token (several per company possible); DICE = one promoter account, plus the ones it cannot see (Genève, SAGREGA)
    2. **an event ↔ platform table**: per event, the platform id, *the credential that returns its tickets*, and the date it was last probed
    3. **coverage alerts**: a configured event going to 0; an event answering on a **second** token; an unrecognised `deal_channel`; a DICE match with two candidates (a cancelled or draft twin)
    4. **last pull** per event: when, rows by status, delta since the previous pull, cursor age
    5. a **"what we cannot see" list**: Genève's DICE, SAGREGA's DICE, events with no id (`evt-sh`)

---

## One page — the shape I would build

**Stores.**
1. `ticketing_accounts`: provider · organisation (EPISODE / SAGREGA / …) · login (organizer id or DICE account) · credential row in `integration_credentials` · provenance (ours / a coproducer's) · last check.
2. `event_ticketing_links`, one row per Festiflow event × platform:
   - platform event id (stored; Shotgun cannot be discovered)
   - **the account that returns its tickets** (one per event × platform, never a per-account pull)
   - probe state (`answers` / `zero` / `second-account-answers`) and probed-at
   - source = `api` · `coprod-token` · `imported-csv` · `none`
3. **Raw rows, one table per platform, every status, upserted on the platform key.**
   - `shotgun_tickets(ticket_id PK, event_id, status, channel, deal_*, vat_rate, ordered_at timestamptz (UTC), ticket_updated_at, ticket_canceled_at, payload jsonb minus the 15 personal keys, first_seen, last_seen, source)`
   - `dice_tickets(ticket_id PK, order_id, event_id, purchased_at, fullPrice, diceCommission, total, fees jsonb, ticket_type, price_tier, present bool, returned_at, return_reason, source)`
   - `dice_returns` kept separately; a return flips `present=false` instead of deleting the row.
   - Imported standalone CSVs land with `source='imported-csv-filtered'` (entry 355).
4. `ticketing_pull_log`: per pull, event · account · mode (full / incremental) · rows by status · pages · seconds · cursor. This is the count history the standalone lacked.
5. **Aggregates are views** (valid by day, by channel, face TTC, DICE net), never stored truth.

**How often.**
- Incremental **hourly** for events on sale: Shotgun `after=<last ticket_updated_at>`; DICE `purchasedAt ≥ cursor` plus `returns returnedAt ≥ cursor`. That is ~1–12 pages per event.
- **A full re-pull nightly** per live event (≈ 20 min for all of Shotgun on the owning tokens) and weekly for finished ones within a season. A full pull is the only DICE path for transfers and adjustments, and the reconciliation check for both.
- Shotgun at **0.8 s pacing, one fetcher at a time per token**: the standalone's cron shares the same quota.

**What is an alert.**
- A configured event returning **0**.
- A Shotgun event answering on a **second** account (log it; never add it).
- A full pull returning fewer valid rows than the stored set by more than the period's refund and cancel rows.
- An unknown `deal_channel` or `ticket_status`.
- A DICE name + date match with **more than one** candidate.
- `totalCount` > orders processed.
- A credential's last call failing.

**What I would NOT copy from the standalone.**
- The per-run CSV, the sidecar JSON cursors, the aggregate-only rows, the hard-coded account lists with a silent `episode` default.
- `classify_ticket()` / `normalize_product_name()`.
- **The `deal_channel` allow-list as written:** it drops `pass_culture` on dual-platform events. Rennes loses 26 valid tickets today (C6). Whether `duplicata`/`distributor` are DICE re-imports is **unknown** and must be measured, not assumed.
- The "zero is a warning but publish anyway" path.
- Naive datetimes: store `timestamptz`, with `ordered_at` read as UTC (C10).

---

## What still needs Leo

1. **Shotgun `/events` key.** Is there a Smartboard "API key" distinct from the ticket token? Where, and can Festiflow have one? (M1)
2. **Issue separate tokens for Festiflow.** Shotgun: one per organizer, from a dedicated member (does a new token revoke an old one?). DICE: can MIO issue a second token? (M7)
3. **DICE for Genève and SAGREGA's events.** Which DICE account holds them, and can a token be issued for it? (M2/M3)
4. **`evt-sh` (Sonora Halloween XXL, 31 Oct).** Its Shotgun id (Smartboard URL), and its DICE id if any. **And 565846 (Sonora Bordeaux 16–17 Oct, 27 888 raw):** should Festiflow hold it?
5. **E64 / M9.** Does a MADAMELOYAL Shotgun account exist? If yes, accept the invitation and re-probe 505434.
6. **O1.** A Shotgun payout statement (which fee the promoter bears). Until then the KPI shows no Shotgun net.
7. **E63.** `payment_plan_pending`: count, show apart, or ignore.
8. **Rulings:**
   - Is `pass_culture` a sale (it is a paid channel)?
   - Are `duplicata` / `distributor` re-imports to drop when DICE also sells the event? Paris XXL 544, Crazy Carnaval 1 473 + 264. One back-office look settles it.
   - The standalone's channel filter should be told about `pass_culture` (theirs to fix, not ours).

---

## ⛔ How I checked that nothing leaked

- **Every printed string passes `scrub()`.** It removes each secret's literal value and any `token=…`, `Bearer …`, JWT, e-mail, URL, or opaque run of 40+ characters. The script never prints a URL, a request header, or a personal field. Shotgun's PII keys were only *counted* and size-measured. The DICE `Fan` type was never selected.
- **Before each commit**, the workflow's commit job grepped `guide/xr2/out` for the three secret values (exact match) and for `token=`, `Bearer `, `eyJ`, an e-mail, `http(s)://` and `contact_email":"`. It refused to commit on any hit. Both commits passed with **0 hits**.
- **I re-ran the same pattern scan locally on the committed outputs:** 0 hits for every pattern, including `ticket_scan_code":"` and `shotgun.live/…?`.
- GitHub masked the secrets in the run logs (`***`), and the runs printed only scrubbed lines.
- **Over-redaction, not a leak:** the scrubber's case-insensitive "bearer" rule ate part of my own label "(bearer scheme)". So `xr2_followup.json` does not parse as JSON. `xr2_followup.log` carries the same numbers.
- The Sonora organizer value was masked to `***` even inside a key name.
- **What this file does contain:** event ids, event names (public marketing names), dates, counts and summed amounts. No person's value.
