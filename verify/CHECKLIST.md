# Verification checklist

`verify/assert_redesign.sh` runs on bash and python alone and is the gate for
every build. Everything below needs extra tooling, so it is manual — run it
after the change described, not on every build.

    bash verify/assert_redesign.sh .          # always, all six dashboards

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
