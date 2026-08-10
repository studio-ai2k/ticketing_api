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
            "Détails room for the next section instead of 2px",
     ".dt { padding: 8px 12px; font-size:var(--fs-tiny); font-weight: 500; color: var(--text-dim); white-space: nowrap; border: none; border-bottom: 2px solid transparent; background: none; font-family: inherit; cursor: pointer; transition: color .15s; }",
     ".dt { padding: 8px 10px; font-size:var(--fs-tiny); font-weight: 500; color: var(--text-dim); white-space: nowrap; border: none; border-bottom: 2px solid transparent; background: none; font-family: inherit; cursor: pointer; transition: color .15s; }"),
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
BUDGET_ADDED = 609
BUDGET_REMOVED = 158

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
             "the desktop size it was just reduced below",
     "  .ck-va,.ck-vb{font-size:var(--fs-micro)}",
     "  .ck-va,.ck-vb{font-size:var(--fs-tiny)}"),
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
    ('AN5', 'anchoring - the one line of copy: the alignment governs both '
            'grains. The launch clause is conditional because the em-dash note '
            'is only true in that mode',
     'L’alignement s’applique aux deux grains'),
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
                     'reader would notice missing',
     'style="margin-left:8px">En vente'),
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
    pages = sorted(V2.glob('*.html'))
    if not pages:
        # Not a silent pass: say which property is unverified and why.
        print('\nno pages under v2/ - the file-vs-page assertion did not run')
        return []

    try:
        from build_v2 import PAGE_PATHS
    except Exception as exc:                                # pragma: no cover
        print(f'\nFAIL  cannot import build_v2.PAGE_PATHS: {exc}')
        return ['build_v2.PAGE_PATHS unavailable']

    css = WORK_CSS.read_text(encoding='utf-8')
    want = css
    for old, new in PAGE_PATHS:
        want = want.replace(old, new)
    want = '\n' + want + '\n'                # the exact wrapper pass 0 writes

    print(f'\nshipped <style> vs the file, through {len(PAGE_PATHS)} known '
          f'substitution(s):')
    failures = []
    for page in pages:
        blocks = STYLE_RE.findall(page.read_text(encoding='utf-8'))
        if len(blocks) != 1:
            failures.append(f'{page.name}: {len(blocks)} <style> blocks')
            print(f'  FAIL  {page.name}: {len(blocks)} <style> block(s), want 1')
            continue
        if blocks[0] == want:
            print(f'  ok    {page.name}')
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
        if old_line == new_line == '__C3i_rides_on_C3c__':
            print(f'ok    {cid}  (rider) {why}')
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
    stray = [a for a in added
             if a.strip()
             and not (a.lstrip().startswith('.db-') and _norm(a) in prod_norm)]
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
        # A pure DELETION has nothing on the working side, so a signature can
        # never match there. Match it against what was REMOVED instead - D21
        # deleted `const LG` outright and this could not have described it.
        haystack = added if j2 > j1 else '\n'.join(lock[i1:i2])
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
