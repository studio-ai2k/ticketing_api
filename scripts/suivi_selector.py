#!/usr/bin/env python3
"""
Deploy 4: the Suivi des ventes comparison selector, plus the revenue line.

Two jobs, both driven by the sidecar `build_dashboard.py` writes beside the
HTML (`<out>.suivi.json`): the observed anchors, and one series per candidate.

  1. SERVER SIDE - tag every Suivi row with the key the client needs, and add
     the revenue figures to the daily rows on both sides.
  2. CLIENT SIDE - inject the dropdown, the payload, and the JS that rewrites
     the left column and the Diff column when a candidate is chosen.

TWO GRAINS, TWO MAPPINGS
------------------------
The offset identity is exact, elegant, and applies to the DAILY table only.
Do not generalise it.

  daily   `data-cur` is an ISO date. matched = data-cur - candidate.offset,
          where offset is constant per candidate (run.py's _prev_match_dow
          collapses to it - see the handoff for the derivation).

  weekly  `data-wk` is an integer week number. There is NO offset and NO
          weekday snap: each side buckets its own tickets by
          `(its own event_date_first - order_date).days // 7`, so week N on
          the left is week N of the candidate's own campaign. Shifting weekly
          rows by the daily offset mis-aligns every one of them, silently.

WHERE data-cur COMES FROM
-------------------------
Positionally, from the observed `cutoff_date` - never by parsing the rendered
dates. "Jeu 15 Déc" carries no year and the table spans 232 rows across a year
boundary, so parsing is ambiguous rather than merely fragile. The past rows are
a strictly consecutive one-per-day sequence ending at cutoff_date (verified:
0 non-consecutive steps over 232 / 179 / 93 rows on three events), so counting
backwards from the last one is exact.
"""

import json
import re
from datetime import date, timedelta

DAYS_FR = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
MONTHS_FR = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin',
             'Juil', 'Aoû', 'Sep', 'Oct', 'Nov', 'Déc']

ROW_RE = re.compile(r'<div class="dtl-row([^"]*)"([^>]*)>')
SALES_RE = re.compile(r'(<div class="dtl-sales"[^>]*>)(\d[\d,\s]*)(</div>)')
ACCUM_RE = re.compile(r'(<div class="dtl-accum"[^>]*>)([^<]*)(</div>)')

# The only rule this feature adds that the vendored stylesheet does not
# already carry - every .cmp-* rule ships in dashboard_v6_7.css, but the mock's
# rows have no revenue at all, so there is nothing there for .dtl-rev.
#
# Appended to the existing <style> rather than added as a second block: pass 4
# replaces that block wholesale, so a separate block would win or lose by
# source order depending on where it landed.
REV_CSS = (
    '\n/* revenue beside the count and the cumulative, Suivi daily rows */\n'
    '.dtl-rev{color:var(--text-dim);font-size:.86em;font-weight:400;'
    'font-variant-numeric:tabular-nums;white-space:nowrap}\n'
)

GROUP_TITLES = (
    ('edition', 'Éditions {family}'),
    ('past', 'Autres éditions passées'),
    ('live', 'Événements en cours'),
)


def _fmt_eur(value):
    """1265.4 -> '€1 265'. Space separator, matching the design."""
    return '€' + f'{round(value):,}'.replace(',', ' ')


def _fmt_num(value):
    """run.py's own thousands style, so injected figures match rendered ones."""
    return f'{value:,}'


def _split_rows(html, start, end):
    """(index, class, tag_span) for every .dtl-row between two offsets."""
    return [(m.start(), m.group(1).strip(), m.span())
            for m in ROW_RE.finditer(html, start, end)]


def _daily_dates(rows, containers, cutoff, cutoff_cum):
    """
    Map each daily row to its current-side date.

    Past rows run consecutively up to cutoff_date; the "today" row is
    cutoff_cumulative; future rows run consecutively from the day after.
    Returns a list of (row_index, date) in document order.
    """
    past, today, future = [], [], []
    for pos, cls, span in rows:
        if 'today' in cls.split():
            today.append((pos, span))
        elif any(a <= pos < b for a, b in containers):
            future.append((pos, span))
        else:
            past.append((pos, span))

    out = []
    for i, (pos, span) in enumerate(past):
        out.append((pos, span, cutoff - timedelta(days=len(past) - 1 - i)))
    for pos, span in today:
        out.append((pos, span, cutoff_cum or cutoff))
    first_future = (cutoff_cum or cutoff) + timedelta(days=1)
    for i, (pos, span) in enumerate(future):
        out.append((pos, span, first_future + timedelta(days=i)))
    return sorted(out, key=lambda t: t[0])


def _prefix(series):
    """{date: cumulative revenue} over the whole series, in date order."""
    total, out = 0.0, {}
    for d in sorted(series):
        total += series[d]['rev']
        out[d] = total
    return out


def apply(html, sidecar_path):
    """Returns (html, problems, stats). A missing sidecar is a no-op."""
    problems, stats = [], {}
    if not sidecar_path.exists():
        return html, [], {'skipped': 'no sidecar'}

    data = json.loads(sidecar_path.read_text(encoding='utf-8'))
    anchors = data.get('anchors') or {}
    if not anchors.get('cutoff_date'):
        return html, ['suivi: sidecar has no cutoff_date anchor'], {}
    cutoff = date.fromisoformat(anchors['cutoff_date'])
    cutoff_cum = (date.fromisoformat(anchors['cutoff_cumulative'])
                  if anchors.get('cutoff_cumulative') else None)

    jour = html.find('<div id="suivi-jour"')
    sem = html.find('<div id="suivi-semaine"')
    if jour < 0 or sem < 0:
        return html, ['suivi: #suivi-jour or #suivi-semaine not found'], {}

    # --- the current event's own series, and the reference's --------------
    by_id = {c['id']: c for c in data.get('candidates', [])}
    ref = by_id.get(data.get('reference'))
    own = data.get('own_series') or {}

    # Future rows live in their own container; everything else before the
    # today row is past.
    containers = []
    fut = html.find('<div id="suivi-future-days"', jour, sem)
    if fut >= 0:
        containers.append((fut, _match_end(html, fut)))

    rows = _split_rows(html, jour, sem)
    dated = _daily_dates(rows, containers, cutoff, cutoff_cum)
    stats['daily_rows'] = len(dated)

    own_prefix = _prefix(own)
    ref_prefix = _prefix(ref['series']) if ref else {}
    ref_offset = ref['offset'] if ref else 0

    # Rewrite from the end so earlier offsets stay valid.
    edits = 0
    for pos, span, day in sorted(dated, key=lambda t: -t[0]):
        tag_start, tag_end = span
        row_end = _match_end(html, pos)
        body = html[tag_end:row_end]
        iso = day.isoformat()

        right = own.get(iso)
        left_iso = (day - timedelta(days=ref_offset)).isoformat() if ref else None
        left = ref['series'].get(left_iso) if ref else None
        new_body = _inject_revenue(
            body,
            (left, ref_prefix.get(left_iso)),
            (right, own_prefix.get(iso)))
        if new_body != body:
            edits += 1
        attrs = f' data-cur="{iso}" data-g="d"'
        html = html[:tag_end - 1] + attrs + html[tag_end - 1:tag_end] + new_body + html[row_end:]
    stats['daily_revenue_rows'] = edits

    # --- weekly rows: tag with their own week number ----------------------
    # Re-found AFTER the daily rewrites above, which inserted attributes and
    # revenue spans and so moved every offset past #suivi-jour. Reusing the
    # index taken before the loop silently tagged nothing.
    sem = html.find('<div id="suivi-semaine"')
    sem_end = _match_end(html, sem)
    weeks = 0
    section = html[sem:sem_end]

    def _tag_week(m):
        nonlocal weeks
        wk = re.search(r'>S-(\d+)', section[m.end():m.end() + 400])
        if not wk:
            return m.group(0)
        weeks += 1
        return f'{m.group(0)[:-1]} data-wk="{wk.group(1)}" data-g="w">'

    html = html[:sem] + ROW_RE.sub(_tag_week, section) + html[sem_end:]
    stats['weekly_rows'] = weeks

    if edits and REV_CSS.strip() not in html:
        html, n = re.subn(r'</style>', REV_CSS + '</style>', html, count=1)
        if n != 1:
            problems.append('suivi: no </style> to append the revenue rule to')
    return html, problems, stats


def _match_end(html, start):
    """Index just past the </div> closing the <div at `start`."""
    depth = 0
    for m in re.finditer(r'<div\b[^>]*>|</div>', html[start:]):
        depth += -1 if m.group(0)[1] == '/' else 1
        if depth == 0:
            return start + m.end()
    return len(html)


def _inject_revenue(body, left, right):
    """
    Add the revenue figures to one daily row, both sides.

    Additive only: the count keeps its place and gains an inline € beside it,
    and the Cumulé line gains " · €N". Nothing is renamed, reordered or
    removed, and a side with no data for that date is left untouched rather
    than shown as €0.
    """
    parts = body.split('<div class="dtl-center">')
    if len(parts) != 2:
        return body
    left_html, rest = parts
    centre, _, right_html = rest.partition('<div class="dtl-right">')

    def _one(chunk, entry, cumulative):
        if not entry:
            return chunk
        chunk = SALES_RE.sub(
            lambda m: (f'{m.group(1)}{m.group(2)} '
                       f'<span class="dtl-rev">{_fmt_eur(entry["rev"])}</span>'
                       f'{m.group(3)}'), chunk, count=1)
        if cumulative is not None:
            chunk = ACCUM_RE.sub(
                lambda m: (f'{m.group(1)}{m.group(2)} · '
                           f'<span class="dtl-rev">{_fmt_eur(cumulative)}</span>'
                           f'{m.group(3)}'), chunk, count=1)
        return chunk

    return (_one(left_html, *left) + '<div class="dtl-center">' + centre
            + '<div class="dtl-right">' + _one(right_html, *right))
