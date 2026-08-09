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
    ('D24', "D6 - overflow-x: clip instead of hidden. `hidden` makes body a "
            "SCROLL CONTAINER, so the sticky nav positioned against body and "
            "scrolled away with it: -353px after 1500px, on BOTH heads, with a "
            "position:sticky rule that was present and correct the whole time. "
            "`clip` clips the same overflow without creating a scroll "
            "container. Measured, not reasoned: hidden -353, clip 0, visible 0",
     "html,body{overflow-x:hidden;min-height:100%;background:var(--bg);",
     "html,body{overflow-x:clip;min-height:100%;background:var(--bg);"),
]

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
    ('D26', 'fm() asks the formatter for the compact form instead of editing '
            'the full one. It stripped trailing digits and appended its own '
            'abbreviation, correct while eur() ended in digits; D1 moved the '
            'symbol to the end, so the strip matched nothing and the append '
            'still ran - "593 421 EUR593k", one figure twice, in a 50px '
            'gutter. Both of Leo\'s chart reports were this one function',
     'ASK THE FORMATTER, DO NOT EDIT ITS OUTPUT'),
    ('D26b', 'D26 - the revenue chart passes k, the compact formatter, so there '
             'is no string left to operate on',
     'k, not eur: the axis and the readout want the compact form'),
    ('D26c', 'D26 - the second line of the same call, which the diff splits',
     "weeklySeries(past,'rcb') : [], k);"),
    ('D27', 'D1(b) - the readout labels the unlabelled figure and separates the '
            'two values, in Leo\'s words: "Tickets" and a middle dot. Uses '
            '.kc-s, the legend\'s own class, so no CSS is invented',
     'kc-s">Tickets<'),
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
        hit = next((a for a in AUTHORISED if a[2] in haystack), None)
        if hit:
            matched.setdefault(hit[0], 0)
            matched[hit[0]] += 1
            print(f'  ok    {hit[0]}  {hit[1]}')
        else:
            failures.append(f'unauthorised hunk at working line {j1 + 1}')
            print(f'  FAIL  UNAUTHORISED hunk at working line {j1 + 1}:')
            for line in work[j1:j2][:3]:
                print(f'          + {line.strip()[:104]}')

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
