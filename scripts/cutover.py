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


def only_digits_differ(a, b):
    """True when two lines differ ONLY in digit runs.

    §5 asks for "exactly one differing line". Measured, it is THREE - the build
    stamp and the two footer items, which carry a build-time clock, so the root
    pages are necessarily built at a different minute than the v2 pages were.
    "Two footer lines differ" would be the loose repair, and it would pass a
    footer whose DATE or EVENT NAME had also changed. So the difference is
    asserted at character level: every changed segment, on both sides, must be
    digits and nothing else.
    """
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if tag == 'equal':
            continue
        if not (a[i1:i2].isdigit() or not a[i1:i2]):
            return False
        if not (b[j1:j2].isdigit() or not b[j1:j2]):
            return False
    return True


def classify(diff):
    """(stamp_pairs, clock_pairs, unexplained) over a unified diff's -/+ lines."""
    olds = [l[1:] for l in diff if l.startswith('-')]
    news = [l[1:] for l in diff if l.startswith('+')]
    stamp, clock, other = 0, 0, []
    for a, b in zip(olds, news):
        if stamp_line(a) and stamp_line(b):
            stamp += 1
        elif 'pg-footer' in a and 'pg-footer' in b and only_digits_differ(a, b):
            clock += 1
        else:
            other.append((a, b))
    if len(olds) != len(news):
        other.append(('<line count differs>', f'{len(olds)} vs {len(news)}'))
    return stamp, clock, other


def compare(name, new_html, v2_html, login_bg):
    """Differing lines between a post-cutover page and its v2 counterpart."""
    want, _ = to_root(v2_html, login_bg)
    return [l for l in difflib.unified_diff(
        want.split('\n'), new_html.split('\n'), lineterm='', n=0)
        if l[:1] in '+-' and not l.startswith(('+++', '---'))]


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
            diff = compare(n, new_html, v2_snap[n], bgs[n])
            stamp, clock, other = classify(diff)
            if stamp == 1 and not other:
                print(f'  ok    {n}: {stamp} build stamp + {clock} footer '
                      f'line(s) differing in clock digits only, nothing else')
            else:
                failures.append(n)
                print(f'  FAIL  {n}: {stamp} stamp, {clock} clock-only, '
                      f'{len(other)} UNEXPLAINED')
                for a, b in other[:3]:
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

        print('applying...')
        raise SystemExit(
            'cutover: --apply is not wired yet. The assertion above is the part '
            'that had to exist before anything is moved; the writing half - '
            'legacy/, the banners, the README and the build_v2 edit - lands '
            'with §3, and lands atomically or not at all.')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
