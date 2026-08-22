# Handoff to CC4

## "GREEN" MEANS THIS LOOP. It does not mean a list someone typed.

```bash
# Every check that EXISTS, enumerated from disk. ~12 minutes. Silence is green.
# The four skipped take a page argument and run inside assert_redesign.sh.
SKIP='check_login_bg check_platform_cards check_section_amber check_stampable'
for f in verify/check_*.py; do
  n=$(basename "$f" .py)
  case " $SKIP " in *" $n "*) continue;; esac
  timeout 600 python3 "$f" >/dev/null 2>&1 || echo "RED  $n"
done
bash verify/assert_redesign.sh >/dev/null 2>&1 || echo "RED  assert_redesign.sh"
```

**The `cutover.py` dry run is NO LONGER PART OF THIS LOOP, and putting it back
would make the loop permanently red.** It was here while the cutover was
pending. Post-cutover `v2/` does not exist, so the dry run refuses with
`cutover: v2/ is missing …` and exits 1 — which is the tool declining to perform
its own irreversible step a second time, i.e. correct. `check_cutover_write.py`
asserts that refusal and IS in the loop above, so the property is still covered;
what is gone is a line whose failure meant success.

**This is first because it is the reason `check_v2_behaviour.py` sat red for two
sessions on a tree three handoffs in a row called green.** It was red from the
moment ruling C4 shipped, on all four live editions, and nobody saw it because
the previous version of this section named three commands and none of them was
that one. A list is a claim about which checks matter, written by someone who is
about to stop looking at them.

`check_b1_switch`, `check_v2_behaviour`, `check_v2_gate` and `check_selector.js`
drive a browser; `check_float_clamp` rebuilds every page. Run it before
believing any statement in this file, **including this one.**

### NAME WHAT YOU EXCLUDED, IN THE SAME BREATH AS "GREEN". EVERY TIME.

`check_b1_switch` takes ~30 minutes, so it is tempting to drop it from the loop
while iterating. That is fine. Reporting the result as **"suite green"** is not.

It happened here: the check last ran at `9bdb3e8`, and then FIVE changes landed
on markup it exercises — the `.sv-solo` layout, the À-venir header, the Présence
card, the payload assertions, the module switcher. Every intermediate report
said "suite green (excl b1_switch)" in a parenthesis and "green" in the prose.
Both were true of the thirty checks that ran and silent about the one that did
not. **It cost nothing, and that is luck rather than evidence** — the check went
green when it finally ran, and had it not, five changes would have been sitting
on main.

This is §0's own rule turned on the seat that wrote it: green means THE LOOP.
A subset is a subset however carefully it was chosen.

> **"30 of 31, `check_b1_switch` not run"** is a true sentence and takes no
> longer to write than "green". Write that one.

And before a merge, the exclusion list must be empty or justified out loud: a
docs-only change need not re-run the browser checks, but saying so is the point,
not skipping it silently.

Three things worth knowing before you do:

- `bash verify/assert_redesign.sh` takes **no argument**. It resolves where pass
  0 publishes, like every other page check (§6.3). `.` meant production, which
  is no longer what this gate asserts.
- `python3 verify/check_page_anchor.py` is the one to read first if the gate is
  red — every absence assertion in it is vacuous on a page that fails the anchor.
- `python3 verify/check_login_bg_wiring.py` **writes `event_config.csv` and
  restores it**, asserting the sha256 afterwards. If it is interrupted, check
  `git status` before anything else.

---

## 0. State, so you start from a known one

**Confirm the tree with `git ls-remote origin main`, never a local ref.** A
stale local `main` at `273457f` is an unrelated "Add files via upload" root that
DELETES the whole `verify/` suite; CC3 hit it and so did CC4. The real
`origin/main` carries all six root pages, `v2/`, `verify/` and `scripts/`.

**The cutover has NOT happened. It was attempted twice, both attempts rolled
back cleanly.** Production is the old pipeline: root pages carry
`<!-- shared:… -->` and production markup, `v2/` holds six pass-0 pages. Nothing
is half-landed.

As of CC4's last commit the loop above is green — 30 checks, the gate, and the
dry run, zero red. That statement is worth exactly one re-run.

Run them first. Not because they are expected to fail, but because a handoff
that says "green" is a claim about a tree you have not seen.

Read `CUTOVER.md` and `HANDOFF_CC3.md` §6 before touching the cutover.

### MERGE ON A CADENCE, NOT AT A FINISH LINE

**Merge whenever the suite is green and nothing is half-applied.** Not when the
work feels complete, not when the open list is short.

FOUR TIMES work has sat unmerged long enough for Leo to notice it missing — the
cutover itself, the SONORA page, the module links, and the scratch-file removal.
Every time the reason was the same and sounded responsible: one more thing to
verify first. Every time the cost was real and one-sided — **the branch is not a
place work exists, it is a place work is invisible.** Pages deploys from `main`;
until the merge, Leo is looking at the previous state and being told about this
one.

The open list has not emptied in two weeks and is not going to. It currently
holds option 2, `preview/`, the untested partial-write rollback, ~700 lines of
dead transformation, the nav divergence and the archive's unasserted provenance.
None of them blocks a deploy and none of them ever will; they are the permanent
backlog of a live system. Waiting for it to clear is waiting for something that
does not happen.

The bar is two conditions, both checkable in a minute:

1. the suite is green, with any exclusion NAMED (see the loop above), and
2. nothing is half-applied — no edit landed without its rebuild, no shared asset
   changed without the pages that stamp against it.

If both hold, merge. A follow-up is cheap; an invisible fortnight is not.

### RESOLVING A MERGE: `scripts/merge_pages.py`, NOT A REBUILD BY REFLEX

Merging `origin/main` conflicts in every generated page, because both sides
regenerated them. The rule is unchanged and right: **a generated page is never
text-merged.** What was wrong was what came next — taking a side and then
rebuilding all seven, every time.

**That rebuild was unnecessary every time and produced junk every time.** The
footer carries `Données API · HH:MM` from the build clock, so a rebuild moves it
whether or not anything else changed. Twice it left five staged files whose
entire diff was footer timestamps and the build stamp, and twice they were
discarded BY HAND afterwards. Hand-cleanup after every merge is the shape where
one day the junk is committed instead — which is exactly how
`_before_rennes.html` reached `main`.

The question the rebuild was answering already has a check.
`check_build_stamp.py` compares each page's stamp against the hash of
`V2_SHARED_ASSETS`, so:

| stamp | meaning | action |
|---|---|---|
| matches | the incoming pages are already correct | **do not rebuild** |
| differs | a shared asset moved on this branch | rebuild — the clock moving is incidental to a change that had to happen |

```bash
python3 scripts/merge_pages.py          # resolve + decide + re-freeze
python3 scripts/merge_pages.py --check  # report only, exit 1 if a rebuild is due
```

Both directions measured: on a current tree it declines and exits 0; with one
line appended to `dashboard_payload.py` it reports all seven stale and exits 1.
It re-freezes the finished events either way, because a rebuild converts
`Données figées · DD/MM` into a live sync time silently.

### AND CHECK THE PR'S DRAFT STATE BEFORE STARTING A MERGE

Twice now a merge has failed at the last step with
`405 Pull Request is still a draft`, because these are opened as drafts by
convention and nobody marked them ready. It is not a problem — one call fixes
it — but it is discovered at exactly the moment everything else is finished,
which is the worst time to find anything. Mark it ready when you open it, or
check before you start.

---

## 1. THE FINDING THAT MATTERS MORE THAN THE TWO BUGS

**`CUTOVER.md` §5 describes the PAGES thoroughly and the CHECKS not at all.**

Both cutover attempts were stopped by something the plan did not list. The plan
had been reviewed repeatedly, by the build seat and the judging seat, and
approved twice. The failure is not that §5 is thin; it is that everyone was
**checking the work against the plan rather than the plan against the artefact.**

### The rule, stated so it can be applied

> **Every check is an artefact the cutover changes.** §5 must enumerate them the
> way it enumerates pages. Anything that reads production markup, production
> paths, or production's asset set is in scope and needs a stated post-cutover
> form BEFORE the cutover runs.

Concretely, that means going through `verify/` file by file and answering, for
each: *does this read the shape of the pipeline being retired?* The two that
bit are below. **Do not assume they are the only two** — that assumption is
exactly what produced this handoff.

---

## 2. P4 — rewrite `assert_redesign.sh` for pass-0 markup. THIS BLOCKS CUTOVER.

The gate is ~400 lines asserting **production's** markup shape. Run against
pass-0 pages it fails immediately:

```
FAIL  .ac-body missing
FAIL  Space Grotesk missing — style block not swapped?
FAIL  literal font-size:Npx present (3)
```

Those are not defects in the new pages. They are the gate asserting the shape of
the thing being retired, against the thing replacing it.

**This is real work, not a tweak.** It needs the same standard as everything
else here: its own before/after evidence, per `verify/CHECKLIST.md`'s "make it
fail" rule. Write it against a pass-0 page, prove it fails on a production page
and on a deliberately broken pass-0 page, and record both.

Two things already true and worth reusing:

- The page list is already config-derived (`scripts/pages.py`), so the gate
  enumerates correctly on both sides of the cutover with no edit. That part is
  done.
- `check_mock_deviations` already asserts pass-0 markup against the locked mock
  and the ledger, and it PASSED on the cutover artefact. Much of what the gate
  should assert post-cutover may already live there. **Measure the overlap
  before writing 400 new lines** — the answer may be that the gate shrinks
  rather than grows.

---

## 3. The version-bump ordering — one ordering fixed, its twin missed

`scripts/postprocess_html.py` is in `build_v2.V2_SHARED_ASSETS`. The cutover
bumps `DASHBOARD_VERSION` from `'6.8'` to `'7.0'` **in the same write plan as the
pages**, so every page ends up stamped against the pre-bump asset set:

```
pass 0: 11 shared asset(s) hash to 8f54ebb8db3d
FAIL  parisxxl.html: built from shared assets eac8f37bfef8, not 8f54ebb8db3d
```

**The bump must precede the build**, exactly as the `PAGE_PATHS` edit now does in
`scripts/cutover.py` (`--apply` writes the `build_v2` edit, THEN builds, THEN
asserts the raw output). The fix is to move the two version writes into that same
pre-build step and recompute `predicted_stamp()` with both edits applied.

This is the second instance of one shape: **an edit to a shared asset must land
before the build that stamps against it.** I fixed the first and did not look for
the second. Check whether there is a third — anything in `V2_SHARED_ASSETS` that
the cutover touches:

```
style/dashboard_v6_8.css        scripts/postprocess_html.py   <- bumped
style/font_links.html           scripts/build_dashboard.py
dashboard_template.html         run.py
redesign/mock/dashboard_v3.39.html
redesign/style/dashboard_redesign.css
scripts/build_v2.py             <- edited
scripts/build_series.py         scripts/dashboard_payload.py
```

Two of the eleven are touched. Satisfy yourself that is all.

---

## 4. What is ALREADY PROVEN — do not rebuild it

| thing | evidence |
|---|---|
| `--apply`'s write path | edit → build → assert **raw**. Six pages `1 stamp + clock-only, 0 ../` on the second attempt. No modelling anywhere in the write path. |
| `verify/check_cutover_write.py` | T1 real edit → PASS; **T2 edit made a no-op → FAIL: 5 `../`**. T2 reproduces the exact state the first attempt shipped, and it breaks the EDIT rather than the page, so it cannot pass by sharing a code path with what it checks. |
| `pages.pass0_dir()` | resolves `v2/` while it exists, root after. All fourteen page checks correct on both sides with no flag-day edit. |
| `check_build_stamp` | audits the sets that EXIST — two now, one after cutover. The production half is not constructed rather than skipped. |
| the dry run | provenance hashes taken before any banner; predicted stamp computed from `build_v2.py` as the cutover leaves it; per-page diff asserted at character level (two footer lines may differ **only in digit runs**). |
| atomic rollback | both attempts rolled back with `git checkout -- . && git clean -fdq legacy preview`, restoring six v2 pages and production-shaped root pages. Verified green after each. |

`scripts/cutover.py --apply` also **refuses** while the workflow still builds to
`v2/`, on a clean-tree precondition, and on an edit site that does not match
exactly once. All three fire.

---

## 5. The timing rule

**Run `--apply` immediately AFTER a scheduled push, never before one.**

The schedule is `0 */4 * * *` but GitHub delays each run by up to an hour —
observed starts 00:57, 05:22, 08:59, 12:2x. So the clock does not tell you when
the window is. Watch for the `Auto-update dashboards` commit to land, then go;
that buys ~3h50m clear.

If a scheduled run lands mid-apply, `origin/main` moves, the push is rejected,
and `legacy/README.md` ends up recording provenance hashes for pages that were
superseded seconds later — wrong provenance in the one artefact whose entire
purpose is provenance. The clean-tree precondition does not catch a concurrent
push. **Abort and redo rather than rebase**, so the hashes stay exact.

---

## 6. The order to do it in

```
1  P4          rewrite assert_redesign.sh for pass-0 markup, with before/after
               evidence. Measure the check_mock_deviations overlap FIRST.
2  §5 audit    go through verify/ and enumerate every check that reads
               production markup, production paths, or SHARED_ASSETS. Write the
               post-cutover form of each into CUTOVER.md §5. This is the rule in
               §1 of this file, applied.
3  ordering    move the version bump ahead of the build in cutover.py --apply,
               and recompute predicted_stamp() with both edits.
4  dry run     fresh, in front of Leo, on the tree of the moment.
5  --apply     immediately after a scheduled push.
```

**Steps 1 and 2 are the ones that have been skipped twice.** Neither is hard.
Both were invisible because the plan was treated as the specification of the
work rather than as a document that could itself be incomplete.

---

## 7. Standing constraints (unchanged)

- **Do not modify** `run.py`, `dashboard_template.html`, `upload.html`,
  `main.py`. `event_config.csv` only where explicitly authorised — and
  **authorised to change one field is not authorised to reformat the file**; it
  has no BOM and CRLF endings, and a `csv.DictWriter` round trip breaks every
  build. See `verify/CHECKLIST.md`.
- **Pure Python stdlib** for the fetcher. Zero pip dependencies.
- **No row-level personal data persisted, ever.** The repo is public.
- **Capacity comes from config**, never from `totalTicketAllocationQty`.
- Any query reading `optInPartners` selects **that field alone**.
- **The mock is the authority on design.** Search it before building.
- The password gate is client-side only (`festipass`, plaintext, public repo).
  Leo has deferred the fix. **Do not change repo visibility without his
  go-ahead.**
- `data/` holds Railway raw uploads carrying contact details and must never be
  committed. A proxy 403 is an org egress-policy denial to report, not route
  around.

## 8. Open items

`HANDOFF.md` §"Open items" is the register. Live ones touching cutover:

- **O12** — Shotgun has no pagination-completeness assertion. 8,391 of epk's
  10,781 tickets unasserted. Blocked on a measurement of real refund churn, not
  on a decision. Do not pick a tolerance before measuring.
- **O1** — closed on both platforms as of 2026-08-12. DICE against a payout
  statement, Shotgun against a back-office export. The fee segment is correct as
  displayed, and **nothing in the code applies a multiplier at all** — the card
  derives it from summed per-ticket data. The per-ticket reconciliation against
  the export is still undone; the file is not in the repo and carries buyer
  identifiers, so it must be stripped to ORDER ID / PRICE / CLIENT PRICE /
  PURCHASE DATE / CATEGORY before it goes anywhere.

## 9. The one habit to keep

From `HANDOFF_CC3.md` §6, and it earned its place twice more this session:

> **A probe, a watcher and a measurement all state a claim, and the claim they
> state must be the one you are making.** Six instances now, and the direction is
> not something you get to assume — two failed toward a false green, four toward
> a false defect or a false pass. The sixth was the cutover's own §5 assertion:
> the dry run modelled the edit, `--apply` asserted against the model, and the
> write performed neither. Model compared to model, and it read as clean.

Say what is unverified when it is. That habit is most of why this project works.

### Three more, and the last two are the same family from the tooling side

**Two quantities that mean different things, reported through one number.** The
adjacent-metric pattern, fourth instance: `projItems` returned `0` both when the
projection menu was empty and when the locator could not find it. A locator
fault read as a payload regression for two sessions, and the investigation that
followed went to the emitter — the one place the defect was not. The repair is
never a better message; it is a second value. `-1` now means "could not
identify", and it prints a different sentence. `only_digits_differ` and
`predicted_stamp()` were the same shape: one number carrying two claims.

**A value read in one frame and reported in another.** Fourth instance, and the
cheapest to make: `git log --date=format:` renders in the AUTHOR's timezone, and
the auto-update commits carry `+0200`. Every timing figure in this session was
two hours out until someone noticed a commit timestamped 42 minutes in the
future. Use `--date=format-local:` or `%aI` when the frame matters, and check a
timestamp against `date -u` before planning around it.

**A loud error can still name the symptom rather than the cause.** `check_b1_switch`
had `v2` hardcoded in THREE places — a dead constant, the payload read, and the
HTTP URL. Fixing two of the three left the check fetching `/v2/bordeaux.html`,
which 404s, so the browser evaluated against an empty body and node died on
`pickMode is not defined`. Nothing was silent and nothing was wrong with
`pickMode`. **A fix that addresses every instance it found is not a fix that
addresses every instance** — grep the file for the pattern, not the line.

**A decision correct in its own scope, invalidating a claim in another.** The
newest member, and the one with no obvious guard. §3(a) deleted `PAGE_PATHS`
because at root the input IS the output — unarguable for the six root pages, and
the reasoning is written out at length. It is also what broke `preview/`, which
is one directory deeper and was the only remaining consumer of the machinery
being removed. Nothing connected the two: no check spans "the thing being
deleted" and "everything that depended on it", because they were reasoned about
in different sections, by different arguments, both sound.

The deleted lines' own comment had named the failure in advance — *"the only one
that would fail at RUNTIME rather than at first paint — a fetch that 404s renders
as 'comparaison indisponible' on every pick"* — and it was deleted along with the
code it described, which is how the warning left with the thing it warned about.

What makes this one different from the rest of the family: every other instance
was a probe stating the wrong claim, and the repair was to fix the probe. Here
both claims were right. The gap is that **no assertion spanned them**, and the
only thing that would have caught it is the one that did: publishing something
through `preview/` and looking. A directory whose contents are never exercised
is a description, not a mechanism.

**A harness produces findings indistinguishable from real ones.** The
post-cutover-shaped tree reported `series_path(...) -> None`, which reads
exactly like a cutover break and was `csv_database/` never being linked into the
tree. The only thing separating a harness fault from a finding is checking the
harness *before* believing its output — the same discipline as the negative
test, applied to the thing running the test. If a simulated environment produces
a failure, the first suspect is the simulation.

**A `|| <literal>` that can fire and has never been ruled on is a claim nobody
made.** `YR = D.ref_year || 2023` put the MOCK'S OWN YEAR on a real page: sonora
has no reference edition, `ref_year` is null, and the dashboard told a reader
"2023 (référence)" and "2023 au même point" twice. Nothing was broken — every
value was computed correctly and rendered cleanly around a year that had nothing
to do with the event.

`check_mock_literals` exists for exactly this and could not see it, for a reason
worth stating precisely: **it strips `${…}` before scanning reader-facing text**,
because an interpolation is data-driven and therefore assumed safe. A
`|| <literal>` fallback makes it neither. `${YR} au même point` scans as
" au même point" — no year to find.

Counted rather than guessed, which is what made the rule tractable: **42** such
fallbacks in the mock, **4** claim-bearing, **1** firing today.

> A fallback is either UNREACHABLE or it is a DECISION. If it can fire, someone
> has to have ruled on what it means; if nobody has, it is a literal answering a
> question that was never asked.

The three dormant ones are now asserted in `dashboard_payload` — `vat`,
`cur_year`, `amode` — so the mock's branches are unreachable rather than merely
unvisited. Same move as `read_warmup_flags()` refusing to default
`day_is_warmup` to False. `ref_year` is the exception and is HANDLED rather than
defaulted, because it is legitimately null on a first edition.

**`vat` is the one to keep in mind, and it is not hypothetical.** A wrong word
gets noticed; a wrong number gets read. `VAT || 0.055` is the French rate, and
Genève already sells in CHF — an event whose rate is not 5.5% is one config row
away, and the failure is every revenue split silently recomputed at a rate
nobody chose, on a page that looks perfect.

**And the sharpest version of this project's recurring pattern: A LEDGER ENTRY
THAT DESCRIBES A FAILURE IT DOES NOT PREVENT.** `X14-fut` in
`check_mock_deviations` ruled the À-venir header and wrote its own rationale:
*"the future rows still saying '2023 (référence)' — half-fixed reads as fixed."*
That sentence describes, exactly, the bug that then shipped — because the ruling
reached the alignment WORD and not the `CMPSEL` gate around it. The description
of the failure sat in the ledger the whole time, as a description of the code.
An entry saying what must not happen is not an assertion that it will not.

**A process check that includes its own command line cannot distinguish RUNNING
from ASKING.** `pgrep -f check_b1_switch` matches the shell running
`pgrep -f check_b1_switch`, so it answers "yes" whether or not the thing exists.
It cost two false "still running" reports in one session — once on a check that
had been dead for twelve hours, killed by a `timeout 1500` cap set from a
measurement taken when the suite had one page fewer; once on a run that had
already finished and gone red. Both times the report to Leo was confident and
wrong, and the second one asserted green-in-progress over an actual failure.

Match the real thing: `pgrep -x`, a pidfile, or the exit status of the job
itself. The bracket trick (`grep "[c]heck_b1_switch"`) is not enough either — it
failed here the moment the name appeared in the command line for an unrelated
reason, because a commit message being passed to `git commit` happened to
contain it. And a background wait must key on the PROCESS exiting, not on a log
going quiet — a log that stops growing looks identical to a log whose writer
died.

**AND THE SAME PATTERN IN `pkill` DOES NOT MISREPORT, IT KILLS YOU.**
`pkill -f "http.server 8732"` matches the shell running that command, so it
terminates its own caller: exit 144, and every line after it in the block never
runs. That is the more expensive half, because what usually sits after a `pkill`
is the cleanup.

Four instances in one session, all the same shape:
  - two file edits silently not applied, and reported as applied
  - `_before_rennes.html`, 351 KB of scratch, shipped to main because the `rm`
    that would have removed it sat after the `pkill`
  - two more scratch files left untracked minutes after writing the commit
    message about the first one

None of it was caught by the suite, and that is the second half of the lesson:
every page assertion enumerates from `event_config`, so a stray file the config
does not know about is invisible to all of them. Green meant "every configured
page is correct", never "the repository is clean".

Kill by PID, or use a pattern that cannot match the caller. Put cleanup BEFORE
anything that can terminate the shell, or in a `trap`, and never at the end of a
chain whose earlier commands can fail.

**A COMMENT WRITTEN IN THE MECHANISM'S OWN VOCABULARY JOINS IN.** Second
instance this session, and the first one should have been enough.

- The workflow's restamp step got a comment explaining why it no longer names
  the staging path — and `check_v2_footer` clause 5 greps that step's body as
  TEXT, so the comment satisfied the check that existed to notice the change.
- A comment added to the mock explaining where the seam is spelled the seam's
  delimiters. `body_of()` locates the region with a plain `find()` for the
  closing nav tag, so the literal inside the comment MOVED THE SEAM: the spliced
  region swallowed the tab bar and pass 0 refused with `.dept-tabs-bg matched
  1 time(s) in the mock and 2 in the page`.

Both were prose about a mechanism, placed inside the mechanism's own input, in
the exact characters it matches on. **If a check or a parser reads a file as
text, every word you add to that file is input** — including the words
explaining what it does. Describe the delimiter, do not spell it; or put the
prose somewhere the parser does not read.

**A CONFIDENT BRIEF FROM THE SEAT THAT KNOWS BEST IS STILL A PREMISE.** The
module-switcher task arrived with four numbered constraints, carefully reasoned.
Three of its premises were wrong, and the instructions built on them would each
have done damage:

- *"it is a mock edit, so it goes through the ledger"* — it is not. The shipped
  switcher is `MODULE_DROPDOWN` in `postprocess_html.py`, in the nav, OUTSIDE the
  seam. Editing the mock changes nothing on any page. **This is the `.sv-solo`
  shape, and it came from the seat that named the `.sv-solo` shape** — the same
  doctrine that file states in its own words, "the mock is a RENDERING of the
  real thing, never a source", was written by the people who then wrote the
  brief.
- *"two items, BOTH disabled … remove `disabled` from both"* — five items, two
  anchors, three spans. Two of those spans are modules that do not exist.
  Following it literally would have lit them up.
- *"`check_archive_provenance` will catch it"* — no such file. See below.

None of this was carelessness; the brief was more careful than most. **The
lesson is that care does not convert a premise into a measurement.** Every one
of the three took under a minute to check — `grep` for the string, count the
items, `ls verify/` — and each was checkable BEFORE any edit. The instruction to
"confirm the second label against the markup rather than taking ours" was in the
brief, and was right, and stopped one line short of the premises around it.

Check the artefact the instruction names before doing what it says, including
when — especially when — the instruction is detailed enough to sound measured.

**THREE SHAPES OF ONE THING: BLINDING YOURSELF, ONE STEP AT A TIME.**

| | what it does |
|---|---|
| `pgrep -f <name>` | matches your own query — answers "yes" whether or not the thing exists |
| `pkill -f <name>` | kills your own caller — exit 144, and the cleanup after it never runs |
| `2>/dev/null` | silences your own error — the step "succeeds" and you carry on |

The third cost an edit that had already been made: `git stash pop` into an
unresolved merge, its refusal sent to `/dev/null`, and the next command reported
the edit missing with no reason attached. Nothing was lost — the stash was still
there — but for one step the tree said something untrue and there was no
evidence of why.

They are the same defect wearing three hats: **a command whose failure mode is
to look like success.** Before writing one, ask what it prints when it is wrong.
If the answer is "the same thing, or nothing", it needs the exit code checked or
the pattern narrowed.

---

### Two safety nets that are documented and do not exist

**`check_archive_provenance` is not a file.** It has been named twice in briefs
as the thing that would catch a `legacy/` page changing. Nothing in `verify/`
reads `legacy/` at all. The archive's hashes are recorded in `legacy/README.md`
and verified only BY HAND, by pasting the command written there — which is a
provenance record, not an assertion.

So the archive is documented but **unasserted**: a rebuild that touched
`legacy/*.html` would ship, and the suite would be green. `rebuild_pages.py` now
refuses `legacy/` explicitly (that is a real guard), and the workflow's rebase
handler refuses it too — but nothing checks the FILES. Worth knowing before
relying on the sentence "the check will catch it", which has now been written
twice about a check nobody wrote.

**And green never meant the repo is clean** — see the entry above. Every page
assertion enumerates from `event_config`, so a file the config does not know
about is invisible to all of them. `_before_rennes.html` shipped to main through
exactly that gap.

Same family as the `-1` vs `0` locator and the two-quantities-one-number
entries above: the predicate answered a question adjacent to the one asked. The
tell is the same too — the answer was available and cheap, and I preferred the
one already in my hand.

*Second instance, same session, one command later.* Running the suite as
`for f in verify/check_*.py; do python3 $f; done` gave **20 red**, not 17. The
three extra were `check_login_bg`, `check_platform_cards` and
`check_section_amber` dying on `IndexError: list index out of range` — they take
`sys.argv[1]`/`[2]` and are driven by `assert_redesign.sh`. §0 of this file
already says so, in the line directly under the loop. A traceback from a check
that was never given its arguments looks exactly like a check that found
something.

**An assertion that is TRUE, on an artefact nobody ships.** SONORA x IMPACT, the
first event added since the cutover and the first with no prior edition, failed
its build on ten `postprocess_html.py` assertions at once — `0 .vel-head`,
`0 .vel-grid`, no `.detail-inset` labelled `"vs …"`, no Chart config for
`chartDay{N}S2`, `recoloured 2 … expected 8`. Every one of them was a true
statement, and not one of them was about the published page.

The obvious reading was "these assertions are not comparison-blind, add
`HAS_CMP`". That was wrong, and the measurement that showed it is a two-line
count: the shipped `rennes.html` carries **0** `.vel-head`, **0** `.vel-grid`,
**0** `.detail-inset` and **0** `chartDay0S2`. Those classes exist only in
`legacy/`. Since the cutover, `postprocess_html.py` produces the INTERMEDIATE
that pass 0 consumes, and pass 0 replaces `</nav>`..`</body>` wholesale. The
assertions guard markup that is discarded seconds after being written — they
cannot catch a defect, and they can stop a build.

**The test is mechanical, so apply it mechanically.** Inside the seam →
discarded → dead; outside → survives → live. Applied to all 73 assertion sites
rather than to the ten that happened to fire, because *the two that bit are not
necessarily the only two* is the rule that produced this file: **50 dead, 23
live**. The ten were the ones this event reached.

Two things nearly made it a wrong answer, and both were caught by measuring
rather than reasoning:

- The first pass counted the `<style>` block as markup — it sits at bytes
  1009–46850, *outside* the seam — and returned MIXED for fourteen tokens that
  are purely in-seam. That is the STANDING RULE at the top of the very file
  being audited, broken while auditing it. Blank `<style>` before counting.
- **Position inside the seam is NOT sufficient.** `build_v2.transplant_footer`
  reaches back into the pre-seam page and carries production's two `.pg-footer`
  blocks across; `prod_nav_script` does the same for the nav JS. So `apply_footer`
  and every footer/stamp/emoji assertion are LIVE despite sitting in the discarded
  region, and deleting them by position would have removed the stampability
  contract. The question is not "where is it" but **"does pass 0 discard it or
  carry it"**.

Closest call, recorded because it is the one a reader will want to re-derive:
`#fbbf24` is the only asserted literal with an occurrence outside the seam, so
`projection: … is gone from the whole document - the recolour was too broad`
looked like it earned its place. Its one outside copy is in the `<style>` block,
which pass 0 also replaces from disk. It lands dead too. **Zero of the 50 guard
anything outside the seam.**

The 50 are not deleted — the passes still run and the messages are still the
fastest way to read the intermediate. They are routed to `seam_discarded`,
printed to **stderr** and never fatal. stderr rather than stdout because
`build_v2.py:595` runs `postprocess_html.py` with `stdout=subprocess.DEVNULL`:
a diagnostic printed the other way is written into nothing on the path that
builds the shipped page. Worth knowing separately — **the fatal `❌` list is
still on stdout, so a postprocess failure under `build_v2` surfaces as a bare
`CalledProcessError` with no reason attached.** The SONORA messages were legible
only because the workflow *also* invokes `postprocess_html.py` directly, one
line above `build_v2`.
