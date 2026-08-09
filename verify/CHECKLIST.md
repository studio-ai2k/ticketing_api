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
| `check_fixture_quarantine.py` | 3 |

---

## After any change to the Suivi renderer

    NODE_PATH=<dir with playwright> node verify/check_selector.js epk.html
    NODE_PATH=... node verify/check_selector.js epk.html 420

Asserts what a reader sees after switching candidate: each Diff equals right
minus left and cannot exceed either, no element the renderer reads holds two
numbers, every left column header names the selection and reverts.

Its two negative tests are load-bearing — reintroduce the `textContent` parse
and the single-label update to confirm it still fires. **Do not remove them.**

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

## Before any redesign acceptance run

    python3 verify/check_fixture_quarantine.py

`redesign/fixtures/fixture_3day.html` is epk's payload wearing bordeaux's day
names — it would pass §7 clean while encoding both the withdrawn default total
and the forward day mapping §5.6 rules out. It is the only three-day fixture, so
a green acceptance run including it proves nothing about the three-day case.

Fails while epk's fingerprints remain; passes once `dashboard_payload.py`
regenerates it to `redesign/FIXTURE_3DAY_TARGET.md`. Deleting it also fails —
that removes the coverage instead of fixing it.

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
