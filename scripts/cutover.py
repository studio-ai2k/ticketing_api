#!/usr/bin/env python3
"""
The cutover, as one runnable step. Reports by default; writes only with --apply.

    python3 scripts/cutover.py              # dry run, writes nothing
    python3 scripts/cutover.py --apply      # completes, or leaves the tree untouched

WHY A SCRIPT AND NOT A SEQUENCE OF COMMANDS
--------------------------------------------
CUTOVER.md §5's central assertion is available ONCE: the first post-cutover root
pages must equal the v2 pages they replace, and the v2 pages stop existing the
moment they are replaced. A sequence of commands with a look between each means
pausing with `legacy/` half-built, which is a state nobody has specified and
nobody can review. So: either every step succeeds and the tree moves, or nothing
is written at all.

The dry run exists so the looking still happens, before anything is at stake. It
builds the post-cutover pages in a temporary directory, reports the byte-diff of
each against its v2 counterpart, prints the single stamp line it expects to
differ, and prints the six SHA-256 hashes destined for the archive README.

TWO CORRECTIONS TO THE PLAN, BOTH FOUND BY BUILDING AGAINST IT
---------------------------------------------------------------
1. §5 says the one differing line will match `postprocess_html.STAMP_RE`. **It
   will not.** That section was written before P1 existed; a v2 page carries
   `<!-- shared-v2:… -->`, and `STAMP_RE` matches only the production
   `<!-- shared:… -->` form. Measured: `STAMP_RE.search(v2/rennes.html)` is
   None, `V2_STAMP_RE.search(...)` matches. Asserting the named regex would have
   failed every page at the one moment the comparison cannot be re-run.

2. §3(a) says `PAGE_PATHS` becomes `[]` because at root the correct output is
   the input. True, and it is no longer the whole edit: **P3 added a SECOND
   location-dependent transform** after §3(a) was written. `style_transforms`
   emits `url('../<bg>')`, and at root the right answer is `url('<bg>')` - not
   the identity, and not the pre-P3 constant either. The section's own warning
   applies to itself: `PAGE_PATHS` was never the complete list of
   location-dependent transforms, only the complete list of path ones.

WHAT --apply DOES, IN ORDER
----------------------------
    1. refuse unless the tree is clean and every config page exists in v2/
    2. snapshot the six v2 pages IN MEMORY, before anything is edited
    3. hash the six CURRENT root pages - the archive's provenance record,
       taken BEFORE the banner (§6.2)
    4. build the post-cutover root pages into a temp dir
    5. assert, per page: exactly ONE differing line against the v2 snapshot
       stripped of `../`, and that line is the v2 build stamp
    6. only then write: legacy/ (six frozen pages + banners + README), the six
       new root pages, and the build_v2 edit

Any failure before step 6 leaves the working tree exactly as it was found.
"""

import argparse
import difflib
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / 'scripts'))

import build_v2                                    # noqa: E402
from pages import page_names                       # noqa: E402

BANNER_ID = 'cutover-archive-banner'


def rel(p):
    try:
        return p.relative_to(BASE_DIR)
    except ValueError:
        return p


def git(*args):
    return subprocess.run(['git', '-C', str(BASE_DIR), *args],
                          capture_output=True, text=True)


# THE EDIT, DECLARED ONCE. It drives three things that must agree: the stamp the
# dry run PREDICTS, the stamp --apply produces, and the source --apply writes. A
# dry run that models the edit loosely is a dry run that approves something else.
PAGE_PATHS_OLD = """PAGE_PATHS = [
    ('src="LOGO_ROND_JAUNE.png"', 'src="../LOGO_ROND_JAUNE.png"'),
    # B1's series files. Third asset class to go one directory deep, and the
    # only one that would fail at RUNTIME rather than at first paint - a broken
    # image is obvious, a fetch that 404s renders as "comparaison indisponible"
    # on every pick. Emitted as a root-relative template and rewritten here.
    ('"series/{id}.json"', '"../series/{id}.json"'),
]"""
PAGE_PATHS_NEW = """# CUTOVER §3(a): DELETED, not made conditional. Every entry rewrote a
# root-relative original into a `../` form, and the pages now land at root - so
# the correct output IS the input and the loop is identity. An empty list kept
# "for later" is a location-dependence nobody can see any more.
PAGE_PATHS = []"""
STYLE_OLD = """    return [(f"url('{SHEET_LOGIN_BG}')", f"url('../{login_bg}')")]"""
STYLE_NEW = """    # CUTOVER §3(a), second half: the `../` goes with the move to root. P3 added
    # this transform AFTER §3(a) was written, so the section's list of
    # location-dependent transforms did not include it - see that section's own
    # warning that PAGE_PATHS was never the complete list.
    return [(f"url('{SHEET_LOGIN_BG}')", f"url('{login_bg}')")]"""


def cutover_edit(src):
    """build_v2.py as the cutover leaves it. Asserts each site matches once."""
    for old, new in ((PAGE_PATHS_OLD, PAGE_PATHS_NEW), (STYLE_OLD, STYLE_NEW)):
        n = src.count(old)
        if n != 1:
            raise SystemExit(
                f'cutover: the edit site matched {n} time(s), want 1. '
                f'build_v2.py has moved under this script, and a cutover that '
                f'edits the wrong text is worse than one that refuses.\n'
                f'  looking for: {old.splitlines()[0][:70]}...')
        src = src.replace(old, new)
    return src


def predicted_stamp():
    """The v2 stamp AFTER the edit, computed from the edited source.

    build_v2.py is in V2_SHARED_ASSETS and the cutover edits it, so the stamp
    moves for a legitimate reason at the one moment the comparison exists. §5
    calls that the failure most likely to be waved through as "that's just the
    stamp" - so it is predicted here, exactly, and then asserted.
    """
    import hashlib as _h
    h = _h.sha256()
    edited = cutover_edit((BASE_DIR / 'scripts' / 'build_v2.py')
                          .read_text(encoding='utf-8')).encode()
    for rel_path in build_v2.V2_SHARED_ASSETS:
        f = BASE_DIR / rel_path
        h.update(rel_path.encode())
        if rel_path == 'scripts/build_v2.py':
            h.update(edited)
        else:
            h.update(f.read_bytes() if f.exists() else b'<absent>')
    return f'<!-- shared-v2:{h.hexdigest()[:12]} -->'


def to_root(html, login_bg):
    """A v2 page as it should look built at root: every `../` prefix gone.

    Derived from the declarations rather than from a list of literals - the same
    reason `check_pages` imports them. Then asserted, because a substitution
    that silently matched nothing is how this class of change goes wrong.
    """
    subs = list(build_v2.PAGE_PATHS) + list(build_v2.style_transforms(login_bg))
    out, moved = html, 0
    for old, new in subs:
        if new in out:
            moved += out.count(new)
            out = out.replace(new, old.replace("url('upload.JPG')",
                                               f"url('{login_bg}')")
                              if old.startswith("url(") else old)
    if '../' in out:
        raise SystemExit(
            f'cutover: {out.count("../")} `../` left after stripping the '
            f'declared transforms. §5 asserts zero in a built root page, so '
            f'something is location-dependent that nothing declares.')
    return out, moved


def stamp_line(html):
    m = build_v2.V2_STAMP_RE.search(html)
    return m.group(0) if m else None


def build_root_pages(outdir):
    """Build each config page with pass 0, into `outdir`, at root semantics."""
    import csv as _csv
    cfg = {}
    with (BASE_DIR / 'event_config.csv').open(encoding='utf-8-sig') as f:
        for row in _csv.DictReader(f):
            n = (row.get('output_filename') or '').strip()
            if n and (row.get('status') or '').strip() == 'active' and n not in cfg:
                cfg[n] = (row.get('event_id') or '').strip()
    # FINISHED EDITIONS ARE RESTAMPED, because a fresh build always emits the
    # LIVE footer - the frozen variant is applied out of band by the workflow.
    # Without this the cutover would ship exactly the regression P3 shipped: a
    # live sync clock over data frozen months ago, on the only pages there are.
    # Liveness from the series file, as check_v2_footer reads it.
    live = {}
    for f in sorted((BASE_DIR / 'series').glob('*.json')):
        try:
            import json as _json
            live[f.stem] = bool(_json.loads(f.read_text(encoding='utf-8'))['live'])
        except (ValueError, KeyError):
            continue

    built = {}
    for name in page_names():
        eid = cfg[name]
        csv_path = BASE_DIR / 'data' / f'{eid}_merged.csv'
        if not csv_path.exists():
            raise SystemExit(f'cutover: no {rel(csv_path)} to build {name} from')
        target = outdir / name
        r = subprocess.run(
            [sys.executable, str(BASE_DIR / 'scripts' / 'build_v2.py'),
             '--event', eid, '--csv', str(csv_path), '--out', str(target)],
            capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f'cutover: build_v2 failed on {name}:\n'
                             f'{(r.stderr or r.stdout)[-600:]}')
        if eid in live and not live[eid]:
            prod = BASE_DIR / name
            frozen = subprocess.run(
                [sys.executable, str(BASE_DIR / 'scripts' / 'stamp_footer.py'),
                 str(prod), '--read-frozen'], capture_output=True, text=True
            ).stdout.strip().splitlines()[-1:] or ['']
            if not frozen[0]:
                raise SystemExit(
                    f'cutover: {name} is a finished edition but its published '
                    f'page carries no freeze date to carry forward. The '
                    f'workflow reads it from there; there is nothing to invent.')
            s = subprocess.run(
                [sys.executable, str(BASE_DIR / 'scripts' / 'stamp_footer.py'),
                 str(target), '--frozen', frozen[0]], capture_output=True, text=True)
            if s.returncode:
                raise SystemExit(f'cutover: could not freeze {name}: {s.stderr}')
        built[name] = target
    return built


FOOT_PAIR_RE = re.compile(
    r'<span class="pgf-k">(.*?)</span><span class="pgf-v">(.*?)</span>')
FOOT_VER_RE = re.compile(r'<span class="pgf-ver">(.*?)</span>')
# The ONE footer field that legitimately moves between the v2 build and the
# root build. Measured across all six pages: `Dernier billet` is data-derived
# and identical, `Données figées` is the frozen variant and identical, the
# brand and every SVG are identical. Only this one differs, and only in HH:MM.
CLOCK_KEY = 'Données API'
CLOCK_RE = re.compile(r'^\d{2}:\d{2}$')
CLOCK_MASK = re.compile(
    r'(<span class="pgf-k">' + CLOCK_KEY + r'</span><span class="pgf-v">)'
    r'[^<]*(</span>)')
VER_MASK = re.compile(r'(<span class="pgf-ver">)[^<]*(</span>)')


def predicted_version():
    """The footer version string AFTER the bump, from the edited source.

    The mirror of predicted_stamp(), and for the same reason: §3(b2) bumps
    DASHBOARD_VERSION during the cutover, so the footer version moves at the one
    moment the §5 comparison exists. Predicted here and then asserted, rather
    than absorbed - see footer_line_ok's docstring for what absorbing it cost.
    """
    src = (BASE_DIR / 'scripts' / 'postprocess_html.py').read_text(encoding='utf-8')
    m = re.search(r"DASHBOARD_VERSION = '([\d.]+)'", src)
    if not m:
        raise SystemExit('cutover: cannot read DASHBOARD_VERSION from '
                         'postprocess_html.py - the version cannot be predicted, '
                         'so the footer comparison cannot be asserted.')
    return 'v7.0' if m.group(1) == '6.8' else f'v{m.group(1)}'


def footer_line_ok(a, b, want_ver):
    """(ok, reason) for a footer line that may differ ONLY in the build clock.

    REPLACES a character-level "every changed segment is digits" test, which was
    wrong in BOTH directions - and the tightening that produced it was itself
    the cause, because a date is digits too:

      FALSE PASS. `12/08 · 14:33` -> `13/08 · 14:33` returned True, as did
      `v6.8` -> `v7.0`. §5 names a changed DATE as the exact thing the check
      exists to prevent, and the §3(b2) version bump would have been absorbed
      as "clock digits" inside the one assertion that cannot be re-run.

      FALSE DEFECT. difflib aligns whole lines, so a replace span can straddle
      the `:` in a clock: measured against the shipped `14:48`, 254 of the 1439
      possible HH:MM values classified as UNEXPLAINED. A CORRECT cutover failed
      about one run in six per page, presenting as two footer lines that look
      identical - whose obvious response is "re-run, it's green", on the one
      assertion §5 says must never be waved through.

    So the difference is addressed by FIELD rather than by character. The footer
    is structured markup; the clock lives in a named field, and every other
    field must be byte-identical. Everything OUTSIDE the two mutable fields is
    then compared as a whole string, because a check that only reads the fields
    it knows about is blind to any markup change beside them.
    """
    ka, kb = FOOT_PAIR_RE.findall(a), FOOT_PAIR_RE.findall(b)
    if [k for k, _ in ka] != [k for k, _ in kb]:
        return False, (f'footer keys changed: {[k for k, _ in ka]} -> '
                       f'{[k for k, _ in kb]}')
    if not ka:
        return False, 'no pgf-k/pgf-v pairs in a line that looks like a footer'
    for (k, va), (_, vb) in zip(ka, kb):
        if k == CLOCK_KEY:
            if not (CLOCK_RE.match(va) and CLOCK_RE.match(vb)):
                return False, (f'{k}: {va!r} -> {vb!r}, and the build clock must '
                               f'be HH:MM on BOTH sides')
        elif va != vb:
            return False, (f'{k}: {va!r} -> {vb!r}. This field does not carry '
                           f'the build clock, so it must not move.')
    va_, vb_ = FOOT_VER_RE.findall(a), FOOT_VER_RE.findall(b)
    if len(va_) != 1 or len(vb_) != 1:
        return False, f'{len(va_)} -> {len(vb_)} .pgf-ver span(s), want 1 each'
    if vb_[0] != want_ver:
        return False, (f'footer version is {vb_[0]!r}, want {want_ver!r}. The '
                       f'§3(b2) bump must land BEFORE the build that stamps it '
                       f'- the same ordering rule as the PAGE_PATHS edit.')
    ma = VER_MASK.sub(r'\1@V@\2', CLOCK_MASK.sub(r'\1@C@\2', a))
    mb = VER_MASK.sub(r'\1@V@\2', CLOCK_MASK.sub(r'\1@C@\2', b))
    if ma != mb:
        return False, 'the footer differs outside the build clock and the version'
    return True, ''


def classify(diff, want_ver):
    """(stamp_pairs, clock_pairs, unexplained) over a unified diff's -/+ lines.

    `unexplained` carries the REASON each line was rejected. The old version
    returned the line pair alone, so a rejected footer printed as two strings
    identical for their first 104 columns and named nothing - which is how a
    false defect here reads as noise to be re-run rather than as a finding.
    """
    olds = [l[1:] for l in diff if l.startswith('-')]
    news = [l[1:] for l in diff if l.startswith('+')]
    stamp, clock, other = 0, 0, []
    for a, b in zip(olds, news):
        if stamp_line(a) and stamp_line(b):
            stamp += 1
        elif 'pg-footer' in a and 'pg-footer' in b:
            ok, why = footer_line_ok(a, b, want_ver)
            if ok:
                clock += 1
            else:
                other.append((a, b, why))
        else:
            other.append((a, b, 'not the build stamp and not a footer line'))
    if len(olds) != len(news):
        other.append(('<line count differs>', f'{len(olds)} vs {len(news)}',
                      'a line was added or removed, not changed'))
    return stamp, clock, other


def compare(name, new_html, v2_html, login_bg):
    """Differing lines between a post-cutover page and its v2 counterpart."""
    want, _ = to_root(v2_html, login_bg)
    return [l for l in difflib.unified_diff(
        want.split('\n'), new_html.split('\n'), lineterm='', n=0)
        if l[:1] in '+-' and not l.startswith(('+++', '---'))]


BANNER = (
    '<div id="{bid}" style="background:#3a2a00;border:1px solid #7a5a00;'
    'border-radius:8px;padding:12px 16px;margin:0 0 16px;'
    'font:500 13px/1.5 \'DM Sans\',sans-serif;color:#ffd479">'
    '<b>Archive — {freeze}.</b> Cette page n\'est plus mise à jour. '
    'Les chiffres sont ceux du {freeze} et ne bougeront plus. '
    'Le tableau de bord actuel est à la racine du site.'
    '</div>'
)


def plan_writes(names, v2_snap, built, hashes, bgs):
    """[(Path, content)] for every file the cutover changes. Computed whole,
    written only once all of it exists - see the staging loop in main()."""
    out = []

    # 1. the six new root pages, exactly as asserted above
    for n in names:
        out.append((BASE_DIR / n, built[n].read_text(encoding='utf-8')))

    # 2. legacy/: the pages that ship TODAY, frozen, each with one banner.
    #    The hashes were taken BEFORE this loop and before any banner - §6.2's
    #    provenance record, so the archive is provably "the page that shipped,
    #    plus one named insertion" and anyone can verify it by stripping the
    #    banner and hashing.
    freeze = subprocess.run(['git', '-C', str(BASE_DIR), 'rev-parse', '--short', 'HEAD'],
                            capture_output=True, text=True).stdout.strip()
    for n in names:
        src = (BASE_DIR / n)
        html = src.read_text(encoding='utf-8')
        frozen_on = subprocess.run(
            [sys.executable, str(BASE_DIR / 'scripts' / 'stamp_footer.py'),
             str(src), '--read-frozen'], capture_output=True, text=True
        ).stdout.strip().splitlines()[-1:] or ['']
        banner = BANNER.format(bid=BANNER_ID, freeze=frozen_on[0] or 'la coupure')
        # Above the content and INSIDE the gate: someone who never gets past the
        # password sees no figures either, so the banner cannot leak more than
        # the page already does.
        marker = '<div class="wrap"'
        if html.count(marker) != 1:
            raise SystemExit(
                f'cutover: {n} has {html.count(marker)} `{marker}` anchors, want '
                f'1 - the archive banner has nowhere unambiguous to go.')
        out.append((BASE_DIR / 'legacy' / n,
                    html.replace(marker, banner + '\n  ' + marker, 1)))

    lines = [f'# `legacy/` — the pages as they shipped at {freeze}', '',
             'Frozen artefacts of the pipeline retired at cutover. **They are',
             'served, and they will lie**: the numbers are cutover-day numbers and',
             'will never move again. Each carries one archive banner saying so,',
             'inserted at freeze time and nowhere else in the file.', '',
             '## Provenance', '',
             'SHA-256 of each page **as it shipped, before the banner was',
             'inserted**. Strip the single `<div id="' + BANNER_ID + '">…</div>`',
             'and its following newline+indent, and the hash returns:', '',
             '| page | sha256 (pre-banner) |', '| --- | --- |']
    lines += [f'| `{n}` | `{hashes[n]}` |' for n in names if n in hashes]
    lines += ['', 'These pages keep their original `<!-- shared:… -->` build',
              'stamp. It is evidence of what built them, and it is meaningful',
              f'only against commit `{freeze}` — the shared assets it hashes have',
              'moved on since.', '',
              '`event_config.csv` points at none of these files, which is why',
              'every page check excludes them: not because they are old, but',
              'because nothing builds them (CUTOVER §6.3).', '']
    out.append((BASE_DIR / 'legacy' / 'README.md', '\n'.join(lines)))

    # 3. build_v2 is ALREADY edited on disk by the time this runs - the edit
    #    goes in BEFORE the build so the pages are produced by the post-cutover
    #    builder rather than transformed into looking like it. Nothing to write.

    # 4. the version, in BOTH places (§3(b2))
    pp_path = BASE_DIR / 'scripts' / 'postprocess_html.py'
    pp_src = pp_path.read_text(encoding='utf-8')
    if pp_src.count("DASHBOARD_VERSION = '6.8'") != 1:
        raise SystemExit('cutover: DASHBOARD_VERSION is not 6.8 - already bumped?')
    out.append((pp_path, pp_src.replace("DASHBOARD_VERSION = '6.8'",
                                        "DASHBOARD_VERSION = '7.0'", 1)))
    tz_path = BASE_DIR / 'verify' / 'check_footer_tz.py'
    tz_src = tz_path.read_text(encoding='utf-8')
    if tz_src.count('Festiflow Dashboard v6.8') != 2:
        raise SystemExit(
            f'cutover: check_footer_tz has '
            f'{tz_src.count("Festiflow Dashboard v6.8")} v6.8 literal(s), want 2 '
            f'- §3(b2) says twice, and a miss here fails the run loudly later.')
    out.append((tz_path, tz_src.replace('Festiflow Dashboard v6.8',
                                        'Festiflow Dashboard v7.0')))

    # 5. THE PREVIEW PATH (§3(c2)), shipping WITH the cutover and not after.
    #    The moment root is production, a push to main is a deploy and work must
    #    move to a branch - and a branch is only reviewable if its build is
    #    published somewhere Leo can open. Every visual defect on this project
    #    without exception was found by Leo opening a page.
    out.append((BASE_DIR / 'preview' / 'README.md', '\n'.join([
        '# `preview/` — where a branch build goes to be looked at', '',
        'Until cutover, `/v2/` was the staging area and work went straight to',
        '`main`: a push published to a path that was not production. That',
        'inverted at cutover. Root IS production now, so a push to `main` is a',
        'deploy, and work moves to a branch.', '',
        'A branch is only reviewable if its build is published. Otherwise every',
        'visual ruling needs a hand-built preview — and the last time that',
        'happened, a self-contained copy of `v2/epk.html` had to be built by',
        'hand with the series pre-seeded so the page\'s own `fetch` never fired.',
        'That is **a transformed artefact used to judge an untransformed one**,',
        'the class `check_v2_identity` and the locked mock exist because of.', '',
        '## How',
        '',
        'GitHub Pages already deploys this repo from `main` (`pages build and',
        'deployment` has run 188 times), so nothing needs hosting built — only a',
        'published location. A branch build lands here and is opened at',
        '`…/preview/<page>.html`.', '',
        'Shipping the cutover without this leaves a window where production is',
        'live, branches are mandatory, and nothing is viewable. That window has',
        'no safe length, which is why this directory exists from the first',
        'cutover commit rather than the second.', ''])))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true',
                    help='write. Without it, nothing is written.')
    a = ap.parse_args()
    mode = 'APPLY' if a.apply else 'DRY RUN - nothing will be written'
    print(f'cutover: {mode}\n')

    names = page_names()
    v2_dir, root = BASE_DIR / 'v2', BASE_DIR
    bgs = build_v2.login_bg_by_page()

    # 1. preflight
    if a.apply:
        st = git('status', '--porcelain')
        if st.stdout.strip():
            raise SystemExit('cutover: working tree is not clean. This rewrites '
                             'six root pages and creates legacy/; it will not '
                             'run on top of unrelated edits.')
    missing = [n for n in names if not (v2_dir / n).exists()]
    if missing:
        raise SystemExit(f'cutover: v2/ is missing {", ".join(missing)}')

    # 2. snapshot, before anything is edited
    v2_snap = {n: (v2_dir / n).read_text(encoding='utf-8') for n in names}
    # 3. provenance, before any banner
    hashes = {n: hashlib.sha256((root / n).read_bytes()).hexdigest()
              for n in names if (root / n).exists()}

    print('ARCHIVE PROVENANCE - SHA-256 of each page as it ships today,')
    print('recorded BEFORE the banner is inserted (§6.2):')
    for n in names:
        print(f'  {hashes.get(n, "(page absent)")}  {n}')
    print()

    tmp = Path(tempfile.mkdtemp(prefix='cutover_'))
    try:
        built = build_root_pages(tmp)

        want_stamp = predicted_stamp()
        want_ver = predicted_version()
        print(f'EXPECTED FOOTER VERSION AFTER THE BUMP: {want_ver}  (§3(b2))')
        print(f'EXPECTED STAMP AFTER THE EDIT: {want_stamp}')
        print(f'  today: {stamp_line(v2_snap[names[0]])}')
        print('  computed from build_v2.py AS THE CUTOVER LEAVES IT, not '
              'observed after the fact.\n')

        print('PER-PAGE DIFF against the v2 page, stripped of `../` (§5):')
        failures = []
        for n in names:
            # The dry run cannot run an edited build_v2 without writing, so it
            # MODELS the edit: strip `../` (what deleting the transforms does)
            # and substitute the predicted stamp. --apply does not model
            # anything - it runs the edited build and asserts against this.
            fresh = built[n].read_text(encoding='utf-8')
            new_html, _ = to_root(fresh, bgs[n])
            here = stamp_line(new_html)
            if here:
                new_html = new_html.replace(here, want_stamp)
            # POSITIVE, not via the diff. classify() only ever sees lines that
            # DIFFER, so a page that missed the bump would carry v6.8 on both
            # sides, produce an identical footer line, never reach the version
            # test, and pass. The blindness the diff has is exactly the one the
            # bump would land in, so the version is asserted on the built page
            # directly, every page, whether or not anything differs.
            vers = FOOT_VER_RE.findall(new_html)
            if vers != [want_ver] * 2:
                failures.append(n)
                print(f'  FAIL  {n}: footer version(s) {vers}, want '
                      f'{[want_ver] * 2} - §3(b2)')
                continue
            diff = compare(n, new_html, v2_snap[n], bgs[n])
            stamp, clock, other = classify(diff, want_ver)
            if stamp == 1 and not other:
                print(f'  ok    {n}: {stamp} build stamp + {clock} footer '
                      f'line(s) differing in the build clock only, nothing else')
            else:
                failures.append(n)
                print(f'  FAIL  {n}: {stamp} stamp, {clock} clock-only, '
                      f'{len(other)} UNEXPLAINED')
                for a, b, why in other[:3]:
                    print(f'          why: {why}')
                    print(f'          - {a[:104]}')
                    print(f'          + {b[:104]}')
        print()

        if failures:
            raise SystemExit(
                f'cutover: {len(failures)} page(s) differ from their v2 '
                f'counterpart by more than the build stamp. This is the one '
                f'assertion that cannot be re-run later, so it is also the one '
                f'that must not be waved through. Nothing was written.')

        print('THE STAMP THAT LEGITIMATELY MOVES: build_v2.py is in '
              'V2_SHARED_ASSETS and the')
        print('cutover edits it, so the v2 stamp changes at the one moment the '
              'comparison exists.')
        print('Asserted rather than ignored - a SECOND differing line fails, '
              'which is what')
        print('"compare modulo the stamp" throws away.\n')

        if not a.apply:
            print('DRY RUN COMPLETE. Nothing written. Re-run with --apply to '
                  'perform the cutover.')
            return 0

        # THE PRECONDITION, AND WHY IT IS A REFUSAL RATHER THAN A STEP.
        # The workflow builds pass 0's output to `v2/$OUT` (line 279) and stages
        # it (390). Move the pages to root without changing that and the next
        # scheduled run rebuilds v2/, leaves the root pages untouched, and
        # production goes stale within four hours while every check still
        # passes. That is a half-cutover, the state nobody has specified.
        #
        # It is NOT folded in here, because a workflow edit is a reviewable diff
        # and this script's job is the part that cannot be reviewed after the
        # fact. So the reviewable half goes first, as an ordinary commit, and
        # this refuses until it is in place. The irreversible step sits behind
        # the reversible one rather than beside it.
        wf = (BASE_DIR / '.github' / 'workflows' / 'daily-dashboards.yml'
              ).read_text(encoding='utf-8')
        if '--out "v2/${{ matrix.event.out }}"' in wf:
            raise SystemExit(
                'cutover: the workflow still builds pass 0 to v2/. Land that '
                'edit first - it is a reviewable diff, and moving the pages '
                'without it leaves production stale within four hours while '
                'every check still passes. Nothing was written.')

        print('applying...\n')

        # EDIT FIRST, THEN BUILD. The dry run MODELS the edit; --apply must not.
        # The first version asserted against the modelled page and then wrote the
        # UNMODELLED build - model compared to model, write untouched by either -
        # and shipped six root pages still carrying `../` past an assertion that
        # said zero. The write path now contains no modelling at all.
        bv = BASE_DIR / 'scripts' / 'build_v2.py'
        original_bv = bv.read_text(encoding='utf-8')
        try:
            bv.write_text(cutover_edit(original_bv), encoding='utf-8')
            tmp2 = Path(tempfile.mkdtemp(prefix='cutover_post_'))
            try:
                built = build_root_pages(tmp2)
                print('POST-EDIT BUILD, asserted RAW (no modelling):')
                bad = []
                for n in names:
                    raw = built[n].read_text(encoding='utf-8')
                    if '../' in raw:
                        bad.append(f'{n}: {raw.count("../")} `../` survived the edit')
                        continue
                    vers = FOOT_VER_RE.findall(raw)
                    if vers != [want_ver] * 2:
                        bad.append(f'{n}: footer version(s) {vers}, want '
                                   f'{[want_ver] * 2} - §3(b2)')
                        continue
                    st, ck, other = classify(
                        compare(n, raw, v2_snap[n], bgs[n]), want_ver)
                    if st == 1 and not other:
                        print(f'  ok    {n}: {st} stamp + {ck} clock-only, 0 `../`')
                    else:
                        bad.append(f'{n}: {st} stamp, {len(other)} unexplained'
                                   + ''.join(f'\n      {w}' for _, _, w in other[:3]))
                if bad:
                    raise SystemExit('cutover: the post-edit build does not '
                                     'match:\n  ' + '\n  '.join(bad))
                writes = plan_writes(names, v2_snap, built, hashes, bgs)

        # ATOMIC: every target is written to a sibling `.cutover-new` file
        # first, and only renamed once ALL of them exist. A failure halfway
        # leaves the tree exactly as it was found, which is the one thing a
        # cutover must never get wrong.
                staged = []
                try:
                    for target, content in writes:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        tmp_t = target.with_suffix(target.suffix + '.cutover-new')
                        tmp_t.write_text(content, encoding='utf-8')
                        staged.append((tmp_t, target))
                    for tmp_t, target in staged:
                        tmp_t.replace(target)
                except BaseException:
                    for tmp_t, _ in staged:
                        tmp_t.unlink(missing_ok=True)
                    raise
                for n in names:
                    (BASE_DIR / 'v2' / n).unlink(missing_ok=True)
                v2d = BASE_DIR / 'v2'
                if v2d.exists() and not any(v2d.iterdir()):
                    v2d.rmdir()
            finally:
                shutil.rmtree(tmp2, ignore_errors=True)
        except BaseException:
            bv.write_text(original_bv, encoding='utf-8')
            raise

        print(f'  wrote {len(writes)} file(s); v2/ removed')
        print('\nCUTOVER COMPLETE. Now, before committing:')
        print('  bash verify/assert_redesign.sh .')
        print('  python3 verify/check_build_stamp.py     # rescope: one set, at root')
        print('  python3 verify/check_v2_footer.py       # reads root now')
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
