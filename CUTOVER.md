# Cutover plan — v2 becomes the dashboards

Requested as a plan, not a build. Every claim below was checked against the tree
rather than reasoned about, and three of them contradicted what the first review
assumed. The measurements are reproducible from the commands in each section.

**URLs.** v2's output takes the current production URLs at the repo root —
`…/ticketing_api/epk.html` and the rest. No path changes and no redirects:
existing bookmarks keep working and start serving the redesign. The archive lives
at `legacy/<name>.html`, a path nobody has bookmarked. **`/v2/` is the URL that
retires.**

**The old pages are kept as a served archive** (`legacy/`, §7), not deleted. That
lowers the stake of every irreversible step below, and §1 says by how much.

**The consequence of keeping the URLs: nothing breaks visibly.** Anyone holding a
link to a dashboard silently starts seeing the redesign — which is what was asked
for, and it means **no reader is ever told the page changed.** Two things follow.
§5's recognisable-good run is the *only* signal that the switch happened
correctly, because a wrong switch is equally silent. And the archive banner (§6.2)
is the only place a reader can discover the old view still exists.

---

## 1. Cleanup as a separate commit — still yes, on a narrower argument

The first version of this plan argued the cleanup must follow a green run because
*"the cleanup is the change that removes the fallback"*. **With `legacy/` retained
that argument no longer holds**, and it fails harder than the addendum credits:

the fallback that survives is not just *frozen artefacts to diff against*. It is
the ability to **rebuild** an old page. Four of the five old-pipeline assets stay
at the repo root because v2 builds on them (§3(d)), so `run.py`,
`dashboard_template.html`, `build_dashboard.py` and `postprocess_html.py` are all
still present and still exercised daily. Only the stylesheet moves. Rebuilding an
old page after cutover is a real command, not a git-archaeology exercise — which
is why the README can carry it (§7.4).

**So the sequencing now rests on attribution alone, and that is enough.** A
cutover moves what builds the pages; a cleanup moves where files live. Run
together, a broken page cannot be attributed to either without unpicking both.
Keep them separate — but price it as a debugging convenience, not as protection
against an unrecoverable state.

**Sequence: pre-work → cutover → one full green run → cleanup.**

---

## 2. Pre-work, and why it is not optional

The first review asked whether the new pipeline keeps unconditional rebuilds. It
does not keep them, because **it never had them.**

```
.github/workflows/daily-dashboards.yml:239   - name: Build dashboard
                                      240     if: steps.change.outputs.changed == 'true'
                                      257     python scripts/build_v2.py …
```

`build_v2.py` runs *inside* the conditional step. Evidence, not inference: every
auto-update commit touches exactly four of the six v2 pages, and never
`v2/bordeaux.html` or `v2/parisxxl.html` — the two finished events. Those two
files have only ever been written by hand.

```
$ for c in $(git log --format=%h --author=github-actions -4); do
    git show --stat --format= $c | grep -c 'v2/bordeaux.html'; done
0 0 0 0
```

**Trap #17 is live in v2 today**, and `check_build_stamp`'s scope note says the
opposite in so many words — the same shape as the `assert_redesign` incident: a
true-sounding statement about the wrong mechanism, holding while its target moved.

It is worse than production's version, because **v2 pages carry no stamp at
all**. `postprocess_html` writes it immediately before `</body>` (`rennes.html`
offset 343 939 of 343 984); pass 0's seam is `</nav>` .. `</body>`, so the stamp
falls inside the replaced region and is spliced away. There is nothing for a v2
half of the check to read.

Four items land **before** the cutover — not "any time", because §5's once-only
snapshot is worth much less without them:

**P0 — RESOLVED, and not by this plan.** The finished-edition footer work gave
v2 real footer content, so `stamp_footer.py` now exits 0 on a v2 page in both
modes (`--checked` and `--frozen`, measured 2026-08-12). The restamp step no
longer fails on day one and needs no repointing. The text below is kept as the
record of what it was.

**P1 — DONE 2026-08-12.** Pass 0 writes `<!-- shared-v2:HASH -->` over
`build_v2.V2_SHARED_ASSETS`, asserting first that exactly one `</body>` exists
and that no production stamp survived the seam.

**P2 — DONE 2026-08-12.** `check_build_stamp` audits both sets, 12 pages. The
scope note claiming v2 could not go stale is deleted as false. All six
production pages were rebuilt in the same commit, because `postprocess_html.py`
is in its own `SHARED_ASSETS` and the signature change moved the hash.

**P1 — pass 0 re-emits the stamp, over a v2 shared set.** The v2 set is a
superset of production's: pass 0 builds *on* a postprocessed page, so everything
production is made of still applies, plus the mock, `dashboard_redesign.css`,
`build_v2.py`, `build_series.py` and `dashboard_payload.py`.

**P2 — `check_build_stamp` grows a v2 half.** Not "make the v2 build
unconditional": that is a fix which can silently stop being true, and it just
did. The check is what caught this class; the check is what should cover it.

**P0 — v2 HAS NO FOOTER CONTENT, AND THE RESTAMP STEP FAILS ON IT.** Production's
footer carries `Données API · HH:MM` in `.pgf-k`/`.pgf-v`, and the workflow's
"Restamp the footer" step patches it with `scripts/stamp_footer.py`. That footer
lives inside the body region, so **pass 0's seam replaces it** with the mock's
`<div class="foot" id="foot"></div>` — which nothing writes to. Measured:
`stamp_footer.py` on a v2 page prints *"footer stamp matched 0 time(s),
expected 2"* and **exits 1**.

That is the good failure mode — loud, not silent — so the cutover cannot quietly
lose the freshness stamp. But the restamp step fails on day one unless v2 grows
a footer or the step is repointed, and it runs on the quiet-hour path for every
event that did not change. Decide which before cutover, not during.

(Found while fixing a separate defect: `#foot` was a child of `page-details` in
the LOCKED mock, so it rendered only on Détails. Fixed. The stamp being absent
from v2 entirely is the larger half and is this item.)

**P3 — the v2 gate's login background is baked, not templated.** Found while
checking §3(d). `dashboard_template.html` renders `{{LOGIN_BG_IMAGE}}` *inside*
the `<style>` block; pass 0 replaces that whole block with the redesign sheet,
which hardcodes `upload.JPG`:

```
template   .db-overlay { … url('{{LOGIN_BG_IMAGE}}') … }
production .db-overlay { … url('upload.JPG')         … }   ← templated per event
v2         .db-overlay { … url('../upload.JPG')      … }   ← from the sheet, fixed
```

Invisible today because all six configured values *are* `upload.JPG` (five
explicit, `parisxxl` blank → default) — trap #14 again: nothing has a
fingerprint. `check_login_bg.py` matches config by `path.name`, so pointing it at
a v2 page would appear to work while reading a value pass 0 can no longer vary.
`postprocess_html.py:278` predicted this in writing: *"a wholesale `<style>`
replacement destroys every templated value in it."* At cutover this becomes the
gate on the only dashboard, so P3 is a per-page style transform in pass 0, not a
note.

---

## 3. The cutover itself

### (a) PAGE_PATHS is deleted, not made conditional

All three substitutions rewrite a **root-relative** original into a `../` form:

```python
('src="LOGO_ROND_JAUNE.png"', 'src="../LOGO_ROND_JAUNE.png"')
("url('upload.JPG')",         "url('../upload.JPG')")
('"series/{id}.json"',        '"../series/{id}.json"')
```

The left-hand sides are what the mock and the redesign sheet already carry. At
root the correct output *is* the input, so the list becomes `[]` and the loop
becomes identity. The URL ruling settles it: output lands at root, so **delete
the list and the loop.** Confirmed exhaustive — the only `../` in a shipped page
are those three (LOGO ×2, `upload.JPG` ×2, series ×1).

**The thing to flag:** there is a *second* location-dependent behaviour and it is
not in the list that names them. `strip_placeholders` removes the upload link,
with the reason *"it points at a page that does not exist under /v2/"* — and at
root `upload.html` exists. It happens not to be a regression, because
`postprocess` pass 1 already removes the same link from production
(`grep -c upload.html rennes.html` → 0), so the removal is right for a reason
that has nothing to do with directories. But the *recorded* reason is
location-based and stale, and the code says so itself: *"at CUTOVER this must not
turn into a feature the redesign silently dropped."* Fix the reason, keep the
removal, and note that `PAGE_PATHS` was never the complete list of
location-dependent transforms — only the complete list of *path* ones.

### (b) `check_mock_deviations`' page check follows PAGE_PATHS — and P3 collides with it

It imports the list rather than restating it, and its docstring was written for
this day. With `PAGE_PATHS == []` it would degrade to a straight equality between
the inlined `<style>` and the file — a *stronger* assertion, and the first version
of this plan stopped there.

**It is not stronger once P3 lands, it is false.** Fixing the login background
means pass 0 substitutes a per-event value *into the stylesheet* at build time, so
each page's inlined `<style>` differs from `dashboard_redesign.css` — which is
precisely what `check_pages` asserts does not happen. P3 and this section are the
same decision seen twice.

**Model the login background the way `PAGE_PATHS` was modelled**: a named
transform, exported from `build_v2`, imported by `check_pages`, and applied to the
file before comparing. Not an exception, not a tolerance. The failure mode
otherwise is concrete and cheap to fall into — someone lands P3, `check_pages`
fails on all six pages at once, and the least-effort way out is to loosen
`check_pages`. That is the D24 assertion again, in the check that guards the
stylesheet.

So after cutover the check reads: *the inlined `<style>` equals the file through
exactly the transforms `build_v2` declares.* Today that list has three entries and
one purpose; then it will have one entry and a different purpose. The shape is
what survives.

Residual, unchanged: `check_pages()` validates only the `<style>` block. The two
transforms in (a) are outside it and unchecked by anything.

### (b2) The version goes to 7.0 — and it is TWO places, not one

Ruled: at cutover the footer version becomes **7.0**, and that is a deliberate
break rather than an increment. 6.x is the pipeline where `run.py`'s body reaches
the page; 7.0 is where pass 0's does. The same bump applies to the project
package so the two stay legible against each other.

Until cutover, v2 shows **production's version unchanged**. v2 is built on the
same pipeline, so inheriting the number asserts nothing false, and no v2 suffix
is invented.

Written down here because it is **two edits, not one**, and the second is the
kind that sits on every page for a month reading the old number:

| where | what | how it is found |
|---|---|---|
| `scripts/postprocess_html.py` | `DASHBOARD_VERSION = '6.8'` → `'7.0'` | the one real knob. `VERSION_OLD` is the TEMPLATE's literal (`Festiflow Dashboard v6`), not the current version, so it does **not** change |
| `verify/check_footer_tz.py` | `v6.8` hardcoded **twice**, in expected footer strings | would fail the run loudly — which is the good case |

`dashboard_template.html` ships the literal `Festiflow Dashboard v6` twice and is
**not** modified: postprocess replaces the prefix, and the count of 2 is asserted
at build time.

`verify/check_v2_footer.py` reads `postprocess_html.DASHBOARD_VERSION` rather
than restating it, so it follows the bump on its own. That is the shape the
other two should have had, and the reason this table exists rather than a note
saying "remember to bump the version".

### (c) `check_build_stamp` — see §2. Not a cutover decision, a pre-work item

Its scope note gets rewritten to say the v2 pipeline is conditional and therefore
covered, rather than unconditional and therefore exempt.

### (c2) A PREVIEW PATH — required BY the cutover, not after it

**Build this as part of the cutover. From the moment it lands, the working
pattern cannot function without it.**

Today `/v2/` *is* the staging area, and that is why work goes straight to `main`:
a push publishes to a path that is not production, and Leo has a URL he can open
on his phone within one daily run. A branch adds a second staging layer on top of
one that already exists, and it costs exactly what the `exact_date` session
showed — the reviewing seat verified `main` and reported the work missing, Leo
could not open the pages at all, and a self-contained copy of `v2/epk.html` had
to be hand-built with the twelve series pre-seeded so the page's own `fetch`
never fired.

That hand-built copy is the thing to notice. It was one added line plus a seed
block and otherwise byte-identical, and it was still **a transformed artefact
being used to judge an untransformed one** — the class of mistake this project
has already been bitten by (`check_v2_identity` and the locked mock exist because
of it).

**At cutover this inverts.** `v2/` becomes production, so a push to `main`
becomes a deploy, and work must move to a branch. But a branch is only reviewable
if its build is published somewhere Leo can open — otherwise every visual ruling
needs a hand-built preview, and every visual defect on this project without
exception was found by Leo opening a page.

So the ordering is not optional:

    now -> cutover     work on main; preflight, push, Leo opens /v2/
    AT cutover         the preview path ships WITH it
    after cutover      branch; publish the branch build to the preview path;
                       merge once Leo has looked

Shipping the cutover without the preview path leaves a window where production is
live, branches are mandatory, and nothing is viewable. That window has no safe
length.

**AND IT IS A SMALLER JOB THAN THIS SECTION FIRST PRICED IT.** GitHub Pages is
already enabled on this repo and already deploying from `main` — `pages build and
deployment` has run 188 times. An earlier note here said "no Pages, no
`gh-pages`, no deploy workflow"; that was wrong, and wrong in an instructive way.
It checked for a workflow FILE and for a `gh-pages` BRANCH, found neither, and
concluded about the mechanism as a whole — but Pages can deploy from a branch
with no workflow of its own, through GitHub's built-in job. Checking one
mechanism and concluding about all of them is the same shape as a check that
cannot see the defect it was written for.

What that changes: the preview path does not need hosting built, only a
published location for a branch build. The conclusion above is unaffected —
`/v2/` on `main` is still the staging area today, and a branch is still
unreviewable without somewhere to publish it.

### (d) What the old pipeline still feeds — measured, and CORRECTED

The first version of this table had one column. It needed two, and the missing
one changes the cleanup.

| asset | reaches a v2 **page**? | **read at build time**? |
|---|---|---|
| `run.py`, `dashboard_template.html`, `build_dashboard.py` | yes — head, nav, gate, nav script, the sidecar carrying the observed cutoff | yes |
| `scripts/postprocess_html.py` | yes — pass 9 builds the nav v2 needs | yes |
| `style/font_links.html` | yes — head-level, outside the seam | yes |
| **`style/dashboard_v6_8.css`** | **no** | **YES — and this was missed** |
| `style/dashboard_v6_6.css` | no | no — unreferenced by any `.py`, `.yml` or `.sh` |

The stylesheet does not reach a v2 page. Chunk the 46 KB sheet into 118 pieces of
400 bytes and count survivors:

```
survives into rennes.html      110/118
survives into v2/rennes.html    12/118   ← generic @media text common to both sheets
```

Pass 0 replaces the single `<style>` block wholesale (`build_v2.py:331`,
`STYLE_RE.subn(…, count=1)`). **But `postprocess_html.py` still reads the file to
inline it in the first place, and pass 0 runs postprocess.** Measured by removing
it and building:

```
$ mv style/dashboard_v6_8.css /tmp/ && python3 scripts/build_v2.py --event rennes_2026 …
subprocess.CalledProcessError: … postprocess_html.py … returned non-zero exit status 1
```

So the file is dead *content* and live *input*. It cannot simply move to
`legacy/`. Three ways out, and the third is the one to take:

  1. leave it at root and copy it into `legacy/` — a duplicated live file, the
     exact hazard §7.1 exists to avoid. No.
  2. move it and repoint `STYLE_PATH` at `legacy/` — then the archive contains a
     load-bearing file. Honest but wrong-shaped.
  3. **make pass 0 skip postprocess's style inlining**, since v2 discards the
     result anyway. Then nothing reads the file and it genuinely retires. This
     touches `postprocess_html.py`, which production also uses — which is exactly
     why it belongs in the **cleanup commit, after cutover**, when postprocess
     has one consumer instead of two.

The assertion that makes this falsifiable is the probe above: after the cleanup,
the v2 build must **succeed** with `style/dashboard_v6_8.css` absent from the
root. Run it as a test, not as a belief.

---

## 4. The cleanup, and why mitigation (a) comes first

`check_build_stamp` hashes the **path** as well as the contents, so *moving* a
shared file fails every page loudly. *Deleting* a file that is not in
`SHARED_ASSETS` fails nothing at all. The cleanup's entire risk is therefore
concentrated in what the checks do not name — mitigation (a) restated, and the
argument for doing (a) **before** the cleanup rather than after.

Mitigation (a): assert that every file `postprocess_html.py` and
`build_dashboard.py` open or read appears in `SHARED_ASSETS`. It turns an
omission from invisible into a failing test — and note that it is precisely the
check that would have caught §3(d)'s missing column, because `STYLE_PATH` is a
read that no page reflects.

The generalisation this round earned, worth applying to the whole cleanup: **any
hand-maintained correspondence between two things the code already relates is the
same hazard.** The page→event map that was wrong in all six rows is one instance;
`SHARED_ASSETS` is another; a restated `PAGE_PATHS` would have been a third; §6
names three more.

---

## 5. What the first successful post-cutover run looks like

Written so a **wrong** run is recognisable.

**The one assertion that is only available once.** Immediately before the
cutover, capture the six `v2/*.html`. The first post-cutover root pages must equal
them after removing the three `../` prefixes. Take the snapshot *during* the
cutover, and take it **before** the archive banner is inserted (§6.2) so the two
changes never have to be separated afterwards.

**It is not byte-for-byte, and pretending it is would sink it.** P1 puts a
shared-set hash in every v2 page, and that set contains `build_v2.py` — which the
cutover *edits*, since deleting `PAGE_PATHS` and its loop is §3(a)'s entire
content. The stamp therefore changes at cutover for an entirely legitimate reason,
and it does so at the one moment the comparison exists and cannot be re-run. It is
also the failure most likely to be waved through as "that's just the stamp", which
is how a real difference gets waved through beside it.

So **assert the difference instead of ignoring it**: exactly one differing line,
that line matching `postprocess_html.STAMP_RE`, and nothing else. A second
differing line then fails, which is the property "compare modulo the stamp" throws
away.

Then, on every run afterwards:

1. Six pages at root, each with a `const D=` payload whose `id` matches its
   `event_config.output_filename` row.
2. **Zero `../` anywhere in any built page.** The positive form of §3(a).
3. A shared stamp present on all six and equal across them (§2 P1/P2).
4. `check_mock_deviations`: the ledger's authorised deviations, the line budget
   exact, and `check_pages` running with an empty `PAGE_PATHS`.
5. `check_b1_switch`: every candidate on every page, both grains.
6. `check_eligibility`: P1–P3; P4 retired by name.
7. Login background per page equals its config row (§2 P3). **Make it falsifiable
   in the negative test rather than waiting for reality**: point one config row at
   a different filename, assert the page follows it, set it back. Every other
   check here is negative-tested; this one should not be excused because the data
   happens to be uniform — uniform data is what made the bug invisible in the
   first place.

**The negative fingerprint, and its scope.** A *built* page containing
`.dashboard {` was written by the old builder: that rule head is in
`dashboard_v6_8.css`, appears **twice in each production page and zero times in
each v2 page**. It is the cheapest single test of which pipeline produced a file.

**Every `legacy/` page contains it by definition**, so the assertion must not be
written as "no page anywhere". Scoping it by non-recursive glob would be exclusion
by pattern — see §6. Scope it to **the pages `event_config.csv` names**, which is
where the answer already lives.

---

## 6. The `legacy/` folder and the four checks that would break quietly

### 6.1 Scope it to what actually retires

§3(d) is the authority, and it says most of the old pipeline survives. **Do not
copy surviving files into `legacy/`.** Two copies of `run.py` would drift, and the
legacy copy would drift *silently* because nothing builds from it.

What goes in:

- **the six rendered pages**, as frozen artefacts
- **`style/dashboard_v6_8.css`** — dead content, but only after §3(d)(3) makes it
  a dead input too. Until then it stays at root, and moving it early breaks the
  v2 build.
- **`style/dashboard_v6_6.css`** — already an orphan. Verified: no `.py`, `.yml`,
  `.sh`, `.html` or `.md` in the repo mentions it, and it is not in
  `SHARED_ASSETS`. 42 KB that has been dead for some time; this is the moment to
  say so.

Anything ambiguous stays where it is. A file in the wrong place is recoverable; a
duplicated live file is not obviously wrong until it drifts.

### 6.2 The frozen pages are served, and they will lie

GitHub Pages will serve `legacy/epk.html`. It carries the same client-side gate,
so anyone who can reach the current page can reach it, and it will show
cutover-day numbers forever with nothing on the page saying so. The README is in
the folder; the reader is in the HTML.

**Recommendation: stamp them, and the archive-should-be-untouched objection
dissolves rather than being overruled.**

Insert one banner per page at freeze time, naming the freeze date, the commit, and
that the page is an archive and is no longer updated. Above the content, inside
the gate — someone who never gets past the gate sees no figures either.

The objection is real but it is about *provenance*, not about *bytes*, and
provenance is recoverable cheaply: **record each page's SHA-256 in the README
before the banner is inserted.** The archive is then provably "the page that
shipped, plus one named insertion", and anyone can verify that by stripping the
banner and hashing. An unstamped archive buys byte-identity and pays for it with
a reader who cannot tell the page is dead — the wrong trade, and the same
degrade-honestly rule as the null refday and the failed-fetch notice.

Two consequences to carry: the banner text is **not** subject to the mock ledger
(these pages are not built from the mock), and the pages keep their existing
`<!-- shared:… -->` stamp. Leave it. It is evidence of what built them, and the
README says it is meaningful only against the freeze commit.

### 6.3 The checks — fix the enumeration, do not add exclusions

Every check that touches pages enumerates them, and there are three different
mechanisms in play today:

```
check_b1_switch.py:212        (ROOT/'v2').glob('*.html')
check_mock_deviations.py:342  V2.glob('*.html')
check_mock_literals.py:136    (ROOT/'v2').glob('*.html')
check_v2_behaviour.py:264     (ROOT/'v2').glob('*.html')
check_v2_gate.py:93           (ROOT/'v2').glob('*.html')
check_v2_identity.py:85       (ROOT/'v2').glob('*.html')
check_build_stamp.py:88       PAGES = ('parisxxl.html', 'bordeaux.html', …)   ← hand-written
assert_redesign.sh:12         FILES=(parisxxl.html bordeaux.html …)           ← hand-written
verify/check_eligibility.py   V2_DIR.glob('*.html')
```

After cutover the six globs point at a directory that no longer exists, so all of
them must change anyway. The addendum asks for each to state whether `legacy/` is
in or out, and warns that **exclusion by glob is coverage lost without a
decision**. Both are right, and there is a single change that satisfies them
better than nine separate exclusions:

**enumerate from `event_config.csv`'s `output_filename` rows.** One helper,
imported everywhere. Then:

- `legacy/` is out **because no config row points at it** — a property of what the
  repo builds, not a property of a path pattern. That is a decision, and it is
  written where the decision lives.
- the two hand-written page lists disappear. They are the same hazard as the
  page→event map that was wrong in all six rows, sitting in the verification
  layer.
- a seventh event added to the config is covered by every check on the day it is
  added, instead of on the day someone remembers.

`check_build_stamp` needs one extra sentence in its docstring regardless: legacy
pages carry a stamp over a shared set that no longer exists, and are excluded
because they are **not built**, not because they are old.

**Status: specified, not shipped.** `check_build_stamp.py:88` and
`assert_redesign.sh:12` still carry hand-written six-name lists as of this
writing. Nothing in this section has been built.

### 6.4 The workflow pathspec — the archive must not be re-staged

```
.github/workflows/daily-dashboards.yml:392
    git add -- '*.html' ':!dashboard_template.html'
```

That pathspec is **recursive**: it would sweep `legacy/*.html` into every daily
commit, and an archive that is re-staged daily is not an archive. It must become
explicit — the six built pages by name, or a `:!legacy/` exclusion stated with its
reason. Same explicit-pathspec care the PII boundary already needs, and the same
reasoning as §6.3: name what is included rather than rely on what a pattern
happens to miss.

Worth noting the pathspec is *already* wider than it reads — it is what stages
`v2/*.html` today, which is intended but nowhere stated.

---

## 6.5 The cleanup is sound, but only if a file is proved dead before it is deleted

The cleanup began as an instinct rather than a derived requirement, and it is a
good one — for a sharper reason than tidiness. **Ambiguity about which file is
authoritative has caused most of this project's real defects**: the badge that
"already existed" in a mock copy that had moved, the stylesheet check validating a
file the page did not carry, the year scan pointed at the wrong artefact, two
production pages frozen for weeks. Dead files are that ambiguity sitting in the
repo waiting for someone to read the wrong one.

**But the method is the whole thing, and this plan has already demonstrated why.**
§3(d) declared `dashboard_v6_8.css` retired because no v2 page contains it — and
removing it breaks the v2 build. *"Looks unused" is not evidence.*

Two rules for the cleanup commit:

1. **Prove a file is dead by measurement, then delete it.** Mitigation (a) —
   assert every file `postprocess_html.py` and `build_dashboard.py` read appears
   in `SHARED_ASSETS` — is what converts the instinct into evidence, which is why
   it is scheduled first. Anything mitigation (a) cannot speak to needs its own
   probe, like the `mv`-and-build test in §3(d), recorded next to the deletion.
2. **Prefer moving to `legacy/` over deleting, where both are available.**
   `check_build_stamp` hashes the *path* as well as the contents, so a
   wrongly-moved shared file fails every page loudly, while a wrongly-deleted file
   outside `SHARED_ASSETS` fails nothing at all. Deletion is the asymmetric
   direction; take the one that announces its own mistakes.

---

## 7. The README in `legacy/`

Written so someone can *use* the folder, not just identify it:

1. **What these pages are**, and the exact freeze date and commit SHA.
2. **They are not built and never will be again** — and the `<!-- shared:… -->`
   stamp in each is meaningful only against the freeze commit.
3. **Which pipeline produced them**, and that its inputs mostly still live at the
   repo root because v2 builds on them.
4. **How to rebuild one**, which is a real command because of §1: the
   `build_dashboard.py` → `postprocess_html.py` pair, the CSV it takes, and where
   `dashboard_v6_8.css` now lives. State what would differ from the frozen copy —
   the footer timestamp and the shared stamp at minimum.
5. **The pre-banner SHA-256 of each page** (§6.2), so the one modification made to
   the archive is verifiable.
6. **A pointer to `CUTOVER.md`** for why the change happened.

---

## 8. Ordering

```
1  P1, P2        stamp in pass 0 · v2 half of check_build_stamp
                 EARLY, not "before cutover". Trap #17 is live in v2 NOW: four
                 live events rebuild daily and two finished ones do not, so
                 v2/bordeaux.html and v2/parisxxl.html are accumulating the
                 exemption production had. Every shared change between today and
                 P1 misses those two pages, and nothing reports it.
2  anchoring     live series (done) · three modes · the two lines of copy
                 P4 in check_eligibility retires here, named by the mode that did it
3  C1, C2        section tab bars                        (render before building)
4  C3, C4        card titles into cards · Projection Finale container
                 more than one round each, accepted knowingly
5  pre-work      P3 login background templated per page, WITH §3(b)'s named
                 transform and §5.7's negative test — the three are one item
                 config-derived page enumeration (§6.3), which is what lets the
                 checks survive v2/ disappearing
6  CUTOVER       §3 · the once-only snapshot (§5), taken BEFORE the banner, and
                 asserted as "exactly one differing line, matching STAMP_RE"
                 legacy/ created: six pages + banners + README
                 THE PREVIEW PATH (§3(c2)) SHIPS HERE. Not after. The moment
                 v2/ is production, branches become mandatory and nothing is
                 viewable without it — and every visual defect on this project
                 was found by Leo opening a page.
                 workflow pathspec made explicit (§6.4)
7  green run
8  CLEANUP       mitigation (a) first — it is also what would have caught §3(d)
                 then §3(d)(3): pass 0 stops inlining v6_8, the file moves to
                 legacy/, and the absent-file probe becomes a test
                 dashboard_v6_6.css moved rather than deleted (§6.5 rule 2)
```

P1/P2 move to the front because they are the only item on this list whose cost
*grows* while it waits.

---

## 9. Open, and it lands on this plan

**The Shotgun 13,03% payout multiplier is still unverified and has no owner.** It
needs Episode or Sonora. Today it is a figure on a side path; at cutover it
becomes the figure on Leo's only dashboard.

`legacy/` does **not** help here, and it is worth being explicit about why, since
the archive resolves most of §1's worries: the frozen pages carry the *same*
unverified multiplier. An archive is a defence against a regression, not against
a figure that was always wrong. §5's byte-for-byte snapshot has the same blind
spot for the same reason.
