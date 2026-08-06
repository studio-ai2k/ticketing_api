#!/usr/bin/env bash
#
# Rebuild every active dashboard locally - the same pipeline .github/workflows/
# daily-dashboards.yml runs, for when Actions runners are unavailable.
#
#   bash scripts/rebuild_all.sh              # every active event
#   bash scripts/rebuild_all.sh epk_2026     # just these
#
# Needs the four API secrets in the environment. In a Codespace they arrive
# automatically if they are set as Codespaces secrets; check with
# `env | grep -c SHOTGUN_TOKEN_EPISODE` before blaming the script.
#
# Writes the dashboards into the working tree but does NOT commit or push -
# review the diff first, then commit yourself. The commands are printed at the
# end.

set -uo pipefail
cd "$(dirname "$0")/.."

# Match the workflow's environment or the output differs from a CI build:
# footer timestamps are rendered in local time, and the pacing value is what
# keeps the Shotgun fetch under its ~100 req/min limit.
export TZ="${TZ:-Europe/Paris}"
export SHOTGUN_PAGE_PACING_S="${SHOTGUN_PAGE_PACING_S:-0.8}"

PY=$(command -v python3 || command -v python)
if [ -z "$PY" ]; then
  echo "❌ no python3 on PATH" >&2
  exit 1
fi

missing=""
for var in SHOTGUN_TOKEN_EPISODE SHOTGUN_TOKEN_SONORA SHOTGUN_ORGANIZER_ID_SONORA DICE_TOKEN; do
  [ -n "${!var:-}" ] || missing="$missing $var"
done
if [ -n "$missing" ]; then
  echo "❌ missing secret(s) in the environment:$missing" >&2
  echo "   Set them as Codespaces secrets (Settings > Codespaces > Secrets)," >&2
  echo "   then rebuild the Codespace so they are injected." >&2
  exit 1
fi

mkdir -p api_output

# The event list comes from the config, exactly as the workflow's plan job
# derives it - active, named, and with somewhere to write to.
mapfile -t PLAN < <("$PY" - "$@" <<'PY'
import csv, sys
only = set(sys.argv[1:])
seen, out = set(), []
for row in csv.DictReader(open('event_config.csv', encoding='utf-8-sig')):
    eid = (row.get('event_id') or '').strip()
    if not eid or eid in seen:
        continue
    if (row.get('status') or '').strip() != 'active':
        continue
    if not (row.get('event_name') or '').strip():
        continue
    outfile = (row.get('output_filename') or '').strip()
    if not outfile:
        continue
    if only and eid not in only:
        continue
    seen.add(eid)
    out.append(f"{eid}\t{outfile}")
if only:
    missing = only - {line.split('\t')[0] for line in out}
    if missing:
        sys.exit(f"not active events with an output_filename: {sorted(missing)}")
print('\n'.join(out))
PY
) || exit 1

if [ "${#PLAN[@]}" -eq 0 ]; then
  echo "❌ no matching active events in event_config.csv" >&2
  exit 1
fi

echo "Rebuilding ${#PLAN[@]} dashboard(s)  ·  TZ=$TZ  pacing=${SHOTGUN_PAGE_PACING_S}s"
echo

ok=(); failed=()
for line in "${PLAN[@]}"; do
  id="${line%%$'\t'*}"
  outfile="${line#*$'\t'}"
  csv="api_output/${id}_merged.csv"
  html="api_output/${id}.html"

  echo "═══ $id → $outfile"
  # One event failing must not stop the rest, same as fail-fast: false.
  if ! "$PY" fetch_csv.py --event "$id" --out "$csv"; then
    echo "   ❌ fetch failed"; failed+=("$id: fetch"); continue
  fi
  if ! "$PY" scripts/build_dashboard.py --event "$id" --csv "$csv" --out "$html"; then
    echo "   ❌ dashboard build failed"; failed+=("$id: build"); continue
  fi
  if ! "$PY" scripts/postprocess_html.py "$html"; then
    echo "   ❌ post-processing failed"; failed+=("$id: postprocess"); continue
  fi
  cp "$html" "$outfile"
  ok+=("$id")
  echo "   ✅ wrote $outfile"
  echo
done

echo
echo "════════════════════════ SUMMARY ════════════════════════"
"$PY" - "${ok[@]:-}" <<'PY'
import csv, sys
from collections import Counter
rows_fmt = "{:<20} {:>8} {:>8} {:>8} {:>16}"
print(rows_fmt.format('event', 'tickets', 'shotgun', 'dice', 'gross (paid)'))
for eid in [a for a in sys.argv[1:] if a]:
    try:
        rows = list(csv.DictReader(open(f'api_output/{eid}_merged.csv', encoding='utf-8')))
    except OSError:
        continue
    c = Counter(r['platform'] for r in rows)
    gross = sum(float(r['gross_price']) for r in rows if r['is_paid'] == '1')
    print(rows_fmt.format(eid, len(rows), c.get('Shotgun', 0), c.get('DICE', 0), f"{gross:,.2f}"))
PY

if [ "${#failed[@]}" -gt 0 ]; then
  echo
  echo "❌ ${#failed[@]} failed:"
  printf '   - %s\n' "${failed[@]}"
fi

echo
echo "Nothing has been committed. To publish:"
echo "   git add -- '*.html' ':!dashboard_template.html'"
echo "   git commit -m \"Auto-update dashboards · \$(date -u +%Y-%m-%d)\""
echo "   git push"

[ "${#failed[@]}" -eq 0 ]
