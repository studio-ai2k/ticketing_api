# Actions archive audit — findings that never reached the repo

**Run 2026-10-06, prompted by Festiflow.** Crazy Carnaval's probe-verified id sat
in an Actions log for six weeks while the repo said we had nothing. The question
was: *if one finding escaped the commit step, how many others did?*

**Answer: at least three, and the method found them in one pass.**

## The method, so it can be repeated

For each probe workflow, count how many `.md` files cite it. **Zero citations
means its output was never written down**, because every probe in this project
exists to answer a question somebody wrote down.

| workflow | cited in docs | runs | verdict |
|---|---:|---:|---|
| `probe-shotgun-account` | 4 | 7 | partly — one run's output was missing |
| `probe-platform-fields` | 1 | — | documented |
| `probe-dice-event` | 1 | — | documented |
| `verify-incremental` | 1 | — | documented |
| **`probe-shotgun-channels`** | **0** | 1 | ⛔ **nothing written down** |
| **`dice-diagnose`** | **0** | — | ⛔ **nothing written down** |
| `fetch-reference-event` | 0 | — | a fetcher, not a probe — no finding expected |

## What was recovered

### 1. Crazy Carnaval's id — run `32658474632`, 2026-08-23

`549064`, `episode` account, probe-verified on both co-host settings,
`event_name='Madame Loyal Paris - Crazy Carnaval Edition'`. Now in
`ADDING_AN_EVENT.md`, where that document says a probe's output belongs.

**Cost:** Festiflow was told, in writing, that we held nothing for this event.

### 2. The whole `ticket_status` enumeration — run `31055925893`, 2026-08-05

Five values observed — `valid`, `resold`, `refunded`, `canceled`,
`payment_plan_pending` — plus every observed `utm_source`, `payment_method` and
`deal_visibilities` value. Now in `SHOTGUN_TICKET_STATUS_AND_CHANNELS.md`.

**Cost:** `PLATFORM_FIELD_INVENTORY.md` and the Festiflow handover both said
pending and failed payments were unknown on the Shotgun side. They had been
enumerated two months earlier. Two findings in that output are load-bearing and
neither was known: **`utm_source` spells the same source two ways across two
events**, and **`deal_visibilities` serialises the same set in two orders** — an
equality test on it mis-buckets 1,295 tickets on one event.

### 3. The 505434 co-host result — run `31053170251` vs `37467368356`

Not a missing output but a **stale** one: the committed paraphrase said Sonora
could not see the event, from a probe that predated the flag that makes the test
meaningful. Corrected in `fetch_csv.py` and `SHOTGUN_ACCOUNT_MATRIX.md`.

**Cost:** two months of a wrong platform-level claim, repeated to Festiflow.

## `dice-diagnose` — unaudited

Zero doc citations, and **I did not read its runs.** It is the one remaining
candidate and it is named here rather than left silent. One line would settle it:
list its runs and read the latest log.

## The shape, which is the part worth keeping

**A probe's value is in its output, and its output lives somewhere nobody
reads.** The repo's own `ADDING_AN_EVENT.md` already requires "put its output in
the commit" — the rule existed and was skipped, which is the ordinary way a rule
fails. Nothing here was hidden; it was merely not copied.

Three properties made it survive two months:

1. **A run log looks like a transcript, not a finding.** Nobody greps Actions.
2. **The paraphrase is written at the moment of discovery**, when the detail
   feels obvious and compressible. `fetch_csv.py:95`'s "and nothing under Sonora"
   was a true sentence about one run and a false claim about the platform.
3. **Nothing fails when it is skipped.** No check asserts that a probe's output
   reached a file.

**The cheap fix is (3)**: a probe workflow could append its own output to a dated
file and open a PR, so the finding lands by default rather than by discipline.
Not built — proposed here, because the next seat will meet this again.

## For anyone using this repo as a reference

**Our Actions logs contain findings our files do not.** If a question matters,
ask rather than assuming the files are complete. That is now stated in the
Festiflow handover too.
