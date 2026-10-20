#!/usr/bin/env python3
"""
XR2 measurement probe -- read-only, Festiflow guide round XR2 (2026-10-20).

    python guide/xr2/probe_xr2.py shotgun   # M1 M3 M4 M5 M6 (Shotgun) + M7 tokens + public docs
    python guide/xr2/probe_xr2.py dice      # M2 M3 M4 M5 M6 (DICE)

WHAT IT MAY DO
  GET on api.shotgun.live, POST *queries* (never a mutation) on the DICE partners
  GraphQL endpoint. Nothing else, nowhere else (one unauthenticated GET on the
  public Shotgun developer site).

WHAT IT MAY PRINT
  Field NAMES, COUNTS, sums of money in cents, event ids, event dates, event
  names (public marketing names, never a person's), HTTP status codes and the
  names of response headers. NEVER a token, a header value carrying a credential,
  a URL (a Shotgun URL with its query string IS a credential), or any personal
  value. Every string that leaves this process goes through scrub(), which also
  removes each secret's literal value, any `token=`, `Bearer `, JWT, e-mail
  address or long opaque run. The workflow then greps the output for the same
  things and refuses to commit if anything matches.

Stdlib only. Writes only under guide/xr2/out/.
"""

import base64
import collections
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

OUT = Path(__file__).resolve().parent / 'out'
OUT.mkdir(parents=True, exist_ok=True)

SG = 'https://api.shotgun.live'
DICE = 'https://partners-endpoint.dice.fm/graphql'
PACE = float(os.environ.get('XR2_PACE_S') or 0.8)       # the standalone's value
TIMEOUT = 60

ENV = {k: os.environ.get(k, '').strip() for k in (
    'SHOTGUN_TOKEN_EPISODE', 'SHOTGUN_TOKEN_SONORA', 'SHOTGUN_ORGANIZER_ID_SONORA', 'DICE_TOKEN')}
SECRETS = sorted({v for v in ENV.values() if v and len(v) >= 6}, key=len, reverse=True)

ACCOUNTS = [
    ('episode', ENV['SHOTGUN_TOKEN_EPISODE'], '171835'),
    ('sonora', ENV['SHOTGUN_TOKEN_SONORA'], ENV['SHOTGUN_ORGANIZER_ID_SONORA'] or '207784'),
]

# Festiflow's events (fixtures/seed.json + corpus ids). evt-sh has no id anywhere;
# 565846 (the standalone's bordeaux_oct_2026, Sonora) is pulled as its candidate.
SG_EVENTS = [
    ('evt-px', 494642), ('evt-sb', 505434), ('evt-cc', 549064), ('evt-ep', 535882),
    ('evt-si', 544355), ('evt-gv', 546274), ('evt-rn', 557151), ('evt-croisiere', 553118),
    ('evt-sh?', 565846),
]
DICE_EVENTS = [
    ('evt-px', 526535), ('evt-sb', 540197), ('evt-ep', 573271), ('evt-rn', 600413),
    ('evt-cc', 591517), ('evt-gv', 588085),
]
KNOWN_SG_IDS = {i for _, i in SG_EVENTS} | {399931, 406642, 408231, 433590, 444613, 455482, 313304}
KNOWN_DICE_IDS = {i for _, i in DICE_EVENTS} | {345933, 395695, 462095}


# ---------------------------------------------------------------- scrubbing
_PATTERNS = [
    (re.compile(r'(?i)token=[^&\s"\']+'), 'token=***'),
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


def out(*parts):
    line = scrub(' '.join(str(p) for p in parts))
    LOG.append(line)
    print(line, flush=True)


# ---------------------------------------------------------------- http
HTTP_STATS = collections.Counter()
RATE_HEADERS = {}          # header name -> last numeric value (rate-limit family only)
HEADER_NAMES = {}          # host -> sorted header names of the first response


def _note_headers(host, headers):
    names = sorted({k.lower() for k in headers.keys()})
    HEADER_NAMES.setdefault(host, names)
    for k in names:
        if re.search(r'rate|retry|limit|quota', k):
            v = str(headers.get(k, '')).strip()
            if re.fullmatch(r'[0-9.]{1,12}', v):
                RATE_HEADERS[k] = v


def request(url, method='GET', body=None, headers=None, host='shotgun'):
    """-> (status, json_or_None, error_text_scrubbed, seconds). Never raises, never logs the url."""
    data = json.dumps(body).encode() if body is not None else None
    h = {'Accept': 'application/json'}
    if body is not None:
        h['Content-Type'] = 'application/json'
    h.update(headers or {})
    rl = 0
    tries = 0
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
                detail = e.read().decode('utf-8', 'replace')[:400]
            except Exception:
                pass
            if e.code == 429 and rl < 6:
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
        except Exception as e:  # network
            HTTP_STATS[f'{host}:neterr'] += 1
            if tries < 4:
                time.sleep(2 ** tries)
                continue
            return None, None, scrub(type(e).__name__), time.time() - t0, 0


def sg_url(path, **params):
    return f'{SG}{path}?' + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})


def shape(v):
    """A value's FORMAT, never the value: digits -> 9, letters -> a."""
    if v is None:
        return 'null'
    s = str(v)
    return re.sub(r'[A-Za-z]', 'a', re.sub(r'\d', '9', s))[:40]


def keys_of(obj):
    return sorted(obj.keys()) if isinstance(obj, dict) else type(obj).__name__


def list_in(payload):
    if isinstance(payload, list):
        return None, payload
    if isinstance(payload, dict):
        for k, v in payload.items():
            if isinstance(v, list) and (not v or isinstance(v[0], dict)):
                return k, v
    return None, None


# =================================================================== M7 tokens
def token_shape(name, tok):
    r = {'name': name, 'set': bool(tok)}
    if not tok:
        return r
    r['length'] = len(tok)
    r['segments_on_dot'] = tok.count('.') + 1
    r['has_colon'] = ':' in tok
    r['has_whitespace'] = bool(re.search(r'\s', tok))
    r['charset'] = ''.join(sorted({('A' if c.isupper() else 'a' if c.islower() else '9' if c.isdigit() else c)
                                   for c in tok}))
    parts = tok.split('.')
    if len(parts) == 3:
        def dec(p):
            p += '=' * (-len(p) % 4)
            return json.loads(base64.urlsafe_b64decode(p.encode()).decode())
        try:
            hdr = dec(parts[0])
            r['jwt_header'] = {k: (v if k in ('alg', 'typ') else type(v).__name__) for k, v in hdr.items()}
        except Exception:
            r['jwt_header'] = 'undecodable'
        try:
            pl = dec(parts[1])
            claims = {}
            for k, v in pl.items():
                if k in ('exp', 'iat', 'nbf', 'auth_time') and isinstance(v, (int, float)):
                    claims[k] = datetime.fromtimestamp(v, timezone.utc).strftime('%Y-%m-%d')
                elif re.search(r'scope|role|perm|type|aud|iss', k, re.I) and isinstance(v, (str, list)):
                    vals = v if isinstance(v, list) else [v]
                    ok = all(isinstance(x, str) and re.fullmatch(r'[A-Za-z_:\- ,]{1,40}', x) for x in vals)
                    claims[k] = (vals if ok else f'<{type(v).__name__}, not printed>')
                else:
                    claims[k] = f'<{type(v).__name__}>'
            r['jwt_claims'] = claims
            flat = json.dumps(pl)
            r['a_claim_equals_episode_org'] = '171835' in flat
            sono = ENV['SHOTGUN_ORGANIZER_ID_SONORA'] or '207784'
            r['a_claim_equals_sonora_org'] = sono in flat
        except Exception:
            r['jwt_claims'] = 'undecodable'
    return r


def m7():
    out('\n## M7 · token shapes (no value printed)')
    res = [token_shape(k, ENV[k]) for k in ('SHOTGUN_TOKEN_EPISODE', 'SHOTGUN_TOKEN_SONORA', 'DICE_TOKEN')]
    for r in res:
        out(json.dumps(r, sort_keys=True))
    so = ENV['SHOTGUN_ORGANIZER_ID_SONORA']
    org = {'SHOTGUN_ORGANIZER_ID_SONORA_set': bool(so),
           'equals_code_default_207784': so == '207784',
           'numeric': so.isdigit() if so else None,
           'fits_festiflow_LOGIN_RX': bool(re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,99}', so)) if so else None,
           'episode_token_differs_from_sonora': ENV['SHOTGUN_TOKEN_EPISODE'] != ENV['SHOTGUN_TOKEN_SONORA']}
    out(json.dumps(org, sort_keys=True))
    return {'tokens': res, 'organizer': org}


# =================================================================== docs
def docs():
    out('\n## Public Shotgun developer pages (no credential)')
    res = []
    for u in ('https://developers.shotgun.live/', 'https://developers.shotgun.live/docs',
              'https://developers.shotgun.live/reference', 'https://api.shotgun.live/'):
        label = u.replace('https://', '')
        try:
            req = urllib.request.Request(u, headers={'Accept': 'text/html,application/json'})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read(2_000_000).decode('utf-8', 'replace')
                st = r.status
        except urllib.error.HTTPError as e:
            st, body = e.code, ''
        except Exception as e:
            st, body = type(e).__name__, ''
        paths = sorted(set(re.findall(r'(?<![\w.])/(?:v\d/)?(?:tickets|events|orders|deals|organizers|webhooks?|attendees|products)[\w/{}:.-]*', body)))[:60]
        heads = [re.sub(r'<[^>]+>', '', h).strip()[:80] for h in re.findall(r'<h[1-3][^>]*>(.*?)</h[1-3]>', body, re.S)][:40]
        title = (re.search(r'<title[^>]*>(.*?)</title>', body, re.S) or [None, ''])[1].strip()[:100]
        words = {w: bool(re.search(w, body, re.I)) for w in ('webhook', 'rate limit', 'updated_after', 'updated_since', 'since', 'include_cohosted_events', 'organizer_id', '/events', '/tickets')}
        r_ = {'page': label, 'status': st, 'bytes': len(body), 'title': scrub(title), 'paths': [scrub(p) for p in paths],
              'headings': [scrub(h) for h in heads], 'mentions': words}
        res.append(r_)
        out(json.dumps(r_, ensure_ascii=False))
        time.sleep(0.5)
    return res


# =================================================================== M1
def m1():
    out('\n## M1 · Shotgun: can a token list its own events?')
    res = []
    variants = [
        ('org+cohost', lambda tok, org: dict(token=tok, organizer_id=org, include_cohosted_events='1')),
        ('org', lambda tok, org: dict(token=tok, organizer_id=org)),
        ('cohost,no-org', lambda tok, org: dict(token=tok, include_cohosted_events='1')),
    ]
    for acct, tok, org in ACCOUNTS:
        if not tok:
            out(f'  {acct}: token not set - SKIPPED'); continue
        for vname, mk in variants:
            rec = {'account': acct, 'path': '/events', 'variant': vname}
            st, js, err, sec, nb = request(sg_url('/events', **mk(tok, org)))
            rec.update(status=st, seconds=round(sec, 2), bytes=nb)
            if err:
                rec['error_body'] = err
            if st == 200 and js is not None:
                rec['top_keys'] = keys_of(js)
                lk, items = list_in(js)
                rec['list_key'] = lk
                pages, allitems, url = 1, list(items or []), None
                pag = js.get('pagination') if isinstance(js, dict) else None
                rec['pagination_keys'] = keys_of(pag) if pag is not None else None
                url = (pag or {}).get('next') if isinstance(pag, dict) else None
                seen = set()
                while url and pages < 60 and url not in seen:
                    seen.add(url)
                    time.sleep(PACE)
                    st2, js2, err2, _, _ = request(url)
                    if st2 != 200 or js2 is None:
                        rec['page_error'] = f'page {pages + 1}: {st2} {err2 or ""}'
                        break
                    pages += 1
                    allitems += list(list_in(js2)[1] or [])
                    url = ((js2.get('pagination') or {}) if isinstance(js2, dict) else {}).get('next')
                rec['pages'] = pages
                rec['finished'] = not url
                rec['count'] = len(allitems)
                fields = collections.Counter(k for it in allitems if isinstance(it, dict) for k in it)
                rec['item_fields'] = sorted(fields)
                for k in ('total', 'total_count', 'totalCount', 'count'):
                    if isinstance(js, dict) and k in js:
                        rec[f'top_{k}'] = js[k]
                idk = next((k for k in ('id', 'event_id', 'eventId') if k in fields), None)
                dk = next((k for k in ('start_time', 'event_start_time', 'starts_at', 'start_date', 'startTime', 'date', 'start') if k in fields), None)
                nk = next((k for k in ('name', 'event_name', 'title') if k in fields), None)
                rec['id_field'], rec['date_field'], rec['name_field'] = idk, dk, nk
                ids = set()
                rows = []
                for it in allitems:
                    if not isinstance(it, dict):
                        continue
                    i = it.get(idk) if idk else None
                    try:
                        i = int(i)
                    except Exception:
                        pass
                    ids.add(i)
                    d = str(it.get(dk) or '')[:10] if dk else ''
                    if d >= '2026-01-01' or i in KNOWN_SG_IDS:
                        rows.append({'id': i, 'start': d, 'name': scrub(str(it.get(nk) or ''))[:80]})
                rec['known_ids_present'] = sorted(x for x in KNOWN_SG_IDS if x in ids)
                rec['known_ids_absent'] = sorted(x for x in KNOWN_SG_IDS if x not in ids)
                rec['events_2026_or_known'] = sorted(rows, key=lambda r: r['start'])
                years = collections.Counter(str(it.get(dk) or '')[:4] for it in allitems if isinstance(it, dict)) if dk else {}
                rec['by_start_year'] = dict(sorted(years.items()))
            res.append(rec)
            out(json.dumps(rec, ensure_ascii=False, default=str))
            time.sleep(PACE)
        # siblings the docs name, with credentials, once each
        for path in ('/orders', '/deals', '/events/505434', '/organizers', '/'):
            st, js, err, sec, nb = request(sg_url(path, token=tok, organizer_id=org, include_cohosted_events='1'))
            rec = {'account': acct, 'path': path, 'status': st, 'bytes': nb,
                   'top_keys': keys_of(js) if js is not None else None, 'error_body': err}
            lk, items = list_in(js) if js is not None else (None, None)
            if items is not None:
                rec['list_key'], rec['count_page1'] = lk, len(items)
                rec['item_fields'] = sorted({k for it in items if isinstance(it, dict) for k in it})
            elif isinstance(js, dict):
                rec['fields'] = sorted(js)
            res.append(rec)
            out(json.dumps(rec, ensure_ascii=False, default=str))
            time.sleep(PACE)
    return res


# =================================================================== M3/M5/M6 Shotgun
def parse_naive(s):
    if not s:
        return None
    t = re.sub(r'([+-]\d{2}:?\d{2}|Z)$', '', str(s).strip()).replace('T', ' ')
    for f in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(t, f)
        except ValueError:
            pass
    return None


def sg_pull(acct, tok, org, eid, after=None, max_pages=2000, keep_ids=True):
    params = dict(token=tok, organizer_id=org, event_id=eid, include_cohosted_events='1')
    if after:
        params['after'] = after
    url = sg_url('/tickets', **params)
    t0 = time.time()
    pages = n = 0
    seen = set()
    tickets = []
    errors = None
    first_shapes = None
    while url:
        if url in seen:
            errors = 'pagination loop'
            break
        seen.add(url)
        st, js, err, sec, nb = request(url)
        if st != 200 or js is None:
            errors = f'HTTP {st} {err or ""}'
            break
        pages += 1
        lk, items = list_in(js)
        items = items or []
        if first_shapes is None and isinstance(js, dict):
            first_shapes = {'envelope_keys': keys_of(js), 'list_key': lk,
                            'pagination_keys': keys_of(js.get('pagination')) if isinstance(js.get('pagination'), dict) else None}
        tickets.extend(items)
        url = ((js.get('pagination') or {}) if isinstance(js, dict) else {}).get('next')
        if pages >= max_pages:
            errors = f'stopped at the {max_pages}-page cap (PARTIAL)'
            break
        if not items:
            break
        if url:
            time.sleep(PACE)
    return tickets, pages, time.time() - t0, errors, first_shapes


def summarize_tickets(tickets, eid):
    s = {}
    s['raw'] = len(tickets)
    st = collections.Counter((str(t.get('ticket_status')), str(t.get('deal_channel'))) for t in tickets)
    s['status_x_channel'] = {f'{a}|{b}': c for (a, b), c in sorted(st.items(), key=lambda kv: -kv[1])}
    s['status'] = dict(collections.Counter(str(t.get('ticket_status')) for t in tickets).most_common())
    s['valid'] = s['status'].get('valid', 0)
    s['event_id_mismatch'] = sum(1 for t in tickets if str(t.get('event_id')) != str(eid))
    s['currency'] = dict(collections.Counter(str(t.get('currency')) for t in tickets))
    s['deal_vat_rate'] = dict(collections.Counter(str(t.get('deal_vat_rate')) for t in tickets))
    s['payment_method'] = dict(collections.Counter(str(t.get('payment_method')) for t in tickets).most_common(8))
    keys = collections.Counter(k for t in tickets for k in t)
    s['key_count'] = len(keys)
    s['keys_union'] = sorted(keys)
    s['keys_not_on_every_row'] = sorted(k for k, c in keys.items() if c != len(tickets))
    nul = {k: sum(1 for t in tickets if t.get(k) is None) for k in keys}
    s['keys_always_null'] = sorted(k for k, c in nul.items() if c == len(tickets) and tickets)
    sizes = [len(json.dumps(t, separators=(',', ':'), ensure_ascii=False).encode()) for t in tickets]
    s['raw_row_bytes_avg'] = round(sum(sizes) / len(sizes)) if sizes else 0
    s['raw_row_bytes_max'] = max(sizes) if sizes else 0
    pii = ('contact_email', 'contact_first_name', 'contact_last_name', 'contact_phone', 'contact_id', 'contact_gender',
           'contact_birthday', 'contact_postal_code', 'contact_locality', 'contact_company_name', 'user_id',
           'contact_country', 'contact_newsletter_optin', 'ticket_scan_code', 'order_id')
    nopii = [{k: v for k, v in t.items() if k not in pii} for t in tickets]
    sz2 = [len(json.dumps(t, separators=(',', ':'), ensure_ascii=False).encode()) for t in nopii]
    s['row_bytes_without_pii_avg'] = round(sum(sz2) / len(sz2)) if sz2 else 0
    # money, cents, by status
    money = {}
    for t in tickets:
        k = str(t.get('ticket_status'))
        m = money.setdefault(k, {'deal_price': 0, 'deal_service_fee': 0, 'deal_user_service_fee': 0, 'deal_producer_cost': 0, 'n': 0})
        m['n'] += 1
        for f in ('deal_price', 'deal_service_fee', 'deal_user_service_fee', 'deal_producer_cost'):
            v = t.get(f)
            if isinstance(v, (int, float)):
                m[f] += v
    s['money_cents_by_status'] = money
    s['producer_cost_nonzero_rows'] = sum(1 for t in tickets if t.get('deal_producer_cost') not in (0, None))
    # formats, never values
    s['formats'] = {f: dict(collections.Counter(shape(t.get(f)) for t in tickets).most_common(3))
                    for f in ('ordered_at', 'ticket_updated_at', 'ticket_canceled_at', 'event_start_time')}
    # zone of ordered_at: ticket_updated_at (Z, UTC) minus ordered_at, on valid rows never modified
    diffs = collections.Counter()
    for t in tickets:
        if t.get('ticket_status') != 'valid':
            continue
        o, u = parse_naive(t.get('ordered_at')), parse_naive(t.get('ticket_updated_at'))
        if o and u:
            m = (u - o).total_seconds() / 60.0
            diffs['%+.0fh' % round(m / 60.0)] += 1
    s['updated_minus_ordered_hours'] = dict(diffs.most_common(6))
    s['canceled_at_set_by_status'] = dict(collections.Counter(str(t.get('ticket_status')) for t in tickets if t.get('ticket_canceled_at')))
    s['deal_visibilities_orders'] = len({json.dumps(t.get('deal_visibilities')) for t in tickets})
    s['utm_source_distinct'] = len({str(t.get('utm_source')) for t in tickets})
    upd = [str(t.get('ticket_updated_at') or '') for t in tickets if t.get('ticket_updated_at')]
    s['ticket_updated_at_max_date'] = max(upd)[:10] if upd else None
    od = [parse_naive(t.get('ordered_at')) for t in tickets]
    od = [x for x in od if x]
    s['ordered_at_max_date'] = max(od).strftime('%Y-%m-%d') if od else None
    first = tickets[0] if tickets else {}
    s['event_start_date'] = str(first.get('event_start_time') or '')[:10] or None
    s['event_name'] = scrub(str(first.get('event_name') or ''))[:80] or None
    return s


def m3_shotgun():
    out('\n## M3/M5/M6 · Shotgun coverage: every Festiflow event x both tokens, full pull, all statuses')
    res = []
    idsets = {}
    for fid, eid in SG_EVENTS:
        for acct, tok, org in ACCOUNTS:
            if not tok:
                continue
            tickets, pages, sec, err, envelope = sg_pull(acct, tok, org, eid)
            rec = {'festiflow': fid, 'shotgun_id': eid, 'account': acct, 'pages': pages,
                   'seconds': round(sec, 1), 'error': err, 'envelope': envelope}
            rec.update(summarize_tickets(tickets, eid))
            idsets[(eid, acct)] = {t.get('ticket_id') for t in tickets}
            res.append(rec)
            out(json.dumps({k: rec[k] for k in ('festiflow', 'shotgun_id', 'account', 'pages', 'seconds', 'error',
                                                 'raw', 'valid', 'status', 'currency', 'raw_row_bytes_avg',
                                                 'updated_minus_ordered_hours', 'event_start_date', 'event_name')},
                            ensure_ascii=False))
            time.sleep(PACE)
    overlap = []
    for fid, eid in SG_EVENTS:
        a, b = idsets.get((eid, 'episode'), set()), idsets.get((eid, 'sonora'), set())
        overlap.append({'festiflow': fid, 'shotgun_id': eid, 'episode': len(a), 'sonora': len(b),
                        'same_ticket_ids': len(a & b), 'only_episode': len(a - b), 'only_sonora': len(b - a)})
    out('overlap by ticket_id: ' + json.dumps(overlap))
    return res, overlap


# =================================================================== M4 Shotgun
def m4_shotgun():
    out('\n## M4 · Shotgun incremental: `after` from a cursor 7 days back')
    res = []
    now = datetime.now(timezone.utc)
    acct_of = {557151: 'episode', 535882: 'episode', 544355: 'sonora', 565846: 'sonora', 546274: 'episode'}
    for eid in (557151, 565846, 544355, 535882, 546274):
        acct, tok, org = next(a for a in ACCOUNTS if a[0] == acct_of[eid])
        for days in (7, 1):
            cut = now - timedelta(days=days)
            cursor = cut.strftime('%Y-%m-%dT%H:%M:%S.000Z') + '_0'
            tickets, pages, sec, err, _ = sg_pull(acct, tok, org, eid, after=cursor)
            cut_naive = cut.replace(tzinfo=None)
            is_old = [(parse_naive(t.get('ordered_at')) or cut_naive) < cut_naive - timedelta(hours=3) for t in tickets]
            older = [t for t, o in zip(tickets, is_old) if o]
            newer = [t for t, o in zip(tickets, is_old) if not o]
            upd_before = sum(1 for t in tickets if (parse_naive(t.get('ticket_updated_at')) or cut_naive) < cut_naive)
            rec = {'shotgun_id': eid, 'account': acct, 'window_days': days, 'pages': pages, 'seconds': round(sec, 1),
                   'error': err, 'rows': len(tickets),
                   'rows_ordered_before_window(modifications)': len(older),
                   'modifications_by_status': dict(collections.Counter(str(t.get('ticket_status')) for t in older)),
                   'rows_ordered_in_window(new sales)': len(newer),
                   'new_by_status': dict(collections.Counter(str(t.get('ticket_status')) for t in newer)),
                   'rows_with_updated_at_before_cursor(should be 0)': upd_before}
            res.append(rec)
            out(json.dumps(rec))
            time.sleep(PACE)
    # a cursor at "now" must return nothing
    acct, tok, org = ACCOUNTS[0]
    tickets, pages, sec, err, _ = sg_pull(acct, tok, org, 557151, after=now.strftime('%Y-%m-%dT%H:%M:%S.000Z') + '_0')
    rec = {'shotgun_id': 557151, 'account': acct, 'cursor': 'now', 'rows': len(tickets), 'pages': pages,
           'seconds': round(sec, 1), 'error': err}
    res.append(rec)
    out(json.dumps(rec))
    return res


# =================================================================== DICE
def dq(query, variables=None):
    st, js, err, sec, nb = request(DICE, method='POST', body={'query': query, 'variables': variables or {}},
                                   headers={'Authorization': 'Bearer ' + ENV['DICE_TOKEN']}, host='dice')
    errs = None
    if js and js.get('errors'):
        errs = [scrub(e.get('message', ''))[:200] for e in js['errors']]
    return st, (js or {}).get('data') if js else None, errs or err, sec, nb


def unwrap(t):
    chain = []
    while t:
        chain.append(t.get('kind'))
        if t.get('name'):
            return t['name'], chain
        t = t.get('ofType')
    return None, chain


TYPEQ = '''query T($n:String!){ __type(name:$n){ kind fields{ name args{ name type{ name kind ofType{ name kind ofType{ name kind }}}} type{ name kind ofType{ name kind ofType{ name kind }}}} inputFields{ name type{ name kind ofType{ name kind ofType{ name kind }}}} enumValues{ name } } }'''


def dtype(name):
    st, d, err, *_ = dq(TYPEQ, {'n': name})
    return (d or {}).get('__type') if d else None, err


def m2():
    out('\n## M2 · DICE live: Viewer, viewer.events')
    res = {}
    st, d, err, *_ = dq('{ __schema { queryType { name fields { name args { name } } } mutationType { name } } }')
    q = ((d or {}).get('__schema') or {})
    res['query_root_fields'] = {f['name']: [a['name'] for a in f.get('args') or []] for f in ((q.get('queryType') or {}).get('fields') or [])}
    res['mutation_type_present'] = bool(q.get('mutationType'))
    res['schema_error'] = err
    out('query root: ' + json.dumps(res['query_root_fields']) + f' · mutation type present: {res["mutation_type_present"]}')
    vt, err = dtype('Viewer')
    viewer = {}
    inputs = set()
    for f in (vt or {}).get('fields') or []:
        args = {}
        for a in f.get('args') or []:
            n, chain = unwrap(a['type'])
            args[a['name']] = n
            if n and n.endswith('Input'):
                inputs.add(n)
        viewer[f['name']] = {'returns': unwrap(f['type'])[0], 'args': args}
    res['viewer_fields'] = viewer
    out('Viewer fields + args: ' + json.dumps(viewer))
    # the where-inputs, one level and their operator inputs
    where = {}
    todo = sorted(inputs)
    seen = set()
    while todo:
        n = todo.pop(0)
        if n in seen:
            continue
        seen.add(n)
        t, _ = dtype(n)
        fl = {}
        for f in (t or {}).get('inputFields') or []:
            tn = unwrap(f['type'])[0]
            fl[f['name']] = tn
            if tn and tn.endswith('Input') and tn not in seen:
                todo.append(tn)
        if t and t.get('enumValues'):
            fl = [e['name'] for e in t['enumValues']]
        where[n] = fl
        time.sleep(0.1)
    res['input_types'] = where
    out('input types: ' + json.dumps(where))
    st, d, err, *_ = dq('{ viewer { id name } }')
    v = (d or {}).get('viewer') or {}
    nm = str(v.get('name') or '')
    res['viewer_identity'] = {'id_present': bool(v.get('id')), 'name_present': bool(nm), 'name_length': len(nm),
                              'name_mentions': {w: (w in nm.lower()) for w in ('episode', 'sagrega', 'madame', 'loyal', 'sonora', 'ggs')},
                              'error': err}
    out('viewer identity (booleans only): ' + json.dumps(res['viewer_identity']))
    et, _ = dtype('Event')
    res['event_fields'] = sorted(f['name'] for f in (et or {}).get('fields') or [])
    est, _ = dtype('EventState')
    res['event_state_values'] = [e['name'] for e in (est or {}).get('enumValues') or []]
    # page through viewer.events
    events, after, pages, total, t0, perr = [], None, 0, None, time.time(), None
    while True:
        st, d, err, sec, nb = dq('query E($a:String){ viewer { events(first:100, after:$a){ totalCount pageInfo{ endCursor hasNextPage } edges{ node{ id name startDatetime endDatetime state currency totalTicketAllocationQty } } } } }', {'a': after})
        if err or not d:
            perr = err
            break
        c = d['viewer']['events']
        total = c.get('totalCount')
        pages += 1
        events += [e['node'] for e in c.get('edges') or []]
        if not c['pageInfo']['hasNextPage'] or pages >= 30:
            break
        after = c['pageInfo']['endCursor']
        time.sleep(0.2)

    def num(rid):
        try:
            return int(base64.b64decode(rid).decode().split(':')[-1])
        except Exception:
            return rid
    ids = {num(e['id']) for e in events}
    res['events'] = {'pages': pages, 'returned': len(events), 'totalCount': total, 'error': perr,
                     'seconds': round(time.time() - t0, 1),
                     'by_state': dict(collections.Counter(str(e.get('state')) for e in events)),
                     'by_currency': dict(collections.Counter(str(e.get('currency')) for e in events)),
                     'by_start_year': dict(sorted(collections.Counter(str(e.get('startDatetime') or '')[:4] for e in events).items())),
                     'known_ids_present': sorted(x for x in KNOWN_DICE_IDS if x in ids),
                     'known_ids_absent': sorted(x for x in KNOWN_DICE_IDS if x not in ids),
                     'events_2026': sorted(({'id': num(e['id']), 'start': str(e.get('startDatetime') or '')[:10],
                                             'state': e.get('state'), 'currency': e.get('currency'),
                                             'name': scrub(e.get('name') or '')[:80]}
                                            for e in events if str(e.get('startDatetime') or '') >= '2026'),
                                           key=lambda r: r['start'])}
    out('viewer.events: ' + json.dumps(res['events'], ensure_ascii=False))
    # can the viewer filter events? try a where on events if the arg exists
    if 'where' in viewer.get('events', {}).get('args', {}):
        res['events_where_arg'] = viewer['events']['args']['where']
    # node() on Genève
    if 'node' in res['query_root_fields']:
        st, d, err, *_ = dq('query N($i:ID!){ node(id:$i){ id ... on Event { name } } }', {'i': base64.b64encode(b'Event:588085').decode()})
        res['node_588085'] = {'null': not (d or {}).get('node'), 'error': err}
        out('node(Event:588085): ' + json.dumps(res['node_588085']))
    return res


ORDERS = '''query O($e:ID!,$a:String){ viewer { orders(first:100, after:$a, where:{eventId:{eq:$e}}){ totalCount pageInfo{ endCursor hasNextPage }
  edges{ node{ id purchasedAt quantity salesChannel fullPrice total commission diceCommission
    adjustments{ processedAt reason } returns{ id }
    tickets{ id fullPrice total commission diceCommission fees{ category dice promoter } ticketType{ name } priceTier{ name } } } } } } }'''


def dice_pull(eid):
    rid = base64.b64encode(f'Event:{eid}'.encode()).decode()
    orders, after, pages, total, t0, err = [], None, 0, None, time.time(), None
    nbytes = 0
    while True:
        st, d, e, sec, nb = dq(ORDERS, {'e': rid, 'a': after})
        nbytes += nb
        if e or not d:
            err = e
            break
        c = d['viewer']['orders']
        total = c.get('totalCount') if total is None else total
        pages += 1
        orders += [x['node'] for x in c.get('edges') or []]
        if not c['pageInfo']['hasNextPage']:
            break
        after = c['pageInfo']['endCursor']
        time.sleep(0.2)
    return orders, pages, time.time() - t0, total, err, nbytes, rid


def count_coll(coll, rid, extra=''):
    st, d, err, *_ = dq('query C($e:ID!){ viewer { %s(first:1, where:{eventId:{eq:$e}%s}){ totalCount } } }' % (coll, extra), {'e': rid})
    if err or not d:
        return {'error': err}
    return (d['viewer'][coll] or {}).get('totalCount')


def m3_dice(where_types):
    out('\n## M3/M4/M5/M6 · DICE coverage, every Festiflow DICE id, full orders pull')
    res = []
    now = datetime.now(timezone.utc)
    ops = where_types.get(where_types.get('OrderWhereInput', {}).get('purchasedAt') or '', {})
    op = next((o for o in ('gte', 'gt') if isinstance(ops, dict) and o in ops), None)
    ret_ops = where_types.get(where_types.get('ReturnWhereInput', {}).get('returnedAt') or '', {})
    rop = next((o for o in ('gte', 'gt') if isinstance(ret_ops, dict) and o in ret_ops), None)
    out(f'purchasedAt operator used: {op} · returnedAt operator used: {rop}')
    for fid, eid in DICE_EVENTS:
        orders, pages, sec, total, err, nbytes, rid = dice_pull(eid)
        tickets = [t for o in orders for t in (o.get('tickets') or [])]
        rec = {'festiflow': fid, 'dice_id': eid, 'pages': pages, 'seconds': round(sec, 1), 'error': err,
               'orders': len(orders), 'orders_totalCount': total, 'orders_empty': sum(1 for o in orders if not o.get('tickets')),
               'tickets': len(tickets),
               'orders_with_returns': sum(1 for o in orders if o.get('returns')),
               'orders_with_adjustments': sum(1 for o in orders if o.get('adjustments')),
               'salesChannel': dict(collections.Counter(str(o.get('salesChannel')) for o in orders)),
               'fee_categories': dict(collections.Counter(f.get('category') for t in tickets for f in (t.get('fees') or []))),
               'fees_promoter_nonzero': sum(1 for t in tickets for f in (t.get('fees') or []) if f.get('promoter')),
               'ticket_commission_nonzero': sum(1 for t in tickets if t.get('commission')),
               'fee_identity_ok_tickets': sum(1 for t in tickets if (t.get('fullPrice') or 0) + (t.get('diceCommission') or 0) == (t.get('total') or 0)),
               'money_cents': {'fullPrice': sum(t.get('fullPrice') or 0 for t in tickets),
                               'diceCommission': sum(t.get('diceCommission') or 0 for t in tickets),
                               'total': sum(t.get('total') or 0 for t in tickets)},
               'zero_price_tickets': sum(1 for t in tickets if not t.get('fullPrice')),
               'purchasedAt_shape': dict(collections.Counter(shape(o.get('purchasedAt')) for o in orders).most_common(2)),
               'response_bytes_total': nbytes,
               'order_node_bytes_avg': round(sum(len(json.dumps(o, separators=(',', ':'))) for o in orders) / len(orders)) if orders else 0,
               'ticket_node_bytes_avg': round(sum(len(json.dumps(t, separators=(',', ':'))) for t in tickets) / len(tickets)) if tickets else 0,
               'returns_totalCount': count_coll('returns', rid), 'ticketTransfers_totalCount': count_coll('ticketTransfers', rid)}
        pa = [o.get('purchasedAt') for o in orders if o.get('purchasedAt')]
        rec['purchasedAt_max_date'] = max(pa)[:10] if pa else None
        if op and orders:
            since = (now - timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ')
            rec['orders_purchased_last_7d_via_filter'] = count_coll('orders', rid, ', purchasedAt:{%s:"%s"}' % (op, since))
            rec['orders_purchased_last_7d_by_scan'] = sum(1 for x in pa if x >= since[:19])
        if rop and orders:
            since = (now - timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ')
            rec['returns_last_7d_via_filter'] = count_coll('returns', rid, ', returnedAt:{%s:"%s"}' % (rop, since))
        # do returned tickets stay in viewer.orders?
        if orders and isinstance(rec['returns_totalCount'], int) and rec['returns_totalCount']:
            rids, after, rp = set(), None, 0
            while rp < 50:
                st, d, e, *_ = dq('query R($e:ID!,$a:String){ viewer { returns(first:100, after:$a, where:{eventId:{eq:$e}}){ pageInfo{ endCursor hasNextPage } edges{ node{ ticketId returnedAt } } } } }', {'e': rid, 'a': after})
                if e or not d:
                    rec['returns_list_error'] = e
                    break
                c = d['viewer']['returns']
                rids |= {str(x['node'].get('ticketId')) for x in c.get('edges') or []}
                rp += 1
                if not c['pageInfo']['hasNextPage']:
                    break
                after = c['pageInfo']['endCursor']
            tid_raw = {str(t.get('id')) for t in tickets}

            def tnum(x):
                try:
                    return base64.b64decode(x).decode().split(':')[-1]
                except Exception:
                    return x
            tid_num = {tnum(x) for x in tid_raw}
            rec['returned_ticket_ids'] = len(rids)
            rec['returned_ids_still_in_orders'] = len({r for r in rids if r in tid_raw or tnum(r) in tid_num or r in tid_num})
            rec['ticketId_shape'] = dict(collections.Counter(shape(r)[:12] for r in list(rids)[:50]).most_common(2))
            rec['ticket_id_shape'] = dict(collections.Counter(shape(t)[:12] for t in list(tid_raw)[:50]).most_common(2))
        res.append(rec)
        out(json.dumps(rec, ensure_ascii=False))
        time.sleep(0.3)
    return res


# =================================================================== run 2 follow-ups
def followup():
    res = {}
    out('\n## Run 2 · Shotgun /events: where does it want its "API key"?')
    tries = []
    for acct, tok, org in ACCOUNTS:
        variants = [
            ('query param key', sg_url('/events', key=tok, organizer_id=org), {}),
            ('query param api_key', sg_url('/events', api_key=tok, organizer_id=org), {}),
            ('header Authorization (bearer scheme)', sg_url('/events', organizer_id=org), {'Authorization': 'Bearer ' + tok}),
            ('header x-api-key', sg_url('/events', organizer_id=org), {'x-api-key': tok}),
            ('query token plus header (bearer scheme)', sg_url('/events', token=tok, organizer_id=org), {'Authorization': 'Bearer ' + tok}),
        ]
        for label, url, hdr in variants:
            st, js, err, sec, nb = request(url, headers=hdr)
            rec = {'account': acct, 'variant': label, 'status': st, 'error_body': err, 'bytes': nb}
            if st == 200 and js is not None:
                lk, items = list_in(js)
                rec['top_keys'] = keys_of(js)
                rec['list_key'] = lk
                rec['count_page1'] = len(items or [])
                rec['item_fields'] = sorted({k for it in (items or []) if isinstance(it, dict) for k in it})
                pag = js.get('pagination') if isinstance(js, dict) else None
                rec['pagination_keys'] = keys_of(pag) if pag is not None else None
            tries.append(rec)
            out(json.dumps(rec, ensure_ascii=False))
            time.sleep(PACE)
    res['events_auth_variants'] = tries

    out('\n## Run 2 · the /tickets envelope: `auth` and `params` (names and types only)')
    acct, tok, org = ACCOUNTS[0]
    st, js, err, *_ = request(sg_url('/tickets', token=tok, organizer_id=org, event_id=557151, include_cohosted_events='1'))
    env = {}
    if isinstance(js, dict):
        for k in ('auth', 'params', 'pagination'):
            v = js.get(k)
            if isinstance(v, dict):
                env[k] = {kk: type(vv).__name__ for kk, vv in v.items()}
            else:
                env[k] = type(v).__name__
        a = js.get('auth') if isinstance(js.get('auth'), dict) else {}
        flat = json.dumps(a)
        env['auth_mentions_episode_org'] = '171835' in flat
        env['auth_scalar_values_safe'] = {kk: vv for kk, vv in a.items()
                                          if isinstance(vv, bool) or (isinstance(vv, str) and re.fullmatch(r'[a-z_:\-]{1,30}', vv))}
    res['tickets_envelope'] = {'status': st, 'error': err, **env}
    out(json.dumps(res['tickets_envelope']))

    if ENV['DICE_TOKEN']:
        out('\n## Run 2 · DICE: mutations (names), events changed lately, Viewer.tickets, the returned ticket still in orders')
        st, d, err, *_ = dq('{ __schema { mutationType { fields { name } } } }')
        mt = (((d or {}).get('__schema') or {}).get('mutationType') or {}).get('fields') or []
        res['dice_mutation_fields'] = sorted(f['name'] for f in mt)
        out('mutation fields: ' + json.dumps(res['dice_mutation_fields']))
        since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%SZ')
        st, d, err, *_ = dq('query($s:Datetime){ viewer { events(first:100, where:{updatedAt:{gte:$s}}){ totalCount } } }', {'s': since})
        res['dice_events_updated_last_30d'] = ((d or {}).get('viewer') or {}).get('events', {}).get('totalCount') if d else err
        out('events updated in the last 30 days: ' + json.dumps(res['dice_events_updated_last_30d']))
        tk = {}
        for eid in (600413, 540197):
            rid = base64.b64encode(f'Event:{eid}'.encode()).decode()
            st, d, err, *_ = dq('query($e:ID!){ viewer { tickets(first:1, where:{eventId:{eq:$e}}){ totalCount } } }', {'e': rid})
            tk[eid] = ((d or {}).get('viewer') or {}).get('tickets', {}).get('totalCount') if d else err
            time.sleep(0.2)
        res['dice_viewer_tickets_totalCount'] = tk
        out('viewer.tickets totalCount: ' + json.dumps(tk))
        # 540197: which returned ticket is still listed in orders, and what is it worth (cents only)
        rid = base64.b64encode(b'Event:540197').decode()
        orders, pages, sec, total, err, nb, _ = dice_pull(540197)
        tix = {}
        for o in orders:
            for t in o.get('tickets') or []:
                tix[str(t.get('id'))] = (o, t)
        rets, after = [], None
        for _ in range(10):
            st, d, e, *_ = dq('query R($e:ID!,$a:String){ viewer { returns(first:100, after:$a, where:{eventId:{eq:$e}}){ pageInfo{ endCursor hasNextPage } edges{ node{ ticketId returnedAt reason } } } } }', {'e': rid, 'a': after})
            if e or not d:
                break
            c = d['viewer']['returns']
            rets += [x['node'] for x in c['edges']]
            if not c['pageInfo']['hasNextPage']:
                break
            after = c['pageInfo']['endCursor']
        still = []
        for r in rets:
            if str(r.get('ticketId')) in tix:
                o, t = tix[str(r['ticketId'])]
                still.append({'fullPrice_cents': t.get('fullPrice'), 'diceCommission_cents': t.get('diceCommission'),
                              'total_cents': t.get('total'), 'returnedAt_date': str(r.get('returnedAt') or '')[:10],
                              'reason': scrub(str(r.get('reason') or ''))[:30],
                              'order_purchasedAt_date': str(o.get('purchasedAt') or '')[:10],
                              'order_ticket_count': len(o.get('tickets') or []), 'order_quantity': o.get('quantity')})
        res['dice_540197_returned_still_listed'] = still
        res['dice_540197_returns_reasons'] = dict(collections.Counter(scrub(str(r.get('reason') or ''))[:30] for r in rets))
        res['dice_540197_orders_quantity_vs_tickets'] = {
            'orders_quantity_sum': sum(o.get('quantity') or 0 for o in orders),
            'tickets_listed': sum(len(o.get('tickets') or []) for o in orders),
            'orders_where_quantity_gt_tickets': sum(1 for o in orders if (o.get('quantity') or 0) > len(o.get('tickets') or []))}
        out('540197 returned-but-listed: ' + json.dumps(still) + ' · reasons ' + json.dumps(res['dice_540197_returns_reasons'])
            + ' · quantity vs tickets ' + json.dumps(res['dice_540197_orders_quantity_vs_tickets']))
    return res


# =================================================================== main
def main(which):
    started = datetime.now(timezone.utc)
    result = {'probe': 'XR2', 'part': which, 'started_utc': started.strftime('%Y-%m-%dT%H:%MZ'), 'pace_s': PACE}
    out(f'# XR2 probe · {which} · {result["started_utc"]} · pace {PACE}s')
    out('secrets set: ' + json.dumps({k: bool(v) for k, v in ENV.items()}))
    if which == 'shotgun':
        result['M7'] = m7()
        result['docs'] = docs()
        result['M1'] = m1()
        result['M4'] = m4_shotgun()
        result['M3'], result['M3_overlap'] = m3_shotgun()
    elif which == 'followup':
        result['RUN2'] = followup()
    elif which == 'dice':
        if not ENV['DICE_TOKEN']:
            out('DICE_TOKEN not set - SKIPPED')
        else:
            result['M2'] = m2()
            result['M3'] = m3_dice(result['M2'].get('input_types', {}))
    result['http_status_counts'] = dict(HTTP_STATS)
    result['response_header_names'] = HEADER_NAMES
    result['rate_limit_headers_numeric'] = RATE_HEADERS
    result['wall_seconds'] = round((datetime.now(timezone.utc) - started).total_seconds())
    out('http: ' + json.dumps(result['http_status_counts']) + ' · rate-limit headers: ' + json.dumps(RATE_HEADERS))
    out('header names: ' + json.dumps(HEADER_NAMES))
    out(f'wall: {result["wall_seconds"]}s')
    (OUT / f'xr2_{which}.json').write_text(scrub(json.dumps(result, indent=1, ensure_ascii=False, default=str)), encoding='utf-8')
    (OUT / f'xr2_{which}.log').write_text('\n'.join(LOG) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else 'shotgun'))
