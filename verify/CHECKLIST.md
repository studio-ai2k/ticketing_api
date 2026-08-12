# Verification checklist

`verify/assert_redesign.sh` runs on bash and python alone and is the gate for
every build. Everything below needs extra tooling, so it is manual — run it
after the change described, not on every build.

    bash verify/assert_redesign.sh .          # always, all six dashboards

---

## BEFORE adding any check to this file — make it fail

**Every new guard ships with evidence that it failed on the artefact it was
written for.** Not "I reasoned that it would fail". Ran it, saw it fail, saw the
message name the right thing.

    1. write the check
    2. run it against the BROKEN artefact       <- it MUST exit non-zero
    3. fix the bug (or restore the fix)
    4. run it again                             <- it MUST exit zero
    5. record steps 2 and 4 in the commit message

If the fix already shipped and the broken artefact is gone, reconstruct it:
revert the fix, run the check, restore. If a check has several independent
claims, break each one separately — a check can be right about three things and
blind on the fourth, and only the fourth matters.

**This is a step, not advice, because it has already caught a check that its own
author was certain about.** `check_suivi_window.py` was written specifically to
catch seven empty Suivi rows on parisxxl, minutes after reading the code that
caused them — and its first version passed on that page, because run.py's
"Aujourd'hui" row is appended after the visible slice and carried the very
tickets that caused the bug. Trap #10 in `HANDOFF.md`.

Understanding a bug completely is not protection against writing a check that
cannot see it. Those are different skills. This step is the cheap one, and it is
cheap precisely when it matters: the broken artefact exists at the moment you
write the check, because that is why you are writing it.

Checks in this file that have passed step 2, with the failure modes exercised:

| check | drift modes confirmed failing |
| --- | ---: |
| `check_selector.js` | 2 |
| `check_offset.py` | 4 |
| `check_footer_tz.py` | 3 |
| `check_spec_example.py` | 4 |
| `check_suivi_window.py` | 1 (and its own first version failed step 2) |
| `check_payout_reconciliation.py` | 3 |
| `check_build_stamp.py` (v2 half) | 3 (12 stale before the rebuild; a v2-only asset fails v2 alone; a shared asset fails both) |
| `check_shotgun_fee_table.py` | 4 (arithmetic change moves every tier; a witnessed tier vanishes; a new tier — must NOT fail; odd rows at a witnessed tier — must NOT fail) |
| `check_mock_deviations.py` | 4 |
| `check_v2_gate.py` | 1 (the page that actually shipped) |
| `check_v2_identity.py` | 2 (the shipped page; and the nav-form regression) |
| `check_fixture_quarantine.py` | 3 |
| `check_exact_date.py` | 4 (one per claim, broken separately) |
| `check_data_freshness.py` | 2 (the outage reconstructed; and threshold below true age) |
| `check_source_order.py` | 4 (must-flag; correct order; lower specificity; masked) + a new defeat still fails while pinned |
| `check_duplicate_decls.py` | 4 (disagree; identical; different condition; different property) |
| `check_b1_switch.py` (diff absence) | 1 (the null coercion restored) |
| `check_selector.js` (diff absence) | 2 (dead below the % filter; then failing a correct page on `J−25`) |
| `check_anchor_modes.py` | 2 (the drift claim and the by-construction one) |
| `check_v2_footer.py` (frozen/live variant) | 2 (a finished edition rebuilt to the live footer — the regression I shipped; and a live edition given a frozen one) |
| `scripts/pages.py` (page enumeration) | 3 (a config page absent from v2/ — the old glob passed on five; an active row with a prose filename; no active page at all) |
| `fetch_csv.py` pagination guards | 5 (undefined `SHOTGUN_PAGE_SIZE`; Shotgun loop; DICE stall; DICE short fetch; and the false-defect control that must NOT fire) |

---

## Is the fetch complete, or just plausible?

Not a `verify/` script — the claim is about a live fetch, so it cannot be
checked from the repo. The guards live in `fetch_csv.py` and fail the run.

DICE compares orders processed against the `totalCount` the server already
returns, **one-sided**: only `processed < reported` is a defect, because
`totalCount` is read from page 1 and an order placed mid-fetch legitimately puts
`processed` ahead of it. Both fetchers now raise instead of warning when
pagination says there is more and makes it unreachable.

**Shotgun has no completeness assertion.** It exposes no total, so there is
nothing to compare against; it is guarded against pagination loops and nothing
else. Trap #24 in `HANDOFF.md` for the measurements and the reasoning.

---

## Is the pipeline still landing data?

    python3 verify/check_data_freshness.py

Asserts the newest ticket on every LIVE event is under 24 h old. It answers the
question the footer cannot: `Données API HH:MM` is written when a page is
REBUILT, so it moves only when something else already changed — and a stopped
fetch and a stopped commit both leave it frozen at the last run that landed.

**N = 24 is measured, not chosen.** Sales sleep, so the threshold has to clear
the quietest real night. Longest gap between consecutive tickets on each live
campaign over 30 days: geneve 16.1 h, rennes 12.9 h, bordeaux_oct 10.2 h,
epk 8.2 h. 24 gives ~1.5× headroom over the binding one and would have caught
the 28-hour outage.

**Finished editions are excluded and that is load-bearing.** Their data is frozen
by design and ages without bound — paris_xxl shows a 369 h gap. Including them
would make this fire permanently, which carries exactly as much information as
never firing.

**It runs AFTER the push, never in the gate.** The outage it exists for was
caused by a check in that gate. An alarm that also blocks the commit that would
clear it is the same mistake twice.

Negative tests: the real outage reconstructed by rolling rennes' timestamps back
28 h (`29.1 h old`, exit 1), and a threshold below the true age (exit 1). Both
return to exit 0 on restore, and the CSV was verified byte-identical after.

## After any change to the stylesheet

    python3 verify/check_source_order.py
    python3 verify/check_duplicate_decls.py

`check_duplicate_decls` asserts one declaration per selector, per property, per
condition. **A duplicate is only a defect when the two declarations DISAGREE** —
identical ones are redundant and harmless, so they are reported and never fail.
Same distinction `check_source_order` draws between defeated and masked, and
what keeps both honest: a check that failed on all 29 would be demanding
tidiness rather than correctness.

Measured before it was built, because the count decides whether it is a rule or
three findings: 29 duplicates across 1497 keys — 14 disagreeing across 6 sites,
15 identical. Six sites is a rule; fifty would have meant the assertion was
wrong about the sheet.

The find that justified it: a **four-column** mobile grid for `.grp-h,.kid,.tot,
.thead` replaced by a five-column one at the same breakpoint, so the four-column
version had never rendered once. All six sites deleted and verified invisible by
comparing computed styles at 1180/720/640/480/393 — no difference at any width.

Media queries add NO specificity, so a base rule declared LATER at equal
specificity beats an earlier `@media` rule. The media rule stays in the file,
looks correct, and does nothing.

D29 is why: `overflow-x` was declared twice on `html` one line apart, and `clip`
won on **source order alone** — the sticky nav worked, resting on the order of
two adjacent lines.

**It reports "this rule does not take", never "the page is wrong."** Only the
first is provable from a stylesheet. A defeated rule can render perfectly when a
later `@media` re-supplies the value, and that case is reported separately as
MASKED so nobody reads it as a rendering bug or deletes it as noise. Currently
3 masked, all benign.

**No allowlist**, deliberately: an allowlist makes the check pass by growing
instead of the sheet getting better. Two `.cmp-trigger` declarations were PINNED
for a while — the same mechanism `check_spec_example` uses for O1 — because both
available fixes changed the sheet's meaning and the choice was a ruling. That
ruling landed (honour it, not delete it: the declaration moved below the base
rule it kept losing to), so **`PINNED` is now empty and the check is strict**.
A new defeat still failed while they were pinned; that was tested before the
pin was emptied.

It cannot compare selectors as element sets, only as normalised text, so `.a .b`
versus `.b` is invisible to it. That needs the DOM, which is what the browser
checks are for.

## WHICH CHECKS MAY RUN IN CI — the rule, and what breaking it cost

**A check that drives a browser does not go in the workflow.** `check_selector.js`
has carried this in its own header since it was written: *"Needs playwright and
the preinstalled chromium; it is therefore NOT wired into
`verify/assert_redesign.sh`"*. It applies to every browser check, not just that
one.

`check_section_bars`, `check_section_heads` and `check_float_clamp` were wired
into the daily workflow's commit gate in `b03a9cc`. Each hardcodes
`CHROME = '/opt/pw-browsers/chromium-1194/…'` and needs
`NODE_PATH=/opt/node22/lib/node_modules` — **dev-container paths**. A GitHub
runner has neither and the job installs neither, so the first of the three died
on `FileNotFoundError: 'node'`.

The very next scheduled run failed, and so did the six after it: **seven
consecutive runs over ~28 hours, every one fetching and building correctly and
then failing at the gate.** Nothing was committed in that window. The visible
symptom was a footer reading `Données API 00:06` against CSVs carrying tickets
from `10/08 14:43` — and the stamp had not frozen, the **commit** had.

Two things to take from it:

- **The gate runs on python alone.** Anything needing a browser is manual, in
  this file, run before a push.
- **A check that cannot run is worse than no check.** It fails 100% of the time,
  so its signal carries no information — and here it took the whole pipeline
  down with it, silently, because nothing watches a red badge.

## After any change to the Suivi renderer

    NODE_PATH=<dir with playwright> node verify/check_selector.js epk.html
    NODE_PATH=... node verify/check_selector.js epk.html 420

Asserts what a reader sees after switching candidate: each Diff equals right
minus left and cannot exceed either, no element the renderer reads holds two
numbers, every left column header names the selection and reverts.

Its two negative tests are load-bearing — reintroduce the `textContent` parse
and the single-label update to confirm it still fires. **Do not remove them.**

## After any change to a rendered figure that can be ABSENT

    NODE_PATH=/opt/node22/lib/node_modules python3 verify/check_b1_switch.py

Null coercing to zero in a rendered figure is now the **third** instance on this
project: `nf(null)` printing 0, a live candidate's future rendering 0 instead of
an em-dash, and `r.a - r.b` rendering `+134` in green against a row with no
counterpart. All three were arithmetically consistent and all three shipped.

**The assertion has to be about ABSENCE, not about correctness.** "Diff equals
right minus left" passes the bug, because `0` is a legal value for the reference
and the subtraction stays internally consistent while the number is one side
restated. `check_b1_switch` therefore asserts, on the rendered cell, that a row
whose reference is an em-dash has an em-dash in Diff too.

The guard is `!= null` and **not** falsy. `b === 0` is a real zero — a day inside
the covered range before the candidate opened — and its diff is honest
arithmetic: 49 of the 90 blank-looking rows on epk vs `bordeaux_oct_2026`.
Em-dashing those would delete a legitimate comparison to fix a different bug.

## After any change to an anchoring mode

    python3 verify/check_exact_date.py
    python3 verify/check_anchor_modes.py

`exact_date` did raw J−X with the weekday snap turned off — a third thing,
neither of the two its own label names — and shipped that way through a spec, a
mirrored client and a check reporting 198/198. `check_exact_date` runs on
`bordeaux_oct`, whose gaps against seven of its candidates are multiples of 7,
because a zero snap is what made the defect invisible: there the broken mode WAS
`j_minus`, byte for byte. **A negative test on the pair where the effect is
largest would have passed against the broken code.**

It asserts four things and each was broken separately to confirm it fires — the
first break does not exercise the third claim, because breaking both grains the
same way leaves them agreeing with each other while both are wrong.

`check_anchor_modes` derives its expectation from the calendar drift rather than
remembering a number, so it stays right on a pair whose drift is a multiple of
7 and whose two modes therefore legitimately coincide. Its old assertion —
`exact_date weekly == j_minus weekly` — was one of the places the false spec was
written down, and it passed by encoding the defect.

## After any change to the comparison offsets or to run.py

    python3 verify/check_offset.py --fuzz

Proves the closed-form offset equals `run.py`'s own `_prev_match_dow` over
every configured pair and 400 random ones. Its transcription guard is scoped to
`_prev_match_dow`'s own body, because the same clamp lines appear verbatim in
`_prev_match_dsl` and a whole-file search passed on a stale copy. **Four
negative tests; do not simplify them away.**

## Always — the spec against the code

    python3 verify/check_spec_example.py

Runs `HANDOFF.md`'s own worked example through `fetch_csv` and compares. It
exists because the spec and the code disagreed about `gross_price` for the life
of the project, both self-consistent, neither ever failing (trap #9).

**It currently reports one PINNED conflict and exits 0.** That is the O1 fee
question, open with Leo — see `docs/O1_FEE_DECISION.md`. Anything else fails,
including editing the spec to match the code. When O1 lands, fix whichever side
is wrong and set `KNOWN_CONFLICT = None`; it becomes strict and stays strict.

Add the same shape wherever a document states a number the code computes.

## After any change to the footer, the stamp, or run.py's footer render

    python3 verify/check_footer_tz.py

`order_datetime` is UTC. Nine checks that the last-ticket time reaches the page
as Europe/Paris, with real DST — a hardcoded +2 passes June and fails December,
which is the whole point. Also asserts the workflow stamps with
`TZ=Europe/Paris`; the runner is UTC and a bare `date +%H:%M` is the same bug
from our own side.

Three negative tests confirmed firing: unwiring the call, the fixed offset, and
reverting the workflow. **Do not remove them.**

## After any rebuild — the Suivi window

    python3 verify/check_suivi_window.py

Asserts the seven visible daily rows contain sales, and that the daily and
weekly "voir les N" buttons count their own grain.

`paris_xxl_2026` shipped with all seven visible rows at zero, because 7 paid
tickets on 2026-03-30 — sixteen days after the event — dragged
`cutoff_velocity` (`max(order_date) - 1`) past the event and into dead space.
`build_dashboard._clamp_cutoff` clamps to `event_date_last + 1`.

**The first version of this check passed on the broken page.** It summed the
last seven rows including run.py's "Aujourd'hui" row, which is appended after
the VISIBLE_DAYS slice and carried those same 7 stragglers — six zero rows plus
one 7 summed to 7, which is not zero. Excluding that row is what makes the check
mean anything. Trap #5's family again, in a check written to catch a different
bug. **Do not simplify the `dated` filter away.**

## After any change to fee or price handling in `fetch_csv.py`

    python3 verify/check_payout_reconciliation.py

Holds the DICE side of `gross_price` to the `bordeaux_2026` payout statement it
was proved against — 9,327 paid, 624 936,39 brut TTC, 38 214,52 commissions,
and the five tiers verbatim. Tolerance is exactly one known ticket; a second is
a finding, not noise.

    python3 verify/check_shotgun_fee_table.py

Holds the SHOTGUN side to the 17-tier schedule the 2026-08-12 back-office export
witnessed on epk. Both platforms now have an external reference.

**A table rather than pinned totals, because `epk_2026` is LIVE.** The DICE
check pins totals and survives because `bordeaux_2026` is finished and frozen;
155 Shotgun orders landed on epk on 2026-08-11 alone, so a pinned
`8391 / 469 296,88` would stop being true before anyone read it. The schedule
survives growth, and it is the stronger claim: a total is one number many wrong
row sets produce, where this moves if the arithmetic moves for one tier.

**Asserted on the MODE, not on every row.** `bordeaux_oct_2026` already has a
tier carrying two fees — 3 728 rows at face 95,00, of which 17 carry 0,50
instead of 12,37 — so "face determines fee" is false on real data at 0,2% of one
event. A per-row assertion would have called a fee arrangement a code defect. A
systematic change moves the mode; a handful of odd rows cannot.

**A new tier is reported, never failed.** Our arithmetic is unchanged and the
fee is simply unwitnessed, so failing would block a legitimate sale — the
false-defect direction, on a check that names revenue loss.

These are **the only figures in this project validated against a document
someone outside it produced.** Settling O1 meant reading
`process_shotgun_ticket`, three lines from the DICE path, so these exist to make
sure both fixed points survive the next edit there.

## BEFORE PUBLISHING v2/ — both of these, every time

    python3 verify/check_v2_gate.py
    python3 verify/check_v2_identity.py

v2 shipped once with the password modal rendering as unstyled text and the whole
dashboard readable beneath it — internal revenue data on a public URL. The
redesign stylesheet had no `.db-overlay` rule at all. **Every other check was
green on that page**: no NaN, no undefined, no console error, no horizontal
scroll.

The gate check loads a page with no auth token and asserts the overlay is fixed,
opaque, covers the viewport, and is what actually paints at the centre of the
screen. The identity check greps for the mock's own event's literals, because
the mock is a single-event artefact and pass 0 splices its identity along with
its structure — bordeaux_oct shipped showing epk's name, venue and dates.

Both were run against the page that actually shipped and both fail on it.

## Before any redesign acceptance run

    python3 verify/check_fixture_quarantine.py

`redesign/fixtures/fixture_3day.html` is epk's payload wearing bordeaux's day
names — it would pass §7 clean while encoding both the withdrawn default total
and the forward day mapping §5.6 rules out. It is the only three-day fixture, so
a green acceptance run including it proves nothing about the three-day case.

Fails while epk's fingerprints remain; passes once `dashboard_payload.py`
regenerates it to `redesign/FIXTURE_3DAY_TARGET.md`. Deleting it also fails —
that removes the coverage instead of fixing it.

## Before touching the redesign mock or its stylesheet

    python3 verify/check_mock_deviations.py

The working mock is not the locked one. `redesign/locked/` holds the original
upload byte-identical and is never edited; this asserts the working copy differs
from it in exactly the authorised ways — **and no fewer**. An unauthorised hunk
is an invention and goes back to Leo; a missing one is an approved change
someone reverted, which is quieter and just as wrong.

The stylesheet has zero authorised deviations: after the `.pill-warm` deletion
the redesign adds no CSS, so `dashboard_redesign.css` must be byte-identical to
the locked copy.

## After any stylesheet swap

    python3 verify/audit_css_overrides.py

Lists selectors declared more than once and reports what the earlier
declaration leaves in force. Shorthand-aware, and ranked additive-vs-redesign —
without both it is noise, and a noisy audit gets ignored, which is the only way
this pattern keeps shipping. Three real bugs came from it.

Anything ranked REDESIGN deserves a look. Anything at 0% is layering and fine.

## Editing `event_config.csv` — do it at byte level, never through `csv`

**Authorised to change one field is not authorised to reformat the file.**

The file has NO BOM and CRLF line endings. Round-tripping it through
`csv.DictReader`/`csv.DictWriter` with `encoding='utf-8-sig'` — the obvious
thing to reach for, and what the next person will reach for, because every
reader in this repo opens it that way — ADDS a BOM on write. `run.load_event_config`
then raises `KeyError: 'event_id'`, because the first header cell is now
`\ufeffevent_id`. Every build stops.

Read the bytes, split on `\r\n`, find the column index from the header row,
replace that one field, join and write back:

    raw = Path('event_config.csv').read_bytes()
    lines = raw.split(b'\r\n')
    col = lines[0].decode().split(',').index('login_bg_image')
    ...
    Path('event_config.csv').write_bytes(b'\r\n'.join(lines))

Then prove the edit was surgical, both directions:

    git diff --numstat event_config.csv     # 1 1, never more
    python3 -c "import run; print(len(run.load_event_config('event_config.csv')))"

and after reverting, `git diff --quiet event_config.csv` must be silent — the
file byte-identical, not merely equivalent.

The event rows are also DUPLICATED: `geneve_2026`, `bordeaux_2026` and others
appear more than once, with the trailing copies carrying an empty
`event_name`. Match on a non-empty name, or a rewrite will change a row nothing
reads and appear to do nothing.

## After changing the login overlay or the template's `<style>`

The background is checked by `assert_redesign.sh` via `check_login_bg.py`, and
`postprocess_html.py` fails the build on any undeclared `{{PLACEHOLDER}}` in
the template's `<style>`. But the file itself has to be served to be proven:

    python3 -m http.server 8765 &   # from the repo root
    # then load a dashboard and confirm the background is HTTP 200

A missing background falls back to the solid colour with nothing in the
console. Checking that the file is committed is not the same as checking that
it loads.
