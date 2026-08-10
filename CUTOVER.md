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

Three items land **before** the cutover — not "any time", because §5's once-only
snapshot is worth much less without them:

**P1 — pass 0 re-emits the stamp, over a v2 shared set.** The v2 set is a
superset of production's: pass 0 builds *on* a postprocessed page, so everything
production is made of still applies, plus the mock, `dashboard_redesign.css`,
`build_v2.py`, `build_series.py` and `dashboard_payload.py`.

**P2 — `check_build_stamp` grows a v2 half.** Not "make the v2 build
unconditional": that is a fix which can silently stop being true, and it just
did. The check is what caught this class; the check is what should cover it.

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

### (b) `check_mock_deviations`' page check already follows PAGE_PATHS

It imports the list rather than restating it, and its docstring was written for
this day. With `PAGE_PATHS == []` it degrades to a straight equality between the
inlined `<style>` and the file, which is a *stronger* assertion.

Residual: `check_pages()` validates only the `<style>` block. The two transforms
in (a) are outside it and unchecked by anything.

### (c) `check_build_stamp` — see §2. Not a cutover decision, a pre-work item

Its scope note gets rewritten to say the v2 pipeline is conditional and therefore
covered, rather than unconditional and therefore exempt.

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
them byte-for-byte after removing the three `../` prefixes. Take the snapshot
*during* the cutover, and take it **before** the archive banner is inserted
(§7.2) so the two changes never have to be separated afterwards.

Then, on every run afterwards:

1. Six pages at root, each with a `const D=` payload whose `id` matches its
   `event_config.output_filename` row.
2. **Zero `../` anywhere in any built page.** The positive form of §3(a).
3. A shared stamp present on all six and equal across them (§2 P1/P2).
4. `check_mock_deviations`: the ledger's authorised deviations, the line budget
   exact, and `check_pages` running with an empty `PAGE_PATHS`.
5. `check_b1_switch`: every candidate on every page, both grains.
6. `check_eligibility`: P1–P3; P4 retired by name.
7. Login background per page equals its config row (§2 P3) — and note this stays
   unfalsifiable until two events are configured differently.

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
1  anchoring     live series (done) · three modes · the two lines of copy
                 P4 in check_eligibility retires here, named by the mode that did it
2  C1, C2        section tab bars                        (render before building)
3  C3, C4        card titles into cards · Projection Finale container
                 more than one round each, accepted knowingly
4  pre-work      P1 stamp in pass 0 · P2 v2 half of check_build_stamp
                 P3 login background templated per page
                 config-derived page enumeration (§6.3) — before cutover, because
                 it is what lets the checks survive v2/ disappearing
5  CUTOVER       §3 · the once-only snapshot (§5), taken BEFORE the banner
                 legacy/ created: six pages + banners + README
                 workflow pathspec made explicit (§6.4)
6  green run
7  CLEANUP       mitigation (a) first
                 then §3(d)(3): pass 0 stops inlining v6_8, the file moves to
                 legacy/, and the absent-file probe becomes a test
                 dashboard_v6_6.css deleted or archived
```

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
