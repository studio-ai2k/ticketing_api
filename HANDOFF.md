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
