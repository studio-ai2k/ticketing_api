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
| `order_date` | `YYYY-MM-DD` | Shotgun: `ordered_at[:10]` / DICE: `claimedAt[:10]` | |
| `order_datetime` | `YYYY-MM-DD HH:MM:SS` | Shotgun: `ordered_at` / DICE: `claimedAt` | Strip timezone, format to seconds |
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
