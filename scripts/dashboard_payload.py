#!/usr/bin/env python3
"""
Build the redesign's `D` payload from the merged CSVs. Standalone, per §2.

    python scripts/dashboard_payload.py --event epk_2026 \
        --csv data/epk_2026_merged.csv --cutoff 2026-08-06

Follows §1's prove-or-observe rule. Every figure here is one of:

  (a) a literal column of the merged CSV - counts, is_paid, price, gross_price,
      access_level, order_date;
  (c) run.py's own function, imported and called - `resolve_attendance` for day
      coverage, `filter_tickets_to_same_point` for the reference cut.

Nothing is reimplemented from run.py, and nothing is recomputed that
`build_dashboard.py` already observed: the CUTOFF arrives from the caller,
because it is the CLAMPED value (`_clamp_cutoff`) and recomputing
`max(order_date) - 1` would put paris_xxl's vélocité windows fourteen days away
from the Suivi table on the same page.

ABSENCE IS REPRESENTABLE. `refday`, `refname`, `coef` and `refvel` are None when
a day has no counterpart in the reference edition. The renderer branches on
null; nothing does arithmetic on it. A coefficient of 1.0 standing in for "no
reference" is what put a flat scenario on epk's Dimanche and rendered it as a
forecast (trap #12).
"""

import argparse
import ast
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / 'scripts'))
import run  # noqa: E402
from build_dashboard import (_ordered_days, _position_map,  # noqa: E402
                             read_warmup_flags)
from suivi_candidates import daily_offset  # noqa: E402  - proven closed form,
# equal to run.py's _prev_match_dow and pinned by verify/check_offset.py (§1 route b).

VAT = 0.055
MONTHS_FR = ('janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet',
             'août', 'septembre', 'octobre', 'novembre', 'décembre')

# Access levels that are not ordinary paid admission, in the order the
# Répartition card groups them. Anything unmatched lands in the catch-all.
FREE_LEVELS = ('invitation', 'jeu_concours', 'group_discount')


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def load_rows(path):
    """Merged-CSV rows with the three fields that need parsing, parsed."""
    out = []
    for r in csv.DictReader(Path(path).open(encoding='utf-8-sig')):
        try:
            r['_d'] = datetime.strptime(r['order_date'], '%Y-%m-%d').date()
        except (ValueError, KeyError):
            continue
        r['_paid'] = r.get('is_paid') == '1'
        try:
            r['_price'] = float(r.get('price') or 0)
            r['_gross'] = float(r.get('gross_price') or 0)
        except ValueError:
            r['_price'] = r['_gross'] = 0.0
        out.append(r)
    return out


def attendance(r):
    """The literal column, parsed. None when absent - resolve_attendance's own
    signal for "fall back to ticket_type"."""
    raw = (r.get('attendance_days') or '').strip()
    if not raw:
        return None
    try:
        return ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return None


def presence(rows, day_names, upto=None, paid_only=False):
    """Per-day presence via run.resolve_attendance - §1 route (c).

    The two-signal rule (attendance_days when populated, ticket_type otherwise)
    is a DESCRIPTION of what this function does, not a specification of it.
    Implemented from that description it gives 8 085 / 4 513 on epk; the
    function gives 8 087 / 4 515, which is what the live page shows.
    """
    tot = Counter()
    for r in rows:
        if upto and r['_d'] > upto:
            continue
        if paid_only and not r['_paid']:
            continue
        p = run.resolve_attendance(r.get('ticket_type'), attendance(r), day_names)
        for d in day_names:
            tot[d] += p.get(d, 0)
    return tot


# ---------------------------------------------------------------------------
# the pieces
# ---------------------------------------------------------------------------

def totals(rows, cutoff=None):
    paid = [r for r in rows if r['_paid'] and (cutoff is None or r['_d'] <= cutoff)]
    free = [r for r in rows if not r['_paid'] and (cutoff is None or r['_d'] <= cutoff)]
    rev = sum(r['_price'] for r in paid)
    plat = defaultdict(lambda: [0, 0.0, 0.0])
    for r in paid:
        p = plat[r['platform']]
        p[0] += 1
        p[1] += r['_price']
        p[2] += r['_gross']
    return {
        'n': len(paid),
        'inv': len(free),
        'rev': round(rev),
        'avg': round(rev / len(paid), 2) if paid else 0,
        # [tickets, faceTTC, grossPaid]. The third is what makes the Revenus
        # card derive its multiplier from data instead of hardcoding 1.1303.
        'plat': {k: [v[0], round(v[1]), round(v[2])] for k, v in sorted(plat.items())},
    }


def velocity(rows, cutoff, windows=(3, 7, 14, 30)):
    """Paid tickets per DAY over the last N complete days ending at the cutoff.

    D0. This returned the window TOTAL, and the card printed it with "/jour"
    after it. A per-day rate cannot climb with the window length, and epk's
    read 504 / 1350 / 2207 / 3677 across 3/7/14/30 - the shape of the numbers
    was the tell, not any assertion.

    Worse than a label error, because the card puts it beside "Rythme requis",
    which IS a true daily rate: 1 350 against 346 reads as four times the pace
    needed, where the truth is 193 against 345 - 56% of it. And `proj = A.n +
    A.vel[7] * JX` multiplied a seven-day total by the days remaining.

    `rolling()`, which feeds the CHART, has always divided by the window. The
    two disagreed about one quantity and the chart was right, so this is now
    the same arithmetic: sum over the window, divided by it.
    """
    out = {}
    for w in windows:
        lo = cutoff - timedelta(days=w - 1)
        n = sum(1 for r in rows if r['_paid'] and lo <= r['_d'] <= cutoff)
        out[str(w)] = round(n / w, 1)
    return out


def repartition(rows):
    """Groups, with a catch-all that makes the sum exact.

    Any access_level not matched by an earlier bucket lands in the last group.
    `invitation` is unmapped on 10 of 12 events and only reconciles today
    because those rows happen to be is_paid=0; one paid invitation and it would
    vanish from the table while still counting in the total.
    """
    paid = [r for r in rows if r['_paid']]
    tot = len(paid)
    buckets = [
        ('Billets Réguliers', lambda r: r['access_level'] == 'regular'),
        ('Entrée anticipée', lambda r: r['access_level'] == 'early_entry'),
        ('VIP / Backstage', lambda r: r['access_level'] in ('vip', 'backstage')),
        ('Tarif groupe', lambda r: r['access_level'] == 'group_discount'),
    ]
    groups, claimed = [], set()
    for label, pred in buckets:
        sel = [r for r in paid if id(r) not in claimed and pred(r)]
        claimed |= {id(r) for r in sel}
        if sel:
            groups.append(_group(label, sel, tot))
    rest = [r for r in paid if id(r) not in claimed]
    if rest:
        groups.append(_group('Autres', rest, tot))
    prices = sorted(r['_price'] for r in paid)
    return {
        'groups': groups,
        'tot': tot,
        'avg': round(prices[len(prices) // 2]) if prices else 0,
        'rev': round(sum(r['_price'] for r in paid)),
    }


def _group(label, rows, tot):
    by = defaultdict(list)
    for r in rows:
        by[r['product_name'] or '—'].append(r)
    kids = []
    for name, sel in sorted(by.items(), key=lambda kv: -len(kv[1])):
        p = sorted(x['_price'] for x in sel)
        kids.append({'k': name, 'n': len(sel),
                     'pct': round(len(sel) / tot * 100, 1) if tot else 0,
                     'rev': round(sum(x['_price'] for x in sel)),
                     'p': round(p[len(p) // 2])})
    p = sorted(r['_price'] for r in rows)
    return {'g': label, 'n': len(rows),
            'pct': round(len(rows) / tot * 100, 1) if tot else 0,
            'rev': round(sum(r['_price'] for r in rows)),
            'p': round(p[len(p) // 2]), 'kids': kids}


def presdays(cur_rows, ref_rows, cur_days, ref_days, caps, dates, warm,
             cutoff, mapping, ref_cut, label_of):
    """Per-day block. `ref` is None where the day has no counterpart."""
    cur_pres = presence(cur_rows, cur_days)
    ref_pres = presence(ref_rows, ref_days, upto=ref_cut) if ref_rows else Counter()
    cur_to_ref = {v: k for k, v in mapping.items()}

    comp = {d: Counter() for d in cur_days}
    v14 = Counter()
    lo14 = cutoff - timedelta(days=13)
    for r in cur_rows:
        p = run.resolve_attendance(r.get('ticket_type'), attendance(r), cur_days)
        multi = r.get('ticket_type') in ('2-jours', '3-jours')
        for d in cur_days:
            if not p.get(d, 0):
                continue
            comp[d]['free' if not r['_paid'] else ('multi' if multi else 'single')] += 1
            if lo14 <= r['_d'] <= cutoff:
                v14[d] += 1

    days = []
    for d in cur_days:
        rd = cur_to_ref.get(d)
        days.append({
            'k': d, 'label': label_of(d), 'date': dates[d],
            'cap': caps[d], 'now': cur_pres[d],
            # None, not 0. A day with no reference has not sold nothing.
            'ref': ref_pres[rd] if rd else None,
            'refday': rd,
            'vel14': round(v14[d] / 14),
            'warmup': d in warm,
            'comp': {'single': comp[d]['single'], 'multi': comp[d]['multi'],
                     'free': comp[d]['free']},
        })
    tt = Counter(r.get('ticket_type') for r in cur_rows)
    multi_n = sum(v for k, v in tt.items() if k in ('2-jours', '3-jours'))
    return {
        'days': days,
        'paid': sum(1 for r in cur_rows if r['_paid']),
        'free': sum(1 for r in cur_rows if not r['_paid']),
        'ref_tot': sum(d['ref'] for d in days if d['ref'] is not None),
        'freebreak': dict(Counter(r['access_level'] for r in cur_rows if not r['_paid'])),
        'one_day': len(cur_rows) - multi_n,
        'multi_day': multi_n,
    }


def series(rows, paid_only=True):
    """{date: (count, revenue)} - literal columns, grouped."""
    n, rev = Counter(), Counter()
    for r in rows:
        if paid_only and not r['_paid']:
            continue
        n[r['_d']] += 1
        rev[r['_d']] += r['_price']
    return n, rev


def rolling(counts, anchor, span, window, cap):
    """[{jx, v}] - `v` is the mean daily rate over `window` days ending jx."""
    out = []
    for k in range(span, -1, -1):
        day = anchor - timedelta(days=k)
        lo = day - timedelta(days=window - 1)
        v = sum(counts.get(lo + timedelta(days=i), 0) for i in range(window))
        out.append({'jx': (anchor - day).days + cap, 'v': round(v / window, 1)})
    return out


def cumulative(counts, anchor, span, cap):
    out, tot = [], 0
    for k in range(span, -1, -1):
        day = anchor - timedelta(days=k)
        tot += counts.get(day, 0)
        out.append({'jx': (anchor - day).days + cap, 'v': tot})
    return out


# The anchoring modes. `j_minus` and `days_since_launch` are NOT new names: they
# are the values `event_config.csv`'s `comparison_mode` column already carries and
# that `run.py:3955` already branches on, with the launch filter written at
# `run.py:1426`. Launch anchoring is unused work here, not new work, so the enum
# is extended rather than replaced and `exact_date` is a third value in it.
MODES = ('j_minus', 'days_since_launch', 'exact_date')


def cal_shift(d, n):
    """Same month and day, `n` years on. 29 February -> 28 February.

    NOT `timedelta`. A calendar match is a date operation, and the constant-day
    approximation of it is only correct until a 29 February falls inside the
    span - which is why `exact_date` carries a per-row mapping rather than one
    offset. See `Align` below.

    The 29 February rule is lossy in one direction and that is deliberate:
    `cal_shift(cal_shift(d, -N), N) == d` for every date EXCEPT 29 February,
    and there only when N is not a multiple of 4. Measured over 2024-2029 for
    N = 1..4: two failures each at N = 1, 2, 3 (2024-02-29 and 2028-02-29) and
    none at N = 4, where the counterpart leap day exists.
    """
    try:
        return d.replace(year=d.year + n)
    except ValueError:          # 29 February onto a common year
        return date(d.year + n, 2, 28)


class Align:
    """The whole of one anchoring mode: both grains and the labels.

    ONE OBJECT BECAUSE THE FAILURE THIS REPLACES WAS TWO RULES KEPT IN STEP.
    `exact_date` shipped for weeks as a daily rule that did one thing and a
    weekly rule that did another, and the mode's own label named a third. The
    four readers of the old `(offset, wshift)` pair each re-derived the mapping
    from those two integers; here they ask this object instead, so there is no
    longer a place for the grains to disagree.

      ref_date(day)   our row's date       -> the reference date it reads
      week_of(d)      a reference date     -> the weekly bucket it falls in
      week_span(w)    a weekly bucket      -> the reference dates it covers
      ref_jx(day)     our row's date       -> the reference's own J-x

    The constant-offset modes are unchanged and expressed here without loss:
    `ref_date` is a subtraction and `week_of` buckets by the reference's OWN
    event, which is what they have always done.
    """

    def __init__(self, offset=None, wshift=0, ref_ev=None, cur_ev=None, N=None):
        self.offset = offset        # None for exact_date: there is no constant
        self.wshift = wshift
        self.ref_ev = ref_ev
        self.cur_ev = cur_ev
        self.N = N                  # set only for exact_date

    @property
    def calendar(self):
        return self.N is not None

    def ref_date(self, day):
        if self.calendar:
            return cal_shift(day, -self.N)
        return day - timedelta(days=self.offset)

    def ref_jx(self, day):
        return (self.ref_ev - self.ref_date(day)).days

    def week_of(self, d):
        """Which bucket a REFERENCE date falls in.

        The calendar case maps the reference day FORWARD N years and buckets it
        by OUR event, so the reference's bucket is our bucket by construction
        rather than by two rules agreeing. The one exception is our own
        29 February row, whose reference day is shared with 28 February: it
        lands one bucket out when the week boundary happens to fall between the
        two, which is 1 event-date position in 7. Measured on a constructed
        straddle pair, since no reachable pair has a 29 February today.
        """
        if self.calendar:
            return (self.cur_ev - cal_shift(d, self.N)).days // 7
        return ((self.ref_ev - d).days - self.wshift) // 7

    def week_span(self, w):
        """The reference dates bucket `w` covers, for the row label.

        Calendar case: the inverse of `week_of`, so the span a row is labelled
        with is the span it counted. Both endpoints are mapped back
        independently - across a 29 February the reference window really is six
        days where ours is seven, and saying so is more honest than adding six
        to the start.
        """
        if self.calendar:
            sa = self.cur_ev - timedelta(days=(w + 1) * 7 - 1)
            return (cal_shift(sa, -self.N),
                    cal_shift(sa + timedelta(days=6), -self.N))
        sb = self.ref_ev - timedelta(days=self.wshift + (w + 1) * 7 - 1)
        return sb, sb + timedelta(days=6)


def anchor(mode, cur_ev, ref_ev, cur_lead, ref_lead):
    """An `Align` for an anchoring mode.

    For the two constant-offset modes the offset is subtracted from a
    current-side row DATE to reach the reference's matched date, and the weekly
    shift is subtracted from the reference's own J−x before bucketing.

    WHY THE WEEKLY SHIFT EXISTS, AND ONLY FOR ONE MODE
    --------------------------------------------------
    Weekly used to take no offset and no snap in every mode, on the reasoning
    that the daily offset is a WEEKDAY SNAP of at most ±3 days and cannot
    survive division by 7. That is true of `j_minus`.

    It is NOT true of `days_since_launch`, where the offset is the difference in
    CAMPAIGN LENGTHS: −59, +98 and +105 days on the six live pairs. Fifteen weeks
    does not round away. Without the shift the daily table realigns by fifteen
    weeks while the weekly table does not move at all, and the two halves of one
    mode disagree about what the mode is.

    AND IT WAS NEVER TRUE OF `exact_date`, WHICH IS WHY THAT MODE IS NOW A DATE
    OPERATION
    --------------------------------------------------------------------------
    This function used to return `(gap, 0)` for `exact_date` and the paragraph
    above used to claim the mode was `j_minus` minus the weekday snap. It was
    not. `m = day - gap` expands to a reference J−x of exactly our own J−x, so
    the mode did raw J−X with the snap turned off — a third thing, neither of
    the two its label names (`Date exacte`, `même J−x, date à date`). On
    `bordeaux_oct` it rendered the same table as `Jour J`, its reference column
    reading 24 August 2025 against our 9 August 2026 where date-to-date reads
    9 August 2025.

    It survived a spec, a mirrored client and a check reporting 198/198 because
    the spec asserted that turning the snap off WAS the calendar match. Turning
    the snap off gives raw J−X; the conclusion did not follow from the premise
    and both were written down as one sentence.

    A calendar match is a date operation, so `exact_date` gets a per-row mapping
    and no offset at all. NOT a constant offset plus an assertion that it stays
    constant: that assertion goes red today on 20 unreachable pairs — every 2024
    edition, all straddling 2024-02-29, invisible only because `build_series`
    emits no 2024 series. Per-row makes the correctness structural, so there is
    nothing left to assert and the 20 violations stop existing rather than being
    tolerated.

    `j_minus` and `days_since_launch` are UNCHANGED. Their offsets are exact
    constants, not incidental ones.

    `daily_offset` does the launch case unchanged - its own docstring already
    says the anchors are event dates for a finished candidate and FIRST-SALE
    dates for a live one.
    """
    if mode == 'exact_date':
        # N >= 0, asserted before the data can reach it. Zero candidates today
        # have a later event year than their page, which makes this exactly the
        # profile of `jr >= 0` and the weekly `w >= 0`: unreachable, and both of
        # those shipped wrong numbers once an assumption moved. `cal_shift`
        # would happily run backwards; the arithmetic below would not mean
        # anything if it did.
        N = cur_ev.year - ref_ev.year
        if N < 0:
            raise ValueError(
                f'exact_date needs the reference edition to be the older one: '
                f'our event {cur_ev} is in {cur_ev.year}, the reference '
                f'{ref_ev} is in {ref_ev.year} (N = {N})')
        return Align(cur_ev=cur_ev, ref_ev=ref_ev, N=N)
    if mode == 'days_since_launch':
        return Align(offset=daily_offset(cur_ev - timedelta(days=cur_lead),
                                         ref_ev - timedelta(days=ref_lead)),
                     wshift=ref_lead - cur_lead, ref_ev=ref_ev, cur_ev=cur_ev)
    return Align(offset=daily_offset(cur_ev, ref_ev), wshift=0,
                 ref_ev=ref_ev, cur_ev=cur_ev)


def daily_rows(cur_n, cur_rev, ref_n, ref_rev, cutoff, first, align, ref_cut,
               cur_ev, ref_ev, ref_last=None):
    """One row per day from `first` to the EVENT, with the reference matched by
    `align`. `b`/`rb` are None where the reference has no day.

    `align` replaced a bare integer offset when `exact_date` became a calendar
    operation. This is a local change because the mapping was always applied to
    a DATE here, never to a J−x: `align.ref_date(day)` is the same shape as the
    subtraction it replaces.

    TWO THINGS THAT LOOK LIKE ONE
    -----------------------------
    `jx` counts down to the event, NOT back from the cutoff. The template reads
    `r.jx === D.jx` for "Aujourd'hui" and `r.jx < D.jx` for "still to come", and
    D.jx is `(event - cutoff).days`. A row scale anchored on the cutoff is off
    by exactly D.jx, which makes today unfindable and every row look past.

    And the rows stop at the cutoff, so there is nothing for `fut` to be true
    OF. Both had to move together: rescaling alone gives a correct "today" and
    still no future; extending alone gives future rows that never match.

    Rows after the cutoff are `fut`. They carry no current-side figures - the
    cutoff is the observed anchor and our side does not exist beyond it - but
    they DO carry the reference's, which is the whole point of the block: what
    the comparison edition did over the stretch we have not lived yet.
    """
    rows, ca, cb, rca, rcb = [], 0, 0, 0.0, 0.0
    day = first
    # `max` because a FINISHED event's cutoff is past its own event date - the
    # clamp puts it at event_date_last + 1. Stopping at the event there would
    # drop the last rows AND lose the "today" row with them, which is how the
    # first version of this passed on four pages and failed on two.
    end = max(cutoff, cur_ev)
    while day <= end:
        fut = day > cutoff
        m = align.ref_date(day) if align is not None else None
        a, ra = (0, 0) if fut else (cur_n.get(day, 0), cur_rev.get(day, 0))
        # Like-for-like truncation is a rule about the PAST: compare the two
        # editions only as far as ours has run. Past the cutoff there is no
        # same-point left to preserve, so the bound becomes the reference's own
        # event - otherwise the future rows are blank on both sides and the
        # block says nothing.
        limit = ref_ev if fut else ref_cut
        has_ref = m is not None and limit is not None and m <= limit
        # AND NOT PAST THE REFERENCE'S OWN LAST DAY OF DATA. For a FINISHED
        # edition `ref_last` is at or after its event, so this is inert - which
        # is why it was never needed. A LIVE candidate's data stops at TODAY
        # while `ref_ev` is still in its future, so every row between the two
        # rendered `ref_n.get(m, 0)` -> 0: "Elektric Park 2026 sold 0 that day",
        # about a day that has not happened for it. Measured on rennes vs
        # epk_2026: 25 of 89 future rows.
        #
        # `.get(m, 0)` is right INSIDE the range - a quiet day is a real zero -
        # and wrong outside it, where absence is the truth. The two are
        # indistinguishable from the value alone, which is the whole trap.
        if has_ref and ref_last is not None and m > ref_last:
            has_ref = False
        b = ref_n.get(m, 0) if has_ref else None
        rb = ref_rev.get(m, 0) if has_ref else None
        ca += a
        rca += ra
        if b is not None:
            cb += b
            rcb += rb
        rows.append({'jx': (cur_ev - day).days, 'da': day.isoformat(),
                     'db': m.isoformat() if has_ref else None,
                     'a': a, 'b': b, 'ra': round(ra), 'rb': round(rb) if rb is not None else None,
                     'ca': ca, 'cb': cb if b is not None else None,
                     'rca': round(rca), 'rcb': round(rcb) if b is not None else None,
                     'fut': fut})
        day += timedelta(days=1)
    return rows


def weekly_rows(cur_n, cur_rev, ref_n, ref_rev, cur_ev, ref_ev, cutoff, ref_cut,
                cur_jx, cap, align=None):
    """Bucketed by `align.week_of`. The two grains do not share the daily
    MAPPING, but they do share the MODE - see `anchor()` for why that is not a
    contradiction.

    Under the two constant-offset modes each side buckets by its OWN distance
    from its own event, shifted by `wshift` on the reference side: 0 for
    `j_minus`, whose offset is a weekday snap that cannot survive division by 7,
    and the campaign-length difference for `days_since_launch`, where it reaches
    fifteen weeks.

    Under `exact_date` the reference is bucketed by OUR event date, after being
    mapped forward N calendar years. That is a DEPARTURE from
    `redesign/reference_suivi_candidates.py`, which has been the authority on
    the weekly grain all project and states that each side buckets by its own
    event. It is correct for a calendar comparison - the whole claim of the mode
    is that a reference date and our date are the same date - and the spec is
    amended in the same commit rather than left to disagree.

    `fut` is `w <= cur_jx // 7`: the week TODAY SITS IN is already future,
    because it has not finished. That is a different rule from the daily grain,
    where today is present and only tomorrow onward is future - and it is the
    rule the locked mock's own payload carries. Both bucket sets extend to
    w = 0 so the "À venir" block has weeks to show.
    """
    w0 = cur_jx // 7
    ca = defaultdict(lambda: [0, 0.0])
    cb = defaultdict(lambda: [0, 0.0])
    for d, k in cur_n.items():
        if d <= cutoff:
            w = (cur_ev - d).days // 7
            ca[w][0] += k
            ca[w][1] += cur_rev.get(d, 0)
    for d, k in ref_n.items():
        w = align.week_of(d)
        # Same split as the daily grain: truncate at the same point for the
        # weeks already lived, and run to the reference's own event for the
        # weeks still ahead.
        keep = (d <= ref_cut) if w > w0 else (d <= ref_ev)
        # AND w >= 0. DECIDED HERE RATHER THAN CARRIED ACROSS, because what it
        # does changed when `exact_date` became a calendar operation.
        #
        # It used to bite only under `days_since_launch`, where the candidate's
        # campaign can run 105 days longer than ours and its EVENT lands fifteen
        # weeks past ours in launch-aligned time - geometrically right, and
        # fifteen rows of "S−−1" … "S−−15" on the page. Under `j_minus` `keep`
        # already implies `d <= ref_ev` and therefore `w >= 0`, so it was
        # unreachable and correct by accident. That is the same profile as
        # `jr >= 0`, which shipped wrong numbers the moment live candidates
        # reached the menu.
        #
        # Under `exact_date` it now bites hard: a reference day whose calendar
        # counterpart falls after OUR event gets a negative bucket. Measured
        # across all 66 reachable page x candidate pairs, 30 of them have at
        # least one such week and one has 31 of them.
        #
        # KEPT, and it is now load-bearing rather than accidental. The reason is
        # not "negative weeks look wrong" - it is that the DAILY grain cannot
        # show those days at all. Daily maps the reference onto OUR rows and our
        # rows stop at our event, so a reference day past our event has nowhere
        # to land. The weekly grain is a union and is the one place it could
        # surface. Dropping the bound would make the two grains cover different
        # spans of the same comparison, which is precisely the disagreement the
        # per-row design exists to make impossible.
        #
        # The cost is real and worth naming: on `bordeaux_oct` vs
        # `halloween_2025` this hides the reference's last three weeks, which
        # are its heaviest. They are hidden at the daily grain too, by the same
        # rule and for the same reason - a date after our event is outside a
        # date-to-date comparison by definition.
        if ref_cut and keep and w >= 0:
            cb[w][0] += k
            cb[w][1] += ref_rev.get(d, 0)
    weeks = sorted(set(ca) | set(cb) | set(range(0, w0 + 1)), reverse=True)
    # ONE denominator, and it is OUR jauge on both sides (ruled, after seeing
    # both rendered). Per-side totals put the two columns on two scales, so the
    # S-17 row read "12.8% cumulé" beside "65.1% cumulé" - same unit, same row,
    # different meanings - and the reference column was a percentage of a total
    # the reader cannot see. It also made the last row read 100% by
    # construction, which is a number that carries no information.
    #
    # The row template says "de la jauge" out loud (D10). An unlabelled "%"
    # over two possible denominators is how this got as far as it did.
    ta = tb = cap or 1
    out, aa, bb = [], 0, 0
    for w in weeks:
        a, ra = ca[w][0], ca[w][1]
        has_b = w in cb
        b, rb = (cb[w][0], cb[w][1]) if has_b else (None, None)
        aa += a
        if has_b:
            bb += b
        sa = cur_ev - timedelta(days=(w + 1) * 7 - 1)
        # The reference label is the exact inverse of the rule the bucket was
        # built with, so the span a row is labelled with is the span it counted.
        # Under the constant-offset modes that is the reference's own event date
        # and its own shift; under `exact_date` it is our week's span mapped back
        # N calendar years. Both live in `Align.week_span` so the label cannot
        # be derived from a different rule than the bucket.
        sb, eb = align.week_span(w)
        out.append({'w': w, 'a': a, 'b': b, 'ra': round(ra),
                    'rb': round(rb) if rb is not None else None,
                    'pa': round(a / ta * 100, 1),
                    'pb': round(b / tb * 100, 1) if has_b else None,
                    'ca': round(aa / ta * 100, 1),
                    'cb': round(bb / tb * 100, 1) if has_b else None,
                    'sa': sa.isoformat(), 'ea': (sa + timedelta(days=6)).isoformat(),
                    'sb': sb.isoformat() if has_b else None,
                    'eb': eb.isoformat() if has_b else None,
                    'fut': w <= w0})
    return out


def ref_day_velocity(ref_rows, ref_days, ref_cut, window=14):
    """14-day presence velocity for each REFERENCE day, at its own cut.

    Not the event-wide sales rate: a coefficient compares our Samedi's pace to
    THEIR matched day's pace, and on a multi-day event those differ. Using the
    event total gave both bordeaux days the same 346.8 and a coefficient that
    was really just a ratio of totals.
    """
    if not ref_cut:
        return {}
    lo = ref_cut - timedelta(days=window - 1)
    tot = Counter()
    for r in ref_rows:
        if not (lo <= r['_d'] <= ref_cut):
            continue
        pres = run.resolve_attendance(r.get('ticket_type'), attendance(r), ref_days)
        for d in ref_days:
            tot[d] += pres.get(d, 0)
    return {d: round(tot[d] / window, 1) for d in ref_days}


def day_cumulative(rows, day, day_names, anchor, span, cap, jx0):
    """[{jx, v}] where v is cumulative presence on `day` as % of its capacity.

    The chart is one line: the projection CONTINUES the actual rather than
    sitting beside it, so both series share this scale.
    """
    per = Counter()
    for r in rows:
        pres = run.resolve_attendance(r.get('ticket_type'), attendance(r), day_names)
        if pres.get(day, 0):
            per[r['_d']] += 1
    out, tot = [], 0
    for k in range(span, -1, -1):
        dt = anchor - timedelta(days=k)
        tot += per.get(dt, 0)
        out.append({'jx': (anchor - dt).days + jx0,
                    'v': round(tot / cap * 100, 2) if cap else 0})
    return out


def projx(days_blocks, cur_days, caps, cutoff, cur_ev, ref_label, ref_key,
          ref_vel, ref_ev, ref_cut, mapping, ref_days_names, charts=None,
          is_ref=True):
    """One candidate. `coef`, `refday`, `refname`, `refvel` are None when the
    day has no counterpart - never 1.0, which reads as "no change" (trap #12)."""
    cur_to_ref = {v: k for k, v in mapping.items()}
    out = []
    for blk in days_blocks:
        d = blk['k']
        rd = cur_to_ref.get(d)
        refvel = coef = None
        if rd and ref_cut:
            rv = ref_vel.get(rd)
            if rv:
                refvel = rv
                coef = round(blk['vel14'] / rv, 2)
        # Everything below is None when there is no matched day. The card
        # then renders its "pas de journée correspondante" empty state, which
        # names how many days the reference had - §5.6's degrade-honestly path,
        # already written in the locked mock and keyed off exactly these nulls.
        s1 = s2 = chart = None
        if rd and charts:
            act = charts['act'][d]
            ref = charts['ref'].get(rd, [])
            jx_left = max((cur_ev - cutoff).days, 0)
            last = act[-1]['v'] if act else 0
            refv = {x['jx']: x['v'] for x in ref}
            base = refv.get(jx_left)
            if base is None and ref:
                base = next((x['v'] for x in ref if x['jx'] <= jx_left), ref[-1]['v'])

            def _curve(scale):
                """One point per remaining day, J-jx_left down to J-0.

                A two-point line from today to the endpoint has the right ends
                and no shape at all, so the two scenarios drew the same flat
                segment and the toggle looked broken. The shape IS the
                reference's own cumulative curve over the same stretch: that
                is what "réplique des ventes" means, and it is the only reason
                the chart is worth drawing.
                """
                out = []
                for jx in range(jx_left, -1, -1):
                    at = refv.get(jx)
                    if at is None:
                        at = next((v for j, v in sorted(refv.items()) if j >= jx),
                                  base if base is not None else 0.0)
                    v = last + max(at - (base or 0.0), 0.0) * scale
                    # 120 is the mock's own ceiling: past it the curve leaves
                    # the plot area and the sellout date has long since been
                    # read off the 100% line anyway.
                    out.append({'jx': jx, 'v': round(min(v, 120.0), 2)})
                return out

            p1 = _curve(1.0) if ref else []
            p2 = _curve(coef) if (ref and coef) else []

            def _sc(curve):
                """`tot` from the curve's own endpoint, so the card and the
                chart can never disagree; `date` is the first day the curve
                reads 100%, and None when it never does."""
                if not curve:
                    return None
                tot = min(round(curve[-1]['v'] / 100 * caps[d]), caps[d])
                hit = next((p['jx'] for p in curve if round(p['v']) >= 100), None)
                return {'tot': tot,
                        'date': (cur_ev - timedelta(days=hit)).isoformat()
                                if hit is not None else None,
                        'add': max(tot - blk['now'], 0),
                        'pct': round(tot / caps[d] * 100) if caps[d] else 0}

            s1, s2 = _sc(p1), _sc(p2)
            chart = {'act': act, 'ref': ref, 'p1': p1, 'p2': p2}
        out.append({
            'day': d, 'cap': caps[d], 'now': blk['now'], 'vel14': blk['vel14'],
            'refday': rd, 'refname': ref_label if rd else None,
            'coef': coef, 'refvel': refvel,
            's1': s1, 's2': s2, 'chart': chart,
        })
    # `refdays` is the reference edition's day NAMES, not a count - the mock's
    # empty state reads "n'a que N journées (vendredi, samedi)" off it, which is
    # §5.6's degrade-honestly path and is already written in the locked mock.
    # `ref` is a boolean: is this the configured comparison?
    return {'label': ref_label, 'days': out,
            'refdays': ref_days_names, 'ref': is_ref}


def build(event, csv_path, cutoff, config, ref_event=None, ref_csv=None,
          extra_refs=(), mode=None):
    cfg_all = run.load_event_config(config)
    cur_cfg = cfg_all[event]
    ref_cfg = cfg_all.get(ref_event) if ref_event else None

    # The anchoring mode comes from the config row, exactly as `run.py:3955`
    # reads it, defaulting the same way. ONE place states the mode; `mode=` here
    # is for the checks, which have to drive all three without editing the
    # config back and forth.
    if mode is None:
        mode = (cur_cfg.get('comparison_mode') or '').strip() or 'j_minus'
    if mode not in MODES:
        raise SystemExit(f'unknown comparison_mode {mode!r}; want one of {MODES}')

    cur_days = _ordered_days(cur_cfg)
    ref_days = _ordered_days(ref_cfg) if ref_cfg else []
    mapping = _position_map(cur_days, ref_days) if ref_days else {}
    warm = read_warmup_flags(config).get(event, set())

    caps = {d['day_name'].strip().lower(): d['day_capacity'] for d in cur_cfg['days']}
    dates = {d['day_name'].strip().lower():
             f"{d['day_date'].day} {MONTHS_FR[d['day_date'].month - 1]} {d['day_date'].year}"
             for d in cur_cfg['days']}
    labels = {d['day_name'].strip().lower(): d['day_name'].strip()
              for d in cur_cfg['days']}

    cur_rows = load_rows(csv_path)
    ref_rows = load_rows(ref_csv) if ref_csv else []

    # Our campaign length, in days before our own event. Same definition as a
    # series file's `lead` (the LARGEST jx with a sale), so the two sides of a
    # launch-anchored comparison are measured the same way.
    _cur_n_all, _ = series(cur_rows)
    cur_lead = ((cur_cfg['event_date_first'] - min(_cur_n_all)).days
                if _cur_n_all else 0)
    ref_lead = 0
    if ref_rows and ref_cfg:
        _ref_n_all, _ = series(ref_rows)
        ref_lead = ((ref_cfg['event_date_first'] - min(_ref_n_all)).days
                    if _ref_n_all else 0)

    # ONE `Align` for the whole build. The cut, both grains and the labels all
    # ask it, so there is no second place the mode can be interpreted - which is
    # the failure `exact_date` shipped with for weeks.
    align = (anchor(mode, cur_cfg['event_date_first'],
                    ref_cfg['event_date_first'], cur_lead, ref_lead)
             if ref_cfg else None)

    ref_cut = None
    if ref_rows and ref_cfg:
        # §1 route (c): run.py's own same-point filters, not reimplementations -
        # and there are TWO of them, one per anchoring mode, both already
        # written. `filter_tickets_to_same_point` cuts at equal days-before-event
        # and `filter_tickets_to_same_point_dsl` at equal days-since-launch.
        #
        # BOTH ARE RAW. Neither applies the weekday snap that the row PAIRING
        # uses. That asymmetry is not an oversight to be tidied up: it is the
        # existing convention, visible in run.py's two functions, and the new
        # modes inherit it rather than reasoning it out again. `exact_date`
        # shares `j_minus`'s cut because the two differ by the snap alone, which
        # the cut never had.
        _rows = [{**r, 'order_date': r['_d']} for r in ref_rows]
        if mode == 'days_since_launch':
            ref_rows_cut = run.filter_tickets_to_same_point_dsl(
                _rows, cutoff,
                cur_cfg['event_date_first'] - timedelta(days=cur_lead),
                ref_cfg['event_date_first'] - timedelta(days=ref_lead))
        elif mode == 'exact_date':
            # `exact_date` NO LONGER SHARES `j_minus`'s CUT, and this is the one
            # place that inheritance was load-bearing rather than cosmetic.
            #
            # The old comment above was right about its own premise: the cut is
            # raw in every mode, and `exact_date` could share `j_minus`'s
            # because "the two differ by the snap alone, which the cut never
            # had". They no longer differ by the snap alone. The same point in a
            # CALENDAR comparison is the reference's counterpart of our cutoff
            # date, not its counterpart J−x, and on a straddle those are
            # different days.
            #
            # Same rule as the other two - keep what the edition had sold by the
            # matched moment - expressed through the mapping this mode actually
            # uses. run.py is untouched: it carries the two filters it carries,
            # and neither of them is this one.
            _m = align.ref_date(cutoff)
            ref_rows_cut = [r for r in _rows if r['order_date'] <= _m]
        else:
            ref_rows_cut = run.filter_tickets_to_same_point(
                _rows, cutoff, cur_cfg['event_date_first'],
                ref_cfg['event_date_first'])
        ref_cut = max((r['order_date'] for r in ref_rows_cut), default=None)

    D = {
        'jx': (cur_cfg['event_date_first'] - cutoff).days,
        # B1: the two scalars a consumer contributes to alignment. `jx` is the
        # same-point truncation (filter_tickets_to_same_point reduces to
        # exactly `keep jx_ref >= D.jx`); `ev` is one half of the weekday snap
        # `signed_mod7(cur_ev - cand_ev)`, the other half being in the
        # candidate's own file. Nothing else about this event enters.
        'ev': cur_cfg['event_date_first'].isoformat(),
        # Which edition this page IS. Not used for rendering - every consumer
        # already knows it is looking at itself - but a checker holding only
        # the shipped HTML does not, and the alternative is a filename-to-id
        # map maintained by hand next to the one in the config.
        'id': event,
        # Launch anchoring's two inputs. `lead` is ours; the candidate's is in
        # its own series file under the same name and the same definition, so a
        # launch offset is `s.lead - D.lead` and nothing else crosses. `amode` is
        # the config's comparison_mode for this event - the mode the picker
        # STARTS on, not a second place the mode is stated.
        'lead': cur_lead,
        'amode': mode,
        'ref_id': ref_event,
        'cap': sum(caps.values()),
        'daycap': max(caps.values()) if caps else 0,
        'vat': VAT,
        'cur_year': cur_cfg['event_date_first'].year,
        'ref_year': ref_cfg['event_date_first'].year if ref_cfg else None,
        'cur': {**totals(cur_rows, cutoff), 'vel': velocity(cur_rows, cutoff)},
        'ref': ({**totals(ref_rows, ref_cut), 'vel': velocity(ref_rows, ref_cut)}
                if ref_rows and ref_cut else {'n': 0}),
        'ref_final': ({'n': sum(1 for r in ref_rows if r['_paid']),
                       'rev': round(sum(r['_price'] for r in ref_rows if r['_paid']))}
                      if ref_rows else {'n': 0, 'rev': 0}),
        'rep': repartition(cur_rows),
        'presdays': presdays(cur_rows, ref_rows, cur_days, ref_days, caps, dates,
                             warm, cutoff, mapping, ref_cut, labels.get),
    }

    # ---- series ----------------------------------------------------------
    cur_n, cur_rev = series(cur_rows)
    ref_n, ref_rev = series(ref_rows) if ref_rows else (Counter(), Counter())
    first = min(cur_n) if cur_n else cutoff
    span = (cutoff - first).days
    D['daily'] = daily_rows(cur_n, cur_rev, ref_n, ref_rev, cutoff, first,
                            align, ref_cut, cur_cfg['event_date_first'],
                            ref_cfg['event_date_first'] if ref_cfg else None,
                            max(ref_n) if ref_n else None)
    D['weekly'] = weekly_rows(cur_n, cur_rev, ref_n, ref_rev,
                              cur_cfg['event_date_first'],
                              ref_cfg['event_date_first'] if ref_cfg else None,
                              cutoff, ref_cut, D['jx'], D['cap'],
                              align) if ref_cfg else []
    D['maxjx'] = max((r['jx'] for r in D['daily']), default=span)
    # The last ten days LIVED, not the last ten rows: with future rows in the
    # list the tail is all `–`.
    D['suivi'] = [{k: r[k] for k in ('jx', 'a', 'b', 'da', 'db')}
                  for r in D['daily'] if not r['fut']][-10:]

    D['cumA'] = cumulative(cur_n, cutoff, span, D['jx'])
    D['r7A'] = rolling(cur_n, cutoff, span, 7, D['jx'])
    D['r14A'] = rolling(cur_n, cutoff, span, 14, D['jx'])
    if ref_cut:
        rspan = (ref_cut - min(ref_n)).days if ref_n else 0
        rjx = (ref_cfg['event_date_first'] - ref_cut).days
        D['cumB'] = cumulative(ref_n, ref_cut, rspan, rjx)
        D['r7B'] = rolling(ref_n, ref_cut, rspan, 7, rjx)
        D['r14B'] = rolling(ref_n, ref_cut, rspan, 14, rjx)
    else:
        D['cumB'] = D['r7B'] = D['r14B'] = []

    # ---- presence rollups ------------------------------------------------
    blocks = D['presdays']['days']
    cur_pres = {b['k']: b['now'] for b in blocks}
    D['cur']['pres'] = cur_pres
    D['cur']['pres_tot'] = sum(cur_pres.values())
    D['cur']['pct'] = round(D['cur']['pres_tot'] / D['cap'] * 100, 1) if D['cap'] else 0
    D['cur']['types'] = [
        {'t': t, 'n': c,
         'pct': round(c / D['cur']['n'] * 100, 1) if D['cur']['n'] else 0,
         'p': round(sum(r['_price'] for r in cur_rows
                        if r['_paid'] and r['ticket_type'] == t) / c, 2) if c else 0,
         'rev': round(sum(r['_price'] for r in cur_rows
                          if r['_paid'] and r['ticket_type'] == t))}
        for t, c in Counter(r['ticket_type'] for r in cur_rows if r['_paid']).most_common()]

    if D['ref'].get('n'):
        ref_pres = {b['refday']: b['ref'] for b in blocks if b['refday']}
        D['ref']['pres'] = ref_pres
        D['ref']['pres_tot'] = sum(ref_pres.values())
        D['ref']['pct'] = round(D['ref']['pres_tot'] / D['cap'] * 100, 1) if D['cap'] else 0
        D['ref']['types'] = []

    D['perday'] = {b['k']: {'now': b['now'], 'ref': b['ref'], 'vel14': b['vel14'],
                            'cap': b['cap'], 'one': b['comp']['single'],
                            'duo': b['comp']['multi']} for b in blocks}
    P = D['presdays']
    D['pres'] = {
        'cur': {'one': P['one_day'], 'duo': P['multi_day'], 'free': P['free'],
                'tot': D['cur']['pres_tot'], 'per': cur_pres, 'paid': P['paid']},
        'ref': {'one': 0, 'duo': 0, 'free': 0, 'tot': P['ref_tot'],
                'per': {b['k']: b['ref'] for b in blocks}, 'paid': D['ref'].get('n', 0)},
        'free': P['freebreak'],
    }

    # ---- projection ------------------------------------------------------
    D['coef'] = None
    D['proj'] = [{'day': b['k'], 'now': b['now'], 'cap': b['cap'],
                  's1': None, 's2': None} for b in blocks]

    # `act` is the CURRENT edition's curve - one per day of ours, and the same
    # under every candidate. Computed once, shared by all of them.
    act_charts = {d: day_cumulative(cur_rows, d, cur_days, cutoff, span,
                                    caps[d], D['jx']) for d in cur_days}

    # The configured comparison first, then every other finished edition that
    # has data. The selector listed exactly one candidate because exactly one
    # was ever built - the menu was right, the payload behind it was a single
    # entry wearing a dropdown.
    cands, order = {}, []
    for cid, ccsv in ([(ref_event, ref_csv)] if ref_cfg else []) + list(extra_refs or []):
        if cid in cands or cid == event or not ccsv:
            continue
        ccfg = cfg_all.get(cid)
        if not ccfg:
            continue
        crows = load_rows(ccsv)
        if not crows:
            continue
        cdays = _ordered_days(ccfg)
        cmap = _position_map(cur_days, cdays)
        c_n, _ = series(crows)
        if not c_n:
            continue
        crows_cut = run.filter_tickets_to_same_point(
            [{**r, 'order_date': r['_d']} for r in crows],
            cutoff, cur_cfg['event_date_first'], ccfg['event_date_first'])
        c_cut = max((r['order_date'] for r in crows_cut), default=None)
        if not c_cut:
            continue
        c_ev = ccfg['event_date_first']
        # The reference curve runs to ITS OWN event, not to the same point:
        # the remaining shape being replayed is precisely the part after the
        # same point, so truncating there leaves nothing to replay.
        cands[cid] = projx(
            blocks, cur_days, caps, cutoff, cur_cfg['event_date_first'],
            ccfg.get('event_name', cid), cid,
            ref_day_velocity(crows, cdays, c_cut), c_ev, c_cut, cmap, cdays,
            {'act': act_charts,
             'ref': {d: day_cumulative(crows, d, cdays, c_ev,
                                       (c_ev - min(c_n)).days,
                                       caps.get(cmap.get(d, d), 1), 0)
                     for d in cdays}},
            is_ref=(cid == ref_event))
        order.append(cid)

    D['projx'] = {'cands': cands, 'default': ref_event if ref_event in cands
                  else (order[0] if order else None),
                  'curdays': cur_days, 'jx': D['jx']}

    # ---- meta ------------------------------------------------------------
    D['meta'] = {'cur': _meta(cur_rows, cur_cfg), 'ref': _meta(ref_rows, ref_cfg)}
    return D


def _meta(rows, cfg):
    if not rows or not cfg:
        return {'n': 0}
    paid = [r for r in rows if r['_paid']]
    days = sorted({r['_d'] for r in rows})
    peak = Counter(r['_d'] for r in paid).most_common(1)
    rev = sum(r['_price'] for r in paid)
    return {
        'n': len(paid), 'free': len(rows) - len(paid), 'rev': round(rev),
        'first': days[0].isoformat(), 'last': days[-1].isoformat(),
        'first_dt': days[0].isoformat(), 'days_sold': len(days),
        'lead': (cfg['event_date_first'] - days[0]).days,
        'avg': round(rev / len(paid), 2) if paid else 0,
        'plat': dict(Counter(r['platform'] for r in paid)),
        'peak_day': [peak[0][0].isoformat(), str(peak[0][1])] if peak else [None, '0'],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--event', required=True)
    ap.add_argument('--csv', required=True)
    ap.add_argument('--cutoff', required=True,
                    help='the CLAMPED cutoff observed by build_dashboard, YYYY-MM-DD')
    ap.add_argument('--config', default=str(BASE_DIR / 'event_config.csv'))
    ap.add_argument('--ref-event')
    ap.add_argument('--ref-csv')
    ap.add_argument('--out')
    a = ap.parse_args()
    D = build(a.event, a.csv, datetime.strptime(a.cutoff, '%Y-%m-%d').date(),
              a.config, a.ref_event, a.ref_csv)
    text = json.dumps(D, ensure_ascii=False, separators=(',', ':'))
    if a.out:
        Path(a.out).write_text(text, encoding='utf-8')
        print(f'{a.out}: {len(text) / 1024:.0f} KB')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
