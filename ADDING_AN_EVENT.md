# Adding an event — the specification

Written from the SONORA x IMPACT addition (2026-08-18), which was the first
event added since the cutover and the first with no prior edition. Recorded as
the spec rather than as a note, so the next one is executed rather than
re-derived.

> **Placement.** Leo asked for this as "the §6.4 spec". There is no `IDEAS.md`
> in the repo and `CUTOVER.md §6.4` is already *The workflow pathspec — the
> archive must not be re-staged*. Rather than overwrite a section or invent a
> number, it is here. Move it if there is a document it belongs in.

---

## 1. The path is TWO EDITS

Everything else is derived. That is the property worth protecting: a third
edit appearing in this list means something stopped being derived.

| # | file | edit |
|---|------|------|
| 1 | `event_config.csv` | one row **per day**, appended at byte level |
| 2 | `fetch_csv.py` | the event id added to the owning `SHOTGUN_ACCOUNTS[...]['events']` |

Derived from those two, with no further edits:

- `pages.py` picks the page up from `output_filename` — the active page count
  goes 6 → 7, and every page check follows it (see §5).
- `build_series.py`, `build_v2.py` and `.github/workflows/daily-dashboards.yml`
  enumerate from the config; the matrix gains a job on its own.

## 2. `event_config.csv` is CRLF with no BOM. APPEND — DO NOT REWRITE

**Authorised to add rows is not authorised to reformat the file.** A
`csv.DictWriter` round-trip added a BOM once and broke `run.load_event_config`
with `KeyError: 'event_id'` — the first column name silently became
`﻿event_id`.

Append at byte level, then assert the file is still what it was:

- the original leading bytes are byte-identical (SONORA: 8050 → 8395, the
  first 8050 unchanged)
- CRLF-only line endings, no BOM
- `csv.DictReader` parses the full grid (55 rows × 26 cols)
- `run.load_event_config()` returns every event with no `KeyError`
- each day row's `day_number` / `day_name` / `day_date` agree —
  `build_dashboard` raises when the orderings disagree, so check the weekday
  rather than trusting the label

## 3. VERIFY THE SHOTGUN ACCOUNT. Do not infer it from the promoter

Run `scripts/probe_shotgun_account.py <shotgun_event_id>` **before writing the
row**, and put its output in the commit. For SONORA (run 32146511963, on
event 544355):

```
episode  (org 171835) cohosted=0: 0 tickets
episode  (org 171835) cohosted=1: 0 tickets
sonora   (org 207784) cohosted=0: 100 tickets on page 1
                                  - event_name='SONORA x IMPACT'
```

Two halves, and both matter:

- The **sonora** line confirms ownership *by name*. Brand and account are
  independent — `bordeaux_2026` lives on Episode despite ML × Sonora branding,
  and that cuts both ways.
- The **episode** lines are why this must be checked rather than assumed.
  `DEFAULT_SHOTGUN_ACCOUNT` is `'episode'`, and a wrong account answers with
  **zero tickets, not an error**. An event missing from every list is
  indistinguishable from an event that has sold nothing, on a page that renders
  perfectly.

A cross-promoter event id could in principle be claimed by the wrong account's
list. Routing is by event id, not by brand, and that is the rule — it is stated
here as a consequence to be aware of, not as something to prevent.

## 4. Fields that are deliberately empty, and the one that cannot be

Leave unknown fields **empty rather than guessed**, and say so. `venue` and
`city` were not supplied for SONORA and were not invented; `build_dashboard`
prints `Venue: , ` and the page renders.

`compare_to` and `comparison_mode` are empty on a first edition.
`comparison_mode` resolves to `j_minus` through `run.py`'s `or` fallback, which
is inert while `compare_to` is empty.

`login_bg_image` empty is the documented way to say "the standard image" —
parisxxl does the same and `postprocess_html` falls back to
`DEFAULT_LOGIN_BG`.

**`currency` cannot be left empty.** `run.py` reads it as
`row.get('currency', 'EUR')`, and `.get()` with a default **does not fire when
the key exists and is empty** — it returns `''`. This is the same trap
`postprocess_html` documents for `login_bg_image`, and it bit there first. Set
it explicitly. Every active row does; only Genève is CHF.

## 5. A FIRST EDITION IS A DIFFERENT ARTEFACT

An event with no `compare_to` produces a page with no comparison markup, and
that is correct: `redesign/fixtures/fixture_no_comparison.html` is the design's
answer for it, and the client gate is `HAS_CMP = !!(D.ref && D.ref.n > 0)`.

`scripts/postprocess_html.py` had ten assertions that failed on exactly this —
`.vel-head`, `.vel-grid`, `.detail-inset`, `chartDay{N}S2`, the recolour
counts. They were not comparison-blind; they asserted the shape of a body that
pass 0 replaces seconds later. See **THE SEAM TEST** at the top of that file
before adding any assertion to it.

Expect the suite to go red on the new page until it is built and committed.
`pages.pass0_pages()` raises on a declared-but-missing page **by design** —
17 checks fail with *"the repo root is missing `<page>` — event_config declares
N active page(s) and only N-1 were built"*. That is the guard working. Do not
add a grace period or an existence check; build the page.

## 6. Afterwards

Run the full suite enumerated from `ls verify/`, not a remembered list — see
the loop at the top of `HANDOFF_CC4.md`. **One** check takes a page argument and
runs inside `assert_redesign.sh`: `check_stampable`. Running it bare produces an
`IndexError` that looks exactly like a finding and is not.

This used to name four. The other three — `check_login_bg`,
`check_platform_cards`, `check_section_amber` — were deleted as checks that ran
nowhere; see `verify/P4_KEEP_DROP.md`. They were skipped because they were
broken, not because they were wired, and listing them here said the opposite.
