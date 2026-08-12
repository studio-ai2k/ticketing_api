#!/usr/bin/env python3
"""
Every difference between the working mock and the LOCKED one must be authorised.

    python verify/check_mock_deviations.py

WHY THIS EXISTS
---------------
`redesign/mock/dashboard_v3.39.html` is no longer v3.39. Same filename,
different file — six authorised changes were applied to it, and "the mock is
absolute" stopped naming a specific artefact the moment the name drifted. That
is how a correct finding got overturned: the badge was searched for in the
WORKING mock, found, and concluded to have always been there. It had not.

So the locked upload is pinned byte-identical at `redesign/locked/`, never
edited, and this asserts that the working copy differs from it in exactly the
authorised ways — no more and **no fewer**.

Both directions matter:

  - an UNAUTHORISED hunk is an invention, and goes back to Leo
  - a MISSING authorised deviation means an approved change was reverted, which
    is just as wrong and much quieter

The stylesheet has exactly ONE class of authorised deviation: `.db-*` rules
carried VERBATIM from `style/dashboard_v6_8.css` to make the auth overlay work.
Those are not mock deviations — the locked mock has no auth overlay at all, so
they are production chrome it never contained.

Anything else fails: a removed line, a modified one, or a `.db-*` rule whose
text does not appear in production's sheet. The property being protected was
never byte identity; it is **the redesign invents no CSS**, and that survives
intact.

A ruling may authorise a specific edit to a specific line — D9 is the first.
Those are listed in AUTHORISED_CSS and checked in both directions, exactly like
the mock's hunks: an unlisted edit is an invention, and a listed one that has
gone missing is an approved change someone reverted.

THE FILE IS NOT THE PAGE
------------------------
Everything above validates `redesign/style/dashboard_redesign.css`. The pages
under `v2/` do not link that file — pass 0 inlines it, and then rewrites asset
paths in it, so the shipped `<style>` is a TRANSFORM of the file and nothing
here could see a change made between the two.

Given how much of this round was checks that kept passing while their target
moved, that gap gets closed rather than noted. `check_pages()` asserts, for
every shipped page, that its inlined `<style>` equals the file put through
**exactly** `build_v2.PAGE_PATHS` — imported, never restated, so the day those
substitutions become location-aware this check follows them instead of
disagreeing with them. Any other difference fails.

That last point is the concrete instance of the cutover problem: `../upload.JPG`
is right one directory deep and wrong at the root.
"""

import difflib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from pages import v2_pages   # noqa: E402 - CUTOVER 6.3, one page list
LOCK_HTML = ROOT / 'redesign' / 'locked' / 'dashboard_v3.39.LOCKED.html'
WORK_HTML = ROOT / 'redesign' / 'mock' / 'dashboard_v3.39.html'
LOCK_CSS = ROOT / 'redesign' / 'locked' / 'dashboard_redesign.LOCKED.css'
WORK_CSS = ROOT / 'redesign' / 'style' / 'dashboard_redesign.css'
V2 = ROOT / 'v2'

STYLE_RE = re.compile(r'<style>(.*?)</style>', re.DOTALL)

# (id, ruling, the LOCKED line, the line that must replace it)
# Whole lines, matched exactly. A ruling that edits CSS lands here; anything
# else that edits CSS is an invention.
AUTHORISED_CSS = [
    ('D9', "--ff-mono becomes JetBrains Mono. DM Mono was declared but never "
           "loaded by any page, so .ac-b code and .dsrc-k fell back to SF Mono "
           "on Apple and to generic monospace elsewhere - the only elements on "
           "the dashboard that rendered differently per device. JetBrains Mono "
           "already downloads at 400/500/600, so this costs no request",
     "  --ff-mono: 'DM Mono', 'SF Mono', monospace;",
     "  --ff-mono: 'JetBrains Mono', monospace;"),
    ('C1a', "C1/C2 - .dt horizontal padding 12px -> 10px. The bar now indexes "
            "EVERY section by rule, which took billetterie from four tabs to "
            "six, and six needed 401px against the 393 of the phone this "
            "project judges mobile at - eight over, with Projections under the "
            "fade. Measured before choosing: no label shortening reaches 393 "
            "(Projections->Projection leaves 3 over, +Velocite->Rythme leaves "
            "2) and the type step was already at its floor, 10px. Padding was "
            "the only lever. 10px gives 377, sixteen of headroom, and leaves "
            "Détails room for the next section instead of 2px. NOTE: the recorded replacement is 8px, not the 10px this ruling chose - TS5 edited the same line again. A locked->working pair cannot hold two edits to one line, so the LATER value is recorded and the earlier decision keeps its text. Fourth structural weakness the ledger has shown, and the same shape as the hunk matcher whose result depended on which side a line landed",
     ".dt { padding: 8px 12px; font-size:var(--fs-tiny); font-weight: 500; color: var(--text-dim); white-space: nowrap; border: none; border-bottom: 2px solid transparent; background: none; font-family: inherit; cursor: pointer; transition: color .15s; }",
     ".dt { padding: 8px 8px; font-size:var(--fs-tiny); font-weight: 500; color: var(--text-dim); white-space: nowrap; border: none; border-bottom: 2px solid transparent; background: none; font-family: inherit; cursor: pointer; transition: color .15s; }"),
    ('C3a', "C3 - THE CLAMP, and it is the entry that generalises. The tooltip "
            "bubble was `left:50%; transform:translateX(-50%)` - centred on the "
            "15px glyph - so the widest it could ever be was 2*min(glyph_x, "
            "vw-glyph_x), set by whichever glyph sat nearest an edge. Measured "
            "at 393px that bound is 213px on sec-overview. THE 210 IN THE SHEET "
            "WAS NOT A LEGACY VALUE FROM NARROWER PHONES: it is one pixel under "
            "the geometric limit and whoever set it measured. Anchoring to the "
            "header row instead removes the bound entirely - and the bubble has "
            "no caret, so its horizontal position never carried meaning. "
            "Measured after: 0/10 overflowing at 393 AND at 360, where the old "
            "rule overflowed once on sec-presence before C3 existed",
     ".sec-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;",
     ".sec-head{position:relative;display:flex;align-items:baseline;justify-content:space-between;gap:12px;"),
    ('C3b', "C3 - the clamp's other half: .info stops being the containing "
            "block so the bubble anchors to the header row. Two lines because "
            "they are one decision needing an ancestor and a descendant to "
            "agree; reverting either alone puts the overflow back",
     "  cursor:help;position:relative;vertical-align:2px;margin-left:7px;font-style:italic;",
     "  cursor:help;position:static;vertical-align:2px;margin-left:7px;font-style:italic;"),
    ('C3c', "C3 - the clamp lands on this line as left:0 (was left:50% + "
            "translateX(-50%)), and THE WIDTH RULING lands on the same line as "
            "min(330px,100%) (was 250px). Two decisions, one line, because the "
            "sheet declares position and width together. The 100% is the header "
            "row, so the bubble can never be wider than its card and can never "
            "leave the viewport - it self-narrows to 304px at 360. Heights at "
            "393: sec-suivi 257 -> 164, sec-presence 210 -> 133, no copy cut",
     ".info span{display:none;position:absolute;bottom:calc(100% + 8px);left:50%;transform:translateX(-50%);",
     ".info span{display:none;position:absolute;top:calc(100% + 8px);left:0;"),
    ('C3i', "C3 - THE BUBBLE OPENS DOWNWARD, and this is a consequence of D6. It "
            "opened UPWARD at z-index 90; D6 made the nav sticky at z-index 100; "
            "so a bubble opening upward from a header near the top of the "
            "viewport renders BEHIND THE NAV. Before D6 the nav scrolled away and "
            "this could not happen. Uniform rather than per-card: which card sits "
            "under the nav depends on scroll position, so a conditional rule "
            "would be right at one offset and wrong at another. Every card has "
            "content below its header, so downward has room. Measured after: no "
            "tooltip reaches the document bottom at either width, and the bubble "
            "covers 7-28% of its own card's content while open (worst is "
            "sec-plateformes, a 183px card). NOTE: this rides on C3c's line "
            "because the sheet declares position in one declaration - it is a "
            "separate DECISION with no separate line to own",
     "__C3i_rides_on_C3c__", "__C3i_rides_on_C3c__"),
    ('C3h', "C3 - THE BUBBLE STOPS INHERITING THE TITLE'S CASE. .sec-title sets "
            "text-transform:uppercase and letter-spacing:.07em, .info lives "
            "INSIDE it, and .info span already reset font-style and font-size "
            "but not those two - so every tooltip has shipped uppercase and "
            "letterspaced. THAT EXISTING RESET IS THE EVIDENCE: someone was "
            "stopping title styling leaking into body copy and stopped one line "
            "short. Legible at 46 characters, much less so at 296, and C3 takes "
            "it from three tooltips to nine. Changes how three ruled tooltips "
            "LOOK and not one word of what they SAY. Written down because 'why "
            "is this reset here' is exactly the question a future reader asks "
            "before removing it",
     "  line-height:1.55;text-align:left;z-index:90;box-shadow:0 14px 34px rgba(0,0,0,.6)}",
     "  line-height:1.55;text-align:left;text-transform:none;letter-spacing:normal;z-index:90;box-shadow:0 14px 34px rgba(0,0,0,.6)}"),
    ('C3d', "C3 - the width ruling again: the mobile override is DELETED rather "
            "than raised. With min(330px,100%) there is one width instead of "
            "two, and the 100% does what the media query was approximating",
     "  width:250px;background:var(--surface-2);border:1px solid var(--border-h);border-radius:9px;",
     "  width:min(330px,100%);background:var(--surface-2);border:1px solid var(--border-h);border-radius:9px;"),
    ('C3e', "C3 - same deletion, the media-query half",
     "@media (max-width:720px){ .dgrid,.dlinks{grid-template-columns:1fr} .info span{width:210px} }",
     "@media (max-width:720px){ .dgrid,.dlinks{grid-template-columns:1fr} }"),
    ('C3f', "C3 - DEAD RULE DELETED. Written in a 720px media query for a "
            "`.card-header` containing a `.section-title`, markup the mock has "
            "never produced. Whoever wrote the mock designed the title-inside-"
            "card arrangement and did not ship it. Confirmed NOT activated by "
            "C3: with the note in a tooltip the Suivi header is a title and a "
            "15px glyph, and the three controls sit on their own row unwrapped "
            "at both widths. An unreachable rule is the CSS form of the "
            "unreachable bound from trap #21",
     "  #sec-suivi .card-header{flex-wrap:wrap}", None),
    ('C3g', "C3 - the second dead rule, deleted with the first. Its own entry "
            "so a partial revert names itself",
     "  #sec-suivi .card-header .section-title{flex:1 0 100%}", None),
    ('SV6', "SUIVI ROW, REVERSED: two rows, matching Projection. Grain "
            "toggle alone on row one, RIGHT-aligned; the two pickers side by "
            "side on row two, LEFT-aligned. Leo's earlier arrangement (SV2-SV4, "
            "retired above) put the grain left and stacked the pickers right at "
            "<=720px; he overruled it on consistency, because Projection is the "
            "newer pattern and two cards showing the same class of control "
            "should not be arranged differently. Measured after: row two is "
            "253px against 337 available at 393 and 304 at 360 - fits with 84 "
            "and 51px spare - and the longest label truncates on .cmp-name's "
            "existing ellipsis rather than anything added",
     ".svctl{display:flex;align-items:center;justify-content:space-between;gap:10px;",
     ".svctl{display:flex;flex-direction:column;gap:10px;margin-bottom:14px}"),
    ('SV7', "the second half of that rule. The two children align to opposite "
            "ends of the column, which is what makes it two rows rather than a "
            "stack: grain to the end, pickers to the start",
     "  flex-wrap:wrap;margin-bottom:14px}",
     ".svctl>.scen{align-self:flex-end}"),
    ('SV8', "and the picker group's own alignment, added rather than edited "
            "because the locked sheet has no line for it",
     None, ".svctl>.svctl-p{align-self:flex-start}"),
    ('DD1', "DUPLICATE DECLARATIONS DELETED, six sites, all dead by "
            "definition - a later rule on the same selector and condition "
            "already set the property, so the earlier one never rendered. "
            "Verified invisible rather than assumed: computed styles compared "
            "at 1180/720/640/480/393 before and after, no difference at any "
            "width on any of the six selectors. THE GRID ONE IS WHY THIS "
            "MATTERED - someone wrote a FOUR-column mobile layout for the group "
            "rows and a later block at the same breakpoint replaced it with "
            "five, so the four-column version had never rendered once. Ruled: "
            "delete it, because five columns is what Leo has been reviewing all "
            "along and shipping four now would be the surprise",
     "  .grp-h,.kid,.tot,.thead{grid-template-columns:1fr 58px 44px 46px;gap:7px}",
     None),
    ('DD2', "the same, .card's mobile padding: 18px never applied because "
            "16px 15px follows it at the same breakpoint",
     "  .card { padding: 18px; }", None),
    ('DD3', "the same, .nav-top's fade mask at 480: the 85% stop never applied "
            "because an 86% one follows. The rule keeps its other declarations, "
            "which are identical duplicates and therefore harmless",
     "  .nav-top{overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:none;",
     "  .nav-top{overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:none}"),
    ('DD4', "the same, the two mask lines that went with it",
     "  mask-image:linear-gradient(to right,#000 85%,transparent);", None),
    ('DD5', "and its webkit twin",
     "  -webkit-mask-image:linear-gradient(to right,#000 85%,transparent)}", None),
    ('DD6', "the same, .dgrid's base gap: 12px never applied because 26px 34px "
            "follows on the same selector. display and grid-template-columns "
            "are IDENTICAL duplicates on that pair and are left alone - "
            "redundant is not dead",
     ".dgrid{display:grid;grid-template-columns:1fr 1fr;gap:12px}",
     ".dgrid{display:grid;grid-template-columns:1fr 1fr}"),
    ('DD7', "the same, .mb-key's gap at 640",
     "  .mb-key{gap:8px 18px}", None),
    ('DD8', "the same, body's font-family. --ff-body carries an -apple-system "
            "fallback that the later literal drops, so the VARIABLE was dead on "
            "body specifically. Deleting the dead declaration keeps what renders "
            "today; restoring the fallback would be a change, not a cleanup",
     "  font-family:var(--ff-body);-webkit-font-smoothing:antialiased;color:var(--text)}",
     "  -webkit-font-smoothing:antialiased;color:var(--text)}"),
    ('SO1', "the .cmp-trigger mobile padding MOVES below the base rule it kept "
            "losing to. check_source_order found it defeated: media queries add "
            "no specificity, so the base .cmp-trigger at L423 outranked this at "
            "L143 purely on source order, and the tighter mobile sizing someone "
            "wrote had NEVER applied. Ruled: honour it, not delete it - the row "
            "had grown a title line above each control since it was written, "
            "and nobody had seen the intent tried. Measured: each trigger 6px "
            "narrower at <=720px, nothing reflows, head height unchanged",
     "  .cmp-trigger{padding:6px 8px;gap:5px}",
     "@media (max-width:720px){ .cmp-trigger{padding:6px 8px;gap:5px} }"),
    ('SV1', "SUIVI ROW - the two pickers get their own flex group. .svctl was "
            "space-between with THREE children, so free space was distributed "
            "BETWEEN all three and the two pickers were pushed apart on a wide "
            "screen - a PRE-EXISTING DESKTOP DEFECT the anchoring picker only "
            "made visible by giving the first picker a second one to be "
            "separated from. Two children now: grain group left, picker group "
            "right, pickers adjacent at the group's own gap",
     None, ".svctl-p{display:flex;align-items:center;gap:10px}"),
    # SV2, SV3 and SV4 RETIRED, not lost. They authorised Leo's first
    # arrangement of this row: at <=720px an explicit column, grain buttons
    # left, pickers stacked right. He has REVERSED it on consistency - the
    # Projection card is the newer pattern and two cards showing the same class
    # of control should not be arranged differently. Recorded as a reversal
    # rather than left to look like drift.
    #
    # The measurement that forced the first arrangement no longer applies: it
    # was 421px of content against 337 available with THREE items sharing a
    # line. The new arrangement puts the grain toggle on its own row, so row two
    # carries two items at 253px against 337 - it fits with 84px spare at 393
    # and 51px at 360, with the longest candidate label truncating on the
    # ellipsis that was already in the sheet.
    ('TS1', "TYPE SCALE - the mobile values. Measured, not felt: the DOMINANT "
            "size on the page was --fs-micro at 11px across 35 uses, against "
            "budgetflow's 13px workhorse in the same app, and the floor was 9px "
            "against budgetflow's 10px. The ticketing module read about two "
            "steps smaller everywhere. micro 11->13 is the change that carries "
            "it; nothing renders below 11px now. \"The text was too small\" is "
            "not a reason a later reader can check; these numbers are",
     "  :root{--fs-nano:9px;--fs-tiny:10px;--fs-mini:11px;--fs-micro:11px;--fs-caption:12px;",
     "  :root{--fs-nano:11px;--fs-tiny:11px;--fs-mini:13px;--fs-micro:13px;--fs-caption:14px;"),
    ('TS1b', "TYPE SCALE - the second line of the same declaration",
     "        --fs-base:12px;--fs-body:13px;--fs-large:15px;--fs-xl:18px;--fs-hero:24px;--fs-display:32px}",
     "        --fs-base:14px;--fs-body:15px;--fs-large:17px;--fs-xl:20px;--fs-hero:26px;--fs-display:32px}"),
    ('TS2', "TYPE SCALE - desktop barely moves. --fs-mini 13->14 only, so it "
            "stops being a step indistinguishable from --fs-micro at 14px. "
            "ELEVEN NAMES, NINE SIZES was the other half of the finding: on "
            "mobile micro==mini and caption==base, distinctions that exist in "
            "the code and are invisible on the page. The proposal makes them "
            "equal ON PURPOSE so the redundant names can be retired later with "
            "no visual change - NOT retired in this unit",
     "  --fs-mini: 13px;", "  --fs-mini: 14px;"),
    ('TS3', "TYPE SCALE - --fs-nano 10->12 desktop, joining --fs-tiny. Same "
            "eight-distinct-sizes move as TS2",
     "  --fs-nano: 10px;", "  --fs-nano: 12px;"),
    ('TS4', "TYPE SCALE - the DUPLICATE 720px BLOCK, deleted. Two "
            "@media (max-width:720px) blocks both redefined every --fs-*, and "
            "they DISAGREED - --fs-display was 28px here and 32px in the later "
            "one, which wins, so this declaration had never once applied. "
            "IF THE TWO HAD AGREED NOBODY WOULD EVER HAVE FOUND THEM: a "
            "correct-looking declaration that does nothing, with nothing "
            "pointing at it - the overflow-x leftover again. Collapsed in the "
            "SAME commit as the values, because editing a scale in two places "
            "and missing one is exactly how the 28px got stranded",
     "  --fs-nano:9px;  --fs-tiny:10px; --fs-mini:11px; --fs-micro:11px;", None),
    ('TS4b', "TYPE SCALE - second line of the dead block", 
     "  --fs-caption:12px; --fs-base:12px; --fs-body:13px; --fs-large:15px;", None),
    ('TS4c', "TYPE SCALE - third line of the dead block, and the 28px itself",
     "  --fs-xl:18px;   --fs-hero:24px; --fs-display:28px;", None),
    ('TS5', "TYPE SCALE - .dt horizontal padding 10->8, and this is NOT the "
            "trade Leo declined in C1. Then, spending padding bought nothing "
            "because the bar already fit. Now --fs-tiny goes 10->11 and six "
            "tabs need 399 against 393; 8px padding gives 375, so the change "
            "moves width OUT of padding and INTO text. Total tab width 375 vs "
            "today's 377 - the tap target is essentially unchanged while the "
            "label grows, on a page whose whole complaint was small text. "
            "Measured: +18 headroom at 393, better than the +16 C1a bought",
     "__TS5_rides_on_C1a__", "__TS5_rides_on_C1a__"),
    ('TS4d', "TYPE SCALE - the dead block's :root{ opener", "  :root{", None),
    ('TS4e', "TYPE SCALE - and its closing brace", "  }", None),
    ('D24', "D6 - overflow-x: clip instead of hidden. `hidden` makes body a "
            "SCROLL CONTAINER, so the sticky nav positioned against body and "
            "scrolled away with it: -353px after 1500px, on BOTH heads, with a "
            "position:sticky rule that was present and correct the whole time. "
            "`clip` clips the same overflow without creating a scroll "
            "container. Measured, not reasoned: hidden -353, clip 0, visible 0",
     "html,body{overflow-x:hidden;min-height:100%;background:var(--bg);",
     "html,body{overflow-x:clip;min-height:100%;background:var(--bg);"),
]

# How much the working mock may differ from the locked one, in lines. See the
# budget check below for why this exists and why it is one pair of numbers
# rather than a count per entry. Raising it is an act of authorisation and
# belongs in the same commit as the ledger entry that explains the lines.
BUDGET_ADDED = 1159
BUDGET_REMOVED = 203

# (id, ruling, signature that must appear on the WORKING side of its hunk)
AUTHORISED = [
    ('D1', 'P4.1 — old commission disclaimer deleted from the Revenus tooltip',
     'Les frais de réservation payés par l’acheteur'),
    ('D2', 'EE1 — default view honours the configured warm-up mark',
     'on[d.k] = !d.warmup'),
    ('D3', 'EE2 + ruling §1 — warmup badge, .badge.amber, English label',
     '<span class="badge amber" style="margin-left:8px">warmup</span>'),
    ('D4', 'FF1 — over-capacity states the overshoot instead of claiming complet',
     'au-delà de la jauge'),
    ('D5', 'FF1 — Places libres reads "jauge dépassée" when over',
     "jauge dépassée"),
    ('D6', 'FF1 — bar fill turns amber when over capacity',
     "d.now>d.cap?'var(--amber)'"),
    ('D7', 'FF2 — gratuits share under the count, amber at >= 50%',
     "pc>=50?'var(--amber)'"),
    # The smallest kind of deviation: appearance identical, input changed.
    ('D8', '§5 — headline ring is presence ÷ jauge, not tickets ÷ jauge. Same '
           'element, same geometry, same position; only its input moves',
     'A.pres_tot != null ? A.pres_tot : A.n'),
    ('D10', 'the weekly % is the JAUGE on both sides, and says so. Two '
            'denominators under one unlabelled "%" is how the ring went wrong '
            'and how trap #14 happened',
     '% de la jauge · ${r.ca}% cumulé'),
    ('D11', 'B1 — the comparison menu is built from D.cands, which is built '
            'from the series files that exist. It was a hardcoded list wired '
            'from a different source than the data behind it',
     'const CMAP = Object.fromEntries'),
    ('D12', 'B1 — picking a comparison fetches that edition\'s own series and '
            'rewrites the reference column. It used to move CSEL and nothing '
            'else',
     'async function pickCmp(n)'),
    ('D13', 'B1 — a failed fetch says so, and says the figures still on screen '
            'are the previous comparison. Silence is the worst outcome',
     'Comparaison indisponible'),
    ('D14', 'a row with no counterpart renders an em-dash, not 1 jan 1970. '
            '`fday(null)` is the epoch, and it shipped',
     "r.db ? fday(r.db) : '—'"),
    ('D15', 'the same for the WEEKLY row - a bucket the reference does not '
            'have renders an em-dash rather than an S-week over the epoch. Two '
            'functions, two edits, two entries: one signature covering both '
            'would have let either be reverted silently',
     "r.sb ? 'S−'+r.w"),
    ('D16', 'the projection methodology reads YC/YR instead of 2023/2026. Same '
            'class as A7, ten literals in one block, found by the year scan on '
            'its first run',
     '1. Trajectoire ${YR}'),
    ('D17', 'D16 continued - the second scenario\'s heading and prose. Three '
            'hunks, three entries, for the same reason D14 and D15 are two: a '
            'single signature would let the others be reverted in silence',
     '2. ${YR} × coef. ${YC}'),
    ('D18', 'D16 continued - the per-day application block',
     '→ Trajectoire ${YR} :'),
]
# D16-D18 named YR/YC. D21 removed the years entirely - the block states a
# METHOD, so it has no year to go stale - which supersedes them. The three
# entries above stay in the ledger as history and are matched by the D21 hunk
# instead; a deviation that is superseded is not a deviation that was reverted.
AUTHORISED = [a for a in AUTHORISED if a[0] not in ('D16', 'D17', 'D18')] + [
    ('D19', 'D0 - the velocity card prints a RATE. It printed the window total '
            'with "/jour" after it, beside "Rythme requis" which is a true '
            'daily rate: 1 350 against 346 read as four times the pace needed '
            'where the truth was 56% of it',
     'billets vendus / jour'),
    ('D20', 'D0 - presence velocity is named "entrées / j". A 2-jours pass is '
            'two entries, so rennes\' days sum to 84/j against 63.9 tickets/j. '
            'Both right, different quantities, one word',
     'entrées / j</span></div></div>'),
    ('D21', 'the projection methodology states a METHOD, so it carries no year '
            'and cannot go stale when the selector moves. Figures come from the '
            'SELECTED candidate, which the payload already carries - which '
            'removed the last reader of const LG, and LG with it',
     'window.renderLogique = function()'),
    ('D22', 'D1 - money through Intl.NumberFormat. The symbol was on the wrong '
            'side for French and k() had no millions tier, so 1 234 000 printed '
            'as €1234k',
     'const _EURF = new Intl.NumberFormat'),
    # One deviation, several hunks. Each gets its own signature for the reason
    # D14/D15 are two entries: a single signature would let the rest be
    # reverted in silence.
    ('D19b', 'D0 - CYR hoisted beside YR. Declared in the Suivi block it was in '
             'the temporal dead zone when the velocity card read it, and threw '
             'before anything rendered',
     'The year of the SELECTED comparison. Declared here'),
    ('D19c', 'D0 - the reference rate in the velocity meta line',
     '${CYR} : ${nf(b)}/j'),
    ('D20b', 'D0 - the projection card names entrées/j too',
     'contre ${nf(p.refvel)} entrées/j'),
    ('D21b', 'D21 - the projection selector repaints the methodology block',
     'if (window.renderLogique) window.renderLogique();'),
    ('D21c', 'D21 - scenario 1, stated as a method',
     '1. Trajectoire ${C.label}'),
    ('D21d', 'D21 - scenario 2, stated as a method',
     '2. ${C.label} × coef. de vélocité'),
    ('D21e', 'D21 - the per-day application block, from the selected candidate',
     '${days.length ? `<div class="eyebrow"'),
    ('D21f', 'D21 - the block renders once at load and on every selection',
     'window.renderLogique();'),
    ('D21a', 'D21 - the comment recording why the block has no year in it',
     'the methodology block states a METHOD'),
    ('D21g', 'D21 - `const LG` deleted. A pure deletion, matched against the '
             'LOCKED side: it was a second copy of numbers the payload already '
             'carried, which is how it came to ship epk\'s under every other '
             'event\'s name',
     'const LG = {'),
    ('D23', 'D4 - the répartition dots are keyed by GROUP and use --green / '
            '--amber / --cur / --text-dim. COL[i%3] borrowed --day-0, one of '
            'the four day colours, so the two colour systems competed',
     "const COL_G = {'Billets Réguliers':'var(--green)'"),
    ('D23b', 'D4 - the group bar takes the same colour as its dot',
     'background:${gcol(g.g)}"></i></div>'),
    ('D25', 'D5 - the prix affiché -> net encaissé bar is green. --cur is the '
            '"current edition" colour everywhere else on the page',
     'style="width:${w(net)}%;background:var(--green)"'),
    # One ruling, five hunks: the bar has a track and a legend and the diff
    # splits them. Each gets a signature for the D14/D15 reason.
    ('D25b', 'D5 - the legend swatch for net HT', 'mb-sw" style="background:var(--green)"'),
    ('D25c', 'D5 - the VAT segment', 'background:rgba(52,211,153,'),
    ('D25d', 'D5 - the fee segment', '--fc:rgba(52,211,153,'),
    ('D23c', 'D4 - the group dot takes its colour by name', 'background:${gcol(g.g)}"></span>'),
]


AUTHORISED_CSS += [
    ('C6', 'the velocity meta stays on the title line at every width. .rb-top '
           'is already space-between, so desktop was always right; only this '
           'mobile override forced the wrap. A rule removed, not layout added. '
           'Measured at 393px: 41.2px -> 20.1px, no overflow',
     "  .rb-m{width:100%}",
     "  .rb-m{font-size:var(--fs-tiny);text-align:right;min-width:0}"),
    ('C5', 'the separator above Vélocité 14j and above Vélocité 30j. The line '
           'Leo already sees is .vproj\'s border-bottom, NOT .rb\'s - all four '
           '.rb inside #vel measure 0px on both edges, because #vel .rb sets '
           'border-bottom:0. Same declaration and same token; it cannot be the '
           'same RULE without dragging .vproj\'s padding and typography onto '
           'the blocks. `+ .rb` cannot match 7j: first child of the accordion, '
           'no preceding sibling. Appended to the SAME PHYSICAL LINE: AUTHORISED_CSS matches whole-line modifications, and a new line of its own would read as an invented rule',
     "#vel .rb{border-bottom:0;padding:22px 0 6px}",
     "#vel .rb{border-bottom:0;padding:22px 0 6px}#vel .rb + .rb{border-top:1px solid var(--border)}"),
    ('C-SUIVI', 'the reference ticket count matches the current one, so the two '
                'sides compare at a glance. Weight kept; only the colour drops',
     ".sv-l .sv-n{color:var(--text-muted);font-weight:500}",
     ".sv-l .sv-n{font-weight:500}"),
    ('D29', "the stray second declaration of overflow-x on html, one line above "
            "the D6 fix. clip won on SOURCE ORDER alone - same specificity, "
            "later declaration - so D6 worked while holding by accident: "
            "reorder those two rules and the nav breaks again with the correct "
            "clip sitting right there. Production's sheet has no such line. "
            "Trap #15's shape pointed at trap #15's own fix",
     "html{scroll-behavior:smooth;scroll-padding-top:96px;overflow-x:hidden}",
     "html{scroll-behavior:smooth;scroll-padding-top:96px}"),
    ('D28', "D1(a) - the hover readout value drops from --fs-caption (16px) to "
            "--fs-mini. It was 16px against an 11-12px row",
     ".ck-va{font-family:var(--ff-display);font-size:var(--fs-caption);font-weight:600;color:var(--cur)}",
     ".ck-va{font-family:var(--ff-display);font-size:var(--fs-mini);font-weight:600;color:var(--cur)}"),
    ('D28b', "D1(a) - the reference value, same change",
     ".ck-vb{font-family:var(--ff-display);font-size:var(--fs-caption);font-weight:600;color:var(--ref)}",
     ".ck-vb{font-family:var(--ff-display);font-size:var(--fs-mini);font-weight:600;color:var(--ref)}"),
    ('D28c', "D1(a) - the mobile override, which would otherwise be LARGER than "
             "the desktop size it was just reduced below. NOW A DELETION: the "
             "rule never took effect. Its base rule sits a few lines BELOW it at "
             "equal specificity, so source order defeated it and .ck-va/.ck-vb "
             "have always rendered at --fs-mini. Ruled deleted rather than "
             "reordered - repairing the order would have shipped 13px -> 11px "
             "on readouts the typography ruling had just taken UP two steps. "
             "The rule was wrong, its defeat was doing what we wanted, and "
             "fixing the bug would have shipped the regression. Measured 13px "
             "at 560 and 393 before and after: zero visual consequence",
     "  .ck-va,.ck-vb{font-size:var(--fs-micro)}",
     None),
    ('TS6', "the same deletion for .ck-jx, and its own entry because it is its "
            "own line and could be restored alone. Never had an AUTHORISED_CSS "
            "entry at all - it was locked-mock content that source order had "
            "been quietly discarding since before this ledger existed, which is "
            "why the source-order check is worth building",
     "  .ck-jx{font-size:var(--fs-tiny)}",
     None),
]

AUTHORISED += [
    ('C7', 'the projection readout moves ABOVE the chart, top right. Inline '
           'with the legend it overflowed its container by 40.8px at 393px and '
           'ran 12.8px past the viewport edge - .ck-key is flex-wrap:nowrap at '
           'that breakpoint, so it could not wrap and clipped instead. Now 0px '
           'overflow, 28px inside the edge. The locked mock clips the same way, '
           'so this is a change request, not a regression',
     '<div style="display:flex;justify-content:flex-end;margin-bottom:5px">'),
    ('C7b', 'C7 - the readout leaves .ck-key, which keeps only the legend',
     '<span class="ck-va"></span><span class="ck-vb"></span></span>'),
    # Covers the fm() hunk in full: D26 removed the string surgery there and
    # D30 rewrote the same line, so one id claims one hunk. D26's ruling text
    # lives in the handoff and in the mock's own comment.
    ('D30', 'fm() asks the formatter instead of editing its output (D26), and '
            'the non-currency branch built its own "1.7k" with a DOT, on '
            'a page where every other number uses a comma. Found by dumping '
            'every tick label across the six pages while checking the zero '
            'tick - same class as D1, same fix: ask Intl',
     "const _NC = new Intl.NumberFormat('fr-FR', {notation:'compact'"),
    ('D31', 'D2 - a weekly series read under a J−X axis names BOTH scales. The '
            'Revenus chart plots one point per week and labelled it J−105, '
            'which is a day number for a week bucket',
     "data-w=\"${o.w!=null?o.w:Math.floor(o.jx/7)}\""),
    ('D31b', 'D2 - the readout renders J−x / S−w when the week is present, and '
             'J−x alone when it is not (the projection charts are daily)',
     "z.dataset.w != null ? ' / S−' + z.dataset.w : ''"),
    ('D32', 'D3(a) - a hit zone for every jx that is DRAWN. Where the '
            'comparison edition started earlier its curve was on the plot and '
            'unreadable, which is the one thing a hover is for. 105 of epk\'s '
            '262 points were unreachable',
     'const mine = new Map(ch.act.concat(proj).map'),
    ('D32b', 'D3(b) - the absolute beside the percentage, as its OWN attribute '
             'rather than concatenated into the value: one label, one number, '
             'so the tick-shape assertion still means something',
     'data-na="${o?abs(o.v):\'\'}"'),
    ('D32c', 'D3 - projChart takes the day capacity, which is what turns a '
             'percentage into a ticket count',
     'function projChart(ch, col, scen, refLabel, cap)'),
    ('D32d', 'D3 - the projection card passes it',
     "projChart(p.chart, col, i?'p2':'p1', C.label, p.cap)"),
    ('D32e', 'D3(a) - the current-side dot hides where our campaign had not '
             'started, rather than parking at 0',
     'the current side can now be absent'),
    ('D32g', 'D3(b) - the readout writes them, and the label and separator are '
             'written on HOVER rather than rendered statically: standing in the '
             'markup they read "Tickets ·" with nothing after them',
     'belong to a HOVERED point, not to the chart'),
    ('D27', 'D1(b) - the readout labels the unlabelled figure and separates the '
            'two values, in Leo\'s words: "Tickets" and a middle dot. The label '
            'travels on the .ck-read element rather than being emitted inline, '
            'so applyZone decides when to show it. Uses .kc-s, the legend\'s '
            'own class, so no CSS is invented',
     "data-lbl=\"Tickets\""),
    ('D26b', 'D26 - the revenue chart passes k, the compact formatter, so there '
             'is no string left to operate on',
     'k, not eur: the axis and the readout want the compact form'),
    ('D26c', 'D26 - the second line of the same call, which the diff splits',
     "weeklySeries(past,'rcb') : [], k);"),
    ('AN2', 'anchoring - the three modes. `anchorOf` mirrors '
            'dashboard_payload.anchor(): j_minus and exact_date differ by the '
            'weekday snap alone and share a weekly column, days_since_launch '
            'shifts BOTH grains because its offset is the campaign-length '
            'difference and reaches 105 days. The cut is raw in every mode, '
            'inherited from run.py\'s two same-point filters rather than '
            're-decided',
     'function anchorOf(s)'),
    ('AN3', 'anchoring - w >= 0 on the reference bucket. Unshifted, `jx >= 0` '
            'already implied it; shifted, the candidate\'s event lands fifteen '
            'weeks past ours in launch-aligned time and rendered fifteen rows '
            'of "S−−1"…"S−−15". Measured: 15 on epk under launch, 0 under '
            'j_minus',
     'if (!keep || w < 0) continue;'),
    ('AN4', 'anchoring - the mode picker, a THIRD instance of the existing '
            '.sw-wrap / .cmp-trigger / .sw-menu component, so no CSS is '
            'invented. Starts on D.amode, the config row, so the mode is not '
            'stated in a second place',
     'function modeMenu()'),
    # AN5 RETIRED, not reverted. It authorised "L'alignement s'applique aux deux
    # grains", which X7 replaces with the four-variant sentence. The entry is
    # removed rather than left to fail as a MISSING deviation, because the line
    # it described no longer exists in either file - and a ledger entry for a
    # deviation that is gone is the same lie in the other direction.
    #
    # The reason the line went rather than moving to the tooltip: it could never
    # have been wrong. It made no claim the table could contradict, which is
    # exactly how `exact_date` shipped green and meaningless underneath it. Its
    # launch clause survives, inside alignNote's launch variant, where it is the
    # only mode it was ever true of.
    ('C1-sec-velocite', 'C1/C2 - anchor on "Vélocité actuelle". One tab per section means every section needs a target; seven had none. Markup, one attribute, no rendered change - and one entry each rather than one covering all seven, so a reverted anchor names itself',
     '<div class="sec" id="sec-velocite">'),
    ('C1-sec-presence', 'C1/C2 - anchor on "Présence attendue par jour". One tab per section means every section needs a target; seven had none. Markup, one attribute, no rendered change - and one entry each rather than one covering all seven, so a reverted anchor names itself',
     '<div class="sec" id="sec-presence">'),
    ('C1-sec-evenement', 'C1/C2 - anchor on "Événement". One tab per section means every section needs a target; seven had none. Markup, one attribute, no rendered change - and one entry each rather than one covering all seven, so a reverted anchor names itself',
     '<div class="sec" id="sec-evenement">'),
    ('C1-sec-jours', 'C1/C2 - anchor on "Jours de l’événement". One tab per section means every section needs a target; seven had none. Markup, one attribute, no rendered change - and one entry each rather than one covering all seven, so a reverted anchor names itself',
     '<div class="sec" id="sec-jours">'),
    ('C1-sec-comparaison', 'C1/C2 - anchor on "Comparaison". One tab per section means every section needs a target; seven had none. Markup, one attribute, no rendered change - and one entry each rather than one covering all seven, so a reverted anchor names itself',
     '<div class="sec" id="sec-comparaison">'),
    ('C1-sec-plateformes', 'C1/C2 - anchor on "Plateformes". One tab per section means every section needs a target; seven had none. Markup, one attribute, no rendered change - and one entry each rather than one covering all seven, so a reverted anchor names itself',
     '<div class="sec" id="sec-plateformes">'),
    ('C1-sec-donnees', 'C1/C2 - anchor on "Données". One tab per section means every section needs a target; seven had none. Markup, one attribute, no rendered change - and one entry each rather than one covering all seven, so a reverted anchor names itself',
     '<div class="sec" id="sec-donnees">'),
    ('FOOT', 'THE FOOTER WAS INVISIBLE ON BILLETTERIE. One </div> after '
             'sec-donnees closes page-details, which the LOCKED mock never '
             'did - so #foot was a CHILD of page-details and rendered only '
             'when Détails was showing. Measured: height 0 on Billetterie, 23 '
             'on Détails, on the shipped page and the locked file alike. A '
             'markup fix to the mock, not a design change: the div imbalance '
             'is exactly 1 and the footer is a sibling of the pages, inside '
             '.wrap, which is where it now sits',
     '</div><!-- /page-details -->'),
    ('C3-campagne', 'RULED OUT of v2: the Page Campagne placeholder block, '
                    'removed rather than fixed. It was a VISIBLE card - "Analyse '
                    'de campagne : forme, phases de prix, heure zéro..." - and '
                    'an unclosed </div> in the LOCKED mock nested it inside '
                    'page-details, so it rendered at the foot of the Détails '
                    'page. Campagne is intel-gathering, not a feature of the '
                    'ticketing tool. Fixing the div would have left a '
                    'correctly-scoped page nothing navigates to, which is dead '
                    'markup with a longer life expectancy. A pure deletion, so '
                    'matched against the LOCKED side',
     '<div class="page" id="page-campagne">'),
    ('B2-absence', 'live editions in the menu made a dormant bound reachable: '
                   '`jr >= 0` bounds the future by the reference\'s EVENT, which '
                   'is right for a finished edition and wrong for a live one '
                   'whose data stops at today. Every row between rendered '
                   '`day[jr] || 0` -> 0 - "sold nothing", about a day that has '
                   'not happened for them. 25 of 89 future rows on rennes vs '
                   'epk_2026, and check_b1_switch was blind to it because the '
                   'server shared the error. Trap #21 again: a bound that was '
                   'correct by accident until an assumption moved',
     'const ok = r.fut ? (jr >= 0 && jr >= lastJr)'),
    ('B2', 'live editions in the comparison menu. The copy shown where a LIVE '
           'candidate is picked, not only where the mode is: under Jour J '
           'alignment its own J−x has not happened for our already-lived rows, '
           'so the reference column is em-dashes - correct, and unreadable '
           'without saying so. The reader who hits this picked an edition, not '
           'an alignment',
     'est une édition EN COURS'),
    ('GRP', 'the comparison menu builds THREE groups. The locked mock has '
            'always had "Événements en cours" as its third and '
            'suivi_selector.GROUP_TITLES carries all three - this loop read '
            'two, so a live candidate filed under "Autres éditions passées". '
            'Genève 2026 is not a past edition. Unreachable since B1 shipped '
            'because every candidate was finished; the widening made it '
            'reachable. Third instance of the class after jr >= 0 and the '
            'weekly w >= 0. The loop iterates the values PRESENT in the '
            'payload rather than any list written here - a hardcoded list is '
            'what broke, and hardcoding three instead of two would only move '
            'the same failure one group further out. ORDER sorts what it '
            'recognises; anything else sorts last and titles itself from its '
            'own key, so an unknown group renders badly-named rather than '
            'vanishing. verify/check_cand_groups.py asserts both ends',
     'const seen = [...new Set((D.cands || []).map(c => c.g))]'),
    ('C4-mk', 'C4/E - THE HEADER CARD LEADS. #logique was a trailing third '
              'card after the days, which is why "where does it go" needed its '
              'own ruling under every other arrangement; at the top it stops '
              'being an orphan and becomes the section header. margin-BOTTOM '
              '12px, the same gap the day cards already carry between '
              'themselves, so the header sits in the same rhythm - read from '
              'the existing value, not chosen',
     '<div class="card" id="logique" style="margin-bottom:12px"></div>'),
    ('C4-detbot', 'C4/E revised - DÉTAILS SITS AT THE BOTTOM OF ITS CARD, '
                  'centred, with the bare .ac-t treatment: no inline overrides, '
                  'because every other accordion on the page does exactly this '
                  '- "Courbe cumulative" on each day card, Revenus\' own '
                  'toggle. It shipped briefly INSIDE the head row with the '
                  'padding and border stripped, where on a phone it hung beside '
                  'the second dropdown and read as a third control rather than '
                  'a disclosure. Consistency bug, not a preference. '
                  'TWO ENTRIES WERE DELETED for this, not reverted by accident: '
                  'C4-det (the id-named .ac-b) and C4-ac (ac()\'s named-target '
                  'fallback). Both existed ONLY because the toggle had left its '
                  'sibling; with it back, ac() returns to nextElementSibling and '
                  'the fallback would have been dormant code that looks needed '
                  'and is not',
     '<div class="ac-t" onclick="ac(this)"><span>Détails</span>'),
    ('SV-gap', 'ruling - the alignment note gains an 11px BOTTOM margin. It had '
               '8px above and nothing below, so it sat close under the controls '
               'and butted straight against the column headers, reading as one '
               'block with the table rather than as an introduction to it. 11px '
               'is READ, not chosen: it is .sec-head\'s own margin-bottom, the '
               'gap Répartition\'s table header already uses above itself. '
               'Measured 0px before and 11px after',
     'class="sec-note" style="margin:8px 0 11px"'),
    ('AUD-fee', 'audit ruling 3 - the Shotgun booking fee is DECLARED as '
                'unconfirmed. AUDIT_SCOPE.md priced it: the fee segment is the '
                'only figure the 13,03%% multiplier touches, 500 210 EUR of the '
                '623 092 EUR shown is Shotgun and unverified, and Paris XXL '
                'alone could be wrong by 142 033 EUR. DICE is confirmed against '
                'a payout statement and says so in the same sentence, so the '
                'reader can see which half is which. Same degrade-honestly rule '
                'as everything else on the page: a silent unknown becomes a '
                'declared one',
     'les frais Shotgun sont dérivés des données de la plateforme'),
    ('C4-total', 'ruling (d) - THE PROJECTION TOTAL: the three facts each day '
                 'card gives, aggregated, which a reader currently assembles by '
                 'hand. It sits directly under the two pickers that define it, '
                 'and that POSITION is what separates it from Vélocité\'s "à ce '
                 'rythme, N billets le jour J" - different calculations that '
                 'will disagree, with the method named adjacent to the result. '
                 'Sell-out is the LATEST per-day date, not a sum, because the '
                 'event is not sold out until every day is; a day with no date '
                 'gives the aggregate none (epk on coefficient: dimanche 8 048 '
                 'of 10 000, so no date). A day with no projection is not '
                 'dropped from the denominator - the jauge is summed over the '
                 'same days and the count is stated (Genève: 1 of 2). Excluded '
                 'days are NOT followed, deliberately: Présence\'s `on` map is '
                 'scoped to that IIFE and THE DAY CARDS DO NOT FOLLOW IT '
                 'EITHER, so a total that did would stop being the sum of what '
                 'sits below it',
     'const total = () => {'),
    ('C4-over', 'C4/E x ruling §1 - a FINISHED edition gets no pickers either. '
                'Both control a forecast that no longer renders, so they would '
                'be affordances that change nothing - the same class §1 was '
                'about. Found by check_finished_edition, which counted two '
                'toggles still in the header of a section that projects '
                'nothing; the check caught the interaction between two rulings '
                'that were each correct alone',
     "${OVER ? '' : `<div id=\"projctl\">"),
    ('C4-head', 'C4/E - the section head is emitted by renderLogique, because '
                'the card carrying it is that one. Three controls in the right '
                'slot, all governing every day below: settings above content, '
                'which reads as governing what follows. That is why B was '
                'rejected - there the same controls sat inside Vendredi\'s card '
                'while changing Samedi\'s numbers. At 393 the row wraps to title '
                '/ controls; ruled acceptable because it wraps deliberately '
                'rather than by accident. "Logique de projection" retires as a '
                'NAME here - one string in one renderer, referenced by no tab, '
                'no scroll-spy target and no check',
     "secHead('sec-projection', undefined,"),
    ('C4-heads', 'C4/E - and its HEADS entry. The tooltip is what stops '
                 'sec-projection trading its EXEMPT entry for a NO_TOOLTIP one: '
                 'check_section_heads wants exactly one .info per head, and an '
                 'exemption swapped for another exemption is not a section '
                 'passing the rule',
     "'sec-projection':  {t:'Projection Finale',"),
    ('C4-rm', 'C4/E - and the per-day segmented control is GONE from the card. '
              'A removal-shaped hunk: the two .scen-b buttons came out and the '
              'panes now follow the section-level PSCEN. Its own entry so the '
              'deletion cannot be quietly undone - restoring those buttons '
              'would restore the per-day independence C4-pscen removed on '
              'purpose',
     '<button class="scen-b on" onclick="scen(this,0)">Trajectoire'),
    ('C4-pscen', 'C4/E - ONE scenario for the section, and this REMOVES A '
                 'CAPABILITY. scen(btn,i) resolved btn.closest("[data-proj]"), '
                 'so every day toggled independently - Vendredi on trajectoire '
                 'while Samedi sat on coefficient, and a reader adding two cards '
                 'could total two days computed under different models. Nothing '
                 'read that state: no check, no export, no other renderer. '
                 'Recorded as a REMOVAL rather than a move, because someone will '
                 'miss it before they miss the bug',
     'let PSCEN = 0;'),
    ('C4-menu', 'C4/E - the trajectory picker: a FOURTH instance of the existing '
                '.sw-wrap / .cmp-trigger / .sw-menu component, so it invents no '
                'CSS. Chosen over the segmented control by measurement - at 393 '
                'the segmented one took a row to itself, head 142px against 95 - '
                'and over .dtog because a switch labelled "× coef. vélocité" '
                'names only the state you get by turning it on and never shows '
                'the alternative',
     'window.scenMenu = () => {'),
    ('C4-pane', 'C4/E - the panes follow PSCEN rather than each card\'s own '
                'button state',
     "style=\"display:${i===PSCEN?'block':'none'}\""),
    ('C4-pm2', 'C4/E - and its other half: render() must tolerate #projctl not '
               'existing yet, because on first load this IIFE runs before '
               'renderLogique creates it. Two entries, because reverting either '
               'alone leaves the picker empty or throws',
     "const pc = document.getElementById('projctl');"),
    ('C4-pm', 'C4/E - #projctl now lives in a head renderLogique emits, so it '
              'does not exist when the projection IIFE first runs. Exposed and '
              'guarded rather than the two modules being reordered: whichever '
              'runs second fills it',
     'window.projMenu = menu;'),
    ('OVER', 'ruling §1 - THE EDITION IS OVER AND THE PAGE SAYS SO. `run.py` '
             'has carried this guard in three places since before the redesign '
             '(`\'Terminé\' if days_remaining_display <= 0`); every v2 component '
             're-derived J−x from D.jx without it. The tell: parisxxl read '
             '"PARIS 130326 · Terminé" in the transplanted nav and "En vente · '
             'J−-2" in the badge below it. <= 0 not < 0 - at exactly 0 the '
             'required rate divides by zero and renders "∞ /j", latent because '
             'every edition passes through 0 for one day. SAME is separate from '
             'JXL because past the event there is no J−x to be at the same point '
             'of. COPY NOT RULED: "en fin de campagne" is mine, not Leo\'s',
     'const OVER = JX <= 0;'),
    ('OVER-b', 'ruling §1 - the hero badge takes the guarded label', 
     '<span class="badge amber">${JXL}</span>'),
    ('OVER-m', 'ruling §1 - the mini-bar reference mark, hover text', 
     'title="${YR} ${SAME}"'),
    ('OVER-y', 'ruling §1 - Présence year-on-year subtitle', 
     'vs ${YR} ${SAME} · '),
    ('OVER-s', 'ruling §1 - Vélocité reference rate subtitle', 
     'rate(`Rythme ${YR}`, B.vel[7], SAME,'),
    ('OVER-n', 'ruling §1 - the Vélocité note. Written as one template with the '
               'branch INSIDE it: branching around the whole string put the '
               'event-date literal in twice and pass 0 failed the build, which '
               'is the identity guard working', 
     "${OVER ? 'Édition terminée' : `${JX} jours restants`} · événement"),
    ('OVER-r', 'ruling §1 - the required rate is not computed past the event. '
               'bordeaux rendered "Rythme requis -17 802 / jour"', 
     'const need = OVER ? null : Math.ceil((CAP - A.n) / JX);'),
    ('OVER-rf', 'ruling §1 - and the row states the result it ended on instead', 
     '<div class="vr-k">Résultat final</div>'),
    ('OVER-p', 'ruling §1 - `A.n + cur7 * JX` projects BELOW current sales at a '
               'negative JX: bordeaux read 26 130 against 26 698 sold', 
     'const proj  = OVER ? A.n : A.n + cur7 * JX;'),
    ('OVER-v', 'ruling §1 - so the sentence states the total rather than a rate', 
     'Édition terminée — <b>${nf(A.n)} billets</b> vendus au total'),
    ('OVER-t', 'ruling §1 - and its tense follows. "il en manquerait" is a '
               'conditional about a day that has already happened', 
     "il en ${OVER ? 'a manqué' : 'manquerait'}"),
    ('OVER-pf', 'ruling §1 - PROJECTION FINALE PROJECTS NOTHING. Every forecast '
                'figure lives inside S(i), which this early return never reaches, '
                'so "sur -1 jours", "de J−-1 à J−0" and the required rate all go '
                'with it rather than each needing its own guard. Degrades in the '
                'same shape as the missing-reference card immediately below. The '
                'retrospective Leo specified REPLACES this block - this is the '
                'floor, and must not be what makes that look done', 
     'if (OVER) return `<div class="card" style="margin-bottom:12px">'),
    ('OVER-me', 'ruling §1 - the methodology sentence names no J−x it does not have', 
     'sur les jours restants${OVER ?'),
    ('OVER-d', 'ruling §1 - the Détails badge, which is the one that contradicted '
               'the nav switcher three lines above it', 
     "${D.jx <= 0 ? 'Terminé' : `En vente · J−${D.jx}`}"),
    ('SV0', 'SUIVI ROW - the markup half: the two pickers wrapped in .svctl-p '
            'so .svctl has two children instead of three',
     '<div class="svctl-p">'),
    ('C3', 'the section head is EMITTED BY THE RENDERER, from HEADS via '
           'secHead(). Every card on the page has its innerHTML replaced at '
           'runtime, so a head placed in the markup is wiped the moment its '
           'renderer runs - trap #20 in a lifecycle rather than a position. '
           'One source for ten heads, so the title a tab scrolls to and the '
           'title the card shows cannot drift',
     'function secHead(id, dynNote, right)'),
    ('C3-heads', 'the head DATA, moved out of ten markup blocks into one map. '
                 'Structural, not per-event: which mode/label a card shows is '
                 'the same on every page, and the one dynamic note travels as '
                 'SUIVINOTE because it names the picked candidate',
     'const HEADS = {'),
    ('C3-rev', 'C3 - the Revenus renderer emits its head',
     "getElementById('rev').innerHTML = secHead('sec-overview')"),
    ('C3-vel', 'C3 - Vélocité. The one section with no note, so it gets a title '
               'and NO tooltip - no copy invented to fill a pattern',
     "getElementById('vel').innerHTML = secHead('sec-velocite')"),
    ('C3-pres', 'C3 - Présence. Its note restated the existing tooltip sentence, '
                'so only the control hint is appended (ruled)',
     "getElementById('pres').innerHTML = secHead('sec-presence')"),
    ('C3-rep', 'C3 - Répartition', "getElementById('rep').innerHTML = secHead('sec-repartition')"),
    ('C3-suivi', 'C3 - Suivi. Its note names the picked candidate, so it is a '
                 'VALUE (SUIVINOTE) rather than a constant - it was written into '
                 'a #suivinote element that no longer exists',
     "getElementById('suivi').innerHTML = secHead('sec-suivi', SUIVINOTE)"),
    ('C3-suivinote', 'C3 - the dynamic note becomes a variable rather than an '
                     'element write',
     "SUIVINOTE = 'comparaison à jour de semaine identique"),
    ('C3-ident', 'C3 - Événement, MERGED. This card opened with its own heading '
                 'row, so a section title above it gave the card two headings - '
                 'which is the thing C3 removes one of. The dhero row moves into '
                 'the head as its right-hand slot',
     "host.innerHTML = secHead('sec-evenement', undefined,"),
    ('C3-identpill', 'C3 - the merged Événement head: the status pill moves from '
                     'margin-left:auto inside the dhero row to margin-left:8px '
                     'beside the event name, because the head already flexes '
                     'the two apart. Its own entry - the pill is the piece a '
                     'reader would notice missing. SIGNATURE NARROWED by ruling '
                     '§1, which rewrote the pill\'s TEXT on the same line: this '
                     'entry asserts the pill\'s POSITION and OVER-d asserts what '
                     'it now says. Trap #22 a second time - one line, two '
                     'rulings - and resolvable here only because the two '
                     'decisions happen to be about different parts of it',
     '<span class="badge amber" style="margin-left:8px">'),
    ('C3-days', 'C3 - Jours', "days.innerHTML = secHead('sec-jours')"),
    ('C3-cmp', 'C3 - Comparaison. The ternary gains a paren because the head is '
               'concatenated before it',
     "cmp.innerHTML = secHead('sec-comparaison') + (HAS_CMP ?"),
    ('C3-plat', 'C3 - Plateformes is the ONE card that is not runtime-filled: '
                'its tile list is static markup, so the head is INSERTED rather '
                'than concatenated. Same source, so the data is still stated once',
     "plat.insertAdjacentHTML('afterbegin', secHead('sec-plateformes'))"),
    ('C3-platcard', 'C3 - the tile list gets a card so it can hold a title. '
                    'Ruled: every section is a card with its title inside, no '
                    'exception, because one rule is what a later reader can apply',
     '<div class="card" id="det-plat">'),
    ('C3-dd', 'C3 - Données', "dd.innerHTML = secHead('sec-donnees')"),
    # ---- exact_date becomes a calendar operation -------------------------
    # Four entries for one ruling, one per reader of the old offset, because a
    # single signature would authorise whichever hunk difflib happened to draw
    # around it. Weakness #2 of this ledger, paid for rather than argued with.
    #
    # These lines land INSIDE hunks that were already authorised, which is
    # weakness #3: a modification to an already-added line changes neither the
    # added nor the removed count for THAT line, so nothing but the budget saw
    # this change coming. The budget is what caught it, and these entries are
    # what make it matchable afterwards.
    ('X1', 'exact_date is a date operation. The mode did raw J−X with the '
           'weekday snap turned off — a third thing, neither of the two its '
           'label names — and rendered bordeaux_oct identically to Jour J. '
           '`anchorOf` now returns the whole mode: both grains, the labels and '
           'the cut, mirroring dashboard_payload.Align',
     'refJx: jx => evd - calShift(evo - jx, -N),'),
    ('X2', 'exact_date: the calendar shift itself, mirroring '
           'dashboard_payload.cal_shift. 29 February -> 28 February, and the '
           'month is checked rather than trusted because Date.UTC rolls 29 Feb '
           'into 1 March on a common year instead of throwing',
     'const calShift = (dn, n) => {'),
    ('X3', 'exact_date: the weekly grain maps the reference day FORWARD N '
           'calendar years and buckets it by OUR event, so the reference bucket '
           'is our bucket by construction. This is the departure from '
           'reference_suivi_candidates.py, amended in the same commit',
     'weekOf: jr => Math.floor((evo - calShift(evd - jr, N)) / 7),'),
    ('X4', 'exact_date: the no-overlap empty state, naming the side that ran '
           'out. Two campaigns lined up by calendar date can miss each other '
           'entirely — 19 of 66 pairs today — and a generic "aucune donnée" '
           'would be indistinguishable from a fetch that failed',
     "${gapShown ? `<div class=\"empty\" style=\"margin:12px 0\">"),
    ('X5', 'RULED: the banner fires on what the READER CAN SEE, not on whether '
           'the table has any matched row at all. rennes vs Bordeaux Juin 2026 '
           'has twelve matched rows, every one of them behind "Voir les 60 '
           'jours precedents", so the visible table was em-dashes with no '
           'explanation - indistinguishable from a broken comparison and worse '
           'than the state that HAS a banner, because it looks like data. '
           'Suppressed where the live-edition sentence already explains the '
           'same em-dashes: two rules correct alone are wrong where they meet, '
           'and the note naming the CAUSE wins over the one naming the symptom',
     "const gapShown = HAS_CMP && !CMPERR && CMPGAP && !liveNoted"),
    ('X6', 'RULED: NO COUNTERPART, NO DIFF. `r.a - r.b` coerced null to 0, so a '
           'row with no reference rendered "+134" in green - a number that '
           'looks like a comparison and is a restatement of one side. Third '
           'instance of null coercing to zero in a rendered figure after '
           'nf(null) printing 0 and a live candidate future rendering 0; both '
           'were ruled fixes. The guard is `!= null` and NOT falsy: `b === 0` '
           'is a REAL zero (a day inside the covered range before the '
           'candidate opened) whose diff is honest arithmetic - 49 of the 90 '
           'blank-looking rows on epk vs bordeaux_oct_2026 - and em-dashing '
           'those would delete a legitimate comparison to fix a different bug. '
           'THE COUNT IS PER CANDIDATE, NOT PER PAGE, and saying so matters '
           'because opening epk shows almost none: on its DEFAULT candidate '
           '(epk_2023, 261 days of history) it is 1 lived row of 130. Switch '
           'candidate and it is 62 for rennes_2026, 41 for bordeaux_oct_2026, '
           '41 for geneve_2026. So it is not a mode problem and not a '
           'default-view problem - B1 made it reachable at scale by putting '
           'eleven candidates in that menu, and one click reaches it with no '
           'exact_date involved',
     "const dif = r => r.b == null ? null : r.a - r.b;"),
    # ---- (b) control labels on both cards --------------------------------
    ('X9', 'EVERY CONTROL GETS A TITLE ABOVE IT, and both cards get the same '
           'pair stacked: the dropdown says WHICH, the title says WHAT IT IS. '
           '`.kc-k` is REUSED rather than a new rule invented - it is the '
           'uppercase letterspaced --text-muted key label already above every '
           'KPI value, the same relationship, and it already carries the 5px '
           'bottom margin that relationship needs. The redesign invents no CSS; '
           'searching the mock before writing a rule is the standing rule and '
           'this is what the search found',
     'function ctl(title, inner){'),
    ('X9-decl', 'ctl is a DECLARATION, not a const arrow, and that is not '
                'style. The renderers run during script execution, some of them '
                'BEFORE that line, so a const put it in the temporal dead zone '
                'and the whole Suivi card rendered EMPTY - innerHTML length 0 '
                'and one console error, with the Projection half working. A '
                'declaration hoists so position stops mattering. Found by '
                'RENDERING the page: reading it would not have shown a blank '
                'card',
     '  return `<div class="ctl-stack"><div class="kc-k">${title}</div>${inner}</div>`;'),
    ('X10', 'the four .cmp-eyebrow labels come out - réf., scén., vs, aligné '
            'sur. With a title above each control they say the same thing '
            'twice. MEASURED, because the handoff asked whether losing them '
            'would rescue the long form at 393: it does NOT. '
            '"Trajectoire Rennes 2025" truncates in .cmp-name at 393 '
            'identically before and after, so the copy question survives and '
            'still needs a ruling',
     '<span class="cmp-name">${CSEL}</span>'),
    ('X11', 'Suivi renders the candidate BEFORE the alignment, matching '
            'Projection. The ruling is that the first label is the same on both '
            'cards because it is the same choice; the existing order had them '
            'opposite - Projection comparatif/méthode, Suivi alignement/'
            'comparatif - which only shows once both carry titles',
     '<div class="svctl-p">${cmpMenu()}${modeMenu()}</div>'),
    ('X12', 'the two "Événement comparatif" call sites - Projection\'s menu() '
            'and Suivi\'s cmpMenu(). ONE entry covers both, and that is the '
            'same D15 caveat as X6: the line is identical in the two because '
            'it is the same label naming the same choice, which is the whole '
            'ruling. Source is not reshaped to give an entry its own diff',
     "return ctl('Événement comparatif', `<div class=\"sw-wrap\""),
    ('X14', 'THE COLUMN HEADERS NAME THE ALIGNMENT THAT IS ON. They read '
            '"2025 (même jour)" against "2026 (actuel)" whichever of the three '
            'the picker had - already wrong under Ouverture, where the '
            'correspondence is the same campaign DAY and not the same day, and '
            'worse under Date exacte at N=0, where it rendered "2026 (MÊME '
            'JOUR)" against "2026 (ACTUEL)": two identical years labelled as '
            'opposites, directly above a sentence saying both sides are the '
            'same date. THE YEAR STOPS BEING AN IDENTIFIER when both sides are '
            '2026, so the reference column falls back to naming the EDITION - '
            'which is what the reader picked anyway. Five of eleven candidates '
            'on every page are N=0',
     'function hdrRef(future){'),
    ('X14-fut', 'the À VENIR header too. Its own entry because it is a separate '
                'line that could be reverted alone, leaving the lived rows '
                'naming the alignment and the future rows still saying "2023 '
                '(référence)" - half-fixed reads as fixed',
     "H(hdrRef(true),'J−X',YC + ' (à venir)') +"),
    ('X14-w', 'the alignment word itself, its own entry because it is the part '
              'a later reader would edit',
     "function alignWord(){"),
    ('X13', 'RULED: the projection method labels lose the edition name - '
            '"Trajectoire", not "Trajectoire Rennes 2025". That form truncated '
            'at 393, and the measurement is what settled it: removing the four '
            '.cmp-eyebrow labels did NOT buy back enough width, so the copy '
            'question did not disappear on its own. The name is not lost, it is '
            'de-duplicated - `Événement comparatif` now names the edition once, '
            'directly above, where the trigger was saying it a second time. '
            'Measured after: no truncated element at 393 or desktop',
     "const L = ['Trajectoire', '× coef. vélocité'];"),
    ('X12b', 'and the matching close, where the trigger template now ends '
             'inside ctl() rather than at the return',
     '</div></div>`);'),
    ('X10-ref', 'the `réf.` eyebrow specifically. A PURE DELETION, so it is '
                'matched against the LOCKED side - the other three eyebrows sit '
                'in hunks that also add a line and are covered there. Its own '
                'entry because it is the one whose removal was supposed to buy '
                'width back at 393, and a silent revert would restore the '
                'truncation this measured',
     '<span class="cmp-eyebrow">réf.</span>'),
    ('X7', 'THE SUIVI ALIGNMENT SENTENCE, four variants driven by CSEL and '
           'AMODE. It replaces "l\'alignement s\'applique aux deux grains", a '
           'line that could never have been wrong because it made no claim the '
           'table could contradict - which is why exact_date shipped doing '
           'something else for weeks under it. The new line says "9 aout 2026 '
           'contre 9 aout 2025" directly above a column showing those dates, so '
           'a reader can falsify it at a glance. Writing the sentence is what '
           'found five defects in that mode; the sentence IS the test. The old '
           '"both grains move together" line is DROPPED rather than moved to '
           'the tooltip - it answers a question only reachable by noticing a '
           'disagreement the per-row design can no longer produce',
     'function alignNote(){'),
    ('X7-fmt', 'full French month names for the sentence. The mock carries only '
               'the abbreviated MOS ("aou"), which is right for a table cell '
               'and wrong in prose',
     "const MOSL = ['janvier','février','mars','avril','mai','juin','juillet','août',"),
    ('X8', 'the live-edition sentence becomes j_minus ONLY. It used to show '
           'under exact_date too, where its reason is the wrong one: a calendar '
           'alignment does not miss because the candidate J-x has not arrived. '
           'Under exact_date a live candidate is necessarily a 2026 edition, so '
           'N = 0, and the alignment sentence already says what the comparison '
           'is; where the campaigns genuinely miss each other the gap banner '
           'names the side that ran out. The exact_date variant of this '
           'sentence is ABSENCE, not different wording',
     "        && AMODE === 'j_minus')"),
    ('X6-head', 'the dRow/wRow head reading through `dif`. ONE ENTRY COVERS BOTH '
                'FUNCTIONS and D15 warns against exactly that - but the line is '
                'character-for-character identical in the two, because the change '
                'IS the same change, and the boundary this project draws is that '
                'source is not reshaped to give an entry its own diff. The line '
                'budget is what bounds it; this note is what makes the gap '
                'visible instead of silent',
     "const d = dif(r), p = r.b ? (r.a - r.b)/r.b*100 : 0;"),
    ('X6-cell', 'the diff CELL, in both dRow and wRow, for the same reason and '
                'with the same caveat as X6-head',
     ": `${difCell(d)}"),
    ('C1', 'the billetterie section bar indexes EVERY section - six tabs in '
           'section order, relabelled. Ruled as a rule rather than a chosen '
           'set: one tab per section is something a later reader can apply. '
           'The relabel is a width GAIN - four long labels needed 382, six '
           'short ones need 401 - and C1a pays the difference',
     "scrollToSection('sec-velocite',this)"),
    ('C2', 'the same bar on Détails, where there was none: goPage hid the only '
           'bar off billetterie and now selects between two. NEW BEHAVIOUR, '
           'not a relabel - the before-shot is an empty strip. Both bars stand '
           'in the markup rather than in JS template strings, so the page\'s '
           'own markup does not move inside a literal',
     'data-bar="details"'),
    ('C2b', 'the scroll-spy is DERIVED from the buttons. It carried its own '
            'ids array and matched by INDEX, so a tab added anywhere but the '
            'end highlighted the wrong section; with six tabs and a second bar '
            'that would have been three places stating one list. Derived, C2 '
            'gets the spy for free',
     'var tgt = new Map();'),
    ('C2d', 'C2 - goPage selects a bar instead of hiding the only one. Its '
            'own entry because the OLD line is what a reader needs to see: the '
            'Détails page having no bar at all was a behaviour, not an '
            'oversight',
     "t.style.display = (t.dataset.bar===pg)"),
    ('C2e', 'C2b - the spy matches by IDENTITY rather than by list index, '
            'which is the half of the derivation that actually fixes the bug: '
            'an index match against a derived list is still wrong the moment a '
            'tab is inserted anywhere but the end',
     'var b=tgt.get(e.target.id); if(!b) return;'),
    ('C2c', 'scrollToSection scoped to the button\'s own bar. With two bars in '
            'the markup, clearing every .dt wipes the hidden bar\'s active tab',
     "var bar = btn && btn.closest('.dept-tabs');"),
    ('AN1', 'anchoring - live editions now get series files, so four of the '
            'twelve are rewritten daily and {cache:no-cache} stops being '
            'hygiene. The reason is recorded at the fetch because that is where '
            'someone would delete the flag. Its own entry even though the '
            'signature `async function pickCmp(n)` already covered the hunk - '
            'which is exactly the hole the line budget closes',
     'no-cache is LOAD-BEARING'),
]


def check_pages():
    """The shipped `<style>` may differ from the file ONLY by PAGE_PATHS.

    Returns a list of failure strings. PAGE_PATHS is imported rather than
    restated: the substitutions are location-dependent - `../upload.JPG` is
    right under /v2/ and wrong at the root - so a second copy here would go
    stale at cutover and disagree with the build silently.
    """
    pages = v2_pages()
    if not pages:
        # Not a silent pass: say which property is unverified and why.
        print('\nno pages under v2/ - the file-vs-page assertion did not run')
        return []

    try:
        from build_v2 import PAGE_PATHS, login_bg_by_page, style_transforms
    except Exception as exc:                                # pragma: no cover
        print(f'\nFAIL  cannot import build_v2 transforms: {exc}')
        return ['build_v2 transforms unavailable']

    css = WORK_CSS.read_text(encoding='utf-8')
    # PAGE_PATHS is page-wide and, since P3, touches nothing in the sheet. It is
    # still applied here rather than dropped: the claim is "the file through
    # exactly the transforms build_v2 declares", and a future entry that DOES
    # hit CSS should be covered the day it lands, not the day someone remembers.
    base = css
    for old, new in PAGE_PATHS:
        base = base.replace(old, new)

    # P3. The login background is per EVENT, so the expected stylesheet is per
    # PAGE. Resolved from event_config here and from the built artefact in
    # build_v2 - two routes to one value, and this failing is what says they
    # disagree. A single `want` computed once would have had to pick one page's
    # background and call it every page's.
    bgs = login_bg_by_page()
    print(f'\nshipped <style> vs the file, through {len(PAGE_PATHS)} page '
          f'substitution(s) + the per-page login background:')
    failures = []
    for page in pages:
        bg = bgs.get(page.name)
        if bg is None:
            failures.append(f'{page.name}: no config row')
            print(f'  FAIL  {page.name}: no event_config row owns this filename, '
                  f'so its login background cannot be derived')
            continue
        want = base
        for old, new in style_transforms(bg):
            want = want.replace(old, new)
        want = '\n' + want + '\n'            # the exact wrapper pass 0 writes

        blocks = STYLE_RE.findall(page.read_text(encoding='utf-8'))
        if len(blocks) != 1:
            failures.append(f'{page.name}: {len(blocks)} <style> blocks')
            print(f'  FAIL  {page.name}: {len(blocks)} <style> block(s), want 1')
            continue
        if blocks[0] == want:
            print(f'  ok    {page.name}  (login bg {bg})')
            continue
        failures.append(f'{page.name}: inlined style is not the file')
        print(f'  FAIL  {page.name}: the inlined stylesheet is NOT the file put')
        print('        through PAGE_PATHS. Something transforms the CSS between')
        print('        the file and the page, and nothing else checks that:')
        diff = [l for l in difflib.unified_diff(
            want.split('\n'), blocks[0].split('\n'), lineterm='', n=0)
            if l[:1] in '+-' and not l.startswith(('+++', '---'))]
        for line in diff[:6]:
            print(f'          {line[:104]}')
        if len(diff) > 6:
            print(f'          ... {len(diff) - 6} more')
    return failures



def _carried_block(prod_css, _norm):
    """The page-footer block from production's sheet, normalised, as one run.

    Located by its own comment banner rather than by line numbers, so an edit
    above it in production's sheet does not silently change what is carried.
    Returns '' if the banner is gone - which fails the carry rather than
    passing an empty block, because a block that cannot be found is a block
    that cannot be checked.
    """
    start = prod_css.find('/* \u2550\u2550\u2550 page footer \u2550\u2550\u2550 */')
    if start < 0:
        return ''
    end = prod_css.find('\n/*', start + 1)
    return _norm(prod_css[start:end if end > 0 else len(prod_css)])

def main():
    for p in (LOCK_HTML, WORK_HTML, LOCK_CSS, WORK_CSS):
        if not p.exists():
            print(f'FAIL: {p.relative_to(ROOT)} is missing.')
            if 'locked' in str(p):
                print('      The locked copy is the reference. Without it nothing')
                print('      here can be checked - restore it from the original upload.')
            return 1

    failures = []

    # ---- the stylesheet may differ ONLY by carried-across .db-* rules ----
    #
    # NOT relaxed generically. The property worth protecting was never byte
    # identity - it was "the redesign invents no CSS". The auth-overlay rules
    # are not inventions: they are carried VERBATIM from dashboard_v6_8.css, and
    # the locked mock has no auth overlay at all, so they were never mock
    # deviations. Anything else - an added line, a modified one, a .db-* rule
    # whose text does not match production's - still fails.
    def _decomment(s):
        # Comments carry the RATIONALE for the carry-across and are meant to be
        # there; comparing them line-by-line would flag prose as invented CSS.
        return re.sub(r'/\*.*?\*/', '', s, flags=re.DOTALL)

    lock_css = _decomment(LOCK_CSS.read_text(encoding='utf-8'))
    work_css = _decomment(WORK_CSS.read_text(encoding='utf-8'))
    prod_css = (ROOT / 'style' / 'dashboard_v6_8.css').read_text(encoding='utf-8')
    added, removed = [], []
    for line in difflib.unified_diff(lock_css.split('\n'), work_css.split('\n'),
                                     lineterm='', n=0):
        if line.startswith('+++') or line.startswith('---') or line.startswith('@@'):
            continue
        if line.startswith('+'):
            added.append(line[1:])
        elif line.startswith('-'):
            removed.append(line[1:])

    def _norm(s):
        return re.sub(r'\s+', '', s)

    # Ruling-authorised line edits come out of the diff first, in BOTH
    # directions - the old line must be gone and the new one present. A
    # deviation that is only half there is a broken edit, not a passing one.
    for cid, why, old_line, new_line in AUTHORISED_CSS:
        # A RIDER: a decision that lands on a line another entry already owns,
        # because the sheet declares several things in one declaration. It gets
        # an id and a reason but no diff of its own - splitting the CSS line to
        # give it one would shape the stylesheet around this file, which is
        # backwards. Recorded rather than merged into the owning entry, so the
        # decision is findable by name.
        if old_line == new_line and str(old_line).startswith('__') and str(old_line).endswith('__'):
            print(f'ok    {cid}  (rider) {why}')
            continue
        # `old_line is None` authorises a pure ADDITION - the mirror of the
        # deletion below, and the fifth shape this list has needed. A ruled
        # LAYOUT change adds rules; it does not edit existing ones. Without
        # this the only ways to ship one were an inline style in the markup
        # (which puts layout where nobody looks for it) or loosening the
        # invented-CSS check (which is the assertion, not a detail).
        #
        # Still bounded: the added line must be ABSENT from locked and PRESENT
        # in working, so a listed addition that gets reverted fails exactly like
        # a listed edit that does.
        if old_line is None:
            if new_line in added:
                added.remove(new_line)
                print(f'ok    {cid}  (addition) {why}')
            else:
                failures.append(f'{cid} not applied as ruled')
                print(f'FAIL  {cid}: authorised ADDITION, but the line is absent')
                print(f'        want +{new_line.strip()!r}')
                print(f'        {why}')
            continue
        # `new_line is None` authorises a pure DELETION. A rule can be wrong by
        # existing - the two `#sec-suivi .card-header` rules were written for
        # markup the mock never produced and were unreachable for months - and
        # this list had no way to say so, because it demanded a replacement.
        # Same shape as the deletion half of the mock's own ledger.
        if new_line is None:
            if old_line in removed and old_line not in added:
                removed.remove(old_line)
                print(f'ok    {cid}  {why}')
            else:
                failures.append(f'{cid} not applied as ruled')
                print(f'FAIL  {cid}: authorised DELETION, but the line is '
                      f'{"still present" if old_line not in removed else "re-added"}')
                print(f'        want gone: {old_line.strip()!r}')
                print(f'        {why}')
            continue
        if old_line in removed and new_line in added:
            removed.remove(old_line)
            added.remove(new_line)
            print(f'ok    {cid}  {why}')
        else:
            failures.append(f'{cid} not applied as ruled')
            print(f'FAIL  {cid} is not applied as ruled: '
                  f'locked line {"removed" if old_line in removed else "STILL THERE"}, '
                  f'replacement {"added" if new_line in added else "MISSING"}')
            print(f'        want -{old_line.strip()!r}')
            print(f'        want +{new_line.strip()!r}')
            print(f'        {why}')

    prod_norm = _norm(prod_css)
    # `.pgf-*` / `.pg-footer` joins `.db-*` as carried-across production chrome:
    # v2 shipped an EMPTY #foot and therefore no footer at all, and production's
    # markup was transplanted rather than the mock's .foot/.fi design being
    # wired up, because stamp_footer.py matches on the .pgf-item structure.
    # The block is carried as ONE CONTIGUOUS RUN, so its continuation lines and
    # its @media wrapper - which start with neither prefix - are covered by
    # membership in the run rather than by a per-line prefix test.
    CARRIED = ('.db-',)
    foot_block = _carried_block(prod_css, _norm)
    if foot_block and foot_block in _norm(WORK_CSS.read_text(encoding='utf-8')):
        added = [a for a in added if _norm(a) not in foot_block or not _norm(a)]
    stray = [a for a in added
             if a.strip()
             and not (a.lstrip().startswith(CARRIED) and _norm(a) in prod_norm)]
    if removed:
        failures.append(f'stylesheet: {len(removed)} line(s) REMOVED from locked')
        print(f'FAIL  stylesheet removes {len(removed)} line(s) from locked - '
              f'the carry-across is additive only')
    if stray:
        failures.append(f'stylesheet: {len(stray)} line(s) not carried from production')
        print('FAIL  stylesheet lines that are neither locked nor verbatim from')
        print('      dashboard_v6_8.css - i.e. invented:')
        for s in stray[:5]:
            print(f'        {s[:100]}')
    if not removed and not stray:
        n_db = sum(1 for a in added if a.lstrip().startswith('.db-'))
        print(f'ok    stylesheet: locked + {n_db} .db-* rule(s) carried verbatim '
              f'from dashboard_v6_8.css, nothing invented')

    # ---- the mock's hunks must each be authorised ----
    lock = LOCK_HTML.read_text(encoding='utf-8').split('\n')
    work = WORK_HTML.read_text(encoding='utf-8').split('\n')
    hunks = [op for op in difflib.SequenceMatcher(None, lock, work).get_opcodes()
             if op[0] != 'equal']
    print(f'\n{len(hunks)} hunk(s) between locked and working mock:')

    matched = {}
    for tag, i1, i2, j1, j2 in hunks:
        added = '\n'.join(work[j1:j2])
        # BOTH SIDES. A pure DELETION has nothing on the working side, so its
        # signature can only match what was REMOVED - D21 deleted `const LG`
        # outright and this could not have described it.
        #
        # It used to read `added if j2 > j1 else removed`, i.e. the removed side
        # ONLY for a pure deletion. That made an entry's matchability depend on
        # its NEIGHBOURS: adding one `</div>` two lines away turned a pure
        # deletion hunk into a replace hunk, the haystack flipped to the added
        # side, and C3-campagne reported as "an approved change someone
        # reverted" about a deletion that was still there. Searching both sides
        # removes that coupling; the line budget is what bounds the total, so
        # nothing is lost by being permissive here.
        haystack = added + '\n' + '\n'.join(lock[i1:i2])
        # EVERY signature present, not the first one. `next()` credited one
        # entry per hunk, so a second authorised deviation inside the same hunk
        # - which happens the moment two rulings touch one region, and difflib
        # decides where the regions are - read as MISSING: "an approved change
        # someone reverted", about a change that was right there. The hunk was
        # never the unit of authorisation; the deviation is.
        hits = [a for a in AUTHORISED if a[2] in haystack]
        if hits:
            for hit in hits:
                matched.setdefault(hit[0], 0)
                matched[hit[0]] += 1
                print(f'  ok    {hit[0]}  {hit[1]}')
        else:
            failures.append(f'unauthorised hunk at working line {j1 + 1}')
            print(f'  FAIL  UNAUTHORISED hunk at working line {j1 + 1}:')
            for line in work[j1:j2][:3]:
                print(f'          + {line.strip()[:104]}')

    # ---- the line budget: a signature must not authorise its neighbours ----
    # A signature authorises a HUNK, and difflib's hunks are as large as the
    # surrounding churn makes them. The B1 block is one `replace` of 154 added
    # lines matched by the 25 characters `async function pickCmp(n)` - 42% of
    # every added line in the mock, riding on one substring. Found by adding a
    # five-line comment inside it and watching the check pass.
    #
    # So the signatures say WHICH deviations are present, and this says HOW MUCH
    # deviation there is. Any unlisted line inside an already-authorised hunk
    # moves the number and fails, whatever it says and wherever it sits.
    #
    # Deliberately ONE pair of numbers rather than a count per entry: a count per
    # entry is a second place to state something the diff already knows, and it
    # would need re-stating every time hunks merge - which has happened five
    # times. Coarse, and it cannot be silently ridden. Raising it IS the act of
    # authorisation, so a ruling that adds lines changes two things in one
    # commit: an entry, and this number.
    n_add = sum(j2 - j1 for _, _, _, j1, j2 in hunks)
    n_rem = sum(i2 - i1 for _, i1, i2, _, _ in hunks)
    if (n_add, n_rem) != (BUDGET_ADDED, BUDGET_REMOVED):
        failures.append(f'line budget {n_add}/{n_rem}, want '
                        f'{BUDGET_ADDED}/{BUDGET_REMOVED}')
        print(f'\n  FAIL  line budget: {n_add} added / {n_rem} removed, '
              f'want {BUDGET_ADDED} / {BUDGET_REMOVED}')
        print(f'        Something changed inside a hunk that was already')
        print(f'        authorised, so no signature had to match it. The'
              f' largest')
        big = sorted(hunks, key=lambda h: h[4] - h[3], reverse=True)[:3]
        for tag, i1, i2, j1, j2 in big:
            print(f'        hunks start at working line {j1 + 1} '
                  f'({j2 - j1} added) - look there first.')
        print(f'        If this is an approved change, raise the budget in the')
        print(f'        same commit as the ledger entry.')
    else:
        print(f'\nok    line budget: {n_add} added / {n_rem} removed, exactly '
              f'as authorised')

    missing = [a for a in AUTHORISED if a[0] not in matched]
    if missing:
        print('\nauthorised deviations NOT present — an approved change was reverted:')
        for mid, why, _ in missing:
            failures.append(f'{mid} missing')
            print(f'  FAIL  {mid}  {why}')

    failures += check_pages()

    print()
    if failures:
        print(f'FAILED: {len(failures)}')
        print('An unauthorised hunk is an invention and goes back to Leo. A missing')
        print('one is an approved change that was reverted. Neither is a detail.')
        return 1
    print(f'working mock differs from locked in exactly the {len(AUTHORISED)} '
          f'authorised ways')
    return 0


if __name__ == '__main__':
    sys.exit(main())
