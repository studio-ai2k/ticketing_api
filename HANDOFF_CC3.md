# Handoff to CC3

## 0. State, so you start from a known one

**`3e6c104` is the last pushed tree on `main`. It is green at 16 checks. Nothing
is half-done. Nothing is waiting on Leo except one figure (§7).**

Nothing about `exact_date` has been touched. The defect described in §1 is
exactly as diagnosed and is live on all six pages today.

Run the suite first anyway — not because it is expected to fail, but because a
handoff that says "green" is a claim about a tree you have not seen:

```
NODE_PATH=/opt/node22/lib/node_modules python3 verify/<name>.py
bash verify/assert_redesign.sh
```

Read `verify/CHECKLIST.md` for the full list. Everything in `verify/` carries its
own reasoning in its docstring; that is where the "why" lives, not in commit
messages.

---

## 1. THE JOB IN FLIGHT: `exact_date` is broken and has always been

### What is wrong

The Suivi card offers three anchoring modes. `exact_date` — labelled
`Date exacte`, `même J−x, date à date` — does not do date-to-date matching. It
does raw J−X matching with the weekday snap turned off, which is a third thing
that is neither of the two the label names.

On `bordeaux_oct` it renders **the same table as `Jour J`**. The reference column
reads 24 August 2025 against our 9 August 2026, where date-to-date should read
9 August 2025.

```
bordeaux_oct  event 2026-10-17, jx 68  ->  today 2026-08-10
halloween_2025 event 2025-11-01        ->  G = 350
  current (off = 0):   ref jx 68  ->  2025-08-24
  calendar match:      ref date 2025-08-10  ->  ref jx 83
  required offset:     -15
```

The label contained its own contradiction from the start —
`{k:'exact_date', n:'Date exacte', d:'même J−x, date à date'}` — and nobody read
it, through a spec, an implementation, a mirrored client, and a check that
covered the mode 198/198 green.

### Why it survived

Because of a spec that said the snap being off *was* the calendar match. It is
not: turning the snap off gives raw J−X. The conclusion did not follow from the
premise, and both were written down as one sentence.

**Read §6 before you write any of the copy. This mode produced five defects and
none of them existed until someone tried to write the sentence describing what it
does.**

---

## 2. THE DESIGN — accepted, complete, not built

### The four formulas

```
daily    jr(jx) = (cand_ev - calBack(cur_ev - jx, N)).days
weekly   w(jr)  = (cur_ev - calFwd(cand_ev - jr, N)).days // 7
labels   the reference week's span uses calFwd too
cut      cutAt  = jr(D.jx)

calBack(d, N) / calFwd(d, N) = same month and day, N years back / forward
                               29 February -> 28 February
N = cur_ev.year - cand_ev.year, asserted >= 0
```

`j_minus` and `days_since_launch` are **unchanged**. Their offsets are exact
constants, not incidental ones. Only `exact_date` becomes a date operation,
because a calendar match *is* a date operation and a constant offset is an
approximation that holds only while no 29 February intervenes.

### Why per-row rather than a constant offset plus an assertion

This was ruled after being got wrong once, and the reasoning matters more than
the outcome:

A constant offset was proposed, guarded by a hard assertion that it stays
constant across a page's row range. That assertion would have gone **red today on
20 unreachable pairs** — all 2024 editions, all straddling 2024-02-29, all
invisible only because `build_series` emits no 2024 series. That left two exits,
weaken the check or delete config rows, both of which are the failure modes this
project exists to prevent.

> The single-`off` architecture was never right for calendar matching; today's
> data was hiding that, and the assertion would have been guarding an accident
> rather than a rule.

Per-row makes correctness structural. Nothing can be non-constant, so there is
nothing to assert, and the 20 violations stop existing rather than being
tolerated.

### The by-construction property — keep it, it is the strongest part

Mapping the reference row **forward** N calendar years and bucketing by our own
`jx` makes the reference's weekly bucket equal ours on every row. The two grains
cannot disagree about what the mode means, because they are one date operation
rather than two rules kept in step.

Verified on `bordeaux_2026` vs `bordeaux_2024` (which straddles 2024-02-29):
`per-row w == ours w` on all 158 rows.

### Evidence that the weekly grain needs it too

A single `wshift` taken at the cut row mis-buckets **7 rows**, one per week,
always the week's boundary row:

```
bordeaux_2026 vs bordeaux_2024   cut row jx=89 -> off=-2 -> single wshift=2
   jx=111  2026-02-22  jr=114   ours w=15   single->16   per-row->15
   jx=118  2026-02-15  jr=121   ours w=16   single->17   per-row->16
   jx=125, 132, 139, 146, 153 — same shape
CONTROL bordeaux_2025 (no straddle): 0 rows differ
```

The control run is not decoration. Without it the 7 means nothing — see §6.

---

## 3. THE FIVE READERS OF THE OFFSET

The count went **4 -> 5** while files were being opened for the refactor, which
is why they are listed with line numbers. It would have gone wrong mid-refactor.

### Server — `scripts/dashboard_payload.py`

| line | reader | note |
|---|---|---|
| 367 | `m = day - timedelta(days=offset)` in `daily_rows` | a **date** subtraction, so per-row is a local change: pass a function of `day` |
| 431 | `w = ((ref_ev - d).days - wshift) // 7` | the weekly bucket |
| 447 | `if ref_cut and keep and w >= 0:` | **DECIDE, DO NOT INHERIT** — see below |
| 473 | `sb = ref_ev - timedelta(days=wshift + (w+1)*7 - 1)` | the label span, the fourth reader |
| — | `cutAt` / `ref_cut` | the cut |

`anchor()` at 297 returns `(offset, wshift)` and for `exact_date` currently
returns `(gap, 0)` — which expands to `jr = jx`, the defect.

**Line 447 is the one to decide.** Its own comment says `w >= 0` only bites once
`wshift` is non-zero. Under a per-row calendar offset it starts biting in
`exact_date` too. That is the same shape as `jr >= 0` and the weekly `w >= 0`,
both of which were correct by accident until an assumption moved, and both of
which shipped wrong numbers before being found. Do not carry it across without
deciding what it should do.

### Client — `redesign/mock/dashboard_v3.39.html`

The client half is the harder one. Named because that only became clear on
opening it:

- `anchorOf(s)` — returns `{off, wshift, cutAt}`
- the daily loop — `const jr = r.jx - off;`
- the weekly loop — `const w = Math.floor((jx - wshift) / 7);`
- `span(evd - wshift, w)` — the week labels

The client and server are mirrored deliberately and `verify/check_b1_switch.py`
drives both. A change to one without the other is caught, but only after the
fact — do them together.

---

## 4. WHAT ELSE THE FIX MUST CARRY

### (a) N = 0 is five of eleven candidates on every page, and it splits in two

`calBack(d, 0)` is identity, so exact-date against another **2026** edition
compares the same calendar day in both campaigns. That is coherent and probably
the most useful comparison the page offers — two live campaigns side by side on
the same day — and those candidates sit at the top of the menu under
*Événements en cours*, so it is the branch a reader meets first.

But it splits:

```
page          candidate            N   our jx     jr   cand lead
rennes_2026   bordeaux_oct_2026    0       89     68        106   ok
rennes_2026   epk_2026             0       89     27        156   ok
rennes_2026   geneve_2026          0       89     68        163   ok
rennes_2026   bordeaux_2026        0       89    -58        156   NO ROW
rennes_2026   paris_xxl_2026       0       89   -149        101   NO ROW
```

**Ten reachable pairs have no overlap at all** — `bordeaux_2026` and
`paris_xxl_2026` from each of the four live pages. Their events are already past
(`jx = -1`, `-2`), so "the same calendar date" falls after their event and no such
row exists. The existing `jr >= 0` bound would render the entire reference column
as em-dashes: correct, and a plausible-looking empty table, which is the failure
shape this project keeps finding.

**Empty state, and name the side that ran out:**

> « Paris XXL 2026 s'est terminé avant le 9 août »

not a generic "aucune donnée". The reader must be able to tell a finished
candidate from a fetch that failed. A generic empty is the plausible-empty-table
shape one level up.

### (b) `N >= 0`, asserted

Zero candidates today have a later event year than their page. Unreachable, and
therefore exactly the profile of `jr >= 0` and the weekly `w >= 0`. Bound it
before the data can reach it rather than after.

### (c) The three Suivi sentences

The Suivi alignment note is being rewritten from a statement about system
behaviour into a live description of the current comparison, driven by `CSEL` and
`AMODE`. Sense, not wording — the wording is Leo's and he rules by looking:

```
j_minus            Rennes 2026 vs Rennes 2025, alignées sur la date d'événement :
                   J−89 contre J−89.
days_since_launch  … alignées sur l'ouverture des ventes : jour 68 de campagne
                   contre jour 68. Ce sont les débuts de campagne qui se
                   correspondent, pas la date d'aujourd'hui — les tirets en bas
                   de tableau sont donc normaux.
exact_date N>=1    … alignées sur la date calendaire : 9 août 2026 contre
                   9 août 2025.
exact_date N=0     … alignées sur la date calendaire : le 9 août 2026 des deux
                   côtés.
exact_date N=0,
  finished cand    no sentence — the empty state of (a)
```

Already ruled and already landed: the note's **11px bottom margin** (`3e6c104`),
read from `.sec-head{margin-bottom:11px}` rather than chosen. Already ruled and
**not** landed: the copy above, held until `exact_date` is real, because one of
its variants is currently a false statement.

Also agreed: drop the old "both grains move together" sentence entirely rather
than moving it to the tooltip. It answers a question only reachable by noticing a
disagreement that can no longer happen.

`D.name` must be added to the payload from `event_name` for these sentences. The
mock's own event name is an identity literal that pass 0 asserts matches
**exactly once**, so a second occurrence fails the build. `D.family` will not do:
it is title-cased from the id and renders `Paris Xxl`.

### (d) The spec amendment — not optional

`redesign/reference_suivi_candidates.py` states that the weekly grain uses no
offset and each side buckets by its own event date. Under `exact_date` the
reference is bucketed by **our** event date. That is correct for a calendar
comparison and it is a departure from the document that has been the authority on
the weekly grain all project.

Amend it in the same commit as the code, and put the reason in the file itself:

> A spec that disagrees with the code is how the 13,03% conflict survived the
> whole life of the project.

### (e) `check_b1_switch` — RE-DERIVED, NOT ADJUSTED

It currently asserts that `j_minus` vs `exact_date` differ on **21 of 45 daily**
rows and **0 of 45 weekly**.

**Both numbers are properties of the broken mode.** 21 is the non-zero-snap
count; 0 is what you get when `wshift` is 0 on both sides. They will change.

Re-derive them from the new rule. **A number nudged until the check goes green is
the precise failure this instruction exists to prevent**, and it would be
invisible afterwards.

### (f) The negative test — on `bordeaux_oct`

Assert the three modes are **distinguishable** on a page where the snap is zero.
`bordeaux_oct`'s gaps against five of its six candidates are exact multiples of 7
(350, 490, 1141, 343, 581), so `smod7(G) == 0` and the broken mode was
indistinguishable from `j_minus` there. That was reported to Leo as a coincidence
of dates. It was not a coincidence — it was the mode not doing anything.

That page is where this hid. It is where the test belongs.

---

## 5. THE QUEUE AFTER `exact_date`

1. **The Suivi note copy** — §4(c), held on `exact_date`.
2. **Control labels on both cards.** Each dropdown gets a title above it and the
   pair stacks: `Événement comparatif` / `Méthode` on Projection,
   `Événement comparatif` / `Alignement` on Suivi. Same first label because it is
   the same choice; different second because Projection picks how the forecast is
   computed and Suivi picks how the editions are lined up. The four
   `.cmp-eyebrow` labels (`réf.`, `scén.`, `vs`, `aligné sur`) come out — with a
   title above, they say it twice. Try `.kc-k` before writing any rule: it is the
   existing uppercase letterspaced `--text-dim` key label used above every KPI
   value, which is the same relationship. **Check it against a render rather than
   asserting it fits; if it misses something, name the property.**
   Costs height deliberately — Leo's complaint was that the card looked empty,
   not tall. Measure head height at 393 and desktop on both cards and confirm no
   horizontal overflow.
   Removing the eyebrows may resolve the `réf.` truncation at 393 without
   touching copy; if the long `Trajectoire Elektric Park 2023` form then fits,
   the copy question disappears instead of needing a ruling.
3. **The column header conflict**, now at three variants: `2025 (MÊME JOUR)` is
   wrong under launch alignment (same campaign day, not same day) and worse under
   exact-date N=0, where it reads `2026 (MÊME JOUR)` against `2026 (ACTUEL)` —
   two identical years labelled as opposites. The header names one alignment
   while the picker offers three.
4. **The source-order check.** Priced and approved, no allowlist. 47 selectors
   are overridden at a breakpoint; a `@media` rule that precedes its base rule at
   equal specificity is silently defeated. 7 flags, 0 property-level false
   positives when last measured. **Word the failure so it says "this rule does
   not take", not "the page is wrong"** — 2 of the 7 are defeated but a later
   media rule re-supplies a mobile value, so nothing renders wrong. Three of the
   seven are already fixed (the `.ck-*` deletions in `08fc06c`).
5. **The duplicate-declaration question**, raised separately and probably
   cheaper: `.dgrid` has two base declarations (L386, L592) and `.card`'s mobile
   padding is set in two media blocks. Third duplicate-declaration find in one
   sheet after `--fs-display`. Worth asking whether the sheet wants a
   one-declaration-per-selector-per-condition assertion.
6. **The two audit checks**, ruled to run before cutover and nothing else:
   the Shotgun `deals` probe (~½ day) and **pagination completeness** — the more
   important of the two, because a truncated fetch produces a smaller, entirely
   plausible number and nothing asserts against it.
7. **Pre-work P1–P3, then cutover per `CUTOVER.md`**, then a green run, then the
   cleanup commit with `legacy/`.

`AUDIT_SCOPE.md` has the full audit picture. `CUTOVER.md` §3(b2) records that the
7.0 version bump is **two** places, not one.

---

## 6. THINGS THAT WILL NOT BE OBVIOUS FROM THE CODE

### The probe habit — the most transferable thing here

**Every check in `verify/` gets negative-tested before it is trusted. The
throwaway measurement scripts did not, and that is backwards.**

Three probes failed in one session, all three toward passing, two caught by the
reviewer rather than by me:

- a float-clamp probe that read the same box five times and reported five passes
- an element screenshot that came back 369px wide and stacked, reading as a
  broken footer, when the element measured 980px and correct
- a leap-day scan that reported **0 pairs vary** having tested **nothing**:
  `on_sale_date` is blank for every row in `event_config.csv`, so
  `if cur not in lead: continue` skipped every pair

That last one is the point. **A check that wrongly passes hides a defect. A probe
that wrongly passes creates a ruling.** "0 pairs vary" was one message from
becoming an architecture.

The habit, which costs nothing: **before quoting a probe's number, run it once
against a case that must violate. If it reports zero there too, the probe is
empty.**

### The same habit, generalised: state the claim you are making

A probe, a watcher and a measurement all state a claim, and **the claim they
state must be the one you are making.** Four instances in one session:

- a watcher on "main moved" when the question was "did the BOT commit" — it
  tripped on my own push and read as the pipeline recovering
- a watcher comparing against a 40-char SHA whose tail I invented rather than
  captured, so the inequality was true on its first iteration and reported
  success instantly
- a width sum over both children of a row whose entire point is that they sit on
  SEPARATE rows, reporting "OVERFLOWS by 37" for a layout that fits with 84px
  spare
- an expectation table asserting a CSS selector sat on L9 when the fixture I had
  retyped put it on L11, reporting "4/6 correct" for a parser that was right on
  all six
- `grep -c 'dashboard_redesign.css\|dept-tabs-bg'` offered as proof that a
  rebuild had written a v2 page over a production one. `dept-tabs-bg` is in a
  CORRECT production page twice, and `dashboard_redesign.css` is in a v2 build
  zero times because pass 0 inlines the sheet. The count was 2 either way

None of these was a wrong answer to the right question. Each was a right answer
to a question adjacent to the one being asked, which is worse, because the
number looks fine and nothing about it invites a second look.

The fifth is the one that shows the pattern is not only about verdicts. The bug
it "proved" was REAL - confirmed afterwards with markers that do discriminate
(`const D=` 0 -> 1, the build stamp 1 -> 0). Only the evidence was unsound. A
right conclusion resting on a wrong measurement still has to be corrected,
because the measurement is what the next person re-runs, and it will not
reproduce.

**AND THE DIRECTION IS NOT SOMETHING YOU GET TO ASSUME.** Two of the five failed
toward a false green — the watcher read a dead pipeline as recovered. Two failed
toward a false defect — the width sum condemned a layout with 84px of room, and
the expectation table condemned a parser that was correct. Acting on either of
the last two would have broken working code, which is the failure mode that does
not announce itself as a failure: you are looking at a number that says
something is wrong, and being wrong about that feels exactly like being right.

So "measurements fail safe" is not the lesson and cannot be leaned on. The
lesson is narrower and holds in both directions: a measurement adjacent to the
claim will send you somewhere, and which way is a property of the mistake, not
of the fact that you made one. When a probe says a thing you believe is broken,
that is the moment to check the probe — not only when it says everything is
fine.

The probe habit says run it once against a case that must violate; this is the
same move applied to the predicate rather than the data — **if your check cannot
distinguish your own action from the event you are waiting for, it has not been
tested at all.** That is the same move as "a negative test on the pair where the effect is
smallest cannot fail", applied one level earlier. The `bordeaux_2025` control run
in §2 is what makes the 7 mean something.

### The copy is what tested the code

`exact_date` produced five defects and **none of them existed until someone tried
to write the sentence describing what the control does**. It shipped green and
meaningless for weeks — through a spec, a mirrored implementation, and a check
reporting 198/198.

The generic line it is replacing — "the alignment applies to both grains" —
could never have failed, because it made no claim the table could contradict. The
new line says "9 août 2026 contre 9 août 2025" directly above a table showing
24 août, and the contradiction is visible to anyone.

**Write the sentence early. It is a test.**

### The seam, and its five casualties

Pass 0 splices the mock's body into a `run.py` page. The seam runs from the nav
close to the body close. Anything that lives inside that region and belongs to
production goes with the body and is silently lost. Five components so far: the
nav markup, the sw-block export, the section bar, the finished-edition guard,
and the page footers.

When something is missing from v2 that exists in production, check the seam
first.

### A comment inside a scanned artefact is not inert

A CSS comment explaining the seam contained a literal `</nav>`. The sheet is
inlined into the page, and `check_v2_identity` locates the nav by searching for
that exact string — so it landed in the comment and stopped excluding the session
switcher. Five pages reported a foreign identity that was a control working
correctly.

Narrow rule, worth knowing: **if a check scans an artefact by string, comments
inside that artefact are part of the haystack.**

### Two live rules can be wrong where they meet

Ruling §1 stopped a finished edition from rendering forecast figures. C4/E gave
the projection header its pickers. Each was correct alone; together, a finished
edition kept two controls over a forecast that no longer rendered. Not a stale
premise — two live rules meeting at a case neither anticipated.

### The ledger's four known weaknesses

`verify/check_mock_deviations.py` holds the working mock to the locked one in both
directions. Four things it cannot do, all recorded in its own entries:

1. A locked→working pair **cannot hold two edits to one line** (`C1a`, and again
   at `C3-identpill`, resolved there only because the two rulings happened to be
   about different parts of the line).
2. A signature authorises a **hunk**, and difflib decides how big a hunk is. The
   line budget exists to bound what a signature can smuggle in with it.
3. The budget counts added and removed **lines**. A modification to an
   already-added line changes neither, so it is invisible to both the signature
   and the budget. Hit twice in `3e6c104`; both edits got their own entries,
   which closes it for those two and not in general.
4. Hunk boundaries move when neighbours change, so an entry's matchability once
   depended on its neighbours. Fixed by searching both sides of the diff.

**The boundary that makes these acceptable: never split a CSS line to give an
entry its own diff.** The sheet's formatting is not yours to change for the
convenience of the checker.

### Standing constraints

- **Do not modify** `run.py`, `dashboard_template.html`, `upload.html`,
  `main.py`. `event_config.csv` only where explicitly authorised.
- **Pure Python stdlib** for the fetcher. Zero pip dependencies.
- **No row-level personal data persisted, ever.** Aggregate at fetch time. The
  repo is public and this is the April incident's lesson.
- **Capacity comes from config**, never from `totalTicketAllocationQty`.
- Any query reading `optInPartners` selects **that field alone**.
- **The mock is the authority on design.** Search it before building; if a
  pattern is genuinely absent, ask rather than invent. Every CSS deviation is
  logged in `AUTHORISED_CSS` with a ruling and checked in both directions.
- Colour divergences between the two modules are **deliberate and out of scope**.
- The password gate is client-side only (`festipass`, in plaintext, public repo).
  Leo has deferred the fix. Do not change repo visibility without his go-ahead.

---

## 7. NOT YOURS TO MOVE

**The Shotgun 13,03% payout multiplier.** Open the whole life of the project,
waiting on a payout statement only Episode or Sonora can produce.

It is now **priced**, which it was not before, and the price is the thing to hand
to Leo:

```
Shotgun face TTC, six events        3 844 502
fee shown now                         500 210
if the spec (1.030) is right           115 335   overstated by 384 875
if ~11% is right                       422 895   overstated by  77 315
displayed fee segment, all six pages   623 092
  DICE, proved against a statement       122 882
  Shotgun, unverified                    500 210   = 80,3%
```

**Paris XXL alone: one bar segment that could be wrong by 142 033 €.**

And the scope is narrower than three weeks of "it sits under every Shotgun
figure" suggested — that was wrong, ours included. `totals()` computes `rev` and
`avg` from `price` (face value). `gross_price` reaches the payload only as
`plat[2]`, read by `moneyBar()` and the "Prix affiché → net encaissé" bar, both
for `fee = paid - face`. **It touches one visual element. No decision anyone makes
from these dashboards moves.**

Already shipped (`3e6c104`): the Revenus tooltip declares it —
« Les frais DICE sont confirmés par un relevé de versement ; les frais Shotgun
sont dérivés des données de la plateforme et n'ont pas été confirmés. »

---

## 8. WHAT IS LOAD-BEARING AND UNVERIFIED

Stated plainly because a handoff that presents everything as settled is less
useful than one that says where to be careful.

1. **The whole `exact_date` design in §2 has never run.** The formulas are
   derived and the weekly evidence is measured, but no line of it is implemented.
   Treat the four formulas as a specification to test, not a result.
2. **`N = 0` against a live candidate has never been rendered.** The `jr` values
   are in range and the arithmetic is checked, but nothing has drawn that table.
   It is five of eleven candidates on every page and the first branch Leo will
   meet.
3. **The 20 straddle pairs are unreachable today and that is the only reason the
   old architecture looked sound.** They become reachable the moment
   `build_series` emits a 2024 series — an eligibility rule this project has
   already widened once. Per-row removes the exposure; if anyone proposes going
   back to a constant offset, this is the reason not to.

Beyond those three, the numbers in this document were measured rather than
reasoned, and the ones that came from probes have a control run behind them.
