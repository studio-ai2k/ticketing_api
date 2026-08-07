#!/usr/bin/env bash
# Post-generation assertions for redesign v6.6 — DEPLOY 1 (CSS + renames).
# Run against the six generated dashboards. Exits non-zero on any failure.
#
#   ./assert_redesign.sh /path/to/output/dir
#
# Deploy 2 assertions are at the bottom, commented out. Enable them only
# after the markup/JS pass has landed.

set -uo pipefail
DIR="${1:-.}"
FILES=(parisxxl.html bordeaux.html epk.html bordeaux_oct.html geneve.html rennes.html)
FAIL=0

fail() { echo "  FAIL  $1"; FAIL=1; }
pass() { echo "  ok    $1"; }

# count occurrences without tripping `set -e` on a zero match
count() { grep -o -- "$1" "$2" 2>/dev/null | wc -l | tr -d ' '; }

for f in "${FILES[@]}"; do
  p="$DIR/$f"
  echo "── $f"
  if [[ ! -f "$p" ]]; then fail "missing file"; continue; fi

  # ---- 1. old class names must be gone (the rename, section 3) ----
  for old in details-toggle details-panel yoy-badge session-sw; do
    n=$(count "$old" "$p")
    [[ "$n" == "0" ]] && pass "no .$old" || fail ".$old still present ($n)"
  done

  # ---- 2. new class names must be present ----
  for new in "ac-t" "ac-body" "pill"; do
    n=$(count "class=\"[^\"]*$new" "$p")
    [[ "$n" -gt 0 ]] && pass ".$new present ($n)" || fail ".$new missing"
  done

  # ---- 3. stylesheet actually swapped ----
  for marker in "fs-nano" "fs-tiny" "fs-mini" "DM Sans" "Space Grotesk"; do
    n=$(count "$marker" "$p")
    [[ "$n" -gt 0 ]] && pass "$marker present" || fail "$marker missing — style block not swapped?"
  done

  # ---- 4. dead / superseded values must be gone ----
  n=$(count "Outfit" "$p");            [[ "$n" == "0" ]] && pass "no Outfit font"      || fail "Outfit still loaded ($n)"
  n=$(count "font-size:[0-9]*px" "$p"); [[ "$n" == "0" ]] && pass "no literal px sizes" || fail "literal font-size:Npx present ($n)"

  # ---- 5. responsive section present, one block per breakpoint ----
  for bp in "720px" "600px" "480px" "420px"; do
    n=$(count "@media (max-width:$bp)" "$p")
    [[ "$n" == "1" ]] && pass "one @media $bp block" || fail "@media $bp appears $n times (want 1)"
  done
  n=$(count "prefers-reduced-motion" "$p")
  [[ "$n" -gt 0 ]] && pass "reduced-motion block" || fail "reduced-motion block missing"

  # ---- 6. mobile nav containment ----
  # corrected stylesheet merges the rule: html,body{overflow-x:hidden;...}
  n=$(count "html,body{overflow-x:hidden" "$p")
  [[ "$n" -gt 0 ]] && pass "overflow-x contained" || fail "overflow-x:hidden missing"

  # ---- 7. footer version tracks the zip version ----
  n=$(count "Festiflow Dashboard v6\.6" "$p")
  [[ "$n" == "2" ]] && pass "footer v6.6 (x2)" || fail "footer version wrong or wrong count ($n, want 2)"

  # ---- 8. nav shell still intact (regression guard) ----
  for m in "sw-wrap" "nav-user" "Partenaires"; do
    n=$(count "$m" "$p")
    [[ "$n" -gt 0 ]] && pass "$m intact" || fail "$m lost — nav shell regressed"
  done

  # ---- 9. logo repoint (E6) still holds ----
  n=$(count "madameloyal.github.io" "$p")
  [[ "$n" == "0" ]] && pass "no external logo hotlink" || fail "hotlink returned ($n)"

  # ---- 10. div balance ----
  o=$(count "<div" "$p"); c=$(count "</div>" "$p")
  [[ "$o" == "$c" ]] && pass "div balance ($o)" || fail "div imbalance: $o open, $c close"
done

# ─────────────────────────────────────────────────────────────
# DEPLOY 2 ONLY — enable after the markup/JS pass lands.
# for f in "${FILES[@]}"; do
#   p="$DIR/$f"
#   count "rgba(96,165,250,\.8)" "$p" | grep -qx 0 || fail "$f: projection line not solid"
#   count "chart-tabs" "$p"           | grep -qx 0 || fail "$f: chart tabs not removed"
# done
# ─────────────────────────────────────────────────────────────

echo
if [[ "$FAIL" == "0" ]]; then echo "ALL ASSERTIONS PASSED"; else echo "ASSERTIONS FAILED"; fi
exit "$FAIL"
