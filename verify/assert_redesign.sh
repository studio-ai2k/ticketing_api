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
# DEPLOY 2 — projection restructure.
#
# Every check here keys on MARKUP, never on a bare class name: the v6.6
# stylesheet still ships .chart-tabs / .chart-tab / .proj-grid rules, so
# `grep -c chart-tabs` is 5 on a correctly-restructured file. That is the same
# trap that made align_nav_shell's "sw-wrap" guard match the stylesheet and
# silently skip every dashboard.
echo "── DEPLOY 2"
for f in "${FILES[@]}"; do
  p="$DIR/$f"
  [[ -f "$p" ]] || continue

  for m in 'class="proj-grid"' 'class="chart-tabs"' 'class="chart-tab"' \
           'id="proj-day' 'id="proj-logique"' 'class="chart-subtitle"'; do
    n=$(count "$m" "$p")
    [[ "$n" == "0" ]] && pass "$f: $m gone" || fail "$f: $m survived ($n)"
  done

  # ---- the chart palette (N1) ----
  # Sales line white, projection solid blue, prior-year reference unchanged.
  for m in "rgba(96,165,250,\.8)" "rgba(251,191,36,\.8)"; do
    n=$(count "$m" "$p")
    [[ "$n" == "0" ]] && pass "$f: $m gone" || fail "$f: $m survived ($n)"
  done

  # #fbbf24 must be gone from the projection block AND still present outside
  # it — it also drives the day tag text colours, the hebdo bars and the
  # velocity/revenue charts. A zero count document-wide means the replace was
  # too broad and repainted half the dashboard.
  n=$(count "#fbbf24" "$p")
  [[ "$n" -gt 0 ]] && pass "$f: #fbbf24 still used elsewhere ($n)" \
                   || fail "$f: #fbbf24 gone entirely — recolour was too broad"
  n=$(python3 - "$p" <<'PY'
import re, sys
h = open(sys.argv[1], encoding='utf-8').read()
i = h.index('<div id="sec-projection"')
j = h.index('🎟 Dernier billet vendu', i)
print(h[i:j].count('#fbbf24'))
PY
)
  [[ "$n" == "0" ]] && pass "$f: no amber left in #sec-projection" \
                    || fail "$f: $n #fbbf24 left inside #sec-projection"

  # Day count, derived twice and required to agree.
  days=$(count 'class="q-card"' "$p")
  s1=$(count 'canvas id="chartDay[0-9]*S1"' "$p")
  [[ "$days" == "$s1" && "$days" -gt 0 ]] \
    && pass "$f: $days day card(s), $s1 S1 canvas(es)" \
    || fail "$f: $days .q-card vs $s1 chartDay*S1 canvas"

  # With the tabs gone nothing can trigger a lazy S1 build, so none may remain.
  n=$(count "_projBuilders\['day[0-9]*S1'\]" "$p")
  [[ "$n" == "0" ]] && pass "$f: every S1 built immediately" || fail "$f: $n S1 chart(s) still lazy"

  # S2 stays lazy on purpose — its wrapper is display:none until switchScenario.
  n=$(count "_projBuilders\['day[0-9]*S2'\]" "$p")
  [[ "$n" == "$days" ]] && pass "$f: $n S2 builder(s) intact" || fail "$f: $n S2 builder(s), want $days"

  # One accordion per day card plus one for the methodology card, on top of
  # the four the rest of the page already had.
  want=$(( days + 5 ))
  n=$(count 'class="ac-t"' "$p")
  [[ "$n" == "$want" ]] && pass "$f: $n .ac-t" || fail "$f: $n .ac-t, want $want"
done
# ─────────────────────────────────────────────────────────────

echo
if [[ "$FAIL" == "0" ]]; then echo "ALL ASSERTIONS PASSED"; else echo "ASSERTIONS FAILED"; fi
exit "$FAIL"
