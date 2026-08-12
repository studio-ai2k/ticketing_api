#!/usr/bin/env bash
# The pass-0 markup gate. Runs on bash and python alone, so it can run on every
# build; anything needing a browser lives in verify/CHECKLIST.md.
#
#   ./assert_redesign.sh [dir]     # default: wherever pass 0 publishes
#
# WHAT THIS GATE IS, AFTER P4
# ---------------------------
# It used to assert PRODUCTION's markup, ~400 lines of it, and at cutover it
# would have been repointed at pass-0 pages and made green. Three measurements
# said that was the wrong move:
#
#   1. 174 of its 396 assertions passed against six ZERO-BYTE files. Absence
#      assertions hold on a page containing nothing, and so does any count whose
#      baseline is derived from the page itself.
#   2. Production ships its body as static markup - 2716 <div>s on rennes.
#      Pass 0 builds the body at runtime from `const D` and ships 67. Most of
#      what this gate asserted has no static artefact on the new pipeline.
#   3. `check_mock_deviations` reads a built page at exactly one line, and reads
#      the <style> element - byte-for-byte against the redesign sheet, per page,
#      through the transforms build_v2 declares. Everything this gate said about
#      CSS was already said there, and said harder.
#
# So the gate did not shrink or grow. It split, and this is what was left:
#
#   DROP  8 CSS assertions      subsumed by check_pages, and it is stricter
#   DEAD 21 absence assertions  zero on BOTH pipelines - not coverage
#   TRAP  2 .ac-t assertions    passed by matching JS template source
#   MOVE 14 markup assertions   no static artefact exists; pinned elsewhere
#   KEEP 12 assertions          genuinely static markup on both pipelines
#
# Full evidence, per assertion: verify/P4_KEEP_DROP.md.
#
# THE TWO RULES THIS FILE NOW FOLLOWS
# -----------------------------------
# 1. Nothing is asserted about a page until check_page_anchor says it is a whole
#    dashboard and its own event. An absence assertion is worth exactly the
#    artefact it ran against.
# 2. Markup counts run against the STATIC REGION, not the whole file. Grepping
#    the file counts the stylesheet and the JS templates too - the trap that has
#    now caught this repo three times. See verify/static_region.py.

set -uo pipefail
HERE="$(dirname "$0")"

# WHERE PASS 0 PUBLISHES, resolved at call time - `v2/` before cutover, the repo
# root after. The same rule the sixteen python page checks follow (CUTOVER
# §6.3): a gate repointed at root BEFORE the pages move is false, and one left
# at `v2/` after they move reads a directory that no longer exists, so no
# flag-day edit is safe on any day. It used to default to `.`, which meant
# PRODUCTION - right while this gate asserted production's markup, wrong now.
DIR="${1:-$(python3 -c 'import sys; sys.path.insert(0, "'"$HERE"'/../scripts"); import pages; print(pages.pass0_dir())')}"
if [[ -z "$DIR" ]]; then
  echo "  FAIL  cannot resolve where pass 0 publishes"; exit 1
fi

# CUTOVER 6.3: the page list comes from event_config's active rows, not from a
# hand-written array here. `scripts/pages.py` is the one declaration; it exits
# non-zero rather than printing a short list, so a config this cannot read stops
# the gate instead of quietly shrinking it.
if ! mapfile -t FILES < <(python3 "$HERE/../scripts/pages.py"); then
  echo "  FAIL  cannot enumerate pages from event_config.csv"; exit 1
fi
if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "  FAIL  event_config.csv named no pages - the gate would pass on nothing"
  exit 1
fi

# The footer version, DERIVED from the source that sets it rather than written
# here as a literal. `v6.8` was hardcoded at this spot and was the THIRD site of
# the §3(b2) bump - the two in cutover.plan_writes are postprocess_html.py and
# check_footer_tz.py, and this one was in neither, so the bump would have turned
# the gate red on a correct page.
WANT_VER="$(python3 -c "
import re, pathlib
s = pathlib.Path('$HERE/../scripts/postprocess_html.py').read_text(encoding='utf-8')
m = re.search(r\"DASHBOARD_VERSION = '([0-9.]+)'\", s)
print('v' + m.group(1) if m else '')")"
if [[ -z "$WANT_VER" ]]; then
  echo "  FAIL  cannot read DASHBOARD_VERSION from scripts/postprocess_html.py"
  exit 1
fi

echo "gate: pass-0 markup in $DIR, footer version $WANT_VER"
FAIL=0
fail() { echo "  FAIL  $1"; FAIL=1; }
pass() { echo "  ok    $1"; }
# count occurrences without tripping on a zero match
count() { grep -o -- "$1" "$2" 2>/dev/null | wc -l | tr -d ' '; }

STATIC="$(mktemp)"
trap 'rm -f "$STATIC"' EXIT

for f in "${FILES[@]}"; do
  p="$DIR/$f"
  echo "── $f"
  if [[ ! -f "$p" ]]; then fail "missing file"; continue; fi

  # ---- 0. THE ANCHOR — before anything that could pass vacuously ----
  anchor_why="$(python3 "$HERE/check_page_anchor.py" "$p" 2>&1 >/dev/null)"
  anchor_n="$(python3 "$HERE/check_page_anchor.py" "$p" 2>/dev/null)"
  if [[ "$anchor_n" != "0" ]]; then
    fail "NOT A COMPLETE DASHBOARD — every assertion below would be vacuous:"
    while IFS= read -r line; do [[ -n "$line" ]] && echo "          $line"; done <<< "$anchor_why"
    continue
  fi
  pass "anchored: whole, stamped, and its own event"

  # The markup, without the stylesheet or the JS templates. Every count below
  # runs against THIS, not against "$p".
  if ! python3 "$HERE/static_region.py" "$p" > "$STATIC"; then
    fail "cannot extract the static region"; continue
  fi

  # ---- 1. the nav shell, which pass 0 transplants from production ----
  # Scoped to the static region: `sw-wrap` reads 16 on the whole file (4 in the
  # stylesheet, 10 in JS templates, 2 in markup) and the bare-name grep was the
  # original align_nav_shell trap.
  for m in "sw-wrap" "nav-user" "Partenaires"; do
    n=$(count "$m" "$STATIC")
    [[ "$n" -gt 0 ]] && pass "$m intact ($n in markup)" || fail "$m lost — nav shell regressed"
  done

  # ---- 2. the login overlay ----
  n=$(count "class=\"db-modal-sub\">Festiflow · Billetterie<" "$STATIC")
  [[ "$n" == "1" ]] && pass "login subtitle" || fail "$n login subtitle(s), want 1"
  n=$(count "class=\"[^\"]*pill" "$STATIC")
  [[ "$n" -gt 0 ]] && pass ".pill present ($n)" || fail ".pill missing from markup"

  # ---- 3. the footer, which stamp_footer.py patches hours later ----
  n=$(count "class=\"pg-footer" "$STATIC")
  [[ "$n" == "2" ]] && pass "2 .pg-footer" || fail "$n .pg-footer in markup, want 2"
  n=$(count "class=\"pg-footer det-footer\"" "$STATIC")
  [[ "$n" == "1" ]] && pass ".det-footer variant kept" || fail "$n .pg-footer.det-footer, want 1"
  n=$(count "class=\"pgf-item" "$STATIC")
  [[ "$n" == "6" ]] && pass "6 footer items" || fail "$n .pgf-item, want 6 (3 x 2 footers)"
  n=$(count "Festiflow Dashboard<span class=\"pgf-ver\">${WANT_VER//./\\.}</span>" "$STATIC")
  [[ "$n" == "2" ]] && pass "footer $WANT_VER (x2, derived from DASHBOARD_VERSION)" \
                    || fail "footer version is not $WANT_VER twice ($n)"

  # The reason §7 shipped alone: stamp_footer.py patches this markup in
  # published HTML hours later, and a mismatch fails silently on a quiet run.
  n=$(python3 "$HERE/check_stampable.py" "$p")
  [[ "$n" == "0" ]] && pass "footer is stampable and stamps surgically" \
                    || fail "footer would break stamp_footer.py (code $n)"

  # ---- 4. platform backend links ----
  # Derived, not fixed: only an event with a DICE backend card gets a Mio URL.
  n=$(count "smartboard.shotgun.live/events/" "$STATIC")
  [[ "$n" == "1" ]] && pass "Smartboard URL" || fail "$n Smartboard URLs, want 1"
  want_mio=$(count "DICE · Mio" "$STATIC")
  n=$(count "mio.dice.fm/events/" "$STATIC")
  [[ "$n" == "$want_mio" ]] && pass "$n Mio URL(s) (matches $want_mio DICE · Mio card(s))" \
                            || fail "$n Mio URLs, want $want_mio"

  # ---- 5. the font the redesign actually uses ----
  # DM Sans, not Space Grotesk. The old gate demanded Space Grotesk and it is
  # absent from the redesign sheet entirely - the assertion outlived the design.
  n=$(count "DM Sans" "$STATIC")
  [[ "$n" -gt 0 ]] && pass "DM Sans in markup ($n)" || fail "DM Sans missing from markup"

  # ---- 6. div balance, in the region where it means something ----
  o=$(count "<div" "$STATIC"); c=$(count "</div>" "$STATIC")
  [[ "$o" == "$c" ]] && pass "div balance ($o)" || fail "div imbalance: $o open, $c close"
done

echo
if [[ "$FAIL" == "0" ]]; then echo "ALL ASSERTIONS PASSED"; else echo "ASSERTIONS FAILED"; fi
exit "$FAIL"
