# Co-hosting, 505434, and a correction to yesterday's Q4

**Written 2026-10-06 against commit `6c5fcb1`.** Markers as before: **verified
today** / **recorded** / **unknown**.

---

## First: I cannot re-probe, and I am not going to imply otherwise

**This session holds no credentials** — *verified today*: `SHOTGUN_TOKEN_EPISODE`,
`SHOTGUN_TOKEN_SONORA`, `SHOTGUN_ORGANIZER_ID_SONORA` and `DICE_TOKEN` are all
unset. I cannot make the call you asked for.

**What I did instead was go to the Actions archive**, which holds the raw output
of every probe this project has run. That turns out to matter more than a fresh
call would have, because **it overturns the premise on both sides.**

---

## ⛔ The headline: 505434 has NEVER been probed under Sonora with the co-host flag

The claim in `fetch_csv.py:95` — *"nothing under Sonora"* — comes from
**run 1, `31053170251`, 2026-08-05**. Here is its output verbatim, *verified
today from the job log*:

```
=== event 505434 ===
  episode  (org 171835): 100 tickets on page 1 (more pages: True) — event_name='MADAME LOYAL x SONORA : BORDEAUX'
  sonora   (org 207784): 0 tickets
```

**Look at what is missing: there is no `cohosted=` label on those lines.** Run 1
predates the co-host flag entirely. The flag was added *the next day*, by the
commit that produced run 2, whose message says why:

> EPK 2026 (535882) exists on Smartboard but returned nothing under either
> organizer. It is co-hosted, and Shotgun's tickets endpoint takes an
> `include_cohosted_events` parameter that **defaults to false** — so a
> co-hosted event owned by the partner returns an empty set indistinguishable
> from no sales.

**So the Sonora attempt on 505434 was made without the one parameter that exists
precisely for co-hosted events.** The conclusion has stood in a code comment for
two months on the strength of a probe that could not have found what you are
describing.

**And the flag is decisive on exactly this class of event.** *Verified today*,
run 2's log for 535882:

```
  episode  (org 171835) cohosted=0: 0 tickets
  episode  (org 171835) cohosted=1: 100 tickets on page 1 — event_name='MADAME LOYAL X ELEKTRIC PARK'
```

**0 → 100 tickets, from the flag alone.** On a co-hosted event, "0 tickets
without the flag" is a known false negative. That is the state 505434's Sonora
result is in.

---

## So: (a) or (b)? **Neither is established, and I would put a third first**

**(c) The existing conclusion is under-tested.** The decisive call —
505434, Sonora, `include_cohosted_events=1` — **has never been made.** Not in
any of the five probe runs.

That said, the archive does carry evidence bearing on (a), and it would be
unhelpful not to state it. **Every complete probe matrix this project has run**,
*verified today from the four job logs*:

| event | id | run / date | episode c=0 | episode c=1 | sonora c=0 | sonora c=1 |
|---|---|---|---|---|---|---|
| `bordeaux_2026` | 505434 | 1 · 08-05 | **100** | *flag not sent* | **0** | *flag not sent* |
| `epk_2026` | 535882 | 2 · 08-06 | 0 | **100** | 0 | **0** |
| `sonora_impact_2026` | 544355 | 3 · 08-18 | 0 | 0 | **100** | **100** |
| *Crazy Carnaval* | 549064 | 4 · 08-23 | **100** | **100** | 0 | **0** |

**Two events were probed under Sonora *with* the flag, and both returned 0 while
Episode returned 100** — 535882 and 549064. That is consistent with **(a)**:
`organizer_id` filters by owner, and the flag widens to co-hosts *of that
organizer*, not to events where you are the co-host.

**But it does not settle your case**, for a reason worth being precise about:
neither 535882 nor 549064 is known to be co-hosted *with Sonora*. 535882 is
co-hosted with Elektric Park. So those two rows show "Sonora cannot see an event
it has no relationship to", which is unsurprising and not the same claim.
**505434 is the only event where you are telling us Sonora genuinely has
visibility, and it is the only one never tested with the flag.**

**(b) is not excluded either.** Nothing in the repo records which Shotgun *user*
either token belongs to or what scope it was issued with — *unknown*, and
`ADDING_AN_EVENT.md` never asks.

### The one call that settles it

The workflow is dispatchable and takes an event list. Running
`probe-shotgun-account.yml` with `events: 505434` produces the four lines
directly — read-only, first page only, no writes. If Sonora + `cohosted=1`
returns tickets, it is **(b)** and the platform has been blamed for a credential;
if it returns 0, **(a)** is confirmed with the flag that makes it meaningful.

**Either way the code comment at `fetch_csv.py:95` should carry the real four
lines, not a paraphrase** — see the last section.

---

## ⛔ A correction to what I told you yesterday: we DO have a Crazy Carnaval id

**Yesterday I said we had never tracked `evt-cc` and held nothing for it. The
first half is true; the second is wrong.**

*Verified today, run 4 `32658474632`, 2026-08-23:*

```
=== event 549064 ===
  episode  (org 171835) cohosted=0: 100 tickets on page 1 (more pages: True) — event_name='Madame Loyal Paris - Crazy Carnaval Edition'
  episode  (org 171835) cohosted=1: 100 tickets on page 1 (more pages: True) — event_name='Madame Loyal Paris - Crazy Carnaval Edition'
  sonora   (org 207784) cohosted=0: 0 tickets
  sonora   (org 207784) cohosted=1: 0 tickets
```

| | |
|---|---|
| `shotgun_event_id` | **549064** |
| account | **`episode`** — probe-verified, both flag settings |
| event name | `Madame Loyal Paris - Crazy Carnaval Edition` |
| our config | still absent; we have never ingested it |

**Why I got it wrong, which is the part worth your attention.** I searched
`event_config.csv` and `fetch_csv.py`, found nothing, and reported nothing. The
repo genuinely does not have it. **The Actions archive did** — and
`ADDING_AN_EVENT.md` requires that a probe's output go into the commit, which
never happened for run 4. So the id existed, probe-verified, for six weeks, in a
place nobody would look.

**"Not in the repo" and "not known" are different claims and I conflated them.**
If you are relying on us as a reference, that is a failure mode to know about:
**our Actions logs contain findings our files do not.**

---

## Does any other event appear under both accounts?

**No event has ever returned tickets under both** — *verified today across all
four probe matrices.* Each of the four resolved to exactly one account, and the
`episode` and `sonora` event lists in `fetch_csv.py` are **disjoint** — *verified
today*.

So on the evidence we hold, **co-hosting has never produced API visibility from
two accounts.** Weak support for (a) — but note it is weak in a specific way:
**only four of our fourteen Shotgun-ided events have ever been probed at all.**
The other ten were assigned by assumption or by the `episode` default. If
co-hosting is common in your catalogue, our sample is too small to call it a
rule.

---

## Your framing is right, and the evidence sharpens it

You wrote that on a co-hosted event the wrong account is the one a person is most
likely to choose, because the sales are visible to them in the UI. **535882 is
that exact failure, already recorded here:** it is co-hosted, it returned
**0 tickets** under `episode` — its true owner — and only the flag revealed it.
Someone reading that zero would reasonably have concluded "wrong account" and
moved the mapping to Sonora, which would have produced a permanent silent zero.

Three compounding properties, all *verified today*:

1. `include_cohosted_events` **defaults to false**.
2. A wrong `organizer_id` returns **0 tickets, HTTP 200**.
3. `DEFAULT_SHOTGUN_ACCOUNT = 'episode'` — an unprobed event silently gets a
   guess.

**For Festiflow:** make the co-host flag non-optional in your client, and treat a
zero from a configured event as an alert rather than a value. Both are one line
and both are the difference between a wrong number and a visible failure.

---

## What I am changing on our side

Nothing yet — reporting first, as before. What I would propose:

1. **Re-probe 505434 with the flag** and put the four lines in the code comment,
   replacing the paraphrase. Until then, `fetch_csv.py:95`'s "confirmed by
   `probe_shotgun_account.py`" is **overstated**: that probe could not have
   tested the case.
2. **Write run 4's Crazy Carnaval result into the repo**, wherever
   `ADDING_AN_EVENT.md` says it should have gone.
3. **Probe the ten unprobed Shotgun-ided events**, since the account for each is
   currently an assumption with a silent failure mode.

Say the word on any of these and I will do them; none needs a decision from you,
but (1) needs a credential I do not have.

---

## Gaps

| gap | what would settle it |
|---|---|
| 505434 under Sonora **with** `cohosted=1` | one dispatch of `probe-shotgun-account.yml` with `events: 505434` |
| Which Shotgun user/scope each token was issued under | ask whoever issued them |
| Whether co-hosting ever grants API visibility to the co-host | the above probe is the first real test |
| The account for the other ten Shotgun-ided events | probe them |
| Whether `evt-cc`'s 549064 is still correct | it was 100+ tickets on 2026-08-23; unchecked since |
