# Cutover plan — v2 becomes the dashboards

Requested as a plan, not a build. Every claim below was checked against the tree
rather than reasoned about, and three of them contradict what the ruling assumed.
The measurements are reproducible from the commands in each section.

**At cutover the old pages retire outright. There is no side-by-side period, and
GIT HISTORY IS THE ONLY FALLBACK** — after this there is no live page to compare
a wrong one against. That raises the bar on the pre-cutover verification rather
than lowering it, which is what §5 is for.

---

## 1. Should the cleanup be a separate commit? Yes — and for a stronger reason

The attribution argument is right: a cutover moves what builds the pages, a
cleanup moves where files live, and together a broken page cannot be attributed
to either without unpicking both.

The reason we would put first is **reversibility, and the two changes have
opposite profiles**:

- A cutover is reversible by reverting one commit. Every input the old pipeline
  needs is still on disk, so the old pages can be *rebuilt* — not merely
  restored — and compared against the new ones.
- A cleanup deletes exactly those inputs. `git revert` restores the files but not
  the confidence: the check you would want to run is "build the old page and
  diff it", and that is only possible while every input survives.

So the cleanup is *the change that removes the fallback*. It must come after a
green run, because the green run is the last moment the fallback is cheap.

**Sequence: pre-work → cutover → one full green run → cleanup.**

---

## 2. Pre-work, and why it is not optional

§3(c) asked whether the new pipeline keeps unconditional rebuilds. It does not
keep them, because **it never had them.**

```
.github/workflows/daily-dashboards.yml:239   - name: Build dashboard
                                      240     if: steps.change.outputs.changed == 'true'
                                      257     python scripts/build_v2.py …
```

`build_v2.py` runs *inside* the conditional step. Evidence, not inference: every
auto-update commit touches exactly four of the six v2 pages, and never
`v2/bordeaux.html` or `v2/parisxxl.html` — the two finished events. Those two
files have only ever been written by hand, by us, in this conversation.

```
$ for c in $(git log --format=%h --author=github-actions -4); do
    git show --stat --format= $c | grep -c 'v2/bordeaux.html'; done
0 0 0 0
```

**Trap #17 is live in v2 today**, and `check_build_stamp`'s scope note says the
opposite in so many words. That note is the same shape as the `assert_redesign`
incident: a true-sounding statement about the wrong mechanism, holding while its
target moved.

It is worse than production's version, because **v2 pages carry no stamp at
all**. `postprocess_html` writes it immediately before `</body>`
(`rennes.html` offset 343 939 of 343 984); pass 0's seam is `</nav>` .. `</body>`,
so the stamp falls inside the replaced region and is spliced away. There is
nothing for a v2 half of the check to read.

Two items therefore land **before** the cutover, not as part of it:

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

This is invisible today because all six configured values *are* `upload.JPG`
(five explicit, `parisxxl` blank → default) — trap #14 again: nothing has a
fingerprint. `check_login_bg.py` matches config by `path.name`, so pointing it at
a v2 page would appear to work while reading a value pass 0 can no longer vary.
`postprocess_html.py:278` predicted this in writing: *"a wholesale `<style>`
replacement destroys every templated value in it."* At cutover this becomes the
gate on the only dashboard.

---

## 3. The cutover itself

### (a) PAGE_PATHS disappears — it does not become location-aware

All three substitutions rewrite a **root-relative** original into a `../` form:

```python
('src="LOGO_ROND_JAUNE.png"', 'src="../LOGO_ROND_JAUNE.png"')
("url('upload.JPG')",         "url('../upload.JPG')")
('"series/{id}.json"',        '"../series/{id}.json"')
```

The left-hand sides are what the mock and the redesign sheet already carry. At
root the correct output *is* the input, so `PAGE_PATHS` becomes `[]` and the loop
becomes identity. **Delete the list and the loop; do not write a conditional.**
Confirmed exhaustive: the only `../` in a shipped page are those three
(`grep -o '\.\./[^"'"'"' ]*' v2/rennes.html` → LOGO ×2, upload.JPG ×2, series ×1).

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
in (a) are outside it and unchecked by anything. That is mitigation (a)'s
territory again.

### (c) `check_build_stamp` — see §2. Not a cutover decision, a pre-work item

Its scope note gets rewritten to say the v2 pipeline is conditional and therefore
covered, rather than unconditional and therefore exempt.

### (d) What the old pipeline still feeds — measured

| asset | reaches a v2 page? | at cutover |
|---|---|---|
| `run.py`, `dashboard_template.html`, `build_dashboard.py` | **yes** — pass 0 builds on their output: head, nav, gate, nav script, and the sidecar that carries the observed cutoff | stays |
| `scripts/postprocess_html.py` | **yes** — pass 9 builds the nav v2 needs | stays |
| `style/font_links.html` | **yes** — head-level, outside the seam | stays |
| `style/dashboard_v6_8.css` | **no** | retires |

The stylesheet measurement, since it decides a deletion. Chunk the 46 KB sheet
into 118 pieces of 400 bytes and count survivors:

```
survives into rennes.html      110/118
survives into v2/rennes.html    12/118   ← generic @media text common to both sheets
```

Pass 0 replaces the single `<style>` block wholesale
(`build_v2.py:331`, `STYLE_RE.subn(…, count=1)`), so the sheet reaches production
only. **But it is in `SHARED_ASSETS`**, so deleting it moves the hash and fails
every production page — which is correct behaviour and is why the deletion
belongs in the cleanup commit, after `SHARED_ASSETS` has been rewritten for the
pipeline that survives.

---

## 4. The cleanup, and why mitigation (a) comes first

`check_build_stamp` hashes the **path** as well as the contents, so *moving* a
shared file fails every page loudly. *Deleting* a file that is not in
`SHARED_ASSETS` fails nothing at all. The cleanup's entire risk is therefore
concentrated in what the checks do not name — which is mitigation (a) restated,
and the argument for doing (a) **before** the cleanup rather than after.

Mitigation (a), as recorded against the check: assert that every file
`postprocess_html.py` and `build_dashboard.py` open or read appears in
`SHARED_ASSETS`. It turns an omission from invisible into a failing test.

The generalisation this round earned, worth applying to the whole cleanup: **any
hand-maintained correspondence between two things the code already relates is
the same hazard.** The page→event map that was wrong in all six rows is one
instance; `SHARED_ASSETS` is another; a restated `PAGE_PATHS` would have been a
third. Before the cleanup, grep for lists that agree with the code instead of
following it.

---

## 5. What the first successful post-cutover run looks like

Written so a **wrong** run is recognisable, because there will be no live page to
compare against.

**The one assertion that is only available once.** Immediately before the
cutover, capture the six `v2/*.html`. The first post-cutover root pages must
equal them byte-for-byte after removing the three `../` prefixes. Take this
snapshot *during* the cutover — it is precisely the comparison the no-side-by-side
decision removes, so it has to be taken while it still exists.

Then, on every run afterwards:

1. Six pages at root, each with a `const D=` payload whose `id` matches its
   `event_config.output_filename` row.
2. **Zero `../` anywhere in any page.** The positive form of §3(a).
3. A shared stamp present on all six and equal across them (§2 P1/P2).
4. `check_mock_deviations`: the ledger's authorised deviations, the line budget
   exact, and `check_pages` running with an empty `PAGE_PATHS`.
5. `check_b1_switch`: every candidate on every page, both grains.
6. `check_eligibility`: P1–P3; P4 retired by name (see §6).
7. Login background per page equals its config row (§2 P3) — and note this stays
   unfalsifiable until two events are configured differently.

**The negative fingerprint.** A root page that still contains `.dashboard {` was
written by the old builder: that rule head is in `dashboard_v6_8.css`, present in
all six production pages and absent from all six v2 pages. It is the cheapest
single test of "which pipeline produced this file", and it should fail the run.

---

## 6. Ordering, against the ruling's list

```
1  anchoring     live series (done) · three modes · the two lines of copy
                 P4 in check_eligibility retires here, named by the mode that did it
2  C1, C2        section tab bars                        (render before building)
3  C3, C4        card titles into cards · Projection Finale container
                 more than one round each, accepted knowingly
   ─────────────  pre-work P1/P2/P3 from §2 land any time before here
4  CUTOVER       §3 · plus the once-only snapshot in §5
5  green run
6  CLEANUP       mitigation (a) first, then the deletions in §3(d)
```

---

## 7. Open, and it lands on this plan

**The Shotgun 13,03% payout multiplier is still unverified and has no owner.** It
needs Episode or Sonora. Today it is a figure on a side path; at cutover it
becomes the figure on Leo's only dashboard, with no old page to check it against.

If it is still unverified when the cutover is ready, that is a decision to take
deliberately rather than to discover — and §5's byte-for-byte snapshot does not
help here, because both pages would carry the same unverified number.
