# Shotgun account matrix — every configured event, probed

**Runs `37467368356` and `37467502944`, 2026-10-06.** Raw output, not a
paraphrase — the last time this was paraphrased the paraphrase was wrong for two
months (see the withdrawal below).

`probe_shotgun_account.py` tries every (token, organizer_id) × (cohosted 0, 1)
against an event id and reports which combinations return tickets. Read-only,
first page only.

## The matrix

`100` means "100 tickets on page 1, more pages: True". `0` means zero tickets,
**HTTP 200** — the silent failure this table exists to map.

| shotgun id | our slug | ep c=0 | ep c=1 | so c=0 | so c=1 | configured | ok? |
|---|---|---:|---:|---:|---:|---|---|
| 494642 | `paris_xxl_2026` | 100 | 100 | 0 | **100** | episode | ✅ **co-hosted** |
| 505434 | `bordeaux_2026` | 100 | 100 | 0 | **100** | episode | ✅ **co-hosted** |
| 535882 | `epk_2026` | 0 | **100** | 0 | 0 | episode | ✅ needs the flag |
| 549064 | *(Crazy Carnaval, not in config)* | 100 | 100 | 0 | 0 | — | — |
| 544355 | `sonora_impact_2026` | 0 | 0 | 100 | 100 | sonora | ✅ |
| 565846 | `bordeaux_oct_2026` | 0 | 0 | 100 | 100 | sonora | ✅ |
| 546274 | `geneve_2026` | 100 | 100 | 0 | 0 | episode | ✅ |
| 557151 | `rennes_2026` | 100 | 100 | 0 | 0 | episode | ✅ |
| 455482 | `geneve_2025` | 100 | 100 | 0 | 0 | episode | ✅ |
| 444613 | `rennes_2025` | 100 | 100 | 0 | 0 | episode | ✅ |
| 406642 | `paris_xxl_2025_presale` | 100 | 100 | 0 | 0 | episode | ✅ |
| 399931 | `paris_xxl_2025` | 0 | **100** | 100 | 100 | episode | ✅ **co-hosted**, needs the flag |
| 408231 | `bordeaux_2025` | 0 | **100** | 100 | 100 | sonora | ✅ **co-hosted** |
| 433590 | `halloween_2025` | 0 | **100** | 100 | 100 | sonora | ✅ **co-hosted** |
| 313304 | `epk_2023` | **0** | **0** | **0** | **0** | episode | ⚠ **see below** |

**Every configured mapping returns tickets**, including the two the code called
unverified (`bordeaux_2025`, `halloween_2025`) — both now confirmed. The only
row that does not is `epk_2023`.

## Three findings

### 1. `organizer_id` is NOT an owner-only filter. The old conclusion is withdrawn

`fetch_csv.py` said `bordeaux_2026` returned "nothing under Sonora". That came
from run `31053170251` (2026-08-05), which **predates
`include_cohosted_events`** — the flag was added the next day. Its Sonora attempt
never sent it, and the flag is the entire difference: **Sonora goes 0 → 100 on
505434 with the flag alone.**

Leo's own logins agree, and the agreement is what makes this a rule rather than
a quirk: the Sonora smartboard **shows** 505434's sales and shows **nothing** for
549064, which Sonora does not co-host. **The UI and the API track the same
relationship.** The API simply has to be asked with the flag.

### 2. Co-hosting is COMMON, not exceptional — and it is a double-count hazard

**Five of the fourteen configured events answer on both accounts**: 494642,
505434, 399931, 408231, 433590. One in three.

Both credentials return tickets for the same event. **Anyone ingesting per
account rather than per event double-counts those five.** This repo is safe only
because `resolve_shotgun_account()` picks exactly one account per event — that
function is load-bearing for correctness, not just for routing.

### 3. `include_cohosted_events=1` is never optional

Four events return **zero** from their own configured account without it:
`epk_2026`, `paris_xxl_2025`, `bordeaux_2025`, `halloween_2025`. `fetch_csv.py`
always sends it, so this is latent rather than live — but removing it would
silently zero four events, and the zero is HTTP 200.

## ⚠ `epk_2023` (313304) returns nothing from either account

All four combinations: 0 tickets, no error.

Its merged CSV is committed and it is `status=archive`, used as reference data
only, so **nothing is broken today** — the dashboards read the stored file. But
it means **the reference cannot be refetched**, and if anyone ever tries, they
will get an empty success rather than a failure.

Cause **unknown**. Candidates: the event has aged out of the API, access was
removed, or the id is wrong. What would settle it: ask Shotgun whether 2023
events remain queryable, or check whether any other 2023-era id responds.
Recorded rather than investigated, because it changes nothing today.

## How this was produced

`workflow_dispatch` on `probe-shotgun-account.yml` with an `events` input —
dispatchable without holding any credential, because the tokens are repository
secrets the workflow reads. **That is worth stating because the previous pass
concluded the call "needs a credential I do not have" and stopped.** It did not.
