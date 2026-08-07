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
