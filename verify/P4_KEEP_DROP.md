# P4 — `assert_redesign.sh`, assertion by assertion

**For Leo to rule on.** Every row carries its measurement. Nothing here is
reasoning about what the pages probably contain; every number came from
`rennes.html` (production) and `v2/rennes.html` (pass 0), counted separately in
the `<style>` element, in `<script>` elements, and in what remains — the static
markup a `grep` on the file is actually testing.

Reproduce the whole table:

    python3 scripts/pages.py                 # the six pages, from the config
    # then count any token in the three regions of a page, e.g.
    python3 - <<'EOF'
    import re, pathlib
    h = pathlib.Path('v2/rennes.html').read_text(encoding='utf-8')
    STYLE  = re.compile(r'<style>(.*?)</style>', re.S)
    SCRIPT = re.compile(r'<script\b[^>]*>(.*?)</script>', re.S)
    static = SCRIPT.sub('', STYLE.sub('', h))
    print(len(re.findall(r'class="vel-head"', static)))
    EOF

---

## Why the gate splits four ways rather than being rewritten

The gate has 396 assertions. Three measurements decide what happens to each:

1. **174 of the 396 passed against six ZERO-BYTE files.** Absence assertions
   hold on a page containing nothing. Fixed first, by
   `verify/check_page_anchor.py` — the anchor now runs before anything else on
   each page and the same six empty files produce **0** passes.
2. **Production ships its body as static markup; pass 0 does not.** 2716
   `<div>`s outside `<script>`/`<style>` on production's rennes, **67** on pass
   0's. The body is built at runtime from `const D`.
3. **`check_mock_deviations` reads a built page at exactly one line** —
   `check_mock_deviations.py:1156` — and reads the `<style>` element alone.

So the CSS half is already asserted, more strictly, somewhere else; the markup
half has no artefact left to assert; and a residue is genuinely static on both
pipelines and stays.

---

## DROP — subsumed by `check_mock_deviations`, and more strictly (8)

`check_pages` asserts the shipped `<style>` is **byte-identical** to
`redesign/style/dashboard_redesign.css` put through the transforms `build_v2`
declares, per page, including the per-event login background. The ledger then
pins that file to the locked mock: every line is either locked, an authorised
deviation, or carried verbatim from production's sheet. A `grep` for a marker
inside that block cannot fail unless byte-equality already has.

These also derive their expectation from `style/dashboard_v6_8.css` — the sheet
being **retired**, which `assert_redesign.sh:27` reads by path. That is a second
reason they cannot survive: §3(d)(3) moves that file to `legacy/` at cleanup.

| token | prod | pass-0 | `<style>` | `<script>` | static |
| --- | ---: | ---: | ---: | ---: | ---: |
| `fs-nano` | 14 | 12 | 12 | 0 | 0 |
| `fs-tiny` | 10 | 25 | 25 | 0 | 0 |
| `fs-mini` | 5 | 12 | 12 | 0 | 0 |
| `font-size:[0-9]*px` | 0 | 3 | 3 | 0 | 0 |
| `@media (max-width:720px)` | 2 | 8 | 8 | 0 | 0 |
| `prefers-reduced-motion` | 1 | 1 | 1 | 0 | 0 |
| `html,body{overflow-x:clip` | 1 | 1 | 1 | 0 | 0 |
| `#fbbf24` | 7 | 4 | 4 | 0 | 0 |

Every one is **CSS-only on pass 0** — zero occurrences outside the `<style>`
element. `@media (max-width:600px)` and the `font-size:Npx` rows are among the
15 classes currently failing, and both fail for the same reason: they compare
pass 0's sheet against production's.

`verify/check_login_bg.py` (called at `assert_redesign.sh:123-126`) goes with
them: `check_pages` resolves the background from `event_config` and from the
built artefact independently and requires agreement, which is the stronger form
of the same claim. **Caveat worth your ruling:** §5.7 asks for a *negative* test
— point one config row at a different filename, assert the page follows, set it
back. All six pages currently carry `upload.JPG`, so the data is uniform and
neither check would notice if the per-page wiring broke. Dropping
`check_login_bg` does not create that gap, but it does not close it either.

## TRAP — passes on pass 0 by matching JavaScript, not markup (2)

| token | prod | pass-0 | `<style>` | `<script>` | static |
| --- | ---: | ---: | ---: | ---: | ---: |
| `class="[^"]*ac-t` | 7 | 5 | 0 | **5** | **0** |
| `class="ac-t"` | 7 | 5 | 0 | **5** | **0** |

**These pass today on pass-0 pages and mean nothing.** All five hits are inside
`<script>` — the accordion markup lives in a JS template string. Zero rendered
markup is being asserted.

This is the gate's own documented trap, re-acquired one layer over. Its Deploy 2
banner says: *"the v6.6 stylesheet still ships .chart-tabs rules, so `grep -c
chart-tabs` is 5 on a correctly-restructured file… the same trap that made
align_nav_shell's `sw-wrap` guard match the stylesheet and silently skip every
dashboard."* The fix then was to key on `class="…"` rather than a bare name.
On pass 0 that repair no longer works, because the template strings contain the
`class="…"` form too.

The count assertion on the same class compounds it. `assert_redesign.sh:180-182`
computes `want = days + 5` from the page's own `.q-card` count. On pass 0
`days` is 0, so `want` is 5, and the page has 5 — **it passes by arithmetic
coincidence**, on a page with no day cards at all.

## MOVE — no static artefact exists post-cutover (14)

Every one of these is present in production's markup and **absent from pass 0's
file entirely** — not relocated, not renamed. They exist only in a rendered DOM.

| token | prod | pass-0 |
| --- | ---: | ---: |
| `class="…ac-body` | 7 | 0 |
| `Space Grotesk` | 1 | 0 |
| `class="q-card"` | 2 | 0 |
| `canvas id="chartDay[0-9]*S1"` | 2 | 0 |
| `_projBuilders['day[0-9]*S2']` | 2 | 0 |
| `id="sep-prev-days"` | 1 | 0 |
| `id="sep-prev-weeks"` | 1 | 0 |
| `h.scrollTop=h.scrollHeight` | 2 | 0 |
| `class="dtl-cutoff"` | 4 | 0 |
| `class="vel-head"` | 1 | 0 |
| `class="vel-grid"` | 1 | 0 |
| `class="inset-divider"` | 1 | 0 |
| `class="det-link"` | 3 | 0 |
| `class="det-link-txt"` | 3 | 0 |

Two callouts go with them, for the same reason:

- `verify/check_platform_cards.py` (distinct hrefs, canonical order) — keys on
  `.det-link`, which is 0 in pass 0's file.
- `verify/check_section_amber.py` — needs `<div id="sec-projection"` in static
  markup. It is absent, so the script prints its `-1` sentinel and the gate
  reports `-1 #fbbf24 left inside #sec-projection`. The sentinel is working
  correctly; the message is misleading, and the assertion is dead either way.

**`Space Grotesk` is not a defect.** It is 0 in pass 0's `<style>` as well —
the redesign does not use that font. The assertion outlived the design.

**Your ruling:** each of these is a real property that nothing will assert once
this gate stops claiming to. The browser-driven checks
(`verify/check_v2_behaviour.py`, `verify/check_selector.js`) are where they can
live, and you have already said the browser does not become a CI dependency —
so moving them means they run by hand or in a workflow that installs Playwright,
not in the daily run. That is a real reduction in daily coverage, and it is the
decision I do not think I should make for you. The alternative is to accept that
the mock ledger pins the *template* these are rendered from, and that the DOM
checks already assert the *behaviour* — in which case several can simply go.

## KEEP — genuinely static on pass-0 pages (12)

The nav shell and the footer are production chrome transplanted into pass 0, so
they are real markup on both pipelines and a `grep` tests what it appears to.

| token | prod | pass-0 | static |
| --- | ---: | ---: | ---: |
| `class="…pill` | 5 | 2 | 2 |
| `class="db-modal-sub"` | 1 | 1 | 1 |
| `class="pg-footer` | 2 | 2 | 2 |
| `class="pg-footer det-footer"` | 1 | 1 | 1 |
| `class="pgf-item` | 6 | 6 | 6 |
| `class="pgf-ver">v6.8` | 2 | 2 | 2 |
| `smartboard.shotgun.live/events/` | 1 | 1 | 1 |
| `mio.dice.fm/events/` | 1 | 1 | 1 |
| `Partenaires` | 1 | 1 | 1 |
| `nav-user` | 3 | 3 | 1 |
| `sw-wrap` | 10 | 16 | 2 |
| `DM Sans` | 10 | 11 | 1 |

Three of these need scoping rather than keeping as-is:

- **`sw-wrap` (2 static, 4 `<style>`, 10 `<script>`)** and **`nav-user`
  (1 static, 2 `<style>`)** — the bare-name greps that the Deploy 3 banner was
  written about. They pass on the stylesheet and the JS as readily as on the
  markup. Scope to the static region or they are TRAP rows too.
- **`DM Sans` (1 static, 5 `<style>`, 5 `<script>`)** — the `<style>` hits are
  subsumed; only the static one is this gate's business.
- **`class="pgf-ver">v6.8`** must become `v7.0` at cutover (§3(b2)). Derive it
  from `postprocess_html.DASHBOARD_VERSION` rather than hardcoding, the way
  `scripts/cutover.py:predicted_version()` now does. `assert_redesign.sh:110`
  is the **third** check site of the version bump and is not in
  `cutover.plan_writes` — the other two, `postprocess_html.py` and
  `check_footer_tz.py`, are (`cutover.py:346-360`).

`verify/check_stampable.py` stays: the footer is static on both sides and
`stamp_footer.py` patches this exact markup in published HTML hours later.

## DEAD — absence assertions with nothing left to regress (21)

Zero on **both** pipelines. Each guards against a class name coming back.

`details-toggle`, `details-panel`, `yoy-badge`, `session-sw`, `Outfit`,
`Tableau de bord interne`, `madameloyal.github.io`, `class="proj-grid"`,
`class="chart-tabs"`, `class="chart-tab"`, `id="proj-day`,
`id="proj-logique"`, `class="chart-subtitle"`, `rgba(96,165,250,.8)`,
`rgba(251,191,36,.8)`, `_projBuilders['day[0-9]*S1']`,
`grid-template-columns:1fr 50px 44px 44px`, `dice.fm/partner/events/`,
`🎟`, `🔄`, `🔒`

These are the bulk of the 174 that passed on empty files. The anchor makes them
non-vacuous — they now run only against a page proved whole — but "non-vacuous"
is not the same as "worth running".

They divide, and the division is a judgement rather than a measurement:

- **Cheap and still meaningful**: `madameloyal.github.io` (an external hotlink
  returning is a live hazard), the three raster glyphs, `Outfit`. These guard
  something that could plausibly come back via a shared asset.
- **Guarding a pipeline that no longer exists**: `proj-grid`, `chart-tabs`,
  `chart-tab`, `chart-subtitle`, `proj-day`, `proj-logique`, both `rgba(...)`
  palette literals, `_projBuilders['dayNS1']`, the old vélocité grid. These
  assert that a Deploy 2 restructure of **production markup** did not regress.
  Pass 0 does not emit that markup on any code path, so nothing can regress it.
- **Renames the mock ledger already pins**: `details-toggle`, `details-panel`,
  `yoy-badge`, `session-sw`, `Tableau de bord interne`. The mock is the source
  these are rendered from, and the ledger fails on any unauthorised hunk in it.

---

## What this leaves

| bucket | tokens | disposition |
| --- | ---: | --- |
| DROP | 8 | subsumed by `check_pages`, and it is stricter |
| TRAP | 2 | passing on JS source — remove or move; they assert nothing today |
| MOVE | 14 | no static artefact — your ruling on DOM harness vs. drop |
| KEEP | 12 | static on both pipelines; 3 need scoping, 1 needs the version derived |
| DEAD | 21 | your ruling; ~5 cheap and live, ~10 guard a retired pipeline, ~5 pinned by the ledger |

The anchor has landed and is not in these counts. It is 1 assertion per page
and it is the one that makes the other buckets mean anything.

---

# RULED — Leo, and what was done

| bucket | ruling | done |
| --- | --- | --- |
| DROP 8 | drop — `check_pages`' byte equality is strictly stronger | deleted |
| DEAD 21 | delete — zero on both pipelines is not coverage | deleted |
| TRAP 2 | scope, do not keep; if a scoped version has no static artefact it is MOVE | **both are MOVE** — see below |
| MOVE 14 | drop, unless pinned by neither the ledger nor a DOM check — name those | **none survive; all 14 dropped** |
| KEEP 12 | unchanged | kept, 3 scoped to the static region |

The gate went from **396 assertions to 84** (14 per page × 6), and from 174
passing on six empty files to **0**.

## TRAP 2 — scoped, and the scoped version has nothing to assert

`class="ac-t"` scoped to the static region reads **0** on every pass-0 page; all
5 whole-file hits are inside `<script>`. So the scoped assertion has no artefact
and the ruling sends it to MOVE, where it then falls to the MOVE ruling. Both
`.ac-t` assertions are gone.

The scoping itself was kept and applied where it *does* have a subject:
`sw-wrap` (16 whole file → 2 in markup), `nav-user` (3 → 1) and `DM Sans`
(11 → 1) are now counted against `verify/static_region.py` rather than the file.
Those three were halfway to being TRAP rows and are now not.

## MOVE 14 — pinned by neither: **none**

Measured against the mock, the locked mock, the built page, and both DOM checks:

| assertion | in mock | in locked | in page | in a DOM check | verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| `class="q-card"` | 1 | 1 | 1 | 0 | ledger + `check_build_stamp` |
| `h.scrollTop=h.scrollHeight` | 1 | 1 | 1 | 0 | ledger + `check_build_stamp` |
| `class="det-link"` | 1 | 1 | 1 | 0 | ledger + `check_build_stamp` |
| the other 11 | 0 | 0 | 0 | 0 | **the redesign does not produce this markup at all** |

The eleven are not unpinned properties. They are **production's vocabulary**,
and the redesign either renamed the thing or removed it:

- `class="…ac-body"` → the redesign's accordion body is **`ac-b`**. Present in
  the mock, the locked mock and the page; renamed, not lost.
- `id="sep-prev-days"` / `id="sep-prev-weeks"` → the redesign has **one**
  separator, `sep-past`. A design change, ruled and shipped.
- `Space Grotesk` → the redesign loads **DM Sans only**. Zero occurrences in the
  redesign sheet. The assertion outlived the design it was written for.
- `class="vel-head"` / `class="vel-grid"` / `class="inset-divider"` /
  `class="dtl-cutoff"` / `class="det-link-txt"` → no `vel-*`, no divider class,
  and only `dtl-rev` / `det-chart` in the redesign's vocabulary.
- `canvas id="chartDay…S1"` / `_projBuilders['day…S2']` → the redesign builds no
  canvases in markup; charts are constructed at runtime.

So the answer to "name the ones pinned by neither" is that **there are none**,
and the reason is not that coverage was found elsewhere — it is that eleven of
the fourteen were asserting a design that no longer exists. That is worth saying
plainly, because "we checked and it is covered" and "there was nothing there"
are different facts and only the second one is true here.

## One gap this leaves, named rather than closed

The three ledger-pinned rows are pinned **transitively**: the ledger pins the
mock against the locked copy, and `check_build_stamp` pins each page against the
shared set that contains the mock and `build_v2.py`. No single check states "the
page's body is the mock's body through the declared transforms" the way
`check_pages` states it for the `<style>` element.

`check_section_bars.py` already does exactly that, scoped to the section tab
bars — *"the shipped section bars are the mock's, byte for byte"*, not "has six
tabs". Generalising that to the body is the real replacement for the markup half,
and it would run on bash and python alone. It is not in this change.

## §5.7's negative test — still open, and unaffected

Dropping `check_login_bg.py` neither creates nor closes the gap. All six pages
carry `upload.JPG`, so the data is uniform and neither `check_login_bg` nor
`check_pages` would notice if the per-page wiring broke. The test §5.7 asks for
is a real config change — point one row at a different filename, assert the page
follows it, revert — and it is its own item, not a side effect of this one.
Uniform data is exactly what made the paris_xxl login background invisible.
