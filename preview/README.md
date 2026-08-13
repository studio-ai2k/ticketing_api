# `preview/` — an unproven claim, now measured. IT DOES NOT WORK YET.

Until cutover, `/v2/` was the staging area and work went straight to `main`: a
push published to a path that was not production. That inverted at cutover. Root
IS production now, so a push to `main` is a deploy, and work moves to a branch.

A branch is only reviewable if its build is published. Otherwise every visual
ruling needs a hand-built preview — and the last time that happened, a
self-contained copy of `v2/epk.html` had to be built by hand with the series
pre-seeded so the page's own `fetch` never fired. That is **a transformed
artefact used to judge an untransformed one**, the class `check_v2_identity` and
the locked mock exist because of.

That is still the need. What follows is what this directory promised, and what
happened when someone finally tried it.

## WHAT IT CLAIMED

> GitHub Pages already deploys this repo from `main`, so nothing needs hosting
> built — only a published location. A branch build lands here and is opened at
> `…/preview/<page>.html`.

Shipped with the cutover, on the argument that a window where production is live,
branches are mandatory and nothing is viewable has no safe length. Correct
argument. The mechanism was never exercised, and it does not hold.

## WHAT IS ACTUALLY TRUE, MEASURED

**1. A branch build is never served.** Pages builds `head_branch: main`, and
only main — 222 deployments, every recent one from main. A file in `preview/` on
a branch is deployed by nothing. The artefact has to reach `preview/` ON MAIN,
which means previewing a branch requires merging something to main first.

**2. A page built into `preview/` is broken, and the cutover is what broke it.**
`preview/` is one directory deep, exactly as `v2/` was — and §3(a) DELETED the
machinery that made a one-deep page work. `PAGE_PATHS = []` now, so a page built
here carries root-relative paths and 404s on all of:

```
  LOGO_ROND_JAUNE.png     the logo
  upload.JPG              the gate background
  series/{id}.json        EVERY B1 comparison
  bordeaux.html, …        the nav's session switcher
```

The deleted code's own comment named the worst one in advance:

> the only one that would fail at RUNTIME rather than at first paint — a broken
> image is obvious, a fetch that 404s renders as "comparaison indisponible" on
> every pick.

Measured on a real `build_v2.py --out preview/rennes.html`: 2 root-relative
logo references, 2 gate-background references, the series template, and five nav
hrefs. The page renders and is wrong, which is the failure mode this project
keeps meeting.

## WHY IT READ AS DONE

Nothing was ever published through it. The directory existed, the README
described a mechanism, and the description was checked by nobody because there
was nothing to check it against — the same shape as an assertion whose reference
cannot fail.

## WHAT WOULD ACTUALLY WORK — a decision, not yet made

Three shapes, none of them free:

- **Serve previews from the root** under a name production does not use
  (`preview-<page>.html`). No depth, so nothing to rewrite, and the cutover's
  deletion stays deleted. Costs a root-level naming convention.
- **Give pass 0 a depth-aware build** — the `../` machinery back, parameterised
  by output depth rather than hardcoded. That is re-adding what §3(a) removed,
  for a different reason than it was removed.
- **Publish previews outside this repo** — an artifact upload, or a branch that
  Pages is configured to serve. Costs configuration that lives outside the tree
  and can go stale unseen, which is the class §6.3 exists to avoid.

Until one is chosen and EXERCISED, the honest state is: **a branch build cannot
be looked at, and any visual ruling on a branch still needs a hand-built
preview** — with the transformed-artefact hazard that implies.
