# Handoff to CC4

## 0. State, so you start from a known one

**`a703a2c` is the last pushed tree on `main`. It is green. The cutover has NOT
happened and has been attempted twice, both attempts rolled back cleanly.**

Production is the old pipeline. Root pages carry `<!-- shared:… -->` and
production markup; `v2/` holds six pass-0 pages. Nothing is half-landed.

```
bash verify/assert_redesign.sh        # CC4: no argument. It now resolves where
                                      # pass 0 publishes, like every other page
                                      # check (§6.3). `.` meant production, which
                                      # is no longer what this gate asserts.
python3 verify/check_page_anchor.py   # CC4: added. Run it first if the gate is red
python3 verify/check_build_stamp.py
python3 scripts/cutover.py            # dry run, writes nothing
```

**CC4 correction to §0's `main`:** confirm the tree with
`git ls-remote origin main`, not a local ref. A stale local `main` at `273457f`
is an unrelated "Add files via upload" root that DELETES the whole `verify/`
suite; CC3 hit it too. The real `origin/main` carries all six root pages, `v2/`,
`verify/` and `scripts/`.

**The dry run is RED as of CC4, and correctly so.** It reports the §3(b2)
version bump landing after the build that stamps it — the ordering bug named in
§3 below, now surfaced by an assertion instead of by a reader. See
`verify/P4_KEEP_DROP.md`.

Run them first. Not because they are expected to fail, but because a handoff
that says "green" is a claim about a tree you have not seen.

Read `CUTOVER.md` and `HANDOFF_CC3.md` §6 before touching the cutover.

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
