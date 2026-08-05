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

# Shotgun serves 100 tickets/page and allows 100 requests/minute -> pace at 0.8s
SHOTGUN_PAGE_PACING_S = 0.8
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
        'events': ['bordeaux_oct_2026', 'bordeaux_2025', 'halloween_2025'],
    },
}

DEFAULT_SHOTGUN_ACCOUNT = 'episode'

CSV_FIELDNAMES = [
    'order_date', 'order_datetime', 'ticket_type', 'access_level', 'attendance_days',
    'product_name', 'platform', 'price', 'gross_price', 'quantity', 'is_paid',
]

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
    for attempt in range(HTTP_RETRIES):
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            detail = e.read().decode('utf-8', 'replace')[:500]
            last_error = f"HTTP {e.code} {e.reason}: {detail}"
            # 4xx other than rate-limiting will not fix themselves
            if e.code not in (429, 500, 502, 503, 504):
                raise RuntimeError(f"{method} {redact(url)} failed - {last_error}")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_error = f"{type(e).__name__}: {e}"

        if attempt < HTTP_RETRIES - 1:
            backoff = 2 ** (attempt + 1)
            log(f"   ⚠ request failed ({last_error}) - retrying in {backoff}s")
            time.sleep(backoff)

    raise RuntimeError(f"{method} {redact(url)} failed after {HTTP_RETRIES} attempts - {last_error}")


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


def fetch_shotgun_pages(token, organizer_id, shotgun_event_id):
    """Yield raw Shotgun ticket dicts, following pagination.next until exhausted."""
    query = urllib.parse.urlencode({
        'token': token,
        'organizer_id': organizer_id,
        'event_id': shotgun_event_id,
    })
    url = f"{SHOTGUN_API}?{query}"

    page = 0
    seen_urls = set()
    while url:
        if url in seen_urls:
            log("   ⚠ pagination loop detected - stopping")
            break
        seen_urls.add(url)

        page += 1
        payload = http_json(url)
        tickets = extract_shotgun_tickets(payload)
        log(f"   page {page}: {len(tickets)} tickets")
        for ticket in tickets:
            yield ticket

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


def fetch_shotgun(event_config, token, organizer_id, account_name='?'):
    """Fetch + classify all Shotgun tickets for the event."""
    shotgun_event_id = event_config['shotgun_event_id']
    log(f"\n🔫 Shotgun: event {shotgun_event_id} (organizer {organizer_id})")

    # Dual-platform event -> drop Shotgun's imported-from-elsewhere channels,
    # because the DICE feed already supplies those same tickets.
    organic_only = bool(event_config.get('dice_mio_id'))
    if organic_only:
        log(f"   dual-platform (dice {event_config['dice_mio_id']}): keeping only "
            f"channels {', '.join(SHOTGUN_ORGANIC_CHANNELS)}")
    else:
        log("   Shotgun-only event: keeping every deal_channel")

    tickets = []
    skipped = defaultdict(int)
    total_raw = 0
    for raw in fetch_shotgun_pages(token, organizer_id, shotgun_event_id):
        total_raw += 1
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
            log("   ⚠ pagination stalled (no new cursor) - stopping")
            break
        cursor = next_cursor

    log(f"   orders processed: {total_orders}")
    log(f"   raw tickets: {total_raw}")
    log(f"   skipped (order has no tickets): {skipped['empty_order']}")
    log(f"   skipped (no purchasedAt on order): {skipped['date']}")
    log(f"   ✅ DICE tickets kept: {len(tickets)}")
    return tickets


# ============================================================================
# MERGE + WRITE
# ============================================================================

def merge_tickets(dice_tickets, shotgun_tickets):
    """Merge both platforms into one list sorted by purchase date."""
    all_tickets = dice_tickets + shotgun_tickets
    all_tickets.sort(key=lambda t: (t['order_date'], t['order_datetime']))
    return all_tickets


def save_merged_csv(tickets, output_path):
    """Write the 11-column merged CSV exactly as run.py's save_merged_csv does."""
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

    shotgun_tickets = []
    dice_tickets = []
    missing = []

    if args.skip_shotgun or not event_config['shotgun_event_id']:
        log("\n🔫 Shotgun: skipped")
    elif not shotgun_token:
        missing.append(SHOTGUN_ACCOUNTS[account]['token_env'])
    else:
        log(f"\nShotgun account: {account}")
        shotgun_tickets = fetch_shotgun(event_config, shotgun_token, organizer_id, account)

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

    tickets = merge_tickets(dice_tickets, shotgun_tickets)
    save_merged_csv(tickets, output_path)
    print_summary(tickets, event_config, output_path)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except RuntimeError as exc:
        # Network / API failures: report the cause, not a stack trace
        sys.exit(f"❌ {exc}")
