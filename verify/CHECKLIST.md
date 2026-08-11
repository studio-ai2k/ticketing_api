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
| `check_mock_deviations.py` | 4 |
| `check_v2_gate.py` | 1 (the page that actually shipped) |
| `check_v2_identity.py` | 2 (the shipped page; and the nav-form regression) |
| `check_fixture_quarantine.py` | 3 |
| `check_exact_date.py` | 4 (one per claim, broken separately) |
| `check_anchor_modes.py` | 2 (the drift claim and the by-construction one) |

---

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

These are **the only figures in this project validated against a document
someone outside it produced.** Settling O1 will mean editing
`process_shotgun_ticket`, three lines from the DICE path, so this exists to make
sure the fixed point survives that edit.

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

## After changing the login overlay or the template's `<style>`

The background is checked by `assert_redesign.sh` via `check_login_bg.py`, and
`postprocess_html.py` fails the build on any undeclared `{{PLACEHOLDER}}` in
the template's `<style>`. But the file itself has to be served to be proven:

    python3 -m http.server 8765 &   # from the repo root
    # then load a dashboard and confirm the background is HTTP 200

A missing background falls back to the solid colour with nothing in the
console. Checking that the file is committed is not the same as checking that
it loads.
