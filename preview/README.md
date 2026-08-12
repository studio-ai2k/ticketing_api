# `preview/` — where a branch build goes to be looked at

Until cutover, `/v2/` was the staging area and work went straight to
`main`: a push published to a path that was not production. That
inverted at cutover. Root IS production now, so a push to `main` is a
deploy, and work moves to a branch.

A branch is only reviewable if its build is published. Otherwise every
visual ruling needs a hand-built preview — and the last time that
happened, a self-contained copy of `v2/epk.html` had to be built by
hand with the series pre-seeded so the page's own `fetch` never fired.
That is **a transformed artefact used to judge an untransformed one**,
the class `check_v2_identity` and the locked mock exist because of.

## How

GitHub Pages already deploys this repo from `main` (`pages build and
deployment` has run 188 times), so nothing needs hosting built — only a
published location. A branch build lands here and is opened at
`…/preview/<page>.html`.

Shipping the cutover without this leaves a window where production is
live, branches are mandatory, and nothing is viewable. That window has
no safe length, which is why this directory exists from the first
cutover commit rather than the second.
