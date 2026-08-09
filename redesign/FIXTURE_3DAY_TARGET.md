# `fixture_3day.html` — authoritative target figures

Measured 2026-08-09 from `data/bordeaux_2026_merged.csv` and
`csv_database/bordeaux_2025/bordeaux_2025_merged.csv`, via
`run.resolve_attendance` (§1 route (c)) and `run.filter_tickets_to_same_point`.

The regenerated fixture must reproduce these. Anything else means the payload
builder disagrees with production somewhere.

## Per day

| day | cap | now | ref | refday | vel14 | single | multi | free |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| jeudi | 8500 | 5979 | — | **none** | 321 | 1112 | 829 | 4038 |
| vendredi | 18000 | 15416 | 16370 | vendredi | 355 | 7487 | 6728 | 1201 |

## Totals

```

total now 40783 / cap 44500 = 91.6%
paid 26736  free 5360
one_day 24922  multi_day 7174
ref_tot 34404
```

## What each row asserts

- **`jeudi` has NO reference.** `bordeaux_2025` is Vendredi + Samedi. Under
  last-day-backward alignment (§5.6) Samedi→Samedi, Vendredi→Vendredi, and
  Jeudi is unmatched. §5.6 requires this to degrade honestly — name that the
  reference edition had two days and say no projection is possible. **Not a
  silent zero, and never `1 640`.**
- **`samedi` exceeds its capacity** — 19 388 against 18 000, 107,7 %. That is
  real, not an error: presence counts every ticket valid for that day including
  multi-day passes and invitations, and the configured `day_capacity` is a
  planning figure. The fixture is the right place to prove a >100 % day renders
  without breaking the bar.
- **`jeudi.free` is 4 038 of 5 979 — 68 % of Thursday's attendance is
  non-paying.** No other day is near that. It is the sharpest single argument
  for counting all days rather than defaulting Thursday out, and it only became
  visible once the day was counted.
- **`comp` differs per day.** The quarantined fixture had one identical block
  copied across all three.
- `ref_tot` is 34 404 — Vendredi + Samedi of the reference only, because Jeudi
  has no counterpart. It is not the reference edition's grand total.

## Regeneration

`dashboard_payload.py`, as its first output. **Not by hand** — see §6. Run
`verify/check_fixture_quarantine.py` after regenerating; it fails while the
fixture still carries epk's markers.
