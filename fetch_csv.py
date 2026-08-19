#!/usr/bin/env python3
"""
FESTIFLOW - API Fetch (Phase 1)
================================
Pulls live ticket data from the Shotgun REST API and the DICE partners GraphQL
API and writes a merged CSV in the exact 11-column format that run.py consumes.

USAGE:
    python fetch_csv.py                        # defaults to rennes_2026
    python fetch_csv.py --event rennes_2026
    python fetch_csv.py --event rennes_2026 --out api_output/rennes_2026_merged.csv
    python fetch_csv.py --event rennes_2026 --skip-dice   # Shotgun only

OUTPUT:
    api_output/{event_id}_merged.csv

ENVIRONMENT VARIABLES (repository secrets):
    SHOTGUN_TOKEN_EPISODE       Episode account JWT   (organizer 171835)
    SHOTGUN_TOKEN_SONORA        Sonora account JWT    (organizer 207784)
    SHOTGUN_ORGANIZER_ID_SONORA optional override for the Sonora organizer id
    DICE_TOKEN                  DICE MIO promoter token

Pure Python stdlib. Writes nothing outside the output directory.
"""

import argparse
import ast
import base64
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, date
from pathlib import Path


# ============================================================================
# CONFIG
# ============================================================================

SHOTGUN_API = 'https://api.shotgun.live/tickets'
DICE_API = 'https://partners-endpoint.dice.fm/graphql'

# Shotgun serves 100 tickets/page and allows ~100 requests/minute. 0.8s keeps a
# single fetcher at ~75/min. When several events are fetched concurrently they
# share that quota, so the workflow raises this via SHOTGUN_PAGE_PACING_S -
# roughly 0.8 x the number of parallel jobs.
SHOTGUN_PAGE_PACING_S = float(os.environ.get('SHOTGUN_PAGE_PACING_S') or 0.8)

# Used by record_total to reject a page-sized "total". It was referenced there
# and never defined, so record_total raised NameError the moment any TOTAL_KEYS
# entry arrived as an int - which is to say, on the first response that would
# have made the total reconciliation work at all. It never fired because the
# live envelope exposes none of those keys at the top level ("total field not
# exposed", every run), so a dead branch hid an undefined name.
SHOTGUN_PAGE_SIZE = 100

# A 429 is a per-minute quota, so backing off for seconds just burns retries -
# the window has to roll over. Wait out the minute instead.
RATE_LIMIT_BACKOFF_S = 60
RATE_LIMIT_RETRIES = 6
# 'resold' is Shotgun's resale marketplace: when a ticket changes hands the
# original row is marked resold and the buyer gets a fresh 'valid' row, so
# counting both counts one physical ticket twice. Bordeaux Jun 2026 carried
# 4,217 such rows. Count 'valid' only.
SHOTGUN_VALID_STATUSES = ('valid',)

# Shotgun's API surfaces tickets imported from other platforms alongside its
# own sales. On a co-hosted event that also has a DICE feed, those imports are
# the same physical tickets we already fetch from DICE - counting both inflated
# Bordeaux Jun 2026 to 36,313 against a real total of ~26,738.
#
# So when an event has BOTH a shotgun_event_id and a dice_mio_id, keep only
# Shotgun's own channels and let the DICE feed supply the rest. Shotgun-only
# events keep every channel: there is no second source to double up with.
SHOTGUN_ORGANIC_CHANNELS = ('online', 'onsite', 'invitation')
SHOTGUN_KNOWN_IMPORT_CHANNELS = ('distributor', 'offline', 'reseller', 'duplicata')

DICE_PAGE_SIZE = 100

HTTP_TIMEOUT_S = 60
HTTP_RETRIES = 4

SHOTGUN_ACCOUNTS = {
    'episode': {
        'token_env': 'SHOTGUN_TOKEN_EPISODE',
        'organizer_id': '171835',
        'organizer_id_env': None,
        # bordeaux_2026 (505434) lives on Episode despite the ML x Sonora
        # branding - confirmed by probe_shotgun_account.py, which got
        # event_name='MADAME LOYAL x SONORA : BORDEAUX' under organizer 171835
        # and nothing under Sonora. Do not "correct" it back by brand.
        'events': ['epk_2026', 'rennes_2026', 'geneve_2026', 'bordeaux_2026',
                   'paris_xxl_2026',
                   'epk_2023', 'geneve_2025', 'rennes_2025',
                   'paris_xxl_2025', 'paris_xxl_2025_presale'],
    },
    'sonora': {
        'token_env': 'SHOTGUN_TOKEN_SONORA',
        'organizer_id': '207784',
        'organizer_id_env': 'SHOTGUN_ORGANIZER_ID_SONORA',
        # bordeaux_oct_2026 (565846) verified on this account - it returned
        # 7,985 tickets. bordeaux_2025/halloween_2025 are unverified but only
        # matter if their reference CSVs are ever refetched.
        #
        # sonora_impact_2026 (544355) verified before the config row was
        # written, by probe_shotgun_account.py in run 32146511963:
        #
        #   episode  (org 171835) cohosted=0: 0 tickets
        #   episode  (org 171835) cohosted=1: 0 tickets
        #   sonora   (org 207784) cohosted=0: 100 tickets on page 1
        #                                     — event_name='SONORA x IMPACT'
        #
        # Both halves matter. The Sonora line confirms ownership BY NAME rather
        # than by promoter - the note above about bordeaux_2026 exists because
        # brand and account are independent. The episode lines confirm what a
        # missing entry costs: DEFAULT_SHOTGUN_ACCOUNT is 'episode', and episode
        # answers with ZERO TICKETS, not an error. An event left out of both
        # lists is therefore indistinguishable from an event that has sold
        # nothing, on a page that renders perfectly.
        'events': ['bordeaux_oct_2026', 'bordeaux_2025', 'halloween_2025',
                   'sonora_impact_2026'],
    },
}

DEFAULT_SHOTGUN_ACCOUNT = 'episode'

CSV_FIELDNAMES = [
    'order_date', 'order_datetime', 'ticket_type', 'access_level', 'attendance_days',
    'product_name', 'platform', 'price', 'gross_price', 'quantity', 'is_paid',
]

# Some events sell on a DICE account this token cannot reach. Genève 2026 is
# one: probe_dice_event.py against 588085 got node -> null and 0 orders, while
# Rennes and Paris XXL resolved fully on the same token, so it is an account
# boundary rather than a bad id. Those sales are exported from the DICE
# back-office by hand, run through the same classify_ticket, and committed here
# in the 11-column merged format, then concatenated onto the API results.
#
# This is a stopgap. The moment the event gets a dice_mio_id in the config the
# API becomes the source of truth and the file is ignored - see the guard in
# main(), which refuses to use both for one event rather than double-counting.
# A refreshed export is just a new commit of the same path plus a rebuild.
MANUAL_DICE_CSVS = {
    'geneve_2026': 'csv_database/geneve_2026_dice_manual/geneve_2026_dice_manual.csv',
}

# Tickets are read through their orders, not through Event.tickets.
#
# Ticket.claimedAt is the only date on a ticket, and it records when the fan
# activated the ticket - null until close to the event, so it is empty for every
# ticket of a future event (all 2215 Rennes 2026 tickets came back null).
# Order.purchasedAt is the actual sale timestamp.
#
# viewer.orders was previously ruled out because an unfiltered query scans every
# order the promoter has ever taken. The where filter scopes it to one event,
# which removes that problem: measured at ~0.5s per page of 50 orders.
#
# Every field below is schema-verified via live introspection. Do not add others.
DICE_ORDERS_QUERY = """
query FetchOrders($eventId: ID!, $first: Int!, $after: String) {
  viewer {
    orders(first: $first, after: $after, where: {eventId: {eq: $eventId}}) {
      totalCount
      pageInfo { endCursor hasNextPage }
      edges {
        node {
          id
          purchasedAt
          quantity
          tickets {
            id
            fullPrice
            total
            ticketType { name }
          }
        }
      }
    }
  }
}
"""


# Tokens that must stay upper-case after .title() lowercases them ("VIP" -> "Vip").
PRODUCT_NAME_UPPER_TOKENS = [
    'VIP', 'VVIP', 'PMR', 'XXL', 'EPK', 'ML', 'DJ', 'B2B', 'CE', 'NYE',
]
_UPPER_TOKEN_RE = re.compile(
    r'\b(' + '|'.join(PRODUCT_NAME_UPPER_TOKENS) + r')\b', re.IGNORECASE
)


def normalize_product_name(raw):
    """
    Title-case a product name so the same product from both platforms collapses
    to one line in the répartition table ("Pass 2 jours" / "PASS 2 JOURS" ->
    "Pass 2 Jours"), then restore acronyms that .title() would mangle.
    """
    if not raw:
        return ''
    name = raw.strip().title()
    return _UPPER_TOKEN_RE.sub(lambda m: m.group(1).upper(), name)


def log(msg):
    print(msg, flush=True)


# ============================================================================
# UNIFIED TICKET CLASSIFIER
# Copied verbatim from run.py (lines 563-745) - single source of truth.
# Do not edit here; edit run.py and re-copy.
# ============================================================================

ALL_DAYS = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche']

def classify_ticket(name, price=None, tags='', is_dice_filename=False, event_days=None):
    """
    Universal ticket classifier. Works on any ticket name string:
    DICE Item Type, Shotgun CATEGORY, Shotgun DEAL TITLE, or DICE filename.

    event_days: optional list of dicts with 'day_name' and 'day_date' (date objects)
                for date-based fallback matching (e.g. "13 Juin" → Samedi)

    Returns: (ticket_type, access_level, attendance_days, product_name)
      - ticket_type: day name, '2-jours', '3-jours', or 'single_day'
      - access_level: 'regular', 'vip', 'backstage', 'early_entry', 'invitation', 'jeu_concours', 'group_discount'
      - attendance_days: list of day names or None if ambiguous
      - product_name: cleaned display name
    """
    if not name:
        return 'single_day', 'regular', [], ''

    raw = name.strip()
    n = raw.upper()

    # DICE filename cleanup
    if is_dice_filename:
        n = n.split('-DICE-')[0].split('-MADAME-LOYAL')[0].split('-SONORA')[0]
        n = n.replace('--', ' ').replace('-', ' ')

    # Clean noise
    n_clean = n
    for suffix in [' - JOUR 1', ' - JOUR 2', ' - JOUR 3', ' - DAY 1', ' - DAY 2', ' - DAY 3',
                   '(DERNIERS TICKETS)', '(OFFRE ULTRA LIMITÉE)', '(OFFRE ULTRA LIMITEE)']:
        n_clean = n_clean.replace(suffix, '')

    # Remove date references like "13 JUIN"
    n_clean = re.sub(
        r'\d{1,2}\s+(JANVIER|FEVRIER|FÉVRIER|MARS|AVRIL|MAI|JUIN|JUILLET|AOUT|AOÛT|SEPTEMBRE|OCTOBRE|NOVEMBRE|DECEMBRE|DÉCEMBRE)',
        '', n_clean
    )

    # ═══ ACCESS LEVEL ═══
    access_level = 'regular'
    if tags and tags.strip().lower() == 'invitation':
        access_level = 'invitation'
    elif 'INVITATION' in n:
        access_level = 'invitation'
    elif 'JEU CONCOURS' in n:
        access_level = 'jeu_concours'
    elif 'VIP' in n or 'ACCÈS SCÈNE' in n or 'ACCES SCENE' in n:
        access_level = 'vip'
    elif 'GOLD' in n:
        access_level = 'vip'
    elif 'BACKSTAGE' in n and 'VIP' not in n:
        access_level = 'backstage'
    elif 'ENTRÉE AVANT' in n or 'ENTREE AVANT' in n:
        access_level = 'early_entry'
    elif '5 POUR 4' in n:
        access_level = 'group_discount'

    if price is not None and float(price) == 0 and access_level == 'regular':
        access_level = 'invitation'

    # ═══ DETECT DAYS MENTIONED ═══
    days_found = []
    for day in ALL_DAYS:
        if day.upper() in n_clean:
            days_found.append(day)
    # Also check parenthetical content
    paren_match = re.search(r'\(([^)]+)\)', n_clean)
    if paren_match:
        for day in ALL_DAYS:
            if day.upper() in paren_match.group(1) and day not in days_found:
                days_found.append(day)
    days_found.sort(key=lambda d: ALL_DAYS.index(d))

    # ═══ DATE-BASED FALLBACK ═══
    # If no day names found but ticket contains a date (e.g. "13 Juin"), match to event_days
    if not days_found and event_days:
        MONTHS_MAP = {
            'JANVIER': 1, 'FEVRIER': 2, 'FÉVRIER': 2, 'MARS': 3, 'AVRIL': 4, 'MAI': 5,
            'JUIN': 6, 'JUILLET': 7, 'AOUT': 8, 'AOÛT': 8, 'SEPTEMBRE': 9,
            'OCTOBRE': 10, 'NOVEMBRE': 11, 'DECEMBRE': 12, 'DÉCEMBRE': 12,
            'JAN': 1, 'FEV': 2, 'FÉV': 2, 'MAR': 3, 'AVR': 4, 'JUN': 6,
            'JUL': 7, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12, 'DÉC': 12,
        }
        date_match = re.search(
            r'(\d{1,2})\s+(JANVIER|FEVRIER|FÉVRIER|MARS|AVRIL|MAI|JUIN|JUILLET|AOUT|AOÛT|SEPTEMBRE|OCTOBRE|NOVEMBRE|DECEMBRE|DÉCEMBRE|JAN|FEV|FÉV|MAR|AVR|JUN|JUL|SEP|OCT|NOV|DEC|DÉC)',
            n
        )
        if date_match:
            day_num = int(date_match.group(1))
            month_num = MONTHS_MAP.get(date_match.group(2))
            if month_num:
                for ed in event_days:
                    dd = ed.get('day_date')
                    if dd and dd.day == day_num and dd.month == month_num:
                        days_found.append(ed['day_name'].lower())
                        break

    # ═══ TICKET TYPE ═══
    ticket_type = None
    attendance_days = []

    if '3 JOURS' in n_clean or 'TROIS JOURS' in n_clean:
        ticket_type = '3-jours'
        attendance_days = days_found if len(days_found) >= 3 else None
    elif '2 JOURS' in n_clean or 'DEUX JOURS' in n_clean:
        ticket_type = '2-jours'
        attendance_days = days_found if len(days_found) >= 2 else None
    elif '1 JOUR' in n_clean:
        ticket_type = 'single_day'
        attendance_days = days_found if days_found else None
    elif len(days_found) >= 3:
        ticket_type = '3-jours'
        attendance_days = days_found
    elif len(days_found) == 2:
        ticket_type = '2-jours'
        attendance_days = days_found
    elif len(days_found) == 1:
        ticket_type = days_found[0]
        attendance_days = days_found
    else:
        ticket_type = 'single_day'
        attendance_days = None

    # ═══ PRODUCT NAME ═══
    if is_dice_filename:
        product_name = raw.split('-DICE-')[0].split('-madame-loyal')[0].split('-sonora')[0]
        product_name = product_name.replace('--', ' + ').replace('-', ' ').strip().title()
    else:
        product_name = raw.strip()
        if product_name.isupper():
            product_name = product_name.title()

    return ticket_type, access_level, attendance_days, product_name


def resolve_attendance(ticket_type, attendance_days, event_day_names):
    """
    Resolve attendance_days into a concrete presence dict.

    Args:
        ticket_type: from classify_ticket
        attendance_days: from classify_ticket (may be None if ambiguous)
        event_day_names: list from event config e.g. ['jeudi', 'vendredi', 'samedi']

    Returns: dict {day_name: 1 or 0}
    """
    presence = {dn: 0 for dn in event_day_names}

    if attendance_days is not None and len(attendance_days) > 0:
        for d in attendance_days:
            if d in presence:
                presence[d] = 1
    elif ticket_type == '3-jours':
        for dn in event_day_names:
            presence[dn] = 1
    elif ticket_type == '2-jours':
        # Default: last 2 main days (not warm-up)
        main_days = event_day_names[-2:] if len(event_day_names) >= 2 else event_day_names
        for dn in main_days:
            presence[dn] = 1
    elif ticket_type in event_day_names:
        presence[ticket_type] = 1
    elif ticket_type == 'single_day':
        # Unknown day - count on all days (conservative, better than invisible)
        for dn in event_day_names:
            presence[dn] = 1

    return presence


# ============================================================================
# EVENT CONFIG
# ============================================================================

def load_event_config(config_path, event_id):
    """
    Read event_config.csv and return the config for one event.

    The config is row-per-day: the first row of an event carries the event-level
    fields, subsequent rows only carry day_number / day_name / day_date / capacity.

    Returns dict with: event_id, event_name, currency, shotgun_event_id,
    dice_mio_id, event_days (list of {'day_number','day_name','day_date'}),
    day_names (lowercased, ordered by day_number).
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise SystemExit(f"Event config not found: {config_path}")

    header = {}
    days = []
    with open(config_path, 'r', encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            if (row.get('event_id') or '').strip() != event_id:
                continue
            if not header and (row.get('event_name') or '').strip():
                header = row
            day_name = (row.get('day_name') or '').strip()
            day_date = parse_config_date((row.get('day_date') or '').strip())
            if day_name and day_date:
                days.append({
                    'day_number': int(row.get('day_number') or len(days) + 1),
                    'day_name': day_name.lower(),
                    'day_date': day_date,
                })

    if not header and not days:
        raise SystemExit(f"Event '{event_id}' not found in {config_path}")
    if not header:
        raise SystemExit(f"Event '{event_id}' has no header row in {config_path}")

    days.sort(key=lambda d: d['day_number'])

    return {
        'event_id': event_id,
        'event_name': (header.get('event_name') or '').strip(),
        'currency': (header.get('currency') or 'EUR').strip(),
        'shotgun_event_id': (header.get('shotgun_event_id') or '').strip(),
        'dice_mio_id': (header.get('dice_mio_id') or '').strip(),
        'event_days': days,
        'day_names': [d['day_name'] for d in days],
    }


def parse_config_date(value):
    """Parse 'YYYY-MM-DD' from event_config.csv into a date object."""
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


def resolve_shotgun_account(event_id):
    """Return (account_name, token, organizer_id) for an event_id."""
    account_name = DEFAULT_SHOTGUN_ACCOUNT
    for name, cfg in SHOTGUN_ACCOUNTS.items():
        if event_id in cfg['events']:
            account_name = name
            break

    cfg = SHOTGUN_ACCOUNTS[account_name]
    token = os.environ.get(cfg['token_env'], '').strip()
    organizer_id = cfg['organizer_id']
    if cfg['organizer_id_env']:
        organizer_id = os.environ.get(cfg['organizer_id_env'], '').strip() or organizer_id
    return account_name, token, organizer_id


# ============================================================================
# HTTP
# ============================================================================

def http_json(url, method='GET', headers=None, payload=None):
    """
    Perform an HTTP request and return the decoded JSON body.
    Retries transient failures (5xx, 429, network errors) with exponential backoff.
    """
    body = json.dumps(payload).encode('utf-8') if payload is not None else None
    headers = dict(headers or {})
    if body is not None:
        headers.setdefault('Content-Type', 'application/json')
    headers.setdefault('Accept', 'application/json')

    last_error = None
    attempt = 0
    rate_limited = 0
    while True:
        attempt += 1
        backoff = 2 ** attempt
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            detail = e.read().decode('utf-8', 'replace')[:500]
            last_error = f"HTTP {e.code} {e.reason}: {detail}"
            if e.code == 429:
                # Rate limited: honour Retry-After when given, else wait out the
                # quota window. Counted separately so a busy period cannot eat
                # the retries meant for genuine transient failures.
                rate_limited += 1
                if rate_limited > RATE_LIMIT_RETRIES:
                    raise RuntimeError(
                        f"{method} {redact(url)} rate limited {rate_limited} times - {last_error}")
                retry_after = (e.headers or {}).get('Retry-After')
                backoff = (int(retry_after) if str(retry_after).isdigit()
                           else RATE_LIMIT_BACKOFF_S)
                attempt -= 1  # does not count against the transient-failure budget
            elif e.code not in (500, 502, 503, 504):
                # Other 4xx will not fix themselves
                raise RuntimeError(f"{method} {redact(url)} failed - {last_error}")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_error = f"{type(e).__name__}: {e}"

        if attempt >= HTTP_RETRIES:
            raise RuntimeError(
                f"{method} {redact(url)} failed after {attempt} attempts - {last_error}")
        log(f"   ⚠ request failed ({last_error}) - retrying in {backoff}s")
        time.sleep(backoff)


def redact(url):
    """Strip the token query param so URLs are safe to log."""
    return re.sub(r'(token=)[^&]+', r'\1***', url)


# ============================================================================
# SHOTGUN
# ============================================================================

def extract_shotgun_tickets(payload):
    """
    Pull the ticket list out of a Shotgun /tickets response.

    The documented sample only pins down `params` / `pagination`, so accept the
    common container keys and fall back to the first list-of-objects present.
    """
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ('tickets', 'data', 'results', 'items', 'rows'):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    for key, value in payload.items():
        if key in ('params', 'pagination'):
            continue
        if isinstance(value, list) and (not value or isinstance(value[0], dict)):
            return value
    return []


# Where the incremental state lives, alongside the merged CSV it describes.
STATE_DIR = Path('data')

# Keys the total might plausibly hide under. Nothing in Shotgun's documented
# response promises one; if none of these appear, reconciliation falls back to
# the modification detector instead of pretending it has a number.
TOTAL_KEYS = ('total', 'total_count', 'totalCount', 'count', 'ticket_count')


def record_cursor(probe, ticket):
    """Track the highest {ticket_updated_at}_{ticket_id} seen this fetch."""
    updated = str(ticket.get('ticket_updated_at') or '').strip()
    ticket_id = ticket.get('ticket_id')
    if not updated or ticket_id in (None, ''):
        return
    candidate = (updated, str(ticket_id))
    if probe.get('max_key') is None or candidate > probe['max_key']:
        probe['max_key'] = candidate
        probe['cursor'] = f"{updated}_{ticket_id}"


def record_total(probe, payload):
    """Note a total-count field if the envelope exposes one."""
    for key in TOTAL_KEYS:
        value = payload.get(key)
        # ticket_count is per-page on the pages we have seen, so only trust a
        # value that exceeds one page - a real total cannot be page-sized.
        if isinstance(value, int) and value > SHOTGUN_PAGE_SIZE:
            probe['total'] = value
            probe['total_key'] = key
            return


def state_path(event_id):
    return STATE_DIR / f"{event_id}_state.json"


def load_state(event_id):
    """Read the sidecar cursor state, or None if there is none / it is unusable."""
    path = state_path(event_id)
    if not path.exists():
        return None
    try:
        with open(path, encoding='utf-8') as f:
            state = json.load(f)
    except (OSError, ValueError) as exc:
        log(f"   ⚠ unreadable state at {path} ({exc}) - falling back to a full fetch")
        return None
    if not isinstance(state, dict) or not state.get('cursor'):
        return None
    return state


def save_state(event_id, cursor, rows, max_ordered_at, shotgun_event_id):
    """
    Persist what an incremental resume needs.

    Deliberately a sidecar rather than extra CSV columns: the cursor needs a
    ticket_id and a timestamp, and the merged CSV is aggregate-only by
    contract (see assert_merged_schema). One id for the newest ticket is not
    the same as a per-ticket identity column.
    """
    path = state_path(event_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({
            'cursor': cursor,
            'rows': rows,
            'max_ordered_at': max_ordered_at,
            'shotgun_event_id': shotgun_event_id,
        }, f, indent=2, sort_keys=True)
        f.write('\n')
    return path


def load_stored_rows(csv_path):
    """
    Read a previously committed merged CSV back into in-memory rows.

    Returns None when there is nothing usable to resume from, which the caller
    treats as "do a full fetch" rather than an error.
    """
    path = Path(csv_path)
    if not path.exists():
        return None
    rows = []
    try:
        with open(path, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            if set(reader.fieldnames or []) != set(CSV_FIELDNAMES):
                log(f"   ⚠ {path} is not the 11-column schema - full fetch")
                return None
            for row in reader:
                dt = parse_shotgun_datetime(row.get('order_datetime'))
                if dt is None:
                    continue
                rows.append({
                    'order_date': dt.date(),
                    'order_datetime': dt.replace(microsecond=0),
                    'ticket_type': (row.get('ticket_type') or '').strip(),
                    'access_level': (row.get('access_level') or '').strip(),
                    'attendance_days': parse_attendance_days(row.get('attendance_days')),
                    'product_name': (row.get('product_name') or '').strip(),
                    'platform': (row.get('platform') or '').strip(),
                    'price': float(row.get('price') or 0),
                    'gross_price': float(row.get('gross_price') or 0),
                    'quantity': int(float(row.get('quantity') or 1)),
                    'is_paid': int(float(row.get('is_paid') or 0)),
                })
    except (OSError, ValueError) as exc:
        log(f"   ⚠ could not read {path} ({exc}) - full fetch")
        return None
    return rows or None


def fetch_shotgun_pages(token, organizer_id, shotgun_event_id, after=None, probe=None):
    """
    Yield raw Shotgun ticket dicts, following pagination.next until exhausted.

    `after` resumes from a keyset cursor. Shotgun's own pagination.next carries
    one and its shape is `{ticket_updated_at}_{ticket_id}`, e.g.
    `2026-01-06T18:01:05.041Z_89328982` - so it orders by ticket_updated_at,
    not ordered_at. That is the useful ordering: it surfaces modifications
    (refunds, cancellations, the resale flip) as well as new sales.

    `probe`, if given, is a dict this fills in as it goes: the highest cursor
    seen, and any total-count field the envelope turns out to expose. Nothing
    in the documented response promises a total, so it is discovered rather
    than assumed.
    """
    query = urllib.parse.urlencode({
        'token': token,
        'organizer_id': organizer_id,
        'event_id': shotgun_event_id,
        # Co-hosted events can be owned by the partner organizer, and the
        # endpoint excludes them by default - returning an empty set that is
        # indistinguishable from "no sales". EPK 2026 (535882) returned nothing
        # under either account until this was set. Harmless for single-host
        # events: there is nothing extra to include.
        'include_cohosted_events': '1',
    })
    url = f"{SHOTGUN_API}?{query}"

    if after:
        url += '&' + urllib.parse.urlencode({'after': after})

    page = 0
    kept = 0
    seen_urls = set()
    while url:
        if url in seen_urls:
            # Was a log line and a `break`, which handed back the pages read so
            # far AS IF THEY WERE ALL OF THEM. That is the whole silent-
            # truncation shape: a smaller, entirely plausible number, written to
            # the CSV and rendered on a dashboard with nothing marking it short.
            # A `next` that points at a URL already fetched is always a defect,
            # so there is no case where continuing with partial data is right.
            raise RuntimeError(
                f"Shotgun pagination loop on page {page + 1}: pagination.next "
                f"points back at a URL already fetched, after {kept} ticket(s). "
                f"Refusing to return a partial fetch as if it were complete."
            )
        seen_urls.add(url)

        page += 1
        payload = http_json(url)
        tickets = extract_shotgun_tickets(payload)
        log(f"   page {page}: {len(tickets)} tickets")
        for ticket in tickets:
            if probe is not None:
                record_cursor(probe, ticket)
            kept += 1
            yield ticket
        if probe is not None and isinstance(payload, dict):
            record_total(probe, payload)

        pagination = payload.get('pagination') if isinstance(payload, dict) else None
        next_url = (pagination or {}).get('next')
        url = next_url if next_url else None
        if url:
            time.sleep(SHOTGUN_PAGE_PACING_S)  # 100 req/min rate limit


def parse_shotgun_datetime(value):
    """Parse Shotgun 'ordered_at' ('2026-01-06 18:00:18.038852' or ISO) -> datetime."""
    if not value:
        return None
    text = str(value).strip().replace('/', '-')
    text = re.sub(r'([+-]\d{2}:?\d{2}|Z)$', '', text).strip()
    text = text.replace('T', ' ')
    for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def cents_to_units(value):
    """Shotgun/DICE money fields are integer cents -> currency units."""
    if value in (None, ''):
        return 0.0
    try:
        return round(float(value) / 100.0, 6)
    except (TypeError, ValueError):
        return 0.0


def process_shotgun_ticket(raw, event_days, organic_only=False):
    """Map one raw Shotgun ticket to a merged-CSV row, or None if it is skipped."""
    status = str(raw.get('ticket_status') or '').strip().lower()
    if status not in SHOTGUN_VALID_STATUSES:
        return None, 'status'

    channel = str(raw.get('deal_channel') or '').strip().lower()
    if organic_only and channel not in SHOTGUN_ORGANIC_CHANNELS:
        # Reported as 'channel:<value>' so the caller can show which channels
        # were dropped and flag any it does not recognise.
        return None, f'channel:{channel or "(none)"}'

    order_dt = parse_shotgun_datetime(raw.get('ordered_at'))
    if not order_dt:
        return None, 'date'

    sub_category = (raw.get('deal_sub_category') or '').strip()
    deal_title = (raw.get('deal_title') or '').strip()
    channel = str(raw.get('deal_channel') or '').strip().lower()

    price = cents_to_units(raw.get('deal_price'))
    # What the buyer actually paid: face value + both service fees.
    gross_price = round(
        cents_to_units(raw.get('deal_price'))
        + cents_to_units(raw.get('deal_service_fee'))
        + cents_to_units(raw.get('deal_user_service_fee')),
        6,
    )

    combined = f"{sub_category} {deal_title}".strip()
    tags = 'invitation' if channel == 'invitation' else ''
    ticket_type, access_level, attendance_days, product_name = classify_ticket(
        combined, price=gross_price, tags=tags, event_days=event_days
    )

    # Display name comes from the sub-category (cleaner than the combined string)
    if sub_category:
        product_name = sub_category
    product_name = normalize_product_name(product_name)

    # is_paid rule mirrors run.py's Shotgun path (line 977): net price drives it
    is_paid = 1 if price > 0 else 0

    return {
        'order_date': order_dt.date(),
        'order_datetime': order_dt.replace(microsecond=0),
        'ticket_type': ticket_type,
        'access_level': access_level,
        'attendance_days': attendance_days,
        'product_name': product_name,
        'platform': 'Shotgun',
        'price': price,
        'gross_price': gross_price,
        'quantity': 1,
        'is_paid': is_paid,
    }, None


def fetch_shotgun(event_config, token, organizer_id, account_name='?', organic_only=None,
                  after=None, since=None, probe=None):
    """Fetch + classify all Shotgun tickets for the event."""
    shotgun_event_id = event_config['shotgun_event_id']
    log(f"\n🔫 Shotgun: event {shotgun_event_id} (organizer {organizer_id})")

    # Dual-platform event -> drop Shotgun's imported-from-elsewhere channels,
    # because the DICE feed already supplies those same tickets. What makes an
    # event dual-platform is having a second source at all, so a manual DICE
    # export counts the same as a dice_mio_id; the caller decides.
    if organic_only is None:
        organic_only = bool(event_config.get('dice_mio_id'))
    if organic_only:
        log(f"   dual-platform: keeping only "
            f"channels {', '.join(SHOTGUN_ORGANIC_CHANNELS)}")
    else:
        log("   Shotgun-only event: keeping every deal_channel")

    tickets = []
    skipped = defaultdict(int)
    total_raw = 0
    for raw in fetch_shotgun_pages(token, organizer_id, shotgun_event_id,
                                   after=after, probe=probe):
        total_raw += 1
        # H9: a delta row whose ordered_at is at or before the stored maximum
        # cannot be a new sale - the cursor orders by ticket_updated_at, so it
        # is an existing ticket that changed (refund, cancellation, the resale
        # flip). Ties are the common case, because the stored maximum IS the
        # most recent sale, so this has to be <= and not <. Appending such a
        # row would book a refund as a fresh sale.
        if since is not None:
            ordered_at = parse_shotgun_datetime(raw.get('ordered_at'))
            if ordered_at is not None and ordered_at.replace(microsecond=0) <= since:
                if probe is not None:
                    probe['modified'] = probe.get('modified', 0) + 1
                continue
        row, reason = process_shotgun_ticket(raw, event_config['event_days'], organic_only)
        if row is None:
            skipped[reason] += 1
            continue
        tickets.append(row)

    log(f"   raw tickets: {total_raw}")
    log(f"   skipped (status not valid, incl. resold duplicates): {skipped['status']}")
    log(f"   skipped (unparseable ordered_at): {skipped['date']}")

    channel_skips = {k.split(':', 1)[1]: v for k, v in skipped.items() if k.startswith('channel:')}
    if channel_skips:
        total_dropped = sum(channel_skips.values())
        log(f"   skipped (non-organic channel): {total_dropped}")
        for channel, count in sorted(channel_skips.items(), key=lambda kv: -kv[1]):
            note = '' if channel in SHOTGUN_KNOWN_IMPORT_CHANNELS else '   <-- UNRECOGNISED'
            log(f"      {channel:<16} {count:>7}{note}")
        unknown = [c for c in channel_skips if c not in SHOTGUN_KNOWN_IMPORT_CHANNELS]
        if unknown:
            log("")
            log("   " + "!" * 66)
            log("   !! WARNING: dropped ticket(s) on unrecognised deal_channel(s): "
                + ', '.join(sorted(unknown)))
            log("   !! If any of these are Shotgun's own sales they are being lost.")
            log("   !! Check with: python scripts/probe_shotgun_channels.py <event_id>")
            log("   " + "!" * 66)
    log(f"   ✅ Shotgun tickets kept: {len(tickets)}")

    if not tickets:
        # A valid token against the wrong organizer_id returns an empty set
        # rather than an error, so zero here usually means a bad account
        # mapping - not "no sales". Never let that pass quietly.
        log("")
        log("   " + "!" * 66)
        log(f"   !! WARNING: event {shotgun_event_id} is configured for Shotgun but")
        log(f"   !! returned 0 tickets under the '{account_name}' account "
            f"(organizer {organizer_id}).")
        log("   !! Check the account mapping before trusting this dashboard:")
        log("   !!   python scripts/probe_shotgun_account.py "
            f"{shotgun_event_id}")
        log("   " + "!" * 66)
        log("")

    return tickets


# ============================================================================
# DICE
# ============================================================================

def dice_relay_id(numeric_id):
    """DICE GraphQL uses Base64 Relay IDs: 600413 -> 'RXZlbnQ6NjAwNDEz'."""
    return base64.b64encode(f'Event:{numeric_id}'.encode()).decode()


def dice_graphql(token, query, variables):
    """POST a GraphQL query and return the `data` object, raising on errors."""
    payload = http_json(
        DICE_API,
        method='POST',
        headers={'Authorization': f'Bearer {token}'},
        payload={'query': query, 'variables': variables},
    )
    if payload.get('errors'):
        messages = '; '.join(str(e.get('message', e)) for e in payload['errors'])
        raise RuntimeError(f"DICE GraphQL error: {messages}")
    return payload.get('data') or {}


def parse_dice_datetime(value):
    """Parse DICE 'claimedAt' (ISO 8601, possibly with tz) -> naive datetime."""
    if not value:
        return None
    text = str(value).strip()
    text = text.replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        pass
    cleaned = re.sub(r'([+-]\d{2}:?\d{2})$', '', text).replace('T', ' ').strip()
    for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def process_dice_ticket(node, order_dt, event_days):
    """Map one DICE ticket node to a merged-CSV row, using its order's purchase date."""
    ticket_type_obj = node.get('ticketType') or {}
    name = (ticket_type_obj.get('name') or '').strip()

    price = cents_to_units(node.get('fullPrice'))
    gross_price = cents_to_units(node.get('total'))

    ticket_type, access_level, attendance_days, product_name = classify_ticket(
        name, price=gross_price, event_days=event_days
    )
    if name:
        product_name = name
    product_name = normalize_product_name(product_name)

    return {
        'order_date': order_dt.date(),
        'order_datetime': order_dt.replace(microsecond=0),
        'ticket_type': ticket_type,
        'access_level': access_level,
        'attendance_days': attendance_days,
        'product_name': product_name,
        'platform': 'DICE',
        'price': price,
        'gross_price': gross_price,
        'quantity': 1,
        # is_paid rule mirrors run.py's DICE path (line 858): access level drives it
        'is_paid': 0 if access_level in ('invitation', 'jeu_concours') else 1,
    }, None


def fetch_dice(event_config, token):
    """Fetch + classify all DICE tickets for the event, one row per ticket."""
    numeric_id = event_config['dice_mio_id']
    event_id = dice_relay_id(numeric_id)
    log(f"\n🎲 DICE: event {numeric_id} (relay id {event_id})")

    tickets = []
    skipped = defaultdict(int)
    total_orders = 0
    total_raw = 0
    cursor = None
    page = 0
    reported_total = None

    while True:
        page += 1
        data = dice_graphql(token, DICE_ORDERS_QUERY, {
            'eventId': event_id,
            'first': DICE_PAGE_SIZE,
            'after': cursor,
        })
        connection = ((data.get('viewer') or {}).get('orders') or {})
        if reported_total is None:
            reported_total = connection.get('totalCount')
            log(f"   orders totalCount: {reported_total}")

        edges = connection.get('edges') or []
        page_tickets = 0
        for edge in edges:
            order_node = (edge or {}).get('node') or {}
            total_orders += 1

            order_dt = parse_dice_datetime(order_node.get('purchasedAt'))
            order_tickets = order_node.get('tickets') or []
            if not order_tickets:
                skipped['empty_order'] += 1
                continue
            if not order_dt:
                total_raw += len(order_tickets)
                skipped['date'] += len(order_tickets)
                continue

            for ticket_node in order_tickets:
                total_raw += 1
                row, reason = process_dice_ticket(
                    ticket_node or {}, order_dt, event_config['event_days']
                )
                if row is None:
                    skipped[reason] += 1
                    continue
                tickets.append(row)
                page_tickets += 1

        log(f"   page {page}: {len(edges)} orders -> {page_tickets} tickets")

        page_info = connection.get('pageInfo') or {}
        if not page_info.get('hasNextPage'):
            break
        next_cursor = page_info.get('endCursor')
        if not next_cursor or next_cursor == cursor:
            # Same correction as the Shotgun loop guard: hasNextPage says there
            # is more and the cursor says we cannot reach it, so whatever we
            # have is short by an unknown amount. Warning-and-continue wrote
            # that unknown amount into the CSV as a fact.
            raise RuntimeError(
                f"DICE pagination stalled after page {page}: hasNextPage is "
                f"true but endCursor is {next_cursor!r}, so the next page is "
                f"unreachable. {total_orders} order(s) read so far. Refusing to "
                f"return a partial fetch as if it were complete."
            )
        cursor = next_cursor

    log(f"   orders processed: {total_orders}")

    # PAGINATION COMPLETENESS. The query already asks for totalCount and this
    # already read it; until now it was logged and never compared, so a fetch
    # that stopped early produced a smaller, entirely plausible number and
    # nothing in the repo could contradict it.
    #
    # ONE-SIDED, DELIBERATELY. Only `processed < reported` is a defect. The
    # reverse is a race, not a truncation: totalCount is read from page 1 and
    # these fetches take ~8s over 17 pages, so an order placed mid-fetch lands
    # in `edges` without being in the total. That direction means we have
    # everything the server had plus one, which is not a hole. Asserting
    # equality would fail a COMPLETE fetch on a busy event - a false defect,
    # and the failure mode that gets acted on because it looks like a finding.
    if reported_total is None:
        log("   ⚠ orders totalCount absent - completeness unverifiable this run")
    elif total_orders < reported_total:
        raise RuntimeError(
            f"DICE fetch is short: processed {total_orders} order(s) but the "
            f"server reported totalCount={reported_total} on page 1, over "
            f"{page} page(s). {reported_total - total_orders} order(s) were "
            f"never read. Refusing to write a truncated file."
        )

    log(f"   raw tickets: {total_raw}")
    log(f"   skipped (order has no tickets): {skipped['empty_order']}")
    log(f"   skipped (no purchasedAt on order): {skipped['date']}")
    log(f"   ✅ DICE tickets kept: {len(tickets)}")
    return tickets


# ============================================================================
# MERGE + WRITE
# ============================================================================

def parse_attendance_days(raw):
    """'['vendredi']' -> ['vendredi']; '' -> None (classify_ticket's own shape)."""
    text = (raw or '').strip()
    if not text:
        return None
    try:
        value = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return None
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return None


def load_manual_dice_tickets(path):
    """
    Read a hand-exported merged CSV back into the same in-memory rows the API
    path produces, so the two can simply be concatenated.

    The file is already the 11-column merged format, produced with this module's
    classify_ticket - so the columns are trusted as-is. Only two things are
    reconstructed: the Python types the CSV flattened to text (dates, the
    attendance_days list, numbers), and product_name, which is normalised here
    because the API path normalises and an un-normalised copy would split one
    product into two rows in the dashboard breakdown.
    """
    path = Path(path)
    if not path.exists():
        raise RuntimeError(
            f"manual DICE CSV not found: {path}\n"
            f"Either commit the export at that path or drop the event from "
            f"MANUAL_DICE_CSVS."
        )

    log(f"\n📄 Manual DICE export: {path}")
    tickets = []
    skipped = defaultdict(int)
    with open(path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        missing_cols = [c for c in CSV_FIELDNAMES if c not in (reader.fieldnames or [])]
        if missing_cols:
            raise RuntimeError(
                f"{path} is missing column(s): {', '.join(missing_cols)}\n"
                f"Expected the 11-column merged format: {', '.join(CSV_FIELDNAMES)}"
            )
        for row in reader:
            order_dt = parse_dice_datetime(row.get('order_datetime'))
            if order_dt is None:
                skipped['date'] += 1
                continue
            try:
                price = float(row.get('price') or 0)
                gross_price = float(row.get('gross_price') or 0)
                quantity = int(float(row.get('quantity') or 1))
                is_paid = int(float(row.get('is_paid') or 0))
            except ValueError:
                skipped['number'] += 1
                continue
            tickets.append({
                'order_date': order_dt.date(),
                'order_datetime': order_dt.replace(microsecond=0),
                'ticket_type': (row.get('ticket_type') or '').strip(),
                'access_level': (row.get('access_level') or '').strip(),
                'attendance_days': parse_attendance_days(row.get('attendance_days')),
                'product_name': normalize_product_name(row.get('product_name') or ''),
                'platform': (row.get('platform') or 'DICE').strip() or 'DICE',
                'price': price,
                'gross_price': gross_price,
                'quantity': quantity,
                'is_paid': is_paid,
            })

    if skipped['date']:
        log(f"   skipped (unparseable order_datetime): {skipped['date']}")
    if skipped['number']:
        log(f"   skipped (unparseable price/quantity): {skipped['number']}")
    if not tickets:
        raise RuntimeError(
            f"{path} yielded 0 usable rows - refusing to build a dashboard that "
            f"silently drops this event's DICE sales."
        )
    log(f"   ✅ manual DICE tickets kept: {len(tickets)}")
    return tickets


def merge_tickets(dice_tickets, shotgun_tickets):
    """Merge both platforms into one list sorted by purchase date."""
    all_tickets = dice_tickets + shotgun_tickets
    all_tickets.sort(key=lambda t: (t['order_date'], t['order_datetime']))
    return all_tickets


def assert_merged_schema(tickets):
    """
    Fail loudly if a row carries anything but the 11 aggregate columns.

    These CSVs are committed to a public repo. Every upstream field is mapped
    explicitly today, so a new key here means Shotgun or DICE started returning
    something we have not looked at - and the Shotgun ticket payload is full of
    contact_email, contact_phone, contact_first_name and friends. Cheap to
    check, and the failure mode it guards against is publishing personal data.
    """
    expected = set(CSV_FIELDNAMES)
    for i, row in enumerate(tickets):
        keys = set(row)
        if keys != expected:
            extra = sorted(keys - expected)
            missing = sorted(expected - keys)
            raise RuntimeError(
                f"merged row {i} does not match the 11-column schema"
                + (f"; unexpected column(s): {extra}" if extra else '')
                + (f"; missing column(s): {missing}" if missing else '')
                + "\nRefusing to write. These CSVs are public - an unexpected "
                  "column may be personal data."
            )


def save_merged_csv(tickets, output_path):
    """Write the 11-column merged CSV exactly as run.py's save_merged_csv does."""
    assert_merged_schema(tickets)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(tickets)
    return output_path


def print_summary(tickets, event_config, output_path):
    """Print the fetch summary: counts, paid/free split, revenue, per-day totals."""
    shotgun = [t for t in tickets if t['platform'] == 'Shotgun']
    dice = [t for t in tickets if t['platform'] == 'DICE']
    paid = [t for t in tickets if t['is_paid'] == 1]
    free = [t for t in tickets if t['is_paid'] == 0]
    currency = event_config.get('currency') or 'EUR'

    log("\n" + "=" * 62)
    log(f"SUMMARY - {event_config['event_id']} ({event_config.get('event_name', '')})")
    log("=" * 62)
    log(f"Shotgun tickets : {len(shotgun)}")
    log(f"DICE tickets    : {len(dice)}")
    log(f"TOTAL tickets   : {len(tickets)}")
    log(f"Paid / Free     : {len(paid)} / {len(free)}")
    log(f"Gross revenue   : {sum(t['gross_price'] for t in paid):,.2f} {currency}")
    log(f"Net revenue     : {sum(t['price'] for t in paid):,.2f} {currency}")

    day_names = event_config['day_names']
    if day_names:
        per_day = {dn: 0 for dn in day_names}
        for t in tickets:
            presence = resolve_attendance(t['ticket_type'], t['attendance_days'], day_names)
            for dn, present in presence.items():
                per_day[dn] += present
        log("\nAttendance by day (all tickets):")
        for dn in day_names:
            log(f"   {dn:12} {per_day[dn]:6}")

    breakdown = defaultdict(lambda: {'DICE': 0, 'Shotgun': 0})
    for t in tickets:
        breakdown[(t['ticket_type'], t['access_level'])][t['platform']] += 1
    log("\nBreakdown by ticket type / access level:")
    for key in sorted(breakdown.keys()):
        d, s = breakdown[key]['DICE'], breakdown[key]['Shotgun']
        log(f"   {key[0]:12} / {key[1]:15} → DICE: {d:5} | Shotgun: {s:5} | Total: {d + s:5}")

    log(f"\n✅ Wrote {len(tickets)} tickets to {output_path}")


# ============================================================================
# MAIN
# ============================================================================

def parse_args(argv):
    parser = argparse.ArgumentParser(description='Fetch Shotgun + DICE tickets into a merged CSV.')
    parser.add_argument('--event', default='rennes_2026', help='event_id from event_config.csv')
    parser.add_argument('--config', default='event_config.csv', help='path to event_config.csv')
    parser.add_argument('--out', default=None, help='output CSV path (default api_output/{event}_merged.csv)')
    parser.add_argument('--skip-shotgun', action='store_true', help='do not fetch Shotgun')
    parser.add_argument('--skip-dice', action='store_true', help='do not fetch DICE')
    parser.add_argument('--allow-dice-shrink', action='store_true',
                        help='publish even when an API DICE fetch returns fewer '
                             'tickets than the manual export it just retired')
    # NOT used by the daily workflow, deliberately - see the note in
    # HANDOFF.md. It works and is verified; it is simply not worth the risk
    # for the current volumes. Do not assume it is broken because nothing
    # calls it.
    parser.add_argument('--incremental', action='store_true',
                        help='resume Shotgun from the stored cursor; DICE is always full '
                             '(built and verified, but the daily job runs full fetches)')
    parser.add_argument('--full', action='store_true',
                        help='force a full fetch even if incremental state exists')
    parser.add_argument('--state-csv', default=None,
                        help='stored merged CSV to resume from (default data/{event}_merged.csv)')
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    event_config = load_event_config(args.config, args.event)
    output_path = Path(args.out) if args.out else Path('api_output') / f"{args.event}_merged.csv"

    log(f"Event      : {event_config['event_id']} - {event_config['event_name']}")
    log(f"Days       : " + ', '.join(
        f"{d['day_name']} {d['day_date']}" for d in event_config['event_days']
    ))
    log(f"Shotgun id : {event_config['shotgun_event_id'] or '(none)'}")
    log(f"DICE id    : {event_config['dice_mio_id'] or '(none)'}")

    account, shotgun_token, organizer_id = resolve_shotgun_account(args.event)
    dice_token = os.environ.get('DICE_TOKEN', '').strip()

    # A manual export only stands in for an API feed we do not have. Once the
    # event has a dice_mio_id the API wins and the file is left alone, so the
    # two can never both be counted.
    manual_dice_path = MANUAL_DICE_CSVS.get(args.event)
    retired_manual_rows = None
    if manual_dice_path and event_config['dice_mio_id']:
        log(f"\n📄 Manual DICE export for {args.event} superseded by "
            f"dice_mio_id {event_config['dice_mio_id']} - ignoring "
            f"{manual_dice_path}")
        # The handover is the dangerous moment. Adding a dice_mio_id retires a
        # committed export in favour of an API call, and if that token cannot
        # reach the event the API returns HTTP 200 with an empty set - valid
        # token, wrong account, indistinguishable from "no sales". Genève is
        # 2,912 tickets and ~186k EUR, more than its Shotgun side, and M1 would
        # not catch it: the CSV changing is exactly what M1 publishes.
        #
        # So count what is being retired and hold the replacement to it below.
        # A non-zero check is not enough - partial access returning three
        # tickets would pass it while losing 2,909.
        try:
            with open(manual_dice_path, newline='', encoding='utf-8-sig') as f:
                retired_manual_rows = sum(1 for _ in csv.DictReader(f))
            log(f"   ⚠ {retired_manual_rows} manual row(s) retired - the API "
                f"fetch must return at least as many")
        except OSError as exc:
            log(f"   ⚠ could not read the retired export to size it: {exc}")
        manual_dice_path = None
    log(f"Manual DICE: {manual_dice_path or '(none)'}")

    # ---- incremental resume state -------------------------------------
    # Shotgun only, and the reason is cost, not capability. Shotgun is 20k+
    # tickets at ~0.8s/page; a DICE event is 2-5k and completes in seconds, so
    # there is nothing to save. DICE *can* be filtered server-side -
    # OrderWhereInput carries purchasedAt alongside eventId and id (measured
    # 2026-08-08, run 31235118312) - so a DICE incremental is buildable
    # whenever the volume justifies it. It does not today.
    stored_shotgun = []
    resume_after = None
    resume_since = None
    probe = {}
    if args.incremental and not args.full and not args.skip_shotgun:
        state_csv = Path(args.state_csv) if args.state_csv else STATE_DIR / f"{args.event}_merged.csv"
        stored = load_stored_rows(state_csv)
        state = load_state(args.event)
        why = None
        if stored is None:
            why = f"no usable stored CSV at {state_csv}"
        elif state is None:
            why = "no stored cursor"
        elif str(state.get('shotgun_event_id') or '') != str(event_config['shotgun_event_id'] or ''):
            why = (f"cursor was written for Shotgun event "
                   f"{state.get('shotgun_event_id')}, config now says "
                   f"{event_config['shotgun_event_id']}")
        if why:
            log(f"\n↻ incremental unavailable ({why}) - full fetch")
        else:
            # H10: only Shotgun rows carry forward. DICE is refetched whole
            # every run, so keeping its stored rows would double the DICE side
            # on every incremental pass.
            stored_shotgun = [t for t in stored if t['platform'] == 'Shotgun']
            resume_after = state['cursor']
            resume_since = parse_shotgun_datetime(state.get('max_ordered_at'))
            log(f"\n↻ incremental: {len(stored_shotgun)} stored Shotgun rows, "
                f"resuming after {redact(resume_after)}")

    shotgun_tickets = []
    dice_tickets = []
    missing = []

    if args.skip_shotgun or not event_config['shotgun_event_id']:
        log("\n🔫 Shotgun: skipped")
    elif not shotgun_token:
        missing.append(SHOTGUN_ACCOUNTS[account]['token_env'])
    else:
        log(f"\nShotgun account: {account}")
        # A manual DICE export makes this event dual-platform just as a
        # dice_mio_id would, so the same import-channel filter has to apply.
        organic_only = bool(event_config['dice_mio_id']) or bool(manual_dice_path)
        delta = fetch_shotgun(
            event_config, shotgun_token, organizer_id, account, organic_only=organic_only,
            after=resume_after, since=resume_since, probe=probe,
        )
        if resume_after and probe.get('modified'):
            # H3 trip. A modification cannot be applied to an append-only file,
            # so refetch this event whole. Machine-greppable for H8.
            log(f"::warning::H3-TRIP event={args.event} reason=modified-rows "
                f"count={probe['modified']} stored={len(stored_shotgun)} "
                f"delta={len(delta)}")
            probe = {}
            shotgun_tickets = fetch_shotgun(
                event_config, shotgun_token, organizer_id, account,
                organic_only=organic_only, probe=probe,
            )
            stored_shotgun = []
        elif resume_after and probe.get('total') is not None and \
                probe['total'] != len(stored_shotgun) + len(delta):
            log(f"::warning::H3-TRIP event={args.event} reason=total-mismatch "
                f"reported={probe['total']} "
                f"expected={len(stored_shotgun) + len(delta)}")
            probe = {}
            shotgun_tickets = fetch_shotgun(
                event_config, shotgun_token, organizer_id, account,
                organic_only=organic_only, probe=probe,
            )
            stored_shotgun = []
        else:
            shotgun_tickets = stored_shotgun + delta
            if resume_after:
                log(f"   ↻ appended {len(delta)} new Shotgun row(s) "
                    f"to {len(stored_shotgun)} stored")

    if args.skip_dice or not event_config['dice_mio_id']:
        log("\n🎲 DICE: skipped")
    elif not dice_token:
        missing.append('DICE_TOKEN')
    else:
        dice_tickets = fetch_dice(event_config, dice_token)

    if missing:
        raise SystemExit(
            "Missing required secret(s) in the environment: " + ', '.join(missing) +
            "\nSet them as env vars (GitHub Actions: repository secrets) and re-run."
        )

    if manual_dice_path and not args.skip_dice:
        dice_tickets = dice_tickets + load_manual_dice_tickets(manual_dice_path)

    # The other half of the handover guard. Refuse to publish a DICE side
    # smaller than the export it just replaced.
    if retired_manual_rows is not None and not args.skip_dice:
        if len(dice_tickets) < retired_manual_rows and not args.allow_dice_shrink:
            raise SystemExit(
                f"REFUSING TO PUBLISH: the manual DICE export for {args.event} "
                f"was retired in favour of dice_mio_id "
                f"{event_config['dice_mio_id']}, but the API returned "
                f"{len(dice_tickets)} ticket(s) against {retired_manual_rows} "
                f"in the file it replaced.\n"
                f"\n"
                f"A valid token on the wrong account returns HTTP 200 and an "
                f"empty set, so this looks identical to 'no sales'. Either the "
                f"token cannot reach this event yet - in which case remove "
                f"dice_mio_id from event_config.csv until it can - or the drop "
                f"is real, in which case re-run with --allow-dice-shrink.\n"
                f"\n"
                f"This guard retires itself: once the API is authoritative, "
                f"drop {args.event} from MANUAL_DICE_CSVS and it stops firing."
            )
        log(f"\n✅ DICE handover: {len(dice_tickets)} API row(s) against "
            f"{retired_manual_rows} retired manual row(s)")

    tickets = merge_tickets(dice_tickets, shotgun_tickets)

    # H10 guard. DICE is replaced wholesale each run, never appended, so the
    # merged file must carry exactly this run's DICE rows. Anything larger
    # means stored DICE rows survived and the platform is doubling.
    dice_in_output = sum(1 for t in tickets if t['platform'] == 'DICE')
    if dice_in_output != len(dice_tickets):
        raise RuntimeError(
            f"DICE row count in the merged output ({dice_in_output}) does not "
            f"match this run's DICE fetch ({len(dice_tickets)}) - stored DICE "
            f"rows leaked through. Refusing to write a doubled file."
        )

    save_merged_csv(tickets, output_path)

    # Record where the next incremental resumes from. Only after a Shotgun
    # fetch that actually paged - otherwise the previous cursor stands.
    if probe.get('cursor') and not args.skip_shotgun and event_config['shotgun_event_id']:
        sg = [t for t in tickets if t['platform'] == 'Shotgun']
        max_ordered = max((t['order_datetime'] for t in sg), default=None)
        save_state(args.event, probe['cursor'], len(sg),
                   max_ordered.strftime('%Y-%m-%d %H:%M:%S') if max_ordered else None,
                   event_config['shotgun_event_id'])
        log(f"   ↻ state saved: {len(sg)} Shotgun rows, "
            f"total field {'found via ' + probe['total_key'] if probe.get('total') else 'not exposed'}")
    print_summary(tickets, event_config, output_path)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except RuntimeError as exc:
        # Network / API failures: report the cause, not a stack trace
        sys.exit(f"❌ {exc}")
