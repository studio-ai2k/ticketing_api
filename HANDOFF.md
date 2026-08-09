# Claude Code Handoff — API Fetch Proof Run

## Mission
Build `fetch_csv.py` that pulls live ticket data from Shotgun and DICE APIs and writes a merged CSV in the exact format `run.py` already consumes. Test with Rennes 2026. Do NOT modify any production files.

## Repo
`https://github.com/madameloyal/festiflow` — branch `main`

## Hard Constraints
- **DO NOT** modify: `run.py`, `main.py`, `upload.html`, `dashboard_template.html`, `event_config.csv`, any `*.html` in root, anything in `festiflow-v5/csv_database/`
- **DO NOT** write to any path that Railway reads from
- All new files go in `festiflow-v5/api_output/` (create this directory)
- Pure Python stdlib only — zero pip dependencies
- The fetch script must produce a CSV that `run.py` can consume without modification

## Output Format — The Merged CSV
`run.py` reads a CSV with exactly these 11 columns. Your fetch script must produce this exact format:

```csv
order_date,order_datetime,ticket_type,access_level,attendance_days,product_name,platform,price,gross_price,quantity,is_paid
2025-06-05,2025-06-05 19:12:00,samedi,early_entry,['samedi'],Pass Samedi - Entrée Avant 21h,DICE,41.514,44.0,1,1
2026-01-06,2026-01-06 18:00:18,3-jours,regular,['jeudi','vendredi','samedi'],General Access - Pass 3 Jours,Shotgun,95.0,97.87,1,1
```

### Column specs:
| Column | Type | Source | Notes |
|---|---|---|---|
| `order_date` | `YYYY-MM-DD` | Shotgun: `ordered_at[:10]` / DICE: `Order.purchasedAt[:10]` | |
| `order_datetime` | `YYYY-MM-DD HH:MM:SS` | Shotgun: `ordered_at` / DICE: `Order.purchasedAt` | Strip timezone, format to seconds. **NOT `claimedAt`** - that is wallet activation, null until close to the event (all 2,215 Rennes 2026 tickets came back null). The code has used `purchasedAt` since the orders query replaced the tickets query; this table said `claimedAt` until 2026-08-08. |
| `ticket_type` | string | Classified from ticket name | One of: day name (`samedi`, `vendredi`, `jeudi`), `2-jours`, `3-jours`, `single_day` |
| `access_level` | string | Classified from ticket name + price | One of: `regular`, `vip`, `invitation`, `early_entry`, `backstage`, `jeu_concours`, `group_discount` |
| `attendance_days` | string | Classified from ticket name | Format: `['samedi']` or `['vendredi','samedi']` — Python list repr as string |
| `product_name` | string | Shotgun: `deal_sub_category` / DICE: `ticketType.name` | Title case if all-upper |
| `platform` | string | Hardcoded | `Shotgun` or `DICE` (capital S, capital D) |
| `price` | float | Shotgun: `deal_price / 100` / DICE: `fullPrice / 100` | Net price in currency units (not cents) |
| `gross_price` | float | Shotgun: `(deal_price + deal_user_service_fee) / 100` / DICE: `total / 100` | What buyer paid |
| `quantity` | int | Always `1` | One row per ticket |
| `is_paid` | int | `0` if invitation/jeu_concours or price=0, else `1` | |

## Ticket Classification
Copy the `classify_ticket()` and `resolve_attendance()` functions from `festiflow-v5/run.py` (lines 563-745). These are the single source of truth for ticket_type, access_level, and attendance_days. Do not rewrite them — copy verbatim.

Key behaviors:
- `PHASE 1 - PASS SAMEDI` → ticket_type=`samedi`, access_level=`regular`
- `VIP - PASS 2 JOURS` → ticket_type=`2-jours`, access_level=`vip`
- `INVITATION PASS SAMEDI` → ticket_type=`samedi`, access_level=`invitation`, is_paid=0
- `ENTRÉE AVANT 21H - PASS VENDREDI` → ticket_type=`vendredi`, access_level=`early_entry`
- Price = 0 and no invitation keyword → force access_level=`invitation`, is_paid=0

For Shotgun: classify using `"{deal_sub_category} {deal_title}"`. Use `deal_sub_category` as `product_name`.
For DICE: classify using `ticketType.name`. Use `ticketType.name` as `product_name`.
For Shotgun: if `deal_channel == 'invitation'`, pass `tags='invitation'` to classify_ticket.

## Two Shotgun Accounts

Events are split across two Shotgun organizer accounts:

| Account | Organizer ID | Token secret | Events |
|---|---|---|---|
| Episode | `171835` | `SHOTGUN_TOKEN_EPISODE` | epk_2026, rennes_2026, geneve_2026 |
| Sonora | `207784` | `SHOTGUN_TOKEN_SONORA` | bordeaux_2026, bordeaux_oct_2026 |

Add a `shotgun_account` column to the fetch logic. Read from `event_config.csv`:
- If `shotgun_event_id` is in the Episode event list → use Episode token + org ID
- If `shotgun_event_id` is in the Sonora event list → use Sonora token + org ID

For V1 simplicity: add a hardcoded mapping in the fetch script:
```python
SHOTGUN_ACCOUNTS = {
    'episode': {
        'token_env': 'SHOTGUN_TOKEN_EPISODE',
        'organizer_id': '171835',
        'events': ['epk_2026', 'rennes_2026', 'geneve_2026', 'epk_2023']
    },
    'sonora': {
        'token_env': 'SHOTGUN_TOKEN_SONORA',
        'organizer_id': '207784',
        'events': ['bordeaux_2026', 'bordeaux_oct_2026', 'bordeaux_2025', 'halloween_2025']
    }
}
```

## Shotgun REST API

**Endpoint:** `GET https://api.shotgun.live/tickets`

**Auth:** `?token=xxx&organizer_id=171835&event_id=535882`

**Pagination:** 100 tickets per page. Response has `pagination.next` URL. Follow until `next` is null.

**Rate limit:** 100 requests/minute. Pace at 0.8s between requests.

**Ticket filtering:** Only process tickets where `ticket_status` is `valid` or `resold`. Skip `refunded`, `canceled`.

**Field mapping:**
```
ordered_at          → order_date ([:10]) and order_datetime
deal_sub_category   → classify input + product_name
deal_title          → classify input (combined with sub_category)
deal_channel        → if 'invitation' → pass tags='invitation' to classifier
deal_price          → price (divide by 100, it's in cents)
deal_user_service_fee → added to deal_price for gross_price
deal_vat_rate       → not needed for CSV, but available
ticket_status       → filter: only 'valid' and 'resold'
```

**Sample response** (one ticket): see `festiflow-v5/api_output/shotgun_schema.json` if it exists, or reference this:
```json
{
  "deal_price": 9500,
  "deal_service_fee": 950,
  "deal_user_service_fee": 287,
  "deal_sub_category": "GENERAL ACCESS - PASS 3 JOURS (JEUDI + VENDREDI + SAMEDI)",
  "deal_title": "PHASE 1",
  "deal_channel": "online",
  "ticket_status": "valid",
  "ordered_at": "2026-01-06 18:00:18.038852"
}
```
This ticket → `price=95.0`, `gross_price=97.87`, `ticket_type=3-jours`, `access_level=regular`, `platform=Shotgun`

## DICE GraphQL API

**Endpoint:** `POST https://partners-endpoint.dice.fm/graphql`

**Auth:** `Authorization: Bearer {DICE_TOKEN}`

### CRITICAL: Relay ID Encoding
DICE GraphQL uses Base64-encoded Relay IDs. The `event_config.csv` stores numeric IDs (e.g. `600413`). You MUST encode them:
```python
import base64
relay_id = base64.b64encode(f'Event:{numeric_id}'.encode()).decode()
# 600413 → 'RXZlbnQ6NjAwNDEz'
```

### Tickets Query (get ticket data + fees):
```graphql
query FetchTickets($eventId: ID!, $first: Int!, $after: String) {
  node(id: $eventId) {
    ... on Event {
      name
      startDatetime
      endDatetime
      tickets(first: $first, after: $after) {
        totalCount
        pageInfo { endCursor hasNextPage }
        edges {
          node {
            id
            code
            fullPrice
            commission
            diceCommission
            total
            fees { category dice promoter }
            ticketType { name }
            claimedAt
          }
        }
      }
    }
  }
}
```

**DO NOT add any other fields to these queries.** These are schema-verified via live introspection. Adding fields that don't exist (like `amount` on TicketFee, or `type` on PriceTier) will crash the query.

### Schema-verified types (from introspection):
- **TicketFee:** `category` (enum), `dice` (Int, cents), `promoter` (Int, cents) — NOT `amount`
- **PriceTier:** `id`, `name`, `price`, `faceValue`, `allocation`, `doorSalesPrice`, `time` — NO `type` field
- **TicketType:** `id`, `name`, `description`, `price`, `faceValue` — all valid

### DICE Field Mapping:
```
claimedAt           → order_date and order_datetime (no purchasedAt on tickets)
ticketType.name     → classify input + product_name
fullPrice           → price (divide by 100, cents)
total               → gross_price (divide by 100, cents)
```

### DICE: Do NOT use viewer.orders
An earlier version tried to fetch `viewer.orders` for purchase dates. This scans ALL orders across ALL events for the promoter — it hangs for 15+ minutes and times out. Use `claimedAt` from the ticket instead. It's not the exact purchase date but it's close enough and available directly on the ticket.

## Event Config for Rennes 2026 (test event)

From `event_config.csv`:
```
event_id: rennes_2026
shotgun_event_id: 557151 (Episode account)
dice_mio_id: 600413
compare_to: rennes_2025
comparison_mode: j_minus
days:
  1: Vendredi, 2026-11-06, capacity 10000
  2: Samedi, 2026-11-07, capacity 10000
```

## Event Day Configuration for Classification

The classifier needs event_days to resolve attendance. For Rennes 2026:
```python
event_days = [
    {'day_name': 'vendredi', 'day_date': datetime.date(2026, 11, 6), 'day_number': 1},
    {'day_name': 'samedi', 'day_date': datetime.date(2026, 11, 7), 'day_number': 2},
]
```

Read these from `event_config.csv` dynamically.

## Phases

### Phase 1 — Fetch and Write CSV
1. Read `event_config.csv` for rennes_2026 config
2. Fetch Shotgun: `GET https://api.shotgun.live/tickets?token={SHOTGUN_TOKEN_EPISODE}&organizer_id=171835&event_id=557151`
3. Fetch DICE: GraphQL query with Relay ID `RXZlbnQ6NjAwNDEz`
4. Classify all tickets using `classify_ticket()` from run.py
5. Write to `festiflow-v5/api_output/rennes_2026_merged.csv`
6. Print summary: total tickets, Shotgun count, DICE count, paid/free split, gross revenue

### Phase 2 — Validate Against Production
1. Copy the API-generated CSV to a temp directory as the "current year" data
2. Copy `festiflow-v5/csv_database/rennes_2025/rennes_2025_merged.csv` as historical data
3. Run: `python festiflow-v5/run.py` with env vars pointing to these directories + rennes_2026 config
4. Capture output HTML as `festiflow-v5/api_output/rennes_test.html`
5. Compare key metrics against the current live `rennes.html`:
   - Total tickets sold (paid)
   - Total CA (revenue)
   - Per-day breakdown
   - Number of ticket types in répartition table
6. Report discrepancies. Small differences are OK (API might have newer data than last CSV upload). Large differences (>5%) flag a mapping issue.

### Phase 3 — GitHub Actions Workflow (only after Phase 2 passes)
Create `.github/workflows/daily-fetch.yml`:
- Trigger: `schedule: cron '0 6 * * *'` (06:00 UTC = 08:00 Paris) + `workflow_dispatch` for manual runs
- For each active event in `event_config.csv`: run fetch → write CSV → run `run.py` → commit HTML
- Secrets injected as env vars: `SHOTGUN_TOKEN_EPISODE`, `SHOTGUN_TOKEN_SONORA`, `SHOTGUN_ORGANIZER_ID_SONORA`, `DICE_TOKEN`
- Commit message: `Auto-update: {event_id} ({date})`
- Only commit if HTML actually changed (diff check)

## Secrets Available (already set as Repository secrets)
- `SHOTGUN_TOKEN_EPISODE` — Episode account JWT
- `SHOTGUN_TOKEN_SONORA` — Sonora account JWT
- `SHOTGUN_ORGANIZER_ID_SONORA` — `207784`
- `DICE_TOKEN` — Greg Germain promoter-level DICE MIO token

Episode organizer ID is `171835` (hardcode as default).

## Success Criteria
Phase 1: CSV written with >0 tickets from both platforms, 11 columns, correct classification
Phase 2: Metrics within 5% of current live dashboard (or exact match if same data)
Phase 3: Action runs, commits HTML, GitHub Pages deploys

## What to Report Back
After Phase 2, produce a comparison table:
```
                    Live Dashboard    API Dashboard    Delta
Tickets (paid):     XXXX              XXXX             X%
Revenue:            €XX,XXX           €XX,XXX          X%
Vendredi:           XXXX              XXXX             X%
Samedi:             XXXX              XXXX             X%
Ticket types:       XX                XX               —
```

If any column is missing or misclassified, report which tickets diverged and why.

---

## Pages deploys: do NOT add deploy-pages@v4 (2026-08-06 outage)

`Settings > Pages > Source` is **"Deploy from a branch"**, confirmed by Leo.
The legacy `pages build and deployment` builder is therefore the only path that
works, and it is fast: run 31113735296 deployed in **6 seconds** at 15:01 UTC.

A separate handoff document (`HANDOFF_V6_6.md`, not in this repo) carries a
trap list whose entry #11 reads:

    "Pages deploys timeout at 10 min. Fixed by switching to Actions deploy
     with deploy-pages@v4."

**That prescribed fix is what caused the outage it describes.** `deploy-pages@v4`
only works when Source is "GitHub Actions". Adding it while Source is
branch-based leaves two paths contending for the single deployment slot, and
every deploy after 15:02:56 UTC hung in `deployment_in_progress` until the
action gave up - the legacy builder included, which had been healthy minutes
earlier. Roughly five hours of dashboards never reached the site.

Rewrite the trap as:

    "deploy-pages@v4 requires Source = GitHub Actions. Adding it while Source
     is branch-based breaks ALL deploys, including the branch builder that was
     working."

`.github/workflows/deploy-pages.yml` was deleted for this reason. Do not
reintroduce it without switching Source first, and prefer leaving the branch
path alone - it has a demonstrated success and needs no help.

Note also that two handoff documents exist and disagree; this file had no trap
list at all before this entry, which is how the contradiction went unnoticed.

## RESOLVED: main.py github_push() - file deleted 2026-08-07

The section below described an unaudited publishing route. `main.py` has since
been deleted as orphaned, so the route no longer exists. Kept for context.

## (historical) Unaudited: main.py github_push() publishes to a second repo

`main.py` has a publishing path nobody has reviewed as part of the API work:

    GITHUB_REPO = os.environ.get("GITHUB_REPO", "")   # e.g. madameloyal/festiflow
    def github_push(event_id, html_content):          # PUT .../contents/{filename}

It writes dashboard HTML into a **different repository** over the GitHub
contents API, using `GITHUB_TOKEN` / `GITHUB_REPO` from the environment. That
is a second route by which these dashboards reach the internet, entirely
separate from the Pages deploy this project drives, and outside the
do-not-modify boundary that covers `main.py` itself.

Worth an hour on its own, independent of the Pages work. Open questions:

- Which repo does `GITHUB_REPO` actually point at in the Railway environment,
  and is that repo public?
- Is this path still invoked, or dead code left from the manual upload flow?
- Does it publish the same post-processed HTML, or the raw run.py output with
  the upload link and the old footer?
- Whatever access control gets put in front of ai2k.dev does not apply to it.

## run.py and main.py are borrowed build tools

Both were copied in from `madameloyal/festiflow` and are used here only to
render dashboards. Their assumptions do not describe this repo:

- `run.py`'s `DATA_DIR` layout (`data/raw`, `data/output`, `data/merged`) and
  `main.py`'s Railway upload flow belong to that other project. **This repo has
  no Railway deployment and no manual upload path** - the whole pipeline is
  Actions fetches the APIs, writes CSVs, renders HTML, commits, Pages serves.
- So `data/` here is free for our own use, and holds the committed merged CSVs
  that incremental fetching resumes from.

This has already caused one wrong call (a `data/raw` PII collision that cannot
happen here). When reasoning about paths, check whether the assumption comes
from the borrowed tool or from this pipeline.

## Trap: anything new under data/ must be re-admitted to git

The `data/` ignore rules were inherited from `run.py`'s DATA_DIR layout in
`madameloyal/festiflow`, a repo whose data model does not apply here. That has
now caused two problems with the same root:

1. The merged CSVs were nearly blocked by a wholesale `data/` ignore.
2. Every `data/{event}_state.json` cursor was silently discarded - the daily
   run wrote them, git ignored them, and they vanished with the runner. The
   CSVs seeded correctly, so nothing looked wrong; incremental simply could
   never resume.

**Any new file written under `data/` must be explicitly re-admitted in
`.gitignore` and staged in the commit step, or it disappears with the runner.**
Current re-admissions: `!data/*_merged.csv`, `!data/*_state.json`.

## Iterating on presentation costs nothing

`scripts/build_dashboard.py --csv data/{event}_merged.csv` regenerates a
dashboard from the committed CSV with **zero API calls, in ~1.3 seconds**.
All six rebuild in about eight. Use it for every presentation change - a
stylesheet swap, a postprocess edit, a design pass - instead of a full fetch:

    for e in paris_xxl_2026 bordeaux_2026 epk_2026 \
             bordeaux_oct_2026 geneve_2026 rennes_2026; do
      python scripts/build_dashboard.py --event $e \
        --csv data/${e}_merged.csv --out api_output/$e.html
      python scripts/postprocess_html.py api_output/$e.html
    done

The data only needs refetching when the *numbers* should change.

## Finished events are not refetched

The daily job derives a per-event `fetch` flag from `max(day_date)` plus a
30-day grace period (stdlib only - no dateutil, so a calendar month is
approximated). Past that, the event is rebuilt from its committed
`data/{event}_merged.csv` and no API call is made.

**Why derived and not a status value.** `status` is read in two places that
matter: the workflow's plan job (the fetch gate) and `run.py:2088`, which
builds `SESSION_SWITCHER_OPTIONS`. Demoting a finished event out of `active`
would drop it from the event dropdown on every dashboard, and `run.py` is
off-limits. Deriving gates the fetch and touches nothing else.

The grace period exists because sales run up to and during the event and
refunds, chargebacks and settlement corrections land for weeks afterwards.
An unparseable `day_date` fetches rather than skips - reading as "past" would
silently freeze a live event. A missing stored CSV also falls back to fetching.

`main.py` was deleted here: orphaned (nothing imports or invokes it), a
Railway upload tool from madameloyal/festiflow with no role in this pipeline.
That also closes the unaudited `github_push()` route to a second repository -
the file is gone, so the route is gone.

## Cadence, and why --incremental exists but is not used

The daily job runs **every four hours**, with **full fetches**. `--incremental`
is built, tested and verified, and deliberately not wired in. It is not broken.

**The cursor is fully verified — accepted AND correctly positioned.** Shotgun's
`after` parameter is a keyset cursor of shape `{ticket_updated_at}_{ticket_id}`,
not a date filter, and we synthesise one from the last row of a completed fetch
rather than keeping the `pagination.next` the API handed us. Both halves of that
are now proven by `verify-incremental.yml` (`workflow_dispatch`, self-contained,
runs a full and an incremental fetch in the same job):

| run | window | result |
| --- | --- | --- |
| `epk_2026` | 12h backdated | PASS (detector) — H9 caught 3 modified rows |
| `rennes_2026` | 6h backdated | PASS (detector) — H9 caught 2 modified rows |
| `rennes_2026` | **2h backdated** | **PASS (positioning)** — delta of 5 rows against a full Shotgun side of 1,379, **zero rows lost, zero gained**, H3 silent. 31s full vs 16s incremental. |

The two detector passes are passes, not failures: a backdated window containing
a refund makes H9 fire on a row whose `ordered_at` predates the cutoff, and it
aborts into a full refetch, which is the designed behaviour. But they leave
positioning untested, which is why the 2h run mattered — a mispositioned cursor
would have shown up as rows lost or gained versus the full fetch.

**The measured modification rate is the evidence for leaving incremental off.**
Roughly **2 modifications per 6h on rennes, 3 per 12h on epk, 0 per 2h**. At a
four-hourly cadence the H3 guard would trip on most windows for a live event,
and every trip costs a full refetch on top of the incremental attempt — i.e.
incremental would be *slower* than full more often than not. Re-measure before
reopening this; the rate is a property of how the events are selling, not of
the code.

**Actions minutes are free here because the repo is PUBLIC.** GitHub's free
allowance for private repos (2,000 min/month) does not apply. That makes
cadence a question of churn and queue exposure rather than cost: every run
commits the dashboards, and runner queues reached 27 minutes on 2026-08-06, so
hourly would buy 24 daily chances at contention and 24 commits of churn for
numbers nobody reads hourly.

**This is a live coupling to the security decision.** If the repo ever goes
private - the mitigation for the client-side-only password gate - Actions
minutes start billing per job, rounded up to the minute. At six jobs per run
(plan + four events + commit) that is ~6 billable minutes per run regardless of
how fast the fetches are: ~4,300 min/month hourly, ~1,080 at four-hourly. The
cadence question reopens the moment visibility changes. Leo has deferred the
security fix to the Festiflow migration (Postgres + proper login), so it stays
public for now.

Why full fetches rather than incremental, at current volumes:

- J3 already removed ~70% of the fetch volume by not refetching finished events.
- The four live events are small. Rennes is 33 seconds for a *full* fetch.
- Abort-to-full-refetch is provably correct and has no mutation path that can
  corrupt a stored file. Incremental's savings are seconds.

**Correction, 2026-08-08 — DICE incremental is possible after all.** This
decision was taken with DICE recorded as full-fetch-only, and that premise was
wrong. The field probe (run 31235118312) recovered the input-object fields the
old introspection dump was missing, and `OrderWhereInput` carries
**`purchasedAt`** alongside `eventId` and `id` — DICE orders *can* be filtered
server-side by purchase date. Nothing has been built on it.

**The decision stands, on cost rather than capability.** J3 removed most of the
volume and the four live events are small; a DICE incremental would save
seconds it is not worth spending complexity on. But the record should say we
chose not to, not that we could not — the difference matters the next time
somebody re-derives this from the handoff.

## Option not taken: correcting a modification in place

If incremental is ever wired in, the expensive part is that a modification
(refund, cancellation, resale) aborts the whole event to a full refetch. It
does not have to.

A stored row is not *identified* by its ticket, it is **derived** from it by
`process_shotgun_ticket`, and a status change does not touch any input to that
derivation - `ordered_at`, `deal_sub_category`, `deal_price` and the fee fields
are all unchanged by a refund. So:

1. Run the modified raw row through `process_shotgun_ticket` **bypassing the
   status filter**. That reconstructs the exact 11-column row currently in the
   stored CSV.
2. Remove **one** matching row (multiset removal - two identical tickets are
   interchangeable, so removing either is correct).
3. If no exact match is found, fall back to a full refetch.

A resale needs no special case: the original returns as `resold` (remove one)
and its replacement arrives `valid` in the same delta (append). Net zero.

Roughly 25 lines, no schema change, no identity column. The reason it was not
built is risk, not difficulty: it is a mutation path over live revenue figures,
and it would want weeks of observation before being trusted to save seconds
inside a job that is already fast. Revisit if volumes grow or the migration
changes the picture.

## Publishing only when the data moved

The build skips an event entirely when its freshly fetched CSV is
byte-identical to the committed one: no rebuild, no staging, no artifact. If
every event is unchanged the commit job commits nothing and no Pages deploy
fires.

**Compare the CSV, never the HTML.** The generated HTML changes on every run
regardless - the footer carries `Données API · HH:MM` and the J-X countdown
moves daily - so an HTML comparison would never skip anything. Skipping the
*rebuild* is the point: a rebuild mints a fresh timestamp, which forces a
commit, which fires a deploy.

Finished events fall out of this for free - their CSV is copied straight from
`data/`, so it is identical by construction.

**A design change moves no data.** After editing `postprocess_html.py`, the
stylesheet, or anything else presentational, dispatch the workflow with
`force_rebuild: true` or nothing will publish. Without it the change looks like
a deploy failure, which has already been misdiagnosed twice.

Not pursued: reading the merged CSVs client-side instead of pre-rendering. The
CSV is one row per ticket, so paris_xxl is 3.7 MB against 185 KB of HTML and
epk 914 KB against 270 KB - the pre-computed page is far smaller than the data
behind it. It would also mean porting run.py's analytics to JS while run.py
stays authoritative, and would not reduce deploys, since any commit triggers
Pages regardless of content.

## The chart palette (applied 2026-08-07)

Leo ruled it in. The projection charts now use the mock's palette:

| series | was | now |
| --- | --- | --- |
| Ventes 2026 (sales line) | `#fbbf24` amber | `#ffffff` white |
| Trajectoire / projection | `rgba(251,191,36,.8)` amber | `#60a5fa` blue |
| prior-year reference | red dashed | unchanged |

Applied in `_recolour_projection` (`postprocess_html.py`), with the legend
swatches so the key agrees with the line. `run.py`'s Chart.js configs
(3604 / 3741 / 3746) are do-not-modify, so this is a postprocess rewrite.

**`#fbbf24` is NOT safe to replace globally.** It also drives the day tag text
colours, the hebdo bar chart, and the velocity and revenue charts - twelve
occurrences outside the projection block on a two-day event. The pass is
therefore scoped twice over: the swatch swap runs only inside
`#sec-projection`, and the dataset swaps only inside the brace-matched config
of a `chartDay{N}S{1,2}` chart, keyed on `borderColor:` rather than on the bare
colour. Both directions are asserted - amber must be **gone** from
`#sec-projection` and must still be **present** document-wide. A zero count
document-wide means the replace was too broad.

**Two residual differences from the mock, both deliberate.** The mock draws the
projection as a solid line with a solid legend swatch labelled "Projection";
here it stays dashed, labelled with the scenario name (`Trajectoire 2023`,
`2023 x coef. 2026`). The dash is what distinguishes projected from actual, and
the scenario name is dynamic per event. Leo's ruling was colour only. Line and
swatch agree with each other, which was the requirement.

**How this was nearly missed, which is the transferable part.** The Deploy 2
spec asked for one swap, `rgba(96,165,250,.8)` -> `#60a5fa`, justified as "so
the line matches its own legend swatch". That literal appears **zero times** in
anything this repo generates - the spec took it from the mock. Reading it as a
mismatch fix makes it a no-op and the whole palette change disappears silently.
It was never about a mismatch; it was the tail end of a recolour whose other
half was never specified.

> **If a spec line looks like a no-op against generated output, check whether
> it is the visible corner of a larger change.**

The `rgba(96,165,250,.8)` entry is still wired and counted, so if the palette
ever moves to the mock's own pre-recolour blue it cannot regress silently.

## Chart canvases: assert the ancestry, not just the markup

Three charts build lazily off `canvas.closest('.ac-body')` — `chartVelocity`,
`chartVelocity14`, `chartRevenue` — and Deploy 2 moves `.ac-body` elements
around them. A `closest()` that stops resolving throws nothing and logs
nothing; the chart simply never draws.

`_assert_projection` therefore walks the div stack from the top of the document
and asserts each of those canvases still has an `.ac-body` ancestor. **Keep
this.** A markup-count assertion cannot catch a re-parenting bug — the counts
stay right while the tree is wrong.

Rendering was also verified end to end in headless Chromium (available in the
container at `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`; Chart.js
comes from npm, since cdnjs is blocked by the network policy — intercept the
`<script src>` with a Playwright route). All six dashboards: every S1 chart
builds and paints, `switchScenario` still builds S2 at full width, no page
errors. Worth repeating after any pass that moves markup.

## The footer carries two different facts — keep them distinct

```
🎟 Dernier billet vendu · DD/MM · HH:MM     how fresh is the DATA
🔄 Données API · HH:MM                      how fresh is the CHECK
🔒 Données figées · DD/MM                   finished event, no longer checked
```

**M1 broke the middle one and it had to be fixed separately.** With
Build/Stage/Upload gated on `changed == 'true'`, a run where nothing sold never
regenerates the page, so `{{DATA_TIME}}` froze at the last time a ticket
**sold** rather than the last time a fetch **ran**. At four-hourly on a quiet
event the stamp drifts within a day, and a dashboard reading
"Données API · 16:50" at 21:00 is indistinguishable from a broken pipeline.
That exact failure has been misdiagnosed twice on this project.

The fix keeps M1's benefit: **CSV changed → full rebuild as before. CSV
unchanged → do not invoke `run.py`; patch the stamp in place in the already
committed HTML** (`scripts/stamp_footer.py`). A quiet event produces a six-byte
diff instead of a full regeneration. What it costs is the no-commit case - up
to six small commits a day - which is the price of a timestamp that tells the
truth.

Four cases, all exercised:

| fetch | CSV changed | what happens |
| --- | --- | --- |
| yes | yes | full rebuild; `run.py` mints the stamp itself |
| yes | no | `--checked $(date +%H:%M)` — six-byte diff |
| no (finished) | no | `--frozen` — once, then a no-op forever |
| no (finished) | yes (`force_rebuild`) | rebuild, then `--frozen` restores the freeze date from `git show HEAD:<file>` |

**A failed fetch never reaches the stamp step** — the job fails at `Fetch
tickets` and the previous stamp survives, which is the honest outcome. Never
bump a stamp on a fetch that did not happen.

**Finished events must not be bumped** — nothing was checked. They get
`🔒 Données figées · DD/MM` instead, dated the day they froze. "figées" says
the numbers will not move again and the date says since when, so a receding
date reads as a deliberate end state rather than a stalled job. Rejected:
"Données finales" (describes the result, not the pipeline state) and anything
built on "dernière vérification" (a claim that we checked, which is exactly
what we did not do). After the first freeze commit a finished event contributes
zero churn forever.

The `--frozen` path deliberately reads the previous freeze date back out of
`git show HEAD:<file>`. Without that, a `force_rebuild` on a finished event
would regenerate the page with a fresh "Données API · HH:MM" — a stamp claiming
a fetch that never happened — and the original freeze date would be lost.

**Considered and not taken:** publishing the check time as a small JSON file
fetched client-side. It shrinks the diff from six files to one, but it still
commits and still deploys, so it saves nothing that matters; it adds a runtime
dependency with a silent failure mode; and it loses the per-event stamp, which
is exactly what makes the frozen/live distinction visible.

## Standing rule: every count says what it counts

Three shipped bugs, all the same mistake — a stylesheet selector counted as
markup:

| | claimed | actual (markup) | where the extra came from |
| --- | --- | --- | --- |
| `.ac-t` baseline | 8 | 4 | four `.ac-t` selectors in the CSS |
| `.inset-divider` | 3 | 2 | the `.inset-divider` rule |
| `sw-wrap` guard | "present" | absent | the guard matched the stylesheet, so **every** dashboard silently got no nav markup |

So, without exception:

1. A markup count keys on `class="name"`, never the bare word.
2. Every assertion states whether it is over **markup** or the **whole file**.
   "3 `.inset-divider`" is not a fact. "3 in the whole file, 2 in markup" is.
3. A whole-file count is only valid for things the stylesheet cannot contain —
   emoji, hostnames, JS identifiers, colour literals inside `borderColor:`.

**When a number in an incoming spec disagrees with generated output, assume the
spec counted the stylesheet before assuming the generator changed.** That has
been the right guess three times out of three.

The rule is also written at the top of `scripts/postprocess_html.py`, where it
gets read.

## The comparison offset is a constant — here is why

`run.py`'s `_prev_match_dow` finds the previous-edition date at the same J-X
*and* the same weekday. It looks date-dependent. It is not: for any given pair
of events it collapses to one constant integer, which is what makes a
client-side comparison selector cheap and keeps every date decision in Python.

With `G = (event_date_first_current − event_date_first_previous).days`:

```
j_x        = (E_cur − d).days
candidate  = E_prev − j_x            =  d − G
wd_diff    = d.weekday() − candidate.weekday()
           = w − ((w − G) mod 7)     where w = d.weekday()
```

Let `r = G mod 7`. Then

```
w ≥ r  →  (w − r) mod 7 = w − r      →  wd_diff = r
w < r  →  (w − r) mod 7 = w − r + 7  →  wd_diff = r − 7
```

Now apply run.py's clamp (`>3 → −7`, `<−3 → +7`):

- `r ∈ {0,1,2,3}`: the first branch gives `r` (no clamp); the second gives
  `r − 7 ∈ [−7,−4]`, which clamps back to `r`. Both → **r**.
- `r ∈ {4,5,6}`: the first gives `r ∈ [4,6]`, which clamps to `r − 7`; the
  second gives `r − 7 ∈ [−3,−1]`, unclamped. Both → **r − 7**.

Either way `wd_diff` is the signed representative of `r` in `[−3, 3]` and does
not depend on `d`. Therefore

```
matched_date = d − (G − signed_mod7(G))

offset = G − signed_mod7(G)          constant per event pair
```

Checked numerically over 200,000 date/pair combinations across random anchor
gaps: **0 mismatches.** The offsets in use:

| event | compare_to | G | offset |
| --- | --- | --- | --- |
| epk_2026 | epk_2023 | 1100 | 1099 |
| bordeaux_2026 | bordeaux_2025 | 363 | 364 |
| geneve_2026 | geneve_2025 | 363 | 364 |
| rennes_2026 | rennes_2025 | 364 | 364 |
| paris_xxl_2026 | paris_xxl_2025 | 364 | 364 |
| bordeaux_oct_2026 | halloween_2025 | 350 | 350 |

It holds for `_prev_match_dsl` too — same clamp, a different constant anchor —
so even that dead mode would not break it. Three worries that do **not** apply:
differing day counts (only `event_date_first` enters), a mid-campaign date
change (`G` changes, the page regenerates, nothing stale is cached), and DST
(`date` arithmetic, no timezones).

## Deploy 3 (v6.7) — what shipped and what did not

Shipped in `680c134`: the stylesheet swap, suivi scroll containers and
`Précédent` separators, the vélocité header, the trailing-inset-divider
removal, and the platform cards.

**Both backend platform links were wrong before this.** `run.py` has no Shotgun
dashboard URL, so that card fell back to `shotgun_url` — the public festival
page — and on rennes and geneve the two Shotgun cards were byte-identical
destinations. DICE pointed at `dice.fm/partner/events/{id}` rather than the Mio
backoffice actually in use. Both are derivable, so both are fixed in
postprocess:

```
https://smartboard.shotgun.live/events/{shotgun_event_id}
https://mio.dice.fm/events/{base64("Event:" + dice_mio_id)}/overview
```

The relay id is the same encoding `fetch_csv.py` uses for GraphQL, generated
rather than tabulated, and asserted against four known values.

**Not shipped: §7, the footer restructure.** It is the only item touching a
runtime contract rather than generated markup — `scripts/stamp_footer.py`
patches that same footer in published HTML, out of band, four hours later, on a
quiet run. A break there fails silently and looks exactly like the pipeline
problem N4 existed to remove. It ships alone so it can be reverted alone. When
it does, see the pass-table note in `postprocess_html.py`: pass 2 emits the
string §7 consumes, the `FOOTER_OLD` end-check has to move after it, and
postprocess must assert the emitted footer is stamp-compatible at build time.

The frozen variant becomes a three-part edit — label, value, and icon, since a
sync arrow is wrong for an event that will never sync again.

## The DICE handover guard

Adding a `dice_mio_id` retires a committed manual export in favour of an API
call (`fetch_csv.py`). If the token cannot reach the event, the API answers
**HTTP 200 with an empty set** — valid token, wrong account, indistinguishable
from "no sales" — and the export is already gone. Genève is 2,912 tickets and
~186k EUR, more than its Shotgun side.

**M1 does not protect against this.** M1 publishes when the CSV changes, and
the CSV changing is the symptom.

So the retiring branch counts what it discards and holds the replacement to
that number. Not a non-zero check: partial account access returning three
tickets passes that while losing 2,909. Override is `--allow-dice-shrink`, for
a drop that is real rather than a reachability failure. The guard retires
itself — once the API is authoritative the event leaves `MANUAL_DICE_CSVS`.

**Do not add `geneve_2026.dice_mio_id` until the Collaborateur token can reach
event 588085.** The guard now turns that mistake into a failed run instead of a
silent loss, but the id still should not land early.

## Suivi comparison selector — decided, not built

Waiting on the revenue row layout (S1). Decisions already made:

- **No `run.py` change.** `scripts/build_dashboard.py` already imports `run`
  and replaces three module attributes before calling `run.main()`. Add a
  fourth that wraps `_generate_suivi_v3` to **observe** — capturing
  `cutoff_date`, `event_config`, `event_config_prev` from the arguments run.py
  itself passes. Nothing is re-derived and `run.py` stays byte-identical.

  > **It is no longer only an observe-wrapper.** Since the Suivi window fix it
  > also *clamps* `cutoff_date` on the way through (`_clamp_cutoff`). Everything
  > else still passes untouched, and `run.py` is still byte-identical, but if
  > you are reading "observe-wrapper" anywhere in this document, read it as
  > **observe-and-clamp-one-argument**. Adding a second mutation is a decision,
  > not a continuation — the file is one clamp away from being a fork of
  > run.py's behaviour maintained at a distance.
- **`data-cur` positionally, never by parsing.** The rendered dates carry no
  year (`Jeu 15 Déc`) and the daily table spans 232 rows across a year
  boundary, so parsing is ambiguous, not merely fragile. The past rows are a
  strictly consecutive one-per-day sequence ending at `cutoff_date` — verified,
  0 non-consecutive steps over 232 / 179 / 93 rows — so counting backwards from
  the last row is exact.
- **Payload: 62 KB raw, ~11 KB gzipped** for all twelve candidates against a
  ~270 KB page. No shortlist.
- **Row range is not extended** (S2). Where a candidate's series does not cover
  a row's matched date, render an em dash — a zero asserts "no sales that day",
  which is false. Caption the coverage when a candidate is short.
- **Cumulative is prefix-summed from the full series, never from visible rows**
  (S3). Follows from the above: on a truncated candidate the first visible
  row's true cumulative is not zero. Summing what is on screen is the obvious
  wrong implementation.
- Add a CI check comparing the closed-form offset against `run._prev_match_dow`
  exhaustively. That retires the divergence risk rather than managing it.

## Trap: a correct match count does not mean a correct match

`stamp_footer.STAMP_ITEM_RE` once matched **exactly twice** — the right number,
one footer per page — while deleting four elements.

The icon body was `<svg class="pgf-ico".*?</svg>` under `re.DOTALL`. A lazy dot
under DOTALL will cross anything. A match starting at the *Dernier billet* item
expanded past that item's own `</svg>`, its label, its value and the separator,
and landed on the next item's `Données API` label — a legal match, twice, and
on substitution it replaced both items with one. Six `.pgf-item` became two.

**Every count-based assertion in this repo would have passed it.** The build-time
check asserting "exactly 2 stampable items" passed. The one that caught it
compared the item count before and after a dry-run substitution.

So the general rule:

> **Matching the right number of times is not the same as matching only your
> own element.** Assert that the surrounding structure is *unchanged*, not just
> that your own match count is right.

In practice: dry-run the substitution and count the elements you did **not**
intend to touch. `postprocess_html.py` and `scripts/stamp_footer.py` both do
this and both refuse to write when it moves.

The fix in the regex is `(?:(?!</svg>).)*` instead of `.*?` — greedy, but
unable to cross a `</svg>`, so a match is confined to one item.

**The guard was proven, not just written.** The lazy dot was deliberately
re-introduced afterwards to confirm the check blocks it: exit 1, file
untouched, `Dernier billet` intact. A guard nobody has seen fire is a guess.

## The dependency graph is wider than postprocess_html.py

The pass table covers passes. It does not cover everything that consumes
generated markup, and Deploy 3 §7 broke two things that are not passes:

| consumer | what it matched | how §7 broke it |
| --- | --- | --- |
| `verify/assert_redesign.sh` | `🎟 Dernier billet vendu` | emoji deleted → the check errored on a correct file |
| `verify/assert_redesign.sh` | `Festiflow Dashboard v6.7` | version moved into `.pgf-ver` → literal reads 0 |
| `scripts/stamp_footer.py` | the whole footer line | would have silently stopped matching |

The first two fail loudly at build time. The third fails **four hours later**,
on a quiet run, as a stamp that stopped moving.

So: **anything that greps generated output is in the dependency graph**, pass
or not. Before restructuring markup, grep `verify/` and `scripts/` for the
strings you are about to destroy. The pass table is necessary, not sufficient.

Recorded in the scope note at the top of `scripts/postprocess_html.py`.

## Trap #4: an aggregate can be correct while a branch is dead

Traps 1–3 were guards that matched the wrong thing. This one is different: the
**measurement** aggregated the failure away.

The Suivi row tagging tags two grains. On its first run it tagged 264 daily
rows correctly and **0 weekly rows** — an entire grain silently doing nothing.
A combined "264 rows tagged" would have read as perfect health, and the
per-grain split is the only reason it surfaced at all.

> **Report counts per branch, never in aggregate.** An aggregate can be correct
> while a branch is dead.

The second-order cause is worth its own line, because any pass can have it:
the section offsets were computed **before** an earlier rewrite shifted every
index after `#suivi-jour`. Position-based slicing must be recomputed after any
edit that precedes it, or taken last. Recorded in the pass table.

## The four traps share one rule

| # | what looked right | what was actually happening |
| --- | --- | --- |
| 1 | `'sw-wrap' in html` | matched the stylesheet, so every dashboard silently got no nav |
| 2 | `STAMP_ITEM_RE` matched exactly twice | consumed four items it did not own |
| 3 | offset transcription markers all present | present inside `_prev_match_dsl`, so a change to `_prev_match_dow` passed |
| 4 | "264 rows tagged" | one of two grains tagged nothing |

> **A check can pass for the wrong reason. Verify that your guard FIRES, not
> only that it is present.**

And the corollary: **a marker that is not unique is not a guard.** Scope every
marker to the smallest region that can contain it, and write the negative test
that proves it fires.

`verify/check_offset.py` carries four such negative tests — a change inside
`_prev_match_dow` must fail it, a change to `_prev_match_dsl` must not.
**Do not "simplify" them away.** They are the only thing standing between a
stale transcription and a silently wrong comparison.

## The positional data-cur derivation, cross-validated by accident

The strongest evidence in this project, and nobody designed it.

`data-cur` is derived **positionally** — counted backwards from the observed
`cutoff_date` — because the rendered dates carry no year. The design mock
arrived at its own `data-cur` values by **parsing those French date strings**.
Two independent methods, on different inputs, written by different people.

Both produce `data-cur="2025-12-18"` for epk's first daily row.

A second accidental confirmation, same class: selecting `rennes_2025` on epk
leaves 107 of 264 daily rows as em dashes — and `rennes_2025` has exactly 157
days of data. 264 − 107 = 157. Every day of the candidate's series lands on
exactly one row, none lost, none doubled.

Neither check was asked for. Both are worth more than the ones that were.

## Trap #5: verify the OUTPUT, not only the round trip

The selector shipped with **every Diff on the page wrong by six orders of
magnitude**, and three green checks did not notice.

R9 put the revenue span inside `.dtl-sales`:

```html
<div class="dtl-sales">135<span class="dtl-rev">€7 402</span></div>
```

The renderer read that element's `textContent` and stripped non-digits, so
`135` and `€7 402` became the single number **1357402**. Subtract the correctly
computed 203 and the page showed `+1,357,199` and `+668,570.9%`.

Why the existing checks all passed:

| check | why it was blind |
| --- | --- |
| "restore is exact" | restore replays *saved HTML*, so it never enters the renderer |
| "em dash count" | uncovered rows were genuinely dashed — that path was fine |
| "no page errors" | `1357402 - 203` is perfectly valid arithmetic |

Traps 1–4 were checks that passed for the wrong reason. This one is different:

> **The check was never in the path.** Round-trip and edge-case assertions can
> all pass while the primary output is nonsense. Assert what a reader would
> actually see.

Two rules came out of it, both now enforced:

1. **Never derive a number from the `textContent` of an element that can
   contain a second number.** Counts travel as `data-n` on `.dtl-sales`,
   written server-side on every element and re-written by the renderer on every
   row it touches — a row the renderer writes without `data-n` re-breaks on the
   next switch.
2. **`querySelector` on a class that appears more than once is a bug waiting.**
   The column header was updated via `querySelector('.dtl-col-label')`, and
   there are three such blocks — past, future and weekly — each with its own
   suffix (`(même jour)`, `(référence)`, none). Two of them kept contradicting
   the selector. Now all are updated, suffixes preserved.

`verify/check_selector.js` covers both, and it is proven to fire: reintroducing
the `textContent` parse fails it (`diff 1914107913 != 1914 - 55`), and
reintroducing the single-label update fails it (`column header "2023
(référence)" does not name "Bordeaux 2025"`). It needs playwright, so it is not
wired into `assert_redesign.sh` — run it by hand after any renderer change.

**Do not remove its negative tests.** Same standing as `check_offset.py`'s.

## Trap #6: injecting code through `re.sub` — the escape you get away with

`postprocess_html.py` injects a client-side `<script>` by passing it to
`re.subn` as the **replacement**, where a backslash is an escape sequence, not
a literal. A single `\s` in an injected JS regex aborted the build:

```
re.error: bad escape \s at position 90129
```

That one was free — it failed loudly, in seconds, because `\s` is not a valid
`re` replacement escape. **The dangerous case is the one that is valid.**
`\1`, `\g<0>`, `\n`, `\\` are all legal in a replacement string, so a JS regex
containing any of them would be silently rewritten on its way into the page.
The build passes, the file looks right, and a client-side regex quietly means
something else.

That is trap #5 in a new place: nothing in the path would have failed.

**Rule: never pass injected code as a `re.sub` replacement string.** Use a
lambda — `re.subn(pattern, lambda _m: payload, html)` — which does no escape
processing at all. Both injection sites in `suivi_selector.py` do this, and any
new one must.

The same hazard applies to `str.format` and f-strings over injected JS (`{}` in
an object literal), and to `%` formatting. Injected code should be concatenated
or passed through a callable, never interpolated by a mechanism that reads its
own metacharacters.

## The stylesheet swap destroys templated values inside `<style>`

`apply_redesign` replaces the template's entire `<style>` block with the
vendored sheet. The template renders **three per-event values inside that
block**, and all three were thrown away from Deploy 1 onward:

| placeholder | status |
| --- | --- |
| `{{LOGIN_BG_IMAGE}}` | **live** — now carried across the swap |
| `{{DAY_TAB_ACTIVE_CSS}}` | dead — Deploy 2 removed `.chart-tabs` from the markup |
| `{{PROJ_GRID_COLS}}` | dead — Deploy 2 removed `.proj-grid` |

The live one is how `paris_xxl` lost its configured background. Config says
`paris_login.jpg`; `run.py` resolves `paris_login.jpg` correctly at every point;
the published page requested `upload.JPG`, because that is what the mock was
baked with. Proven from history — `git show 12182c4:parisxxl.html` has
`url('paris_login.jpg')`, and every build after Deploy 1 has `url('upload.JPG')`.

It failed in total silence twice over: a missing background falls back to the
solid colour with nothing in the console, **and** the file it fell back to does
not exist either.

`verify/check_login_bg.py` now compares each published page against
`event_config.csv` and is wired into `assert_redesign.sh`.

**Before adding a fourth templated value to the template's `<style>`, add it to
the carry-across list in `apply_redesign`.** A wholesale block replacement
destroys everything in it, and nothing about that failure is visible.

## Duplicate CSS selectors — the audit

`verify/audit_css_overrides.py` lists every selector declared more than once at
top level and reports which properties the **earlier** declaration leaves in
force. Three real bugs came from this pattern (`.hero-unit`, `.det-link-icon`,
`.scenario-toggle`), each visible only by looking at the page.

Two things make the output usable rather than noise:

- **Shorthand awareness.** A later `border-bottom: 2px solid #fff` does reset an
  earlier `border-bottom-color`, so that is not a survivor. Without this the
  audit cried wolf on `.dt.on`, and a noisy audit gets ignored — which is the
  only way this pattern keeps shipping.
- **Additive vs redesign.** Findings are ranked by how much of the earlier rule
  the later one replaces. Near 0% means the later rule is layering a property
  on, which is fine and is most of the list. High means it is a redesign, and
  whatever it forgot to reset is the latent surprise.

Current state: 398 selectors, 18 declared twice, **3 classed as redesigns**:

- `.scenario-toggle` (83%) — `margin-bottom: 12px` still survives from the
  pill-track rule even after the T3 fix. Harmless spacing, but it is a survivor.
- `.scenario-btn` (71%) — `font-weight: 600` survives onto every button, which
  makes `.scenario-btn.active { font-weight: 600 }` a **no-op**. Measured, not
  inferred: idle and active both compute to 600. The active state cannot
  distinguish itself by weight; it relies entirely on background and border.
- `.pill` (89%) — created by Deploy 1's rename. `yoy-badge` became `pill`, which
  is also the nav module dropdown's badge class, so two unrelated components now
  share one name. The nav rule adds `margin-left: auto`, which lands on the YoY
  badge too. Benign where it sits today, but the collision is real and a rename
  is a design decision, not a build one.

## Trap #7: a wholesale swap of a TEMPLATED block discards the templating

`dashboard_template.html`'s `<style>` block is not static. It renders three
per-event placeholders, and `apply_redesign` replaces the whole block:

| placeholder | state |
| --- | --- |
| `{{LOGIN_BG_IMAGE}}` | live — re-injected after the swap |
| `{{DAY_TAB_ACTIVE_CSS}}` | retired (Deploy 2 removed `.chart-tabs`) |
| `{{PROJ_GRID_COLS}}` | retired (Deploy 2 removed `.proj-grid`) |

The swap replaced a placeholder with a **constant**, and the page still
rendered perfectly — which is why nothing downstream could notice. The
stylesheet is extracted from a generated mock, so it contains
`url('upload.JPG')` baked in from whichever event that mock was built for.

**A future stylesheet is not clean.** It will keep containing that constant.
The swap must re-inject every time; never treat a new sheet as fixed.

`STYLE_PLACEHOLDERS` in `postprocess_html.py` is the registry, and
`_assert_style_placeholders` fails the build both ways: a placeholder added
upstream that is not declared here, and one declared here that has vanished
upstream. Negative-tested in both directions.

Second layer, found by fixing the first: `run.py` defaults the value with
`.get(key, default)`, which does **not** fire when the key exists and is empty.
Clearing the config value — the documented way to say "use the standard image"
— rendered `url('')`. The fallback now lives in `postprocess_html.py`.

## A rename must check what the TARGET name already means

Deploy 1 renamed `yoy-badge` → `pill`. `.pill` was already the BudgetFlow nav
dropdown's badge, so two unrelated components ended up sharing a class and the
nav rule's `margin-left: auto` landed on the YoY badge.

The rename was verified only in one direction — that the source name was gone.
Nobody checked what the destination name already denoted.

> **Before renaming a class, grep the target name.** "The old name is absent" is
> half the check.

Now `yoy-pill`, applied through `CSS_FIXUPS` in `postprocess_html.py` rather
than by editing the vendored sheet, so it survives a future sheet swap.
`verify/audit_css_overrides.py` confirms the collision is gone — it audits a
**built dashboard**, not the `.css` file, because the fixups are applied on the
way in.

## Suivi selector: two anchors, chosen by the candidate

A finished candidate anchors on its **event date** — J-X against J-X, the
reference comparison's original meaning.

A live candidate cannot: its event has not happened, so an event anchor maps
recent rows into the candidate's *future*. epk (5 Sep) against bordeaux_oct
(16 Oct) gives offset −42, so today's row asks for 18 September. Live
candidates therefore anchor on **launch** — campaign day N against campaign day
N — with the same weekday snap, so it stays one constant per candidate and the
payload model is unchanged. `first_sale` is derived, not configured:
`min(order_date)` over the candidate's merged CSV.

**What this does not do.** It does not make today's row comparable, and it does
not materially change how many rows are covered — coverage is bounded by the
candidate's series length, not by the anchor. Measured on epk, both anchors
cover essentially the same number of rows.

**What it does do** is move *where* the covered window sits:

| candidate | event anchor window | launch anchor window |
| --- | --- | --- |
| bordeaux_oct_2026 | 2026-05-21 … 06-26 | **2026-04-02** … 05-08 |
| paris_xxl (if live) | 2026-05-26 … **09-06** | 2026-03-31 … 07-27 |
| geneve_2026 | 2026-03-25 … 06-26 | 2026-04-01 … 07-03 |

epk's own campaign starts 2026-04-02. Launch anchoring lands the window on
epk's day one; the event anchor lands it at an arbitrary calendar point, and in
the paris_xxl case ran it into epk's own *future* rows.

The caption names the rule in use, because two candidates in one dropdown can
now align differently.

**This partially answers the parked launch-vs-event question.** The
live-candidate case is solved by candidate-dependent anchoring, with no UI
control. The general user-facing toggle remains open — and must still not be
built on `comparison_mode: days_since_launch`, which is dead code that anchors
on the event **end** despite its name.

## Trap #8: `.get(key, default)` does not fire on an empty value

A CSV always provides the key. `row.get('login_bg_image', 'upload.JPG')`
returns `''` — not the default — when the column exists and is blank. Clearing
the value, which is the documented way to say "use the standard image",
rendered `url('')`.

The right pattern is four lines above the wrong one, in the same dict literal:

```python
'comparison_mode': row.get('comparison_mode', '').strip() or 'j_minus',   # correct
'login_bg_image':  row.get('login_bg_image', 'upload.JPG'),               # wrong
```

**Audited across `run.py`, `fetch_csv.py` and every script.** 21 config reads
carry a non-empty default; measured against the row `run.py` actually reads
(the first per event, not the blank continuation rows):

| key | blank on active events | verdict |
| --- | --- | --- |
| `login_bg_image` | 1 (paris_xxl) | **the one real instance** — fixed in postprocess |
| `comparison_mode` | 2 | safe — normalised with `.strip() or` at load |
| `currency`, `brand`, `status` | 0 | never blank on an event-level row |

So: one bug, already fixed, and no others. But the shape is a one-liner that
produces plausible-looking output, which is the family that keeps costing us.

> **Any config field where blank means "use the default" needs an explicit
> truthiness check, not `dict.get`.**

## The vendored stylesheet is not what ships

`CSS_FIXUPS` in `postprocess_html.py` runs on the sheet on its way in — the
`.pill` → `.yoy-pill` rename and the `.scenario-btn` weight live there, not in
the `.css` file, so they survive a future sheet swap.

Consequence: **anything that reads `style/dashboard_v6_8.css` is reading the
wrong artefact.** `verify/audit_css_overrides.py` now defaults to a built
dashboard and extracts its `<style>`; pointing it at the `.css` reports a
`.pill` collision that no longer ships.

Same class as trap #7 — checking the input to a transformation instead of its
output.

## Standing pattern for specs: publish the numbers, invite the correction

Three for three now. Each of these was caught before it shipped because the
instruction was "reproduce this before implementing, and if your numbers differ
from ours, yours are probably right":

| spec figure | reality |
| --- | --- |
| `.ac-t` baseline of 8 | 4 in markup; the other four are stylesheet selectors |
| `rgba(96,165,250,.8)` N×2 occurrences | zero — the generator emits amber |
| launch-anchor coverage table | windows move, counts barely do |

The pattern is worth keeping in every spec that quotes a measurement: state the
number, state how it was measured, and say explicitly that a disagreement means
the spec is probably wrong. A number quoted without its method is an assertion;
quoted with one, it is a test.

## Open items

Carried forward, not fixed. Each needs a decision or an input we do not have.

| # | item | blocked on |
| --- | --- | --- |
| O1 | **Half closed 2026-08-08.** DICE is proved against a payout statement, to one ticket in 9,327. The spec/code conflict is now Shotgun-only: is 13,03% buyer-facing? See `docs/O1_FEE_DECISION.md` | **a SHOTGUN payout statement** — Leo has no access, so Episode or Sonora |
| O10 | **Days are matched between editions by weekday name, not position** — three dashboards affected. Diagnosed, ruling given, mechanism pending. See DD4 below | a ruling on route 1 vs 2 |
| O11 | **"prix affiché au client" is ambiguous** — advertised (45,57) or charged (49,00)? Card sums the first. `docs/O1_FEE_DECISION.md` §CC2 | Leo looking at both checkout funnels |
| O9 | **The revenue disclaimer is wrong for DICE** and possibly right for Shotgun — a copy decision, raised not fixed. `docs/O1_FEE_DECISION.md` §CC2 | O1, then a copy call |
| O2 | ~~a 2h DICE/Shotgun skew~~ **— measured 2026-08-08, and there is no cross-platform skew.** Both streams share a clock; that clock is UTC | a decision on displaying Paris local |
| O7 | Shotgun `GET /events` exists (400, not 404) and nobody has called it | a decision — it may carry the capacity/phase metadata `/tickets` lacks |
| O8 | Whether DICE `viewer.orders` already nets out returns (28 on `rennes_2026`) | a reconciliation |
| O3 | `dice_url` form is wrong on the platform cards | Leo |
| O4 | `geneve_2026 dice_mio_id` deliberately not added — data-loss risk | Leo (A6) |
| O5 | General user-facing launch-vs-event anchor toggle | not specced |
| O6 | Archive data inventory — what exists for finished editions | not started |

### O1 — the fee assumption and the 2% overshoot

**Read this first: the code and this document disagree about the formula, and
have since the start.** The column spec at the top of this file says Shotgun
`gross_price` is `(deal_price + deal_user_service_fee) / 100`, and its worked
example says the sample ticket comes out at **97.87**. `fetch_csv.py`
(`process_shotgun_ticket`) adds **both** fees:

```python
gross_price = round(
    cents_to_units(raw.get('deal_price'))
    + cents_to_units(raw.get('deal_service_fee'))        # <- not in the spec
    + cents_to_units(raw.get('deal_user_service_fee')),
    6,
)
```

On that same sample ticket the code produces **107.37**, not 97.87. Measured
over every Shotgun row we hold, the ratio is uniform and unambiguous
**[measured]**:

| event | paid Shotgun rows | gross / price |
| --- | ---: | ---: |
| bordeaux_2026 | 17,409 | 1.1302 |
| bordeaux_oct_2026 | 7,732 | 1.1294 |
| epk_2026 | 7,696 | 1.1303 |
| geneve_2026 | 1,174 | 1.1302 |
| paris_xxl_2026 | 21,405 | 1.1303 |
| rennes_2026 | 1,369 | 1.1302 |

13.03% = 10.0% (`deal_service_fee`) + 3.0% (`deal_user_service_fee`). The spec's
formula would give 1.030. So this is not an ambiguity about which fee the buyer
bears — **it is two documents making opposite assumptions, and nobody noticing
for the whole life of the project.** Which one is right is still Leo's question;
that they conflict is arithmetic.

**This also corrects what was written here on 2026-08-08.** The note below
argued that DICE's 5.33% buyer-borne fee against Shotgun's 3.0% meant a missing
`deal_service_fee` would make our gross too *low*, so the overshoot pointed away
from that hypothesis. That reasoning read the spec instead of the code. We are
already adding the larger fee. If we ship 13.03% and land only ~2% high, the
implied truth is nearer **11%** — which says the buyer bears most, but not all,
of `deal_service_fee`, and points back at exactly the hypothesis the earlier
note dismissed. VAT (`deal_vat_rate` 0.055) is the obvious candidate for the
remainder and has not been tested.

**So the first action on O1 is not a measurement of the sign — it is deciding
which of the two formulas is correct.** The sign argument was built on a premise
that does not hold.

The original framing follows, for the record.

`gross_price` for Shotgun is documented as `(deal_price + deal_user_service_fee)
/ 100`. That is a *choice*: the payload also carries `deal_service_fee`, an
order of magnitude larger (9500 face → `deal_service_fee` 950, i.e. 10.0% of
face; `deal_user_service_fee` 287, 3.0%), and nothing in the payload says which
of the two the buyer actually pays. If some or all of `deal_service_fee` is
buyer-borne, every Shotgun `gross_price` we have written is too low.

Separately, our Shotgun gross has been running **~2% over** the reference for as
long as anyone has looked. Two unexplained things about the same two fields is
one unexplained thing, most likely: the split between `deal_service_fee` and
`deal_user_service_fee` is not what the code assumes, and the residual shows up
as a percentage drift rather than an obvious break.

Worth pursuing on its own, independently of the Campagne page. It is not
answerable from the API — see P6 in `docs/PLATFORM_FIELD_INVENTORY.md`. It needs
either Shotgun's own documentation of the two fields or one reconciliation
against a real payout statement, and one such statement settles both halves at
once.

**Narrowed on 2026-08-08 by the field probe, in two ways.** First, DICE's
decomposition is now proven exact — `fullPrice + Σ fees.dice = total`, to the
cent, with every `promoter` share zero — so the DICE half of `gross_price` is
right and the 2% is Shotgun-side. Second, and against the hypothesis above:
DICE's buyer-borne fee runs at 5.33% of face where Shotgun's
`deal_user_service_fee` is 3.0%. If the buyer really bore the larger
`deal_service_fee` (10.0%), our Shotgun gross would be too *low*, not too high.
**So the sign of the 2% discriminates between the two explanations, and
measuring it is step one** — before anyone reasons further about which fee is
whose.

**Do not "fix" this by changing the formula on a guess.** `gross_price` feeds
every revenue figure and every comparison on the dashboard; a wrong correction
is worse than a known 2%.

## Trap #9: a spec and its code can both be self-consistent and disagree

`HANDOFF.md`'s column spec says Shotgun `gross_price` is
`(deal_price + deal_user_service_fee) / 100`, and its worked example says the
sample ticket produces **97.87**. `fetch_csv.process_shotgun_ticket` adds
`deal_service_fee` as well and produces **107.37** for that same input.

Both documents were internally consistent. Neither ever failed. Every test
checked the code against itself, and every reader of the spec checked the spec
against itself. The disagreement survived the entire life of the project and
surfaced only because an unrelated question — why `product_name` is never blank
— was traced through the same function.

**The rule:**

> A specification and its implementation can BOTH be self-consistent and
> disagree with each other. Nothing fails. Assert the spec against the code, not
> just the code against itself.

This is a different failure from traps #1–#8. Those were all one artefact being
checked in the wrong place — the input instead of the output, the round trip
instead of the result, the vendored sheet instead of the shipped one. This one
is two artefacts, each correctly checked, that were never checked *against each
other*. No amount of care inside either would have found it.

**The guard is `verify/check_spec_example.py`.** It parses the worked example
out of `HANDOFF.md` — it does not copy it, because a copy is a third statement
of the same fact and free to drift from both — runs it through the real
function, and compares. While O1 is open it pins the one known delta and fails
on anything else. Four drift modes were confirmed to exit non-zero: the code
moving to a third value, someone editing the spec to match the code, the code
being corrected while the pin is left stale, and the example being removed from
the doc altogether.

Wire the same shape anywhere a document states a number the code also computes.
A worked example in a spec is a test that nobody has run yet.

## The two clocks in one footer

`run.py:3986` converts the generation time with `ZoneInfo('Europe/Paris')`.
`run.py:2048` renders the last-ticket time straight off `order_datetime`, which
is UTC, with no conversion. Both sit in the same footer, three items apart.

That is why it survived. A footer with two timestamps where one is right does
not look broken — it looks like a footer. And the error is 1h in winter and 2h
in summer, so a reader checking it against a remembered sale time disagrees by a
different amount depending on the season, which reads as their own
misremembering rather than a bug.

The lesson is not about timezones. **A partial fix is more durable camouflage
than no fix.** When the same conversion is needed in several places and applied
in some of them, the ones that got it make the ones that did not look
deliberate. When you find a conversion, normalisation or guard applied
somewhere, the next question is where else it should be and is not.

## Day buckets are UTC, and the size of that is closed-form

`order_date` is `date()` of the UTC timestamp on both platforms, and `run.py`
buckets everything on that column, so daily rows are UTC days. Measured over
92,527 rows, **3,219 (3.48%)** sit on the wrong Paris day.

The band that moves is exactly:

    rows in UTC hours 22 and 23 during CEST (+2)
  + rows in UTC hour 23 during CET (+1)

That prediction reproduces the measurement to two decimal places on all six
events — 3.35, 3.16, 3.56, 8.72, 3.10, 2.77 — so the effect is fully
characterised, not estimated.

| event | CEST share | moved |
| --- | ---: | ---: |
| geneve_2026 | 100% | **8.72%** |
| epk_2026 | 100% | 3.56% |
| bordeaux_2026 | 65% | 3.35% |
| bordeaux_oct_2026 | 100% | 3.16% |
| paris_xxl_2026 | 0% | 3.10% |
| rennes_2026 | 100% | 2.77% |

**Why geneve is the outlier — and it is not the DICE share.** Two factors
multiply, and the platform-mix guess only explains part of one:

1. **Season.** A summer event loses two UTC hours, a winter event one.
   `paris_xxl_2026` sells entirely in CET, so despite having 8.5% of its rows in
   UTC hours 22–23 it only moves 3.10% — hour 22 is still 23:00 Paris in winter.
   `geneve_2026` sells entirely in CEST, so both hours count.
2. **Geneve's DICE audience genuinely buys late**, and this is specific to
   geneve rather than to DICE:

   | | hour 22 | hour 23 | moved |
   | --- | ---: | ---: | ---: |
   | geneve Shotgun | 2.9% | 2.1% | 4.99% |
   | geneve DICE | 6.8% | 3.5% | **10.23%** |
   | rennes DICE | — | — | 2.18% |

   `rennes_2026` is 62% DICE and its DICE rows move at 2.18%. So "DICE-heavy
   events buy later" is not a general property — geneve's DICE cohort is the
   outlier, not the platform. Expect this on late-selling summer events, not on
   DICE-heavy ones as such.

**Held, deliberately.** Converting is a pure relabel — no data lost, fully
reversible, and the band is deterministic — but it rewrites published daily
numbers and moves rows between rows of the Suivi table, including across the
comparison. That is a decision, not a fix.

## Trigger: one sale on the far side of a gap (the Suivi window bug)

**Framed by the trigger, not the symptom, deliberately.** This was first
reported as a finished-event bug, and a fix built on that frame would have
branched on whether the event had passed — and missed the actual case. A
**live** event with a single backdated correction, a late-entered door sale,
or a resale breaks in exactly the same way, and nobody would be looking. The
wrong frame is what makes a bug recur somewhere else.


`cutoff_velocity` is `max(order_date) - 1` over all tickets
(`load_ticket_data`), and `_generate_suivi_v3` shows the last `VISIBLE_DAYS = 7`
rows ending there. For a live event that is exactly right: the newest sales are
the interesting ones.

It breaks when one sale lands long after the event. `paris_xxl_2026` had **7
paid tickets on 2026-03-30** — sixteen days after a 13-14 March event, fifteen
days after the previous sale. That single day moved the cutoff to 29 March, so
the seven visible rows were 23-29 March, every one zero on both sides, with 112
real selling days behind "Voir les 112 jours précédents". The page read as
empty.

**Three things about this that are easy to get wrong:**

1. **The trigger is a sale on the far side of a gap — nothing else.**
   `bordeaux_2026` is finished and was never affected, because its last sale
   falls on its own event days. Being finished is neither necessary nor
   sufficient. What matters is one sale separated from the rest by more than
   `VISIBLE_DAYS`, and that can happen to a live event tomorrow.
2. **The rows are not "generated past the last sale".** They stop at a real
   sale. The dead space is the *gap*, and one ticket beyond it is enough to
   stretch the window across it.
3. **"Anchor on the last day with non-zero sales" does not fix it.** 30 March
   *is* a day with sales. That rule gives 24-30 March: six empty rows and a
   seven-ticket day. Still an empty table.

**The fix** is `build_dashboard._clamp_cutoff`: `min(cutoff, event_date_last +
1)`. The `+1` matches run.py's own convention for the future rows ("+1 for
post-midnight sales") and keeps the 41 tickets sold on 15 March. For a live
event the event is in the future, so `min` is a no-op — one rule, no
live/finished branch. Measured across all six events, only `paris_xxl_2026`
moves: its window becomes 9-15 March with 4,816 sales, and its hidden-days
button drops 112 → 98. The other five are unchanged.

It lives in the build wrapper because `run.py` is do-not-modify and the bug is
in run.py's choice of anchor. That widens the wrapper's job from *observe* to
*observe and clamp one argument*, which is a real change in what that file is
for and is documented at the top of it.

**The stragglers are not lost.** run.py's "Aujourd'hui" row is driven by
`cutoff_cumulative`, untouched here, so the 7 tickets still render — the row now
follows 15 March directly instead of following fourteen blank ones.

### The check written for it passed on it — see trap #10

### AA3/AA4, checked and not bugs

- The weekly button reads **"Voir les 8 semaines"**, not 112. The daily one
  reads 112. Each grain counts its own rows (`hidden_weekly` vs `hidden_past`).
  Each label appears twice per file because each dashboard carries two pages,
  main and details. `check_suivi_window.py` now asserts the two counts do not
  coincide.
- parisxxl having **no "À venir" separator is correct**, and is guarded by
  `if future_rows:` in run.py. `future_start = cutoff_cumulative + 1` (31 March)
  is past `future_end = event_date_last + 1` (15 March), so the count goes
  negative and nothing renders. `bordeaux_2026`, also finished, does get a
  one-row future block because its arithmetic lands differently. Not a side
  effect of the range logic — the guard is doing its job.
- The `Voir les 0 jour restant` buttons are real in the markup but carry
  `style="display:none"`, set by `SUIVI_BTN_HIDE` when the count is 0. Not
  visible to a reader.

## Trap #10: a check written for a known bug, which passed on that bug

`verify/check_suivi_window.py` was written for one purpose: catch the Suivi
window showing seven empty rows on `paris_xxl_2026`. Its first version summed
the last seven rows of the daily table. It reported the broken page as **fine**.

The reason is that run.py appends its "Aujourd'hui" row *after* the
`VISIBLE_DAYS` slice, and drives it from `cutoff_cumulative`. On paris_xxl that
row carried the very 7 straggler tickets that caused the bug. Six zeros plus a
seven is seven, and seven is not zero, so the assertion held.

**This one does not have the usual excuse.** Traps #1–#8 are all explicable as
not knowing enough — the wrong artefact was checked, or a branch was dead, or a
default did not fire, and in each case the author did not yet understand the
system well enough to see it. This check was written *minutes after* reading the
row-generation code that causes the bug, by someone who could state the cause in
one sentence and did. Understanding the bug completely is not protection against
writing a check that cannot see it, because the two are different skills: one is
about the system, the other is about the check's own blind spots.

**The rule, and it is a step rather than a lesson:**

> Run a new check against the KNOWN-BROKEN artefact before trusting it. If it
> does not fail there, it does not work.

It is cheap in a way the earlier traps' remedies were not. There is no need to
reason about what the check might miss — the broken artefact already exists at
the moment the check is written, because that is why the check is being written.
Running it there costs one command and converts "I believe this check works"
into "this check has caught the thing once".

Where the broken artefact no longer exists — because the fix shipped first —
reconstruct it: revert the fix, run the check, restore. That is what
`check_footer_tz.py` and `check_spec_example.py` did, and it is now a required
step in `verify/CHECKLIST.md` rather than a habit.

## DD4: days are matched between editions by WEEKDAY NAME — confirmed, and wider

Diagnosed against `run.py` and `event_config.csv`, 2026-08-08. **Not yet fixed**
— the ruling is "match by position, day 1 to day 1", but the mechanism is a real
decision because `run.py` is do-not-modify. See "how to fix it" below.

### The mechanism, confirmed

```python
day_name_map = {}
if comparison_mode == 'days_since_launch' and event_config_prev:
    ...                                    # position mapping, day 1 -> day 1
mapped_dn = day_name_map.get(dn, dn)       # j_minus: the SAME French weekday
```

Position mapping only happens under `days_since_launch`. Measured over
`event_config.csv`: `comparison_mode` is **`''` on 49 rows and `j_minus` on 4.
Never `days_since_launch`.** So the map is always empty and every event matches
on the French weekday string.

**Correction to the reported cause.** The branch is not dead because
`launch_date` is missing. `launch_date` **is** populated — `run.py:3948-3949`
derives it from the first sale in the data and assigns it to both configs before
the dashboard is generated. The `on_sale_date` column being empty is real but
irrelevant. **The only thing keeping the branch dead is `comparison_mode`.**

That distinction decides the fix. Setting `comparison_mode =
'days_since_launch'` would enable the position mapping *and* switch
`_prev_match_dsl` for the Suivi table, `filter_tickets_to_same_point_dsl` for
the whole comparison, and the `prev_cutoff` computation at `run.py:1869`. That
is a far larger behaviour change than the ruling asks for. **Do not fix it by
flipping the mode.**

### It is three sites, not one, with seven consumers

`day_name_map` has exactly one consumer, `_get_prev_day_presence` (Par Jour).
But the same guard, the same shape and the same bug appear twice more under a
different name:

| site | name | consumers |
| --- | --- | --- |
| `run.py:1921` | `day_name_map` | Par Jour presence |
| `run.py:2881` | `prev_presence_key_map` | vélocité (2969, 3050), projections (3028) |
| `run.py:3514` | `prev_presence_key_map` (redefined) | vélocité (3551), projections (3649, 3676), **day capacity (3704)** |

All three test `comparison_mode == 'days_since_launch'` and all three fall back
to the identity mapping. **A fix must hit all three.** Par Jour matched by
position while Vélocité is still matched by name would be worse than both being
wrong the same way — the page would disagree with itself and nothing would say
so.

### Which days actually lose their comparison

| event | current days | reference days | unmatched |
| --- | --- | --- | --- |
| `epk_2026` | samedi, dimanche | vendredi, samedi (epk_2023) | **dimanche** |
| `bordeaux_2026` | jeudi, vendredi, samedi | vendredi, samedi | **jeudi** |
| `geneve_2026` | vendredi, samedi | **samedi** (one day) | **vendredi** |
| `paris_xxl_2026`, `rennes_2026`, `bordeaux_oct_2026` | ven, sam | ven, sam | — |

**Correction: `geneve_2026` loses one day, not both.** `geneve_2025` is a
single-day event and that day is named `Samedi`, so geneve's samedi matches by
name and only vendredi falls through. Three of six dashboards are affected, but
the geneve damage is half what was reported.

EPK is the clearest case of the second failure mode, which is worse than a zero:
EPK 2023 ran Friday-Saturday, EPK 2026 runs Saturday-Sunday. Sunday has no
reference at all, **and Saturday silently compares our opening day against their
closing day** — a number that looks plausible and is meaningless.

### How to fix it, given run.py is do-not-modify

The three blocks are inline inside large functions, so they cannot be
monkeypatched the way `_generate_suivi_v3` was. Two routes:

1. **Re-key the reference data before run.py reads it.** All three sites end up
   looking up a *current* day name in a *previous-year* structure —
   `metrics_prev['day_presence'][dn]` and the per-ticket `presence_<dn>` keys.
   Renaming the previous edition's day keys into the current edition's names, in
   positional order, turns every name lookup into a position lookup at all three
   sites at once, with no run.py change and no `comparison_mode` change.
   Positional, single point of control, and it cannot desynchronise the three
   sites because there is only one rename.
2. **Ask Leo to lift do-not-modify for these three blocks.** Smaller diff,
   clearer intent, but it forks a borrowed file.

Route 1 is the recommendation. **Not implemented pending the ruling**, because
it changes what every comparison on three dashboards means, and because the
ordering key is the open question below.

### Open: what is the ordering key

`event_config.csv` has `day_number`, populated 1..N and consistent with
`day_date` on every event checked. But `day_date` is the fact and `day_number`
is an assertion about it. **Recommend ordering by `day_date`** and asserting
`day_number` agrees — if they ever disagree, that is a config error worth
failing on rather than silently preferring one.

## DD5: the comparison anchor is consistent in run.py — the 1/2 Sept split is the weekday snap

Audited every site that derives a previous-year anchor. **All ~20 use
`event_config_prev['event_date_first']`** — Revenus, Vélocité, Présence,
Projections and the Suivi header alike. No card derives its own. The one
data-derived date (`run.py:2140`, `prev_dates[0]`) feeds a display label
("première vente"), not a comparison.

For `epk_2023` that anchor is **2023-09-01, Vendredi** — day 1 in the config, as
expected.

**But a 1 Sept / 2 Sept split is still explainable, and it is by design.**
`_prev_match_dow` maps a current date to the previous edition by J-X *and then
snaps to the same weekday*. epk_2026 is samedi/dimanche against epk_2023's
vendredi 1 / samedi 2, so a current Saturday snaps onto **2 Sept**, while the
J-X arithmetic alone would land on 1 Sept. The weekly grain does no snapping —
it buckets on `(event_date_first - order_date) // 7`, anchored on 1 Sept.

So the daily grain and everything else legitimately reference different dates,
and the offset between them is the constant proved earlier in this document. If
the mock shows some cards on 1 Sept and others on 2 Sept, that is reproducible
from the grain each card uses — it is not evidence of inconsistent anchors, and
re-anchoring the cards would break the daily comparison rather than fix it.

## Clamping is safe for LAYOUT and lossy for MEANING

Twice now, a clamp added to keep a layout intact has also erased the fact the
layout was displaying.

- **`Math.min(fill,100)` on the per-day presence bar.** `bordeaux_2026` Samedi
  is 19 388 against an 18 000 capacity — 107,7 %, 1 388 people over. The clamp
  kept the bar inside its track, which is right, and the accompanying
  `d.now>=d.cap ? ' · complet'` then labelled it *complet* — so an overbooked
  day rendered pixel-identical to an exactly-sold-out one. An operational fact
  became a rounding artefact.
- **The earlier case was the same shape**: a guard added for safety that
  silently removed the thing it was guarding.

**The rule:** a clamp answers one of two questions — "how wide should this box
be?" or "what is this number?" It is almost always right for the first and
almost always wrong for the second. When one expression does both, split it.
Here the bar keeps `width: min(fill, 100%)` and gains an amber fill plus an
explicit `+1 388 au-delà de la jauge`; nothing about the width changed.

Worth checking wherever `Math.min`, `Math.max`, `clamp()` or a `>=` threshold
sits next to a rendered figure. The width is a display decision. The number is
not ours to round.

## A clamp answers one of two questions

The canonical form of the lesson above, because it names where to look rather
than only what is true:

> A clamp answers one of two questions — **"how wide should this box be?"** or
> **"what is this number?"** It is almost always right for the first and almost
> always wrong for the second. When one expression does both, split it.

Checkable: grep for `Math.min`, `Math.max`, `clamp()` or any `>=` threshold
sitting next to a rendered figure. The bordeaux over-capacity day had two — the
bar width and a `d.now >= d.cap` label — and fixing only the one that was
reported would have left the card still claiming *complet*, because a second
element made the same claim from the same comparison.

## Trap #11: a fixture that renders cleanly but describes nothing

`redesign/fixtures/fixture_3day.html` was the only fixture exercising the
three-day case. It rendered without a console error, without a `NaN`, without a
horizontal scroll — it passed every assertion §6 and §7 define — and it
described no event that has ever existed. It was epk's payload with bordeaux's
day names, dates and capacities pasted over it.

**Why this was the one place with no coverage at all: a fixture looks like data
rather than like code, and data is what checks are pointed *at*.** Every guard
in `verify/` aims at generated output or at source. Nothing aimed at the inputs
those guards trust, because trusting them is the point of having them.

The tell was in the payload the whole time: **`presdays.days` summed to 34 266
while `presdays.paid` said 10 039.** Two numbers describing the same tickets,
disagreeing by a factor of three, and nothing compared them.

**The rule, actionable half first:**

> **Generate fixtures; never hand-author them.** A generated fixture is
> consistent by construction; a hand-authored one is consistent only by luck.
>
> Where one must be trusted before it can be regenerated, **assert it is
> internally consistent — its own totals must reconcile** — before trusting
> anything it proves. A fixture that renders cleanly but describes nothing tests
> nothing.

The second half detects the failure; the first removes it. Prefer removing it.

The cheap consistency assertion is the one that would have caught this: within a
fixture, every figure derivable two ways must agree both ways —
`sum(presdays.days[*].now)` against the composition totals,
`presdays.paid + presdays.free` against `cur.n + cur.inv`. Neither needs to know
the right answer, only that the fixture agrees with itself.

Same family as trap #10, one level out: #10 was a *check* that passed for the
wrong reason; this is *test data* that passed for the wrong reason.
`verify/check_fixture_quarantine.py` enforces the specific case.

## Trap #12: a missing input given the operation's IDENTITY value

epk's Dimanche had no reference day at all under name matching. Its projection
card rendered a coefficient of **exactly ×1.00** and *Trajectoire 2023 = 4 515*
— which is Dimanche's own current presence. The no-reference path projected the
present straight back at itself and displayed it as a forecast, with flat
scenarios of 4 515 / 4 675. It has been on a live page for the life of the
dashboard.

**That is worse than the zero comparisons DD4 was about.** A zero is visibly
missing. A flat scenario at ×1.00 looks like a considered projection that
happens to predict no growth, and someone could plan against it.

> **When an input is absent, propagate the absence. Never substitute the
> operation's identity element — it makes "we have nothing" arithmetically
> indistinguishable from "we measured no change".**

×1 for a coefficient, 1 for a divisor, 0 for a count, an empty string for a
label: all of them render as ordinary values. The same bug produced a
`+16 000 %` on the redesign mock via `B.vel || 1`, three weeks apart, in a
different codebase, and neither was found by a check.

**What makes it hard to see is that it arrives as a *defensive* guard.** The
line is `run.py:3051`:

```python
coef_display = vel_14d / prev_vel_14d_dn if prev_vel_14d_dn > 0 else 1.0
```

Whoever wrote that was preventing a `ZeroDivisionError`, correctly. The bug is
entirely in the choice of fallback: `1.0` instead of `None`. A crash would have
been *better* — it would have been found on the first build.

**It is not one line. There are six, all in the projection path** (run.py is
do-not-modify, so these are recorded, not fixed):

| line | expression | what the fallback means |
| --- | --- | --- |
| **3051** | `vel_14d / prev_vel_14d_dn … else 1.0` | **confirmed firing** — Dimanche's ×1.00 |
| 2975 | `weeks[0]['vel'] if … > 0 else 1` | a zero first-week velocity becomes a baseline of 1, so every later ratio is the raw velocity wearing a ratio's clothes |
| 2978 | `w['vel'] / baseline_vel … else 1.0` | same shape, one level down |
| 3554 | duplicate of 2975 | |
| 3557 | duplicate of 2978 | |
| 3632 | `… if day_ratios else 1.0` | an empty ratio list becomes a flat multiplier |

Only 3051 is confirmed to have fired. The others are the same shape and have not
been observed — which is exactly what 3051 looked like until someone matched
Dimanche to a real day.

**Grep target:** `else 1.0`, `else 1`, `or 1`, `|| 1`, `?? 0` sitting on the
false branch of a guard whose true branch is a division or a ratio. Ours are all
in `run.py`; `scripts/` currently has none — the two hits there are an exit code
and a depth counter, which are not this.

## Two traps from the Route 1 re-key

**The obvious seam can be complete-looking and partial.** run.py calls
`calculate_metrics(tickets_prev_filtered, event_config_prev)` exactly once, which
makes it look like the whole reference side passes through one place. It does
not: `tickets_prev_full` — the *unfiltered* list — is what vélocité and
projections read. Re-keying only what `calculate_metrics` was handed would have
fixed Par Jour and left the other two sites on the old day names: the exact
partial fix that was ruled worse than none, arrived at by doing the obvious
thing at the obvious seam. **A single call site is not evidence that a single
object flows through it.**

**A rename map can destroy its own input.** epk's mapping is
`{samedi → dimanche, vendredi → samedi}`. Applied in place, sequentially,
`samedi` is overwritten by `vendredi`'s value before its own is read. Build a
fresh dict; never rename in place. Same family as the `re.sub` backslash bug —
an operation that consumes the thing it is also producing into.

## The failures that survive review are the ones that WORK

Traps #10, #11 and #12 are the same fact seen from three sides, and the fact is
worth stating on its own:

| # | what it was | it survived because |
| --- | --- | --- |
| #10 | a **check** written for a known bug | it passed |
| #11 | a **fixture** in the acceptance criteria | it rendered |
| #12 | a **guard** against a division by zero | it prevented the crash |

None of them failed. Each did the thing it was written to do — and each did it
at something other than the thing that mattered. A check that errors, a fixture
that throws, a guard that lets the exception through: all three would have been
found on the first run.

**Review looks for things that are broken. These are not broken.** They pass,
render and return. So the question review has to ask is not "does this work?"
but **"if this were wrong, what would look different?"** — and when the honest
answer is *nothing*, that is the finding.

Practically: for any check, fixture or guard, name the artefact it would fail
on and go run it there (`verify/CHECKLIST.md`'s standing step). For a guard
specifically, ask what its fallback *means* — a fallback that renders as an
ordinary value is trap #12 waiting.

## The redesign replaces the body; the passes patch regions. That is a real gap.

Every deploy so far has patched REGIONS of run.py's markup and asserted the
surrounding structure was unchanged. The redesign replaces the entire page body,
so "assert the surroundings" has no referent. Three consequences found by
inspection, recorded before the payload work starts:

1. **`apply_redesign` swaps the single `<style>` block wholesale.** There is no
   inline-style rewriter — `CLASS_RENAMES` rewrites three `class=` attributes and
   nothing touches `style=`. The real collision is the `<style>` block itself:
   the redesign needs its CSS in the same one place `apply_redesign` overwrites.
   Ordering is the whole answer, and it must be decided, not discovered.
2. **The `.sw-*` dropdown JS is document-delegated, not nav-scoped** — the
   handler is `document.addEventListener('click', …)` finding triggers via
   `e.target.closest('[data-sw-trigger]')`, and `closeAll()` is
   `document.querySelectorAll('.sw-wrap.open')`. Page content gets it free.
   **But the mock ships its own copy of that JS**, and two identical
   document-level handlers do not merely duplicate work: the first opens the
   wrap, the second then sees `wasOpen === true` and closes it. `stopPropagation`
   does not stop a sibling listener on the same element. **The dropdown would
   never open.** Inject the mock's body JS wholesale and this ships.
3. **`refday` is never null anywhere in the mock**, so §5.6's "a reference with
   fewer days must degrade honestly" has never actually been rendered. Bordeaux's
   Jeudi is the first null, and the quarantined fixture avoided the case by
   inventing `jeudi ref 1640`. The one path the spec singles out as needing care
   is the one with no coverage at all.

## `day_is_warmup`: the column, and the two ways it can be silently absent

A warm-up is a configured per-day fact (`DASHBOARD_REDESIGN_SPEC` §5.3). The
column is in `event_config.csv`, marked on `bordeaux_2026` Jeudi and nowhere
else. Adding it changed no output — all six dashboards byte-identical.

**It can go missing in two independent ways, and neither one fails on its own.**

1. **The column is absent from the CSV.** `csv.DictReader` ignores unknown
   columns, which is what made adding this one provably inert — and is exactly
   what makes losing it invisible. Every day would read unmarked, bordeaux would
   open on 40 783 / 44 500 instead of 34 804 / 36 000, no badge would render,
   and nothing would fail.
2. **run.py drops it even when the CSV has it.** `run.py:242` builds each day
   from four explicit keys — `day_number`, `day_name`, `day_date`,
   `day_capacity`. `day_is_warmup` never reaches `event_config['days']` however
   the CSV is written.

The second one nearly shipped. `_assert_warmup_shapes` originally read
`x.get('day_is_warmup')` off run.py's day dicts, and its unit tests passed —
because the tests built their own dicts, which carried the key. It would have
seen nothing forever, on every event, and reported every shape as fine. **A
guard that reads from the wrong structure is trap #10 with a bigger blast
radius: the check does not merely miss the bug, it certifies its absence.**

So `read_warmup_flags()` reads `event_config.csv` **directly**, asserts the
column exists in the header, and asserts the mark is present on the events §5.6
depends on. Proved against the real file, not a copy: column removed → exit 1;
column present but mark cleared → exit 1; both restored → exit 0.

**A default of `False` would have been the wrong answer, silently** — trap #12
in a config reader rather than an arithmetic guard. When an input is absent,
propagate the absence.

## The locked artefact and the working one must have different names

`redesign/mock/dashboard_v3.39.html` stopped being v3.39 the moment the first
authorised change landed in it. Same filename, different file — and **"the mock
is absolute" does not name anything once the name has drifted.**

That is how a correct finding got overturned. The warm-up badge was searched for
in the WORKING mock, found at lines 643 and 1165, and concluded to have been
there all along. It had not: both lines were added under EE2, and the original
upload contains no `pill-warm`, no `d.warmup` and no badge markup at all. The
instinct that it was missing was right, and the artefact that disproved it was
the wrong artefact.

**The fix is naming, then enforcement.** `redesign/locked/` holds the upload
byte-identical and is never edited. `verify/check_mock_deviations.py` asserts
the working copy differs from it in exactly the authorised ways — in **both**
directions, because a missing authorised deviation is an approved change
someone reverted, which is quieter than an invention and no less wrong. Four
failure modes confirmed: an unauthorised hunk, a reverted authorised one, new
CSS, and the locked reference deleted.

The stylesheet now has zero authorised deviations, which is the strongest form
this takes: `dashboard_redesign.css` must be byte-identical to locked.

### The mock's COMMENTS carry design decisions, not just its markup

The original mock said, on the warm-up toggle:

> `/* … Until that is a config field, … */`

That is a deliberate deferral, recorded in the artefact. Reading it would have
said the badge was absent **by choice** rather than by oversight, and the
correct finding would not have been overturned.

**When an artefact appears to be missing something, check whether it says why.**
A generated file has no opinions; a hand-authored reference is full of them, and
they are load-bearing.

## run.py:242 is a chokepoint: no new config column ever reaches `days`

```python
events[eid]['days'].append({
    'day_number': …, 'day_name': …, 'day_date': …, 'day_capacity': …,
})
```

Four explicit keys. **Any column added to `event_config.csv` is invisible to
`event_config['days']`, forever, silently.** `day_is_warmup` is simply the first
one we needed; the next person to add a column will hit exactly this.

The pattern to copy is `build_dashboard.read_warmup_flags()`: read
`event_config.csv` directly, assert the column is in the header, assert the
values that matter are present. Do not read a new column off run.py's day dicts
and do not default it — see trap #12.

And the reason this one nearly shipped is worth keeping attached to it:

> **A guard that reads from the wrong structure does not merely miss the bug —
> it certifies its absence.**

`_assert_warmup_shapes` read the flag off run.py's dicts and its five unit tests
passed, because the tests built their own dicts, which carried the key. It would
have reported every event's warm-up shape as correct, forever, having never seen
a flag.

## Trap #13: a signal that always fires carries no information

"Daily dashboards / Commit dashboards" failed on **every run** for days, in
about eight seconds, while all six build jobs went green. The cause was one
line:

```
git add -- 'data/*_merged.csv' 'data/*_state.json'
```

A quoted pathspec matching nothing makes `git add` exit 128 **and stage nothing
from that command**, and each Actions `run:` block is `bash -e` — so the step
aborted there. The diff check, the commit and the whole push-retry loop below it
were unreachable and always had been.

No `*_state.json` has ever existed, for two independent reasons: the daily job
calls `fetch_csv.py` without `--incremental`, and the commit job runs on a
separate runner that sees only the uploaded artifacts, which never included
state files. `.gitignore` carries `!data/*_state.json` — an un-ignore rule for a
file type that has never been produced. The whole path was written for a mode
the daily job does not use.

**The failure was not that it broke. It was that it kept breaking.** A red
"Commit dashboards" became the normal state of the board, so a *genuine* commit
failure — a push race, a permissions change, a real conflict — would have looked
exactly like the noise and been read the same way: as the usual one.

> **A signal that always fires carries no information.** An alert that has been
> red for days is not an alert; it is a background colour. The cost is not the
> broken job, it is the loss of the channel — everything that would have used
> that signal to reach a human no longer can.

Same family as #10–#12 seen from the operator's side rather than the code's:
each of those was something that *worked* at the wrong thing, and this is
something that *reported* at the wrong thing until reporting stopped meaning
anything.

**Worth checking whenever a job is red:** how long has it been red, and did
anything change on the day it went red? If the answer is "since it was written",
the step below it has never run, and that is a separate finding from the error
message.

### What it actually cost, which was not what it looked like

The obvious reading is "the dashboards are frozen". They were not. The pages on
`main` were rebuilt by hand during this work as recently as `8c5ca1c`. What
stopped was the **data**: the last `data/*_merged.csv` commit is `6c772a9`,
2026-08-07.

So the pages were freshly generated *from two-day-old CSVs* — which is harder to
notice than a stale page, because the file's commit date looks current while its
contents are not. The footer says so if you read it: `epk` stamps
`Dernier billet 07/08 · 09:41` on a page written on the 9th, because the newest
`order_date` in the CSV is the 7th.

**Consequence to carry forward:** every figure verified during the Route 1 work
— the byte-identical canaries, epk's 3 866 / 6 766 — was measured against 07/08
data. The comparisons were like-for-like so the conclusions hold, but the
numbers are as of the 7th, not today.

## Typography is frozen as the mock renders it, with one exception (D9)

Ruling, after a full frontend audit of the six published v2 pages came back
clean: **what Leo sees rendered IS the target.** Any change that alters the
rendering is a regression by definition — including a change that makes the CSS
more internally correct. "More correct" is not the standard; "pixel-identical to
what Leo approved" is.

Four things in the type stack look like oversights and are **not** to be fixed.
They are recorded here precisely so that a future pass does not discover them
afresh and tidy them:

| # | What it looks like | Ruling |
|---|---|---|
| (a) | `Space Grotesk` is downloaded on every page at 400/500/600/700 and used by nothing. The browser confirms it: `document.fonts` reports all four faces `unloaded` after a full render. | **Leave it.** It lives in the shared `font_links.html`, which production also uses. Removing it is a production change dressed up as a redesign cleanup. |
| (b) | `--ff-mono` named `DM Mono` first and DM Mono was never loaded by any page. | **REVERSED — see D9 below.** |
| (c) | `.fver` hardcodes `'JetBrains Mono', monospace` instead of going through `--ff-mono`. | **Leave the rule as written.** D9 makes the token resolve to the same family, so the inconsistency it recorded disappears without the rule being touched. |
| (d) | `--ff-display` and `--ff-body` are the same stack, so the display token buys nothing. | **Leave it.** Collapsing them changes nothing today and removes the seam where a display face would go. |

And the thing that makes (a)–(d) matter less than it seems: **Leo approves on
Apple hardware.** Anything that falls through to a system font renders one way
for him and another on Windows and Android. Approval on his iPad is approval of
the Apple render, not of the page everywhere.

### D9 — `--ff-mono` becomes `'JetBrains Mono', monospace`

That last paragraph is what overturned (b). The requirement changed from "do not
alter the render" to "render identically on every device", and `--ff-mono` was
the only thing standing in the way:

- `--ff-mono: 'DM Mono', 'SF Mono', monospace` — **DM Mono is never requested by
  any page.** So the stack fell through to SF Mono on Apple and to whatever
  generic monospace the device had on Windows and Android.
- Every other element uses DM Sans or JetBrains Mono. Both download. Both were
  already consistent everywhere.
- SF Mono cannot be served — Apple system font, not licensed for web embedding,
  absent from Google Fonts. So consistency *requires* a webfont, and any webfont
  necessarily changes how those elements look on Leo's iPad. He accepted that
  trade.

JetBrains Mono was chosen because it already downloads on every page at
400/500/600 and already renders in `.fver`: not a new typeface to him, and no
additional request. DM Mono — the mock's own declared first choice — was
considered and rejected. It was never actually loaded, so it is an unrealised
intention rather than something that ever rendered, and adopting it would add a
font download for six small labels.

Scope is two rules: inline `<code>` in the détails accordions (`.ac-b code`) and
the data-source keys (`.dsrc-k`). Roughly a dozen elements per page.

**One line to revert if he dislikes it on screen**, which is why it is a token
change and not a rewrite of the two rules.

### D9 is the first authorised CSS deviation, and the check had to learn the shape

`check_mock_deviations` allowed exactly one class of stylesheet difference:
`.db-*` rules carried verbatim from production. A *modified* line was a failure
by construction — correctly, until a ruling authorised one.

`AUTHORISED_CSS` now carries `(id, ruling, locked line, replacement)` and is
checked **in both directions**, exactly like the mock's HTML hunks: the locked
line must be gone *and* the replacement present. Half-applied is not passing.
A ruling-authorised edit that someone later reverts fails as loudly as an
invented one, which is the whole point of the two-direction rule.

## The check validated the FILE, not the PAGE

Found in the same audit, and the more important of its two findings.

`check_mock_deviations` compared `redesign/style/dashboard_redesign.css` against
the locked copy. But **no v2 page links that file.** Pass 0 inlines it and then
rewrites asset paths inside it, so the shipped `<style>` is a *transform* of the
file. Everything between the two was outside the check's coverage: a future
transform could have altered any rule and the check would still have printed
`ok`.

That is the same failure mode as traps #10–#13 — a check that keeps passing
while its target moves — so it was closed rather than noted.

`check_pages()` now asserts, for every page under `v2/`, that its inlined
`<style>` equals the file put through **exactly** `build_v2.PAGE_PATHS`. Any
other difference fails. Negative-tested by editing one rule in one shipped page:
`.dsrc-k{font-family:sans-serif…}` → exit 1, with the offending line printed.

**`PAGE_PATHS` is imported, never restated.** That is deliberate and it is the
concrete instance of the cutover problem: `url('../upload.JPG')` is correct one
directory deep and wrong at the root. When those substitutions become
location-aware, a second copy of them in the check would go stale and start
disagreeing with the build — silently, since a stale expectation still produces
a clean diff against itself. Importing means the check follows the build.

## Leo's v2 review: four of the six bugs were one missing boolean

The review found six bugs. Diagnosis collapsed four of them into one line of
the payload, and the shape of that is worth keeping.

`fut` was `false` on every row of every page. The Suivi template reads:

```js
const past = rows.filter(r => !r.fut && r.jx > D.jx + 8);
const now  = rows.filter(r => !r.fut && r.jx <= D.jx + 8);
const fut  = rows.filter(r => r.fut);
```

and the `CUT('Précédent')` / `CUT('À venir')` separators live *inside* the
`past` and `fut` blocks. So one false flag removed four things Leo listed
separately: the À venir block, the Précédent button, and both separators.

**Two faults, and they had to be fixed together.** `jx` was
`(cutoff - day).days` — days ago — while `D.jx` is `(event - cutoff).days`,
days remaining. Two scales, differing by exactly `D.jx`. Nothing could ever
equal `D.jx` (no "Aujourd'hui" row) and nothing could be less than it (no
future). And the rows stopped at the cutoff, so there was nothing for `fut` to
be true *of*. Rescaling alone gives a correct today and still no future;
extending alone gives future rows that never match. Either fix alone looks
like it did nothing.

**The clue that was there all along:** the chart series already had it right —
`rolling()` and `cumulative()` both end `+ cap` where `cap` is `D.jx`. Only
`daily_rows` omitted it. One function on a different scale from its neighbours,
in a file where every other series agreed.

### The projection was a straight line between two correct endpoints

`p1` and `p2` were `[{jx: jx_left, v: today}, {jx: 0, v: final}]`. Both ends
right, no shape, and — because the scenarios differ only in slope — *identical
to each other*. The toggle worked perfectly and swapped one flat segment for
the same flat segment. A bug you cannot see by checking values, only by
checking that two things which must differ actually do.

The shape is the reference's own cumulative curve replayed over the remaining
days: `p1(jx) = today + (ref(jx) − ref(D.jx))`, `p2` the same scaled by the
velocity coefficient, both clamped at 120% — read off the locked mock's own
payload rather than invented, and cross-checked point-by-point against it.

### A5: the seam again, one layer up

The mock's nav block ended `window.swCloseAll = closeAll;`. Replacing that
block with production's (correctly — production's nav is the live one) took the
export with it. Production defines `closeAll` and keeps it private.

Both call sites are written `if (window.swCloseAll) window.swCloseAll();`, so
the guard did its job: no error, no console, nothing to notice. The dropdown
simply stopped closing when you picked something.

**Markup and behaviour were reconciled; the INTERFACE between them was not.**
Grepped both blocks for `window.` assignments to establish that `swCloseAll` is
the only symbol the replaced block ever exported — "the one I noticed" is not
an answer to "what else did it export".

### Found while fixing A0, not by any check: `const LG`

`const D` was not the only payload in the mock. `const LG` sits three lines
below it and drives the "Logique de projection" accordion. Nothing substituted
it, so **every v2 page shipped epk's samedi 8 083 / dimanche 4 513** under its
own event's name — a full accordion of another festival's figures, with no
error and no missing value.

`check_v2_identity` could not see it: it greps for the mock's *names and
dates*, and this was the mock's *numbers*. Same lesson as the residual-leak
scan that found the three hardcoded identity blocks — the thing you search for
determines what you can find.

Still open in the same family: `CANDS`, the Suivi comparison menu, is a
hardcoded list in the mock. It happens to name the right editions because the
mock was built from real data, but the "179 j" metadata is a snapshot. It
should be built from the payload when B1 wires that menu up, not before —
wiring it twice is how the two menus came to disagree in the first place.

### A6 is a defect in both heads, so it was fixed in the shared pass

Nothing in `dashboard_template.html` ever locked scroll, so the dashboard slid
past behind the gate on production too. The template is do-not-modify, but
`postprocess_html.py` already patches that same script block (it is where
shared auth is injected), so the fix went there and reaches both heads.

Driven off a `MutationObserver` on the overlay rather than off the two code
paths that hide it. Both paths work today and so will a third added later,
because the observer watches the element whose state actually decides the
answer.

### The check that would have caught all of it

`verify/check_v2_behaviour.py`, in two halves that must both pass:

  - the **payload**, asserted against the file: some row carries `fut:true`,
    exactly one row matches `jx === D.jx`, the two scenarios are not equal,
    `projx.cands` has more than one entry, `LG`'s days are this event's days.
  - the **page**, asserted in a browser: `#b-fut` and `#b-past` exist, the two
    scenario panes draw different `d` attributes, the menu closes on select,
    the document does not scroll while the gate is up.

Deliberately split. `const D` is script-scoped and unreachable from the page,
which is the right constraint: reading the payload in the browser half would
let a correct payload vouch for a page that never used it, and that is the
entire class of failure this repo keeps meeting.

Everything forward-looking is gated on `D.jx > 0`. A finished event has no
future, and an assertion that cannot hold on two of six pages is one that gets
disabled by whoever meets it first.

**Negative-tested, five ways:** flag every row `fut:false`, set `p2 = p1`, drop
all but one candidate, delete the `swCloseAll` export, delete the scroll-lock —
each fails on its own assertion, and the payload and page halves catch the
first three independently.

### `check_v2_identity` had to learn the difference between prose and data

A4 puts every finished edition's `label` in the payload, so "Elektric Park
2023" now appears on the Bordeaux page legitimately, as a comparison you can
pick. The scan failed five pages for it.

The exclusion is the `const D` / `const LG` literals — and, so that this is a
narrowing rather than a hole, every label inside the payload is now checked
against `event_config.csv`. A mock literal cannot hide there without also being
a configured event. Same move as the `<nav>` exclusion, and the second time
this scan has had to separate what the page *says* from what the page *offers*.
