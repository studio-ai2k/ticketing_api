#!/usr/bin/env bash
# Post-generation assertions for redesign v6.6 — DEPLOY 1 (CSS + renames).
# Run against the six generated dashboards. Exits non-zero on any failure.
#
#   ./assert_redesign.sh /path/to/output/dir
#
# Deploy 2 assertions are at the bottom, commented out. Enable them only
# after the markup/JS pass has landed.

set -uo pipefail
# WHERE PASS 0 PUBLISHES, resolved at call time - `v2/` before cutover, the repo
# root after. The same rule the sixteen python page checks already follow
# (CUTOVER §6.3), and for the same reason: a gate repointed at root BEFORE the
# pages move is false, and one left at `v2/` after they move reads a directory
# that no longer exists, so no flag-day edit is safe on any day.
#
# It used to default to `.`, which meant PRODUCTION. That was right while this
# gate asserted production's markup and is wrong now that it asserts pass 0's -
# see verify/check_page_anchor.py. An explicit directory is still honoured.
DIR="${1:-$(python3 -c 'import sys; sys.path.insert(0, "'"$(dirname "$0")"'/../scripts"); import pages; print(pages.pass0_dir())')}"
if [[ -z "$DIR" ]]; then
  echo "  FAIL  cannot resolve where pass 0 publishes"; exit 1
fi
echo "gate: asserting pass-0 pages in $DIR"
# CUTOVER 6.3: the page list comes from event_config's active rows, not from a
# hand-written array here. `scripts/pages.py` is the one declaration; it exits
# non-zero rather than printing a short list, so a config this cannot read stops
# the gate instead of quietly shrinking it.
if ! mapfile -t FILES < <(python3 "$(dirname "$0")/../scripts/pages.py"); then
  echo "  FAIL  cannot enumerate pages from event_config.csv"; exit 1
fi
if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "  FAIL  event_config.csv named no pages - the gate would pass on nothing"
  exit 1
fi
FAIL=0

# The stylesheet postprocess_html.py vendors in. Assertions that would
# otherwise hardcode a property of the design derive it from here instead.
CSS="$(dirname "$0")/../style/dashboard_v6_8.css"

fail() { echo "  FAIL  $1"; FAIL=1; }
pass() { echo "  ok    $1"; }

# count occurrences without tripping `set -e` on a zero match
count() { grep -o -- "$1" "$2" 2>/dev/null | wc -l | tr -d ' '; }

# Pages that failed the anchor. Every later loop skips them: an absence
# assertion on a page that is not a whole dashboard is not a pass, and printing
# it as one beside a real failure is how 396 green lines came to describe six
# empty files.
ANCHOR_FAILED=""

for f in "${FILES[@]}"; do
  p="$DIR/$f"
  echo "── $f"
  if [[ ! -f "$p" ]]; then fail "missing file"; ANCHOR_FAILED="$ANCHOR_FAILED $f"; continue; fi

  # ---- 0. THE ANCHOR — before any assertion that could pass vacuously ----
  # 174 of this gate's 396 assertions passed against six ZERO-BYTE files.
  # Absence assertions hold on a page containing nothing, and so does every
  # count whose baseline is derived from the page itself. This says the page is
  # a whole dashboard and is its own event, so the rest has an artefact to be
  # true of. See verify/check_page_anchor.py.
  anchor_why="$(python3 "$(dirname "$0")/check_page_anchor.py" "$p" 2>&1 >/dev/null)"
  anchor_n="$(python3 "$(dirname "$0")/check_page_anchor.py" "$p" 2>/dev/null)"
  if [[ "$anchor_n" != "0" ]]; then
    fail "NOT A COMPLETE DASHBOARD — every assertion below would be vacuous:"
    while IFS= read -r line; do [[ -n "$line" ]] && echo "          $line"; done <<< "$anchor_why"
    ANCHOR_FAILED="$ANCHOR_FAILED $f"
    continue
  fi
  pass "anchored: whole, stamped, and its own event"

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

  # ---- 5. responsive section present, intact ----
  # Derived from the vendored stylesheet, not hardcoded. This used to assert
  # exactly one block per breakpoint, which was true of v6.6 and became wrong
  # the moment v6.7 added mobile rules for .det-link, .vel-head and .pg-footer.
  # Comparing against the source file still catches both real failures - the
  # swap not happening, and a block lost in it - and survives design changes.
  for bp in "720px" "600px" "480px" "420px"; do
    want=$(count "@media (max-width:$bp)" "$CSS")
    n=$(count "@media (max-width:$bp)" "$p")
    [[ "$n" == "$want" ]] && pass "@media $bp x$n (matches stylesheet)" \
                          || fail "@media $bp appears $n times, stylesheet has $want"
  done
  n=$(count "prefers-reduced-motion" "$p")
  [[ "$n" -gt 0 ]] && pass "reduced-motion block" || fail "reduced-motion block missing"

  # ---- 6. mobile nav containment ----
  # D24: clip, not hidden. `hidden` makes body a scroll container and the
  # sticky nav positions against it, so the nav never stuck on either head.
  # This assertion outlived the ruling and kept demanding the broken value.
  n=$(count "html,body{overflow-x:clip" "$p")
  [[ "$n" -gt 0 ]] && pass "overflow-x contained (clip)" || fail "overflow-x:clip missing"

  # ---- 7. footer version tracks the zip version ----
  # Deploy 3 §7 split this: "Festiflow Dashboard v6.7" is no longer one string,
  # the version sits in its own .pgf-ver span. Asserting the old literal would
  # now read 0 on a correct file.
  n=$(count "Festiflow Dashboard<span class=\"pgf-ver\">v6\.8</span>" "$p")
  [[ "$n" == "2" ]] && pass "footer v6.8 (x2)" || fail "footer version wrong or wrong count ($n, want 2)"

  # ---- 11. login overlay (T1, T2) ----
  n=$(count "class=\"db-modal-sub\">Festiflow · Billetterie<" "$p")
  [[ "$n" == "1" ]] && pass "login subtitle" || fail "$n login subtitle(s), want 1"
  n=$(count "Tableau de bord interne" "$p")
  [[ "$n" == "0" ]] && pass "old subtitle gone" || fail "old subtitle survived ($n)"

  # The per-event login background lives inside the template's <style>, which
  # apply_redesign replaces wholesale - so it has to be carried across the
  # swap. Without that, every event silently inherits whatever the mock was
  # baked with, which is how paris_xxl lost paris_login.jpg.
  want=$(python3 verify/check_login_bg.py "$p" expected)
  n=$(python3 verify/check_login_bg.py "$p" actual)
  [[ "$n" == "$want" ]] && pass "login background $n (from config)" \
                        || fail "login background is $n, config says $want"

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
  # Skipped rather than asserted: see the anchor at the top. A page that is
  # not a whole dashboard makes every absence assertion below meaningless.
  [[ " $ANCHOR_FAILED " == *" $f "* ]] && continue

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
  # Bounded by div depth, not by the footer. This originally sliced up to the
  # "🎟 Dernier billet vendu" string, which Deploy 3 §7 deleted - so the check
  # started erroring on a correct file. An assertion consuming something a
  # later pass emits is the same trap the pass table exists for; it applies to
  # the verify scripts too.
  n=$(python3 verify/check_section_amber.py "$p")
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

# ─────────────────────────────────────────────────────────────
# DEPLOY 3 — suivi scroll/separators, vélocité header, platform cards.
#
# Every markup count keys on class="..." / id="...". The v6.7 stylesheet ships
# .dtl-cutoff, .vel-head, .det-link and .inset-divider rules, so a bare grep
# counts the CSS as well — the mistake that has now produced three wrong
# baselines (.ac-t 8+N, .inset-divider 3, and the sw-wrap guard).
echo "── DEPLOY 3"
for f in "${FILES[@]}"; do
  p="$DIR/$f"
  [[ -f "$p" ]] || continue
  # Skipped rather than asserted: see the anchor at the top. A page that is
  # not a whole dashboard makes every absence assertion below meaningless.
  [[ " $ANCHOR_FAILED " == *" $f "* ]] && continue

  # --- suivi ---
  for sep in sep-prev-days sep-prev-weeks; do
    n=$(count "id=\"$sep\"" "$p")
    [[ "$n" == "1" ]] && pass "$f: #$sep" || fail "$f: $n #$sep in markup, want 1"
  done
  n=$(count "h.scrollTop=h.scrollHeight" "$p")
  [[ "$n" == "2" ]] && pass "$f: 2 scroll-to-bottom calls" || fail "$f: $n scroll calls, want 2"

  # .dtl-cutoff is derived, never fixed: parisxxl generates none, bordeaux one,
  # the other four two — plus the two this pass adds.
  n=$(count "class=\"dtl-cutoff\"" "$p")
  [[ "$n" -ge 2 ]] && pass "$f: $n .dtl-cutoff in markup" \
                   || fail "$f: $n .dtl-cutoff in markup, want at least the 2 new ones"

  # --- vélocité ---
  n=$(count "grid-template-columns:1fr 50px 44px 44px" "$p")
  [[ "$n" == "0" ]] && pass "$f: old vélocité grid gone (whole file)" || fail "$f: old grid survived ($n)"
  for cls in vel-head vel-grid; do
    n=$(count "class=\"$cls\"" "$p")
    [[ "$n" == "1" ]] && pass "$f: .$cls" || fail "$f: $n .$cls in markup, want 1"
  done

  # --- comparison inset ---
  n=$(count "class=\"inset-divider\"" "$p")
  [[ "$n" == "1" ]] && pass "$f: 1 .inset-divider in markup" \
                    || fail "$f: $n .inset-divider in markup, want 1 (whole file reads 2: +1 CSS rule)"

  # --- platform cards ---
  links=$(count "class=\"det-link\"" "$p")
  [[ "$links" -ge 2 ]] && pass "$f: $links platform card(s)" || fail "$f: $links platform cards"
  n=$(count "class=\"det-link-txt\"" "$p")
  [[ "$n" == "$links" ]] && pass "$f: $n .det-link-txt" || fail "$f: $n .det-link-txt, want $links"
  n=$(( $(count "<img src=\"logo-shotgun.png\"" "$p") + $(count "<img src=\"logo-dice.png\"" "$p") ))
  [[ "$n" == "$links" ]] && pass "$f: $n platform logo(s)" || fail "$f: $n logos, want $links"

  n=$(count "dice.fm/partner/events/" "$p")
  [[ "$n" == "0" ]] && pass "$f: old DICE backend URL gone" || fail "$f: old DICE backend URL survived ($n)"
  n=$(count "smartboard.shotgun.live/events/" "$p")
  [[ "$n" == "1" ]] && pass "$f: Smartboard URL" || fail "$f: $n Smartboard URLs, want 1"

  # Derived: only an event with a DICE backend card gets a Mio URL.
  want_mio=$(count "DICE · Mio" "$p")
  n=$(count "mio.dice.fm/events/" "$p")
  [[ "$n" == "$want_mio" ]] && pass "$f: $n Mio URL(s)" || fail "$f: $n Mio URLs, want $want_mio"

  # Both Shotgun cards shared an href before this pass; if they still do, the
  # Smartboard rewrite silently did nothing.
  n=$(python3 verify/check_platform_cards.py "$p" dupes)
  [[ "$n" == "0" ]] && pass "$f: every platform card has a distinct href" \
                    || fail "$f: $n duplicate platform href(s)"

  n=$(python3 verify/check_platform_cards.py "$p" order)
  [[ "$n" == "0" ]] && pass "$f: platform cards in canonical order" \
                    || fail "$f: platform cards out of canonical order"

  # --- footer (§7) ---
  n=$(count "class=\"pg-footer" "$p")
  [[ "$n" == "2" ]] && pass "$f: 2 .pg-footer" || fail "$f: $n .pg-footer in markup, want 2"
  n=$(count "class=\"pg-footer det-footer\"" "$p")
  [[ "$n" == "1" ]] && pass "$f: .det-footer variant kept" || fail "$f: $n .pg-footer.det-footer, want 1"
  n=$(count "class=\"pgf-item" "$p")
  [[ "$n" == "6" ]] && pass "$f: 6 footer items" || fail "$f: $n .pgf-item, want 6 (3 x 2 footers)"

  # Whole file: the stylesheet cannot contain an emoji. 🔒 belongs here too —
  # stamp_footer.py's frozen label used it, and it is the same raster glyph
  # problem §7 exists to remove.
  for g in "🎟" "🔄" "🔒"; do
    n=$(count "$g" "$p")
    [[ "$n" == "0" ]] && pass "$f: no $g" || fail "$f: raster glyph $g survived ($n)"
  done

  # The reason §7 shipped alone: stamp_footer.py patches this markup in
  # published HTML hours later, and a mismatch fails silently on a quiet run.
  n=$(python3 verify/check_stampable.py "$p")
  [[ "$n" == "0" ]] && pass "$f: footer is stampable and stamps surgically" \
                    || fail "$f: footer would break stamp_footer.py (code $n)"
done
# ─────────────────────────────────────────────────────────────

echo
if [[ "$FAIL" == "0" ]]; then echo "ALL ASSERTIONS PASSED"; else echo "ASSERTIONS FAILED"; fi
exit "$FAIL"
