# Shotgun `ticket_status`, `deal_channel` and provenance — the observed values

**Recovered from Actions run `31055925893`, 2026-08-05.** This output was never
committed, so for two months the repo said these values were unknown while a
complete enumeration sat in a run log. See `ARCHIVE_AUDIT.md` for the others.

Probe: `probe_shotgun_channels.py`, cross-tabbing `deal_channel` against
`ticket_status`, plus `utm_source`, `payment_method` and `deal_visibilities` per
channel. 27,217 raw tickets on `bordeaux_2026`, 1,366 on `rennes_2026`.

## ⛔ `ticket_status` — five observed values, not one

`bordeaux_2026` (505434), 27,217 raw tickets:

| channel | status | count |
|---|---|---:|
| `online` | `valid` | 17,409 |
| `online` | `resold` | 4,217 |
| `online` | **`payment_plan_pending`** | **20** |
| `online` | **`refunded`** | **9** |
| `invitation` | `valid` | 5,358 |
| `invitation` | **`canceled`** | **204** |

`rennes_2026` (557151): `online` only — `valid` 1,312, `resold` 54.

**`SHOTGUN_VALID_STATUSES = ('valid',)` therefore excludes four things, and
until now only one of them was written down:**

| status | what it is | our treatment | was it documented? |
|---|---|---|---|
| `resold` | the marketplace flip; the buyer gets a fresh `valid` row | excluded — counting both double-counts one physical ticket | **yes**, in `fetch_csv.py` |
| `refunded` | a refunded ticket | excluded | **no** |
| `canceled` | a cancelled ticket — **204, all on `invitation`** | excluded | **no** |
| `payment_plan_pending` | an instalment plan not yet complete | excluded | **no** |

All four exclusions are correct for "tickets sold". What was missing was that
**they are distinguishable at all**: the repo described the other statuses as
unenumerated, so nobody knew a pending-payment state existed, let alone that it
is 20 tickets on one event.

**`payment_plan_pending` is the one to watch.** It is neither a sale nor a
non-sale — it is a sale in progress, and a ticket can presumably move from it to
`valid`. A figure that counts only `valid` therefore lags instalment buyers.
Whether that matters is a ruling nobody has been in a position to make.

## `deal_channel` — two observed values on these events

| channel | bordeaux_2026 | rennes_2026 |
|---|---:|---:|
| `online` | 21,655 | 1,366 |
| `invitation` | 5,562 | — |

`SHOTGUN_ORGANIC_CHANNELS` also lists `onsite`, and
`SHOTGUN_KNOWN_IMPORT_CHANNELS` lists `distributor`, `offline`, `reseller`,
`duplicata`. **None of those six appeared in this probe.** They are either rare,
event-specific, or inherited from documentation rather than observation —
**unknown which**, and worth knowing before relying on the import-channel filter.

## Provenance fields — values, not just names

**`utm_source`** (`online` channel): `shotgun` 14,879 · `direct` 3,645 ·
`google` 1,756 · `instagram.com` 707 · `cz4e3.r.ag.d.sendibm3.com` 172 ·
`code-promo-v-2` 136. On `rennes_2026` the same field spells Instagram **`ig`**,
not `instagram.com`, and carries `reel-tfq`.

> **It is a free string, not an enum**, and the same source is spelled two ways
> across two events. Anyone grouping by it needs a normalisation table.

**`payment_method`**: `card` 20,981 · `(none)` 481 · `revolut_pay` 188 ·
`bancontact` 5. Invitations are `(none)` throughout, which is consistent.

**`deal_visibilities`**: `public,xpress_door,promoters` 20,350 ·
`promoters,public,xpress_door` 1,295 · `private` 10.

> **The same set is serialised in two different orders** — `public,xpress_door,
> promoters` and `promoters,public,xpress_door` — so it must be parsed as a set,
> never string-compared. 1,295 tickets would be mis-bucketed by an equality test.

## What this changes

Nothing in the pipeline: `valid`-only was already right, and the fetcher already
sends the co-host flag. What changes is what can be **stated**:

- the handover to Festiflow said pending / failed / test orders were "unknown"
  on the Shotgun side. **Three of the four are now named**, and the correction is
  carried in `handover/FESTIFLOW_INGESTION_HANDOVER.md`.
- test orders remain **unknown** — no status observed looks like one.
