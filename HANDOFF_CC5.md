# Handoff — the migration is parked

Leo is parking the Billetterie migration. This is the state at that moment, what
is **ruled but unwritten**, what is **open**, and how the seat works.

`HANDOFF_CC4.md` remains the source for the standing material — the green loop,
the merge rules, and §9's catalogue of ways a measurement lies. **Read its §9.**
This file does not repeat it; it adds to it.

> **`HANDOFF_CC4.md` §0 is now WRONG about one thing and it matters.** It says
> "The cutover has NOT happened." It has. Main is post-cutover: `v2/` does not
> exist, the root pages are the pass-0 build, `legacy/` holds the retired ones,
> and `check_cutover_write.py` asserts the tool's refusal to run again. Its §1,
> §2 and §3 are historical. Everything from §4 down still applies.

---

## 0. State, verified rather than remembered

Confirm with `git ls-remote origin main`, never a local ref — a stale local
`main` at `273457f` is an unrelated root that deletes the whole `verify/` suite.

At the time of writing, `origin/main` is **`07ff8d9`**.

- Seven active pages, built by `scripts/build_v2.py` and post-processed by
  `scripts/postprocess_html.py`, deployed from `main` by Pages.
- `V2_SHARED_ASSETS` has **11 entries**. Touching any one forces a full
  seven-page rebuild; `check_build_stamp.py` is what notices.
- `verify/` holds **36 `check_*.py`** plus `assert_redesign.sh`.
- `event_config.csv` is **CRLF, no BOM**, 8452 bytes, 56 lines. Edit at byte
  level. A `csv.DictWriter` round-trip once added a BOM and broke
  `run.load_event_config` with `KeyError: 'event_id'`.

### The loop. Run it before believing anything here, including this line.

```bash
SKIP='check_login_bg check_platform_cards check_section_amber check_stampable'
for f in verify/check_*.py; do
  n=$(basename "$f" .py)
  case " $SKIP " in *" $n "*) continue;; esac
  timeout 1800 python3 "$f" >/dev/null 2>&1 || echo "RED  $n"
done
bash verify/assert_redesign.sh >/dev/null 2>&1 || echo "RED  assert_redesign.sh"
```

**32 checks run.** The four skipped take a page argument and run *inside*
`assert_redesign.sh`; running them bare produces an `IndexError` that looks
exactly like a finding and is not.

`check_b1_switch` is the slow one — **350s** at last run, well inside the
timeout, but it is documented at ~30 minutes and a `timeout` that fires reads as
RED, not as "did not run". If you shorten the timeout, run it separately and say
so. **Name every exclusion in the same breath as "green". Every time.**

Last full run before parking: **32 of 32 green, plus `assert_redesign.sh`.**

---

## 1. RULED AND UNWRITTEN — the queue

Every item here has a decision behind it. None needs re-litigating; they were
cut from the last pass for scope, not for doubt. **The order below is the order
Leo gave.**

### 1.1 The bank-label subtext

The switcher subtext currently reads `{{EVENT_CODE}} · {{J_MINUS_LABEL}}` —
`REN 061126 · J-75`. It should read the event's **bank label** instead. **The
countdown stays.** Separator is an **en dash, U+2013** — our transcription used a
hyphen and the fiche won.

| event_id | bank label |
|---|---|
| `paris_xxl_2026` | `ML 130326 – VILLEPINTE` |
| `bordeaux_2026` | `ML 120626 – BORDEAUX` |
| `epk_2026` | **`ML EPK 050926`** — see below |
| `bordeaux_oct_2026` | `SONORA BORDEAUX 161026` |
| `geneve_2026` | *(empty — see 1.2)* |
| `rennes_2026` | `ML 061126 – RENNES` |
| `sonora_impact_2026` | `SONORA VILLEPINTE 260926` |

**`ML EPK 050926` IS A SHORTENED FORM OF AN ACCOUNT NAME, NOT THE ACCOUNT NAME.**
The real one is `MADAME LOYAL X ELECTRICK PARK 050926` — 43 characters with the
countdown, measured at 264px of text and **253px of nav overflow** at 393px,
against 82px today. It does not truncate; it pushes the module switcher and
"Détails" off the initial view. Leo shortened this one and only this one. Record
it where someone will read it, so nobody later "corrects" it back to the bank's
spelling and reintroduces the overflow. **`ELECTRICK` stays misspelled wherever
the real name is stored — it is the account's real name.**

**Where it is emitted.** `run.py:2076` computes `event_code` and **run.py is
do-not-modify**, so the substitution goes through `postprocess_html.py`, which
already owns this string: `NAV_SW_BLOCK_RE` captures it as group `sub` and
`build_session_menu` re-emits it into the trigger and the active menu row.
Measured at byte 48821–50028 in `rennes.html`, well before `</nav>` at 55808 —
**outside the seam, survives pass 0.**

**It now costs almost nothing.** With the full name in the trigger, the name is
the wider element on six of eight events, so the subtext is free on those.

### 1.2 Genève's empty bank cell, and the check that names it

Genève has **no row on the bank list** — six of seven events have a bank label
and it does not. Leave the cell **empty**, and write a check that names Genève as
**the one authorised empty**, so a *new* empty cell fails.

Not a silent `|| <literal>` fallback. `check_mock_literals` strips `${…}` before
scanning reader-facing text, so a fallback literal is structurally invisible to
it — an absence has to be declared, not defaulted.

This is the four-kinds-of-empty-cell lesson applied **before** the fact rather
than after it, which is the first time on this project an absence has been given
a name at the moment it was created.

### 1.3 The `notes` line on `bordeaux_2026`

`fetch_csv.py:90` already carries the comment *"bordeaux_2026 (505434) lives on
Episode despite the ML x Sonora branding … Do not 'correct' it back by brand."*
Probed and confirmed. Once the brand becomes `Sonora` (1.4), **nothing on the
config row hints that the event fetches on Episode** and that comment becomes the
only guard.

A wrong account returns **zero tickets, not an error**, on a page that renders
perfectly. That is Genève's failure mode exactly. Add the line, and note what it
is: **a fact the file cannot otherwise express.**

### 1.4 The two brand changes — RULED IN THE FIRST BRIEF, NEVER WRITTEN

Not in the names-only cut, and never re-ruled after it, so flagging rather than
assuming: the fiche's MARQUE column says `bordeaux_2026` is **`Sonora`**; the
config still says `ML x Sonora`. `bordeaux_oct_2026` was **already** `Sonora`, so
only one row actually moves. **Nothing about routing changes — the account does
not move.** Confirm with Leo before writing; it is one field but it is the field
1.3 exists to compensate for.

### 1.5 Madame Loyal x Crazy Carnaval — a new event

`ADDING_AN_EVENT.md` is the spec. Two edits: a row per day in
`event_config.csv`, and the event id added to `SHOTGUN_ACCOUNTS['episode']
['events']`.

| field | value | how it is known |
|---|---|---|
| name | `Madame Loyal x Crazy Carnaval` | fiche NOM |
| brand | `Madame Loyal` | fiche MARQUE |
| city | Paris | fiche |
| date | **4 July 2026, ONE day** | fiche |
| capacity | **3 800** | fiche |
| `shotgun_event_id` | **549064** | probe run **32658474632** |
| account | **EPISODE** | same probe, by name |
| `dice_mio_id` | **591517** | `RXZlbnQ6NTkxNTE3` decodes to `Event:591517`; confirmed on DICE as `'Madame Loyal Paris : Crazy Carnaval Edition'` |
| bank | `ML 040726 – MICHELETTY` | fiche bank list |
| `compare_to` | **empty** | reference is "any July event at Micheletty 2025", to be announced. Do not guess a candidate. |
| status | finished | 4 July is past |

The probe, both accounts, verbatim:

```
episode  (org 171835) cohosted=0: 100 tickets on page 1 (more pages: True)
                                 — event_name='Madame Loyal Paris - Crazy Carnaval Edition'
episode  (org 171835) cohosted=1: 100 tickets on page 1 (more pages: True)
sonora   (org 207784) cohosted=0: 0 tickets
sonora   (org 207784) cohosted=1: 0 tickets
```

**`currency` cannot be left empty** — `run.py` reads it as
`row.get('currency', 'EUR')` and `.get()` with a default does **not** fire when
the key exists and is empty.

**Two things about it that are genuinely new**, and one that is not:

- **It is one day**, where every other event is two or three. `presdays()` takes
  it (it iterates `cur_days`), and `build_v2.py:216` already handles the span:
  `if first == last: span = f"le {first.day} …"` → *"événement le 4 juillet
  2026"*. Written in, never exercised. **Exercise it and look.**
- **Both platforms**, unlike SONORA x IMPACT.
- **Already finished is NOT new.** `OVER = JX <= 0` and `bordeaux.html` already
  ships at `jx = -1`. The finished path runs daily. What is new is reaching it on
  the first build.

Its Bil badge on the fiche reads dim — Billetterie integration apparently off.
Leo has seen the fiche and still wants the page. Flagged, not blocking.

### 1.6 The single-day plural

`redesign/mock/dashboard_v3.39.html:1343`:

```
Pass multi-jours    ${nf(PD.multi_day)}<small>× ${PD.days.length} journées</small>
```

On a one-day event that reads **`0 × 1 journées`** — plural noun on one day, and
a row with no meaning on a single-day event. The correct pattern is already two
hundred lines below at **:1630**: `journée${C.refdays.length>1?'s':''}`.

Remember the mock is a **rendering, never a source**, and that the seam's
delimiters (`</nav>`, `</body>`) must **not** be spelled in that file — writing
them in a comment once moved the seam and broke a deviation count.

### 1.7 The day toggle on a one-day event — bring it back as a question

`dashboard_v3.39.html:1279`. With one day, toggling it off gives
`inc = []`, so the hero reads **`0 / 0 entrées · 0% de la jauge · 1 journée
exclue`** with an empty bar — reachable in one tap and indistinguishable from
"no data". Not a crash. **This needs a design answer, not a patch.** Ask.

---

## 2. OPEN — waiting on an input nobody has yet

### 2.1 `poster_url` — the avatar shows the wrong brand

`poster_url` is **empty on all seven active rows**, so `run.py:2081` falls back to
`LOGO_ROND_JAUNE.png` for every page — including `SONORA BORDEAUX OCTOBRE` and
`SONORA x IMPACT`, where Budgetflow shows the Sonora logo. **One app, two
modules, different logos on one event.** Live today.

Blocked on asset URLs Leo has to supply. **Do not invent a path.**

Note the avatar is an `<img>`; the two-letter initials are its `onerror`
fallback and are not normally rendered. An earlier report of a live "SB
collision" between the two Bordeaux events was **wrong for that reason** — it can
only appear if the image fails to load.

### 2.2 Croisière Madame Loyal x Elektric Park — RULED: no dashboard

On the fiche (6 Sept 2026, Paris, 5 000, En vente) with no config row. **The next
person reading the fiche will ask the same question, so here is the answer.**

- **DICE enumerates.** `viewer.events` → `EventConnection`; 200 requested, **85
  returned**, so the whole catalogue and not a page cap. Ids run 91459 (2022) to
  600413 (Rennes, Nov 2026). **No event matches** croisi/cruise/bateau/boat. EPK
  is **one** DICE event — `573271` — not two.
- **Shotgun cannot be enumerated at all.** `/tickets` is a ticket feed ordered by
  `ticket_updated_at`, not an event list.
- **`data/epk_2026_merged.csv` carries 74 `'Pass Festival + Croisiere'`** of
  13 481 — all Shotgun, under EPK's own `535882`, still selling, 57.26–98.09 EUR.
  `resolve_attendance` maps them onto festival days (49 dimanche, 25 2-jours),
  so **they already count toward `epk.html`'s Sunday présence. A separate page
  would double-count them.**

The fiche lists it as an event; the ticketing feed says it is a ticket type.
Both are right about their own domain. `scripts/probe_croisiere.py` re-runs the
whole thing.

### 2.3 Carried forward from `HANDOFF_CC4.md` §8

- **O12** — Shotgun has no pagination-completeness assertion. Blocked on a
  measurement of real refund churn, not on a decision. **Do not pick a tolerance
  before measuring.**
- **O1** — the per-ticket reconciliation against the back-office export is still
  undone. The file is not in the repo and carries buyer identifiers; strip it to
  ORDER ID / PRICE / CLIENT PRICE / PURCHASE DATE / CATEGORY before it goes
  anywhere.

---

## 3. HOW THIS SEAT WORKS

**Leo decides anything visual by LOOKING.** Propose renders, not descriptions. A
paragraph explaining that a label fits is worth less than a 393px screenshot of
it fitting. Chromium is at `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`;
dismiss the login gate with `document.getElementById('db-overlay').style.display
= 'none'`.

**A review seat re-derives every claim from the repo.** Anything stated will be
checked against the artefact, so state only what was measured.

**Say what is unverified when it is.** This is the whole habit. Its two hardest
forms:

- **Name the exclusion in the same breath as "green".** *"30 of 31,
  `check_b1_switch` not run"* is a true sentence and takes no longer to write.
- **A blocker is reported, not worked around.** When the fiche had not reached
  this seat, the right move was to stop and say so — taking the transcribed table
  would have written wrong names into production config.

**Merge on a cadence, not at a finish line.** The bar is two checkable
conditions: the suite is green with exclusions named, and nothing is
half-applied. The open list has not emptied in weeks and will not. **The branch
is not a place work exists, it is a place work is invisible** — Pages deploys
from `main`.

**Resolving a merge:** `python3 scripts/merge_pages.py`. Never text-merge a
generated page; never rebuild by reflex either — `check_build_stamp` decides, and
the script re-freezes the finished editions, which a rebuild silently converts to
a live sync clock.

**Check the PR's draft state before starting a merge.** Main uses **merge
commits**, not squash.

**Do not modify** `run.py` or `dashboard_template.html`. Changes that would land
there go through `postprocess_html.py` on the way past — the established
precedent, and now also how the nav trigger gets its name.

---

## 4. Added to `HANDOFF_CC4.md` §9

Four this session. The first two are about references that have moved and cannot
say so; the last two are about fixes.

### A SCREENSHOT IS A MEASUREMENT WITH NO TIMESTAMP

Three capacities on the fiche disagreed with the config — Rennes 14 000 vs
20 000, EPK 12 000 vs 20 000, Genève 15 000 vs 20 000 — and EPK's read as
**105.7% of jauge, oversold**, against the 63.4% the page shows. It was reported
as a live defect. **The config was right and the fiche was stale**: Leo had
updated those capacities in Festiflow after the screenshot was taken.

The measurement was correct. Only the reference was. Same family as the stale
local ref and the v6.4 package: **an artefact that has moved and cannot tell you
when it was true.** Ask for the timestamp, or say the comparison is undated.

Stopping was still right. Had the fiche been current, the alternative was a page
claiming 63% of a jauge it had already exceeded.

### NEVER PRINT AN UNFINISHED READ AS AN ABSENCE

`probe_croisiere.py`'s first run reported **`1 distinct event(s)`** per Shotgun
account. That was its own 8-page cap — 800 tickets is not enough to leave the
first event — not a property of the accounts. Reported as a finding it would have
been the exact silent-truncation shape `fetch_shotgun_pages` raises on: **a
smaller, entirely plausible number with nothing marking it short.**

A read that stopped early must say so, and an unfinished read is never evidence
that something is absent. Its sibling: **"not in this list" means "not under this
token"** — DICE's 85 events exclude Genève and every Sonora event, and both
demonstrably exist.

### THE BETTER FIX MAY BE TO STOP CONSULTING THE DERIVATION, NOT TO STATE THE VALUE

`event_name` was put through `split(' 20')[0]`, a case-sensitive prefix list and
an 18-character cap to make a nav trigger name. On the new names that produced
**"Madame Loyal" for three of seven pages** — each losing its city into a shared
brand.

The first ruling was right by this project's own pattern: replace the derivation
with a stated short-name column, the way `D.id`, `page_names()` and
`pass0_dir()` each replaced a derived guess with a stated fact.

**The measurement made a better answer visible.** The full name *fits* — 334px of
393 at the worst case, 59px spare — so the trigger reads `event_name` verbatim
and the derivation is not consulted at all. No new column, no seven strings for
two people to keep in step, and the module it must agree with agrees **by
construction**. That option only appeared after measuring the thing everyone
assumed did not fit.

### A RULE THAT LOOKS HALF-APPLIED MAY CORRECTLY BE TWO RULES

The follow-on instruction was *"three renderings, one rule"*, and it was wrong.
`event_name` has six reader-facing renderings; five now take it verbatim and
**one still splits on `" 20"`** — the reference label at `build_v2.py:285`.

That one must. Its template is `{stem} ${YR}`, and `ref_label` is an **archive**
row's name — `Rennes 2025`, `Elektric Park 2023` — which already carries a year.
Unifying it renders **"Rennes 2025 2025"** on every page with a reference.

The rule is not "one column, one rule". It is: **a rendering that supplies its
own year splits; one that does not, does not.** Two rules because there are two
shapes of input. It is commented in place, because to the next reader one derived
consumer among five verbatim ones looks exactly like a missed edit.
