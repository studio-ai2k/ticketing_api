#!/usr/bin/env python3
"""
Generate the HTML dashboard from an API-fetched merged CSV.

run.py's current-year path expects raw platform exports (a DICE zip plus a
Shotgun CSV) and has no option for a pre-merged CSV, so this shim feeds the
merged rows in by replacing run.py's two file-loading functions at import time,
then calls run.main() unchanged. run.py itself is never modified.

Everything downstream - merge, metrics, comparison, template rendering - is
run.py's own code, so the dashboard is exactly what the production pipeline
would produce from the same tickets.

Mirrors the environment main.py sets up for its subprocess call (see
main.py:233-247): FESTIFLOW_RAW_DIR, FESTIFLOW_HISTORICAL_DIR,
FESTIFLOW_OUTPUT_DIR, and the historical merged CSV copied in from
csv_database/<compare_to>/.

    python scripts/build_dashboard.py --event rennes_2026 \
        --csv api_output/rennes_2026_merged.csv \
        --out api_output/rennes_2026.html
"""

import argparse
import csv
import inspect
import json
import os
import shutil
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import suivi_candidates

BASE_DIR = Path(__file__).resolve().parent.parent


def _iso(value):
    """date -> 'YYYY-MM-DD', anything else -> None."""
    return value.isoformat() if hasattr(value, 'isoformat') else None


def read_config_field(config_path, event_id, field):
    """Read one event-level field for an event from event_config.csv."""
    with open(config_path, 'r', encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            if (row.get('event_id') or '').strip() == event_id and (row.get('event_name') or '').strip():
                return (row.get(field) or '').strip()
    return ''


# ---------------------------------------------------------------------------
# DD4 / Route 1 - days are compared by POSITION, not by weekday name
# ---------------------------------------------------------------------------
# run.py matches a current day to a reference day by the French weekday string.
# epk_2026 is samedi+dimanche against epk_2023's vendredi+samedi, so Dimanche
# has no reference at all and Samedi compares our OPENING night to their CLOSING
# one - a number that looks plausible and means nothing.
#
# The guard that would have mapped by position (`comparison_mode ==
# 'days_since_launch'`) is dead: comparison_mode is '' on 49 config rows and
# 'j_minus' on 4, never that. It is not dead for want of a launch_date, which
# run.py:3948 does populate.
#
# THE SAME GUARD APPEARS THREE TIMES - run.py:1921 (`day_name_map`, feeding Par
# Jour) and run.py:2881 and :3514 (`prev_presence_key_map`, feeding vélocité,
# projections and day capacity). Seven consumers. A partial fix is worse than
# none: Par Jour by position while Vélocité is still by name means the page
# disagrees with itself and nothing says so.
#
# So this does not patch the three sites. It re-keys the DATA they all read, in
# one place, after run.py has finished computing it with the reference's own
# names. One rename, and the three cannot desynchronise because there is only
# one of them. run.py stays byte-identical.
#
# ALIGNMENT IS FROM THE LAST DAY BACKWARD, not day-1-forward. Forward is wrong
# whenever the editions have different day counts and would REGRESS a comparison
# that is correct today:
#
#     bordeaux_2026  Jeudi 8 500 | Vendredi 18 000 | Samedi 18 000
#     bordeaux_2025                Vendredi 18 000 | Samedi 18 000
#
# Forward gives Jeudi->Vendredi (wrong day AND wrong capacity), Vendredi->Samedi,
# and Samedi->nothing, suppressing the projection on the largest day. Backward
# gives Samedi->Samedi, Vendredi->Vendredi, Jeudi unmatched - which is what name
# matching already produces. Equal counts are unaffected; forward and backward
# are then the same mapping.
#
# Measured across all six compare_to pairs, this changes exactly one page: epk.
# bordeaux and geneve reproduce name matching exactly, which makes them
# REGRESSION CANARIES - if either moves, the mapping ran forward.


WARMUP_TRUE = ('1', 'true', 'yes', 'oui')
# Events whose §5.6 mapping depends on the mark being right. If the column is
# present but these carry no mark, the config regressed and the page would open
# on the wrong default with no symptom.
WARMUP_REQUIRED = {'bordeaux_2026': {'jeudi'}}


def read_warmup_flags(config_path):
    """{event_id: {marked day names}}, read straight from event_config.csv.

    RAISES if the `day_is_warmup` column is absent. That is the whole point.

    csv.DictReader ignores columns it does not know, which is exactly what made
    adding this one provably inert - and is exactly what would make LOSING it
    invisible. Every day would read unmarked, bordeaux would open on
    40 783 / 44 500 instead of 34 804 / 36 000, the échauffement badge would
    never render, and nothing would fail. A default of False is not a safe
    fallback here; it is the wrong answer, silently. Trap #12: when an input is
    absent, propagate the absence.
    """
    with open(config_path, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if 'day_is_warmup' not in (reader.fieldnames or []):
            raise SystemExit(
                f'{config_path}: the `day_is_warmup` column is missing.\n'
                '  A warm-up is a CONFIGURED PER-DAY FACT (DASHBOARD_REDESIGN_SPEC '
                'ss5.3). Without the column every day reads unmarked, bordeaux_2026 '
                'opens on 40 783 / 44 500 instead of 34 804 / 36 000, and no badge '
                'renders - with nothing failing. Restore the column; do not default '
                'it to false.')
        flags = {}
        for row in reader:
            eid = (row.get('event_id') or '').strip()
            day = (row.get('day_name') or '').strip().lower()
            if not eid or not day:
                continue
            if (row.get('day_is_warmup') or '').strip().lower() in WARMUP_TRUE:
                flags.setdefault(eid, set()).add(day)
    for eid, wanted in WARMUP_REQUIRED.items():
        got = flags.get(eid, set())
        if not wanted <= got:
            raise SystemExit(
                f'{config_path}: {eid} should mark {sorted(wanted)} as a warm-up, '
                f'has {sorted(got) or "none"}. The column exists but the mark was '
                'lost - the page would open on the wrong default silently.')
    return flags


def _ordered_days(cfg):
    """Day names, ordered by day_date, asserting day_number agrees.

    day_date is the fact; day_number is an assertion about it. When they
    disagree that is a config error worth failing on, not a preference to
    resolve silently.
    """
    days = (cfg or {}).get('days') or []
    if not days:
        return []
    by_date = sorted(days, key=lambda x: x['day_date'])
    if all(str(x.get('day_number') or '').strip().isdigit() for x in days):
        by_number = sorted(days, key=lambda x: int(x['day_number']))
        if [x['day_name'] for x in by_date] != [x['day_name'] for x in by_number]:
            raise SystemExit(
                'event_config.csv: day_number and day_date disagree on the day '
                'order for this edition. day_date is the fact; fix day_number.')
    return [x['day_name'].strip().lower() for x in by_date]


def _position_map(cur_days, prev_days):
    """{reference day name -> current day name}, aligned from the last day back.

    Only pairs that exist on both sides appear. A current day with no
    counterpart is simply absent from the values, and a reference day with no
    counterpart is absent from the keys - both then read as "no comparison",
    which is what §5.6 asks for.
    """
    out = {}
    for i in range(min(len(cur_days), len(prev_days))):
        out[prev_days[-1 - i]] = cur_days[-1 - i]
    return out


def _assert_warmup_shapes(cur_id, prev_id, warm_flags, cur_days, prev_days, mapping):
    """EE3 + GG1. The two rules below coincide TODAY; nothing guarantees it.

    Last-day-backward and a main-days-only mapping give identical results on all
    six current pairs, because bordeaux's only warm-up is a LEADING day and
    backward alignment consumes from the end - so a leading warm-up falls off as
    unmatched without being special-cased. That coincidence holds while:

      (1) no REFERENCE edition marks a warm-up, and
      (2) every warm-up is a leading day.

    Either failing would silently shift every day after it. Assert, do not
    assume - that turns a wrong page into a failed build.

    The flags arrive as `warm_flags` - read from event_config.csv DIRECTLY, not
    from run.py's day dicts. run.py:242 builds each day from four explicit keys
    (day_number, day_name, day_date, day_capacity), so `day_is_warmup` never
    reaches `event_config['days']` however the CSV is written. An earlier version
    of this function read `x.get('day_is_warmup')` off those dicts and would have
    seen nothing forever, on every event, while its unit tests passed against
    hand-built dicts that did carry the key. Trap #10 one level down.

    GG1 also applies: the warm-up mark and the mapping both decide whether a day
    is excluded, by different means. On bordeaux they must AGREE - jeudi is both
    unmatched and marked. If a marked day is matched, or an unmatched day is
    unmarked, the page has two mechanisms disagreeing about the same day and
    that is a finding, not a detail.
    """
    cur_warm = [n for n in cur_days if n in (warm_flags.get(cur_id) or set())]
    prev_warm = [n for n in prev_days if n in (warm_flags.get(prev_id) or set())]

    if prev_warm:
        raise SystemExit(
            f'EE3: the reference edition marks a warm-up ({prev_warm}). '
            'Backward alignment then maps one of our main days onto it. The '
            'mapping must run over main days only - see DASHBOARD_REDESIGN_SPEC '
            'ss5.6. Refusing to publish a silently shifted comparison.')

    for w in cur_warm:
        if cur_days.index(w) != 0:
            raise SystemExit(
                f'EE3: warm-up {w!r} is not the leading day (position '
                f'{cur_days.index(w) + 1} of {len(cur_days)}). Backward '
                'alignment only absorbs a LEADING warm-up; a mid-run or '
                'trailing one shifts every day after it.')
        if w in mapping.values():
            raise SystemExit(
                f'GG1: {w!r} is marked a warm-up AND matched to a reference '
                f'day. Two mechanisms disagree about whether it is excluded.')

    # GG1, the other direction: an unmatched day that nobody marked is not an
    # error, but it is worth saying out loud - it is excluded by structure
    # rather than by decision.
    unmatched = [n for n in cur_days if n not in mapping.values()]
    for n in unmatched:
        note = 'marked warm-up' if n in cur_warm else 'no counterpart in the reference edition'
        print(f'   · {n}: no reference ({note})')


def main():
    parser = argparse.ArgumentParser(description='Build the HTML dashboard from a merged CSV.')
    parser.add_argument('--event', default='rennes_2026')
    parser.add_argument('--csv', required=True, help='merged CSV produced by fetch_csv.py')
    parser.add_argument('--out', required=True, help='where to write the dashboard HTML')
    parser.add_argument('--config', default=str(BASE_DIR / 'event_config.csv'))
    args = parser.parse_args()

    merged_csv = Path(args.csv)
    if not merged_csv.exists():
        raise SystemExit(f"Merged CSV not found: {merged_csv}")

    with open(merged_csv, 'r', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit(f"Merged CSV is empty: {merged_csv}")
    print(f"Loaded {len(rows)} tickets from {merged_csv}")

    tmp = Path(tempfile.mkdtemp(prefix='festiflow_'))
    raw_dir = tmp / 'raw'
    historical_dir = tmp / 'historical'
    output_dir = tmp / 'output'
    for d in (raw_dir, historical_dir, output_dir):
        d.mkdir(parents=True)

    # Historical comparison reads the pre-merged, PII-free CSV for compare_to.
    # Raw exports are never copied here - same rule main.py follows.
    # Raises if `day_is_warmup` is gone. Loaded before anything is built, so a
    # config regression stops the build rather than producing a wrong page.
    warm_flags = read_warmup_flags(args.config)
    compare_to = read_config_field(args.config, args.event, 'compare_to')
    if compare_to:
        ref_folder = BASE_DIR / 'csv_database' / compare_to
        copied = 0
        if ref_folder.is_dir():
            for ref_file in ref_folder.iterdir():
                if ref_file.name.endswith('_merged.csv'):
                    shutil.copy(ref_file, historical_dir / ref_file.name)
                    copied += 1
        print(f"compare_to={compare_to}: copied {copied} historical merged CSV(s)")

    os.environ['FESTIFLOW_RAW_DIR'] = str(raw_dir)
    os.environ['FESTIFLOW_HISTORICAL_DIR'] = str(historical_dir)
    os.environ['FESTIFLOW_OUTPUT_DIR'] = str(output_dir)

    sys.path.insert(0, str(BASE_DIR))
    import run  # imported after the env vars above: run.py reads them at import

    # Feed the merged rows in place of raw-export parsing. run.py's merge step
    # calls process_shotgun_csv() for the current year and skips DICE when the
    # match has no zip; the rows already carry their own 'platform' column, so
    # the DICE/Shotgun split survives intact.
    run.auto_match_files = lambda raw: {
        'current': {'dice': None, 'shotgun': merged_csv},
        'previous': {'dice': None, 'shotgun': None},
    }
    run.process_shotgun_csv = lambda path: rows
    run.find_merge_into_files = lambda raw_dir_, config_path, event_id: []

    # The Suivi selector needs the anchors the Suivi table was built from:
    # which day the last complete row is, and the two event_date_first values
    # the comparison is aligned on. All three are arguments run.py already
    # passes to _generate_suivi_v3.
    #
    # So OBSERVE rather than change. The wrapper calls through untouched and
    # records what it saw. Nothing is re-derived, and the alternative - parsing
    # the rendered French dates back out of the HTML - is not merely fragile:
    # "Jeu 15 Déc" carries no year, and the daily table spans 232 rows across a
    # year boundary.
    #
    # It now also CLAMPS one argument - see _clamp_cutoff below. That is a
    # deliberate widening of this wrapper's job, and the reason it lives here is
    # that run.py is do-not-modify while the bug is in run.py's own choice of
    # anchor. Everything else still passes through untouched.
    #
    # Bound through the real signature rather than by position, so a new
    # argument in run.py cannot silently shift what gets captured.
    anchors = {}
    _suivi = run._generate_suivi_v3

    def _clamp_cutoff(cutoff, cfg):
        """
        Stop the daily rows at the event, not at the last stray sale.

        run.py anchors the Suivi window on `cutoff_velocity`, which is
        `max(order_date) - 1` over ALL tickets. The visible window is the last
        seven of those rows. For a live event that is exactly right - the newest
        sales are the interesting ones.

        It fails when a sale lands long after the event. `paris_xxl_2026` has 7
        paid tickets on 2026-03-30, sixteen days after a 13-14 March event and
        fifteen days after the previous sale. That single straggler moves the
        cutoff to 29 March, so the seven visible rows are 23-29 March: all zero
        on both sides, with the 112 real selling days collapsed behind "Voir les
        112 jours precedents". The table reads as empty.

        Note what the trigger is NOT. It is not "the event has finished":
        `bordeaux_2026` is finished too and is unaffected, because its last sale
        falls on its own event days. It is not "the range runs past the event
        into dead space" either - the rows stop at a real sale. The dead space
        is the *gap* in between, and one ticket on the far side of it is enough.

        It is also why "anchor on the last day with non-zero sales" does not fix
        it: 30 March IS a day with sales. That rule gives 24-30 March - six
        empty rows and a seven-ticket day - which is still an empty table.

        So clamp to the event instead. `event_date_last + 1` rather than
        `event_date_last`, matching run.py's own convention for the future rows
        ("+1 for post-midnight sales"), which keeps the 41 tickets sold on 15
        March. For a live event the event is in the future, so `min` is a no-op
        and nothing changes - one rule, no live/finished branch.

        Measured across all six events, only `paris_xxl_2026` moves: its window
        becomes 09-15 March with 4,816 sales in it. The other five are byte
        identical.

        The stragglers are not lost. run.py's "Aujourd'hui" row is driven by
        `cutoff_cumulative`, which this does not touch, so the 7 tickets of 30
        March still render - verified on the rebuilt page. What changes is that
        the row now follows 15 March directly instead of following fourteen
        blank ones, so the date jump is visible rather than padded. That is the
        honest shape for a finished event.
        """
        last = (cfg or {}).get('event_date_last') or (cfg or {}).get('event_date_first')
        if not cutoff or not last:
            return cutoff, None
        limit = last + timedelta(days=1)
        return (limit, cutoff) if cutoff > limit else (cutoff, None)

    def _observe_suivi(*a, **kw):
        bound = inspect.signature(_suivi).bind(*a, **kw)
        bound.apply_defaults()
        arg = bound.arguments
        cfg, prev = arg.get('event_config') or {}, arg.get('event_config_prev') or {}

        clamped, was = _clamp_cutoff(arg.get('cutoff_date'), cfg)
        if was is not None:
            print(f"   ↻ Suivi cutoff clamped to the event: {was} -> {clamped} "
                  f"(a sale after the event was dragging the visible window "
                  f"into dead space)")
            bound.arguments['cutoff_date'] = clamped

        anchors.update({
            'cutoff_date': _iso(clamped),
            'cutoff_raw': _iso(was),          # None unless the clamp fired
            'cutoff_cumulative': _iso(arg.get('cutoff_cumulative')),
            'event_first': _iso(cfg.get('event_date_first')),
            'prev_first': _iso(prev.get('event_date_first')),
            'prev_event': prev.get('event_id'),
        })
        # The selector reads `cutoff_date`, so it must see the SAME day the
        # table was built from - pass the bound arguments through, not *a/**kw.
        return _suivi(*bound.args, **bound.kwargs)

    run._generate_suivi_v3 = _observe_suivi

    # ---- DD4 / Route 1: re-key the reference edition's day names ----------
    # run.py calls calculate_metrics(tickets_prev_filtered, event_config_prev)
    # exactly once, after every reference figure has been computed with the
    # reference's OWN day names. That is the seam: let it finish, then rename.
    #
    # Both artefacts have to move together, or the three consumer sites split:
    #   metrics_prev['day_presence']   keyed by day name
    #   every prev ticket's presence_<day>  keys
    # and the tickets are the FULL list, not the filtered subset - vélocité and
    # projections read tickets_prev_full, so re-keying only what
    # calculate_metrics was handed would leave the rest on the old names.
    _calc = run.calculate_metrics
    _load = run.load_ticket_data
    seen_cfgs = []
    prev_ticket_lists = []

    def _observe_load(rows, event_config=None, **kw):
        out = _load(rows, event_config=event_config, **kw)
        seen_cfgs.append(event_config)
        if len(seen_cfgs) > 1:                      # the reference load
            prev_ticket_lists.append(out[0] if isinstance(out, tuple) else out)
        return out

    def _rekey_metrics(tickets, event_config=None, **kw):
        result = _calc(tickets, event_config, **kw)
        # The current-year call comes first and must pass through untouched.
        if not seen_cfgs or event_config is seen_cfgs[0] or len(seen_cfgs) < 2:
            return result
        cur_cfg = seen_cfgs[0]
        cur_days, prev_days = _ordered_days(cur_cfg), _ordered_days(event_config)
        if not cur_days or not prev_days:
            return result
        mapping = _position_map(cur_days, prev_days)
        _assert_warmup_shapes(args.event, compare_to, warm_flags,
                              cur_days, prev_days, mapping)
        if mapping == {n: n for n in mapping}:
            print(f'   ↻ day mapping: identical to name matching '
                  f'({", ".join(f"{k}→{v}" for k, v in mapping.items())})')
        else:
            print('   ↻ day mapping RE-KEYED by position (last day backward): '
                  + ', '.join(f'{k}→{v}' for k, v in mapping.items()))

        # Build fresh dicts rather than renaming in place: on epk the map is
        # {samedi→dimanche, vendredi→samedi}, so a sequential in-place rename
        # would overwrite samedi with vendredi's value before reading it.
        dp = result.get('day_presence')
        if isinstance(dp, dict):
            result['day_presence'] = {mapping[k]: v for k, v in dp.items() if k in mapping}
        for lst in prev_ticket_lists:
            for t in lst:
                moved = {f'presence_{mapping[k]}': t[f'presence_{k}']
                         for k in mapping if f'presence_{k}' in t}
                for k in prev_days:
                    t.pop(f'presence_{k}', None)
                t.update(moved)
        return result

    run.load_ticket_data = _observe_load
    run.calculate_metrics = _rekey_metrics

    sys.argv = ['run.py', '--event', args.event]
    run.main()

    if not anchors.get('cutoff_date'):
        raise SystemExit(
            '_generate_suivi_v3 was never called, or called without a '
            'cutoff_date - the Suivi anchors are the one thing that cannot be '
            'recovered afterwards, so this is a hard failure rather than a '
            'dashboard with a silently inert selector.')

    produced = output_dir / 'dashboard_FINAL.html'
    if not produced.exists():
        raise SystemExit(f"run.py finished but {produced} was not created")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(produced, out_path)

    # Sidecar for postprocess_html.py: the observed anchors plus the comparison
    # candidates. Written beside the HTML and consumed in the same build, so it
    # never needs committing.
    sidecar = out_path.with_suffix(out_path.suffix + '.suivi.json')
    try:
        payload = suivi_candidates.build(args.event, args.config)
    except SystemExit as exc:
        print(f"   ⚠ no comparison candidates: {exc}")
        payload = {'event': args.event, 'candidates': []}
    payload['anchors'] = anchors
    sidecar.write_text(json.dumps(payload, separators=(',', ':'),
                                  ensure_ascii=False), encoding='utf-8')
    print(f"   ↳ suivi sidecar: {len(payload['candidates'])} candidate(s), "
          f"{sidecar.stat().st_size / 1024:.0f} KB")

    print(f"\n✅ Dashboard written to {out_path} ({out_path.stat().st_size:,} bytes)")

    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
