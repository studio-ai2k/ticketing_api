#!/usr/bin/env python3
"""
FESTIFLOW - Dashboard Builder v5.0
===================================
Single-script festival dashboard generator.
Reads raw DICE + Shotgun exports, merges them, calculates metrics,
and generates a complete HTML dashboard.

USAGE:
    python run.py                          # Auto-detect files in data/raw/
    python run.py --event bordeaux_2026    # Force specific event from config

OUTPUT:
    data/output/dashboard_FINAL.html

ENVIRONMENT VARIABLES (optional - used by Railway/SaaS deployment):
    FESTIFLOW_RAW_DIR     Override input directory (temp dir per request)
    FESTIFLOW_OUTPUT_DIR  Override output directory (temp dir per request)

CHANGELOG:
    v5.0 (2026-03-13) - Railway/SaaS compatibility
        - RAW_DIR and OUTPUT_DIR now respect FESTIFLOW_RAW_DIR /
          FESTIFLOW_OUTPUT_DIR env vars, enabling concurrent Railway requests
          without file collisions
        - parse_datetime_dice() - new function, extracts full datetime
          from DICE 'Purchase date' field (was date-only before)
        - DICE ticket dicts now include 'order_datetime' field
        - load_ticket_data() - order_datetime preserved through processing
          pipeline and correctly parsed back from CSV string format
        - save_merged_csv() - order_datetime added to fieldnames
        - generation_time placeholder set at final file-write moment
          (not mid-pipeline) so 'Données uploadées' timestamp is accurate
        - dashboard_template.html header updated:
          '🎟 Dernier billet vendu · {LAST_TICKET_TIME}'  (actual last tx)
          '📤 Données uploadées · {DATA_TIME}'            (file-write time)

    v4.5 (2026-03-13) - timestamp fixes (intermediate, now superseded by v5.0)
    v4.4 (2026-03-12) - dual-counting system (paid vs all tickets)
    v4.3 (2026-03-xx) - initial stable release

AUTHORS: Leo & Claude
DATE: March 2026
"""

import csv
import sys
import os
import re
import zipfile
import shutil
import tempfile
import argparse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from collections import defaultdict
from pathlib import Path


# ============================================================================
# CONSTANTS
# ============================================================================

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
# Allow Railway (or any caller) to inject temp dirs via env vars
RAW_DIR    = Path(os.environ["FESTIFLOW_RAW_DIR"])    if "FESTIFLOW_RAW_DIR"    in os.environ else DATA_DIR / "raw"
OUTPUT_DIR = Path(os.environ["FESTIFLOW_OUTPUT_DIR"]) if "FESTIFLOW_OUTPUT_DIR" in os.environ else DATA_DIR / "output"
HISTORICAL_DIR = Path(os.environ["FESTIFLOW_HISTORICAL_DIR"]) if "FESTIFLOW_HISTORICAL_DIR" in os.environ else DATA_DIR / "historical"
MERGED_DIR = DATA_DIR / "merged"
CONFIG_PATH = BASE_DIR / "event_config.csv"
TEMPLATE_PATH = BASE_DIR / "dashboard_template.html"

# French month names (single source of truth)
MONTHS_FR_FULL = {
    1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
    5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
    9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'
}
MONTHS_FR_ABBR = {
    1: 'Jan', 2: 'Fév', 3: 'Mar', 4: 'Avr', 5: 'Mai', 6: 'Juin',
    7: 'Juil', 8: 'Aoû', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Déc'
}
MONTHS_FR_TO_NUM = {v.lower(): k for k, v in MONTHS_FR_FULL.items()}

DAYS_FR = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']

# Day name display mapping
DAY_DISPLAY_NAMES = {
    'jeudi': 'Jeudi',
    'vendredi': 'Vendredi',
    'samedi': 'Samedi',
    'dimanche': 'Dimanche',
}

# Day colors for dashboard cards and sections
DAY_COLORS = {
    'jeudi': {'gradient': '#FF8800, #FFAA44', 'bg': 'rgba(255, 136, 0, 0.1)', 'border': '#FF8800'},
    'vendredi': {'gradient': '#FF0066, #FF6699', 'bg': 'rgba(255, 0, 102, 0.1)', 'border': '#FF0066'},
    'samedi': {'gradient': '#9900FF, #CC66FF', 'bg': 'rgba(153, 0, 255, 0.1)', 'border': '#9900FF'},
    'dimanche': {'gradient': '#00AAFF, #66CCFF', 'bg': 'rgba(0, 170, 255, 0.1)', 'border': '#00AAFF'},
}


# ============================================================================
# PRINT UTILITIES (single copy)
# ============================================================================

def print_header(text):
    print(f"\n{'='*80}\n  {text}\n{'='*80}\n")

def print_success(text):
    print(f"✅ {text}")

def print_warning(text):
    print(f"⚠️  {text}")

def print_error(text):
    print(f"❌ {text}")

def print_info(text):
    print(f"ℹ️  {text}")


# ============================================================================
# FORMAT UTILITIES (single copy)
# ============================================================================

def fmt_num(num):
    """Format number with thousands separator: 24294 -> 24,294"""
    return f"{int(num):,}"

def fmt_currency(amount):
    """Format currency: 1593661 -> €1.59M or €1,593,661"""
    if amount >= 1000000:
        return f"€{amount/1000000:.2f}M"
    elif amount >= 1000:
        return f"€{amount/1000:.0f}k"
    else:
        return f"€{amount:.2f}"

def fmt_pct(value, decimals=1):
    """Format percentage: 0.677 -> 67.7%"""
    return f"{value*100:.{decimals}f}%"

def fmt_date_fr(date):
    """Format date in French: 2026-02-20 -> '20 Février 2026'"""
    return f"{date.day} {MONTHS_FR_FULL[date.month]} {date.year}"

def fmt_date_fr_short(date):
    """Short French date: 2026-02-20 -> '20 Février'"""
    return f"{date.day} {MONTHS_FR_FULL[date.month]}"

def fmt_date_fr_weekday(date):
    """Weekday + date: 'Ven 20 Fév'"""
    return f"{DAYS_FR[date.weekday()]} {date.day} {MONTHS_FR_ABBR[date.month]}"

def clean_price(price_str):
    """Clean price string to float: '€89.00' -> 89.0"""
    if not price_str or price_str.strip() == '':
        return 0.0
    cleaned = price_str.strip().replace('€', '').replace('$', '').replace(' ', '').replace(',', '')
    try:
        return float(cleaned)
    except ValueError:
        print_warning(f"Could not parse price: '{price_str}', defaulting to 0.0")
        return 0.0


# ============================================================================
# EVENT CONFIG LOADING
# ============================================================================

def load_event_config(config_path, event_id=None):
    """
    Load event configuration from CSV.
    
    Args:
        config_path: Path to event_config.csv
        event_id: Specific event to load (e.g., 'bordeaux_2026'). 
                  If None, returns all active events.
    
    Returns:
        dict with event metadata:
        {
            'event_id': 'bordeaux_2026',
            'event_name': 'Sonora Bordeaux 2026',
            'brand': 'ML x Sonora',
            'venue': 'Parc Expo Bordeaux',
            'city': 'Bordeaux',
            'currency': 'EUR',
            'shotgun_event_id': '505434',
            'dice_mio_id': '540197',
            'compare_to': 'bordeaux_2025',
            'days': [
                {'day_number': 1, 'day_name': 'Jeudi', 'day_date': date(2026,6,11), 'day_capacity': 18000},
                {'day_number': 2, 'day_name': 'Vendredi', 'day_date': date(2026,6,12), 'day_capacity': 18000},
                {'day_number': 3, 'day_name': 'Samedi', 'day_date': date(2026,6,13), 'day_capacity': 18000},
            ],
            'total_capacity': 54000,
            'event_date_first': date(2026,6,11),
            'event_date_last': date(2026,6,13),
            'status': 'active'
        }
    """
    events = {}
    
    with open(config_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            eid = row['event_id']
            
            if eid not in events:
                events[eid] = {
                    'event_id': eid,
                    'event_name': row['event_name'],
                    'brand': row['brand'],
                    'venue': row['venue'],
                    'city': row['city'],
                    'currency': row.get('currency', 'EUR'),
                    'shotgun_event_id': row.get('shotgun_event_id', ''),
                    'dice_mio_id': row.get('dice_mio_id', ''),
                    'compare_to': row.get('compare_to', ''),
                    'comparison_mode': row.get('comparison_mode', '').strip() or 'j_minus',
                    'merge_into': row.get('merge_into', ''),
                    'status': row.get('status', 'archive'),
                    'login_password': row.get('login_password', ''),
                    'login_bg_image': row.get('login_bg_image', 'upload.JPG'),
                    'poster_url': row.get('poster_url', ''),
                    'dice_url': row.get('dice_url', ''),
                    'dice_public_id': row.get('dice_public_id', ''),
                    'shotgun_url': row.get('shotgun_url', ''),
                    'output_filename': row.get('output_filename', ''),
                    'notes': row.get('notes', ''),
                    'days': []
                }
            
            # Parse day info
            day_date_str = row.get('day_date', '')
            day_date = datetime.strptime(day_date_str, '%Y-%m-%d').date() if day_date_str else None
            day_capacity = int(row.get('day_capacity', 0)) if row.get('day_capacity', '').strip() else 0
            
            events[eid]['days'].append({
                'day_number': int(row.get('day_number', 1)),
                'day_name': row.get('day_name', ''),
                'day_date': day_date,
                'day_capacity': day_capacity,
            })
    
    # Calculate derived fields
    for eid, event in events.items():
        event['days'].sort(key=lambda d: d['day_number'])
        
        dates = [d['day_date'] for d in event['days'] if d['day_date']]
        event['event_date_first'] = min(dates) if dates else None
        event['event_date_last'] = max(dates) if dates else None
        event['total_capacity'] = sum(d['day_capacity'] for d in event['days'])
        event['num_days'] = len(event['days'])
    
    if event_id:
        if event_id in events:
            return events[event_id]
        else:
            print_error(f"Event '{event_id}' not found in config. Available: {list(events.keys())}")
            sys.exit(1)
    
    return events


def detect_event_from_files(raw_dir, config_path):
    """
    Auto-detect which event we're working with by matching Shotgun filenames
    to shotgun_event_id in the config.
    
    Shotgun files are named like: valid_orders_505434_2026.csv
    The number 505434 is the Shotgun event ID.
    
    Returns: (current_event_config, comparison_event_config or None)
    """
    all_events = load_event_config(config_path)
    
    # Build lookup: shotgun_event_id -> event_id
    shotgun_lookup = {}
    for eid, event in all_events.items():
        sg_id = event.get('shotgun_event_id', '')
        if sg_id:
            shotgun_lookup[sg_id] = eid
    
    # Scan CSV files for Shotgun IDs
    matched_events = {}
    for csv_file in raw_dir.glob("*.csv"):
        # Extract number from filename: valid_orders_505434_2026.csv -> 505434
        match = re.search(r'valid_orders_(\d+)', csv_file.name)
        if match:
            sg_id = match.group(1)
            if sg_id in shotgun_lookup:
                eid = shotgun_lookup[sg_id]
                matched_events[eid] = all_events[eid]
                print_info(f"Matched {csv_file.name} → {all_events[eid]['event_name']} (Shotgun ID: {sg_id})")
    
    if not matched_events:
        print_warning("Could not match any Shotgun files to event config")
        return None, None
    
    # Find the active event (current)
    active = [e for e in matched_events.values() if e['status'] == 'active']
    archive = [e for e in matched_events.values() if e['status'] == 'archive']
    
    if active:
        current = active[0]  # Take first active event
        # Check if comparison event is in our matched files
        compare_to = current.get('compare_to', '')
        comparison = matched_events.get(compare_to) or all_events.get(compare_to)
        return current, comparison
    elif archive:
        # No active events, use most recent archive
        current = archive[0]
        return current, None
    
    return None, None


# ============================================================================
# FILE DETECTION & MATCHING
# ============================================================================

def detect_year_from_shotgun(csv_path):
    """Detect event year from Shotgun CSV START/END dates."""
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i >= 10:
                    break
                date_str = row.get('DEBUT') or row.get('START', '')
                if date_str and date_str.strip():
                    year_part = date_str.strip().split('/')[0].split('-')[0].split(' ')[0]
                    try:
                        year = int(year_part)
                        if 2020 <= year <= 2030:
                            return year
                    except ValueError:
                        continue
        return None
    except Exception as e:
        print_warning(f"Error reading {csv_path}: {e}")
        return None


def detect_year_from_dice_zip(zip_path):
    """Detect event year from DICE zip — tries filenames first, then CSV content."""
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            csv_files = [f for f in z.namelist() if f.endswith('.csv') and not f.startswith('__MACOSX')]
            if not csv_files:
                return None
            # Method 1: year in internal CSV filename
            year_match = re.search(r'\b(202[0-9])\b', csv_files[0].lower())
            if year_match:
                return int(year_match.group(1))
            # Method 2: year in the zip filename itself
            year_match = re.search(r'\b(202[0-9])\b', str(zip_path.name).lower())
            if year_match:
                return int(year_match.group(1))
            # Method 3: read Purchase date from first CSV content
            with z.open(csv_files[0]) as cf:
                import io
                reader = csv.reader(io.TextIOWrapper(cf, encoding='utf-8'))
                header = next(reader, None)
                if header:
                    date_col = None
                    for i, col in enumerate(header):
                        if 'purchase date' in col.lower().strip():
                            date_col = i
                            break
                    if date_col is not None:
                        row = next(reader, None)
                        if row and date_col < len(row):
                            year_match = re.search(r'\b(202[0-9])\b', row[date_col])
                            if year_match:
                                return int(year_match.group(1))
            return None
    except Exception as e:
        print_warning(f"Error reading {zip_path}: {e}")
        return None


def auto_match_files(raw_dir):
    """
    Scan data/raw/ and match DICE zips + Shotgun CSVs by year.
    
    Current year requires DICE + Shotgun pair.
    Previous/reference year can be Shotgun-only (e.g. EPK 2023).
    
    Returns: dict with 'current' and optionally 'previous' keys,
             each containing 'dice' (Path or None), 'shotgun', 'year'.
    """
    print_header("AUTO-DETECTING FILES")
    
    dice_files = list(raw_dir.glob("*.zip"))
    shotgun_files = list(raw_dir.glob("*.csv"))
    
    print(f"📂 Found {len(dice_files)} DICE file(s), {len(shotgun_files)} Shotgun file(s)")
    
    if not shotgun_files:
        print_error("Need at least one Shotgun CSV!")
        return None
    
    if not dice_files:
        print_info("No DICE zip found — Shotgun-only mode")
    
    # Detect years
    print("\n🔍 Detecting years from file contents...")
    
    dice_years = {}
    for f in dice_files:
        print(f"   📦 Scanning {f.name}...", end=" ")
        year = detect_year_from_dice_zip(f)
        if year:
            print(f"→ {year} ✅")
            dice_years[year] = f
        else:
            print("→ Failed ❌")
    
    shotgun_years = {}
    for f in shotgun_files:
        print(f"   📄 Scanning {f.name}...", end=" ")
        year = detect_year_from_shotgun(f)
        if year:
            print(f"→ {year} ✅")
            # If multiple CSVs for same year, keep the largest (most complete export)
            if year in shotgun_years:
                existing_size = shotgun_years[year].stat().st_size
                new_size = f.stat().st_size
                if new_size > existing_size:
                    print(f"      ↳ Replacing {shotgun_years[year].name} ({existing_size:,}B) with {f.name} ({new_size:,}B)")
                    shotgun_years[year] = f
                else:
                    print(f"      ↳ Keeping {shotgun_years[year].name} (larger)")
            else:
                shotgun_years[year] = f
        else:
            print("→ Failed ❌")
    
    # Current year: prefer DICE + Shotgun pair, accept Shotgun-only
    paired_years = sorted(set(dice_years.keys()) & set(shotgun_years.keys()), reverse=True)
    shotgun_only_years = sorted(set(shotgun_years.keys()) - set(dice_years.keys()), reverse=True)
    
    if paired_years:
        current_year = paired_years[0]
        result = {
            "current": {
                "dice": dice_years[current_year],
                "shotgun": shotgun_years[current_year],
                "year": current_year
            }
        }
        print(f"\n✅ Current year: {current_year} (DICE + Shotgun)")
    elif shotgun_only_years:
        current_year = shotgun_only_years[0]
        result = {
            "current": {
                "dice": None,
                "shotgun": shotgun_years[current_year],
                "year": current_year
            }
        }
        print(f"\n✅ Current year: {current_year} (Shotgun only)")
    else:
        print_error("No Shotgun data found for any year!")
        return None
    
    # Previous year: DICE+Shotgun pair preferred, Shotgun-only accepted
    # Consider all years with Shotgun data that aren't the current year
    all_shotgun_years = sorted([y for y in shotgun_years if y != current_year], reverse=True)
    
    if all_shotgun_years:
        prev_year = all_shotgun_years[0]
        prev_dice = dice_years.get(prev_year, None)
        result["previous"] = {
            "dice": prev_dice,
            "shotgun": shotgun_years[prev_year],
            "year": prev_year
        }
        if prev_dice:
            print(f"✅ Previous year: {prev_year} (DICE + Shotgun)")
        else:
            print(f"✅ Previous year: {prev_year} (Shotgun only)")
    
    # Also check: if there are more paired years beyond the first, use the second
    # (e.g. if we have 2026 DICE+SG and 2025 DICE+SG and 2023 SG-only,
    #  the 2025 pair takes priority over 2023 SG-only as "previous")
    if len(paired_years) > 1 and 'previous' not in result:
        prev_year = paired_years[1]
        result["previous"] = {
            "dice": dice_years[prev_year],
            "shotgun": shotgun_years[prev_year],
            "year": prev_year
        }
    
    # Display matches
    print(f"\n📅 Current Year ({result['current']['year']}):")
    print(f"   DICE:    {result['current']['dice'].name}")
    print(f"   Shotgun: {result['current']['shotgun'].name}")
    
    if "previous" in result:
        prev = result['previous']
        print(f"\n📅 Previous Year ({prev['year']}):")
        print(f"   DICE:    {prev['dice'].name if prev['dice'] else '(none — Shotgun only)'}")
        print(f"   Shotgun: {prev['shotgun'].name}")
        print(f"\n🔄 Mode: COMPARISON (year-over-year)")
    else:
        print(f"\n📊 Mode: SINGLE EVENT (no comparison)")
    
    return result


def find_merge_into_files(raw_dir, config_path, parent_event_id):
    """
    Find additional Shotgun CSVs in raw_dir that belong to events
    with merge_into pointing to parent_event_id.
    
    Example: paris_xxl_2025_presale has merge_into=paris_xxl_2025,
    so its Shotgun CSV should be merged into the paris_xxl_2025 data.
    
    Returns: list of (csv_path, child_event_config) tuples
    """
    if not config_path or not Path(config_path).exists():
        return []
    
    all_events = load_event_config(config_path)
    
    # Find child events that merge into parent
    children = []
    for eid, event in all_events.items():
        if event.get('merge_into', '') == parent_event_id:
            children.append((eid, event))
    
    if not children:
        return []
    
    # Build shotgun_id -> child lookup
    child_sg_lookup = {}
    for eid, event in children:
        sg_id = event.get('shotgun_event_id', '')
        if sg_id:
            child_sg_lookup[sg_id] = (eid, event)
    
    # Scan raw_dir for matching CSVs
    found = []
    for csv_file in raw_dir.glob("*.csv"):
        match = re.search(r'valid_orders_(\d+)', csv_file.name)
        if match:
            sg_id = match.group(1)
            if sg_id in child_sg_lookup:
                eid, event = child_sg_lookup[sg_id]
                print_info(f"Found merge_into CSV: {csv_file.name} → {event['event_name']} (merges into {parent_event_id})")
                found.append((csv_file, event))
    
    return found


# ============================================================================
# DICE CSV PROCESSING
# ============================================================================

# ============================================================================
# UNIFIED TICKET CLASSIFIER
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


def determine_day_from_dates(date_debut, date_fin):
    """Determine which day a ticket is for based on START/END dates."""
    if not date_debut or not date_fin:
        return None
    try:
        debut = date_debut.strip().split(' ')[0].replace('/', '-')
        date_obj = datetime.strptime(debut, '%Y-%m-%d')
        day_map = {0: 'lundi', 1: 'mardi', 2: 'mercredi', 3: 'jeudi', 4: 'vendredi', 5: 'samedi', 6: 'dimanche'}
        return day_map.get(date_obj.weekday())
    except Exception:
        return None


# ============================================================================
# DICE CSV PROCESSING
# ============================================================================

def parse_date_dice(date_str):
    """Parse DICE date: '2025-12-02 19:02' or '2026-01-06 19:00' -> date object."""
    if not date_str or not date_str.strip():
        return None
    try:
        date_part = date_str.strip().split(' ')[0]
        datetime.strptime(date_part, '%Y-%m-%d')
        return date_part
    except (ValueError, IndexError):
        return None


def parse_datetime_dice(date_str):
    """Parse DICE datetime: '2026-01-06 19:00' -> datetime object"""
    if not date_str or not date_str.strip():
        return None
    try:
        return datetime.strptime(date_str.strip(), '%Y-%m-%d %H:%M')
    except (ValueError, IndexError):
        try:
            return datetime.strptime(date_str.strip().split(' ')[0], '%Y-%m-%d')
        except (ValueError, IndexError):
            return None


def process_dice_zip(zip_path):
    """
    Extract and process DICE doorlist ZIP.
    Uses Item Type column for ticket classification (not filename).
    Falls back to filename if Item Type is missing.
    Returns: List of ticket dictionaries.
    """
    print_header("PROCESSING DICE DATA")
    
    tickets = []
    extract_dir = Path(tempfile.mkdtemp(prefix='festiflow_dice_'))
    
    print(f"📦 Extracting ZIP: {zip_path}")
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
    except Exception as e:
        print_error(f"Failed to extract ZIP: {e}")
        shutil.rmtree(extract_dir, ignore_errors=True)
        return []
    
    csv_files = list(extract_dir.glob('*.csv'))
    # Filter out __MACOSX files
    csv_files = [f for f in csv_files if '__MACOSX' not in str(f)]
    print(f"📄 Found {len(csv_files)} CSV files")
    
    if not csv_files:
        print_warning("No CSV files found in ZIP!")
        shutil.rmtree(extract_dir, ignore_errors=True)
        return []
    
    print("\n📊 Processing DICE tickets:")
    for csv_file in csv_files:
        # Get filename-based classification as fallback
        fn_type, fn_access, fn_days, fn_name = classify_ticket(csv_file.name, is_dice_filename=True)
        
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                file_count = 0
                
                for row in reader:
                    order_date = parse_date_dice(row.get('Purchase date', ''))
                    order_datetime = parse_datetime_dice(row.get('Purchase date', ''))
                    
                    # Price: strip currency symbol (€89.00 → 89.00)
                    price_raw = row.get('Price', '0')
                    gross_price = clean_price(price_raw)
                    net_price = gross_price * 0.9435  # ~5.65% DICE platform fee
                    
                    if not order_date:
                        continue
                    
                    # PRIMARY: classify from Item Type column
                    item_type = row.get('Item Type', '').strip()
                    if item_type:
                        ticket_type, access_level, attendance_days, product_name = classify_ticket(
                            item_type, price=gross_price
                        )
                    else:
                        # FALLBACK: use filename classification
                        ticket_type, access_level, attendance_days, product_name = fn_type, fn_access, fn_days, fn_name
                    
                    tickets.append({
                        'order_date': order_date,
                        'order_datetime': order_datetime,
                        'ticket_type': ticket_type,
                        'access_level': access_level,
                        'attendance_days': attendance_days,
                        'product_name': product_name,
                        'platform': 'DICE',
                        'price': net_price,
                        'gross_price': gross_price,
                        'quantity': 1,
                        'is_paid': 0 if access_level in ('invitation', 'jeu_concours') else 1
                    })
                    file_count += 1
                
                print(f"   ✅ {csv_file.name[:60]}... → {file_count} tickets")
        except Exception as e:
            print_error(f"Error processing {csv_file.name}: {e}")
    
    shutil.rmtree(extract_dir, ignore_errors=True)
    print_success(f"DICE total: {len(tickets)} tickets processed")
    return tickets


# ============================================================================
# SHOTGUN CSV PROCESSING
# ============================================================================


def parse_date_shotgun(date_str):
    """Parse Shotgun date: '2025/12/17 18:20:09' -> '2025-12-17'"""
    if not date_str or not date_str.strip():
        return None
    try:
        date_part = date_str.strip().split(' ')[0].replace('/', '-')
        datetime.strptime(date_part, '%Y-%m-%d')
        return date_part
    except (ValueError, IndexError):
        return None


def parse_datetime_shotgun(date_str):
    """Parse Shotgun datetime: '2025/12/17 18:20:09' -> datetime object"""
    if not date_str or not date_str.strip():
        return None
    try:
        cleaned = date_str.strip().replace('/', '-')
        return datetime.strptime(cleaned, '%Y-%m-%d %H:%M:%S')
    except (ValueError, IndexError):
        try:
            date_part = cleaned.split(' ')[0]
            return datetime.strptime(date_part, '%Y-%m-%d')
        except (ValueError, IndexError):
            return None


def process_shotgun_csv(csv_path):
    """
    Process Shotgun CSV file. Supports French AND English column names.
    Classifies from CATEGORY (primary) + DEAL TITLE (secondary) combined.
    Falls back to START/END dates for day resolution.
    Returns: List of ticket dictionaries.
    """
    print_header("PROCESSING SHOTGUN DATA")
    
    tickets = []
    print(f"📄 Reading: {csv_path}")
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            total_rows = 0
            valid_rows = 0
            invalid_status = 0
            invalid_date = 0
            invitation_count = 0
            jeu_concours_count = 0
            
            for row in reader:
                total_rows += 1
                
                # Support French AND English column names
                status = row.get('STATUT', row.get('STATUS', '')).strip()
                
                if status not in ['valid', 'scanned']:
                    invalid_status += 1
                    continue
                
                categorie = row.get('CATEGORIE', row.get('CATEGORY', ''))
                nom_du_tarif = row.get('NOM DU TARIF', row.get('DEAL TITLE', ''))
                tags = row.get('TAGS', '')
                
                # Use PRIX HT (net revenue) - what you actually receive
                prix_ht = row.get('PRIX HT', row.get('PRICE', ''))
                prix_client = row.get('PRIX CLIENT', row.get('CLIENT PRICE', ''))
                
                date_debut = row.get('DEBUT', row.get('START', ''))
                date_fin = row.get('FIN', row.get('END', ''))
                raw_date_str = row.get('DATE ACHAT', row.get('PURCHASE DATE', ''))
                order_date = parse_date_shotgun(raw_date_str)
                order_datetime = parse_datetime_shotgun(raw_date_str)
                
                price = clean_price(prix_ht)
                
                if not order_date:
                    invalid_date += 1
                    continue
                
                # Classify from CATEGORY + DEAL TITLE combined
                # CATEGORY has type (PASS VENDREDI, PASS 2 JOURS...)
                # DEAL TITLE has tier + sometimes day (VIP - SAMEDI, Phase 3, Entrée avant 20h)
                combined = f"{categorie} {nom_du_tarif}".strip()
                ticket_type, access_level, attendance_days, product_name = classify_ticket(
                    combined, price=clean_price(prix_client), tags=tags
                )
                
                # Use CATEGORY as display name (cleaner than combined)
                if categorie.strip():
                    product_name = categorie.strip()
                    if product_name.isupper():
                        product_name = product_name.title()
                
                # Fallback: if no day found, try START/END dates
                if (attendance_days is None or len(attendance_days) == 0) and ticket_type == 'single_day':
                    day_from_date = determine_day_from_dates(date_debut, date_fin)
                    if day_from_date:
                        ticket_type = day_from_date
                        attendance_days = [day_from_date]
                
                is_paid = 1 if price > 0 else 0
                
                tickets.append({
                    'order_date': order_date,
                    'order_datetime': order_datetime,
                    'ticket_type': ticket_type,
                    'access_level': access_level,
                    'attendance_days': attendance_days,
                    'product_name': product_name,
                    'platform': 'Shotgun',
                    'price': price,
                    'gross_price': clean_price(prix_client),
                    'quantity': 1,
                    'is_paid': is_paid
                })
                valid_rows += 1
                
                if access_level == 'invitation':
                    invitation_count += 1
                elif access_level == 'jeu_concours':
                    jeu_concours_count += 1
        
        print(f"\n📊 Shotgun processing summary:")
        print(f"   Total rows: {total_rows}")
        print(f"   Valid tickets: {valid_rows}")
        print(f"   └─ Paid tickets: {valid_rows - invitation_count - jeu_concours_count}")
        print(f"   └─ Invitations (free): {invitation_count}")
        print(f"   └─ Jeu concours (free): {jeu_concours_count}")
        print(f"   Excluded (non-valid status): {invalid_status}")
        print(f"   Excluded (invalid date): {invalid_date}")
        
        print_success(f"Shotgun total: {len(tickets)} tickets processed")
    
    except Exception as e:
        print_error(f"Error processing Shotgun CSV: {e}")
        return []
    
    return tickets


# ============================================================================
# MERGE
# ============================================================================

def merge_tickets(dice_tickets, shotgun_tickets):
    """
    Merge DICE and Shotgun tickets into a single sorted list.
    Returns: list of ticket dicts, sorted by order_date.
    """
    print_header("MERGING DATA")
    
    all_tickets = dice_tickets + shotgun_tickets
    
    print(f"📊 Combined totals:")
    print(f"   DICE: {len(dice_tickets)} tickets")
    print(f"   Shotgun: {len(shotgun_tickets)} tickets")
    print(f"   TOTAL: {len(all_tickets)} tickets")
    
    all_tickets.sort(key=lambda x: x['order_date'])
    
    # Print breakdown
    breakdown = defaultdict(lambda: {'DICE': 0, 'Shotgun': 0})
    for t in all_tickets:
        key = f"{t['ticket_type']}_{t['access_level']}"
        breakdown[key][t['platform']] += 1
    
    print(f"\n📈 Breakdown by ticket type:")
    for key in sorted(breakdown.keys()):
        ticket_type, access_level = key.split('_', 1)
        d = breakdown[key]['DICE']
        s = breakdown[key]['Shotgun']
        print(f"   {ticket_type:12} / {access_level:15} → DICE: {d:5} | Shotgun: {s:5} | Total: {d+s:5}")
    
    print_success(f"Merge completed: {len(all_tickets)} tickets")
    return all_tickets


def save_merged_csv(tickets, output_path):
    """Save merged tickets to CSV."""
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['order_date', 'order_datetime', 'ticket_type', 'access_level', 'attendance_days', 'product_name', 'platform', 'price', 'gross_price', 'quantity', 'is_paid']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(tickets)
    print_success(f"Saved {len(tickets)} tickets to {output_path}")


# ============================================================================
# DATA LOADING (from merged CSV or in-memory)
# ============================================================================

def load_ticket_data(tickets_raw, cutoff_date=None, event_config=None):
    """
    Process ticket data: parse dates, calculate presence, apply dual cutoff.
    
    Dual cutoff system:
      - cutoff_cumulative (= max_date): used for revenue, counts, presence
      - cutoff_velocity (= max_date - 1): used for velocity, projections
    
    Args:
        tickets_raw: List of ticket dicts (from merge) or path to CSV
        cutoff_date: Optional velocity cutoff override (defaults to latest - 1 day)
        event_config: Event config dict (for day structure)
    
    Returns: (processed_tickets, cutoff_velocity, cutoff_cumulative)
    """
    print_header("LOADING TICKET DATA")
    
    # If given a path, read CSV
    if isinstance(tickets_raw, (str, Path)):
        print(f"📄 Reading: {tickets_raw}")
        tickets_raw_list = []
        with open(tickets_raw, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                tickets_raw_list.append(row)
        tickets_raw = tickets_raw_list
    
    # Find latest date
    all_dates = []
    for t in tickets_raw:
        d = t['order_date']
        if isinstance(d, str):
            d = datetime.strptime(d, '%Y-%m-%d').date()
        all_dates.append(d)
    
    max_date = max(all_dates)
    
    # Dual cutoff: include ALL data up to max_date (cumulative),
    # but velocity uses yesterday (max_date - 1) for complete-day accuracy
    cutoff_cumulative = max_date
    if cutoff_date is None:
        cutoff_velocity = max_date - timedelta(days=1)
    elif isinstance(cutoff_date, str):
        cutoff_velocity = datetime.strptime(cutoff_date, '%Y-%m-%d').date()
    else:
        cutoff_velocity = cutoff_date
    
    print(f"📅 Latest date in data: {max_date}")
    print(f"📅 Cutoff cumulative (revenue/counts): {cutoff_cumulative} (all data)")
    print(f"📅 Cutoff velocity (rates/projections): {cutoff_velocity} (complete days only)")
    
    # Determine day structure from config
    day_names = []
    if event_config:
        day_names = [d['day_name'].lower() for d in event_config['days']]
    
    # Process ALL tickets up to cumulative cutoff (= max_date)
    tickets = []
    for t in tickets_raw:
        order_date = t['order_date']
        if isinstance(order_date, str):
            order_date = datetime.strptime(order_date, '%Y-%m-%d').date()
        
        if order_date > cutoff_cumulative:
            continue
        
        # Parse attendance_days from stored data (may be string repr from CSV)
        attendance_days = t.get('attendance_days')
        if isinstance(attendance_days, str):
            if attendance_days and attendance_days != 'None':
                try:
                    import ast
                    attendance_days = ast.literal_eval(attendance_days)
                except (ValueError, SyntaxError):
                    attendance_days = None
            else:
                attendance_days = None
        
        # Parse order_datetime (may be string from CSV or datetime object)
        order_datetime_raw = t.get('order_datetime')
        if isinstance(order_datetime_raw, str) and order_datetime_raw:
            try:
                order_datetime_parsed = datetime.strptime(order_datetime_raw, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                try:
                    order_datetime_parsed = datetime.strptime(order_datetime_raw, '%Y-%m-%d %H:%M')
                except ValueError:
                    order_datetime_parsed = None
        else:
            order_datetime_parsed = order_datetime_raw if isinstance(order_datetime_raw, datetime) else None

        ticket = {
            'order_date': order_date,
            'order_datetime': order_datetime_parsed,
            'ticket_type': t['ticket_type'],
            'access_level': t['access_level'],
            'platform': t['platform'],
            'price': float(t['price']),
            'quantity': int(t['quantity']),
            'is_paid': int(t.get('is_paid', 1)),
            'product_name': t.get('product_name', ''),
        }
        
        # Re-classify single_day tickets using event dates if product_name contains a date
        if ticket['ticket_type'] == 'single_day' and event_config:
            event_days = event_config.get('days', [])
            _, _, reclassified_days, _ = classify_ticket(
                ticket['product_name'], event_days=event_days
            )
            if reclassified_days and len(reclassified_days) == 1:
                ticket['ticket_type'] = reclassified_days[0]
                attendance_days = reclassified_days
        
        # Add presence for each day using resolve_attendance
        presence = resolve_attendance(t['ticket_type'], attendance_days, day_names)
        for dn in day_names:
            ticket[f'presence_{dn}'] = presence.get(dn, 0)
        
        tickets.append(ticket)
    
    today_count = len([t for t in tickets if t['order_date'] == cutoff_cumulative])
    yesterday_count = len([t for t in tickets if t['order_date'] == cutoff_velocity])
    
    print_success(f"Loaded {len(tickets)} tickets (up to {cutoff_cumulative})")
    print(f"   Including today ({cutoff_cumulative}): {today_count} tickets (partial day)")
    print(f"   Yesterday ({cutoff_velocity}): {yesterday_count} tickets (complete)")
    if tickets:
        min_d = min(t['order_date'] for t in tickets)
        max_d = max(t['order_date'] for t in tickets)
        print(f"   Date range: {min_d} to {max_d}")
    
    return tickets, cutoff_velocity, cutoff_cumulative


# ============================================================================
# METRICS CALCULATION
# ============================================================================

def calculate_metrics(tickets, event_config=None, velocity_cutoff=None):
    """
    Calculate all dashboard metrics from ticket data.
    Now dynamic: works with any number of days from config.
    
    Dual cutoff: tickets includes ALL data (up to today).
    velocity_cutoff limits which tickets are used for rate-based metrics.
    """
    print_header("CALCULATING METRICS")
    
    metrics = {}
    
    day_names = []
    if event_config:
        day_names = [d['day_name'].lower() for d in event_config['days']]
    
    # Basic counts
    total_tickets_all = len(tickets)
    paid_tickets = [t for t in tickets if t.get('is_paid', 1) == 1]
    total_tickets_paid = len(paid_tickets)
    
    print(f"📊 Total tickets (all): {fmt_num(total_tickets_all)}")
    print(f"📊 Total tickets (paid): {fmt_num(total_tickets_paid)}")
    
    # By type, platform, access
    by_type = defaultdict(int)
    by_type_paid = defaultdict(int)
    by_platform = defaultdict(int)
    by_platform_paid = defaultdict(int)
    by_access = defaultdict(int)
    total_revenue = 0
    
    for t in tickets:
        by_type[t['ticket_type']] += 1
        by_platform[t['platform']] += 1
        by_access[t['access_level']] += 1
        if t.get('is_paid', 1) == 1:
            total_revenue += t['price']
            by_type_paid[t['ticket_type']] += 1
            by_platform_paid[t['platform']] += 1
    
    # Dynamic presence calculation per day
    day_presence = {}
    total_presence = 0
    for dn in day_names:
        key = f'presence_{dn}'
        p = sum(t.get(key, 0) for t in tickets)
        day_presence[dn] = p
        total_presence += p
        print(f"   {dn.capitalize()} presence (all): {fmt_num(p)}")
    
    print(f"   Total presence (all): {fmt_num(total_presence)}")
    
    # Per-day detailed breakdown
    day_breakdown = {}
    for dn in day_names:
        key = f'presence_{dn}'
        day_tix = [t for t in tickets if t.get(key, 0) > 0]
        day_paid = [t for t in day_tix if t.get('is_paid', 1) == 1]
        day_free = [t for t in day_tix if t.get('is_paid', 1) == 0]
        day_rev = sum(t['price'] for t in day_paid)
        day_avg = day_rev / len(day_paid) if day_paid else 0
        day_sg = sum(1 for t in day_paid if t['platform'] == 'Shotgun')
        day_dice = sum(1 for t in day_paid if t['platform'] == 'DICE')
        # By ticket type
        by_type = {}
        for t in day_tix:
            tt = t['ticket_type']
            by_type[tt] = by_type.get(tt, 0) + 1
        day_breakdown[dn] = {
            'paid': len(day_paid), 'free': len(day_free),
            'revenue': day_rev, 'avg_price': day_avg,
            'sg': day_sg, 'dice': day_dice,
            'by_type': by_type,
        }
    
    # Revenue
    revenue_dice = sum(t['price'] for t in paid_tickets if t['platform'] == 'DICE')
    revenue_shotgun = sum(t['price'] for t in paid_tickets if t['platform'] == 'Shotgun')
    avg_ticket_price = total_revenue / total_tickets_paid if total_tickets_paid > 0 else 0
    
    print(f"   Total revenue: {fmt_currency(total_revenue)}")
    print(f"   DICE: {fmt_currency(revenue_dice)}")
    print(f"   Shotgun: {fmt_currency(revenue_shotgun)}")
    print(f"   Avg ticket price: €{avg_ticket_price:.2f}")
    
    # Velocity (global) - uses velocity_cutoff for complete-day accuracy
    # Filter to complete days only for rate calculations
    vel_cutoff = velocity_cutoff if velocity_cutoff else max(t['order_date'] for t in paid_tickets) if paid_tickets else None
    paid_velocity = [t for t in paid_tickets if t['order_date'] <= vel_cutoff] if vel_cutoff else paid_tickets
    
    if paid_velocity:
        latest_vel_date = vel_cutoff
        
        velocities = {}
        for days in [7, 14, 30]:
            threshold = latest_vel_date - timedelta(days=days)
            count = len([t for t in paid_velocity if t['order_date'] > threshold])
            velocities[days] = count / days
        
        velocity_7d = velocities[7]
        velocity_14d = velocities[14]
        velocity_30d = velocities[30]
        
        print(f"   Velocity cutoff: {vel_cutoff} (complete days only)")
        print(f"   Velocity 7d: {velocity_7d:.1f}/day")
        print(f"   Velocity 14d: {velocity_14d:.1f}/day")
        print(f"   Velocity 30d: {velocity_30d:.1f}/day")
        
        # Day-specific velocity with trends
        day_velocity = {}
        for dn in day_names:
            presence_key = f'presence_{dn}'
            
            # 7-day window (from velocity cutoff, not max date)
            date_7d = latest_vel_date - timedelta(days=7)
            tickets_7d = [t for t in paid_velocity if t['order_date'] > date_7d]
            
            # Day-specific tickets in last 7d
            day_only_7d = [t for t in tickets_7d if t['ticket_type'] == dn]
            # Multi-day passes that include this day
            pass2j_7d = [t for t in tickets_7d if t['ticket_type'] == '2-jours']
            pass3j_7d = [t for t in tickets_7d if t['ticket_type'] == '3-jours']
            
            vel_day_only = len(day_only_7d) / 7
            vel_pass2j = len(pass2j_7d) / 7 if dn in ('vendredi', 'samedi') else 0
            vel_pass3j = len(pass3j_7d) / 7
            vel_total = vel_day_only + vel_pass2j + vel_pass3j
            
            # Previous 7-day window for trend
            date_14d = latest_vel_date - timedelta(days=14)
            tickets_prev_7d = [t for t in paid_velocity if date_14d < t['order_date'] <= date_7d]
            
            day_only_prev = [t for t in tickets_prev_7d if t['ticket_type'] == dn]
            pass2j_prev = [t for t in tickets_prev_7d if t['ticket_type'] == '2-jours']
            pass3j_prev = [t for t in tickets_prev_7d if t['ticket_type'] == '3-jours']
            
            vel_prev = (len(day_only_prev) + (len(pass2j_prev) if dn in ('vendredi', 'samedi') else 0) + len(pass3j_prev)) / 7
            
            trend_pct = ((vel_total - vel_prev) / vel_prev * 100) if vel_prev > 0 else 0
            
            # 14-day velocity (for display)
            date_14d_start = latest_vel_date - timedelta(days=14)
            tickets_14d = [t for t in paid_velocity if t['order_date'] > date_14d_start]
            day_tickets_14d = [t for t in tickets_14d if t.get(presence_key, 0) == 1]
            vel_14d = len(day_tickets_14d) / 14
            
            day_velocity[dn] = {
                'velocity_14d': vel_14d,
                'velocity_day_only_7d': vel_day_only,
                'velocity_pass2j_7d': vel_pass2j,
                'velocity_pass3j_7d': vel_pass3j,
                'velocity_total_7d': vel_total,
                'trend_pct': trend_pct,
            }
            
            print(f"   Velocity {dn.capitalize()} 14d: {vel_14d:.1f}/day")
            print(f"   - Trend: {trend_pct:+.1f}% vs previous 7d")
    else:
        velocity_7d = velocity_14d = velocity_30d = 0
        day_velocity = {dn: {'velocity_14d': 0, 'velocity_day_only_7d': 0, 'velocity_pass2j_7d': 0, 'velocity_pass3j_7d': 0, 'velocity_total_7d': 0, 'trend_pct': 0} for dn in day_names}
    
    # Multi-day pass counts
    deux_jours_tickets = by_type.get('2-jours', 0)
    trois_jours_tickets = by_type.get('3-jours', 0)
    
    metrics = {
        'total_tickets': total_tickets_paid,
        'total_tickets_paid': total_tickets_paid,
        'total_tickets_all': total_tickets_all,
        'total_presence': total_presence,
        'day_presence': day_presence,
        'day_breakdown': day_breakdown,
        'deux_jours_tickets': deux_jours_tickets,
        'trois_jours_tickets': trois_jours_tickets,
        'by_type': dict(by_type),
        'dice_tickets': by_platform_paid.get('DICE', 0),
        'shotgun_tickets': by_platform_paid.get('Shotgun', 0),
        'total_revenue': total_revenue,
        'revenue_dice': revenue_dice,
        'revenue_shotgun': revenue_shotgun,
        'avg_ticket_price': avg_ticket_price,
        'velocity_7d': velocity_7d,
        'velocity_14d': velocity_14d,
        'velocity_30d': velocity_30d,
        'day_velocity': day_velocity,
        'vip_tickets': by_access.get('vip', 0),
        'backstage_tickets': by_access.get('backstage', 0),
        'early_entry_tickets': by_access.get('early_entry', 0),
        'invitation_tickets': by_access.get('invitation', 0),
        'jeu_concours_tickets': by_access.get('jeu_concours', 0),
        'group_discount_free_tickets': len([t for t in tickets if t['access_level'] == 'group_discount' and t.get('is_paid', 1) == 0]),
    }
    
    print_success("Metrics calculated successfully")
    return metrics


# ============================================================================
# YEAR-OVER-YEAR COMPARISON
# ============================================================================

def filter_tickets_to_same_point(tickets_prev, cutoff_date_current, event_date_current, event_date_prev):
    """
    Filter previous year tickets to match same point in campaign (J-minus mode).
    E.g., if we're 112 days before 2026 event, filter 2025 to 112 days before 2025 event.
    """
    days_before = (event_date_current - cutoff_date_current).days
    same_point_prev = event_date_prev - timedelta(days=days_before)
    
    filtered = [t for t in tickets_prev if t['order_date'] <= same_point_prev]
    
    print(f"\n⏱️  SAME POINT COMPARISON (J-minus):")
    print(f"   Current: {cutoff_date_current} ({days_before} days before event)")
    print(f"   Previous: {same_point_prev} ({days_before} days before event)")
    print(f"   Previous tickets filtered: {len(tickets_prev)} → {len(filtered)}")
    
    return filtered


def filter_tickets_to_same_point_dsl(tickets_prev, cutoff_date_current, launch_date_current, launch_date_prev):
    """
    Filter previous year tickets to match same point in campaign (days-since-launch mode).
    E.g., if current is 11 days since launch, filter prev to 11 days since their launch.
    """
    days_since_launch = (cutoff_date_current - launch_date_current).days
    same_point_prev = launch_date_prev + timedelta(days=days_since_launch)
    
    filtered = [t for t in tickets_prev if t['order_date'] <= same_point_prev]
    
    print(f"\n⏱️  SAME POINT COMPARISON (days-since-launch):")
    print(f"   Current launch: {launch_date_current}, cutoff: {cutoff_date_current} ({days_since_launch} days since launch)")
    print(f"   Previous launch: {launch_date_prev}, cutoff: {same_point_prev} ({days_since_launch} days since launch)")
    print(f"   Previous tickets filtered: {len(tickets_prev)} → {len(filtered)}")
    
    return filtered


def compare_years(metrics_current, metrics_prev):
    """Calculate year-over-year comparison metrics."""
    print_header("YEAR-OVER-YEAR COMPARISON")
    
    ticket_diff = metrics_current['total_tickets'] - metrics_prev['total_tickets']
    ticket_growth = (ticket_diff / metrics_prev['total_tickets'] * 100) if metrics_prev['total_tickets'] > 0 else 0
    
    revenue_diff = metrics_current['total_revenue'] - metrics_prev['total_revenue']
    revenue_growth = (revenue_diff / metrics_prev['total_revenue'] * 100) if metrics_prev['total_revenue'] > 0 else 0
    
    price_diff = metrics_current['avg_ticket_price'] - metrics_prev['avg_ticket_price']
    price_growth = (price_diff / metrics_prev['avg_ticket_price'] * 100) if metrics_prev['avg_ticket_price'] > 0 else 0
    
    print(f"📊 Tickets: {fmt_num(metrics_current['total_tickets'])} vs {fmt_num(metrics_prev['total_tickets'])}")
    print(f"   Growth: {ticket_diff:+,} ({ticket_growth:+.1f}%)")
    print(f"💰 Revenue: {fmt_currency(metrics_current['total_revenue'])} vs {fmt_currency(metrics_prev['total_revenue'])}")
    print(f"   Growth: {fmt_currency(revenue_diff)} ({revenue_growth:+.1f}%)")
    
    comparison = {
        'ticket_diff': ticket_diff,
        'ticket_growth_pct': ticket_growth,
        'revenue_diff': revenue_diff,
        'revenue_growth_pct': revenue_growth,
        'price_diff': price_diff,
        'price_growth_pct': price_growth,
    }
    
    print_success("Comparison calculated")
    return comparison


# ============================================================================
# PROJECTION SCENARIOS
# ============================================================================

def calculate_projection_scenarios(tickets, cutoff_date, event_config):
    """
    Calculate projection scenarios (pessimiste/base/optimiste) for global and each day.
    Dynamic: works with any number of days from config.
    """
    print_header("CALCULATING PROJECTION SCENARIOS")
    
    day_names = [d['day_name'].lower() for d in event_config['days']]
    day_capacities = {d['day_name'].lower(): d['day_capacity'] for d in event_config['days']}
    event_date = event_config['event_date_first']
    total_capacity = event_config['total_capacity']
    
    days_remaining = max(0, (event_date - cutoff_date).days)  # clamp to 0 when event is past
    
    # Calculate all 7-day velocity windows
    all_dates = sorted(set(t['order_date'] for t in tickets))
    
    velocities_global = []
    velocities_by_day = {dn: [] for dn in day_names}
    
    for i in range(len(all_dates) - 6):
        window_start = all_dates[i]
        window_end = all_dates[i + 6]
        window_tickets = [t for t in tickets if window_start <= t['order_date'] <= window_end]
        
        velocities_global.append(len(window_tickets) / 7)
        
        for dn in day_names:
            presence = sum(t.get(f'presence_{dn}', 0) for t in window_tickets)
            velocities_by_day[dn].append(presence / 7)
    
    # 14-day base velocity
    last_14 = cutoff_date - timedelta(days=13)
    tickets_14d = [t for t in tickets if last_14 <= t['order_date'] <= cutoff_date]
    
    base_vel_global = len(tickets_14d) / 14
    base_vel_by_day = {}
    for dn in day_names:
        base_vel_by_day[dn] = sum(t.get(f'presence_{dn}', 0) for t in tickets_14d) / 14
    
    # Current totals
    total_tickets = len(tickets)
    current_by_day = {}
    for dn in day_names:
        current_by_day[dn] = sum(t.get(f'presence_{dn}', 0) for t in tickets)
    
    # Scenario calculator
    def calc_scenario(current, velocity, capacity, days_rem):
        projected = current + (velocity * days_rem)
        pct = (projected / capacity * 100) if capacity > 0 else 0
        
        remaining = capacity - current
        if remaining > 0 and velocity > 0:
            days_to_sellout = remaining / velocity
            if days_to_sellout <= days_rem * 1.10:
                sellout_date = cutoff_date + timedelta(days=int(days_to_sellout))
                days_before = (event_date - sellout_date).days
                if days_to_sellout <= days_rem:
                    sellout_text = f"Sold out: {sellout_date.strftime('%d %b')} ({days_before} jours avant)"
                else:
                    sellout_text = f"Sold out serré: ~{sellout_date.strftime('%d %b')}"
                will_sellout = True
            else:
                sellout_text = "Ne se vendra pas avant l'événement"
                will_sellout = False
        else:
            sellout_text = "Déjà complet" if remaining <= 0 else "Ne se vendra pas"
            will_sellout = remaining <= 0
        
        return {
            'projected': int(projected),
            'pct_capacity': pct,
            'velocity': velocity,
            'sellout_text': sellout_text,
            'will_sellout': will_sellout
        }
    
    scenarios = {}
    
    # Global
    best_g = max(velocities_global) if velocities_global else 0
    worst_g = min(velocities_global) if velocities_global else 0
    
    scenarios['global'] = {
        'pessimiste': calc_scenario(total_tickets, worst_g, total_capacity, days_remaining),
        'base': calc_scenario(total_tickets, base_vel_global, total_capacity, days_remaining),
        'optimiste': calc_scenario(total_tickets, best_g, total_capacity, days_remaining),
    }
    
    print(f"✅ Global velocities - Best: {best_g:.1f}/day, Worst: {worst_g:.1f}/day")
    
    # Per-day scenarios
    for dn in day_names:
        cap = day_capacities.get(dn, 0)
        vels = velocities_by_day[dn]
        best_d = max(vels) if vels else 0
        worst_d = min(vels) if vels else 0
        
        scenarios[dn] = {
            'pessimiste': calc_scenario(current_by_day[dn], worst_d, cap, days_remaining),
            'base': calc_scenario(current_by_day[dn], base_vel_by_day[dn], cap, days_remaining),
            'optimiste': calc_scenario(current_by_day[dn], best_d, cap, days_remaining),
        }
        
        print(f"   {dn.capitalize()} velocities - Best: {best_d:.1f}/day, Worst: {worst_d:.1f}/day")
    
    scenarios['days_remaining'] = days_remaining
    scenarios['current_tickets'] = total_tickets
    scenarios['current_by_day'] = current_by_day
    
    return scenarios


# ============================================================================
# HTML GENERATION - Festiflow v3 Template
# ============================================================================

# Day color palette for the new template (--day-0, --day-1, --day-2, --day-3)
DAY_PALETTE_V3 = [
    {'hex': '#a855f7', 'rgb': '168,85,247'},   # purple
    {'hex': '#6366f1', 'rgb': '99,102,241'},    # indigo
    {'hex': '#f472b6', 'rgb': '244,114,182'},   # pink
    {'hex': '#4f46e5', 'rgb': '79,70,229'},     # deep indigo
]

DAY_ABBREV = {
    'jeudi': 'Jeu', 'vendredi': 'Ven', 'samedi': 'Sam', 'dimanche': 'Dim',
    'lundi': 'Lun', 'mardi': 'Mar', 'mercredi': 'Mer'
}


def resolve_template_blocks(html, conditions):
    """Handle {{#COND}}...{{/COND}} mustache-like blocks."""
    import re
    for key, show in conditions.items():
        pattern = r'\{\{#' + key + r'\}\}(.*?)\{\{/' + key + r'\}\}'
        if show:
            html = re.sub(pattern, r'\1', html, flags=re.DOTALL)
        else:
            html = re.sub(pattern, '', html, flags=re.DOTALL)
    return html


def build_dashboard_html_v3(template_path, metrics, cutoff_date, event_config,
                            tickets=None, tickets_prev_filtered=None, tickets_prev_full=None,
                            comparison=None, metrics_prev=None, event_config_prev=None,
                            cutoff_cumulative=None):
    """
    Build dashboard HTML using the Festiflow v3 template.
    Maps existing metrics dict → new template placeholders.
    """
    print_header("BUILDING FESTIFLOW V3 DASHBOARD")
    
    with open(template_path, 'r', encoding='utf-8') as f:
        html = f.read()
    
    # ── Extract config ──
    day_names = [d['day_name'].lower() for d in event_config['days']]
    day_configs = {d['day_name'].lower(): d for d in event_config['days']}
    total_capacity = event_config['total_capacity']
    event_date = event_config['event_date_first']
    event_date_last = event_config['event_date_last']
    num_days = event_config['num_days']
    days_remaining = max(0, (event_date - cutoff_date).days)  # clamp to 0 when event is past  # From velocity cutoff, for projections
    days_remaining_display = max(0, (event_date - cutoff_cumulative).days if cutoff_cumulative else days_remaining)  # From today, clamped to 0 when event is past
    current_year = str(event_date.year)
    
    has_comparison = comparison is not None and metrics_prev is not None

    # ── Warmup day exclusion (Jeudi = warmup if event has 3+ days and first day is Jeudi) ──
    day_names_list = [d['day_name'].lower() for d in event_config['days']]
    warmup_day = 'jeudi' if len(day_names_list) >= 3 and day_names_list[0] == 'jeudi' else None
    day_presence_current = metrics.get('day_presence', {})
    if warmup_day and warmup_day in day_presence_current:
        warmup_presence = int(day_presence_current[warmup_day])
        warmup_capacity = next((d['day_capacity'] for d in event_config['days'] if d['day_name'].lower() == warmup_day), 0)
    else:
        warmup_day = None
        warmup_presence = 0
        warmup_capacity = 0
    presence_no_warmup = int(metrics['total_presence']) - warmup_presence
    capacity_no_warmup = int(total_capacity) - warmup_capacity
    pct_no_warmup = round(presence_no_warmup / capacity_no_warmup * 100, 1) if capacity_no_warmup > 0 else 0

    # ── Conditional blocks ──
    html = resolve_template_blocks(html, {
        'HAS_COMPARISON': has_comparison,
        'IS_FIRST_EDITION': not has_comparison,
        'SHOW_PAR_JOUR': num_days > 1,
        'IS_TERMINE': days_remaining_display <= 0,
        'IS_LIVE': days_remaining_display > 0,
        'HAS_WARMUP': 'true' if warmup_day is not None else 'false',
        'DICE_DASHBOARD_URL': bool(event_config.get('dice_mio_id', '')),
        'SHOTGUN_DASHBOARD_URL': bool(event_config.get('shotgun_url', '')),
        'DICE_PUBLIC_URL': bool(event_config.get('dice_url', '')),
        'SHOTGUN_PUBLIC_URL': bool(event_config.get('shotgun_url', '')),
    })
    
    # ── Date formatting ──
    if num_days == 1:
        dates_short = f"{event_date.day} {MONTHS_FR_FULL[event_date.month].lower()} {current_year}"
        dates_compact = f"{event_date.day} {MONTHS_FR_FULL[event_date.month].lower()}"
    elif event_date.month == event_date_last.month:
        dates_short = f"{event_date.day}-{event_date_last.day} {MONTHS_FR_FULL[event_date.month].lower()} {current_year}"
        dates_compact = f"{event_date.day}-{event_date_last.day} {MONTHS_FR_FULL[event_date.month].lower()}"
    else:
        dates_short = f"{event_date.day} {MONTHS_FR_FULL[event_date.month].lower()} - {event_date_last.day} {MONTHS_FR_FULL[event_date_last.month].lower()} {current_year}"
        dates_compact = dates_short
    
    # ── Days on sale ──
    # Use first ticket order date if available
    if tickets:
        first_sale = min(t['order_date'] for t in tickets)
        days_on_sale = (cutoff_date - first_sale).days
        sale_start = f"{first_sale.day} {MONTHS_FR_ABBR.get(first_sale.month, MONTHS_FR_ABBR[first_sale.month].lower())} {first_sale.year}"
    else:
        days_on_sale = 0
        sale_start = "-"
    
    # ── Weeks remaining badge ──
    weeks_rem = max(1, (days_remaining + 6) // 7)
    
    # ── Revenue calculations ──
    total_revenue = metrics['total_revenue']
    avg_price = metrics['avg_ticket_price']
    sell_through_pct = (metrics['total_presence'] / total_capacity * 100) if total_capacity > 0 else 0


    ring_offset = int(264 - (264 * sell_through_pct / 100))
    
    # Revenue formatting
    def fmt_revenue(amount):
        if amount >= 1_000_000:
            return f"€{amount/1_000_000:.2f}M"
        elif amount >= 1_000:
            return f"€{amount/1_000:.0f}k"
        return f"€{amount:.0f}"
    
    # Projection revenue (velocity-14d based)
    avg_presence_per_ticket = metrics['total_presence'] / metrics['total_tickets'] if metrics['total_tickets'] > 0 else 1.2
    projected_tickets = metrics['total_tickets'] + int(metrics['velocity_14d'] * days_remaining)
    max_tickets_for_capacity = total_capacity / avg_presence_per_ticket if avg_presence_per_ticket > 0 else total_capacity
    capped_tickets = min(projected_tickets, max_tickets_for_capacity)
    revenue_projection = capped_tickets * avg_price
    revenue_if_soldout = max_tickets_for_capacity * avg_price
    
    # ── Comparison values ──
    compare_year = str(event_config_prev['event_date_first'].year) if event_config_prev else "-"
    compare_event_name = event_config_prev['event_name'] if event_config_prev else ""
    
    if event_config_prev:
        prev_date = event_config_prev['event_date_first']
        prev_date_last = event_config_prev['event_date_last']
        if prev_date.month == prev_date_last.month:
            compare_dates = f"{prev_date.day}-{prev_date_last.day} {MONTHS_FR_FULL[prev_date.month].lower()} {prev_date.year}"
        else:
            compare_dates = f"{prev_date.day} {MONTHS_FR_FULL[prev_date.month].lower()} - {prev_date_last.day} {MONTHS_FR_FULL[prev_date_last.month].lower()} {prev_date.year}"
        prev_capacity = event_config_prev['total_capacity']
        cap_delta_pct = ((total_capacity - prev_capacity) / prev_capacity * 100) if prev_capacity > 0 else 0
        compare_cap_delta = f"{cap_delta_pct:+.0f}%"
    else:
        compare_dates = ""
        prev_capacity = 0
        compare_cap_delta = ""
    
    # ── YoY values ──
    if has_comparison:
        revenue_yoy_pct = comparison['revenue_growth_pct']
        revenue_yoy = f"{revenue_yoy_pct:+.1f}%"
        revenue_yoy_class = 'positive' if revenue_yoy_pct >= 0 else 'negative'
        price_delta_pct = comparison['price_growth_pct']
        avg_price_delta = f"{price_delta_pct:+.1f}%"
        compare_revenue = fmt_revenue(metrics_prev['total_revenue'])
        revenue_vs_compare_raw = total_revenue - metrics_prev['total_revenue']
        revenue_vs_compare = f"+€{abs(revenue_vs_compare_raw)/1000:.0f}k" if revenue_vs_compare_raw >= 0 else f"-€{abs(revenue_vs_compare_raw)/1000:.0f}k"
        
        presence_yoy_pct = ((metrics['total_presence'] - metrics_prev['total_presence']) / metrics_prev['total_presence'] * 100) if metrics_prev['total_presence'] > 0 else 0
        presence_yoy = f"{presence_yoy_pct:+.1f}%"
        presence_yoy_class = 'positive' if presence_yoy_pct >= 0 else 'negative'
    else:
        revenue_yoy = revenue_yoy_class = avg_price_delta = ""
        compare_revenue = revenue_vs_compare = ""
        presence_yoy = presence_yoy_class = ""
    
    # ── Accent gradient ──
    if num_days == 1:
        accent_gradient = 'var(--day-0)'
    else:
        stops = ', '.join(f'var(--day-{i})' for i in range(num_days))
        accent_gradient = f'linear-gradient(90deg, {stops})'
    
    # ── Projection grid cols ──
    proj_grid_cols = '1fr' if num_days == 1 else ' '.join(['1fr'] * min(num_days, 3)) if num_days <= 3 else f'repeat({num_days}, 1fr)'
    
    # ── Day tab active CSS ──
    tab_css_lines = []
    for i in range(num_days):
        c = DAY_PALETTE_V3[i % len(DAY_PALETTE_V3)]
        cls = 'active' if i == 0 else f'active-day{i}'
        r, g, b = c['rgb'].split(',')
        tab_css_lines.append(f'.chart-tab.{cls} {{ background: rgba({r},{g},{b},0.1); border-color: var(--day-{i}); color: var(--day-{i}); }}')
    
    # ── Platform split ──
    rev_sg = metrics['revenue_shotgun']
    rev_dice = metrics['revenue_dice']
    total_rev = rev_sg + rev_dice
    sg_pct = (rev_sg / total_rev * 100) if total_rev > 0 else 50
    
    platform_split_bar = f'<div class="split-bar"><div class="seg" style="width:{sg_pct:.1f}%;background:var(--sg-green)"></div><div class="seg" style="width:{100-sg_pct:.1f}%;background:rgba(255,255,255,0.15)"></div></div>'
    platform_rows = f'''<div class="platform-row"><span class="platform-name"><span class="plat-dot" style="background:var(--sg-green)"></span>Shotgun</span><span class="platform-stats">{fmt_revenue(rev_sg)} <span class="platform-tickets">· {fmt_num(metrics['shotgun_tickets'])} billets</span></span></div>
<div class="platform-row"><span class="platform-name"><span class="plat-dot" style="background:rgba(255,255,255,0.35)"></span>DICE</span><span class="platform-stats">{fmt_revenue(rev_dice)} <span class="platform-tickets">· {fmt_num(metrics['dice_tickets'])} billets</span></span></div>'''
    
    # Platform ticket counts for main card
    sg_tickets = metrics['shotgun_tickets']
    dice_tickets = metrics['dice_tickets']
    sg_tix_pct = (sg_tickets / (sg_tickets + dice_tickets) * 100) if (sg_tickets + dice_tickets) > 0 else 50
    platform_ticket_counts = f'''<div class="meta-row"><span class="meta-key"><span class="plat-dot" style="background:var(--sg-green)"></span>Shotgun</span><span class="meta-val">{fmt_num(sg_tickets)} billets</span></div>
    <div style="height:4px"></div>
    <div class="meta-row"><span class="meta-key"><span class="plat-dot" style="background:rgba(255,255,255,0.35)"></span>DICE</span><span class="meta-val">{fmt_num(dice_tickets)} billets</span></div>'''
    
    # ── Capacity day rows ──
    cap_day_rows = []
    for dn in day_names:
        display = DAY_DISPLAY_NAMES.get(dn, dn.capitalize())
        cap_day_rows.append(f'<div class="inset-row"><span class="k">{display}</span><span class="v">{fmt_num(day_configs[dn]["day_capacity"])}</span></div>')
    
    compare_cap_day_rows = []
    if event_config_prev:
        prev_day_configs = {d['day_name'].lower(): d for d in event_config_prev['days']}
        for dn in [d['day_name'].lower() for d in event_config_prev['days']]:
            display = DAY_DISPLAY_NAMES.get(dn, dn.capitalize())
            compare_cap_day_rows.append(f'<div class="inset-row"><span class="k">{display}</span><span class="v">{fmt_num(prev_day_configs[dn]["day_capacity"])}</span></div>')
    
    # ── Stacked bar segments ──
    day_presence = metrics['day_presence']
    stacked_segs = []
    pct_legend_items = []
    for i, dn in enumerate(day_names):
        pres = day_presence.get(dn, 0)
        cap = day_configs[dn]['day_capacity']
        day_pct = (pres / total_capacity * 100) if total_capacity > 0 else 0
        fill_pct = (pres / cap * 100) if cap > 0 else 0
        abbrev = DAY_ABBREV.get(dn, dn[:3].capitalize())
        stacked_segs.append(f'<div class="stacked-seg" style="width:{day_pct:.1f}%;background:var(--day-{i})"></div>')
        pct_legend_items.append(f'<div class="pct-legend-item"><div class="pct-dot" style="background:var(--day-{i})"></div>{abbrev} {fill_pct:.0f}%</div>')
    
    # ── Stacked bar (no warmup version) ──
    if warmup_day:
        stacked_segs_nw = []
        pct_legend_items_nw = []
        total_cap_nw = total_capacity - warmup_capacity
        for i, dn in enumerate(day_names):
            if dn == warmup_day:
                continue
            pres = day_presence.get(dn, 0)
            cap = day_configs[dn]['day_capacity']
            day_pct_nw = (pres / total_cap_nw * 100) if total_cap_nw > 0 else 0
            fill_pct_nw = (pres / cap * 100) if cap > 0 else 0
            abbrev = DAY_ABBREV.get(dn, dn[:3].capitalize())
            stacked_segs_nw.append(f'<div class="stacked-seg" style="width:{day_pct_nw:.1f}%;background:var(--day-{i})"></div>')
            pct_legend_items_nw.append(f'<div class="pct-legend-item"><div class="pct-dot" style="background:var(--day-{i})"></div>{abbrev} {fill_pct_nw:.0f}%</div>')
    else:
        stacked_segs_nw = stacked_segs
        pct_legend_items_nw = pct_legend_items

    # ── Velocity rows ──
    vel_rows_parts = []
    vel_windows = [(3, 'Vélocité 3j'), (7, 'Vélocité 7j'), (14, 'Vélocité 14j'), (30, 'Vélocité 30j')]
    
    # Add column headers if we have comparison data
    if has_comparison and tickets_prev_filtered:
        current_year = event_config['event_date_first'].year
        compare_year = event_config_prev['event_date_first'].year
        vel_rows_parts.append(f'<div style="display:grid;grid-template-columns:1fr 50px 44px 44px;gap:4px 10px;align-items:baseline;font-size:0.85em">')
        # Header row
        vel_rows_parts.append(f'<span style="color:var(--text-muted);font-weight:500">Fenêtre</span><span style="color:var(--text-muted);font-weight:500;text-align:right">{current_year}</span><span style="color:rgba(255,255,255,0.5);font-weight:500;text-align:right">{compare_year}</span><span style="color:rgba(255,255,255,0.5);font-weight:500;text-align:right">Δ</span>')
    else:
        vel_rows_parts.append('<div style="display:grid;grid-template-columns:1fr auto;gap:4px 10px;align-items:baseline;font-size:0.85em">')
    
    for window_days, label in vel_windows:
        # Calculate velocity for this window (only complete days up to velocity cutoff)
        if tickets:
            threshold = cutoff_date - timedelta(days=window_days)
            count = len([t for t in tickets if threshold < t['order_date'] <= cutoff_date and t.get('is_paid', 1) == 1])
            vel = count / window_days
        else:
            vel = 0
        
        if has_comparison and tickets_prev_filtered:
            comparison_mode = event_config.get('comparison_mode', 'j_minus')
            if comparison_mode == 'days_since_launch' and event_config.get('launch_date') and event_config_prev.get('launch_date'):
                days_since_launch = (cutoff_date - event_config['launch_date']).days
                prev_cutoff = event_config_prev['launch_date'] + timedelta(days=days_since_launch)
            else:
                prev_event_date = event_config_prev['event_date_first']
                prev_cutoff = prev_event_date - timedelta(days=days_remaining)
            prev_threshold = prev_cutoff - timedelta(days=window_days)
            prev_count = len([t for t in tickets_prev_full if prev_threshold < t['order_date'] <= prev_cutoff and t.get('is_paid', 1) == 1])
            prev_vel = prev_count / window_days
            if prev_vel > 0:
                delta = ((vel - prev_vel) / prev_vel * 100)
                color = 'var(--green)' if delta >= 0 else 'var(--red)'
                vel_rows_parts.append(f'<span class="meta-key">{label}</span><span style="color:#fff;font-weight:500;text-align:right">{int(vel)}/j</span><span style="color:rgba(255,255,255,0.55);text-align:right">{int(prev_vel)}/j</span><span style="color:{color};font-weight:500;text-align:right">{delta:+.0f}%</span>')
            else:
                vel_rows_parts.append(f'<span class="meta-key">{label}</span><span style="color:#fff;font-weight:500;text-align:right">{int(vel)}/j</span><span style="color:rgba(255,255,255,0.35);text-align:right">-</span><span style="color:var(--text-dim);text-align:right">-</span>')
        else:
            vel_rows_parts.append(f'<span class="meta-key">{label}</span><span style="color:#fff;font-weight:500;text-align:right">{int(vel)}/j</span>')
    
    vel_rows_parts.append('</div>')
    
    velocity_rows = '\n    '.join(vel_rows_parts)
    
    # ── Presence card values ──
    tickets_paid = metrics['total_tickets_paid']
    tickets_invitations = metrics.get('invitation_tickets', 0)
    tickets_jc = metrics.get('jeu_concours_tickets', 0)
    tickets_total = metrics['total_tickets_all']
    
    # ── Tickets to presence rows ──
    t2p_rows = []
    # Single-day tickets
    single_day_count = sum(1 for t in tickets if t['ticket_type'] in day_names) if tickets else 0
    if single_day_count > 0:
        t2p_rows.append(f'<div class="inset-row"><span class="k">Billets 1 jour</span><span class="v">{fmt_num(single_day_count)} <span style="font-size:0.85em;color:var(--text-dim)">× 1</span></span></div>')
    
    deux_j = metrics.get('deux_jours_tickets', 0)
    if deux_j > 0:
        t2p_rows.append(f'<div class="inset-row"><span class="k">Pass 2 Jours</span><span class="v">{fmt_num(deux_j)} <span style="font-size:0.85em;color:var(--text-dim)">× 2</span></span></div>')
    
    trois_j = metrics.get('trois_jours_tickets', 0)
    if trois_j > 0:
        t2p_rows.append(f'<div class="inset-row"><span class="k">Pass 3 Jours</span><span class="v">{fmt_num(trois_j)} <span style="font-size:0.85em;color:var(--text-dim)">× {num_days}</span></span></div>')
    
    free_count = tickets_invitations + tickets_jc + metrics.get('group_discount_free_tickets', 0)
    if free_count > 0:
        t2p_rows.append(f'<div class="inset-row"><span class="k">Gratuits (inv + groupes)</span><span class="v">{fmt_num(free_count)} <span style="font-size:0.85em;color:var(--text-dim)">× 1</span></span></div>')
    
    # ── Compare presence day rows (now shown in Par Jour detail) ──
    compare_presence_day_rows = []
    
    # Build day-position mapping for DSL mode (Day 1 ↔ Day 1 regardless of name)
    comparison_mode = event_config.get('comparison_mode', 'j_minus') if event_config else 'j_minus'
    day_name_map = {}  # maps current day_name → prev day_name for comparison
    if comparison_mode == 'days_since_launch' and event_config_prev:
        prev_day_names = [d['day_name'].lower() for d in event_config_prev['days']]
        for idx, dn in enumerate(day_names):
            if idx < len(prev_day_names):
                day_name_map[dn] = prev_day_names[idx]  # Day 1 → Day 1, Day 2 → Day 2
    
    def _get_prev_day_presence(dn):
        """Get previous year presence for a day, using position mapping in DSL mode."""
        if not metrics_prev:
            return 0
        mapped_dn = day_name_map.get(dn, dn)  # DSL: map by position; J-minus: same name
        return metrics_prev['day_presence'].get(mapped_dn, 0)
    
    # ── Day summary blocks (Par Jour) ──
    day_summary_blocks = []
    day_pacing_charts = []
    for i, dn in enumerate(day_names):
        dc = day_configs[dn]
        cap = dc['day_capacity']
        pres = day_presence.get(dn, 0)
        fill_pct = (pres / cap * 100) if cap > 0 else 0
        display = DAY_DISPLAY_NAMES.get(dn, dn.capitalize())
        date_display = f"{dc['day_date'].day} {MONTHS_FR_FULL[dc['day_date'].month].lower()} {current_year}" if dc['day_date'] else ""
        dv = metrics['day_velocity'].get(dn, {})
        vel_14d = dv.get('velocity_14d', 0)
        remaining = cap - pres
        
        # YoY delta for this day
        yoy_pill = ""
        if has_comparison and metrics_prev:
            prev_pres = _get_prev_day_presence(dn)
            if prev_pres > 0:
                delta = ((pres - prev_pres) / prev_pres * 100)
                pill_class = 'green' if delta >= 0 else 'red'
                yoy_pill = f'<span class="tag-pill {pill_class}">{delta:+.0f}% vs {compare_year}</span>'
        
        day_summary_blocks.append(f'''<div class="day-summary"><div class="day-row-main"><div class="day-accent" style="background:var(--day-{i})"></div><div class="day-content"><div class="day-top"><div class="day-name" style="color:var(--day-{i})">{display}</div><div class="day-date">{date_display}</div></div><div class="day-presence"><span class="dj-count">{fmt_num(pres)}</span><span class="dj-cap">/ {fmt_num(cap)}</span></div><div class="day-bar"><div class="day-bar-fill" style="width:{min(fill_pct,100):.1f}%;background:var(--day-{i})"></div></div><div class="day-meta"><span class="dj-pct" style="color:var(--day-{i})">{fill_pct:.1f}%</span>{yoy_pill}</div><div style="height:8px"></div><div class="meta-row"><span class="meta-key">Vélocité 14j</span><span class="meta-val">{int(vel_14d)} /jour</span></div><div style="height:4px"></div><div class="meta-row"><span class="meta-key">Restants</span><span class="meta-val">{fmt_num(remaining)}</span></div></div></div></div>''')
        
        # Per-day detail breakdown (replacing Courbe de remplissage)
        db = metrics['day_breakdown'].get(dn, {})
        day_paid = db.get('paid', 0)
        day_free = db.get('free', 0)
        day_rev = db.get('revenue', 0)
        day_avg = db.get('avg_price', 0)
        day_sg = db.get('sg', 0)
        day_dice = db.get('dice', 0)
        day_by_type = db.get('by_type', {})
        
        # Type breakdown rows
        type_display = {'2-jours': 'Pass 2 Jours', '3-jours': 'Pass 3 Jours'}
        type_rows = ''
        for tt, count in sorted(day_by_type.items(), key=lambda x: -x[1]):
            tt_label = type_display.get(tt, tt.capitalize())
            type_rows += f'<div class="inset-row"><span class="k">{tt_label}</span><span class="v">{fmt_num(count)}</span></div>'
        
        # Per-day presence breakdown by ticket type
        key = f'presence_{dn}'
        day_tix = [t for t in tickets if t.get(key, 0) > 0]
        # Count by ticket type category
        day_single = sum(1 for t in day_tix if t['ticket_type'] in day_names)
        day_pass2 = sum(1 for t in day_tix if t['ticket_type'] == '2-jours')
        day_pass3 = sum(1 for t in day_tix if t['ticket_type'] == '3-jours')
        day_total = day_single + day_pass2 + day_pass3  # = presence for this day
        
        detail_rows = ''
        if day_single > 0:
            detail_rows += f'<div class="inset-row"><span class="k">Billets 1 jour</span><span class="v">{fmt_num(day_single)}</span></div>'
        if day_pass2 > 0:
            detail_rows += f'<div class="inset-row"><span class="k">Pass 2 Jours</span><span class="v">{fmt_num(day_pass2)}</span></div>'
        if day_pass3 > 0:
            detail_rows += f'<div class="inset-row"><span class="k">Pass 3 Jours</span><span class="v">{fmt_num(day_pass3)}</span></div>'
        
        # YoY for this day
        day_yoy = ''
        if has_comparison and metrics_prev:
            prev_pres_day = _get_prev_day_presence(dn)
            if prev_pres_day > 0:
                d_pct = ((day_total - prev_pres_day) / prev_pres_day * 100)
                c_yoy = 'var(--green)' if d_pct >= 0 else 'var(--red)'
                day_yoy = f'<div class="detail-inset" style="margin-top:10px"><div class="inset-label">vs {compare_year} (même J-{days_remaining_display})</div><div class="inset-row"><span class="k">Présence totale</span><span class="v">{fmt_num(prev_pres_day)} <span class="change-tag" style="color:{c_yoy}">{d_pct:+.0f}%</span></span></div></div>'
        
        day_pacing_charts.append(f'''<div class="detail-day"><div class="detail-day-header"><div class="detail-day-dot" style="background:var(--day-{i})"></div><span class="detail-day-name" style="color:var(--day-{i})">{display}</span></div><div class="day-detail-grid">{detail_rows}<div class="inset-sep"></div><div class="inset-row"><span class="k" style="font-weight:600">Présence totale</span><span class="v" style="font-weight:700">{fmt_num(day_total)}</span></div>{day_yoy}</div></div>''')
    
    # ── Ticket groups (breakdown table) ──
    ticket_groups_html = _generate_ticket_groups_v3(tickets, event_config, has_comparison, metrics_prev, compare_year) if tickets else ""
    
    # ── Suivi des ventes ──
    suivi_daily, suivi_weekly, remaining_days_count, remaining_weeks_count = _generate_suivi_v3(
        tickets, tickets_prev_full, cutoff_date, event_config, event_config_prev, days_remaining, cutoff_cumulative=cutoff_cumulative
    ) if tickets else ("", "", 0, 0)
    
    # ── Projection quadrant cards ──
    proj_cards, proj_tabs, proj_panels, proj_methodology, proj_day_ids, proj_tab_classes = _generate_projection_v3(
        tickets, tickets_prev_full, cutoff_date, event_config, event_config_prev, metrics, day_presence, days_remaining_display
    ) if tickets else ("", "", "", "", "'day0'", "day0:'active'")
    
    # ── Velocity chart JS ──
    velocity_chart_js = _generate_velocity_chart_js_v3(tickets, tickets_prev_full, cutoff_date, event_config, event_config_prev, days_remaining)
    velocity_14d_chart_js = _generate_velocity_14d_chart_js_v3(tickets, tickets_prev_full, cutoff_date, event_config, event_config_prev, days_remaining)
    revenue_chart_js = _generate_revenue_chart_js_v3(tickets, tickets_prev_full, cutoff_date, event_config, event_config_prev, days_remaining)
    
    # ── Projection charts JS ──
    proj_charts_js = _generate_projection_charts_js_v3(tickets, tickets_prev_full, cutoff_date, event_config, event_config_prev, metrics, day_presence)
    
    # ── Platforms list ──
    platforms = set()
    if tickets:
        for t in tickets:
            platforms.add(t['platform'])
    platforms_list = ' · '.join(sorted(platforms)) if platforms else "-"
    
    # ── Edition badge ──
    # Count how many events with same brand exist in config history
    edition_badge = event_config.get('notes', '') or f"{num_days}j"
    # Simple: if compare_to exists, at least 2nd edition
    if has_comparison:
        edition_badge = "2ème éd."  # Will be overridden by config if provided
    else:
        edition_badge = "1ère éd."
    
    # ── Last ticket sold datetime (from Shotgun order_datetime) ──
    last_ticket_dt = None
    if tickets:
        datetimes = [t.get('order_datetime') for t in tickets if t.get('order_datetime')]
        if datetimes:
            last_ticket_dt = max(datetimes)
    last_ticket_str = last_ticket_dt.strftime('%d/%m · %H:%M') if last_ticket_dt else '-'

    # ── Generation time (placeholder - will be replaced just before file write) ──
    generation_time = '{{GENERATION_TIME_PLACEHOLDER}}'

    # ── Nav: session switcher + details page data ──
    # Short name: strip brand prefix and year suffix
    raw_name = event_config['event_name']
    event_short = raw_name.split(' 20')[0].strip()
    # Remove common brand prefixes
    for prefix in ['ML x ', 'ML × ', 'Madame Loyal x ', 'Madame Loyal × ', 'Sonora ']:
        if event_short.startswith(prefix):
            event_short = event_short[len(prefix):]
            break
    if len(event_short) > 18:
        event_short = event_short[:18].rsplit(' ', 1)[0]
    # Initials: from the cleaned short name (ensure 2+ chars)
    init_words = event_short.split()
    if len(init_words) >= 2:
        event_initials = (init_words[0][0] + init_words[1][0]).upper()
    else:
        event_initials = event_short[:2].upper()
    event_date_first = event_config['event_date_first']
    # Event code: short ID + first event date (matches BudgetFlow: "ML 130326")
    eid = event_config['event_id']
    eid_prefix = eid.split('_')[0].upper()
    if len(eid_prefix) > 5:
        eid_prefix = eid_prefix[:3]
    event_code = f"{eid_prefix} {event_date_first.strftime('%d%m%y')}" if event_date_first else eid
    j_minus_label = 'Terminé' if days_remaining_display <= 0 else f'J-{days_remaining_display}'
    sale_status_dot = 'green' if days_remaining_display > 0 else 'text-dim'
    poster_url = event_config.get('poster_url', '')
    if not poster_url:
        poster_url = 'https://madameloyal.github.io/budgetflow/LOGO_ROND_JAUNE.png'
    
    # Session switcher: build options from all active events in config
    session_options = ''
    try:
        all_events = load_event_config(CONFIG_PATH)
        for eid, ev in all_events.items():
            if ev.get('status') != 'active' or ev.get('merge_into'):
                continue
            fname = ev.get('output_filename', '')
            if not fname:
                fname = eid.split('_')[0] + '.html'
            selected = ' selected' if eid == event_config['event_id'] else ''
            label = ev['event_name']
            session_options += f'<option value="{fname}"{selected}>{label}</option>\n'
    except Exception:
        session_options = f'<option value="" selected>{event_config["event_name"]}</option>'
    
    # Capacity per day label
    day_caps = set(d['day_capacity'] for d in event_config['days'])
    if len(day_caps) == 1:
        cap_per_day = f"{fmt_num(day_caps.pop()).replace(',', ' ')}/jour"
    else:
        cap_per_day = ' · '.join(f"{d['day_name']} {fmt_num(d['day_capacity']).replace(',', ' ')}" for d in event_config['days'])
    
    # Details: platform URLs
    dice_mio_id = event_config.get('dice_mio_id', '')
    dice_dashboard_url = f"https://dice.fm/partner/events/{dice_mio_id}" if dice_mio_id else ''
    shotgun_event_id = event_config.get('shotgun_event_id', '')
    shotgun_dashboard_url = event_config.get('shotgun_url', '')
    dice_public_url = event_config.get('dice_url', '')
    shotgun_public_url = event_config.get('shotgun_url', '')
    
    def _url_short(url, max_len=30):
        """Shorten URL for display."""
        if not url: return ''
        short = url.replace('https://', '').replace('http://', '').replace('www.', '')
        return short[:max_len] + '...' if len(short) > max_len else short
    
    # Details: comparison info
    compare_venue = ''
    compare_first_sale = ''
    compare_selling_period = ''
    compare_total_tickets = ''
    compare_total_revenue_str = ''
    comparison_mode_label = ''
    comparison_mode_desc = ''
    if event_config_prev:
        compare_venue = f"{event_config_prev.get('venue', '')}, {event_config_prev.get('city', '')}"
        comp_mode = event_config.get('comparison_mode', 'j_minus')
        if comp_mode == 'days_since_launch':
            comparison_mode_label = 'Event-end anchoring · days_since_launch'
            comparison_mode_desc = 'Ancrage fin d\'événement (même distance de la fin)'
        else:
            comparison_mode_label = 'J-minus · weekday matched'
            comparison_mode_desc = 'J-X avant l\'événement, même jour de semaine'
        if tickets_prev_full:
            prev_dates = sorted(set(t['order_date'] for t in tickets_prev_full))
            if prev_dates:
                first_sale_d = prev_dates[0]
                if isinstance(first_sale_d, str):
                    first_sale_d = datetime.strptime(first_sale_d, '%Y-%m-%d').date()
                compare_first_sale = f"{first_sale_d.day} {MONTHS_FR_FULL[first_sale_d.month].lower()} {first_sale_d.year}"
                last_sale_d = prev_dates[-1]
                if isinstance(last_sale_d, str):
                    last_sale_d = datetime.strptime(last_sale_d, '%Y-%m-%d').date()
                compare_selling_period = f"{(last_sale_d - first_sale_d).days} jours"
            paid_prev = [t for t in tickets_prev_full if t.get('is_paid', 1) == 1]
            compare_total_tickets = fmt_num(len(paid_prev))
            compare_total_revenue_str = fmt_revenue(sum(t.get('price', 0) for t in paid_prev))
    
    # Details: days HTML
    details_days_rows = []
    for i, d in enumerate(event_config['days']):
        day_tag_colors = ['rgba(168,85,247,.08)', 'rgba(99,102,241,.1)', 'rgba(251,191,36,.08)']
        day_tag_text_colors = ['#c4b5fd', '#818cf8', '#fbbf24']
        ci = i % len(day_tag_colors)
        day_date_str = f'{d["day_date"].day} {MONTHS_FR_FULL[d["day_date"].month].lower()}' if d["day_date"] else ''
        details_days_rows.append(
            f'<div class="det-row"><span class="det-k">{d["day_name"]} {day_date_str}</span>'
            f'<span class="det-v">{fmt_num(d["day_capacity"]).replace(",", " ")} places '
            f'<span class="badge badge-edition" style="font-size:10px;padding:2px 7px;background:{day_tag_colors[ci]};color:{day_tag_text_colors[ci]}">Jour {i+1}</span></span></div>'
        )

    # ═══ BUILD REPLACEMENTS ═══
    replacements = {
        # Event config
        'EVENT_NAME': event_config['event_name'],
        'BRAND': event_config.get('brand', 'Madame Loyal'),
        'EVENT_DATES_SHORT': dates_short,
        'EVENT_DATES_COMPACT': dates_compact,
        'VENUE': event_config['venue'],
        'CITY': event_config.get('city', ''),
        'EDITION_BADGE': edition_badge,
        'SALE_STATUS': 'Terminé' if days_remaining_display <= 0 else 'En vente',
        'LOGIN_PASSWORD': event_config.get('login_password', ''),
        'LOGIN_BG_IMAGE': event_config.get('login_bg_image', 'upload.JPG'),
        'EVENT_ID': event_config.get('event_id', ''),
        'OUTPUT_FILENAME': event_config.get('output_filename', '') or (event_config.get('event_id', '').split('_')[0] + '.html'),
        'IS_TERMINE': 'true' if days_remaining_display <= 0 else '',
        'CURRENT_YEAR': current_year,
        'NUM_DAYS': str(num_days),
        'NUM_DAYS_PLURAL': 's' if num_days > 1 else '',
        'CAPACITY_TOTAL_FMT': fmt_num(total_capacity).replace(',', ' '),
        'DAYS_ON_SALE': str(days_on_sale),
        'SALE_START_DATE': sale_start,
        'DAYS_REMAINING': str(days_remaining_display),
        'WEEKS_REMAINING_BADGE': 'Terminé' if days_remaining_display <= 0 else f'J-{days_remaining_display}',
        'DATA_DATE': fmt_date_fr(cutoff_cumulative) if cutoff_cumulative else fmt_date_fr(cutoff_date),
        'DATA_TIME': generation_time,
        'LAST_TICKET_TIME': last_ticket_str,
        'PLATFORMS_LIST': platforms_list,
        
        # Nav
        'EVENT_SHORT_NAME': event_short,
        'EVENT_SHORT_INITIALS': event_initials,
        'EVENT_CODE': event_code,
        'J_MINUS_LABEL': j_minus_label,
        'SALE_STATUS_DOT': sale_status_dot,
        'POSTER_URL': poster_url,
        'SESSION_SWITCHER_OPTIONS': session_options,
        
        # Détails page
        'CAPACITY_PER_DAY_LABEL': cap_per_day,
        'DICE_MIO_ID': dice_mio_id,
        'DICE_DASHBOARD_URL': dice_dashboard_url,
        'SHOTGUN_EVENT_ID': shotgun_event_id,
        'SHOTGUN_DASHBOARD_URL': shotgun_dashboard_url,
        'DICE_PUBLIC_URL': dice_public_url,
        'DICE_PUBLIC_URL_SHORT': _url_short(dice_public_url),
        'SHOTGUN_PUBLIC_URL': shotgun_public_url,
        'SHOTGUN_PUBLIC_URL_SHORT': _url_short(shotgun_public_url),
        'COMPARE_VENUE': compare_venue,
        'COMPARISON_MODE_LABEL': comparison_mode_label,
        'COMPARISON_MODE_DESCRIPTION': comparison_mode_desc,
        'COMPARE_FIRST_SALE': compare_first_sale,
        'COMPARE_SELLING_PERIOD': compare_selling_period,
        'COMPARE_TOTAL_TICKETS': compare_total_tickets,
        'COMPARE_TOTAL_REVENUE': compare_total_revenue_str,
        'DETAILS_DAYS_HTML': '\n'.join(details_days_rows),
        
        # Comparison
        'COMPARE_EVENT_NAME': compare_event_name,
        'COMPARE_YEAR': compare_year,
        'COMPARE_DATES': compare_dates,
        'COMPARE_CAPACITY_FMT': fmt_num(prev_capacity).replace(',', ' ') if prev_capacity else '',
        'COMPARE_CAP_DELTA': compare_cap_delta,
        'COMPARE_REVENUE': compare_revenue,
        'REVENUE_VS_COMPARE': revenue_vs_compare,
        
        # Revenue
        'RING_OFFSET': str(ring_offset),
        'SELL_THROUGH_PCT': f'{sell_through_pct:.0f}',
        'REVENUE_TOTAL': fmt_revenue(total_revenue),
        'REVENUE_YOY': revenue_yoy,
        'REVENUE_YOY_CLASS': revenue_yoy_class if has_comparison else '',
        'AVG_PRICE': f'€{avg_price:.2f}',
        'AVG_PRICE_DELTA': avg_price_delta,
        'REVENUE_PROJECTION': fmt_revenue(revenue_projection),
        'REVENUE_IF_SOLDOUT': fmt_revenue(revenue_if_soldout),
        
        # Presence
        'PRESENCE_TOTAL': fmt_num(metrics['total_presence']),
        'PRESENCE_PCT_TOTAL': f'{sell_through_pct:.1f}',
        'PRESENCE_TOTAL_RAW': str(int(metrics['total_presence'])),
        'CAPACITY_TOTAL_RAW': str(int(total_capacity)),
        'PRESENCE_NO_WARMUP': str(presence_no_warmup),
        'CAPACITY_NO_WARMUP': str(capacity_no_warmup),
        'PCT_NO_WARMUP': str(pct_no_warmup),
        'HAS_WARMUP': 'true' if warmup_day is not None else 'false',
        'WARMUP_DAY_NAME': warmup_day.capitalize() if warmup_day else '',
        'PRESENCE_YOY': presence_yoy,
        'PRESENCE_YOY_CLASS': presence_yoy_class if has_comparison else '',
        'TICKETS_PAID': fmt_num(tickets_paid),
        'TICKETS_INVITATIONS': fmt_num(tickets_invitations),
        'TICKETS_JC': fmt_num(tickets_jc),
        'TICKETS_GROUP_FREE': fmt_num(metrics.get('group_discount_free_tickets', 0)),
        'TICKETS_TOTAL': fmt_num(tickets_total),
        'COMPARE_PRESENCE_TOTAL': fmt_num(metrics_prev['total_presence']) if metrics_prev else '',
        
        # Layout
        'ACCENT_GRADIENT': accent_gradient,
        'PROJ_GRID_COLS': proj_grid_cols,
        'DAY_TAB_ACTIVE_CSS': '\n'.join(tab_css_lines),
        
        # HTML blocks
        'PLATFORM_SPLIT_BAR': platform_split_bar,
        'PLATFORM_TICKET_COUNTS': platform_ticket_counts,
        'PLATFORM_ROWS': platform_rows,
        'CAPACITY_DAY_ROWS': '\n'.join(cap_day_rows) if num_days > 1 else '',
        'COMPARE_CAPACITY_DAY_ROWS': '\n'.join(compare_cap_day_rows),
        'STACKED_BAR_SEGMENTS': ''.join(stacked_segs),
        'PCT_LEGEND_ITEMS': ''.join(pct_legend_items) if num_days > 1 else '',
        'STACKED_BAR_SEGMENTS_NW': ''.join(stacked_segs_nw),
        'PCT_LEGEND_ITEMS_NW': ''.join(pct_legend_items_nw) if num_days > 1 else '',
        'PRESENCE_PCT_NW': f'{pct_no_warmup:.1f}',
        'VELOCITY_ROWS': velocity_rows,
        'TICKETS_TO_PRESENCE_ROWS': '\n'.join(t2p_rows),
        'COMPARE_PRESENCE_DAY_ROWS': '\n'.join(compare_presence_day_rows),
        'DAY_SUMMARY_BLOCKS': '\n'.join(day_summary_blocks),
        'DAY_PACING_CHARTS': '\n'.join(day_pacing_charts),
        'TICKET_GROUPS': ticket_groups_html,
        'SUIVI_DAILY_ROWS': suivi_daily,
        'SUIVI_WEEKLY_ROWS': suivi_weekly,
        'SUIVI_REMAINING_DAYS': str(remaining_days_count),
        'SUIVI_BTN_HIDE': 'style="display:none"' if remaining_days_count == 0 else '',
        'SUIVI_REMAINING_WEEKS': str(remaining_weeks_count),
        'SUIVI_WEEK_BTN_HIDE': 'style="display:none"' if remaining_weeks_count == 0 else '',
        'SUIVI_REMAINING_DAYS_LABEL': f"{remaining_days_count} jour{'s' if remaining_days_count > 1 else ''} restant{'s' if remaining_days_count > 1 else ''}",
        'SUIVI_REMAINING_WEEKS_LABEL': f"{remaining_weeks_count} semaine{'s' if remaining_weeks_count > 1 else ''} restante{'s' if remaining_weeks_count > 1 else ''}",
        
        # Projection
        'PROJECTION_QUADRANT_CARDS': proj_cards,
        'PROJECTION_DAY_TABS': proj_tabs,
        'PROJECTION_DAY_CHART_PANELS': proj_panels,
        'PROJECTION_METHODOLOGY_HTML': proj_methodology,
        
        # JS
        'PROJ_DAY_IDS_JS': proj_day_ids,
        'DAY_TAB_CLASSES_JS': proj_tab_classes,
        'VELOCITY_CHART_JS': velocity_chart_js,
        'VELOCITY_14D_CHART_JS': velocity_14d_chart_js,
        'REVENUE_CHART_JS': revenue_chart_js,
        'PROJECTION_CHARTS_JS': proj_charts_js,
    }
    
    for key, val in replacements.items():
        html = html.replace('{{' + key + '}}', str(val))
    
    # DSL mode: swap column header label from "(même jour)" to "(même période)"
    comparison_mode = event_config.get('comparison_mode', 'j_minus') if event_config else 'j_minus'
    if comparison_mode == 'days_since_launch':
        html = html.replace('(même jour)', '(même période)')
        # Swap "à J-X" labels in KPI cards to DSL-appropriate text
        html = html.replace(f'à J-{days_remaining_display}', '(même période)')
        html = html.replace(f'même J-{days_remaining_display}', 'même période')
        # Also update J-X info bubbles to reflect DSL alignment
        html = html.replace('à nombre de jours égal avant l\'événement', 'à même stade de vente (jours depuis lancement)')
        html = html.replace('au même point du calendrier', 'au même stade de la campagne de vente')
    
    # Check for unreplaced
    remaining_placeholders = re.findall(r'\{\{[A-Z_]+\}\}', html)
    if remaining_placeholders:
        print_warning(f"Unreplaced placeholders ({len(remaining_placeholders)}): {sorted(set(remaining_placeholders))}")
    else:
        print_success("All placeholders replaced!")
    
    return html


# ── Helper: Ticket groups for breakdown table ──
def _generate_ticket_groups_v3(tickets, event_config, has_comparison, metrics_prev, compare_year):
    """Generate ticket breakdown groups in the v3 format (collapsible groups)."""
    day_names = [d['day_name'].lower() for d in event_config['days']]
    
    # Classify tickets by access level
    groups = {
        'regular': {'name': 'Billets Réguliers', 'products': defaultdict(lambda: {'count': 0, 'revenue': 0})},
        'premium': {'name': 'Premium / VIP', 'products': defaultdict(lambda: {'count': 0, 'revenue': 0})},
        'free': {'name': 'Invitations', 'products': defaultdict(lambda: {'count': 0, 'revenue': 0})},
    }
    
    # Display names: use ticket_type for known categories, product_name for unknown
    type_display = {
        '3-jours': 'Pass 3 Jours', '2-jours': 'Pass 2 Jours',
        'jeudi': 'Jeudi', 'vendredi': 'Vendredi', 'samedi': 'Samedi', 'dimanche': 'Dimanche',
    }
    
    total_tickets = len(tickets)
    
    for t in tickets:
        al = t['access_level']
        tt = t['ticket_type']
        
        # Get display name: known type → nice label, unknown → use product_name
        if tt in type_display:
            name = type_display[tt]
        else:
            # Fallback: use product_name if available, else format ticket_type
            pn = t.get('product_name', '').strip()
            name = pn if pn else tt.replace('_', ' ').title()
        
        if al in ('vip', 'backstage'):
            prefix = 'VIP ' if al == 'vip' else 'Backstage '
            bucket = 'premium'
            name = prefix + name
        elif al in ('invitation', 'jeu_concours'):
            bucket = 'free'
            name = 'Invitations' if al == 'invitation' else 'Jeu Concours'
        else:
            bucket = 'regular'
        
        groups[bucket]['products'][name]['count'] += 1
        groups[bucket]['products'][name]['revenue'] += t['price']
    
    html_parts = []
    for bucket_key in ['regular', 'premium', 'free']:
        group = groups[bucket_key]
        products = dict(group['products'])
        if not products:
            continue
        
        group_total = sum(p['count'] for p in products.values())
        group_pct = (group_total / total_tickets * 100) if total_tickets > 0 else 0
        group_rev = sum(p['revenue'] for p in products.values())
        group_avg = group_rev / group_total if group_total > 0 else 0
        
        is_free = bucket_key == 'free'
        opacity = ' style="opacity:0.6"' if is_free else ''
        vs_class = 'neutral' if is_free else 'pos'
        vs_text = '-' if is_free else '+0%'  # Placeholder - real comparison TBD
        price_text = 'gratuit' if is_free else f'€{group_avg:.0f}'
        
        html_parts.append(f'''<div class="group-header" onclick="toggleGroup(this)"><div class="group-left"><span class="group-arrow"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg></span><span class="group-name"{opacity}>{group["name"]}</span></div><span class="group-total"{opacity}>{fmt_num(group_total)}</span><span class="group-pct"{opacity}>{group_pct:.1f}%</span><span class="group-price"{opacity}>{price_text}</span></div>''')
        html_parts.append('<div class="group-body">')
        
        for name, data in sorted(products.items(), key=lambda x: -x[1]['count']):
            pct = (data['count'] / total_tickets * 100) if total_tickets > 0 else 0
            avg = data['revenue'] / data['count'] if data['count'] > 0 else 0
            price_display = f'€{avg:.0f}' if avg > 0 else '€0'
            row_opacity = ' style="opacity:0.6"' if is_free else ''
            html_parts.append(f'    <div class="pr-row"{row_opacity}><div class="pr-name">{name}</div><div class="pr-num">{fmt_num(data["count"])}</div><div class="pr-pct">{pct:.1f}%</div><div class="pr-price">{price_display}</div></div>')
        
        html_parts.append('</div>')
    
    # Grand total row
    total_count = len(tickets)
    total_rev = sum(t['price'] for t in tickets)
    total_avg = total_rev / total_count if total_count > 0 else 0
    total_paid = sum(1 for t in tickets if t.get('is_paid', 1) == 1)
    total_free = total_count - total_paid
    
    html_parts.append(f'<div class="group-header grand-total" style="margin-top:8px;border-top:1px solid var(--border);padding-top:12px"><div class="group-left"><span class="group-arrow" style="visibility:hidden"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M9 18l6-6-6-6"/></svg></span><span class="group-name" style="font-weight:700">Total</span></div><span class="group-total" style="font-weight:700">{fmt_num(total_count)}</span><span class="group-pct" style="font-weight:700">100%</span><span class="group-price">€{total_avg:.0f}</span></div>')
    
    return '\n    '.join(html_parts)


# ── Helper: Suivi des ventes ──
def _generate_suivi_v3(tickets, tickets_prev_full, cutoff_date, event_config, event_config_prev, days_remaining, cutoff_cumulative=None):
    
    def _prev_match_dow(current_date, event_date_cur, prev_event_date):
        """Find the previous year date that matches BOTH the same J-X position AND the same weekday.
        This ensures we compare Fri-to-Fri, Sat-to-Sat etc. which is critical for festival sales patterns."""
        j_x = (event_date_cur - current_date).days
        candidate = prev_event_date - timedelta(days=j_x)
        # Shift to same weekday as current_date
        wd_diff = current_date.weekday() - candidate.weekday()
        if wd_diff > 3: wd_diff -= 7
        if wd_diff < -3: wd_diff += 7
        return candidate + timedelta(days=wd_diff)
    
    def _prev_match_dsl(current_date, launch_date_cur, launch_date_prev):
        """Find the previous year date at the same distance from event end, matched to same weekday.
        All pre-launch sales accumulate naturally in the cumulative on the first row."""
        cur_end = event_config['event_date_last'] + timedelta(days=1)
        prev_end = event_config_prev['event_date_last'] + timedelta(days=1)
        days_before_end = (cur_end - current_date).days
        candidate = prev_end - timedelta(days=days_before_end)
        # Shift to same weekday as current_date
        wd_diff = current_date.weekday() - candidate.weekday()
        if wd_diff > 3: wd_diff -= 7
        if wd_diff < -3: wd_diff += 7
        return candidate + timedelta(days=wd_diff)
    
    # Determine alignment mode
    comparison_mode = event_config.get('comparison_mode', 'j_minus') if event_config else 'j_minus'
    use_dsl = (comparison_mode == 'days_since_launch' 
               and event_config.get('launch_date') 
               and event_config_prev and event_config_prev.get('launch_date'))
    
    def _match_prev_date(current_date):
        """Route to the right alignment matcher based on comparison_mode."""
        if use_dsl:
            return _prev_match_dsl(current_date, event_config['launch_date'], event_config_prev['launch_date'])
        else:
            return _prev_match_dow(current_date, event_config['event_date_first'], event_config_prev['event_date_first'])
    
    """Generate daily and weekly sales tracking rows.
    cutoff_date = velocity cutoff (yesterday, complete days)
    cutoff_cumulative = today (includes partial day)
    """
    from collections import defaultdict
    
    # Daily: last 7 days before cutoff + 1 future day
    daily_rows = []
    
    # Count tickets per date
    sales_by_date = defaultdict(int)
    platform_by_date = defaultdict(lambda: defaultdict(int))
    accum_by_date = {}
    
    paid_tickets = sorted([t for t in tickets if t.get('is_paid', 1) == 1], key=lambda t: t['order_date'])
    
    # Build cumulative
    running = 0
    for t in paid_tickets:
        d = t['order_date']
        sales_by_date[d] += 1
        platform_by_date[d][t['platform']] += 1
        running += 1
        accum_by_date[d] = running
    
    # Previous year same-point data
    prev_sales_by_date = defaultdict(int)
    prev_platform_by_date = defaultdict(lambda: defaultdict(int))
    prev_accum_by_date = {}
    if tickets_prev_full and event_config_prev:
        prev_paid = sorted([t for t in tickets_prev_full if t.get('is_paid', 1) == 1], key=lambda t: t['order_date'])
        prev_running = 0
        for t in prev_paid:
            d = t['order_date']
            prev_sales_by_date[d] += 1
            prev_platform_by_date[d][t['platform']] += 1
            prev_running += 1
            prev_accum_by_date[d] = prev_running
    
    DAYS_FR = {0: 'Lun', 1: 'Mar', 2: 'Mer', 3: 'Jeu', 4: 'Ven', 5: 'Sam', 6: 'Dim'}
    
    # Find table start: earliest first sale across both events (mapped to current year timeline)
    all_dates = sorted(sales_by_date.keys())
    first_sale = all_dates[0] if all_dates else cutoff_date - timedelta(days=6)
    
    # If reference year started earlier (mapped to current timeline), extend table start
    if prev_sales_by_date and event_config_prev:
        prev_first_sale = min(prev_sales_by_date.keys())
        if use_dsl:
            # DSL: days from prev launch → same days from current launch
            days_from_prev_launch = (prev_first_sale - event_config_prev['launch_date']).days
            mapped_start = event_config['launch_date'] + timedelta(days=days_from_prev_launch)
        else:
            # J-minus: same J-X from event
            j_x = (event_config_prev['event_date_first'] - prev_first_sale).days
            mapped_start = event_config['event_date_first'] - timedelta(days=j_x)
        first_sale = min(first_sale, mapped_start)
    
    # Generate rows from cutoff-6 back, then cutoff+1 as future
    VISIBLE_DAYS = 7  # Show last 7 days by default
    
    # Build all day offsets: from first sale to cutoff (past data only)
    start_offset = -(cutoff_date - first_sale).days
    all_offsets = list(range(start_offset, 1))  # up to cutoff (offset 0)
    
    for offset in all_offsets:
        d = cutoff_date + timedelta(days=offset)
        sales = sales_by_date.get(d, 0)
        accum = accum_by_date.get(d, 0)
        sg = platform_by_date.get(d, {}).get('Shotgun', 0)
        dice = platform_by_date.get(d, {}).get('DICE', 0)
        
        dow = DAYS_FR[d.weekday()]
        date_str = f"{dow} {d.day} {MONTHS_FR_ABBR[d.month]}"
        
        # Previous year matching date
        if event_config_prev:
            prev_match = _match_prev_date(d)
            prev_sales = prev_sales_by_date.get(prev_match, 0)
            prev_accum = prev_accum_by_date.get(prev_match, 0)
            prev_sg = prev_platform_by_date.get(prev_match, {}).get('Shotgun', 0)
            prev_dice = prev_platform_by_date.get(prev_match, {}).get('DICE', 0)
            prev_dow = DAYS_FR[prev_match.weekday()]
            prev_date_str = f"{prev_dow} {prev_match.day} {MONTHS_FR_ABBR[prev_match.month]}"
        else:
            prev_sales = prev_accum = prev_sg = prev_dice = 0
            prev_date_str = "-"
        
        diff = sales - prev_sales
        diff_class = 'pos' if diff >= 0 else 'neg'
        diff_pct = ((diff / prev_sales * 100) if prev_sales > 0 else 0) if prev_sales > 0 else 0
        
        is_today = False  # offset 0 = cutoff_velocity = yesterday, not today
        row_class = ''
        
        prev_detail = f'<div class="dtl-detail">SG {prev_sg} · DICE {prev_dice}</div>' if event_config_prev else ''
        
        today_mark = ''
        today_label = ''
        daily_rows.append(f'<div class="dtl-row{row_class}"><div class="dtl-left"><div class="dtl-date">{prev_date_str}</div><div class="dtl-sales">{prev_sales}</div>{prev_detail}<div class="dtl-accum">Cumulé {fmt_num(prev_accum)}</div></div><div class="dtl-center"><div class="dtl-diff {diff_class}">{diff:+d}</div><div class="dtl-pct">{diff_pct:+.1f}%</div></div><div class="dtl-right"><div class="dtl-date">{date_str}</div><div class="dtl-sales">{sales}</div><div class="dtl-detail">SG {sg} · DICE {dice}</div><div class="dtl-accum">Cumulé {fmt_num(accum)}</div></div></div>')
    
    # Generate future rows: from after today through last event day + 1 (catches post-midnight sales)
    future_rows = []
    event_date = event_config['event_date_first']
    event_date_last = event_config.get('event_date_last', event_date)
    future_end_date = event_date_last + timedelta(days=1)  # +1 for post-midnight sales
    future_start_date = (cutoff_cumulative if cutoff_cumulative else cutoff_date) + timedelta(days=1)
    future_days_count = (future_end_date - future_start_date).days + 1  # through last event day + 1
    for offset in range(max(0, future_days_count)):
        d = future_start_date + timedelta(days=offset)
        dow = DAYS_FR[d.weekday()]
        date_str = f"{dow} {d.day} {MONTHS_FR_ABBR[d.month]}"
        j_minus = (event_date - d).days
        if j_minus >= 0:
            j_label = f"J-{j_minus}"
        else:
            # Multi-day event: J+1 = second event day, etc.
            j_label = f"J+{abs(j_minus)}"
        
        # 2025 reference data for that J-X
        if event_config_prev:
            prev_match = _match_prev_date(d)
            prev_sales = prev_sales_by_date.get(prev_match, 0)
            prev_accum = prev_accum_by_date.get(prev_match, 0)
            prev_sg = prev_platform_by_date.get(prev_match, {}).get('Shotgun', 0)
            prev_dice = prev_platform_by_date.get(prev_match, {}).get('DICE', 0)
            prev_dow = DAYS_FR[prev_match.weekday()]
            prev_date_str = f"{prev_dow} {prev_match.day} {MONTHS_FR_ABBR[prev_match.month]}"
            prev_detail = f'<div class="dtl-detail">SG {prev_sg} · DICE {prev_dice}</div>'
        else:
            prev_sales = prev_accum = 0
            prev_date_str = "-"
            prev_detail = ''
        
        future_rows.append(f'<div class="dtl-row future"><div class="dtl-left"><div class="dtl-date">{prev_date_str}</div><div class="dtl-sales">{prev_sales}</div>{prev_detail}<div class="dtl-accum">Cumulé {fmt_num(prev_accum)}</div></div><div class="dtl-center"><div class="dtl-diff" style="color:var(--text-dim)">{j_label}</div></div><div class="dtl-right"><div class="dtl-date" style="color:var(--text-muted)">{date_str}</div><div class="dtl-sales" style="color:var(--text-dim)">À venir</div></div></div>')
    
    # Split past rows: show last VISIBLE_DAYS, hide older
    visible_past = daily_rows[-VISIBLE_DAYS:] if len(daily_rows) > VISIBLE_DAYS else daily_rows
    hidden_past = daily_rows[:-VISIBLE_DAYS] if len(daily_rows) > VISIBLE_DAYS else []
    # hidden_past stays chronological (oldest first) so it flows into visible_past
    
    # Build HTML
    daily_html = ''
    if hidden_past:
        show_older_day_count = len(hidden_past)
        daily_html += f'<button class="show-more-btn" onclick="var h=document.getElementById(\'suivi-hidden-days\');if(h){{if(h.style.display===\'none\'){{h.style.display=\'block\';this.textContent=\'Masquer les jours anciens\'}}else{{h.style.display=\'none\';this.textContent=\'Voir les {show_older_day_count} jours précédents\'}}}}">Voir les {show_older_day_count} jours précédents</button>'
        daily_html += f'\n        <div id="suivi-hidden-days" style="display:none">\n        '
        daily_html += '\n        '.join(hidden_past)
        daily_html += '\n        </div>'
    daily_html += '\n        '.join(visible_past)
    
    # ── "Aujourd'hui" row: partial day data ──
    if cutoff_cumulative and cutoff_cumulative > cutoff_date:
        today_d = cutoff_cumulative
        today_sales = sales_by_date.get(today_d, 0)
        today_accum = accum_by_date.get(today_d, 0)
        today_sg = platform_by_date.get(today_d, {}).get('Shotgun', 0)
        today_dice = platform_by_date.get(today_d, {}).get('DICE', 0)
        today_dow = DAYS_FR[today_d.weekday()]
        today_date_str = f"{today_dow} {today_d.day} {MONTHS_FR_ABBR[today_d.month]}"
        
        # 2025 reference for today's J-X
        event_date_ref = event_config['event_date_first']
        today_j_minus = (event_date_ref - today_d).days
        # Reference for today
        if event_config_prev:
            prev_match_today = _match_prev_date(today_d)
            prev_today_sales = prev_sales_by_date.get(prev_match_today, 0)
            prev_today_accum = prev_accum_by_date.get(prev_match_today, 0)
            prev_today_sg = prev_platform_by_date.get(prev_match_today, {}).get('Shotgun', 0)
            prev_today_dice = prev_platform_by_date.get(prev_match_today, {}).get('DICE', 0)
            prev_today_dow = DAYS_FR[prev_match_today.weekday()]
            prev_today_str = f"{prev_today_dow} {prev_match_today.day} {MONTHS_FR_ABBR[prev_match_today.month]}"
            prev_today_detail = f'<div class="dtl-detail">SG {prev_today_sg} · DICE {prev_today_dice}</div>'
        else:
            prev_today_sales = prev_today_accum = 0
            prev_today_str = "-"
            prev_today_detail = ''
        
        today_diff = today_sales - prev_today_sales
        today_diff_class = 'pos' if today_diff >= 0 else 'neg'
        
        today_row = (
            f'<div class="dtl-row today" style="border:1px solid var(--amber);border-radius:8px;margin:6px 0;padding:2px 0">'
            f'<div class="dtl-left"><div class="dtl-date">{prev_today_str}</div><div class="dtl-sales">{prev_today_sales}</div>{prev_today_detail}<div class="dtl-accum">Cumulé {fmt_num(prev_today_accum)}</div></div>'
            f'<div class="dtl-center"><div class="dtl-diff {today_diff_class}">{today_diff:+d}</div><div class="dtl-pct" style="font-size:0.7em;color:var(--amber)">en cours</div></div>'
            f'<div class="dtl-right"><div class="dtl-date" style="color:var(--amber)">Aujourd\'hui</div><div class="dtl-sales" style="color:var(--amber)">{today_sales}</div><div class="dtl-detail">SG {today_sg} · DICE {today_dice}</div><div class="dtl-accum">Cumulé {fmt_num(today_accum)}</div></div>'
            f'</div>'
        )
        daily_html += '\n        ' + today_row
    
    # Cutoff separator + future rows (hidden by default)
    remaining_future_count = len(future_rows)
    current_year = event_config['event_date_first'].year
    compare_year = event_config_prev['event_date_first'].year if event_config_prev else ''
    col_headers = f'<div class="dtl-col-labels" style="margin-top:8px"><div class="dtl-col-label">{compare_year} (référence)</div><div class="dtl-col-label center">J-X</div><div class="dtl-col-label right">{current_year} (à venir)</div></div>'
    
    if future_rows:
        daily_html += '\n        <div class="dtl-cutoff"><div class="dtl-cutoff-line"></div><div class="dtl-cutoff-label">À venir</div><div class="dtl-cutoff-line"></div></div>'
        daily_html += f'\n        <div id="suivi-future-days" style="display:none;max-height:400px;overflow-y:auto">'
        daily_html += f'\n        {col_headers}'
        daily_html += '\n        ' + '\n        '.join(future_rows)
        daily_html += '\n        </div>'
    
    # Weekly: aggregate by week
    weekly_rows = []
    # Group sales by week number relative to event
    week_sales = defaultdict(lambda: {'current': 0, 'prev': 0, 'cur_rev': 0, 'prev_rev': 0, 'cur_sg': 0, 'cur_dice': 0, 'prev_sg': 0, 'prev_dice': 0})
    
    event_date = event_config['event_date_first']
    for t in paid_tickets:
        weeks_before = (event_date - t['order_date']).days // 7
        if weeks_before >= 1:
            week_sales[weeks_before]['current'] += 1
            week_sales[weeks_before]['cur_rev'] += t['price']
            if t['platform'] == 'Shotgun':
                week_sales[weeks_before]['cur_sg'] += 1
            else:
                week_sales[weeks_before]['cur_dice'] += 1
    
    prev_event_date = event_config_prev['event_date_first'] if event_config_prev else event_date
    
    if tickets_prev_full and event_config_prev:
        for t in tickets_prev_full:
            if t.get('is_paid', 1) != 1:
                continue
            if use_dsl:
                # Event-end anchoring: same distance from event end
                prev_end = event_config_prev['event_date_last'] + timedelta(days=1)
                cur_end = event_config['event_date_last'] + timedelta(days=1)
                days_before_prev_end = (prev_end - t['order_date']).days
                equiv_date_cur = cur_end - timedelta(days=days_before_prev_end)
                weeks_before = (event_date - equiv_date_cur).days // 7
            else:
                weeks_before = (prev_event_date - t['order_date']).days // 7
            if weeks_before >= 1:
                week_sales[weeks_before]['prev'] += 1
                week_sales[weeks_before]['prev_rev'] += t['price']
                if t['platform'] == 'Shotgun':
                    week_sales[weeks_before]['prev_sg'] += 1
                else:
                    week_sales[weeks_before]['prev_dice'] += 1
    
    # Current week: the one containing today (cutoff_cumulative)
    today_ref = cutoff_cumulative if cutoff_cumulative else cutoff_date
    current_week_num = (event_date - today_ref).days // 7
    if current_week_num < 1:
        current_week_num = 1
    
    def _week_label(w_num, ref_event_date):
        """Generate 'S-X · DD-DD Mon' label."""
        ws_d = ref_event_date - timedelta(days=w_num * 7)
        we_d = ws_d + timedelta(days=6)
        if ws_d.month == we_d.month:
            return f"S-{w_num} · {ws_d.day:02d}-{we_d.day:02d} {MONTHS_FR_ABBR[ws_d.month]}"
        else:
            return f"S-{w_num} · {ws_d.day:02d} {MONTHS_FR_ABBR[ws_d.month]}-{we_d.day:02d} {MONTHS_FR_ABBR[we_d.month]}"
    
    # Show all past + current weeks that have data in EITHER year (full timeline)
    past_week_nums = sorted([w for w in week_sales if w >= current_week_num and (week_sales[w]['current'] > 0 or week_sales[w]['prev'] > 0)], reverse=True)
    
    # Compute cumulative totals for percentage display
    total_capacity = event_config.get('total_capacity', 0) if event_config else 0
    prev_total_capacity = event_config_prev.get('total_capacity', 0) if event_config_prev else 0
    
    # Build cumulative from oldest week (highest S-number) to newest
    cur_cumul = 0
    prev_cumul = 0
    week_cumul = {}  # {week_num: {'cur_cumul': X, 'prev_cumul': Y}}
    for w in sorted(past_week_nums, reverse=True):  # oldest first
        ws = week_sales[w]
        cur_cumul += ws['current']
        prev_cumul += ws['prev']
        week_cumul[w] = {'cur_cumul': cur_cumul, 'prev_cumul': prev_cumul}
    
    # Also account for weeks older than the visible ones (tickets sold before the earliest visible week)
    all_week_nums_with_data = sorted([w for w in week_sales if week_sales[w]['current'] > 0 or week_sales[w]['prev'] > 0], reverse=True)
    pre_cur_cumul = 0
    pre_prev_cumul = 0
    for w in sorted(all_week_nums_with_data, reverse=True):
        if w not in past_week_nums:
            pre_cur_cumul += week_sales[w]['current']
            pre_prev_cumul += week_sales[w]['prev']
    # Adjust cumulative to include pre-visible weeks
    for w in week_cumul:
        week_cumul[w]['cur_cumul'] += pre_cur_cumul
        week_cumul[w]['prev_cumul'] += pre_prev_cumul
    
    for w in past_week_nums:
        ws = week_sales[w]
        week_start = event_date - timedelta(days=w * 7)
        week_end = week_start + timedelta(days=6)
        date_label = _week_label(w, event_date)
        
        diff = ws['current'] - ws['prev']
        diff_class = 'pos' if diff >= 0 else 'neg'
        diff_pct = ((diff / ws['prev'] * 100) if ws['prev'] > 0 else 0)
        
        is_current = (w == current_week_num)
        cur_rev_fmt = f"€{ws['cur_rev']/1000:.0f}k"
        prev_rev_fmt = f"€{ws['prev_rev']/1000:.0f}k"
        
        # Percentage labels
        wc = week_cumul.get(w, {'cur_cumul': 0, 'prev_cumul': 0})
        cur_week_pct = (ws['current'] / total_capacity * 100) if total_capacity else 0
        cur_cumul_pct = (wc['cur_cumul'] / total_capacity * 100) if total_capacity else 0
        prev_week_pct = (ws['prev'] / prev_total_capacity * 100) if prev_total_capacity else 0
        prev_cumul_pct = (wc['prev_cumul'] / prev_total_capacity * 100) if prev_total_capacity else 0
        
        cur_pct_html = f'<div class="dtl-detail" style="margin-top:2px">{cur_week_pct:.1f}%&ensp;·&ensp;{cur_cumul_pct:.1f}% cumulé</div>'
        prev_pct_html = f'<div class="dtl-detail" style="margin-top:2px">{prev_week_pct:.1f}%&ensp;·&ensp;{prev_cumul_pct:.1f}% cumulé</div>' if event_config_prev else ''
        
        # Determine if this is a 2025-only week (no 2026 sales yet)
        is_prev_only = ws['current'] == 0
        
        if is_current:
            # Current (partial) week
            if event_config_prev:
                prev_label = _week_label(w, prev_event_date)
            else:
                prev_label = f"S-{w}"
            prev_detail = f'<div class="dtl-detail">SG {ws["prev_sg"]} · DICE {ws["prev_dice"]}</div>' if event_config_prev else ''
            weekly_rows.append(f'<div class="dtl-row today" style="border:1px solid var(--amber);border-radius:8px;margin:2px 0;padding:2px 0"><div class="dtl-left"><div class="dtl-date">{prev_label}</div><div class="dtl-sales">{ws["prev"]}</div>{prev_detail}{prev_pct_html}<div class="dtl-accum">{prev_rev_fmt}</div></div><div class="dtl-center"><div class="dtl-diff {diff_class}">{diff:+d}</div><div class="dtl-pct" style="color:var(--amber)">en cours</div></div><div class="dtl-right"><div class="dtl-date" style="color:var(--amber)">{date_label} · en cours</div><div class="dtl-sales" style="color:var(--amber)">{ws["current"]}</div><div class="dtl-detail">SG {ws["cur_sg"]} · DICE {ws["cur_dice"]}</div>{cur_pct_html}<div class="dtl-accum">{cur_rev_fmt}</div></div></div>')
        elif is_prev_only:
            # Week with only 2025 data - show dash on 2026 side
            if event_config_prev:
                prev_label = _week_label(w, prev_event_date)
            else:
                prev_label = f"S-{w}"
            prev_detail = f'<div class="dtl-detail">SG {ws["prev_sg"]} · DICE {ws["prev_dice"]}</div>' if event_config_prev else ''
            weekly_rows.append(f'<div class="dtl-row" style="opacity:0.5"><div class="dtl-left"><div class="dtl-date">{prev_label}</div><div class="dtl-sales">{ws["prev"]}</div>{prev_detail}{prev_pct_html}<div class="dtl-accum">{prev_rev_fmt}</div></div><div class="dtl-center"><div class="dtl-diff" style="color:var(--text-dim)">-</div></div><div class="dtl-right"><div class="dtl-date" style="color:var(--text-dim)">{date_label}</div><div class="dtl-sales" style="color:var(--text-dim)">-</div></div></div>')
        else:
            # Complete past week with data on both sides
            if event_config_prev:
                prev_label = _week_label(w, prev_event_date)
            else:
                prev_label = f"S-{w}"
            prev_detail = f'<div class="dtl-detail">SG {ws["prev_sg"]} · DICE {ws["prev_dice"]}</div>' if event_config_prev else ''
            weekly_rows.append(f'<div class="dtl-row"><div class="dtl-left"><div class="dtl-date">{prev_label}</div><div class="dtl-sales">{ws["prev"]}</div>{prev_detail}{prev_pct_html}<div class="dtl-accum">{prev_rev_fmt}</div></div><div class="dtl-center"><div class="dtl-diff {diff_class}">{diff:+d}</div><div class="dtl-pct">{diff_pct:+.1f}%</div></div><div class="dtl-right"><div class="dtl-date">{date_label}</div><div class="dtl-sales">{ws["current"]}</div><div class="dtl-detail">SG {ws["cur_sg"]} · DICE {ws["cur_dice"]}</div>{cur_pct_html}<div class="dtl-accum">{cur_rev_fmt}</div></div></div>')
    
    # Future weeks: weeks closer to event that have no 2026 data
    future_weekly_rows = []
    for w in range(1, current_week_num):
        if w in week_sales and week_sales[w]['current'] > 0:
            continue  # Already has data, not future
        date_label = _week_label(w, event_date)
        
        prev_sales_w = 0
        prev_rev_w = 0
        prev_sg_w = 0
        prev_dice_w = 0
        prev_label = f"S-{w}"
        if event_config_prev:
            prev_label = _week_label(w, prev_event_date)
            prev_sales_w = week_sales.get(w, {}).get('prev', 0) if w in week_sales else 0
            prev_rev_w = week_sales.get(w, {}).get('prev_rev', 0) if w in week_sales else 0
            prev_sg_w = week_sales.get(w, {}).get('prev_sg', 0) if w in week_sales else 0
            prev_dice_w = week_sales.get(w, {}).get('prev_dice', 0) if w in week_sales else 0
            # Search prev year data for this week if not already counted
            if prev_sales_w == 0:
                for t in tickets_prev_full:
                    if t.get('is_paid', 1) != 1:
                        continue
                    if use_dsl:
                        prev_end = event_config_prev['event_date_last'] + timedelta(days=1)
                        cur_end = event_config['event_date_last'] + timedelta(days=1)
                        days_before_prev_end = (prev_end - t['order_date']).days
                        equiv_date_cur = cur_end - timedelta(days=days_before_prev_end)
                        wb = (event_date - equiv_date_cur).days // 7
                    else:
                        wb = (prev_event_date - t['order_date']).days // 7
                    if wb == w:
                        prev_sales_w += 1
                        prev_rev_w += t['price']
                        if t['platform'] == 'Shotgun':
                            prev_sg_w += 1
                        else:
                            prev_dice_w += 1
        
        prev_rev_fmt = f"€{prev_rev_w/1000:.0f}k"
        prev_detail = f'<div class="dtl-detail">SG {prev_sg_w} · DICE {prev_dice_w}</div>' if event_config_prev else ''
        future_weekly_rows.append(f'<div class="dtl-row future"><div class="dtl-left"><div class="dtl-date">{prev_label}</div><div class="dtl-sales">{prev_sales_w}</div>{prev_detail}<div class="dtl-accum">{prev_rev_fmt}</div></div><div class="dtl-center"><div class="dtl-diff" style="color:var(--text-dim)">S-{w}</div></div><div class="dtl-right"><div class="dtl-date" style="color:var(--text-muted)">{date_label}</div><div class="dtl-sales" style="color:var(--text-dim)">À venir</div></div></div>')
    
    # Sort future weeks (closest to event first = smallest w)
    future_weekly_rows.reverse()
    
    remaining_weeks_count = len(future_weekly_rows)
    
    # Split weekly rows: show last 6, hide older
    VISIBLE_WEEKS = 6
    visible_weekly = weekly_rows[-VISIBLE_WEEKS:] if len(weekly_rows) > VISIBLE_WEEKS else weekly_rows
    hidden_weekly = weekly_rows[:-VISIBLE_WEEKS] if len(weekly_rows) > VISIBLE_WEEKS else []
    
    weekly_html = ''
    if hidden_weekly:
        show_older_count = len(hidden_weekly)
        weekly_html += f'<button class="show-more-btn" onclick="var h=document.getElementById(\'suivi-hidden-weeks\');if(h){{if(h.style.display===\'none\'){{h.style.display=\'block\';this.textContent=\'Masquer les semaines anciennes\'}}else{{h.style.display=\'none\';this.textContent=\'Voir les {show_older_count} semaines précédentes\'}}}}">Voir les {show_older_count} semaines précédentes</button>'
        weekly_html += f'\n        <div id="suivi-hidden-weeks" style="display:none">\n        '
        weekly_html += '\n        '.join(hidden_weekly)
        weekly_html += '\n        </div>'
    weekly_html += '\n        '.join(visible_weekly)
    if future_weekly_rows:
        weekly_html += '\n        <div class="dtl-cutoff"><div class="dtl-cutoff-line"></div><div class="dtl-cutoff-label">À venir</div><div class="dtl-cutoff-line"></div></div>'
        weekly_html += f'\n        <div id="suivi-future-weeks" style="display:none;max-height:300px;overflow-y:auto">'
        weekly_html += '\n        ' + '\n        '.join(future_weekly_rows)
        weekly_html += '\n        </div>'
    
    return daily_html, weekly_html, remaining_future_count, remaining_weeks_count


# ── Helper: Projection cards + charts ──
def _generate_projection_v3(tickets, tickets_prev_full, cutoff_date, event_config, event_config_prev, metrics, day_presence, days_remaining_display=None):
    """Generate projection cards with two scenarios: Tendance récente + Trajectoire historique."""
    day_names = [d['day_name'].lower() for d in event_config['days']]
    day_configs = {d['day_name'].lower(): d for d in event_config['days']}
    event_date = event_config['event_date_first']
    days_remaining = max(0, (event_date - cutoff_date).days)  # clamp to 0 when event is past
    if days_remaining_display is None:
        days_remaining_display = days_remaining
    num_days = len(day_names)
    paid = [t for t in tickets if t.get('is_paid', 1) == 1]
    
    # Day name mapping for reference year (Day 1↔Day 1 in DSL mode)
    prev_presence_key_map = {}  # maps current dn → key to use for reference year presence
    if event_config.get('comparison_mode', 'j_minus') == 'days_since_launch' and event_config_prev:
        prev_day_names_list = [d['day_name'].lower() for d in event_config_prev['days']]
        for idx, dn in enumerate(day_names):
            prev_presence_key_map[dn] = f'presence_{prev_day_names_list[idx]}' if idx < len(prev_day_names_list) else f'presence_{dn}'
    else:
        for dn in day_names:
            prev_presence_key_map[dn] = f'presence_{dn}'
    
    # ── Scenario helpers ──
    def _simulate_sellout(current, vel_start, remaining_days, cap, weekly_accel=0):
        """Simulate day-by-day with optional weekly acceleration. Returns (projected, sellout_day_offset)."""
        total = current
        vel = vel_start
        sellout_offset = None
        for d in range(1, remaining_days + 1):
            total += vel
            if total >= cap and sellout_offset is None:
                sellout_offset = d
            if d % 7 == 0 and weekly_accel:
                vel *= (1 + weekly_accel)
                vel = min(vel, cap * 0.05)  # cap at 5% of capacity/day
        return min(total, cap), sellout_offset
    
    def _simulate_historical(current, vel_start, remaining_days, cap, accel_ratios):
        """Simulate with historical acceleration ratios per week bracket."""
        total = current
        sellout_offset = None
        day_count = 0
        for bracket_days, ratio in accel_ratios:
            vel = vel_start * ratio
            for _ in range(min(bracket_days, remaining_days - day_count)):
                total += vel
                day_count += 1
                if total >= cap and sellout_offset is None:
                    sellout_offset = day_count
                if day_count >= remaining_days:
                    break
            if day_count >= remaining_days:
                break
        return min(total, cap), sellout_offset
    
    def _sellout_text_fr(sellout_offset, cutoff, cap, projected, pct_proj):
        """Generate sellout info: date if sellout, otherwise projected %."""
        if sellout_offset:
            sd = cutoff + timedelta(days=sellout_offset)
            return f'Sold out ~{sd.day} {MONTHS_FR_ABBR[sd.month]}', 'var(--green)'
        elif pct_proj >= 95:
            return f'Sold out probable ({pct_proj:.0f}%)', 'var(--green)'
        else:
            return f'{pct_proj:.0f}% de la capacité', 'var(--text-muted)'
    
    # ── Compute dynamic acceleration curve from reference year ──
    hist_accel = {}
    # Pre-compute DSL-equivalent cutoff for reference year
    comparison_mode = event_config.get('comparison_mode', 'j_minus')
    dsl_prev_cutoff = None
    if comparison_mode == 'days_since_launch' and event_config.get('launch_date') and event_config_prev and event_config_prev.get('launch_date'):
        days_since_launch = (cutoff_date - event_config['launch_date']).days
        dsl_prev_cutoff = event_config_prev['launch_date'] + timedelta(days=days_since_launch)
    
    if tickets_prev_full and event_config_prev:
        prev_event = event_config_prev['event_date_first']
        prev_paid = [t for t in tickets_prev_full if t.get('is_paid', 1) == 1]
        
        for dn in day_names:
            # Build weekly velocity buckets from current position forward to event
            # Each bucket is 7 days, except possibly the last one
            weeks = []
            d = days_remaining
            while d > 0:
                bucket_end_j = d
                bucket_start_j = max(d - 7, 0)  # 0 = event day (excluded), 1 = J-1
                bucket_days = bucket_end_j - bucket_start_j
                if bucket_days < 1:
                    break
                
                if dsl_prev_cutoff:
                    # DSL mode: offset from the equivalent cutoff in reference year
                    # bucket_end_j = days remaining, so offset from cutoff = days_remaining - bucket_end_j
                    start_date = dsl_prev_cutoff + timedelta(days=days_remaining - bucket_end_j)
                    end_date = dsl_prev_cutoff + timedelta(days=days_remaining - bucket_start_j - 1)
                else:
                    # J-minus mode: same J-X window in reference year
                    start_date = prev_event - timedelta(days=bucket_end_j)
                    end_date = prev_event - timedelta(days=bucket_start_j + 1)
                
                bucket_tix = [t for t in prev_paid if start_date <= t['order_date'] <= end_date]
                vel = sum(t.get(prev_presence_key_map[dn], 0) for t in bucket_tix) / bucket_days if bucket_tix else 0
                weeks.append({'j_start': bucket_end_j, 'j_end': bucket_start_j, 'days': bucket_days, 'vel': vel})
                
                d -= 7
            
            # Calculate ratios relative to first week (current position baseline)
            baseline_vel = weeks[0]['vel'] if weeks and weeks[0]['vel'] > 0 else 1
            accel_ratios = []
            for w in weeks:
                ratio = w['vel'] / baseline_vel if baseline_vel > 0 else 1.0
                accel_ratios.append((w['days'], max(ratio, 0.1)))  # floor at 0.1 to avoid zero
            
            hist_accel[dn] = {
                'ratios': accel_ratios,
                'baseline_vel': baseline_vel,
                'num_weeks': len(weeks),
            }
    
    cards = []
    tabs = []
    panels = []
    methodology_parts = []
    
    for i, dn in enumerate(day_names):
        cap = day_configs[dn]['day_capacity']
        pres = day_presence.get(dn, 0)
        pct_sold = (pres / cap * 100) if cap > 0 else 0
        remaining = cap - pres
        display = DAY_DISPLAY_NAMES.get(dn, dn.capitalize())
        
        # Current 7d and 14d velocity
        last_7 = cutoff_date - timedelta(days=6)
        t7 = [t for t in paid if last_7 <= t['order_date'] <= cutoff_date]
        vel_7d = sum(t.get(f'presence_{dn}', 0) for t in t7) / 7
        
        last_14 = cutoff_date - timedelta(days=13)
        t14 = [t for t in paid if last_14 <= t['order_date'] <= cutoff_date]
        vel_14d = sum(t.get(f'presence_{dn}', 0) for t in t14) / 14
        
        # ── Single scenario: Trajectoire (with ref) or Standard profile (without) ──
        has_reference = dn in hist_accel
        
        if has_reference:
            ha = hist_accel[dn]
            prev_year = event_config_prev['event_date_first'].year if event_config_prev else ''
            
            # SCENARIO A: Pure replay - exact reference remaining-day sales grafted onto current
            prev_event = event_config_prev['event_date_first']
            prev_paid_tickets = [t for t in tickets_prev_full if t.get('is_paid', 1) == 1]
            replay_total = pres
            replay_sellout = None
            for d_offset in range(1, days_remaining + 1):
                if dsl_prev_cutoff:
                    # DSL mode: replay from equivalent cutoff forward
                    prev_date = dsl_prev_cutoff + timedelta(days=d_offset)
                else:
                    # J-minus mode: replay from same J-X position
                    prev_date = prev_event - timedelta(days=days_remaining - d_offset)
                day_sales = sum(1 for t in prev_paid_tickets 
                               if t['order_date'] == prev_date and t.get(prev_presence_key_map[dn], 0) > 0)
                replay_total += day_sales
                if replay_total >= cap and replay_sellout is None:
                    replay_sellout = d_offset
            replay_total = min(replay_total, cap)
            replay_total = max(replay_total, pres)  # projected can never be below current
            pct_replay = (replay_total / cap * 100) if cap > 0 else 0
            replay_text, replay_color = _sellout_text_fr(replay_sellout, cutoff_date, cap, replay_total, pct_replay)
            
            # SCENARIO B: Reference × coef. current - use 14d velocity for more stable coefficient
            proj_final, sellout_final = _simulate_historical(pres, vel_14d, days_remaining, cap, ha['ratios'])
            proj_final = max(proj_final, pres)  # projected can never be below current
            
            # Compute the coefficient from 14d velocity for display
            if dsl_prev_cutoff:
                prev_cutoff = dsl_prev_cutoff
            else:
                prev_event_date = event_config_prev['event_date_first']
                prev_cutoff = prev_event_date - timedelta(days=days_remaining)
            prev_last_14 = prev_cutoff - timedelta(days=13)
            prev_paid_all = [t for t in tickets_prev_full if t.get('is_paid', 1) == 1]
            prev_t14 = [t for t in prev_paid_all if prev_last_14 <= t['order_date'] <= prev_cutoff]
            prev_vel_14d_dn = sum(t.get(prev_presence_key_map[dn], 0) for t in prev_t14) / 14 if prev_t14 else 0
            coef_display = vel_14d / prev_vel_14d_dn if prev_vel_14d_dn > 0 else 1.0
            
            scenario_a_label = f'Trajectoire {prev_year}'
            scenario_b_label = f'{prev_year} × coef. {event_date.year}'
            scenario_a_color = '#fbbf24'
            scenario_b_color = '#fbbf24'
        else:
            # Standard festival acceleration profile
            STANDARD_PROFILE = {
                20: 0.4, 19: 0.5, 18: 0.6, 17: 0.6, 16: 0.5,
                15: 0.5, 14: 0.7, 13: 0.7, 12: 0.8, 11: 0.8,
                10: 1.0, 9: 1.0, 8: 0.9, 7: 0.9, 6: 1.1,
                5: 1.6, 4: 1.8, 3: 1.6, 2: 1.8, 1: 3.0, 0: 3.0
            }
            # Build acceleration ratios from standard profile
            current_week = max(0, min(20, (days_remaining + 6) // 7))
            current_mult = STANDARD_PROFILE.get(current_week, 1.0)
            if current_mult == 0:
                current_mult = 0.5
            
            std_ratios = []
            d = days_remaining
            while d > 0:
                bucket_days = min(7, d)
                week_num = max(0, min(20, (d + 6) // 7))
                ratio = STANDARD_PROFILE.get(week_num, 1.0) / current_mult
                std_ratios.append((bucket_days, max(ratio, 0.1)))
                d -= 7
            
            proj_final, sellout_final = _simulate_historical(pres, vel_7d, days_remaining, cap, std_ratios)
            proj_final = max(proj_final, pres)  # projected can never be below current
            scenario_label = 'Profil standard festival'
            scenario_color = '#a78bfa'
        
        pct_final = (proj_final / cap * 100) if cap > 0 else 0
        final_text, final_color = _sellout_text_fr(sellout_final, cutoff_date, cap, proj_final, pct_final)
        
        # ── Card HTML ──
        if has_reference:
            # Dual scenario card with toggle
            pct_final_b = pct_final  # scenario B (coef) already computed above
            final_text_b, final_color_b = final_text, final_color
            
            cards.append(f'''<div class="q-card">\
<div class="q-header"><span class="q-day-name" style="color:var(--day-{i})">{display}</span></div>\
<div class="scenario-toggle"><button class="scenario-btn active" onclick="switchScenario(this,{i},'a')">Trajectoire {prev_year}</button><button class="scenario-btn" onclick="switchScenario(this,{i},'b')">{prev_year} × coef. {event_date.year}</button></div>\
<div class="q-scenarios">\
<div class="q-scenario-content active" id="day{i}-sa">\
<div class="q-current"><span class="q-current-num">{fmt_num(int(replay_total)).replace(",", " ")}</span><span class="q-current-cap">projetés · {pct_replay:.0f}%</span></div>\
<div class="q-bar"><div class="q-bar-fill" style="width:{min(pct_replay, 100):.1f}%;background:var(--day-{i})"></div></div>\
<div class="q-scenario-row"><div class="q-scenario-name"><span class="q-scenario-sub">Actuels</span></div><div class="q-scenario-nums"><span class="q-scenario-proj" style="font-size:0.85em">{fmt_num(pres).replace(",", " ")}</span></div></div>\
<div class="q-scenario-row"><div class="q-scenario-name"><span class="q-scenario-sub">Restants projetés</span></div><div class="q-scenario-nums"><span class="q-scenario-proj" style="color:var(--text-muted);font-size:0.85em">+{fmt_num(int(replay_total - pres)).replace(",", " ")}</span></div></div>\
<div class="q-scenario-row"><div class="q-scenario-name"><span class="q-scenario-sub">Sellout</span></div><div class="q-scenario-nums"><span class="q-scenario-result" style="color:{replay_color}">{replay_text}</span></div></div>\
<div style="font-size:0.6em;color:var(--text-dim);margin-top:6px;line-height:1.4">Réplique exacte des ventes {prev_year} de J-{days_remaining_display} à J-0</div>\
</div>\
<div class="q-scenario-content" id="day{i}-sb">\
<div class="q-current"><span class="q-current-num">{fmt_num(int(proj_final)).replace(",", " ")}</span><span class="q-current-cap">projetés · {pct_final_b:.0f}%</span></div>\
<div class="q-bar"><div class="q-bar-fill" style="width:{min(pct_final_b, 100):.1f}%;background:var(--day-{i})"></div></div>\
<div class="q-scenario-row"><div class="q-scenario-name"><span class="q-scenario-sub">Actuels</span></div><div class="q-scenario-nums"><span class="q-scenario-proj" style="font-size:0.85em">{fmt_num(pres).replace(",", " ")}</span></div></div>\
<div class="q-scenario-row"><div class="q-scenario-name"><span class="q-scenario-sub">Restants projetés</span></div><div class="q-scenario-nums"><span class="q-scenario-proj" style="color:var(--text-muted);font-size:0.85em">+{fmt_num(int(proj_final - pres)).replace(",", " ")}</span></div></div>\
<div class="q-scenario-row"><div class="q-scenario-name"><span class="q-scenario-sub">Coefficient</span></div><div class="q-scenario-nums"><span class="q-scenario-proj" style="color:var(--green)">×{coef_display:.2f}</span></div></div>\
<div class="q-scenario-row"><div class="q-scenario-name"><span class="q-scenario-sub">Sellout</span></div><div class="q-scenario-nums"><span class="q-scenario-result" style="color:{final_color_b}">{final_text_b}</span></div></div>\
<div style="font-size:0.6em;color:var(--text-dim);margin-top:6px;line-height:1.4">Courbe {prev_year} × ratio vélocité {event_date.year}/{prev_year} à J-{days_remaining_display}</div>\
</div>\
</div></div>''')
        else:
            # Single scenario card (no reference data)
            cards.append(f'''<div class="q-card">\
<div class="q-header"><span class="q-day-name" style="color:var(--day-{i})">{display}</span></div>\
<div class="q-current"><span class="q-current-num">{fmt_num(int(proj_final)).replace(",", " ")}</span><span class="q-current-cap">projetés · {pct_final:.0f}%</span></div>\
<div class="q-bar"><div class="q-bar-fill" style="width:{min(pct_final, 100):.1f}%;background:var(--day-{i})"></div></div>\
<div class="q-scenarios">\
<div class="q-scenario-row"><div class="q-scenario-name"><span class="q-scenario-dot" style="background:{scenario_color}"></span><span class="q-scenario-sub">{scenario_label}</span></div><div class="q-scenario-nums"><span class="q-scenario-proj">{fmt_num(int(proj_final)).replace(",", " ")}</span><span class="q-scenario-result" style="color:{final_color}">{final_text}</span></div></div>\
</div></div>''')
        
        # Tab
        active_class = ' active' if i == 0 else ''
        tabs.append(f'<button class="chart-tab{active_class}" onclick="showProjTab(\'day{i}\',this)">{display}</button>')
        
        # Panel: chart(s) per day
        hidden = '' if i == 0 else ' class="hidden"'
        prev_year_label = event_config_prev["event_date_first"].year if event_config_prev else ""
        
        legend_ref = f'<div class="legend-item"><div class="legend-swatch dashed" style="border-color:rgba(239,68,68,0.5)"></div>{prev_year_label}</div>' if has_reference else ''
        disclaimer = '' if has_reference else f'<div style="margin-top:8px;padding:10px 14px;background:rgba(167,139,250,0.08);border:1px solid rgba(167,139,250,0.2);border-radius:8px;font-size:11px;color:rgba(255,255,255,0.5)">⚠️ Modèle en construction - projection basée sur un profil standard festival. Le modèle définitif utilisera les données historiques de l\'ensemble des événements Madame Loyal.</div>'
        
        if has_reference:
            # Two canvases: one per scenario, toggled by switchScenario
            panels.append(f'''<div id="proj-day{i}"{hidden}><div class="chart-subtitle">{display} - Courbe cumulative (% capacité)</div>\
<div class="q-chart-wrap" id="day{i}-chart-a"><div class="chart-canvas-wrap"><canvas id="chartDay{i}S1"></canvas></div>\
<div class="chart-legend-custom"><div class="legend-item"><div class="legend-swatch" style="background:#fbbf24"></div>Ventes {event_date.year}</div><div class="legend-item"><div class="legend-swatch dashed" style="border-color:{scenario_a_color}"></div>{scenario_a_label}</div>{legend_ref}<div class="legend-item"><div class="legend-swatch dashed" style="border-color:rgba(255,255,255,0.35)"></div>100% capacité</div></div></div>\
<div class="q-chart-wrap" id="day{i}-chart-b" style="display:none"><div class="chart-canvas-wrap"><canvas id="chartDay{i}S2"></canvas></div>\
<div class="chart-legend-custom"><div class="legend-item"><div class="legend-swatch" style="background:#fbbf24"></div>Ventes {event_date.year}</div><div class="legend-item"><div class="legend-swatch dashed" style="border-color:{scenario_b_color}"></div>{scenario_b_label}</div>{legend_ref}<div class="legend-item"><div class="legend-swatch dashed" style="border-color:rgba(255,255,255,0.35)"></div>100% capacité</div></div></div>\
</div>''')
        else:
            panels.append(f'''<div id="proj-day{i}"{hidden}><div class="chart-subtitle">{display} - Courbe cumulative (% capacité)</div><div class="chart-canvas-wrap"><canvas id="chartDay{i}S1"></canvas></div><div class="chart-legend-custom"><div class="legend-item"><div class="legend-swatch" style="background:#fbbf24"></div>Ventes {event_date.year}</div><div class="legend-item"><div class="legend-swatch dashed" style="border-color:{scenario_color}"></div>{scenario_label}</div>{legend_ref}<div class="legend-item"><div class="legend-swatch dashed" style="border-color:rgba(255,255,255,0.35)"></div>100% capacité</div></div>{disclaimer}</div>''')
        
        # Store projection data for chart builder
        # Pass the ratios used so chart function can replicate
        if has_reference:
            ha = hist_accel[dn]
            methodology_parts.append(f'<strong>{display}:</strong> vel. 14j = {vel_14d:.1f}/jour · coef. = ×{coef_display:.2f}<br>→ Trajectoire {prev_year}: {fmt_num(int(replay_total)).replace(",", " ")} ({pct_replay:.0f}%)<br>→ {prev_year} × coef. {event_date.year}: {fmt_num(int(proj_final)).replace(",", " ")} ({pct_final:.0f}%)')
        else:
            methodology_parts.append(f'<strong>{display}:</strong> vel. 7j = {vel_7d:.1f}/jour · Profil standard festival → {fmt_num(int(proj_final)).replace(",", " ")} ({pct_final:.0f}%)')
    
    has_any_reference = bool(tickets_prev_full and event_config_prev)
    prev_year_str = str(event_config_prev['event_date_first'].year) if event_config_prev else 'N/A'
    
    if has_any_reference:
        proj_methodology = f'<strong>Méthodologie - Deux scénarios de projection</strong><br><br>\
<strong>1. Trajectoire {prev_year_str}</strong><br>\
Réplique exacte des ventes {prev_year_str} sur les J-{days_remaining_display} restants. Les ventes journalières observées en {prev_year_str} à la même distance de l\'événement sont ajoutées au cumul actuel {event_date.year}. Aucun ajustement - projection conservatrice basée sur l\'historique brut.<br><br>\
<strong>2. {prev_year_str} × coef. {event_date.year}</strong><br>\
La courbe de ventes {prev_year_str} est multipliée par le ratio de vélocité actuelle ({event_date.year} vs {prev_year_str} à J-{days_remaining_display}). Ce coefficient reflète la dynamique de vente actuelle : un coef. > 1 signifie que {event_date.year} vend plus vite que {prev_year_str} au même stade.<br><br>' + '<br>'.join(methodology_parts) + '<br><br><strong>Paramètres :</strong> billets payants uniquement · pass multi-jours = 1 entrée/jour · coefficient basé sur la vélocité 14j · projections plafonnées à la capacité'
    else:
        proj_methodology = f'<strong>Méthodologie - Profil standard festival</strong><br><br>⚠️ <em>Modèle en construction</em> - cette projection utilise un profil d\'accélération standard basé sur les tendances typiques de festivals (accélération progressive puis forte hausse en S-5 à S-0). Le modèle définitif intégrera les données historiques de l\'ensemble des événements Madame Loyal pour une projection plus précise.<br><br>La vélocité actuelle (7 derniers jours) est projetée avec les multiplicateurs hebdomadaires du profil standard.<br><br>' + '<br>'.join(methodology_parts) + '<br><br><strong>Paramètres :</strong> billets payants uniquement · pass multi-jours = 1 entrée/jour · projections plafonnées à la capacité'
    
    proj_day_ids = ','.join(f"'day{i}'" for i in range(num_days))
    tab_class_parts = []
    for i in range(num_days):
        cls = 'active' if i == 0 else f'active-day{i}'
        tab_class_parts.append(f"day{i}:'{cls}'")
    proj_tab_classes = ','.join(tab_class_parts)
    
    return '\n        '.join(cards), ''.join(tabs), '\n    '.join(panels), proj_methodology, proj_day_ids, proj_tab_classes


def _generate_velocity_chart_js_v3(tickets, tickets_prev_full, cutoff_date, event_config, event_config_prev, days_remaining):
    """Generate the velocity trend Chart.js code for 7-day rolling velocity."""
    from collections import defaultdict
    
    event_date = event_config['event_date_first']
    labels = []
    v_current = []
    v_prev = []
    
    # Dynamic range: go back far enough to cover all data up to cutoff
    max_weeks = max(16, (days_remaining // 7) + 4)  # enough headroom
    
    for w in range(max_weeks, 0, -1):
        week_start = event_date - timedelta(days=w * 7)
        week_end = week_start + timedelta(days=6)
        
        # Skip weeks entirely in the future
        if week_start > cutoff_date:
            continue
        
        # For partial weeks (current week), only count days up to cutoff
        effective_end = min(week_end, cutoff_date)
        days_in_window = (effective_end - week_start).days + 1
        if days_in_window < 1:
            continue
        
        count = len([t for t in tickets if week_start <= t['order_date'] <= effective_end and t.get('is_paid', 1) == 1])
        v_current.append(round(count / days_in_window, 1))
        
        is_partial = week_end > cutoff_date
        labels.append(f'S-{w}{"*" if is_partial else ""}')
        
        if tickets_prev_full and event_config_prev:
            comparison_mode = event_config.get('comparison_mode', 'j_minus')
            if comparison_mode == 'days_since_launch' and event_config.get('launch_date') and event_config_prev.get('launch_date'):
                # DSL mode: match by days-since-launch
                days_since = (week_start - event_config['launch_date']).days
                prev_start = event_config_prev['launch_date'] + timedelta(days=days_since)
            else:
                # J-minus mode: match by weeks before event
                prev_event = event_config_prev['event_date_first']
                prev_start = prev_event - timedelta(days=w * 7)
            prev_end = prev_start + timedelta(days=6)
            prev_count = len([t for t in tickets_prev_full if prev_start <= t['order_date'] <= prev_end and t.get('is_paid', 1) == 1])
            v_prev.append(round(prev_count / 7, 1))
        else:
            v_prev.append(0)
    
    labels_js = str(labels)
    v26_js = str(v_current)
    v25_js = str(v_prev)
    
    has_prev = any(v > 0 for v in v_prev)
    
    gap_plugin = '''var velocityGapPlugin={id:'velocityGap',beforeDatasetsDraw:function(chart){
  var meta0=chart.getDatasetMeta(0),meta1=chart.getDatasetMeta(1);
  if(!meta0.data.length||!meta1.data.length)return;
  var ctx=chart.ctx,pts26=meta0.data,pts25=meta1.data;
  ctx.save();
  for(var i=0;i<pts26.length-1;i++){
    var x0=pts26[i].x,y26a=pts26[i].y,y25a=pts25[i].y;
    var x1=pts26[i+1].x,y26b=pts26[i+1].y,y25b=pts25[i+1].y;
    var d0=y25a-y26a,d1=y25b-y26b;
    if(d0*d1<0){var t=d0/(d0-d1);var cx=x0+t*(x1-x0),cy=y26a+t*(y26b-y26a);ctx.beginPath();ctx.moveTo(x0,y26a);ctx.lineTo(cx,cy);ctx.lineTo(x0,y25a);ctx.closePath();ctx.fillStyle=d0>0?'rgba(52,211,153,0.12)':'rgba(248,113,113,0.12)';ctx.fill();ctx.beginPath();ctx.moveTo(cx,cy);ctx.lineTo(x1,y26b);ctx.lineTo(x1,y25b);ctx.closePath();ctx.fillStyle=d1>0?'rgba(52,211,153,0.12)':'rgba(248,113,113,0.12)';ctx.fill()}
    else{ctx.beginPath();ctx.moveTo(x0,y26a);ctx.lineTo(x1,y26b);ctx.lineTo(x1,y25b);ctx.lineTo(x0,y25a);ctx.closePath();ctx.fillStyle=d0>=0?'rgba(52,211,153,0.12)':'rgba(248,113,113,0.12)';ctx.fill()}
  }ctx.restore()}};''' if has_prev else ''
    
    plugins_arr = '[velocityGapPlugin]' if has_prev else '[]'
    
    datasets = f'''[
          {{label:'{event_date.year}',data:{v26_js},borderColor:'#fbbf24',borderWidth:2.5,pointRadius:4,pointHoverRadius:7,pointBackgroundColor:'#fbbf24',pointBorderColor:'#16161f',pointBorderWidth:2,tension:.4,fill:false}}'''
    
    if has_prev:
        prev_year = event_config_prev['event_date_first'].year
        datasets += f''',
          {{label:'{prev_year}',data:{v25_js},borderColor:'rgba(239,68,68,0.5)',borderWidth:1.5,borderDash:[5,4],pointRadius:3,pointHoverRadius:5,pointBackgroundColor:'rgba(239,68,68,0.5)',pointBorderColor:'#16161f',pointBorderWidth:1.5,tension:.4,fill:false}}'''
    
    datasets += ']'
    
    return f'''{gap_plugin}
(function(){{
  var built=false;var canvas=document.getElementById('chartVelocity');if(!canvas)return;
  var panel=canvas.closest('.details-panel');if(!panel)return;
  new MutationObserver(function(){{
    if(!built&&panel.classList.contains('open')){{built=true;setTimeout(function(){{
      new Chart(canvas,{{type:'line',data:{{labels:{labels_js},datasets:{datasets}}},plugins:{plugins_arr},options:{{responsive:true,maintainAspectRatio:false,interaction:{{mode:'index',intersect:false}},plugins:{{legend:{{display:false}},tooltip:{{backgroundColor:'rgba(16,16,23,0.95)',borderColor:'rgba(255,255,255,0.08)',borderWidth:1,padding:12,titleFont:{{size:11,weight:'600'}},bodyFont:{{size:11}}}}}},scales:{{x:{{ticks:{{font:{{size:10}},color:'rgba(255,255,255,0.3)'}},grid:{{display:false}}}},y:{{min:0,ticks:{{font:{{size:10}},color:'rgba(255,255,255,0.25)'}},grid:{{color:'rgba(255,255,255,0.03)'}},title:{{display:true,text:'/jour',font:{{size:9}},color:'rgba(255,255,255,0.2)'}}}}}}
      }}}});
    }},80)}}
  }}).observe(panel,{{attributes:true,attributeFilter:['class']}});
}})();'''


def _generate_velocity_14d_chart_js_v3(tickets, tickets_prev_full, cutoff_date, event_config, event_config_prev, days_remaining):
    """Generate the 14-day rolling velocity Chart.js code."""
    event_date = event_config['event_date_first']
    labels = []
    v_current = []
    v_prev = []
    
    # Use bi-weekly windows, stepping by 1 week for a rolling 14d average
    max_weeks = max(16, (days_remaining // 7) + 4)
    
    for w in range(max_weeks, 0, -1):
        window_end = event_date - timedelta(days=w * 7)
        window_start = window_end - timedelta(days=13)
        
        # Skip if entirely in the future
        if window_start > cutoff_date:
            continue
        
        effective_end = min(window_end, cutoff_date)
        days_in_window = (effective_end - window_start).days + 1
        if days_in_window < 7:  # Need at least 7 days for meaningful 14d average
            continue
        
        count = len([t for t in tickets if window_start <= t['order_date'] <= effective_end and t.get('is_paid', 1) == 1])
        v_current.append(round(count / days_in_window, 1))
        
        is_partial = window_end > cutoff_date
        labels.append(f'S-{w}{"*" if is_partial else ""}')
        
        if tickets_prev_full and event_config_prev:
            comparison_mode = event_config.get('comparison_mode', 'j_minus')
            if comparison_mode == 'days_since_launch' and event_config.get('launch_date') and event_config_prev.get('launch_date'):
                days_since = (window_end - event_config['launch_date']).days
                prev_end = event_config_prev['launch_date'] + timedelta(days=days_since)
            else:
                prev_event = event_config_prev['event_date_first']
                prev_end = prev_event - timedelta(days=w * 7)
            prev_start = prev_end - timedelta(days=13)
            prev_count = len([t for t in tickets_prev_full if prev_start <= t['order_date'] <= prev_end and t.get('is_paid', 1) == 1])
            v_prev.append(round(prev_count / 14, 1))
        else:
            v_prev.append(0)
    
    labels_js = str(labels)
    v26_js = str(v_current)
    v25_js = str(v_prev)
    
    has_prev = any(v > 0 for v in v_prev)
    
    gap_plugin_14 = '''var vel14GapPlugin={id:'vel14Gap',beforeDatasetsDraw:function(chart){
  var meta0=chart.getDatasetMeta(0),meta1=chart.getDatasetMeta(1);
  if(!meta0.data.length||!meta1.data.length)return;
  var ctx=chart.ctx,pts26=meta0.data,pts25=meta1.data;
  ctx.save();
  for(var i=0;i<pts26.length-1;i++){
    var x0=pts26[i].x,y26a=pts26[i].y,y25a=pts25[i].y;
    var x1=pts26[i+1].x,y26b=pts26[i+1].y,y25b=pts25[i+1].y;
    var d0=y25a-y26a,d1=y25b-y26b;
    if(d0*d1<0){var t=d0/(d0-d1);var cx=x0+t*(x1-x0),cy=y26a+t*(y26b-y26a);ctx.beginPath();ctx.moveTo(x0,y26a);ctx.lineTo(cx,cy);ctx.lineTo(x0,y25a);ctx.closePath();ctx.fillStyle=d0>0?'rgba(52,211,153,0.12)':'rgba(248,113,113,0.12)';ctx.fill();ctx.beginPath();ctx.moveTo(cx,cy);ctx.lineTo(x1,y26b);ctx.lineTo(x1,y25b);ctx.closePath();ctx.fillStyle=d1>0?'rgba(52,211,153,0.12)':'rgba(248,113,113,0.12)';ctx.fill()}
    else{ctx.beginPath();ctx.moveTo(x0,y26a);ctx.lineTo(x1,y26b);ctx.lineTo(x1,y25b);ctx.lineTo(x0,y25a);ctx.closePath();ctx.fillStyle=d0>=0?'rgba(52,211,153,0.12)':'rgba(248,113,113,0.12)';ctx.fill()}
  }ctx.restore()}};''' if has_prev else ''
    
    plugins_arr = '[vel14GapPlugin]' if has_prev else '[]'
    
    datasets = f'''[
          {{label:'{event_date.year}',data:{v26_js},borderColor:'#fbbf24',borderWidth:2.5,pointRadius:4,pointHoverRadius:7,pointBackgroundColor:'#fbbf24',pointBorderColor:'#16161f',pointBorderWidth:2,tension:.4,fill:false}}'''
    
    if has_prev:
        prev_year = event_config_prev['event_date_first'].year
        datasets += f''',
          {{label:'{prev_year}',data:{v25_js},borderColor:'rgba(239,68,68,0.5)',borderWidth:1.5,borderDash:[5,4],pointRadius:3,pointHoverRadius:5,pointBackgroundColor:'rgba(239,68,68,0.5)',pointBorderColor:'#16161f',pointBorderWidth:1.5,tension:.4,fill:false}}'''
    
    datasets += ']'
    
    return f'''{gap_plugin_14}
(function(){{
  var built=false;var canvas=document.getElementById('chartVelocity14');if(!canvas)return;
  var panel=canvas.closest('.details-panel');if(!panel)return;
  new MutationObserver(function(){{
    if(!built&&panel.classList.contains('open')){{built=true;setTimeout(function(){{
      new Chart(canvas,{{type:'line',data:{{labels:{labels_js},datasets:{datasets}}},plugins:{plugins_arr},options:{{responsive:true,maintainAspectRatio:false,interaction:{{mode:'index',intersect:false}},plugins:{{legend:{{display:false}},tooltip:{{backgroundColor:'rgba(16,16,23,0.95)',borderColor:'rgba(255,255,255,0.08)',borderWidth:1,padding:12,titleFont:{{size:11,weight:'600'}},bodyFont:{{size:11}}}}}},scales:{{x:{{ticks:{{font:{{size:10}},color:'rgba(255,255,255,0.3)'}},grid:{{display:false}}}},y:{{min:0,ticks:{{font:{{size:10}},color:'rgba(255,255,255,0.25)'}},grid:{{color:'rgba(255,255,255,0.03)'}},title:{{display:true,text:'/jour',font:{{size:9}},color:'rgba(255,255,255,0.2)'}}}}}}
      }}}});
    }},80)}}
  }}).observe(panel,{{attributes:true,attributeFilter:['class']}});
}})();'''


def _generate_revenue_chart_js_v3(tickets, tickets_prev_full, cutoff_date, event_config, event_config_prev, days_remaining):
    """Generate cumulative revenue Chart.js code, aligned by J-X countdown."""
    from collections import defaultdict
    
    event_date = event_config['event_date_first']
    
    # Build weekly cumulative revenue for 2026, aligned by weeks-before-event
    paid_26 = sorted([t for t in tickets if t.get('is_paid', 1) == 1], key=lambda t: t['order_date'])
    
    # Aggregate revenue by week relative to event
    current_week = max(0, (days_remaining + 6) // 7)
    max_weeks = max(20, current_week + 2)  # Always cover current selling period
    rev_by_week_26 = defaultdict(float)
    for t in paid_26:
        w = (event_date - t['order_date']).days // 7
        if 0 <= w <= max_weeks:
            rev_by_week_26[w] += t['price']
    
    # Build cumulative from oldest week to newest
    weeks_with_data = sorted(set(rev_by_week_26.keys()), reverse=True)
    if not weeks_with_data:
        return ''
    
    start_week = weeks_with_data[0]  # Furthest from event
    
    labels = []
    cum_26 = []
    cum_25 = []
    running_26 = 0
    running_25 = 0
    
    # Previous year data
    rev_by_week_25 = defaultdict(float)
    if tickets_prev_full and event_config_prev:
        comparison_mode = event_config.get('comparison_mode', 'j_minus')
        if comparison_mode == 'days_since_launch' and event_config.get('launch_date') and event_config_prev.get('launch_date'):
            # DSL mode: bucket previous year by weeks-since-launch, mapped to current year's week grid
            launch_cur = event_config['launch_date']
            launch_prev = event_config_prev['launch_date']
            for t in tickets_prev_full:
                if t.get('is_paid', 1) != 1:
                    continue
                # Days since prev launch
                days_since_prev = (t['order_date'] - launch_prev).days
                # Map to current year: what week-before-event would this be?
                equiv_date_cur = launch_cur + timedelta(days=days_since_prev)
                w = (event_date - equiv_date_cur).days // 7
                if 0 <= w <= max_weeks:
                    rev_by_week_25[w] += t['price']
        else:
            prev_event = event_config_prev['event_date_first']
            for t in tickets_prev_full:
                if t.get('is_paid', 1) != 1:
                    continue
                w = (prev_event - t['order_date']).days // 7
                if 0 <= w <= max_weeks:
                    rev_by_week_25[w] += t['price']
    
    all_weeks = max(start_week, max(rev_by_week_25.keys()) if rev_by_week_25 else 0)
    
    for w in range(all_weeks, -1, -1):
        running_26 += rev_by_week_26.get(w, 0)
        running_25 += rev_by_week_25.get(w, 0)
        labels.append(f'S-{w}' if w > 0 else 'Événement')
        cum_26.append(round(running_26))
        cum_25.append(round(running_25))
    
    # Trim leading zeros from both
    first_nonzero = 0
    for i, (a, b) in enumerate(zip(cum_26, cum_25)):
        if a > 0 or b > 0:
            first_nonzero = i
            break
    labels = labels[first_nonzero:]
    cum_26 = cum_26[first_nonzero:]
    cum_25 = cum_25[first_nonzero:]
    
    # For 2026, null out future weeks (after current week)
    # current_week = weeks remaining, so S-{current_week} is current
    # In our array, index for S-w is (all_weeks - w - first_nonzero_offset)
    # Simpler: null out entries where cum value hasn't changed from last real data
    # Actually: just cut 2026 data at current week
    cutoff_idx = len(labels)
    for i, l in enumerate(labels):
        if l == 'Événement':
            cutoff_idx = i
            break
        w_num = int(l.split('-')[1])
        if w_num < current_week:
            cutoff_idx = i
            break
    
    # Replace future 2026 points with null
    for i in range(cutoff_idx, len(cum_26)):
        cum_26[i] = None
    
    labels_js = str(labels)
    
    # Format data with null handling
    def fmt_data(arr):
        return '[' + ','.join('null' if v is None else str(v) for v in arr) + ']'
    
    c26_js = fmt_data(cum_26)
    c25_js = fmt_data(cum_25)
    
    has_prev = any(v > 0 for v in cum_25)
    
    # Gap fill plugin
    gap_plugin = '''var revGapPlugin={id:'revGap',beforeDatasetsDraw:function(chart){
  var meta0=chart.getDatasetMeta(0),meta1=chart.getDatasetMeta(1);
  if(!meta0.data.length||!meta1.data.length)return;
  var ctx=chart.ctx,pts26=meta0.data,pts25=meta1.data;
  ctx.save();
  for(var i=0;i<pts26.length-1;i++){
    var p0=pts26[i],p1=pts26[i+1],q0=pts25[i],q1=pts25[i+1];
    if(!p0||!p1||!q0||!q1)continue;
    if(p0.skip||p1.skip||!isFinite(p0.y)||!isFinite(p1.y)||!isFinite(q0.y)||!isFinite(q1.y))continue;
    var x0=p0.x,y26a=p0.y,y25a=q0.y,x1=p1.x,y26b=p1.y,y25b=q1.y;
    var ahead=y26a-y25a;
    ctx.beginPath();ctx.moveTo(x0,y26a);ctx.lineTo(x1,y26b);ctx.lineTo(x1,y25b);ctx.lineTo(x0,y25a);ctx.closePath();
    ctx.fillStyle=ahead<=0?'rgba(52,211,153,0.18)':'rgba(248,113,113,0.18)';ctx.fill();
  }ctx.restore()}};''' if has_prev else ''
    
    plugins_arr = '[revGapPlugin]' if has_prev else '[]'
    
    datasets = f'''[
          {{label:'{event_date.year}',data:{c26_js},borderColor:'#fbbf24',borderWidth:2.5,pointRadius:3,pointHoverRadius:6,pointBackgroundColor:'#fbbf24',pointBorderColor:'#16161f',pointBorderWidth:2,tension:.4,fill:false,spanGaps:false}}'''
    
    if has_prev:
        prev_year = event_config_prev['event_date_first'].year
        datasets += f''',
          {{label:'{prev_year}',data:{c25_js},borderColor:'rgba(239,68,68,0.5)',borderWidth:1.5,borderDash:[5,4],pointRadius:3,pointHoverRadius:5,pointBackgroundColor:'rgba(239,68,68,0.5)',pointBorderColor:'#16161f',pointBorderWidth:1.5,tension:.4,fill:false}}'''
    
    datasets += ']'
    
    return f'''{gap_plugin}
(function(){{
  var built=false;var canvas=document.getElementById('chartRevenue');if(!canvas)return;
  var panel=canvas.closest('.details-panel');if(!panel)return;
  new MutationObserver(function(){{
    if(!built&&panel.classList.contains('open')){{built=true;setTimeout(function(){{
      new Chart(canvas,{{type:'line',data:{{labels:{labels_js},datasets:{datasets}}},plugins:{plugins_arr},options:{{responsive:true,maintainAspectRatio:false,interaction:{{mode:'index',intersect:false}},plugins:{{legend:{{display:false}},tooltip:{{backgroundColor:'rgba(16,16,23,0.95)',borderColor:'rgba(255,255,255,0.08)',borderWidth:1,padding:12,titleFont:{{size:11,weight:'600'}},bodyFont:{{size:11}},callbacks:{{label:function(c){{if(c.parsed.y==null)return null;return c.dataset.label+': €'+(c.parsed.y/1000).toFixed(0)+'k'}}}}}}}},scales:{{x:{{ticks:{{font:{{size:10}},color:'rgba(255,255,255,0.3)',maxTicksLimit:8}},grid:{{display:false}}}},y:{{ticks:{{font:{{size:10}},color:'rgba(255,255,255,0.25)',callback:function(v){{return '€'+(v/1000).toFixed(0)+'k'}}}},grid:{{color:'rgba(255,255,255,0.03)'}}}}}}}}}});
    }},80)}}
  }}).observe(panel,{{attributes:true,attributeFilter:['class']}});
}})();'''
def _generate_projection_charts_js_v3(tickets, tickets_prev_full, cutoff_date, event_config, event_config_prev, metrics, day_presence):
    """Generate Chart.js code for projection cumulative curves per day with dual scenarios."""
    from collections import defaultdict
    
    day_names = [d['day_name'].lower() for d in event_config['days']]
    day_configs = {d['day_name'].lower(): d for d in event_config['days']}
    event_date = event_config['event_date_first']
    days_remaining = max(0, (event_date - cutoff_date).days)  # clamp to 0 when event is past
    num_days = len(day_names)
    paid = [t for t in tickets if t.get('is_paid', 1) == 1]
    
    # Day name mapping for reference year (Day 1↔Day 1 in DSL mode)
    prev_presence_key_map = {}
    if event_config.get('comparison_mode', 'j_minus') == 'days_since_launch' and event_config_prev:
        prev_day_names_list = [d['day_name'].lower() for d in event_config_prev['days']]
        for idx, dn in enumerate(day_names):
            prev_presence_key_map[dn] = f'presence_{prev_day_names_list[idx]}' if idx < len(prev_day_names_list) else f'presence_{dn}'
    else:
        for dn in day_names:
            prev_presence_key_map[dn] = f'presence_{dn}'
    
    # ── Reference year acceleration ratios ──
    hist_accel = {}
    comparison_mode = event_config.get('comparison_mode', 'j_minus')
    dsl_prev_cutoff = None
    if comparison_mode == 'days_since_launch' and event_config.get('launch_date') and event_config_prev and event_config_prev.get('launch_date'):
        days_since_launch = (cutoff_date - event_config['launch_date']).days
        dsl_prev_cutoff = event_config_prev['launch_date'] + timedelta(days=days_since_launch)
    
    if tickets_prev_full and event_config_prev:
        prev_event = event_config_prev['event_date_first']
        prev_paid = [t for t in tickets_prev_full if t.get('is_paid', 1) == 1]
        for dn in day_names:
            # Build weekly velocity buckets (same as projection cards)
            weeks = []
            d = days_remaining
            while d > 0:
                bucket_end_j = d
                bucket_start_j = max(d - 7, 0)
                bucket_days = bucket_end_j - bucket_start_j
                if bucket_days < 1:
                    break
                if dsl_prev_cutoff:
                    start_date = dsl_prev_cutoff + timedelta(days=days_remaining - bucket_end_j)
                    end_date = dsl_prev_cutoff + timedelta(days=days_remaining - bucket_start_j - 1)
                else:
                    start_date = prev_event - timedelta(days=bucket_end_j)
                    end_date = prev_event - timedelta(days=bucket_start_j + 1)
                bucket_tix = [t for t in prev_paid if start_date <= t['order_date'] <= end_date]
                vel = sum(t.get(prev_presence_key_map[dn], 0) for t in bucket_tix) / bucket_days if bucket_tix else 0
                weeks.append({'days': bucket_days, 'vel': vel})
                d -= 7
            baseline_vel = weeks[0]['vel'] if weeks and weeks[0]['vel'] > 0 else 1
            accel_ratios = []
            for w in weeks:
                ratio = w['vel'] / baseline_vel if baseline_vel > 0 else 1.0
                accel_ratios.append((w['days'], max(ratio, 0.1)))
            hist_accel[dn] = {'ratios': accel_ratios}
    
    js_parts = []
    
    # Dynamic chart width: sales history + future days
    # Find first sale date to determine lookback
    paid_all = [t for t in tickets if t.get('is_paid', 1) == 1]
    if paid_all:
        first_sale = min(t['order_date'] for t in paid_all)
        history_days = (cutoff_date - first_sale).days
    else:
        history_days = 30
    history_days = max(history_days, 14)  # minimum 14 days lookback
    
    N_POINTS = history_days + days_remaining + 1  # +1 for cutoff day itself
    cutoff_idx_base = history_days  # position of cutoff in the array
    
    js_parts.append(f"const N={cutoff_idx_base};")
    # Labels: J-(history+remaining) down to J-0
    total_j = history_days + days_remaining
    js_parts.append(f"const L=Array.from({{length:{N_POINTS}}},(_,i)=>'J-'+({total_j}-i));")
    js_parts.append("window._projBuilders = {};")
    
    for i, dn in enumerate(day_names):
        cap = day_configs[dn]['day_capacity']
        pres = day_presence.get(dn, 0)
        c = DAY_PALETTE_V3[i % len(DAY_PALETTE_V3)]
        
        # 7d velocity (for standard profile) and 14d velocity (for coefficient scenario)
        last_7 = cutoff_date - timedelta(days=6)
        t7 = [t for t in paid if last_7 <= t['order_date'] <= cutoff_date]
        vel_7d = sum(t.get(f'presence_{dn}', 0) for t in t7) / 7
        
        last_14 = cutoff_date - timedelta(days=13)
        t14 = [t for t in paid if last_14 <= t['order_date'] <= cutoff_date]
        vel_14d = sum(t.get(f'presence_{dn}', 0) for t in t14) / 14
        
        # Build single projection curve: Trajectoire (with ref) or Standard profile (without)
        has_reference = dn in hist_accel
        proj_curve = [None] * N_POINTS
        cutoff_idx = cutoff_idx_base
        proj_curve[cutoff_idx] = int(pres)
        
        if has_reference:
            ratios_list = hist_accel[dn].get('ratios', [(days_remaining, 1.0)])
            proj_color = 'rgba(251,191,36,.8)'
        else:
            # Standard festival profile ratios
            STANDARD_PROFILE = {
                20: 0.4, 19: 0.5, 18: 0.6, 17: 0.6, 16: 0.5,
                15: 0.5, 14: 0.7, 13: 0.7, 12: 0.8, 11: 0.8,
                10: 1.0, 9: 1.0, 8: 0.9, 7: 0.9, 6: 1.1,
                5: 1.6, 4: 1.8, 3: 1.6, 2: 1.8, 1: 3.0, 0: 3.0
            }
            current_week = max(0, min(20, (days_remaining + 6) // 7))
            current_mult = max(STANDARD_PROFILE.get(current_week, 1.0), 0.5)
            ratios_list = []
            d = days_remaining
            while d > 0:
                bucket_days = min(7, d)
                week_num = max(0, min(20, (d + 6) // 7))
                ratio = STANDARD_PROFILE.get(week_num, 1.0) / current_mult
                ratios_list.append((bucket_days, max(ratio, 0.1)))
                d -= 7
            proj_color = 'rgba(167,139,250,.8)'
        
        # Build projection from ratios (this is the COEFFICIENT scenario = scenario B, uses 14d velocity)
        day_ratios = []
        for bucket_days, ratio in ratios_list:
            day_ratios.extend([ratio] * bucket_days)
        vel_for_coef = vel_14d if has_reference else vel_7d  # 14d for coefficient, 7d for standard profile
        val = pres
        for d in range(1, days_remaining + 1):
            ratio = day_ratios[d - 1] if d - 1 < len(day_ratios) else day_ratios[-1] if day_ratios else 1.0
            val += vel_for_coef * ratio
            proj_curve[cutoff_idx + d] = min(int(val), cap)
        
        # Build REPLAY curve (scenario A): pure reference remaining-day sales grafted on
        replay_curve = [None] * N_POINTS
        replay_curve[cutoff_idx] = int(pres)
        if has_reference and tickets_prev_full and event_config_prev:
            prev_event_replay = event_config_prev['event_date_first']
            prev_paid_replay = [t for t in tickets_prev_full if t.get('is_paid', 1) == 1]
            replay_val = pres
            for d_offset in range(1, days_remaining + 1):
                if dsl_prev_cutoff:
                    prev_date = dsl_prev_cutoff + timedelta(days=d_offset)
                else:
                    prev_date = prev_event_replay - timedelta(days=days_remaining - d_offset)
                day_sales = sum(1 for t in prev_paid_replay 
                               if t['order_date'] == prev_date and t.get(prev_presence_key_map[dn], 0) > 0)
                replay_val += day_sales
                replay_curve[cutoff_idx + d_offset] = min(int(replay_val), cap)
        
        # Build actual 2026 data curve (real cumulative presence by day)
        actual_data = [None] * N_POINTS
        # Pre-compute: count presence per order_date for this day
        from collections import Counter
        pres_by_date_cur = Counter()
        for t in paid:
            if t.get(f'presence_{dn}', 0) > 0:
                pres_by_date_cur[t['order_date']] += 1
        # Build cumulative for each chart position
        cum = 0
        for p in range(cutoff_idx + 1):
            d = first_sale + timedelta(days=p)
            cum += pres_by_date_cur.get(d, 0)
            actual_data[p] = cum
        
        # Build reference year curve (real cumulative, aligned)
        prev_data = [None] * N_POINTS
        prev_year_label = event_config_prev['event_date_first'].year if event_config_prev else 'Réf.'
        if tickets_prev_full and event_config_prev:
            prev_event = event_config_prev['event_date_first']
            prev_paid = [t for t in tickets_prev_full if t.get('is_paid', 1) == 1]
            pres_by_date_prev = Counter()
            for t in prev_paid:
                if t.get(prev_presence_key_map[dn], 0) > 0:
                    pres_by_date_prev[t['order_date']] += 1
            # Align reference year curve
            if dsl_prev_cutoff:
                # DSL mode: start from same days-since-launch offset
                prev_start = dsl_prev_cutoff - timedelta(days=history_days)
            else:
                # J-minus mode: same J-X from event
                total_j = history_days + days_remaining
                prev_start = prev_event - timedelta(days=total_j)
            # Pre-accumulate any sales before the chart start date
            cum_prev = sum(v for d, v in pres_by_date_prev.items() if d < prev_start)
            for p in range(N_POINTS):
                prev_d = prev_start + timedelta(days=p)
                cum_prev += pres_by_date_prev.get(prev_d, 0)
                prev_data[p] = cum_prev
            # Include any remaining sales after the chart range (event day sales)
            post_sales = sum(v for d, v in pres_by_date_prev.items() if d > prev_start + timedelta(days=N_POINTS - 1))
            if post_sales > 0 and N_POINTS > 0:
                prev_data[-1] = prev_data[-1] + post_sales
        
        # Y-axis: percentage of capacity (0-100%)
        # Normalize 2026 data and projections to 2026 capacity
        # Normalize 2025 data to 2025 capacity
        prev_cap = 0
        if event_config_prev:
            prev_day_configs = {d['day_name'].lower(): d for d in event_config_prev['days']}
            # In DSL mode, map by position (samedi→vendredi, dimanche→samedi)
            mapped_dn = prev_presence_key_map[dn].replace('presence_', '')
            prev_cap = prev_day_configs.get(mapped_dn, {}).get('day_capacity', cap)
        if prev_cap == 0:
            prev_cap = cap  # fallback
        
        def _to_pct(data_list, capacity):
            """Convert absolute values to percentage of capacity."""
            return [round(v / capacity * 100, 1) if v is not None and capacity > 0 else None for v in data_list]
        
        actual_data_pct = _to_pct(actual_data, cap)
        proj_curve_pct = _to_pct(proj_curve, cap)
        replay_curve_pct = _to_pct(replay_curve, cap) if has_reference else [None] * N_POINTS
        prev_data_pct = _to_pct(prev_data, prev_cap)
        
        tick_step = max(1, N_POINTS // 6)
        co = f"{{responsive:true,maintainAspectRatio:false,interaction:{{mode:'index',intersect:false}},plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:function(c){{if(c.parsed.y==null)return null;return c.dataset.label+': '+c.parsed.y.toFixed(1)+'%'}}}}}},annotation:{{annotations:{{cap:{{type:'line',yMin:100,yMax:100,borderColor:'rgba(255,255,255,0.35)',borderWidth:1.5,borderDash:[8,4]}},now:{{type:'line',xMin:N,xMax:N,borderColor:'rgba(255,255,255,0.2)',borderWidth:1,borderDash:[3,3]}}}}}}}},scales:{{x:{{ticks:{{maxTicksLimit:7,font:{{size:9}},callback:(v,idx)=>idx%{tick_step}===0?L[idx]:''}},grid:{{display:false}}}},y:{{min:0,max:110,ticks:{{font:{{size:9}},callback:v=>v+'%'}},grid:{{color:'rgba(255,255,255,0.03)'}}}}}}}}"
        
        # Convert Python lists to JSON (None → null)
        import json
        a_js = json.dumps(actual_data_pct)
        proj_js = json.dumps(proj_curve_pct)
        p_js = json.dumps(prev_data_pct)
        
        prev_year_label = event_config_prev['event_date_first'].year if event_config_prev else ''
        proj_label_a = f'Trajectoire {prev_year_label}' if has_reference else 'Profil standard'
        proj_label_b = f'{prev_year_label} × coef. {event_date.year}' if has_reference else ''
        
        # Common datasets
        ds_common = f"{{label:'Ventes {event_date.year}',data:{a_js},borderColor:'#fbbf24',borderWidth:1.5,pointRadius:0,tension:.3,fill:false}}"
        
        if has_reference:
            import json as json2
            replay_js = json2.dumps(replay_curve_pct)
            
            ds_prev = f"{{label:'{prev_year_label}',data:{p_js},borderColor:'rgba(239,68,68,.5)',borderWidth:1.5,borderDash:[4,3],pointRadius:0,tension:.3,fill:false}}"
            
            # Chart S1: Replay (pure 2025) - yellow dashed
            ds_replay = f"{{label:'{proj_label_a}',data:{replay_js},borderColor:'rgba(251,191,36,.8)',borderWidth:2,borderDash:[8,5],pointRadius:0,tension:.3,fill:false}}"
            datasets_s1 = f"[{ds_common},{ds_replay},{ds_prev}]"
            chart_s1 = f"new Chart(document.getElementById('chartDay{i}S1'),{{type:'line',data:{{labels:L,datasets:{datasets_s1}}},options:{co}}})"
            
            # Chart S2: Coefficient (2025 × coef)
            ds_coef = f"{{label:'{proj_label_b}',data:{proj_js},borderColor:'rgba(251,191,36,.8)',borderWidth:2,borderDash:[8,5],pointRadius:0,tension:.3,fill:false}}"
            datasets_s2 = f"[{ds_common},{ds_coef},{ds_prev}]"
            chart_s2 = f"new Chart(document.getElementById('chartDay{i}S2'),{{type:'line',data:{{labels:L,datasets:{datasets_s2}}},options:{co}}})"
            
            if i == 0:
                js_parts.append(f"// Day 0 - built immediately\n{chart_s1};")
                js_parts.append(f"window._projBuilders['day{i}S2'] = function(){{{chart_s2}}};")
            else:
                js_parts.append(f"window._projBuilders['day{i}S1'] = function(){{{chart_s1}}};")
                js_parts.append(f"window._projBuilders['day{i}S2'] = function(){{{chart_s2}}};")
        else:
            ds_proj = f"{{label:'{proj_label_a}',data:{proj_js},borderColor:'{proj_color}',borderWidth:2,borderDash:[8,5],pointRadius:0,tension:.3,fill:false}}"
            datasets = f"[{ds_common},{ds_proj}]"
            chart_code = f"new Chart(document.getElementById('chartDay{i}S1'),{{type:'line',data:{{labels:L,datasets:{datasets}}},options:{co}}})"
            
            if i == 0:
                js_parts.append(f"// Day 0 - built immediately\n{chart_code};")
            else:
                js_parts.append(f"window._projBuilders['day{i}S1'] = function(){{{chart_code}}};")
    
    return '\n'.join(js_parts)


def _generate_hebdo_chart_js_v3(tickets, tickets_prev_full, cutoff_date, event_config, event_config_prev):
    """Generate weekly sales bar chart JS."""
    from collections import defaultdict
    
    event_date = event_config['event_date_first']
    
    labels = []
    data_current = []
    data_prev = []
    
    for w in range(9, 1, -1):
        week_start = event_date - timedelta(days=w * 7)
        week_end = week_start + timedelta(days=6)
        
        count = len([t for t in tickets if week_start <= t['order_date'] <= week_end and t.get('is_paid', 1) == 1])
        data_current.append(count)
        labels.append(f'S-{w}')
        
        if tickets_prev_full and event_config_prev:
            comparison_mode = event_config.get('comparison_mode', 'j_minus')
            if comparison_mode == 'days_since_launch' and event_config.get('launch_date') and event_config_prev.get('launch_date'):
                days_since = (week_start - event_config['launch_date']).days
                prev_start = event_config_prev['launch_date'] + timedelta(days=days_since)
            else:
                prev_event = event_config_prev['event_date_first']
                prev_start = prev_event - timedelta(days=w * 7)
            prev_end = prev_start + timedelta(days=6)
            prev_count = len([t for t in tickets_prev_full if prev_start <= t['order_date'] <= prev_end and t.get('is_paid', 1) == 1])
            data_prev.append(prev_count)
        else:
            data_prev.append(0)
    
    prev_year = event_config_prev['event_date_first'].year if event_config_prev else 'Réf.'
    
    return f"""window._projBuilders['hebdo'] = function(){{new Chart(document.getElementById('chartHebdo'),{{type:'bar',data:{{labels:{labels},datasets:[{{label:'{prev_year}',data:{data_prev},backgroundColor:'rgba(255,255,255,.08)',borderRadius:4,barPercentage:.7,categoryPercentage:.7}},{{label:'{event_date.year}',data:{data_current},backgroundColor:'rgba(251,191,36,.6)',borderRadius:4,barPercentage:.7,categoryPercentage:.7}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{position:'top',labels:{{usePointStyle:true,pointStyle:'rectRounded',padding:16,font:{{size:10}}}}}}}},scales:{{x:{{ticks:{{font:{{size:9}}}},grid:{{display:false}}}},y:{{ticks:{{font:{{size:9}},callback:v=>v>=1000?(v/1000).toFixed(1)+'k':v}},grid:{{color:'rgba(255,255,255,.03)'}}}}}}}}}})}}"""


# ============================================================================
# MAIN WORKFLOW (updated to use v3 template)
# ============================================================================

def main():
    print_header("FESTIFLOW - Dashboard Builder v4.3")
    
    parser = argparse.ArgumentParser(description="Generate festival dashboards")
    parser.add_argument("--event", help="Force event ID from config (e.g., bordeaux_2026)")
    parser.add_argument("--current-dice", help="Current year DICE zip")
    parser.add_argument("--current-shotgun", help="Current year Shotgun CSV")
    parser.add_argument("--previous-dice", help="Previous year DICE zip")
    parser.add_argument("--previous-shotgun", help="Previous year Shotgun CSV")
    args = parser.parse_args()
    
    # Ensure directories exist
    for d in [RAW_DIR, MERGED_DIR, OUTPUT_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    
    # ========= DETECT EVENT FROM CONFIG =========
    event_config = None
    event_config_prev = None
    
    if CONFIG_PATH.exists():
        if args.event:
            event_config = load_event_config(CONFIG_PATH, args.event)
            print_success(f"Loaded config for: {event_config['event_name']}")
            if event_config.get('compare_to'):
                compare_id = event_config['compare_to']
                try:
                    event_config_prev = load_event_config(CONFIG_PATH, compare_id)
                except SystemExit:
                    print_warning(f"Comparison event '{compare_id}' not found in config")
        else:
            event_config, event_config_prev = detect_event_from_files(RAW_DIR, CONFIG_PATH)
            if event_config:
                print_success(f"Auto-detected event: {event_config['event_name']}")
                if not event_config_prev and event_config.get('compare_to'):
                    compare_id = event_config['compare_to']
                    try:
                        event_config_prev = load_event_config(CONFIG_PATH, compare_id)
                    except SystemExit:
                        print_warning(f"Comparison event '{compare_id}' not found in config")
    
    if not event_config:
        print_warning("No event config detected. Using file auto-detection only.")
    else:
        print(f"\n📋 Event: {event_config['event_name']}")
        print(f"   Venue: {event_config['venue']}, {event_config['city']}")
        print(f"   Days: {event_config['num_days']}")
        for d in event_config['days']:
            print(f"   - {d['day_name']} ({d['day_date']}): {d['day_capacity']:,} capacity")
        print(f"   Total capacity: {event_config['total_capacity']:,}")
        if event_config_prev:
            print(f"   Comparing to: {event_config_prev['event_name']}")
    
    # ========= MATCH FILES =========
    matched = auto_match_files(RAW_DIR)
    if not matched:
        print_error("Could not find matching DICE + Shotgun files")
        sys.exit(1)
    
    # ========= MERGE CURRENT YEAR =========
    print_header("STEP 1: MERGE CURRENT YEAR DATA")
    if matched['current']['dice']:
        dice_current = process_dice_zip(matched['current']['dice'])
    else:
        dice_current = []
        print_info("No DICE data — Shotgun only")
    shotgun_current = process_shotgun_csv(matched['current']['shotgun'])
    
    # Check for merge_into Shotgun CSVs (e.g. presale events)
    if event_config:
        merge_into_files = find_merge_into_files(RAW_DIR, CONFIG_PATH, event_config['event_id'])
        for child_csv, child_event in merge_into_files:
            print_header(f"PROCESSING MERGE_INTO: {child_event['event_name']}")
            child_tickets = process_shotgun_csv(child_csv)
            shotgun_current.extend(child_tickets)
            print_success(f"Added {len(child_tickets)} tickets from {child_event['event_name']}")
    
    merged_current = merge_tickets(dice_current, shotgun_current)
    save_merged_csv(merged_current, MERGED_DIR / "merged_current.csv")
    
    # ========= LOAD PREVIOUS YEAR (from merged CSV only) =========
    # Historical comparison reads a pre-merged PII-free CSV from HISTORICAL_DIR.
    # Raw files (DICE zips, Shotgun valid_orders_*/valid_tickets_*) are never
    # consumed for historical comparison. See HANDOFF §data-handling and
    # incident 2026-04-21_PII_EXPOSURE.
    merged_previous = None
    historical_csvs = sorted(HISTORICAL_DIR.glob("*_merged.csv")) if HISTORICAL_DIR.exists() else []

    if historical_csvs:
        print_header("STEP 2: LOAD PREVIOUS YEAR (from merged CSV)")
        if len(historical_csvs) > 1:
            print_info(f"Multiple merged CSVs in historical dir, concatenating {len(historical_csvs)} files")
        merged_previous = []
        for hist_csv in historical_csvs:
            with open(hist_csv, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            print_success(f"Loaded {len(rows)} tickets from {hist_csv.name}")
            merged_previous.extend(rows)
    elif event_config and event_config.get('compare_to'):
        print_error(
            f"compare_to='{event_config['compare_to']}' but no *_merged.csv "
            f"found in csv_database/{event_config['compare_to']}/. Historical "
            f"comparison requires a merged CSV. See HANDOFF §data-handling."
        )
        sys.exit(1)
    # else: no compare_to configured — single-event dashboard, skip comparison.
    
    # ========= LOAD & CALCULATE =========
    print_header("STEP 3: CALCULATE METRICS")
    tickets_current, cutoff_velocity, cutoff_cumulative = load_ticket_data(merged_current, event_config=event_config)
    metrics_current = calculate_metrics(tickets_current, event_config, velocity_cutoff=cutoff_velocity)
    
    # For display and days_remaining, use velocity cutoff (complete days)
    cutoff_date = cutoff_velocity
    
    # Comparison
    comparison = None
    metrics_prev = None
    tickets_prev_filtered = None
    tickets_prev_full = None
    
    if merged_previous and event_config and event_config_prev:
        tickets_prev_all, _, _ = load_ticket_data(merged_previous, event_config=event_config_prev)
        # Cap previous year data at event date (exclude post-event ghost tickets)
        prev_event_last = event_config_prev['event_date_last']
        tickets_before_cap = len(tickets_prev_all)
        tickets_prev_all = [t for t in tickets_prev_all if t['order_date'] <= prev_event_last]
        tickets_after_cap = len(tickets_prev_all)
        if tickets_before_cap != tickets_after_cap:
            print(f"   ✂️  Capped {event_config_prev['event_date_first'].year} data at event date ({prev_event_last}): {tickets_before_cap} → {tickets_after_cap} (removed {tickets_before_cap - tickets_after_cap} post-event tickets)")
        tickets_prev_full = tickets_prev_all
        
        # Compute launch dates from actual first sale in data
        current_dates = sorted(set(t['order_date'] for t in tickets_current))
        prev_dates = sorted(set(t['order_date'] for t in tickets_prev_all))
        if current_dates and prev_dates:
            launch_date_current = datetime.strptime(current_dates[0], '%Y-%m-%d').date() if isinstance(current_dates[0], str) else current_dates[0]
            launch_date_prev = datetime.strptime(prev_dates[0], '%Y-%m-%d').date() if isinstance(prev_dates[0], str) else prev_dates[0]
            event_config['launch_date'] = launch_date_current
            event_config_prev['launch_date'] = launch_date_prev
            print(f"\n🚀 Launch dates (from data):")
            print(f"   Current: {launch_date_current}")
            print(f"   Previous: {launch_date_prev}")
        
        # Filter previous year to same point based on comparison_mode
        comparison_mode = event_config.get('comparison_mode', 'j_minus')
        if comparison_mode == 'days_since_launch' and 'launch_date' in event_config and 'launch_date' in event_config_prev:
            tickets_prev_filtered = filter_tickets_to_same_point_dsl(
                tickets_prev_all, cutoff_cumulative,
                event_config['launch_date'],
                event_config_prev['launch_date']
            )
        else:
            tickets_prev_filtered = filter_tickets_to_same_point(
                tickets_prev_all, cutoff_cumulative,
                event_config['event_date_first'],
                event_config_prev['event_date_first']
            )
        metrics_prev = calculate_metrics(tickets_prev_filtered, event_config_prev)
        comparison = compare_years(metrics_current, metrics_prev)
    
    # ========= GENERATE HTML (V3) =========
    print_header("STEP 4: GENERATE FESTIFLOW V3 DASHBOARD")
    
    html = build_dashboard_html_v3(
        TEMPLATE_PATH, metrics_current, cutoff_date, event_config,
        tickets=tickets_current,
        tickets_prev_filtered=tickets_prev_filtered,
        tickets_prev_full=tickets_prev_full,
        comparison=comparison,
        metrics_prev=metrics_prev,
        event_config_prev=event_config_prev,
        cutoff_cumulative=cutoff_cumulative
    )
    
    # Save - set generation time as late as possible (right before write)
    html = html.replace('{{GENERATION_TIME_PLACEHOLDER}}', datetime.now(ZoneInfo('Europe/Paris')).strftime('%H:%M'))
    output_path = OUTPUT_DIR / "dashboard_FINAL.html"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    # Summary
    print_header("✅ DASHBOARD GENERATED SUCCESSFULLY!")
    print(f"📊 Event: {event_config['event_name']}")
    print(f"   Tickets: {fmt_num(metrics_current['total_tickets'])}")
    print(f"   Revenue: {fmt_currency(metrics_current['total_revenue'])}")
    print(f"   Presence: {fmt_num(metrics_current['total_presence'])} / {fmt_num(event_config['total_capacity'])}")
    
    if comparison:
        print(f"\n📈 Year-over-year:")
        print(f"   Tickets: {comparison['ticket_diff']:+,} ({comparison['ticket_growth_pct']:+.1f}%)")
        print(f"   Revenue: {fmt_currency(comparison['revenue_diff'])} ({comparison['revenue_growth_pct']:+.1f}%)")
    
    print(f"\n📄 Output: {output_path}")
    print(f"⏱️  Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
