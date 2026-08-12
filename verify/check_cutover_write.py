"""build -> edit -> rebuild -> assert agree. Then break the edit and assert FAIL."""
import shutil, subprocess, sys, tempfile
from pathlib import Path
R = Path('/home/user/ticketing_api'); sys.path.insert(0, str(R/'scripts'))
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
    st, ck, other = C.classify(C.compare(NAME, raw, v2html, bg))
    return 'PASS' if (st == 1 and not other) else f'FAIL: {st} stamp, {len(other)} unexplained'

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
