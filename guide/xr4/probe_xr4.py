#!/usr/bin/env python3
"""
XR4 measurement probe -- read-only, Festiflow guide round XR4 (R2, 2026-10-25).

    python -I guide/xr4/probe_xr4.py dice      # M1 DICE schema in full (with arguments) · M2 personal fill (counts)
    python -I guide/xr4/probe_xr4.py overlap   # M3 one person on Shotgun and DICE (run-keyed hashes, counts only)

WHAT IT MAY DO
  GET on api.shotgun.live; POST GraphQL *queries* (never a mutation) on DICE. Nothing else.
  `Ticket.code` and `Extra.code` (a ticket's barcode) are never selected.

WHAT IT MAY PRINT OR COMMIT (ticketing_api is PUBLIC, so are its Actions logs)
  Field NAMES, TYPES, ARGUMENTS, COUNTS, timings, event ids, HTTP status codes. Schema enum values (public).
  NEVER a token, a header, a URL (a Shotgun URL carries its token), a personal value, a ticket id, a money figure,
  a hash. Personal values are read in this process only, tested (filled? equal?), hashed with a key drawn from
  os.urandom in this process and never written, counted, and dropped. Every printed string passes scrub().

Secrets arrive as environment variables named by the workflow step that uses them. Stdlib only.
"""

import collections
import hashlib
import hmac
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import base64
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'out'
OUT.mkdir(parents=True, exist_ok=True)

SG = os.environ.get('XR4_SG_BASE') or 'https://api.shotgun.live'               # override = local mock tests only
DICE = os.environ.get('XR4_DICE_URL') or 'https://partners-endpoint.dice.fm/graphql'
PACE = float(os.environ.get('XR4_PACE_S') or 0.8)       # the standalone's value, one fetcher per token
DPACE = float(os.environ.get('XR4_DPACE_S') or 0.25)
TIMEOUT = 90
T_START = time.time()

ENV = {k: os.environ.get(k, '').strip() for k in (
    'SHOTGUN_TOKEN_EPISODE', 'SHOTGUN_ORGANIZER_ID_EPISODE', 'DICE_TOKEN')}
SECRETS = sorted({ENV[k] for k in ('SHOTGUN_TOKEN_EPISODE', 'DICE_TOKEN') if ENV[k] and len(ENV[k]) >= 6},
                 key=len, reverse=True)

M2_EVENTS = {600413: 'Rennes 2026', 526535: 'Paris XXL 2026'}
M3_PAIRS = [('Paris XXL 2026', 494642, 526535), ('Bordeaux 2026', 505434, 540197)]
M3_FIDELES = [('Paris XXL 2025', 399931), ('Paris XXL 2025 presale (extra)', 406642)]

# ---------------------------------------------------------------- scrubbing / output
_PATTERNS = [
    (re.compile(r'(?i)(token|key|api_key)=[^&\s"\']+'), r'\1=***'),
    (re.compile(r'(?i)bearer\s+\S+'), 'Bearer ***'),
    (re.compile(r'eyJ[\w-]{5,}\.[\w-]{5,}\.[\w-]*'), '<jwt>'),
    (re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'), '<email>'),
    (re.compile(r'https?://\S+'), '<url>'),
    (re.compile(r'(?<![\w:-])\+?(?:\d[ .]?){9,14}\d(?![\w:-])'), '<digits>'),
    (re.compile(r'(?<![\w-])(?=[A-Za-z_\-]*\d)[A-Za-z0-9_\-]{32,}'), '<opaque>'),
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


def jd(o, indent=None):
    return json.dumps(o, ensure_ascii=False, default=str, indent=indent)


def filled(v):
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip() != ''
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return True


# ---------------------------------------------------------------- http
HTTP_STATS = collections.Counter()
HEADER_NAMES = {}
RATE_HEADERS = {}
CALLS = collections.Counter()


def _note_headers(host, headers):
    names = sorted({k.lower() for k in headers.keys()})
    HEADER_NAMES.setdefault(host, names)
    for k in names:
        if re.search(r'rate|retry|limit|quota|cost|complex', k):
            v = str(headers.get(k, '')).strip()
            if re.fullmatch(r'[0-9.]{1,12}', v):
                RATE_HEADERS[f'{host}:{k}'] = v


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
            raw = b''
            try:
                raw = e.read()
                detail = raw.decode('utf-8', 'replace')[:300]
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
            # a GraphQL 400 still carries a JSON error body: hand it back (scrubbed by the caller)
            js = None
            try:
                js = json.loads(raw.decode('utf-8'))
            except Exception:
                pass
            return e.code, js, scrub(detail), time.time() - t0, 0
        except Exception as e:
            HTTP_STATS[f'{host}:neterr'] += 1
            if tries < 5:
                time.sleep(2 ** tries)
                continue
            return None, None, scrub(type(e).__name__), time.time() - t0, 0


# =================================================================== DICE transport
def dq(query, variables=None):
    """-> (status, data, [scrubbed error dicts], seconds, bytes). A query only, never a mutation."""
    assert not re.match(r'\s*mutation\b', query), 'no mutation, ever'
    CALLS['dice'] += 1
    st, js, err, sec, nb = request(DICE, method='POST', body={'query': query, 'variables': variables or {}},
                                   headers={'Authorization': 'Bearer ' + ENV['DICE_TOKEN']}, host='dice')
    errs = []
    if isinstance(js, dict) and js.get('errors'):
        for e in js['errors']:
            errs.append({'message': scrub(e.get('message', ''))[:240],
                         'path': [p for p in (e.get('path') or []) if not isinstance(p, int)],
                         'code': scrub(str(((e.get('extensions') or {}).get('code')) or ''))[:40]})
    elif err:
        errs.append({'message': scrub(err)[:240], 'path': [], 'code': f'http {st}'})
    time.sleep(DPACE)
    data = js.get('data') if isinstance(js, dict) else None
    return st, data, errs, sec, nb


def rid(eid):
    return base64.b64encode(f'Event:{eid}'.encode()).decode()


TYPE_REF = 'kind name ofType { kind name ofType { kind name ofType { kind name ofType { kind name ofType { kind name ofType { kind name } } } } } }'
INTRO = ('query XR4Intro { __schema { queryType { name } mutationType { name } subscriptionType { name } '
         'types { kind name %s fields(includeDeprecated: true) { name %s isDeprecated '
         'args { name %s type { ' + TYPE_REF + ' } defaultValue } type { ' + TYPE_REF + ' } } '
         'inputFields { name %s type { ' + TYPE_REF + ' } defaultValue } '
         'interfaces { name } enumValues(includeDeprecated: true) { name } possibleTypes { name } } } }')


def intro_query(with_desc):
    d = 'description' if with_desc else ''
    return INTRO % (d, d, d, d)


def tstr(t):
    """GraphQL type ref -> SDL string ([Ticket]!)."""
    if not t:
        return '?'
    k = t.get('kind')
    if k == 'NON_NULL':
        return tstr(t.get('ofType')) + '!'
    if k == 'LIST':
        return '[' + tstr(t.get('ofType')) + ']'
    return t.get('name') or '?'


def tbase(t):
    while t and not t.get('name'):
        t = t.get('ofType')
    return (t or {}).get('name'), (t or {}).get('kind')


def is_list(t):
    while t:
        if t.get('kind') == 'LIST':
            return True
        t = t.get('ofType')
    return False


# ---------------------------------------------------------------- what TK1 stores AS BUILT (Festiflow main 06a19b2)
# read at source: shim/ticketing_clients.js (the queries) · shim/ticketing_mapper.js (the rows) ·
# shim/ticketing_sync.js (events -> ticketing_events.details) · db/schema.sql (dice_orders / dice_tickets / dice_returns)
TK1 = {
    'Viewer.id': 'selected (credential check), not stored', 'Viewer.name': 'selected (credential check), not stored',
    'Viewer.events': 'selected', 'Viewer.orders': 'selected', 'Viewer.returns': 'selected',
    'Event.id': 'STORED (platform_event_id + details.relay_id)', 'Event.name': 'STORED (ticketing_events.name)',
    'Event.startDatetime': 'STORED (starts_at)', 'Event.endDatetime': 'STORED (ends_at)',
    'Event.state': 'STORED (state)', 'Event.currency': 'STORED (details.currency)',
    'Event.totalTicketAllocationQty': 'STORED (details.allocation)',
    'Order.id': 'STORED (order_id)', 'Order.purchasedAt': 'STORED (purchased_at)', 'Order.quantity': 'STORED (quantity)',
    'Order.salesChannel': 'STORED (sales_channel)', 'Order.promoCode': 'STORED (promo_code)',
    'Order.promoName': 'STORED (promo_name)', 'Order.promoType': 'STORED (promo_type)',
    'Order.promoDiscount': 'STORED (promo_discount)', 'Order.ipCountry': 'STORED (ip_country)',
    'Order.fan': 'selected: optInPartners only', 'Order.tickets': 'selected',
    'Fan.optInPartners': 'STORED (dice_orders.optin)',
    'Ticket.id': 'STORED (ticket_id)', 'Ticket.fullPrice': 'STORED (full_price_cents)',
    'Ticket.diceCommission': 'STORED (dice_commission_cents)', 'Ticket.total': 'STORED (total_cents)',
    'Ticket.fees': 'STORED (fees jsonb)', 'Ticket.ticketType': 'STORED (ticket_type, ticket_type_id)',
    'Ticket.priceTier': 'STORED (price_tier name; id in payload)',
    'TicketFee.category': 'STORED (fees jsonb)', 'TicketFee.dice': 'STORED (fees jsonb)',
    'TicketFee.promoter': 'STORED (fees jsonb)',
    'TicketType.id': 'STORED (ticket_type_id)', 'TicketType.name': 'STORED (ticket_type)',
    'PriceTier.id': 'payload only', 'PriceTier.name': 'STORED (price_tier)',
    'Return.id': 'STORED (return_id)', 'Return.ticketId': 'STORED (ticket_id)', 'Return.reason': 'STORED (reason)',
    'Return.returnedAt': 'STORED (returned_at)', 'Return.order': 'STORED (order_id: order { id })',
}

# personal classification (the column « personal or not »)
CREDENTIAL = re.compile(r'(?i)^(code|barcode|qr\w*|secure\w*|token|accessToken|fanSecureToken)$')
PERSONAL_TYPES = {'Fan', 'Address', 'FanSurveyAnswer'}
PERSONAL_FIELD = re.compile(r'(?i)(email|phone|first_?name|last_?name|full_?name|dob|birth|address|holder|'
                            r'^fan$|fanSurvey|survey|^ip(City|Country|Address)?$|ipCity|ipCountry|postcode|postal|zip|'
                            r'gender|optIn)')


def personal_of(tname, fname, base):
    if CREDENTIAL.match(fname):
        return 'CREDENTIAL (never select)'
    if tname in PERSONAL_TYPES:
        return 'yes'
    if base in PERSONAL_TYPES:
        return 'yes (leads to personal)'
    if PERSONAL_FIELD.search(fname):
        return 'yes'
    return 'no'


# =================================================================== M1 · the schema, in full
def m1_schema():
    res = {}
    t0 = time.time()
    st, d, errs, sec, nb = dq(intro_query(True))
    with_desc = True
    if errs or not d:
        res['introspection_with_descriptions_errors'] = errs
        st, d, errs, sec, nb = dq(intro_query(False))
        with_desc = False
    if errs or not d:
        res['introspection_errors'] = errs
        out('M1: introspection FAILED: ' + jd(errs))
        return res, None
    sch = d['__schema']
    types = {t['name']: t for t in sch['types'] if t.get('name')}
    res['introspection'] = {'status': st, 'seconds': round(sec, 2), 'bytes': nb, 'with_descriptions': with_desc,
                            'types_total': len(types),
                            'types_non_introspection': sum(1 for n in types if not n.startswith('__')),
                            'query_root': (sch.get('queryType') or {}).get('name'),
                            'mutation_root': (sch.get('mutationType') or {}).get('name'),
                            'subscription_root': (sch.get('subscriptionType') or {}).get('name')}
    qroot = types.get((sch.get('queryType') or {}).get('name') or 'Query') or {}
    res['query_root_fields'] = [{'field': f['name'], 'type': tstr(f['type']),
                                 'args': [f'{a["name"]}: {tstr(a["type"])}' for a in f.get('args') or []]}
                                for f in qroot.get('fields') or []]
    mroot = types.get((sch.get('mutationType') or {}).get('name') or '') or {}
    res['mutations_NEVER_CALLED'] = [{'field': f['name'], 'type': tstr(f['type']),
                                      'args': [f'{a["name"]}: {tstr(a["type"])}' for a in f.get('args') or []]}
                                     for f in mroot.get('fields') or []]

    # reachable from Viewer: output types through fields; input types through args and input fields
    reach, order, queue = set(), [], ['Viewer']
    while queue:
        n = queue.pop(0)
        if n in reach or n not in types or n.startswith('__'):
            continue
        reach.add(n)
        order.append(n)
        t = types[n]
        for f in (t.get('fields') or []):
            queue.append(tbase(f['type'])[0])
            for a in f.get('args') or []:
                queue.append(tbase(a['type'])[0])
        for f in (t.get('inputFields') or []):
            queue.append(tbase(f['type'])[0])
        for p in (t.get('possibleTypes') or []):
            queue.append(p['name'])
        for i in (t.get('interfaces') or []):
            queue.append(i['name'])
    res['reachable_from_viewer'] = len(reach)
    res['not_reachable_from_viewer'] = sorted(n for n in types if n not in reach and not n.startswith('__')
                                              and types[n]['kind'] not in ('SCALAR',))

    rows, inputs, enums, unions = [], [], {}, {}
    for n in order:
        t = types[n]
        k = t['kind']
        if k in ('OBJECT', 'INTERFACE'):
            for f in t.get('fields') or []:
                base, bkind = tbase(f['type'])
                rows.append({
                    'type': n, 'field': f['name'], 'returns': tstr(f['type']), 'kind': bkind,
                    'args': [f'{a["name"]}: {tstr(a["type"])}' + (f' = {scrub(a["defaultValue"])}' if a.get('defaultValue') else '')
                             for a in f.get('args') or []],
                    'personal': personal_of(n, f['name'], base),
                    'tk1': TK1.get(f'{n}.{f["name"]}', 'no'),
                    'deprecated': bool(f.get('isDeprecated')),
                    'description': scrub((f.get('description') or '').replace('\n', ' '))[:180],
                })
        elif k == 'INPUT_OBJECT':
            for f in t.get('inputFields') or []:
                inputs.append({'input': n, 'field': f['name'], 'type': tstr(f['type']),
                               'personal': personal_of(n, f['name'], tbase(f['type'])[0])})
        elif k == 'ENUM':
            enums[n] = [v['name'] for v in t.get('enumValues') or []]
        elif k == 'UNION':
            unions[n] = [p['name'] for p in t.get('possibleTypes') or []]
    res['object_types_reachable'] = sorted({r['type'] for r in rows})
    res['field_rows'] = len(rows)
    res['fields_personal'] = sum(1 for r in rows if r['personal'].startswith('yes'))
    res['fields_credential'] = [f'{r["type"]}.{r["field"]}' for r in rows if r['personal'].startswith('CREDENTIAL')]
    res['fields_with_arguments'] = [f'{r["type"]}.{r["field"]}({", ".join(r["args"])})' for r in rows if r['args']]
    res['tk1_stored_or_selected'] = sum(1 for r in rows if r['tk1'] != 'no')
    res['enums'] = enums
    res['unions'] = unions
    res['seconds'] = round(time.time() - t0, 1)
    (OUT / 'xr4_dice_schema_rows.json').write_text(jd({'fields': rows, 'input_fields': inputs, 'enums': enums,
                                                       'unions': unions}, 1) + '\n')
    out(f'M1: {len(types)} types · {len(reach)} reachable from Viewer · {len(rows)} object fields · '
        f'{len(inputs)} input fields · {len(enums)} enums · {res["fields_personal"]} personal · '
        f'{len(res["fields_with_arguments"])} fields with arguments · mutations: '
        + jd([m['field'] for m in res['mutations_NEVER_CALLED']]))
    return res, types


# =================================================================== the selection builder (M2)
DENY = {('Ticket', 'code'), ('Extra', 'code')}
SKIP_BACKREFS = {'event', 'order', 'orders', 'ticket', 'venue', 'venues', 'artists', 'products', 'product',
                 'images', 'priceTiers'}


def build_selection(types, tname, depth, max_depth, path, dropped, keep_backrefs=()):
    t = types.get(tname) or {}
    parts = []
    for f in t.get('fields') or []:
        fname = f['name']
        key = f'{tname}.{fname}'
        if (tname, fname) in DENY or CREDENTIAL.match(fname):
            continue
        if key in dropped:
            continue
        if any(a for a in f.get('args') or [] if a['type'].get('kind') == 'NON_NULL' and a.get('defaultValue') is None):
            continue
        base, bkind = tbase(f['type'])
        if bkind in ('SCALAR', 'ENUM'):
            parts.append(fname)
            continue
        if bkind not in ('OBJECT', 'INTERFACE'):
            continue
        if base.endswith('Connection') or base in path:
            continue
        if fname in SKIP_BACKREFS and fname not in keep_backrefs:
            continue
        if depth >= max_depth:
            continue
        sub = build_selection(types, base, depth + 1, max_depth, path | {base}, dropped)
        if sub:
            parts.append(f'{fname} {{ {sub} }}')
    return ' '.join(parts)


# =================================================================== value walking (counts only)
class Fill:
    """path -> [occurrences, filled]; list paths -> lengths; never a value kept."""

    def __init__(self):
        self.occ = collections.Counter()
        self.fil = collections.Counter()
        self.list_n = collections.Counter()        # path -> number of parents with a non-empty list
        self.list_items = collections.Counter()    # path -> total items
        self.enum_vals = collections.defaultdict(collections.Counter)

    def walk(self, obj, path, enum_paths):
        if isinstance(obj, dict):
            for k, v in obj.items():
                p = f'{path}.{k}'
                if isinstance(v, list):
                    self.occ[p] += 1
                    if v:
                        self.fil[p] += 1
                        self.list_n[p] += 1
                        self.list_items[p] += len(v)
                    for it in v:
                        self.walk(it, p + '[]', enum_paths)
                elif isinstance(v, dict):
                    self.occ[p] += 1
                    self.fil[p] += 1
                    self.walk(v, p, enum_paths)
                else:
                    self.occ[p] += 1
                    if filled(v):
                        self.fil[p] += 1
                    if p in enum_paths and v is not None:
                        self.enum_vals[p][str(v)] += 1

    def table(self):
        return {p: {'n': self.occ[p], 'filled': self.fil[p],
                    **({'non_empty_lists': self.list_n[p], 'items': self.list_items[p]} if p in self.list_items else {})}
                for p in sorted(self.occ)}


def enum_paths_of(types, root, sel_root_type):
    """paths whose leaf is a schema ENUM (their values are public and may be printed)."""
    res = set()

    def rec(tname, path, depth, seen):
        if depth > 5:
            return
        for f in (types.get(tname) or {}).get('fields') or []:
            base, bkind = tbase(f['type'])
            p = f'{path}.{f["name"]}'
            pl = p + ('[]' if is_list(f['type']) else '')
            if bkind == 'ENUM':
                res.add(p)
            elif bkind in ('OBJECT', 'INTERFACE') and base not in seen:
                rec(base, pl, depth + 1, seen | {base})
    rec(sel_root_type, root, 0, {sel_root_type})
    return res


def norm_email(e):
    return e.strip().lower() if isinstance(e, str) and e.strip() else None


def norm_phone(p):
    """digits only, in the +33 form for French numbers; None when unusable. -> (normalised, class)"""
    if not isinstance(p, str) or not p.strip():
        return None, 'empty'
    raw = p.strip()
    d = re.sub(r'\D', '', raw)
    if not d:
        return None, 'no digits'
    if raw.startswith('+'):
        pass
    elif d.startswith('00'):
        d = d[2:]
    elif len(d) == 10 and d.startswith('0'):
        d = '33' + d[1:]
    elif len(d) == 9 and d[0] in '67':
        d = '33' + d
    if d.startswith('330') and len(d) == 12:          # +33 (0)6 ... written with its trunk zero
        d = '33' + d[3:]
    if len(d) < 8 or len(d) > 15:
        return None, 'unusable length'
    if d.startswith('33') and len(d) == 11:
        return d, 'FR mobile' if d[2] in '67' else 'FR other'
    if d.startswith('33'):
        return d, 'FR wrong length'
    return d, 'foreign'


# =================================================================== M2 · DICE personal fill
def dice_orders_pages(sel, eid, label, page_size=100, max_pages=400):
    """Yield order nodes for one event (all pages). Shrinks the page on a complexity error."""
    after, pages, total, t0 = None, 0, None, time.time()
    size = page_size
    q = ('query O($first:Int!, $after:String, $e:ID!){ viewer { orders(first:$first, after:$after, '
         'where:{eventId:{eq:$e}}){ totalCount pageInfo{ endCursor hasNextPage } edges{ node{ %s } } } } }' % sel)
    stats = {'pages': 0, 'orders': 0, 'errors': collections.Counter(), 'page_size_used': size}
    while pages < max_pages:
        st, d, errs, sec, nb = dq(q, {'first': size, 'after': after, 'e': rid(eid)})
        conn = (((d or {}).get('viewer') or {}).get('orders')) if d else None
        if errs:
            for e in errs:
                stats['errors'][f'{".".join(e["path"]) or "-"} :: {e["message"][:120]}'] += 1
        if conn is None:
            if size > 10 and any(re.search(r'(?i)complex|cost|depth|too (large|many)|limit', e['message']) for e in errs):
                size = max(10, size // 2)
                stats['page_size_used'] = size
                continue
            stats['fatal'] = errs[:3]
            break
        total = conn.get('totalCount')
        pages += 1
        if pages % 50 == 0:
            out(f'   [{datetime.now(timezone.utc).strftime("%H:%M:%S")}Z dice {eid}: {pages} pages]')
        for edge in conn.get('edges') or []:
            stats['orders'] += 1
            yield edge.get('node') or {}
        pi = conn.get('pageInfo') or {}
        if not pi.get('hasNextPage') or not pi.get('endCursor') or pi.get('endCursor') == after:
            break
        after = pi['endCursor']
    stats['pages'] = pages
    stats['totalCount'] = total
    stats['seconds'] = round(time.time() - t0, 1)
    stats['errors'] = dict(stats['errors'])
    dice_orders_pages.last = stats


def probe_selection(types, eid, root_sel):
    """Run first:1 with the full selection; drop fields the API refuses (validation), up to 25 rounds.
    -> (selection, dropped {Type.field: scrubbed reason}, field-level runtime errors)"""
    dropped = {}
    runtime = collections.Counter()
    sel = None
    for _ in range(25):
        sel = root_sel(dropped)
        q = ('query P($e:ID!){ viewer { orders(first:1, where:{eventId:{eq:$e}}){ totalCount '
             'edges{ node{ %s } } } } }' % sel)
        st, d, errs, *_ = dq(q, {'e': rid(eid)})
        if not errs:
            return sel, dropped, dict(runtime)
        changed = False
        for e in errs:
            m = re.search(r'''Cannot query field ["'](\w+)["'] on type ["'](\w+)["']''', e['message'])
            if m:
                dropped[f'{m.group(2)}.{m.group(1)}'] = 'not in schema for this query: ' + e['message'][:120]
                changed = True
                continue
            if e['path'] and d:
                # a resolver refused one field (authorisation…): drop the leaf field, note why
                leaf = e['path'][-1]
                runtime[f'{".".join(e["path"])} :: {e["message"][:120]}'] += 1
                # resolve the type that owns the leaf by walking the selection path
                owner = owner_type(types, e['path'])
                if owner:
                    dropped[f'{owner}.{leaf}'] = 'refused at run time: ' + e['message'][:120]
                    changed = True
        if not changed:
            return sel, dropped, {**dict(runtime), 'unresolved': [x['message'][:160] for x in errs[:3]]}
    return sel, dropped, dict(runtime)


def owner_type(types, path):
    """['viewer','orders','edges','node','fan','email'] -> 'Fan'"""
    t = 'Query'
    qroot = types.get('Query') or types.get('RootQueryType') or {}
    t = qroot.get('name') or 'Query'
    for seg in path[:-1]:
        f = next((f for f in (types.get(t) or {}).get('fields') or [] if f['name'] == seg), None)
        if not f:
            return None
        t = tbase(f['type'])[0]
    return t


def m2(types):
    res = {'events': {}}
    enum_ps = enum_paths_of(types, 'Order', 'Order')

    def root_sel(dropped):
        return build_selection(types, 'Order', 0, 3, {'Order'}, dropped, keep_backrefs=('tickets',))

    first = next(iter(M2_EVENTS))
    sel, dropped, runtime = probe_selection(types, first, root_sel)
    res['selection_field_count'] = len(re.findall(r'\b\w+\b', sel))
    res['selection_names'] = sel           # field NAMES only (no value)
    res['dropped_fields'] = dropped
    res['probe_runtime_errors'] = runtime
    out('M2 selection (names only): ' + sel)
    if dropped:
        out('M2 dropped: ' + jd(dropped))

    for eid, label in M2_EVENTS.items():
        t0 = time.time()
        fill = Fill()
        buyers, holders = set(), set()
        holder_present = holder_null = holder_ne_buyer_id = holder_ne_buyer_email = holder_eq = 0
        tickets_n = 0
        survey_q = set()
        survey_tickets = survey_answers = survey_answered = 0
        listed_ids = set()
        orders_without_tickets = 0
        for node in dice_orders_pages(sel, eid, label):
            fill.walk(node, 'Order', enum_ps)
            fan = node.get('fan') or {}
            bid = fan.get('id')
            bem = norm_email(fan.get('email'))
            if bid is not None:
                buyers.add(str(bid))
            tk = node.get('tickets') or []
            if not tk:
                orders_without_tickets += 1
            for t in tk:
                tickets_n += 1
                if t.get('id') is not None:
                    listed_ids.add(str(t['id']))
                h = t.get('holder')
                if not h:
                    holder_null += 1
                else:
                    holder_present += 1
                    if h.get('id') is not None:
                        holders.add(str(h['id']))
                    if h.get('id') is not None and bid is not None:
                        if str(h['id']) != str(bid):
                            holder_ne_buyer_id += 1
                        else:
                            holder_eq += 1
                    hem = norm_email(h.get('email'))
                    if hem and bem and hem != bem:
                        holder_ne_buyer_email += 1
                fsa = t.get('fanSurveyAnswers') or []
                if fsa:
                    survey_tickets += 1
                for a in fsa:
                    survey_answers += 1
                    if isinstance(a, dict):
                        # a question's identity: any id-like field, else a digest of its non-answer strings (in memory)
                        qid = None
                        for k, v in a.items():
                            if isinstance(v, dict) and v:
                                qid = (f'{k}:{v["id"]}' if v.get('id') is not None else
                                       hashlib.sha256(json.dumps(v, sort_keys=True).encode()).hexdigest())
                                break
                        if qid is None:
                            for k in ('questionId', 'surveyQuestionId', 'question', 'title', 'label'):
                                if a.get(k) is not None:
                                    qid = hashlib.sha256(f'{k}:{a[k]}'.encode()).hexdigest()
                                    break
                        if qid:
                            survey_q.add(qid)
                        ans = [v for k, v in a.items() if re.search(r'(?i)answer|value|response|text', k)]
                        if any(filled(v) for v in ans):
                            survey_answered += 1
        ostats = dict(dice_orders_pages.last)
        # transfers per ticket
        tr = transfers_per_ticket(eid, listed_ids)
        ev = {
            'label': label, 'orders_stats': ostats, 'tickets_listed': tickets_n,
            'orders_without_listed_ticket': orders_without_tickets,
            'distinct_buyers_by_fan_id': len(buyers), 'distinct_holders_by_fan_id': len(holders),
            'holder': {'present': holder_present, 'null': holder_null, 'same_fan_as_buyer': holder_eq,
                       'different_fan_from_buyer': holder_ne_buyer_id,
                       'different_email_from_buyer': holder_ne_buyer_email},
            'fanSurveyAnswers': {'tickets_with_answers': survey_tickets, 'answers': survey_answers,
                                 'answers_with_a_filled_answer_field': survey_answered,
                                 'distinct_questions': len(survey_q)},
            'transfers': tr,
            'fill': fill.table(),
            'enum_values': {p: dict(c) for p, c in fill.enum_vals.items()},
            'seconds': round(time.time() - t0, 1),
        }
        res['events'][str(eid)] = ev
        f = ev['fill']

        def pc(p):
            x = f.get(p) or {}
            return f'{x.get("filled", 0)}/{x.get("n", 0)}'
        out(f'M2 {eid} {label}: {ostats.get("orders")} orders (totalCount {ostats.get("totalCount")}) · '
            f'{tickets_n} tickets · {ostats.get("pages")} pages · {ev["seconds"]}s')
        out('   fan: ' + ' · '.join(f'{k} {pc("Order.fan." + k)}' for k in
                                    ('id', 'firstName', 'lastName', 'email', 'phoneNumber', 'dob', 'optInPartners')))
        out('   order address: ' + ' · '.join(f'{p.split(".")[-1]} {pc(p)}' for p in f if p.startswith('Order.address.')))
        out('   holder: ' + jd(ev['holder']) + ' · survey: ' + jd(ev['fanSurveyAnswers']))
        out('   transfers: ' + jd({k: v for k, v in tr.items() if k != 'errors'}))
    return res


def transfers_per_ticket(eid, listed_ids):
    after, pages, t0 = None, 0, time.time()
    per_ticket = collections.Counter()
    transfers = 0
    errs_all = collections.Counter()
    total = None
    q = ('query T($first:Int!, $after:String, $e:ID!){ viewer { ticketTransfers(first:$first, after:$after, '
         'where:{eventId:{eq:$e}}){ totalCount pageInfo{ endCursor hasNextPage } edges{ node{ id transferredAt '
         'tickets{ id } } } } } }')
    while pages < 300:
        st, d, errs, *_ = dq(q, {'first': 100, 'after': after, 'e': rid(eid)})
        for e in errs:
            errs_all[e['message'][:120]] += 1
        conn = (((d or {}).get('viewer') or {}).get('ticketTransfers')) if d else None
        if conn is None:
            break
        total = conn.get('totalCount')
        pages += 1
        for edge in conn.get('edges') or []:
            transfers += 1
            for t in (edge.get('node') or {}).get('tickets') or []:
                if t and t.get('id') is not None:
                    per_ticket[str(t['id'])] += 1
        pi = conn.get('pageInfo') or {}
        if not pi.get('hasNextPage') or not pi.get('endCursor') or pi.get('endCursor') == after:
            break
        after = pi['endCursor']
    dist = collections.Counter(min(n, 4) for n in per_ticket.values())
    in_listing = sum(1 for t in per_ticket if t in listed_ids)
    return {'totalCount': total, 'transfers_read': transfers, 'pages': pages,
            'tickets_transferred': len(per_ticket),
            'transfers_per_ticket': {('4+' if k == 4 else str(k)): v for k, v in sorted(dist.items())},
            'transferred_ticket_ids_still_in_order_listing': in_listing,
            'share_of_listed_tickets_transferred': round(in_listing / len(listed_ids), 4) if listed_ids else None,
            'seconds': round(time.time() - t0, 1), 'errors': dict(errs_all)}


# =================================================================== M3 · one person on both platforms
KEY = None


def h(v):
    return hmac.new(KEY, v.encode('utf-8'), hashlib.sha256).digest()


class Side:
    def __init__(self):
        self.email = collections.defaultdict(set)    # bucket -> {hash}
        self.phone = collections.defaultdict(set)
        self.pairs = collections.defaultdict(set)    # bucket -> {(email_h, phone_h)}
        self.cls = collections.Counter()
        self.rows = collections.Counter()
        self.email_changed_by_norm = 0

    def add(self, buckets, email, phone):
        e = norm_email(email)
        if isinstance(email, str) and e and email != e:
            self.email_changed_by_norm += 1
        p, c = norm_phone(phone)
        self.cls[c] += 1
        eh = h('e:' + e) if e else None
        ph = h('p:' + p) if p else None
        for b in buckets:
            self.rows[b] += 1
            if eh:
                self.email[b].add(eh)
            if ph:
                self.phone[b].add(ph)
            if eh or ph:
                self.pairs[b].add((eh, ph))


def sg_pull(eid, side, label):
    tok, org = ENV['SHOTGUN_TOKEN_EPISODE'], ENV['SHOTGUN_ORGANIZER_ID_EPISODE']
    url = f'{SG}/tickets?' + urllib.parse.urlencode({'token': tok, 'organizer_id': org, 'event_id': eid,
                                                       'include_cohosted_events': '1'})
    pages = rows = 0
    status = collections.Counter()
    channel = collections.Counter()
    fill = collections.Counter()
    t0, err, seen = time.time(), None, set()
    while url:
        if url in seen:
            err = 'pagination loop'
            break
        seen.add(url)
        CALLS['shotgun'] += 1
        st, js, e, sec, nb = request(url)
        if st != 200 or not isinstance(js, dict):
            err = f'HTTP {st} {e or ""} at page {pages + 1}'
            break
        pages += 1
        if pages % 100 == 0:
            out(f'   [{datetime.now(timezone.utc).strftime("%H:%M:%S")}Z shotgun {eid}: {pages} pages]')
        items = js.get('data') if isinstance(js.get('data'), list) else next(
            (v for v in js.values() if isinstance(v, list)), [])
        for t in items:
            if not isinstance(t, dict):
                continue
            if str(t.get('event_id')) != str(eid):
                fill['event_id_mismatch'] += 1
                continue
            rows += 1
            s = str(t.get('ticket_status'))
            ch = str(t.get('deal_channel'))
            status[s] += 1
            channel[ch] += 1
            em, ph = t.get('contact_email'), t.get('contact_phone')
            fill['contact_email'] += filled(em)
            fill['contact_phone'] += filled(ph)
            buckets = ['all']
            if s == 'valid':
                buckets.append('valid')
                if ch != 'invitation':
                    buckets.append('valid_not_invitation')
            side.add(buckets, em, ph)
        nxt = (js.get('pagination') or {}).get('next') if isinstance(js.get('pagination'), dict) else None
        if not items or not nxt:
            break
        url = nxt
        time.sleep(PACE)
    del url
    r = {'event': eid, 'label': label, 'pages': pages, 'rows': rows, 'status': dict(status),
         'channel': dict(channel), 'fill': dict(fill), 'seconds': round(time.time() - t0, 1), 'error': err}
    out(f'M3 shotgun {eid} {label}: {rows} rows · {pages} pages · {r["seconds"]}s · email {fill["contact_email"]} · '
        f'phone {fill["contact_phone"]}' + (f' · ERROR {err}' if err else ''))
    return r


def dice_pull_people(eid, side, label):
    sel = 'id fan { email phoneNumber } tickets { id holder { email phoneNumber } }'
    stats = {'orders': 0, 'orders_with_listed_ticket': 0, 'tickets': 0, 'fan_email': 0, 'fan_phone': 0,
             'holder_email': 0, 'holder_phone': 0}
    for node in dice_orders_pages(sel, eid, label):
        stats['orders'] += 1
        fan = node.get('fan') or {}
        tk = node.get('tickets') or []
        stats['fan_email'] += filled(fan.get('email'))
        stats['fan_phone'] += filled(fan.get('phoneNumber'))
        b = ['buyers_all']
        if tk:
            stats['orders_with_listed_ticket'] += 1
            b.append('buyers_listed')
        side.add(b + ['people_all'], fan.get('email'), fan.get('phoneNumber'))
        for t in tk:
            stats['tickets'] += 1
            ho = t.get('holder') or {}
            stats['holder_email'] += filled(ho.get('email'))
            stats['holder_phone'] += filled(ho.get('phoneNumber'))
            if ho:
                side.add(['holders', 'people_all'], ho.get('email'), ho.get('phoneNumber'))
    stats.update({k: v for k, v in dice_orders_pages.last.items() if k in ('pages', 'totalCount', 'seconds', 'errors', 'fatal')})
    out(f'M3 dice {eid} {label}: ' + jd(stats))
    return stats


def inter(a, b):
    return len(a & b)


def either_match(pairs_a, emails_b, phones_b):
    """distinct people of A (by e-mail when present, else phone) matched in B by e-mail OR phone."""
    people = {}
    for eh, ph in pairs_a:
        key = eh or ph
        people.setdefault(key, set()).add((eh, ph))
    m = 0
    for key, ps in people.items():
        if any((eh and eh in emails_b) or (ph and ph in phones_b) for eh, ph in ps):
            m += 1
    return len(people), m


def m3():
    global KEY
    KEY = os.urandom(32)          # never written, never printed; dies with this process
    res = {'pairs': [], 'fideles': None}
    sg_sides = {}
    for label, sg_id, dice_id in M3_PAIRS:
        sgs, ds = Side(), Side()
        r_sg = sg_pull(sg_id, sgs, label)
        r_d = dice_pull_people(dice_id, ds, label)
        sg_sides[sg_id] = sgs
        pr = {'label': label, 'shotgun': r_sg, 'dice': r_d,
              'phone_classes': {'shotgun': dict(sgs.cls), 'dice': dict(ds.cls)},
              'emails_changed_by_trim_lower': {'shotgun': sgs.email_changed_by_norm, 'dice': ds.email_changed_by_norm},
              'distinct': {}, 'intersection': {}}
        for side_name, sd in (('shotgun', sgs), ('dice', ds)):
            pr['distinct'][side_name] = {b: {'emails': len(sd.email[b]), 'phones': len(sd.phone[b])} for b in sd.rows}
        combos = [('valid', 'buyers_listed', 'PRIMARY: Shotgun valid × DICE buyers with a listed ticket'),
                  ('valid_not_invitation', 'buyers_listed', 'Shotgun valid minus invitations × DICE buyers listed'),
                  ('all', 'buyers_all', 'every Shotgun row × every DICE order'),
                  ('valid', 'people_all', 'Shotgun valid × DICE buyers + holders')]
        for sb, db, name in combos:
            se, sp = sgs.email[sb], sgs.phone[sb]
            de, dp = ds.email[db], ds.phone[db]
            n_people, n_either = either_match(sgs.pairs[sb], de, dp)
            pr['intersection'][name] = {
                'shotgun_emails': len(se), 'dice_emails': len(de), 'emails_in_both': inter(se, de),
                'union_emails': len(se | de),
                'shotgun_phones': len(sp), 'dice_phones': len(dp), 'phones_in_both': inter(sp, dp),
                'shotgun_people': n_people, 'shotgun_people_matched_by_email_or_phone': n_either,
                'share_of_dice_emails_also_on_shotgun': round(inter(se, de) / len(de), 4) if de else None,
                'share_of_shotgun_emails_also_on_dice': round(inter(se, de) / len(se), 4) if se else None,
            }
            out(f'M3 {label} · {name}: ' + jd(pr['intersection'][name]))
        res['pairs'].append(pr)
        del ds
    # the two events together: how many distinct e-mails Brevo would hold from them
    allsg = set()
    # (re-using what is still in memory)
    for pr_sg in sg_sides.values():
        allsg |= pr_sg.email['valid']
    res['both_events_shotgun_valid_distinct_emails'] = len(allsg)
    # fidèles: Paris XXL 2025 -> 2026 on Shotgun
    s26 = sg_sides.get(494642)
    fid = {'2026_event': 494642, 'rows': []}
    prev_union = Side()
    for label, eid in M3_FIDELES:
        s = Side()
        r = sg_pull(eid, s, label)
        for b in ('all', 'valid'):
            prev_union.email[b] |= s.email[b]
        fid['rows'].append({'event': eid, 'label': label, 'pull': r,
                            **{f'{b}_emails_2025': len(s.email[b]) for b in ('all', 'valid')},
                            **{f'{b}_emails_2026': len(s26.email[b]) for b in ('all', 'valid')},
                            **{f'{b}_in_both': inter(s.email[b], s26.email[b]) for b in ('all', 'valid')},
                            'valid_share_of_2026_returning': round(inter(s.email['valid'], s26.email['valid']) /
                                                                   len(s26.email['valid']), 4) if s26.email['valid'] else None})
        out(f'M3 fidèles {label} → 2026: ' + jd({k: v for k, v in fid['rows'][-1].items() if k != 'pull'}))
    fid['2025_main_plus_presale'] = {b: {'emails_2025': len(prev_union.email[b]),
                                         'in_both': inter(prev_union.email[b], s26.email[b])} for b in ('all', 'valid')}
    out('M3 fidèles 2025 (main + presale) → 2026: ' + jd(fid['2025_main_plus_presale']))
    res['fideles'] = fid
    KEY = None
    return res


# =================================================================== main
def main():
    part = sys.argv[1] if len(sys.argv) > 1 else ''
    started = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    res = {'probe': 'xr4', 'part': part, 'started_utc': started, 'pace_s': PACE, 'dice_pace_s': DPACE}
    if part == 'dice':
        if not ENV['DICE_TOKEN']:
            out('DICE_TOKEN not set - SKIPPED')
        else:
            st, d, errs, *_ = dq('{ viewer { id name } }')
            res['viewer_ok'] = bool(d and d.get('viewer')) and not errs
            out('viewer reachable: ' + str(res['viewer_ok']))
            res['M1'], types = m1_schema()
            if types:
                res['M2'] = m2(types)
    elif part == 'overlap':
        if not (ENV['DICE_TOKEN'] and ENV['SHOTGUN_TOKEN_EPISODE'] and ENV['SHOTGUN_ORGANIZER_ID_EPISODE']):
            out('a secret is missing - SKIPPED')
        else:
            res['M3'] = m3()
    else:
        print('usage: probe_xr4.py dice|overlap')
        return 2
    res['calls'] = dict(CALLS)
    res['http_status_counts'] = dict(HTTP_STATS)
    res['response_header_names'] = HEADER_NAMES
    res['rate_limit_headers_numeric'] = RATE_HEADERS
    res['wall_seconds'] = round(time.time() - T_START, 1)
    out(f'calls {jd(dict(CALLS))} · http {jd(dict(HTTP_STATS))} · {res["wall_seconds"]}s')
    (OUT / f'xr4_{part}.json').write_text(scrub(jd(res, 1)) + '\n')
    (OUT / f'xr4_{part}.log').write_text('\n'.join(LOG) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
