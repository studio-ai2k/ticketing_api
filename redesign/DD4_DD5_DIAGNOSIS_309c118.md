DD4 is a production bug and DD1 is my own overreach. Let me verify the diagnosis in code first.

Three copies of the same mapping, not one. Checking their guards and whether `launch_date` is ever actually set.

Diagnosis confirmed, but the bug is wider than reported. Checking DD5's anchor consistency.

Diagnosis confirmed with three corrections. Writing it up.

Now recording the DD4 diagnosis and DD5 finding.

Pushed as `309c118`. **DD4 confirmed but not fixed** — the mechanism needs your ruling, and I found three things that change it.

**The branch is dead, but not for the reason given.** `comparison_mode` is `''` on 49 rows and `j_minus` on 4 — never `days_since_launch`. But `launch_date` **is** populated: `run.py:3948` derives it from the first sale in the data and assigns it to both configs before the dashboard is built. `on_sale_date` being empty is real and irrelevant.

That distinction decides the fix. Flipping `comparison_mode` would enable position mapping *and* switch `_prev_match_dsl` for the Suivi table, `filter_tickets_to_same_point_dsl` for the whole comparison, and the `prev_cutoff` at `run.py:1869` — far more than the ruling asks. **Don't fix it by setting the mode.**

**It's three sites, not one.** `day_name_map` has exactly one consumer, as you asked. But the same guard, same shape, same bug appears twice more under another name:

| site | name | consumers |
|---|---|---|
| `run.py:1921` | `day_name_map` | Par Jour presence |
| `run.py:2881` | `prev_presence_key_map` | vélocité, projections |
| `run.py:3514` | `prev_presence_key_map` (redefined) | vélocité, projections, **day capacity** |

Seven consumers total. A fix must hit all three — Par Jour matched by position while Vélocité is still matched by name is worse than both being wrong the same way, because the page would disagree with itself silently.

**geneve loses one day, not both.** `geneve_2025` is single-day and that day is named `Samedi`, so geneve_2026's samedi matches by name; only vendredi falls through. epk and bordeaux are exactly as you reported — and epk is the clearest case of the failure that's worse than a zero: Saturday silently compares our opening day against their closing day.

**On your two questions:** `day_name_map` has one consumer, but the pattern has seven. And `day_number` is populated 1..N and agrees with `day_date` everywhere I checked — but `day_date` is the fact and `day_number` is an assertion about it, so I'd order by `day_date` and *assert* `day_number` agrees, failing on disagreement rather than silently preferring one.

**Mechanism — I need your call.** run.py is do-not-modify and these are inline blocks inside large functions, so they can't be monkeypatched the way `_generate_suivi_v3` was. Two routes:

1. **Re-key the reference data before run.py reads it.** All three sites do a *current* day-name lookup in a *previous-year* structure (`metrics_prev['day_presence'][dn]`, per-ticket `presence_<dn>`). Renaming the previous edition's day keys into the current edition's names, positionally, turns every name lookup into a position lookup at all three sites at once — one rename, no run.py change, and the three cannot desynchronise because there's only one of them.
2. **Lift do-not-modify for these three blocks.** Smaller diff, clearer intent, forks a borrowed file.

Route 1 is my recommendation. Not implemented, because it changes what every comparison on three dashboards means.

**DD5 doesn't reproduce in run.py.** All ~20 previous-year anchors use `event_config_prev['event_date_first']` — Revenus, Vélocité, Présence, Projections alike. No card derives its own; the single data-derived date (`run.py:2140`) feeds a display label, not a comparison. For epk_2023 that anchor is 2023-09-01 Vendredi, as your config says.

But your 1/2 Sept split **is** explainable and intentional: `_prev_match_dow` snaps to the same weekday, so a current Saturday lands on 2 Sept, while the weekly grain buckets from 1 Sept with no snap. Cards on different grains legitimately reference different dates — that's the constant offset proved earlier. Re-anchoring the cards would break the daily comparison rather than fix it.

**DD1** — recorded as an open ambiguity with both readings tabled, explicitly kept separate from the deduction error so an unverified claim doesn't ship under cover of a verified one. My "second error" was an over-claim.

**DD3** — stated as the general rule, with the corollary that matters for anyone deriving phases: **the last tier never closes.** A routine expecting every phase to have an end will either wait forever or invent one.
