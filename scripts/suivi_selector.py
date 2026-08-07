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

    # --- the dropdown, the payload and the render script ------------------
    if data.get('candidates'):
        html, ok = _ui(html, data)
        if not ok:
            problems.append('suivi: could not place the comparison trigger')
        stats['trigger'] = ok

        # A caption slot under the header, filled in by the render script only
        # when a non-reference candidate is showing.
        html = html.replace('<div id="suivi-jour"',
                            '<div class="cmp-note" id="cmp-note"></div>\n    '
                            '<div id="suivi-jour"', 1)

        # The payload rides as inert JSON rather than a JS literal, so nothing
        # in an event name can execute. </script> inside a string would still
        # close the tag, so it is escaped.
        blob = json.dumps(data, separators=(',', ':'),
                          ensure_ascii=False).replace('</', '<\\/')
        html, n = re.subn(
            r'</body>',
            f'<script type="application/json" id="cmp-data">{blob}</script>\n'
            + RENDER_JS + '\n</body>', html, count=1)
        if n != 1:
            problems.append('suivi: no </body> to attach the selector to')
        stats['candidates'] = len(data['candidates'])
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


# ---------------------------------------------------------------- the UI --
# Every .cmp-* rule already ships in dashboard_v6_7.css, including the mobile
# ones, so nothing here authors CSS. Three details that cost the design work
# rounds and are load-bearing rather than cosmetic:
#
#   - the trigger must be LAST in .card-controls (the stylesheet gives it
#     order:2). First, it stranded itself at the left edge on mobile, and the
#     menu is anchored right:0, so it opened off-screen.
#   - .card-controls needs the section title on its own line below 720px, or
#     the dropdown wraps above the Jour/Semaine toggle. Stylesheet handles it,
#     but only if .toggle-group and .cmp are siblings inside .card-controls.
#   - the menu is capped at min(280px, 100vw - 34px) and the name ellipsises
#     at ~15ch, so "Bordeaux Octobre 2026" truncates instead of wrapping.

TOGGLE_RE = re.compile(r'(<div class="toggle-group">.*?</div>)', re.DOTALL)

CHEVRON = ('<svg class="cmp-chev" viewBox="0 0 10 6" fill="none" '
           'stroke="currentColor" stroke-width="1.6"><path d="M1 1l4 4 4-4"/></svg>')


def _menu_html(data):
    """The grouped dropdown. Only groups with candidates are emitted."""
    fam = data['name'].rsplit(' ', 1)[0] if data.get('name') else ''
    out = ['<div class="cmp-menu" id="cmp-menu" role="listbox">']
    for group, title in GROUP_TITLES:
        members = [c for c in data['candidates'] if c['group'] == group]
        if not members:
            continue
        out.append(f'<div class="cmp-group">{title.format(family=fam)}</div>')
        for c in members:
            ref = '<span class="cmp-ref">référence</span>' if c['reference'] else ''
            out.append(
                f'<button class="cmp-item" role="option" data-cmp="{c["id"]}" '
                f'aria-current="{"true" if c["reference"] else "false"}">'
                f'<span>{c["name"]}{ref}</span>'
                f'<span class="cmp-meta">{c["days"]} j</span></button>')
    out.append('</div>')
    return ''.join(out)


def _ui(html, data):
    """Wrap the toggle in .card-controls and append the trigger. (html, ok)."""
    start = html.find('<div id="sec-suivi"')
    if start < 0:
        return html, False
    header_end = html.find('</div>\n', start)
    m = TOGGLE_RE.search(html, start, start + 3000)
    if not m:
        return html, False

    ref = next((c for c in data['candidates'] if c['reference']), None)
    label = ref['name'] if ref else '—'
    block = (
        '<div class="card-controls">' + m.group(1) +
        '<div class="cmp">'
        '<button class="cmp-trigger" id="cmp-trigger" aria-haspopup="listbox" '
        'aria-expanded="false">'
        '<span class="cmp-eyebrow">vs</span>'
        f'<span class="cmp-name" id="cmp-current">{label}</span>{CHEVRON}</button>'
        + _menu_html(data) + '</div></div>'
    )
    return html[:m.start(1)] + block + html[m.end(1):], True


# The render script. Kept as one IIFE with no globals except the data element.
#
# Three rules that are easy to get wrong and silent when you do:
#   - cumulative figures are prefix-summed over the candidate's FULL series,
#     never over the rows on screen. A candidate whose campaign started before
#     the table does has no row for its early days, so summing what is visible
#     would understate every cumulative on the left.
#   - a date the candidate's series does not cover renders an em dash. A zero
#     asserts "no sales that day", which is false.
#   - the Diff column is rewritten only where it is actually a diff. The today
#     row's centre says "en cours" and future rows show J-X; both would be
#     destroyed by a blind rewrite.
RENDER_JS = """<script>
(function(){
  var el = document.getElementById('cmp-data');
  if(!el) return;
  var D = JSON.parse(el.textContent);
  var byId = {}; D.candidates.forEach(function(c){ byId[c.id] = c; });
  var DAYS = ['Lun','Mar','Mer','Jeu','Ven','Sam','Dim'];
  var MONTHS = ['Jan','Fév','Mar','Avr','Mai','Juin','Juil','Aoû','Sep','Oct','Nov','Déc'];
  var DASH = '—';

  function num(n){ return n.toLocaleString('en-US'); }
  function eur(v){ return '€' + Math.round(v).toLocaleString('en-US').replace(/,/g,' '); }
  function iso(d){ return d.toISOString().slice(0,10); }
  function parse(s){ var p = s.split('-'); return new Date(Date.UTC(+p[0], p[1]-1, +p[2])); }
  function label(d){ return DAYS[(d.getUTCDay()+6)%7] + ' ' + d.getUTCDate() + ' ' + MONTHS[d.getUTCMonth()]; }

  // Prefix sums over the WHOLE series, computed once per candidate.
  function pfx(c){
    if(c._p) return c._p;
    var keys = Object.keys(c.series).sort(), n = 0, r = 0, out = {};
    keys.forEach(function(k){ n += c.series[k].n; r += c.series[k].rev; out[k] = {n:n, rev:r}; });
    c._p = out; return out;
  }
  // Weekly buckets: weeks before the CANDIDATE's own event date. No offset.
  // Cumulative runs from the oldest week (highest S-number) downwards, which
  // is the direction run.py accumulates in, and over the FULL series - not
  // over the weeks that happen to be on screen.
  function wks(c){
    if(c._w) return c._w;
    var first = parse(c.first), out = {};
    Object.keys(c.series).forEach(function(k){
      var w = Math.floor((first - parse(k)) / 604800000);
      if(w < 1) return;
      var e = out[w] || (out[w] = {n:0, sg:0, dice:0, rev:0});
      e.n += c.series[k].n; e.sg += c.series[k].sg;
      e.dice += c.series[k].dice; e.rev += c.series[k].rev;
    });
    var cum = 0;
    Object.keys(out).map(Number).sort(function(a,b){ return b - a; })
      .forEach(function(w){ cum += out[w].n; out[w].cum = cum; });
    c._w = out; return out;
  }

  var rows = [].slice.call(document.querySelectorAll('#sec-suivi .dtl-row[data-cur], #sec-suivi .dtl-row[data-wk]'));
  // Snapshot the server-rendered original: returning to the reference restores
  // it rather than recomputing it, so the default view is always exactly what
  // run.py produced.
  rows.forEach(function(r){
    var l = r.querySelector('.dtl-left'), c = r.querySelector('.dtl-center');
    if(l) r._l = l.innerHTML;
    if(c) r._c = c.innerHTML;
  });

  function setSide(el, entry, cum, text){
    var d = el.querySelector('.dtl-date'), s = el.querySelector('.dtl-sales'),
        det = el.querySelector('.dtl-detail'), ac = el.querySelector('.dtl-accum');
    if(d) d.textContent = text;
    if(!entry){
      if(s) s.textContent = DASH;
      if(det) det.textContent = DASH;
      if(ac) ac.textContent = DASH;
      return;
    }
    if(s) s.innerHTML = num(entry.n) + ' <span class="dtl-rev">' + eur(entry.rev) + '</span>';
    if(det) det.textContent = 'SG ' + entry.sg + ' · DICE ' + entry.dice;
    if(ac && cum) ac.innerHTML = 'Cumulé ' + num(cum.n) + ' · <span class="dtl-rev">' + eur(cum.rev) + '</span>';
  }

  // The weekly row is a different shape from the daily one: five lines, a
  // percentage line the daily row does not have, and € in .dtl-accum where the
  // daily row has "Cumulé N". Reusing setSide here left that percentage line
  // showing the PREVIOUS candidate's figures under the new candidate's name -
  // stale numbers presented as current, which is worse than no numbers.
  function setWeek(el, entry, wk, capacity){
    var d = el.querySelector('.dtl-date'), s = el.querySelector('.dtl-sales'),
        det = el.querySelectorAll('.dtl-detail'), ac = el.querySelector('.dtl-accum');
    if(!entry){
      if(d) d.textContent = DASH;
      if(s) s.textContent = DASH;
      det.forEach(function(x){ x.textContent = DASH; });
      if(ac) ac.textContent = DASH;
      return;
    }
    if(d) d.textContent = 'S-' + wk;
    if(s) s.textContent = num(entry.n);
    if(det[0]) det[0].textContent = 'SG ' + entry.sg + ' · DICE ' + entry.dice;
    if(det[1]){
      var wp = capacity ? entry.n / capacity * 100 : 0;
      var cp = capacity ? entry.cum / capacity * 100 : 0;
      det[1].innerHTML = wp.toFixed(1) + '%&ensp;·&ensp;' + cp.toFixed(1) + '% cumulé';
    }
    if(ac) ac.textContent = '€' + Math.round(entry.rev / 1000) + 'k';
  }

  function setDiff(row, mine, theirs){
    var c = row.querySelector('.dtl-center');
    if(!c) return;
    var pct = c.querySelector('.dtl-pct'), diff = c.querySelector('.dtl-diff');
    // Only a real diff cell. "en cours" and "J-28" are not, and rewriting them
    // would delete information the row exists to show.
    if(!pct || !/%$/.test(pct.textContent) || !diff) return;
    if(theirs === null){ diff.textContent = DASH; pct.textContent = ''; return; }
    var d = mine - theirs;
    diff.textContent = (d >= 0 ? '+' : '') + num(d);
    diff.className = 'dtl-diff ' + (d >= 0 ? 'pos' : 'neg');
    pct.textContent = (theirs > 0 ? ((d / theirs * 100) >= 0 ? '+' : '') + (d / theirs * 100).toFixed(1) : '+0.0') + '%';
  }

  function render(id){
    var c = byId[id];
    if(!c) return;
    var isRef = !!c.reference, P = pfx(c), W = wks(c);
    rows.forEach(function(r){
      var left = r.querySelector('.dtl-left');
      if(!left) return;
      if(isRef){
        left.innerHTML = r._l;
        if(r._c) r.querySelector('.dtl-center').innerHTML = r._c;
        return;
      }
      var cur = r.getAttribute('data-cur');
      if(cur){
        var m = parse(cur); m.setUTCDate(m.getUTCDate() - c.offset);
        var k = iso(m), e = c.series[k] || null;
        setSide(left, e, P[k], e ? label(m) : DASH);
        var mineEl = r.querySelector('.dtl-right .dtl-sales');
        var mine = mineEl ? parseInt(mineEl.textContent.replace(/[^0-9]/g,''), 10) || 0 : 0;
        setDiff(r, mine, e ? e.n : null);
      } else {
        setWeek(left, W[r.getAttribute('data-wk')] || null,
                r.getAttribute('data-wk'), c.capacity);
      }
    });
    document.getElementById('cmp-current').textContent = c.name;
    var note = document.getElementById('cmp-note');
    if(note){
      note.textContent = isRef ? '' :
        c.name + ' — jauge ' + num(c.capacity) + ' places (contre ' + num(D.capacity) +
        ' ici) · seul ce tableau change, les autres chiffres restent sur ' +
        (byId[D.reference] ? byId[D.reference].name : 'la référence') + '.';
    }
    document.querySelectorAll('.cmp-item').forEach(function(b){
      b.setAttribute('aria-current', b.getAttribute('data-cmp') === id ? 'true' : 'false');
    });
  }

  var menu = document.getElementById('cmp-menu'), trig = document.getElementById('cmp-trigger');
  trig.addEventListener('click', function(e){
    e.stopPropagation();
    var open = menu.classList.toggle('open');
    trig.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
  document.addEventListener('click', function(e){
    if(!e.target.closest('.cmp')){ menu.classList.remove('open'); trig.setAttribute('aria-expanded','false'); }
  });
  document.addEventListener('keydown', function(e){ if(e.key === 'Escape') menu.classList.remove('open'); });
  document.querySelectorAll('.cmp-item').forEach(function(b){
    b.addEventListener('click', function(){
      render(b.getAttribute('data-cmp'));
      menu.classList.remove('open');
      trig.setAttribute('aria-expanded','false');
    });
  });
  // Selection is deliberately not persisted: a remembered comparison someone
  // forgot about is how a table quietly stops meaning what they think it does.
})();
</script>"""
