# Event ids, accounts, and the four questions

**From `studio-ai2k/ticketing_api`, written 2026-10-06 against commit `79490c8`.**
Same confidence markers as the first handover — **verified today** / **recorded**
(dated probe in the repo, not re-run) / **unknown**.

Companion file: **`ticketing_api_event_ids.csv`** — 35 rows, generated from
`event_config.csv` and `fetch_csv.py` by script, not transcribed, because they
are ids.

---

## The two ids you are missing, first

**`evt-sb` is our `bordeaux_2026`.** *Verified today:*

| | |
|---|---|
| `shotgun_event_id` | **505434** |
| `dice_mio_id` | **540197** → `RXZlbnQ6NTQwMTk3` |
| account | **`episode`** — probe-verified |

**You have it as DICE "—". We have a DICE id for it.** Your table shows DICE
ids on three of nine; on our side `bordeaux_2026` is a fourth. It is also the
event with the external *reddition de comptes*, so if you want one event to
reconcile against an independent document, this is the one and now you can
address both halves of it.

**`evt-cc` (Crazy Carnaval): we have no id for it, because we have never tracked
it.** See Q4.

---

## The table

`ticketing_api_event_ids.csv`, 35 rows. Columns:

| column | meaning |
|---|---|
| `ticketing_api_slug` | our event id |
| `shotgun_event_id` | what we pass as `event_id`. **14 of 35 have one** |
| `dice_event_id_numeric` | what we pass as `dice_mio_id`. **7 of 35 have one** |
| `dice_event_id_base64` | the Relay id we actually send, derived |
| `shotgun_account_name` | **`episode`** or **`sonora`** — names only |
| `account_source` | `explicit list`, or `DEFAULT fallback — NOT listed` |
| `account_probe_verified` | the evidence, where the repo records one |
| `config_status`, `last_event_day`, `fetched_today` | aged out or live |

**Read `account_source` before trusting `shotgun_account_name`.** 21 of the 35
rows say `DEFAULT fallback — NOT listed`: they are archived events with no
Shotgun id, so the account was never established and `episode` is just the
fallback, not a finding. **For any row with no `shotgun_event_id`, the account
column is meaningless.**

**Only four assignments are probe-verified** — *recorded*:
`bordeaux_2026`, `epk_2026`, `bordeaux_oct_2026`, `sonora_impact_2026`.
`bordeaux_2025` and `halloween_2025` sit on the `sonora` list as an
**unverified assumption**; the code says so in as many words, because they only
matter if their reference CSVs are ever refetched.

**Currently fetched: 5 events** — *computed today*: `epk_2026`,
`bordeaux_oct_2026`, `geneve_2026`, `rennes_2026`, `sonora_impact_2026`.
`epk_2026` is at exactly 30 days past its last day and **ages out tomorrow**.

---

## 1 ⭐ How we resolve an event with no Smartboard/Mio link

**By hand, from the back office. There is no list endpoint in use, and the
public URL cannot give you the id.** *Verified today.*

I checked all three routes you named:

**By hand — yes, that is what we do.** `ADDING_AN_EVENT.md` documents writing
the id into `event_config.csv` as a manual step, and the only tooling around it
is `probe_shotgun_account.py`, which **takes the id as an argument**. It tells
you which account owns an id you already have. It does not find ids.

**From the public slug — no, and this is a firm negative.** *Verified today:*
**not one of our 13 public Shotgun URLs contains the numeric id.** They are all
slugs:

```
505434  ->  shotgun.live/en/festivals/madame-loyal-x-sonora
544355  ->  shotgun.live/events/sonora-x-impact
494642  ->  shotgun.live/en/events/madame-loyal-paris-xxl-2026
```

**And worse than absent — ambiguous.** `bordeaux_2026` (505434) and
`bordeaux_2025` (408231) have the **same public URL**,
`shotgun.live/en/festivals/madame-loyal-x-sonora`, because the festival page is
shared between editions. So a public link does not identify an event even in
principle: it identifies a festival, which may have several. **If `evt-cc`'s
public URL is a `/festivals/` one, it may not be resolvable to a single event at
all.**

**From a list endpoint — not in use, but there is a real lead and it is the best
thing I can give you.** *Recorded*, from endpoint discovery:

> **`GET /events` on `api.shotgun.live` returns 400, not 404** — while seven
> sibling paths return 404 from the same host in the same run. A 400 is a route
> that **exists** and rejected the request, "almost certainly for the same
> missing `token`/`organizer_id` that `/tickets` requires."

**We never called it with credentials.** The probe deliberately sends none to
discovery paths, so what it returns is **unknown**. But it is a route that
exists, on an API with no published index, and one authenticated call would
settle it.

> **If you are going to make one exploratory call for this project, make it that
> one.** If `GET /events?token=…&organizer_id=…` returns an account's events with
> their ids, Festiflow never stores a Shotgun id — it stores an account, which is
> exactly the design you said you wanted. We would also take the answer.

**On the DICE side the equivalent is better documented but also unused.**
*Recorded:* the introspection dump shows `viewer` carries `orders`, `returns`
and `ticketTransfers`, all event-scopeable. **Whether `viewer` also exposes an
events collection I did not check** — one line would settle it: grep the
introspection dump we sent you for a field named `events` on the `Viewer` type.
I would do it before assuming the DICE id must be stored either.

---

## 2 ⭐ Does the account split follow the production company? **Yes — and your default is right**

**The producer decides. Branding does not.** *Verified today against the code,
and the decisive case is the one you nominated.*

`evt-sb` = `bordeaux_2026`: branded **Sonora** (our config's `brand` column says
`Sonora`), produced by **EPISODE** on your side — and we query it under the
**`episode`** account. Not Sonora.

That is not an accident of our config. It is **probe-verified and the code warns
against "correcting" it** — *recorded*, `fetch_csv.py:95`:

> `bordeaux_2026` (505434) lives on Episode despite the ML x Sonora branding —
> confirmed by `probe_shotgun_account.py`, which got
> `event_name='MADAME LOYAL x SONORA : BORDEAUX'` under organizer 171835 and
> nothing under Sonora. **Do not "correct" it back by brand.**

And `ADDING_AN_EVENT.md` makes it a rule, in its heading: **"VERIFY THE SHOTGUN
ACCOUNT. Do not infer it from the promoter."**

Checked across every event where your table and ours overlap — *verified today*:

| your event | producteur | marque | our account |
|---|---|---|---|
| `evt-sb` → `bordeaux_2026` | EPISODE | **Sonora** | **episode** |
| `evt-ep`, `evt-px`, `evt-rn`, `evt-gv` | EPISODE | Madame Loyal | episode |
| `evt-sh` → `bordeaux_oct_2026` | **SAGREGA** | Sonora | **sonora** |
| `evt-si` → `sonora_impact_2026` | **SAGREGA** | Sonora | **sonora** |

**EPISODE → `episode`, SAGREGA → `sonora`, with brand cutting across both.** Your
default is correct and `evt-sb` confirms it rather than breaking it.

**Three cautions before you rely on it.**

1. **It is a correlation over four verified events, not a stated rule.** Nobody
   at Shotgun told us producer determines account; we observed it. The account
   name `sonora` not matching the producer name SAGREGA is a hint that the
   account was named for a brand at some point.
2. **Two entries are assumptions.** `bordeaux_2025` and `halloween_2025` are on
   the `sonora` list **unverified** — the code says so.
3. **The failure is silent.** A wrong account returns **0 tickets, HTTP 200**.
   So "our default worked" and "our default was never wrong" are not the same
   observation. **Probe each new event before trusting the default**, the way
   `ADDING_AN_EVENT.md` requires — it costs one read-only call.

---

## 3 · DICE coverage is partial on our side too

**Confirmed — build for partial.** *Verified today.* Of our 5 currently-fetched
events, **2 have a DICE id**:

| event | DICE | how |
|---|---|---|
| `rennes_2026` | **600413** | API |
| `epk_2026` | **573271** | API |
| `geneve_2026` | **none** | **hand export, committed as a CSV** |
| `bordeaux_oct_2026` | **none** | Shotgun only |
| `sonora_impact_2026` | **none** | Shotgun only |

**Genève is the case you asked about, and it is worse than "stale" — it is a
different mechanism.** *Recorded:* `probe_dice_event.py` against DICE id 588085
got `node -> null` and 0 orders on the token that fully resolved Rennes and Paris
XXL, so the repo concluded **an account boundary, not a bad id**. Those sales are
exported from the DICE back office by hand and committed as a CSV
(`MANUAL_DICE_CSVS`), which the code itself calls "a stopgap".

**So on our side the DICE gap has two different causes** and you will meet both:
an event genuinely not sold on DICE, and an event sold on a DICE account the
token cannot reach. **They look identical from the API** — both are zero. The only
thing that distinguishes them is someone knowing.

**Do not infer DICE coverage from a missing backend URL.** `rennes_2026` has a
working `dice_mio_id` and **no public DICE link stored at all** — *verified
today* — so absence of a link means nothing in either direction.

---

## 4 · Crazy Carnaval — no, we have never tracked it

*Verified today:* **`evt-cc` appears in neither `event_config.csv` nor
`fetch_csv.py`.** No slug, no id, no account mapping, no stored data. It was
raised once in our queue as an event to add and never landed.

**So yes — it would be the first event Festiflow pulls that we never have, and
there is no cross-check available for it from us.** Worth saying plainly since
you are using us as the reference: for `evt-cc`, agreement with our numbers is
not a test you can run.

**And there is a second one.** `evt-croisiere` (Shotgun **553118**) is also
absent from our config — *verified today*. That one is deliberate: it was ruled
**"no dashboard"** on our side. The id you hold is good; we simply do not pull
it. So of your nine real events, **we cover seven**.

---

## What I would check first, in your position

1. **Make the authenticated `GET /events` call.** It is one request and it either
   removes stored Shotgun ids from your design entirely or closes the question.
2. **Grep the introspection dump for an events collection on `Viewer`** before
   assuming DICE ids must be stored.
3. **Probe the account for `evt-cc` and `evt-sb` before the first real pull** —
   `evt-sb` we can confirm as `episode`, `evt-cc` nobody can.
4. **Reconcile on `bordeaux_2026`**, now that you have both ids. It is the only
   event with an independent statement, and it reconciled to one ticket in 9,327
   on the DICE side.

---

## Gaps in this answer

| gap | what would settle it |
|---|---|
| What `GET /events` returns | one authenticated call |
| Whether DICE's `Viewer` exposes an events collection | grep the introspection dump |
| Whether producer→account is a **rule** or our four-event correlation | ask Shotgun, or probe a fifth |
| The account for `bordeaux_2025` / `halloween_2025` | `probe_shotgun_account.py` on 408231 / 433590 |
| Anything about `evt-cc` | we hold nothing |
| Whether `evt-cc`'s public URL is a `/festivals/` one | you hold it; if so it may not resolve to one event |
