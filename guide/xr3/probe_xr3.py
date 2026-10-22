#!/usr/bin/env python3
"""
XR3 measurement probe -- read-only, Festiflow guide round XR3 (2026-10-21/22).

    python -I guide/xr3/probe_xr3.py shotgun episode   # M1 walk · M4 past ids · M6 fills · M7 paths (EPISODE token)
    python -I guide/xr3/probe_xr3.py shotgun sonora    # the same on the SONORA token
    python -I guide/xr3/probe_xr3.py dice              # M4 history · M6 fields/fills · M7 schema (DICE token)

WHAT IT MAY DO
  GET on api.shotgun.live; POST GraphQL *queries* (never a mutation) on DICE. Nothing else.

WHAT IT MAY PRINT OR COMMIT (ticketing_api is PUBLIC, so are its Actions logs)
  Field NAMES, COUNTS, timings, event ids, event names (public marketing names),
  dates, HTTP status codes, organiser ids (not secret, ruled 2026-10-21).
  NEVER a token, a header, a URL (a Shotgun URL carries its token), a personal
  value, a ticket id, or a MONEY total. Money and ticket-id sets go to
  guide/xr3/private/ only; seal.sh encrypts that folder to a key held by the
  measurement seat and deletes the plaintext. Every printed string passes scrub().

Secrets arrive as environment variables named by the workflow step that uses them.
Stdlib only.
"""

import base64
import collections
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'out'
PRIV = HERE / 'private'
OUT.mkdir(parents=True, exist_ok=True)

SG = os.environ.get('XR3_SG_BASE') or 'https://api.shotgun.live'          # override = local mock tests only
DICE = os.environ.get('XR3_DICE_URL') or 'https://partners-endpoint.dice.fm/graphql'
PACE = float(os.environ.get('XR3_PACE_S') or 0.8)          # the standalone's value, one fetcher per token
DPACE = float(os.environ.get('XR3_DPACE_S') or 0.2)
TIMEOUT = 60
WALK_BUDGET_S = float(os.environ.get('XR3_WALK_BUDGET_MIN') or 290) * 60
DICE_BUDGET_S = float(os.environ.get('XR3_DICE_BUDGET_MIN') or 200) * 60
T_START = time.time()

ENV = {k: os.environ.get(k, '').strip() for k in (
    'SHOTGUN_TOKEN_EPISODE', 'SHOTGUN_TOKEN_SONORA', 'SHOTGUN_ORGANIZER_ID_EPISODE',
    'SHOTGUN_ORGANIZER_ID_SONORA', 'DICE_TOKEN')}
# Only the TOKENS are scrubbed: the organiser ids are printed by ruling (not secret).
SECRETS = sorted({ENV[k] for k in ('SHOTGUN_TOKEN_EPISODE', 'SHOTGUN_TOKEN_SONORA', 'DICE_TOKEN')
                  if ENV[k] and len(ENV[k]) >= 6}, key=len, reverse=True)

PAST_SG_IDS = [313304, 399931, 406642, 408231, 433590, 444613, 455482, 505434]
WATCH_SG_IDS = (433590, 505434)
FESTIFLOW_SG = {494642: 'evt-px', 505434: 'evt-sb', 549064: 'evt-cc', 535882: 'evt-ep', 544355: 'evt-si',
                546274: 'evt-gv', 557151: 'evt-rn', 553118: 'evt-croisiere'}

# Shotgun keys that are personal or identify a ticket/buyer: never printed, counted only.
SG_PERSONAL = ('contact_email', 'contact_first_name', 'contact_last_name', 'contact_phone', 'contact_id',
               'contact_gender', 'contact_birthday', 'contact_postal_code', 'contact_locality',
               'contact_company_name', 'user_id', 'contact_country', 'contact_newsletter_optin',
               'ticket_scan_code', 'order_id')
SG_MONEY = ('deal_price', 'deal_service_fee', 'deal_user_service_fee', 'deal_producer_cost')

# ---------------------------------------------------------------- scrubbing / output
_PATTERNS = [
    (re.compile(r'(?i)(token|key|api_key)=[^&\s"\']+'), r'\1=***'),
    (re.compile(r'(?i)bearer\s+\S+'), 'Bearer ***'),
    (re.compile(r'eyJ[\w-]{5,}\.[\w-]{5,}\.[\w-]*'), '<jwt>'),
    (re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'), '<email>'),
    (re.compile(r'https?://\S+'), '<url>'),
    (re.compile(r'[A-Za-z0-9_\-]{40,}'), '<opaque>'),
]


def scrub(text):
    s = str(text)
    for sec in SECRETS:
        s = s.replace(sec, '***')
    for rx, rep in _PATTERNS:
        s = rx.sub(rep, s)
    return s


LOG = []
PRIVATE = {}


def out(*parts):
    line = scrub(' '.join(str(p) for p in parts))
    LOG.append(line)
    print(line, flush=True)


def jd(o):
    return json.dumps(o, ensure_ascii=False, default=str, sort_keys=False)


def elapsed():
    return time.time() - T_START


# ---------------------------------------------------------------- http
HTTP_STATS = collections.Counter()
HEADER_NAMES = {}
RATE_HEADERS = {}


def _note_headers(host, headers):
    names = sorted({k.lower() for k in headers.keys()})
    HEADER_NAMES.setdefault(host, names)
    for k in names:
        if re.search(r'rate|retry|limit|quota', k):
            v = str(headers.get(k, '')).strip()
            if re.fullmatch(r'[0-9.]{1,12}', v):
                RATE_HEADERS[k] = v


def request(url, method='GET', body=None, headers=None, host='shotgun'):
    """-> (status, json_or_None, scrubbed error, seconds, bytes). Never raises, never logs the url."""
    data = json.dumps(body).encode() if body is not None else None
    h = {'Accept': 'application/json'}
    if body is not None:
        h['Content-Type'] = 'application/json'
    h.update(headers or {})
    rl = tries = 0
    while True:
        tries += 1
        t0 = time.time()
        try:
            req = urllib.request.Request(url, data=data, headers=h, method=method)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                raw = r.read()
                _note_headers(host, r.headers)
                HTTP_STATS[f'{host}:{r.status}'] += 1
                try:
                    return r.status, json.loads(raw.decode('utf-8')), None, time.time() - t0, len(raw)
                except ValueError:
                    return r.status, None, 'non-JSON body (%d bytes)' % len(raw), time.time() - t0, len(raw)
        except urllib.error.HTTPError as e:
            _note_headers(host, e.headers or {})
            HTTP_STATS[f'{host}:{e.code}'] += 1
            detail = ''
            try:
                detail = e.read().decode('utf-8', 'replace')[:300]
            except Exception:
                pass
            if '<html' in detail.lower() or '<!doctype' in detail.lower():
                detail = '(an HTML page)'
            if e.code == 429 and rl < 6 and 'challenge' not in detail:
                rl += 1
                ra = (e.headers or {}).get('Retry-After')
                wait = int(ra) if str(ra).isdigit() else 60
                out(f'   [429 #{rl} on {host}; Retry-After={"set" if ra else "absent"}; waiting {wait}s]')
                time.sleep(wait)
                continue
            if e.code in (500, 502, 503, 504) and tries < 4:
                time.sleep(2 ** tries)
                continue
            return e.code, None, scrub(detail), time.time() - t0, 0
        except Exception as e:
            HTTP_STATS[f'{host}:neterr'] += 1
            if tries < 5:
                time.sleep(2 ** tries)
                continue
            return None, None, scrub(type(e).__name__), time.time() - t0, 0


def sg_url(path, **params):
    return f'{SG}{path}?' + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})


def list_in(payload):
    if isinstance(payload, list):
        return None, payload
    if isinstance(payload, dict):
        for k, v in payload.items():
            if isinstance(v, list) and (not v or isinstance(v[0], dict)):
                return k, v
    return None, None


def next_of(js):
    return ((js.get('pagination') or {}) if isinstance(js, dict) else {}).get('next')


def shape(v):
    """A value's FORMAT, never the value: digits -> 9, letters -> a."""
    if v is None:
        return 'null'
    return re.sub(r'[A-Za-z]', 'a', re.sub(r'\d', '9', str(v)))[:40]


def after_shape(next_url):
    """The `after` cursor's FORMAT inside pagination.next (the URL itself is never kept)."""
    if not next_url:
        return None
    try:
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(next_url).query)
        a = (q.get('after') or [None])[0]
        return shape(a) if a else 'no after param'
    except Exception:
        return 'unparsable'


def after_value(next_url):
    """The bare cursor (timestamp_ticketid) -- kept SEALED only, for a resume."""
    try:
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(next_url).query)
        return (q.get('after') or [None])[0]
    except Exception:
        return None


def parse_dt(s):
    if not s:
        return None
    t = re.sub(r'([+-]\d{2}:?\d{2}|Z)$', '', str(s).strip()).replace('T', ' ')
    for f in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(t, f)
        except ValueError:
            pass
    return None


def filled(v):
    return v is not None and v != '' and v != [] and v != {}


# =================================================================== token claims
def claims_of(tok):
    parts = tok.split('.') if tok else []
    if len(parts) != 3:
        return {'jwt': False, 'length': len(tok or '')}
    try:
        p = parts[1] + '=' * (-len(parts[1]) % 4)
        pl = json.loads(base64.urlsafe_b64decode(p.encode()).decode())
    except Exception:
        return {'jwt': True, 'claims': 'undecodable'}
    r = {'jwt': True, 'length': len(tok), 'claim_names': sorted(pl)}
    org = pl.get('organizerId')
    r['organizerId'] = int(org) if str(org).isdigit() else ('absent' if org is None else '<non-numeric>')
    if 'iat' in pl and isinstance(pl['iat'], (int, float)):
        r['iat_date'] = datetime.fromtimestamp(pl['iat'], timezone.utc).strftime('%Y-%m-%d')
    r['has_exp'] = 'exp' in pl
    return r


# =================================================================== Shotgun
class EventAgg:
    __slots__ = ('rows', 'name', 'start', 'end', 'status', 'channel', 'currency', 'ord_min', 'ord_max',
                 'upd_min', 'upd_max', 'ids', 'fill', 'money', 'pm', 'optin_true', 'utm', 'org_fields',
                 'vat', 'first_seen_page')

    def __init__(self):
        self.rows = 0
        self.name = self.start = self.end = None
        self.status = collections.Counter()
        self.channel = collections.Counter()
        self.currency = collections.Counter()
        self.ord_min = self.ord_max = self.upd_min = self.upd_max = None
        self.ids = set()
        self.fill = collections.Counter()
        self.money = {}
        self.pm = collections.Counter()
        self.optin_true = 0
        self.utm = {}
        self.org_fields = {}
        self.vat = collections.Counter()
        self.first_seen_page = None


def sg_add(agg, t, page):
    a = agg.get(str(t.get('event_id')))
    if a is None:
        a = agg[str(t.get('event_id'))] = EventAgg()
        a.first_seen_page = page
    a.rows += 1
    if a.name is None:
        a.name = scrub(str(t.get('event_name') or ''))[:90]
        a.start = str(t.get('event_start_time') or '')[:16] or None
        a.end = str(t.get('event_end_time') or '')[:16] or None
    st = str(t.get('ticket_status'))
    a.status[st] += 1
    a.channel[f'{st}|{t.get("deal_channel")}'] += 1
    a.currency[str(t.get('currency'))] += 1
    a.vat[str(t.get('deal_vat_rate'))] += 1
    o = str(t.get('ordered_at') or '')[:19]
    if o:
        a.ord_min = o if a.ord_min is None or o < a.ord_min else a.ord_min
        a.ord_max = o if a.ord_max is None or o > a.ord_max else a.ord_max
    u = str(t.get('ticket_updated_at') or '')[:19]
    if u:
        a.upd_min = u if a.upd_min is None or u < a.upd_min else a.upd_min
        a.upd_max = u if a.upd_max is None or u > a.upd_max else a.upd_max
    a.ids.add(str(t.get('ticket_id')))
    for k, v in t.items():
        if filled(v):
            a.fill[k] += 1
        if k.startswith('utm_') and filled(v):
            a.utm.setdefault(k, set()).add(str(v)[:200])
        if re.search(r'organi[sz]|host|owner|producer_id|promoter', k) and not k.startswith('deal_') and filled(v):
            a.org_fields.setdefault(k, set()).add(str(v)[:40])
    if t.get('contact_newsletter_optin') is True:
        a.optin_true += 1
    a.pm[str(t.get('payment_method'))] += 1
    m = a.money.setdefault(st, {f: 0 for f in SG_MONEY})
    for f in SG_MONEY:
        v = t.get(f)
        if isinstance(v, (int, float)):
            m[f] += v


def sg_walk(acct, tok, org, extra=None, budget_s=None, label='walk'):
    """Walk /tickets WITHOUT event_id to the end (or the budget). Aggregates per event."""
    params = dict(token=tok, organizer_id=org, include_cohosted_events='1')
    params.update(extra or {})
    url = sg_url('/tickets', **params)
    agg, pages, rows = {}, 0, 0
    seen = set()
    err, envelope, cursor_shape = None, None, None
    upd_prev, inversions = None, 0
    first_upd = last_upd = None
    keys = collections.Counter()
    t0 = time.time()
    last_note = t0
    finished = False
    resume = None
    while url:
        if budget_s is not None and time.time() - t0 > budget_s:
            err = f'stopped at the time budget ({round(budget_s / 60)} min) - PARTIAL'
            resume = after_value(url)
            break
        if url in seen:
            err = 'pagination loop'
            break
        seen.add(url)
        st, js, e, sec, nb = request(url)
        if st != 200 or js is None:
            err = f'HTTP {st} {e or ""} at page {pages + 1}'
            resume = after_value(url)
            break
        pages += 1
        lk, items = list_in(js)
        items = items or []
        if envelope is None and isinstance(js, dict):
            envelope = {'envelope_keys': sorted(js), 'list_key': lk,
                        'pagination_keys': sorted(js['pagination']) if isinstance(js.get('pagination'), dict) else None}
        for t in items:
            if not isinstance(t, dict):
                continue
            rows += 1
            keys.update(t.keys())
            u = str(t.get('ticket_updated_at') or '')
            if u:
                if first_upd is None:
                    first_upd = u[:19]
                last_upd = u[:19]
                if upd_prev is not None and u < upd_prev:
                    inversions += 1
                upd_prev = u
            sg_add(agg, t, pages)
        nxt = next_of(js)
        if cursor_shape is None and nxt:
            cursor_shape = after_shape(nxt)
        if not items or not nxt:
            finished = True
            break
        url = nxt
        if time.time() - last_note > 600:
            out(f'   [{acct} {label}: {pages} pages, {rows} rows, {len(agg)} events, {round(time.time() - t0)}s]')
            last_note = time.time()
        time.sleep(PACE)
    return {'agg': agg, 'pages': pages, 'rows': rows, 'seconds': round(time.time() - t0, 1), 'error': err,
            'finished': finished, 'envelope': envelope, 'after_cursor_shape': cursor_shape,
            'ticket_updated_at_inversions': inversions, 'first_ticket_updated_at': first_upd,
            'last_ticket_updated_at': last_upd, 'keys': keys, 'resume_cursor': resume}


def sg_event_pull(tok, org, eid, max_pages=None, budget_s=None):
    url = sg_url('/tickets', token=tok, organizer_id=org, event_id=eid, include_cohosted_events='1')
    pages, ids, status = 0, set(), collections.Counter()
    t0, err, seen = time.time(), None, set()
    first_page_rows = None
    mismatch = 0
    while url:
        if url in seen:
            err = 'pagination loop'
            break
        seen.add(url)
        st, js, e, sec, nb = request(url)
        if st != 200 or js is None:
            err = f'HTTP {st} {e or ""}'
            break
        pages += 1
        items = list_in(js)[1] or []
        if first_page_rows is None:
            first_page_rows = len(items)
        for t in items:
            ids.add(str(t.get('ticket_id')))
            status[str(t.get('ticket_status'))] += 1
            if str(t.get('event_id')) != str(eid):
                mismatch += 1
        nxt = next_of(js)
        if not items or not nxt:
            break
        if max_pages and pages >= max_pages:
            err = f'stopped at {max_pages} page(s) by design'
            break
        if budget_s and time.time() - t0 > budget_s:
            err = 'stopped at the time budget - PARTIAL'
            break
        url = nxt
        time.sleep(PACE)
    return {'pages': pages, 'rows': sum(status.values()), 'distinct_ids': len(ids), 'status': dict(status),
            'first_page_rows': first_page_rows, 'event_id_mismatch': mismatch, 'error': err,
            'seconds': round(time.time() - t0, 1)}, ids


def digest(ids):
    return hashlib.sha256('\n'.join(sorted(ids)).encode()).hexdigest()[:16]


def shotgun(acct):
    tok = ENV[f'SHOTGUN_TOKEN_{acct.upper()}']
    org = ENV[f'SHOTGUN_ORGANIZER_ID_{acct.upper()}']
    res = {'account': acct}
    if not tok:
        out(f'{acct}: token not set - SKIPPED')
        return res
    cl = claims_of(tok)
    cl['organizerId_equals_secret'] = (str(cl.get('organizerId')) == org) if org else None
    cl['organizer_secret_set'] = bool(org)
    res['token'] = cl
    out(f'\n## {acct} · token claims (names; organiser id printed by ruling)')
    out(jd(cl))
    if not org and isinstance(cl.get('organizerId'), int):
        org = str(cl['organizerId'])
        out('   organiser secret empty: using the id from the claims')

    # ---- M7 · Shotgun payout-like paths (read GETs, status only)
    out(f'\n## M7 · {acct} · payout-like paths (GET, status only)')
    m7 = []
    for path in ('/payouts', '/payments', '/settlements', '/transfers', '/balance', '/invoices'):
        st, js, e, sec, nb = request(sg_url(path, token=tok, organizer_id=org))
        rec = {'path': path, 'status': st, 'error_body': e}
        if js is not None:
            lk, items = list_in(js)
            rec['top_keys'] = sorted(js) if isinstance(js, dict) else type(js).__name__
            rec['list_key'] = lk
            rec['count_page1'] = len(items) if items is not None else None
            rec['item_fields'] = sorted({k for it in (items or []) if isinstance(it, dict) for k in it})
        m7.append(rec)
        out(jd(rec))
        time.sleep(PACE)
    res['M7_paths'] = m7

    # ---- M4 · past ids by event_id, first page (does the per-event read still answer?)
    out(f'\n## M4 · {acct} · known past Shotgun ids, by event_id, first page')
    m4 = []
    for eid in PAST_SG_IDS:
        r, _ = sg_event_pull(tok, org, eid, max_pages=1)
        r['shotgun_id'] = eid
        m4.append(r)
        out(jd(r))
        time.sleep(PACE)
    res['M4_first_pages'] = m4

    # ---- M1 · the co-host flag: one page with vs without, organiser-wide, 7-day cursor
    now = datetime.now(timezone.utc)
    cur7 = (now - timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%S.000Z') + '_0'
    out(f'\n## M1 · {acct} · organiser-wide incremental: after = 7 days ago, no event_id')
    inc = {}
    for flag in ('1', None):
        label = 'with_cohost_flag' if flag else 'without_cohost_flag'
        params = {'after': cur7}
        if flag is None:
            w = sg_walk_noflag(tok, org, cur7)
        else:
            w = sg_walk(acct, tok, org, extra=params, budget_s=40 * 60, label='incremental 7d')
        ev = {eid: {'rows': a.rows, 'name': a.name, 'start': a.start, 'status': dict(a.status)}
              for eid, a in sorted(w['agg'].items(), key=lambda kv: -kv[1].rows)}
        fu = parse_dt(w['first_ticket_updated_at'])
        upd_before = bool(fu and fu < parse_dt(cur7[:19]))
        inc[label] = {'pages': w['pages'], 'rows': w['rows'], 'seconds': w['seconds'], 'finished': w['finished'],
                      'error': w['error'], 'distinct_events': len(w['agg']), 'events': ev,
                      'first_ticket_updated_at': w['first_ticket_updated_at'],
                      'last_ticket_updated_at': w['last_ticket_updated_at'],
                      'a_row_older_than_cursor': upd_before,
                      'ticket_updated_at_inversions': w['ticket_updated_at_inversions'],
                      'after_cursor_shape': w['after_cursor_shape']}
        out(jd({k: v for k, v in inc[label].items() if k != 'events'}))
        out('   events: ' + jd({k: (v['rows'], v['name']) for k, v in ev.items()}))
        time.sleep(PACE)
    res['M1_incremental_7d'] = inc

    # ---- M1 · 433590 by event_id in full (to hold the walk against it)
    out(f'\n## M1/M4 · {acct} · 433590 by event_id, full')
    r433, ids433 = sg_event_pull(tok, org, 433590, budget_s=20 * 60)
    r433['digest'] = digest(ids433) if ids433 else None
    res['pull_433590'] = r433
    out(jd(r433))

    # ---- M1 · THE WALK
    out(f'\n## M1 · {acct} · the organiser-wide walk: /tickets, no event_id, include_cohosted_events=1')
    budget = max(15 * 60, WALK_BUDGET_S - elapsed())
    w = sg_walk(acct, tok, org, budget_s=budget, label='walk')
    agg = w['agg']
    cat = []
    for eid, a in sorted(agg.items(), key=lambda kv: (kv[1].start or '', kv[0])):
        cat.append({'event_id': int(eid) if eid.isdigit() else eid, 'festiflow': FESTIFLOW_SG.get(int(eid)) if eid.isdigit() else None,
                    'name': a.name, 'start': a.start, 'end': a.end, 'rows': a.rows, 'valid': a.status.get('valid', 0),
                    'status': dict(a.status.most_common()), 'currency': dict(a.currency),
                    'ordered_first': (a.ord_min or '')[:10] or None, 'ordered_last': (a.ord_max or '')[:10] or None,
                    'updated_first': (a.upd_min or '')[:10] or None, 'updated_last': (a.upd_max or '')[:10] or None,
                    'distinct_ticket_ids': len(a.ids), 'ticket_id_set_digest': digest(a.ids),
                    'first_seen_on_page': a.first_seen_page,
                    'organiser_like_fields': {k: sorted(v)[:5] if all(x.isdigit() for x in v) else f'{len(v)} distinct'
                                              for k, v in a.org_fields.items()}})
    starts = [c['start'] for c in cat if c['start']]
    ords = [c['ordered_first'] for c in cat if c['ordered_first']]
    walk = {'pages': w['pages'], 'rows': w['rows'], 'seconds': w['seconds'], 'finished': w['finished'],
            'error': w['error'], 'envelope': w['envelope'], 'after_cursor_shape': w['after_cursor_shape'],
            'distinct_events': len(agg), 'ticket_updated_at_inversions': w['ticket_updated_at_inversions'],
            'first_ticket_updated_at': w['first_ticket_updated_at'], 'last_ticket_updated_at': w['last_ticket_updated_at'],
            'oldest_event_start': min(starts) if starts else None, 'newest_event_start': max(starts) if starts else None,
            'oldest_ordered_at': min(ords) if ords else None,
            'by_start_year': dict(sorted(collections.Counter((c['start'] or '????')[:4] for c in cat).items())),
            'key_count': len(w['keys']), 'keys_union': sorted(w['keys']),
            'keys_not_on_every_row': sorted(k for k, c in w['keys'].items() if c != w['rows']),
            'watch': {str(e): (next((c for c in cat if c['event_id'] == e), None) or 'ABSENT from the walk')
                      for e in WATCH_SG_IDS},
            'festiflow_ids_absent': sorted(e for e in FESTIFLOW_SG if str(e) not in agg),
            'pull_433590_vs_walk': None}
    if '433590' in agg:
        walk['pull_433590_vs_walk'] = {'walk_rows': agg['433590'].rows, 'pull_rows': r433['rows'],
                                       'same_ticket_id_set': digest(agg['433590'].ids) == r433['digest']}
    res['M1_walk'] = walk
    res['M1_catalogue'] = cat
    out(jd({k: v for k, v in walk.items() if k not in ('keys_union', 'watch')}))
    out('watch: ' + jd(walk['watch']))
    for c in cat:
        out('   ' + jd({k: c[k] for k in ('event_id', 'festiflow', 'name', 'start', 'end', 'rows', 'valid',
                                           'ordered_first', 'ordered_last', 'updated_last', 'currency')}))

    # ---- M6 · Shotgun fill rates (counts only), every event + the two named
    fills = {}
    for eid, a in agg.items():
        fills[eid] = {'rows': a.rows, 'filled': {k: a.fill.get(k, 0) for k in sorted(w['keys'])},
                      'newsletter_optin_true': a.optin_true,
                      'utm_distinct_values': {k: len(v) for k, v in a.utm.items()},
                      'payment_method': dict(a.pm.most_common(8)),
                      'status_x_channel': dict(a.channel.most_common()),
                      'deal_vat_rate': dict(a.vat)}
    tot = collections.Counter()
    for a in agg.values():
        tot.update(a.fill)
    res['M6_fill_all_rows'] = {'rows': w['rows'], 'filled': {k: tot.get(k, 0) for k in sorted(w['keys'])}}
    res['M6_fill_by_event'] = fills
    out('\n## M6 · fill over every walked row: ' + jd(res['M6_fill_all_rows']))

    # ---- M4 · every past event the walk found: does event_id answer (first page)?
    out(f'\n## M4 · {acct} · every event the walk found that started before 2026-01-01, by event_id (first page)')
    m4b = []
    for c in cat:
        if (c['start'] or '9999') >= '2026-01-01' or elapsed() > WALK_BUDGET_S + 25 * 60:
            continue
        r, _ = sg_event_pull(tok, org, c['event_id'], max_pages=1)
        r['shotgun_id'] = c['event_id']
        m4b.append({k: r[k] for k in ('shotgun_id', 'first_page_rows', 'status', 'error', 'event_id_mismatch')})
        time.sleep(PACE)
    res['M4_walk_past_events_first_page'] = m4b
    out(jd({'checked': len(m4b), 'answered_rows': sum(1 for r in m4b if r['first_page_rows']),
            'empty': [r['shotgun_id'] for r in m4b if not r['first_page_rows']],
            'errors': [(r['shotgun_id'], r['error']) for r in m4b if r['error'] and 'by design' not in r['error']]}))

    # ---- sealed: money per event and status, ticket-id sets (for the cross-token overlap)
    PRIVATE['money_by_event_status'] = {eid: a.money for eid, a in agg.items()}
    PRIVATE['ticket_ids_by_event'] = {eid: sorted(a.ids) for eid, a in agg.items()}
    PRIVATE['ticket_ids_433590_pull'] = sorted(ids433)
    PRIVATE['resume_cursor'] = w['resume_cursor']
    return res


def sg_walk_noflag(tok, org, cur7):
    """The same 7-day organiser-wide read WITHOUT include_cohosted_events."""
    url = sg_url('/tickets', token=tok, organizer_id=org, after=cur7)
    agg, pages, rows, t0, err, finished = {}, 0, 0, time.time(), None, False
    first = last = None
    seen = set()
    while url and time.time() - t0 < 40 * 60:
        if url in seen:
            err = 'pagination loop'
            break
        seen.add(url)
        st, js, e, sec, nb = request(url)
        if st != 200 or js is None:
            err = f'HTTP {st} {e or ""}'
            break
        pages += 1
        items = list_in(js)[1] or []
        for t in items:
            rows += 1
            u = str(t.get('ticket_updated_at') or '')[:19]
            first = first or u
            last = u or last
            sg_add(agg, t, pages)
        nxt = next_of(js)
        if not items or not nxt:
            finished = True
            break
        url = nxt
        time.sleep(PACE)
    return {'agg': agg, 'pages': pages, 'rows': rows, 'seconds': round(time.time() - t0, 1), 'error': err,
            'finished': finished, 'first_ticket_updated_at': first, 'last_ticket_updated_at': last,
            'ticket_updated_at_inversions': None, 'after_cursor_shape': None}


# =================================================================== DICE
def dq(query, variables=None):
    st, js, err, sec, nb = request(DICE, method='POST', body={'query': query, 'variables': variables or {}},
                                   headers={'Authorization': 'Bearer ' + ENV['DICE_TOKEN']}, host='dice')
    errs = None
    if js and js.get('errors'):
        errs = [scrub(e.get('message', ''))[:200] for e in js['errors']]
    time.sleep(DPACE)
    return st, (js or {}).get('data') if js else None, errs or err, sec, nb


def rid(eid):
    return base64.b64encode(f'Event:{eid}'.encode()).decode()


def num(x):
    try:
        return int(base64.b64decode(x).decode().split(':')[-1])
    except Exception:
        return x


TYPEQ = ('query T($n:String!){ __type(name:$n){ name kind fields{ name type{ name kind ofType{ name kind '
         'ofType{ name kind ofType{ name kind }}}}} } }')


def unwrap(t):
    chain = []
    while t:
        chain.append(t.get('kind'))
        if t.get('name'):
            return t['name'], t.get('kind'), chain
        t = t.get('ofType')
    return None, None, chain


def dtype(name):
    st, d, err, *_ = dq(TYPEQ, {'n': name})
    t = (d or {}).get('__type') if d else None
    if not t:
        return None
    return {f['name']: unwrap(f['type']) for f in (t.get('fields') or [])}


PERSONAL_RX = re.compile(r'(?i)(email|phone|first_?name|last_?name|fullname|^name$|dob|birth|secure|token|'
                         r'address|barcode|^code$|holder|fan$|survey|ip$|^ipAddress)')
MARKET_RX = re.compile(r'(?i)(channel|source|utm|track|referr|campaign|promo|affiliate|partner|city|country|'
                       r'post|zip|age|gender|opt|marketing|consent|device|platform|app|lang|locale|link|code)')
PAYOUT_RX = re.compile(r'(?i)(payout|settle|balance|statement|remit|invoice|payment|bank|reddition|report|'
                       r'transfer|withdraw|disburse|account)')


def dice():
    res = {}
    if not ENV['DICE_TOKEN']:
        out('DICE_TOKEN not set - SKIPPED')
        return res
    # ---- schema: type names (M7), Viewer fields
    out('\n## M7 · DICE schema: every type and field whose name looks like payouts / settlements')
    st, d, err, *_ = dq('{ __schema { types { name kind fields { name } } queryType { name } mutationType { fields { name } } } }')
    types = ((d or {}).get('__schema') or {}).get('types') or []
    res['schema_error'] = err
    res['type_count'] = len(types)
    pay_types = sorted(t['name'] for t in types if PAYOUT_RX.search(t['name'] or '') and not t['name'].startswith('__'))
    pay_fields = sorted(f'{t["name"]}.{f["name"]}' for t in types if not (t['name'] or '').startswith('__')
                        for f in (t.get('fields') or []) if PAYOUT_RX.search(f['name']))
    res['M7_types_matching'] = pay_types
    res['M7_fields_matching'] = pay_fields
    res['mutation_fields'] = sorted(f['name'] for f in ((((d or {}).get('__schema') or {}).get('mutationType') or {}).get('fields') or []))
    out(jd({'types': len(types), 'payout_like_types': pay_types, 'payout_like_fields': pay_fields,
            'mutation_fields': res['mutation_fields']}))
    viewer = dtype('Viewer') or {}
    res['viewer_fields'] = {k: v[0] for k, v in viewer.items()}
    out('Viewer fields: ' + jd(res['viewer_fields']))
    # any viewer connection whose name looks like money movement: count it, nothing else
    for fname, (tname, kind, _) in viewer.items():
        if PAYOUT_RX.search(fname) and tname and tname.endswith('Connection'):
            st, d, e, *_ = dq('{ viewer { %s(first:1){ totalCount } } }' % fname)
            res.setdefault('M7_viewer_counts', {})[fname] = ((d or {}).get('viewer') or {}).get(fname) if d else e
    out('M7 viewer counts: ' + jd(res.get('M7_viewer_counts')))

    # ---- M6 · field names of the marketing-bearing types
    out('\n## M6 · DICE types: field names (no value)')
    tf = {}
    for tn in ('Order', 'Ticket', 'Event', 'Fan', 'Return', 'TicketTransfer', 'Extra', 'TicketType', 'PriceTier'):
        f = dtype(tn)
        if f is not None:
            tf[tn] = {k: f'{v[0]}:{v[1]}' for k, v in sorted(f.items())}
    res['M6_type_fields'] = tf
    for tn, f in tf.items():
        out(f'{tn}: ' + jd(sorted(f)))

    # ---- M4 · every event on the token
    out('\n## M4 · DICE: every event on the token, with counts')
    events, after, pages, total = [], None, 0, None
    while pages < 30:
        st, d, e, *_ = dq('query E($a:String){ viewer { events(first:100, after:$a){ totalCount pageInfo{ endCursor hasNextPage }'
                          ' edges{ node{ id name startDatetime endDatetime state currency } } } } }', {'a': after})
        if e or not d:
            res['events_error'] = e
            break
        c = d['viewer']['events']
        total = c.get('totalCount')
        pages += 1
        events += [x['node'] for x in c.get('edges') or []]
        if not c['pageInfo']['hasNextPage']:
            break
        after = c['pageInfo']['endCursor']
    rows = []
    for ev in events:
        r = rid(num(ev['id'])) if isinstance(num(ev['id']), int) else ev['id']
        q = ('query C($e:ID!){ viewer { o: orders(first:1, where:{eventId:{eq:$e}}){ totalCount } '
             'r: returns(first:1, where:{eventId:{eq:$e}}){ totalCount } '
             't: tickets(first:1, where:{eventId:{eq:$e}}){ totalCount } '
             'x: ticketTransfers(first:1, where:{eventId:{eq:$e}}){ totalCount } } }')
        st, d, e, *_ = dq(q, {'e': r})
        v = (d or {}).get('viewer') or {}
        rows.append({'dice_id': num(ev['id']), 'name': scrub(ev.get('name') or '')[:90],
                     'start': str(ev.get('startDatetime') or '')[:16], 'end': str(ev.get('endDatetime') or '')[:16],
                     'state': ev.get('state'), 'currency': ev.get('currency'),
                     'orders': (v.get('o') or {}).get('totalCount'), 'returns': (v.get('r') or {}).get('totalCount'),
                     'tickets': (v.get('t') or {}).get('totalCount'), 'transfers': (v.get('x') or {}).get('totalCount'),
                     'error': e})
    rows.sort(key=lambda r: r['start'])
    res['M4_events'] = {'returned': len(events), 'totalCount': total, 'pages': pages, 'rows': rows}
    by_year = collections.defaultdict(lambda: collections.Counter())
    for r in rows:
        y = r['start'][:4]
        by_year[y]['events'] += 1
        by_year[y]['with_orders'] += 1 if (r['orders'] or 0) > 0 else 0
        by_year[y]['with_returns'] += 1 if (r['returns'] or 0) > 0 else 0
        by_year[y]['orders'] += r['orders'] or 0
        by_year[y]['tickets'] += r['tickets'] or 0
        by_year[y]['returns'] += r['returns'] or 0
    res['M4_by_year'] = {y: dict(c) for y, c in sorted(by_year.items())}
    out(jd({'returned': len(events), 'totalCount': total, 'by_year': res['M4_by_year']}))
    for r in rows:
        out('   ' + jd(r))

    # ---- M4 · full pulls (money sealed; counts + dates public)
    out('\n## M4 · DICE full pulls of every event with orders (money sealed, counts public)')
    pulls, money = [], {}
    ORD = ('query O($e:ID!,$a:String){ viewer { orders(first:100, after:$a, where:{eventId:{eq:$e}}){ totalCount '
           'pageInfo{ endCursor hasNextPage } edges{ node{ purchasedAt quantity '
           'tickets{ fullPrice diceCommission total } } } } } }')
    for r in rows:
        if not r['orders']:
            continue
        if elapsed() > DICE_BUDGET_S:
            pulls.append({'dice_id': r['dice_id'], 'skipped': 'time budget'})
            continue
        t0, after, pages, n_orders, n_tix, qty = time.time(), None, 0, 0, 0, 0
        fp = dc = tt = 0
        pmin = pmax = None
        err = None
        while True:
            st, d, e, *_ = dq(ORD, {'e': rid(r['dice_id']), 'a': after})
            if e or not d:
                err = e
                break
            c = d['viewer']['orders']
            pages += 1
            for x in c.get('edges') or []:
                o = x['node']
                n_orders += 1
                qty += o.get('quantity') or 0
                p = str(o.get('purchasedAt') or '')[:10]
                if p:
                    pmin = p if pmin is None or p < pmin else pmin
                    pmax = p if pmax is None or p > pmax else pmax
                for t in o.get('tickets') or []:
                    n_tix += 1
                    fp += t.get('fullPrice') or 0
                    dc += t.get('diceCommission') or 0
                    tt += t.get('total') or 0
            if not c['pageInfo']['hasNextPage']:
                break
            after = c['pageInfo']['endCursor']
        rec = {'dice_id': r['dice_id'], 'pages': pages, 'seconds': round(time.time() - t0, 1), 'error': err,
               'orders': n_orders, 'orders_totalCount': r['orders'], 'tickets_listed': n_tix,
               'tickets_totalCount': r['tickets'], 'quantity_sum': qty, 'returns_totalCount': r['returns'],
               'purchased_first': pmin, 'purchased_last': pmax}
        pulls.append(rec)
        money[str(r['dice_id'])] = {'fullPrice': fp, 'diceCommission': dc, 'total': tt, 'tickets': n_tix}
        out('   ' + jd(rec))
    res['M4_pulls'] = pulls
    PRIVATE['dice_money_by_event'] = money

    # ---- M6 · fill rates on two events: Order / Ticket scalar fields that look like marketing
    out('\n## M6 · DICE fill rates on two events (non-personal scalars; Fan.optInPartners ALONE, X4)')
    order_f = dtype('Order') or {}
    ticket_f = dtype('Ticket') or {}

    def pick(fields):
        return sorted(k for k, (tn, kind, _) in fields.items()
                      if kind in ('SCALAR', 'ENUM') and MARKET_RX.search(k) and not PERSONAL_RX.search(k))

    def pick_personal_scalar(fields):
        # personal-but-coarse scalars (IP city/country): fetched for a FILL COUNT only, never printed
        return sorted(k for k, (tn, kind, _) in fields.items()
                      if kind in ('SCALAR', 'ENUM') and re.fullmatch(r'(?i)ip(City|Country)', k))
    of = sorted(set(pick(order_f)) | set(pick_personal_scalar(order_f)))
    tf_ = pick(ticket_f)
    res['M6_fields_selected'] = {'Order': of, 'Ticket': tf_,
                                 'personal_fill_count_only': pick_personal_scalar(order_f)}
    res['M6_fields_never_selected'] = {'Order': sorted(k for k in order_f if PERSONAL_RX.search(k)),
                                       'Ticket': sorted(k for k in ticket_f if PERSONAL_RX.search(k)),
                                       'Fan': sorted(tf.get('Fan', {}))}
    out(jd({'selected': res['M6_fields_selected'], 'never_selected': res['M6_fields_never_selected']}))
    fan_ok = 'fan' in order_f and 'optInPartners' in (tf.get('Fan') or {})
    fills = {}
    for eid in (600413, 526535):
        sel_o = ' '.join(of)
        sel_t = (' tickets{ %s }' % ' '.join(tf_)) if tf_ else ''
        q = ('query F($e:ID!,$a:String){ viewer { orders(first:100, after:$a, where:{eventId:{eq:$e}}){ '
             'pageInfo{ endCursor hasNextPage } edges{ node{ id %s%s } } } } }') % (sel_o, sel_t)
        after, cnt_o, cnt_t, fo, ft, distinct, err = None, 0, 0, collections.Counter(), collections.Counter(), {}, None
        for _ in range(300):
            st, d, e, *_ = dq(q, {'e': rid(eid), 'a': after})
            if e or not d:
                err = e
                break
            c = d['viewer']['orders']
            for x in c.get('edges') or []:
                o = x['node']
                cnt_o += 1
                for k in of:
                    if filled(o.get(k)):
                        fo[k] += 1
                        if not re.fullmatch(r'(?i)ip(City|Country)', k):
                            distinct.setdefault(k, set()).add(str(o.get(k))[:100])
                for t in o.get('tickets') or []:
                    cnt_t += 1
                    for k in tf_:
                        if filled(t.get(k)):
                            ft[k] += 1
            if not c['pageInfo']['hasNextPage']:
                break
            after = c['pageInfo']['endCursor']
        opt = None
        if fan_ok:
            qf = ('query G($e:ID!,$a:String){ viewer { orders(first:100, after:$a, where:{eventId:{eq:$e}}){ '
                  'pageInfo{ endCursor hasNextPage } edges{ node{ fan { optInPartners } } } } } }')
            after, opt = None, collections.Counter()
            for _ in range(300):
                st, d, e, *_ = dq(qf, {'e': rid(eid), 'a': after})
                if e or not d:
                    opt['error'] = 1
                    break
                c = d['viewer']['orders']
                for x in c.get('edges') or []:
                    f = (x['node'] or {}).get('fan')
                    opt['no_fan' if not f else str(f.get('optInPartners'))] += 1
                if not c['pageInfo']['hasNextPage']:
                    break
                after = c['pageInfo']['endCursor']
            opt = dict(opt)
        fills[eid] = {'orders': cnt_o, 'tickets': cnt_t, 'order_filled': dict(fo), 'ticket_filled': dict(ft),
                      'order_distinct_value_counts': {k: len(v) for k, v in distinct.items()},
                      'fan_optInPartners': opt, 'error': err}
        out(f'   {eid}: ' + jd(fills[eid]))
    res['M6_fill'] = fills
    return res


# =================================================================== main
def main(which, acct=None):
    started = datetime.now(timezone.utc)
    part = f'{which}_{acct}' if acct else which
    result = {'probe': 'XR3', 'part': part, 'started_utc': started.strftime('%Y-%m-%dT%H:%MZ'), 'pace_s': PACE}
    out(f'# XR3 probe · {part} · {result["started_utc"]} · pace {PACE}s')
    out('secrets set (names): ' + jd(sorted(k for k, v in ENV.items() if v)))
    try:
        if which == 'shotgun':
            result.update(shotgun(acct))
        elif which == 'dice':
            result.update(dice())
    except Exception as e:  # keep what was measured
        import traceback
        result['fatal'] = scrub(f'{type(e).__name__}: {e}')[:300]
        out('FATAL ' + result['fatal'])
        out(scrub(traceback.format_exc())[-1500:])
    result['http_status_counts'] = dict(HTTP_STATS)
    result['response_header_names'] = HEADER_NAMES
    result['rate_limit_headers_numeric'] = RATE_HEADERS
    result['wall_seconds'] = round((datetime.now(timezone.utc) - started).total_seconds())
    out('http: ' + jd(result['http_status_counts']) + ' · rate-limit headers: ' + jd(RATE_HEADERS))
    out(f'wall: {result["wall_seconds"]}s')
    if PRIVATE:
        PRIV.mkdir(parents=True, exist_ok=True)
        (PRIV / f'xr3_{part}_private.json').write_text(json.dumps(PRIVATE, ensure_ascii=False, default=str),
                                                        encoding='utf-8')
        out(f'private: {len(PRIVATE)} key(s) written for sealing (values not printed)')
    (OUT / f'xr3_{part}.json').write_text(scrub(json.dumps(result, indent=1, ensure_ascii=False, default=str)),
                                          encoding='utf-8')
    (OUT / f'xr3_{part}.log').write_text('\n'.join(LOG) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
