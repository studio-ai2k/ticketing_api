"""build -> edit -> rebuild -> assert agree. Then break the edit and assert FAIL.

POST-CUTOVER THIS ASSERTS THE OPPOSITE, AND THAT IS THE POINT
-------------------------------------------------------------
Until the cutover this ran the write path for real: build a page, apply
`cutover_edit`, rebuild, and require the raw output to differ from the pre-edit
page by the build stamp alone (T1) - then make the edit a no-op and require it
to FAIL with 5 `../` (T2). T2 reproduced the exact state the first attempt
shipped, and it broke the EDIT rather than the page, so it could not pass by
sharing a code path with what it checks.

The cutover has happened. `PAGE_PATHS` is gone from build_v2.py, so
`cutover_edit` finds 0 sites and refuses - which is `check_cutover_write`
failing on a tree where nothing is wrong.

Rather than retire it, it now asserts what IS true and worth knowing: THE
CUTOVER CANNOT BE APPLIED TWICE. The refusal is the property. A tool that
silently re-ran its own irreversible step - deleting a `legacy/` it had already
written, re-archiving pages that are already the archive - is a worse failure
than the one this file was built to catch, and nothing else asserts it.

The T1/T2 body is kept, not deleted, and runs whenever the edit sites exist
again. That is not hypothetical: it is what a future pipeline swap would look
like, and reconstructing this file from the handoff would be the expensive way
to get it back."""
import shutil, subprocess, sys, tempfile
from pathlib import Path
R = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(R/'scripts'))
import cutover as C, build_v2

bv = R/'scripts'/'build_v2.py'; orig = bv.read_text()
EV, CSV, NAME = 'rennes_2026', R/'data'/'rennes_2026_merged.csv', 'rennes.html'

def build(out):
    r = subprocess.run([sys.executable, str(R/'scripts'/'build_v2.py'),
        '--event', EV, '--csv', str(CSV), '--out', str(out)],
        capture_output=True, text=True)
    assert not r.returncode, r.stderr[-400:]
    return out.read_text(encoding='utf-8')

def verdict(raw, v2html, bg):
    if '../' in raw:
        return f'FAIL: {raw.count("../")} `../` in the built page'
    # current_version(), NOT predicted_version(). This test applies ONLY
    # `cutover_edit` (the build_v2 half); it never bumps DASHBOARD_VERSION, so
    # both pages here legitimately carry today's version and asking for the
    # post-bump one would fail T1 - a correct edit reported as a defect.
    st, ck, other = C.classify(C.compare(NAME, raw, v2html, bg),
                               C.current_version())
    return 'PASS' if (st == 1 and not other) else f'FAIL: {st} stamp, {len(other)} unexplained'

# WHICH SIDE OF THE CUTOVER ARE WE ON? Asked of the artefact, not of a flag or
# a date: does build_v2.py still contain the site the cutover edits?
try:
    C.cutover_edit(orig)
    PRE_CUTOVER = True
except SystemExit:
    PRE_CUTOVER = False

if not PRE_CUTOVER:
    # The cutover has run. Assert the refusal itself - the tool must not be able
    # to perform its own irreversible step a second time.
    fails = []
    try:
        C.cutover_edit(orig)
        fails.append('cutover_edit did NOT refuse on an already-cut-over '
                     'build_v2.py - it would edit the wrong text, or none')
    except SystemExit as exc:
        if 'matched 0 time(s)' not in str(exc):
            fails.append(f'cutover_edit refused for an unexpected reason: {exc}')
        else:
            print('  post-cutover: cutover_edit REFUSES, as it must - '
                  '"the edit site matched 0 time(s), want 1"')
    # And the archive it already wrote must still be there to be clobbered.
    legacy = R / 'legacy'
    n = len(list(legacy.glob('*.html'))) if legacy.is_dir() else 0
    if n != 6:
        fails.append(f'legacy/ holds {n} page(s), want 6 - the archive a second '
                     f'run would overwrite is not intact')
    else:
        print(f'  post-cutover: legacy/ intact with {n} pages, so the refusal is '
              f'protecting something')
    if fails:
        for f in fails:
            print(f'  FAIL  {f}')
        sys.exit(1)
    print('  the cutover cannot be applied twice')
    sys.exit(0)

try:
    tmp = Path(tempfile.mkdtemp())
    bg = build_v2.login_bg_by_page()[NAME]
    a = build(tmp/'a.html')                       # pre-edit == the v2 shape
    bv.write_text(C.cutover_edit(orig))           # THE REAL EDIT
    b = build(tmp/'b.html')
    print('  T1 real edit, raw post-edit page vs pre-edit page:', verdict(b, a, bg))

    bv.write_text(orig)                           # BREAK IT: edit is a no-op
    c = build(tmp/'c.html')
    print('  T2 edit made a NO-OP, same assertion:            ', verdict(c, a, bg))
finally:
    bv.write_text(orig); shutil.rmtree(tmp, ignore_errors=True)
