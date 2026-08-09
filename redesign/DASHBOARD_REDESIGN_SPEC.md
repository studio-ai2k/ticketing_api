# DASHBOARD REDESIGN — SPEC

**For:** CC2, `studio-ai2k/ticketing_api`
**Reference build:** `mock/dashboard_v3.39.html` — password `festipass`
**Status:** not approved to build. §1 and §2 need your answer first.

**The mock is the spec for everything visual.** It is a complete, working,
single-file dashboard running on real figures from `data/epk_2026_merged.csv`
and `csv_database/epk_2023/`. Layout, spacing, type, colour, interaction and
copy are all settled there — this document does not restate them.

What this document carries is what the mock *cannot* say: where the data comes
from, why each derivation was chosen, what each card must survive, and how to
verify it.

---

## 1. THE RULE THAT MATTERS MOST — prove, or observe

**No figure may silently disagree with production.**

We learned this the hard way twice.

Auditing the mock we found different cards anchoring the 2023 comparison on
different dates — 1 September in some, 2 September in others — and "fixed" it by
standardising on `event_date_first`. **That fix was wrong.** As you established
in DD5, run.py already uses `event_config_prev['event_date_first']` everywhere;
the 1-vs-2 September difference is `_prev_match_dow` snapping to the same
weekday for the daily grain while the weekly grain buckets with no snap.
Verified independently: offset 1099, and 2026-09-05 Saturday − 1099 =
2023-09-02 Saturday. The snap is the point, not a bug.

**But "never recompute" is too blunt a rule, and you have already written the
right one.** `scripts/suivi_candidates.py` states it in its own header:

> the series is `is_paid == 1` grouped by `order_date` — literal columns of the
> merged CSV, run.py's classification never enters. The daily offset is a
> closed form over `event_date_first`, **proven equal** to `_prev_match_dow`
> rather than reimplementing its traversal, and checked exhaustively by
> `verify/check_offset.py`.

So the rule this redesign must follow:

> **Recompute only what is either (a) a literal column of the merged CSV,
> (b) a closed form proven equal to run.py's own function and pinned by a
> negative-tested check, or (c) run.py's own function, imported and called.
> Everything else is observed.**

That is what makes `suivi_candidates.py` safe without touching run.py, and it
is the standard every figure in §5 must meet.

**Route (c) is new, and it is stronger than (b).** A proven-equal closed form
can drift the day run.py changes; an imported function cannot, because it *is*
the function. It is available whenever run.py's helper is module-level and pure
— takes plain values, returns a value, touches no globals. Two qualify and both
are used below:

| function | signature | why it is safe |
| --- | --- | --- |
| `run.resolve_attendance` | `(ticket_type, attendance_days, day_names)` | three literal CSV columns in, presence map out |
| `run.filter_tickets_to_same_point` | `(tickets_prev, cutoff_cur, event_cur, event_prev)` | ticket dicts and three dates; plain J−X, no weekday snap |

Importing `run` is already how `build_dashboard.py` works, so this adds no new
coupling. **Prefer (c) over (b) whenever it is available** — a reimplementation
that has to be proven is a liability that a call is not. Reserve (b) for cases
like the daily offset, where the traversal cannot be called in isolation.

**Two grains, two mappings.** Your header also records something our earlier
spec missed and this one must not: the daily table snaps to the weekday
(constant offset) while the weekly table buckets each side by its own
`event_date_first` with no snap. **A candidate carries both `offset` and
`first`.** Any card comparing across editions has to declare which grain it is
on.

## 2. MECHANISM — the pattern already exists

**Answered by the mirror; confirm rather than choose.**

The redesign needs a payload run.py does not emit (§4). `run.py` is
do-not-modify. You have already solved this twice:

| file | role |
|---|---|
| `scripts/suivi_candidates.py` | standalone payload builder — reads the merged CSVs, uses literal columns plus proven closed forms |
| `scripts/build_dashboard.py` | wraps `run._generate_suivi_v3` to **observe** (and now clamp) the anchors run.py itself passes |
| `scripts/suivi_selector.py` | injects the payload and renderer in postprocess |

**Our proposal: extend this pattern rather than invent one.** A
`scripts/dashboard_payload.py` alongside `suivi_candidates.py`, emitting the
§4 contract, consumed by a new postprocess pass.

**What we need from you** is not a choice but a check: does every field in §4
meet the §1 standard under that pattern, or does any of it need an
observe-wrapper because it cannot be proven from the CSV alone? The candidates
we are least sure of:

- **per-day presence** — needs run.py's day mapping, which DD4 is changing
- **projection curves** — need the reference's per-day series at matched J−X
- **`vel` windows** — trivially derivable, but must agree with what the current
  card shows to the ticket

**Answered.** None of the three needs an observe-wrapper; two need route (c) and
one needs the DD4 result:

| field | route |
| --- | --- |
| per-day presence | **(c)** `run.resolve_attendance`. The prose rule in §5.3 was measured against production and is 2 short per day — see §5.3. |
| projection curves | **(c)** for the same-point filter, plus the DD4 mapping, which lands first |
| `vel` windows | **(a)**, but only once the cutoff is observed — see below |

**A fourth field needs observing and was not on the list: `cutoff_date` itself.**
Since `5d71c80` the Suivi cutoff is clamped to `event_date_last + 1`
(`build_dashboard._clamp_cutoff`). On `paris_xxl_2026` the raw
`max(order_date) − 1` is **29 March** and the clamped value is **15 March**. Any
payload that recomputes the raw form puts its vélocité windows fourteen days
away from the Suivi table on the same page, and nothing would say so. **Read the
clamped value from the `.suivi.json` sidecar; never recompute it.**

## 3. STAGING — build to a subdirectory, not a branch

Do **not** develop this on a feature branch. GitHub Pages serves one branch, so
a branch gives no live preview — you would be merging blind on the largest
change this project has made.

Generate the redesign alongside production:

```
ai2k.dev/ticketing_api/epk.html         ← production, untouched
ai2k.dev/ticketing_api/v2/epk.html      ← redesign, real data, live
```

The workflow already publishes the whole repo, so this costs one extra output
path. Production keeps running its existing passes; the redesign runs its own
into `v2/`. Leo reviews on real data, on a phone, at every stage, with zero
risk to the live link. When it is right, the swap is one output path.

This also removes the one-shot-versus-stages question: build it in one pass and
still stage the review, because nothing is live until Leo says so.

---

## 4. PAYLOAD CONTRACT

Shape the mock consumes. Field names are ours and negotiable; the *content* is
not. Read §1 before deciding where each value comes from.

```js
D = {
  cap, daycap, jx, vat, cur_year, ref_year,

  cur: { n, inv, rev, avg,
         plat: { "Shotgun": [tickets, faceTTC, grossPaid], ... },   // 3 elements
         vel:  { "3":n, "7":n, "14":n, "30":n } },
  ref: { n, rev, vel: {...} },              // n === 0 ⇒ no comparison
  ref_final: { n, rev },                    // the reference's FINAL totals

  daily:  [ { jx, a, b, ra, rb, ca, cb, rca, rcb, fut } ],
  weekly: [ { w, a, b, ra, rb, pa, pb, ca, cb, sa, ea, sb, eb, fut } ],

  presdays: { days: [ { k, label, date, cap, now, ref, vel14,
                        comp: { single, multi, free } } ],
              paid, free, one_day, multi_day, ref_tot },

  rep: { groups: [ { g, n, pct, rev, p, kids: [...] } ], tot, avg, rev },

  projx: { default, jx, curdays,
           cands: { "<key>": { label, ref, refdays,
                               days: [ { day, cap, now, vel14, refday,
                                         coef, refvel,
                                         s1: {tot,date}, s2: {tot,date},
                                         chart: { act, ref, p1, p2 } } ] } } },

  meta: { cur: {...}, ref: {...} }          // Détails page
}
```

**Contract notes that are not cosmetic:**

- `plat` is `[tickets, faceTTC, grossPaid?]`. **The third element is OPTIONAL.**
  `cur.plat` carries it; `ref.plat` does not — the mock ships
  `"ref":{...,"plat":{"Shotgun":[7266,393120]}}`. Consumers fall back to
  `paid = face` when it is absent, which `moneyBar()` already does; the contract
  simply never said so. A consumer that assumes three elements renders
  `undefined`, which §6 forbids.
- `ref.n === 0` is the sole signal for "no comparison". Everything keys off it.
- `projx.cands` is a map, so the selector's candidate list is data, not code.
- **`cutoff_date` is an OBSERVED field, not a derived one.** It comes from the
  `.suivi.json` sidecar written by `build_dashboard.py`, and it is the *clamped*
  value. `paris_xxl_2026`: raw 29 March, clamped 15 March. Recomputing
  `max(order_date) − 1` here would put the vélocité windows a fortnight away
  from the Suivi table on the same page.
- **No warm-up field.** Jeudi is a warm-up in fact and is not modelled: no flag,
  no config column, no badge, no persisted per-day state. See §5.3.
- `presdays.ref` and `projx.*.refday` consume the DD4 mapping and are blocked
  until it lands. They are not to be reimplemented here.

---

## 5. CARD BY CARD

For each: what it must show, how each figure is derived, and what it must
survive. **Layout is in the mock.**

### 5.1 Revenus

Face value TTC as the headline, net HT beneath it, then three blocks — Billets,
and one per platform — each a stacked bar with a legend.

**`gross_price` is read, never derived.** The card originally computed
`face × 1.1303`. That was wrong by €22 and would have needed a code edit the
moment O1 resolves. It now reads the summed `gross_price` and derives the
*rate* from it (`mult = paid / face`), so when the Shotgun formula changes the
card follows with no code change. **Preserve this.**

**Semantics, settled by the DICE payout statement** you reconciled to the cent:

```
price       = valeur faciale TTC — what the promoter receives, VAT included
gross_price = what the buyer paid — face + booking fee
net HT      = face / 1.055
```

**Copy:** the section note reads *"valeur faciale TTC · hors frais de
réservation"*. It deliberately does **not** claim a deduction, because on DICE
there is none. Do not restore the old wording.

**The provenance footnote is required**, not decoration: DICE marked *vérifié*,
Shotgun *à confirmer*. Presenting both with equal confidence is the thing we are
avoiding.

**Open:** the "prix affiché" ambiguity (your DD1 note). The mock currently says
*"prix affiché à l'acheteur"*. Whichever way Leo rules, mock and production
change together.

### 5.2 Vélocité

Three rates in a row — **actuel / requis / reference** — then a sentence
projecting the current pace to the event, then 3j and 14j windows each with
their own rolling curve. 7j and 30j behind *Autres fenêtres*.

The old card was four blocks of three columns with no trend. A velocity figure
without its curve is a number without a verb: `−53,5% vs 2023` on the 3-day
window looks like a collapse until the curve shows 2023 had its own late surge.

`Rythme requis = ceil((cap − sold) / jx)`.

### 5.3 Présence par jour  *(merges the old Présence + Par Jour)*

Total as the head with a stacked bar, then one block per day, each with a
**toggle to exclude that day from the total**.

**Excluding a day removes its capacity as well as its attendance.** Samedi alone
must read 8 087 / 10 000 at 80,9%, not 8 087 / 20 000 at 40%. Getting this
wrong halves every percentage.

**Day coverage: call `run.resolve_attendance`. Do not reimplement it.**

```python
from run import resolve_attendance
presence = resolve_attendance(ticket_type, attendance_days, day_names)
```

Route (c) of §1. All three arguments are literal columns of the merged CSV.

*The description below is why the rule is not trivial. It is a description, not
a specification — the function is the specification.*

Two signals are both needed. `attendance_days` when populated (bordeaux's
`['vendredi','samedi']` correctly excludes Thursday); `ticket_type` otherwise
(**epk's multi-day passes have `attendance_days` empty on 2 501 of 2 557 rows**
— the other 56 carry `['samedi','dimanche']`). A rule using only
`attendance_days` drops **2 501** epk tickets; a rule using only `ticket_type`
cannot know a bordeaux 2-jours pass skips Thursday.

**But knowing that is not enough to reproduce production.** Implemented exactly
as those two rules read, the result is **8 085 / 4 513**. `resolve_attendance`
gives **8 087 / 4 515**, which is what the live page shows. Two tickets per day,
from cases the prose does not name. That gap is the entire argument for route
(c): a rule you can describe correctly and still implement wrong is a rule you
should call rather than restate.

**No warm-up badge, and no warm-up concept.** Jeudi is a warm-up in fact; that
is not modelled in the product. No flag, no config column, no badge, no per-day
state to persist. **Do not build any.**

run.py's inference — matching the literal string `'jeudi'` on a 3+ day event —
is removed. It flags a Thursday that is not a warm-up and misses one held on any
other weekday. Removing it is what makes "counted everywhere" uniform rather
than event-specific.

- **All days are counted, everywhere, by default**, including this card's own
  headline. Bordeaux opens on **40 783 / 44 500 = 91,6 %**.
- The per-day toggle is a **session-only viewing control**. Switch days off to
  read the total for the days you want. A quick read, nothing more.
- It affects **this card's total and capacity only**. Not revenue, not
  vélocité, not projections, not répartition.
- Excluding a day removes its capacity as well as its attendance. That is what
  makes the quick read meaningful.

**Deliberate behaviour change, on the corrected figure.** Production shows
bordeaux at **34 804 / 36 000 = 96,7 %** with Thursday excluded. The redesign
shows **40 783 / 44 500 = 91,6 %** with all three counted. That is **+5 979
attendance and −5 points of fill rate** against the live page. Leo has ruled to
keep it.

> An earlier draft put this as 34 266 / 44 500 — a *decrease* of 538 against
> production, which is why leaving it looked harmless. **The sign was
> backwards.** 34 266 does not reproduce from any rule; measured with
> `resolve_attendance` the three days are 5 979 / 15 416 / 19 388 = **40 783**,
> and 34 804 is exactly Vendredi + Samedi. Capacities confirmed from
> `event_config.csv`: 8 500 + 18 000 + 18 000 = 44 500, and 36 000 is where
> production's denominator comes from.

**No time component.** Arrival hours are not in the consolidated CSV.
`event_start_time` and `ticket_scanned_at` would give it; neither is fetched.
A section explaining missing data was removed rather than shipped.

### 5.4 Répartition des billets

Expandable groups, five columns: Billets / % / Revenu / Prix méd.

**The last group is a CATCH-ALL.** Any `access_level` not matched by an earlier
bucket lands there. `invitation` is unmapped on 10 of 12 events and only
reconciles today because those rows happen to be `is_paid = 0`. One paid
invitation and it would vanish from the table while still counting in the
Total. Verified by injecting seven paid tickets on an unmapped level.

Gratuits keeps production's three buckets — Invitations / Jeu concours /
Groupes — rendered even at zero.

`early_entry` and `group_discount` get their own labelled rows. Previously they
were silently folded into "Billets Réguliers"; paris_xxl has 4 029 early-entry
and bordeaux 2 079.

Header reads **Prix méd.**, not "Prix Ø" — it is a median, and on a skewed
price ladder that is a different number from the mean.

### 5.5 Suivi des ventes

Unchanged in substance from what ships today: two grains, three blocks each
(past scrollable, current, future), both header sets, the `Précédent` and
`À venir` separators, all four buttons, the `Aujourd'hui` marker, and the
comparison selector.

Weekly rows keep their own structure — `%` and `% cumulé` plus `€Nk` where the
daily row has `Cumulé N`. **Do not apply the daily layout to weekly.** Reusing
the daily renderer once left the previous candidate's percentages under the new
candidate's name.

### 5.6 Projection Finale

One card per day, two scenarios each, an event selector, and the cumulative
%-capacity curve **behind an accordion** (per Leo — the card is 378px collapsed
against ~780px open).

**Days map by POSITION, aligned from the LAST day backward.** This is the DD4
fix. **Route 1** — re-keying the previous edition's day keys into the current
edition's names before run.py reads them — is the mechanism; one rename covers
all three sites (`run.py:1921`, `:2881`, `:3514`) and they cannot desynchronise
because there is only one of them. The redesign consumes the result and does not
implement its own mapping.

**Forward day-1-to-day-1 is wrong when the editions have different day counts,
and it would regress a comparison that is correct today.**

```
bordeaux_2026   Jeudi 11 Jun 8 500 | Vendredi 12 Jun 18 000 | Samedi 13 Jun 18 000
bordeaux_2025                       Vendredi 13 Jun 18 000 | Samedi 14 Jun 18 000
```

Forward gives Jeudi (8 500) → Vendredi (18 000) — wrong day *and* wrong
capacity — Vendredi → Samedi, and Samedi → nothing, which suppresses the
projection on the largest day. Backward gives Samedi → Samedi, Vendredi →
Vendredi, Jeudi unmatched, which is what name matching already produces.

**Equal counts are unaffected: forward and backward are the same mapping.**
Across all six `compare_to` pairs the rule changes exactly one page:

| pair | shape | result |
| --- | --- | --- |
| `paris_xxl_2026` → 2025 | Ven+Sam vs Ven+Sam | no change |
| `bordeaux_oct_2026` → halloween_2025 | Ven+Sam vs Ven+Sam | no change |
| `rennes_2026` → 2025 | Ven+Sam vs Ven+Sam | no change |
| **`epk_2026` → epk_2023** | **Sam+Dim vs Ven+Sam** | **FIXED — the actual bug** |
| `geneve_2026` → 2025 | Ven+Sam vs Sam only | Sam→Sam, Ven unmatched = today |
| `bordeaux_2026` → 2025 | Jeu+Ven+Sam vs Ven+Sam | Sam→Sam, Ven→Ven, Jeu unmatched = today |

**Bordeaux and geneve are regression canaries. If DD4 changes any bordeaux or
geneve figure, the mapping ran forward.** Assert that.

**Assert the shape, do not assume it.** Both unequal cases here extend at the
*front* — bordeaux added a Thursday, geneve added a Friday — which is why
backward alignment fits. An edition that adds a day at the **end** would break
the rule. Fail loudly rather than mapping silently.

**What moves on epk.** Dimanche gains a real reference for the first time —
2023's **Samedi**, 6 766. Samedi's reference becomes 2023's **Vendredi**,
3 866, down from the 6 766 it gets today by name-matching, because it now
compares our opening day to their opening day rather than to their closing day.

> An earlier draft named 2023's Samedi as Dimanche's *new* reference while also
> calling it Samedi's *old* one. Both cannot be true. Dimanche's new reference
> was right; Samedi's old figure was given as 7 708 and is **6 766** — measured
> from `csv_database/epk_2023/` at J−29 via `resolve_attendance`, and confirmed
> by the mock's own payload, which carries `samedi ref 3 866`,
> `dimanche ref 6 766`, `ref_tot 10 632`, and 3 866 + 6 766 = 10 632 exactly.

**A reference with fewer days must degrade honestly** — name how many days that
edition had and say no projection is possible. Not a silent zero.

The chart is cumulative % of the day's capacity, four series, and the
projection **continues** the actual line — last actual 80,8%, first projected
80,9%. Not a second line beside it.

### 5.7 Détails page

Five sections: Événement, Jours de l'événement, Comparaison, Plateformes,
Données. Nothing from the current page removed.

**Comparaison** documents the matching method — axis, position mapping, the ±3
weekday snap — and explains in prose why day 1 maps to day 1. That is where
someone will look when the numbers surprise them.

**Données** is new: platform count, days of data, best day, VAT rate, then a
field glossary (`price`, `gross_price`, `order_datetime` UTC, `attendance_days`,
`access_level`), and the statement that jauge and dates come from
`event_config.csv` and never from the APIs.

**Backend URLs are derivable**, both currently wrong in production:

```
Shotgun  https://smartboard.shotgun.live/events/{shotgun_event_id}
DICE     https://mio.dice.fm/events/{base64("Event:"+dice_mio_id)}/overview
```

---

## 6. WHAT EVERY CARD MUST SURVIVE

Four fixtures ship with this package. All four must render with **zero console
errors, no `NaN`, no `undefined`, no unresolved `${...}`, and no horizontal
scroll** at 1100px and 393px.

| fixture | what it exercises | status |
|---|---|---|
| `dashboard_v3.39.html` | baseline — 2 days, comparison, 2 platforms | ok |
| `fixture_1day.html` | single-day event | ok |
| **`fixture_3day.html`** | 3 days, unequal capacities, a sold-out day | **QUARANTINED — see below** |
| `fixture_no_comparison.html` | first edition — `ref.n === 0` | ok |
| `fixture_single_platform.html` | one platform only | ok |

### `fixture_3day.html` is quarantined, and it is worse than "wrong numbers"

It is **not a bordeaux fixture with stale figures. It is epk's payload wearing
bordeaux's day names.** Inspected field by field:

| field | fixture says | bordeaux actually |
| --- | --- | --- |
| `presdays.days[*].now` | 1 916 / 14 189 / 18 161 = **34 266** | 5 979 / 15 416 / 19 388 = **40 783** |
| `presdays.days[*].comp` | `{single:5528, multi:2559, free:4}` on **all three days**, identical | differs per day; jeudi is `{single:1112, multi:829, free:4038}` |
| `presdays.paid` / `free` | 10 039 / 4 | **26 736 / 5 360** |
| `presdays.ref_tot`, `one_day`, `multi_day` | 10 632 / 7 482 / 2 557 | all epk values |
| `jeudi.ref` | 1 640 | bordeaux_2025 **has no Jeudi** |
| `projx.cands` | `{"epk_2023": {label:"EPK 2023", …}}` | should be bordeaux_2025 |
| `projx…s1.date` | `2026-09-01` | bordeaux is 11–13 **June** |
| `projx…refday` | jeudi → `vendredi` | the forward mapping §5.6 rules out |

`presdays.days` sums to 34 266 while `presdays.paid` says 10 039 — the fixture
is not internally consistent with itself, let alone with any event.

**It must not be repaired by hand.** Hand-authoring a payload from partly-real
figures is exactly how this file came to exist, and a half-patched fixture —
real `presdays`, epk's `projx` — would look regenerated and pass §7 while still
being meaningless. That is START_HERE §5 again, one level up.

**It is regenerated by `dashboard_payload.py`, as that builder's first output.**
Until then `verify/check_fixture_quarantine.py` fails if it is used for
acceptance, and **a green §7 run that includes it means nothing for the
three-day case.**

The authoritative target figures are in `redesign/FIXTURE_3DAY_TARGET.md`.

**The no-comparison case is the one to take seriously.** Before it was
implemented the redesign did not crash — it printed **`+16 000,0% vs 2023`**,
because `B.vel || 1` divided by one. No error, no `NaN`, every number
confidently wrong. There is no first-edition event today, so this would have
shipped unnoticed until one appeared.

Per-card behaviour without a comparison is in the mock; the short version is
that comparison elements disappear rather than showing zero, and **Revenu
projeté is suppressed entirely** — a projection replaying a campaign that never
existed is not a projection.

---

## 7. ASSERTIONS

Per generated file:

```
no NaN / undefined / Infinity / ${ in rendered text     == 0
scrollWidth == viewport at 1100 and 393                 pass
console errors                                          == 0
platform blocks           == number of platforms in the data (1, 2, …)
day blocks                == number of configured days (1, 2, 3)
répartition group sum     == total rows        (catch-all makes this exact)
presence per day          == production's own figure, per day
```

**Derive, never hardcode.** Every count above is shape-dependent. We have
written three assertions in this project that counted a CSS selector as if it
were markup — `.ac-t`, `.inset-divider`, `.det-footer`. If a number disagrees
with generated output, assume the spec counted the stylesheet.

**And `verify/` is a consumer.** The pass table's SCOPE note covers this:
anything that greps generated output is in the dependency graph. The redesign
restructures the entire page body, so `assert_redesign.sh`, every `check_*.py`
and `stamp_footer.py` must be grepped for strings this change destroys —
before it lands, not after. Deploy 3 §7 broke two of these and neither was a
pass.

**And run every new check against the broken artefact first**, per
`verify/CHECKLIST.md`. The `check_suivi_window.py` case is the precedent: a
check written minutes after reading the cause still could not see the bug.

**Run `verify/check_fixture_quarantine.py` before any acceptance run.** While it
fails, `fixture_3day.html` is not evidence of anything and the three-day case is
uncovered.

---

## 8. OPEN — needs Leo, not you

1. **O1** — a Shotgun payout statement. DICE is settled.
2. **"Prix affiché"** — the DD1 ambiguity. Mock and production change together.
3. **Mobile type floor** — mock matches production (9/10/11/11/12/13px, 878
   elements under 12px at 393). Leo has ruled to keep it matched.
4. **Rename `--sg-green` / `--dice-blue`** — they are now violet and amber.
5. **Suivi's page** — stays on Billetterie for now; Campagne is still an idea.

---

## 9. WHAT WE ARE NOT ASKING FOR

- **Not the Campagne page.** Separate concept, `mock/campagne_mock.html`.
- **Not a run.py rewrite.** §2 is a question about mechanism, not licence.
- **Not the DD4 fix itself** — that is its own change, and the redesign should
  consume it rather than duplicate it.
