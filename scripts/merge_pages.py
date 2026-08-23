#!/usr/bin/env python3
"""
Resolve a merge's generated-page conflicts without producing churn.

    python3 scripts/merge_pages.py          # during a conflicted merge
    python3 scripts/merge_pages.py --check  # report only, change nothing

WHAT THIS REPLACES, AND WHY IT IS A SCRIPT RATHER THAN A HABIT
--------------------------------------------------------------
Merging `origin/main` into a working branch conflicts in every generated page,
because both sides regenerated them. The project's rule is right and unchanged:
**a generated page is never text-merged, it is rebuilt.** So the sequence was:
take one side, rebuild all seven, re-freeze the finished two.

That rebuild was UNNECESSARY EVERY TIME, and it produced junk every time. The
footer carries "Données API · HH:MM", set from the clock at build time, so a
rebuild moves it whether or not anything else changed. Twice the result was five
staged files whose entire diff was footer timestamps and the build stamp - and
twice they were discarded BY HAND after the fact.

Hand-cleanup after every merge is the shape where one day the junk gets
committed instead of discarded. That is exactly how `_before_rennes.html`
reached `main`: a scratch file that survived because the step which would have
removed it did not run.

THE QUESTION THE REBUILD WAS ANSWERING ALREADY HAS A CHECK
-----------------------------------------------------------
"Are these pages built from the current shared assets?" is precisely what
`verify/check_build_stamp.py` asks - it compares each page's `<!-- shared-v2: -->`
stamp against the hash of `V2_SHARED_ASSETS`. So:

  * stamp matches  -> the incoming pages are already correct. Rebuilding would
                      change nothing but the clock. DO NOT REBUILD.
  * stamp differs  -> a shared asset moved on this branch and the pages really
                      are stale. Rebuild, and the clock moving is incidental to
                      a change that had to happen anyway.

The rebuild stops being a ritual and becomes a decision with an input.

WHY `--theirs` FOR THE CONFLICTED PAGES
---------------------------------------
`main`'s copy is what the workflow published from the freshest fetch. Ours is a
local rebuild of older data. Taking theirs is not "picking a side" in a merge
sense - both are about to be either accepted or regenerated wholesale, and the
one built from newer data is the better starting point.

Finished events are re-frozen afterwards either way: their footer reads
"Données figées · DD/MM", applied out of band by the workflow's restamp step,
and any rebuild silently converts it into a live sync time.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from pages import page_names  # noqa: E402


def git(*args, **kw):
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True,
                          text=True, **kw)


def conflicted():
    out = git('diff', '--name-only', '--diff-filter=U').stdout.split()
    return [f for f in out if f.endswith('.html') or f.startswith(('data/', 'series/'))]


def stamps_current():
    """check_build_stamp's own verdict, not a second opinion on it."""
    r = subprocess.run([sys.executable, str(ROOT / 'verify' / 'check_build_stamp.py')],
                       cwd=ROOT, capture_output=True, text=True)
    return r.returncode == 0, r.stdout


def event_for(page):
    import csv
    with (ROOT / 'event_config.csv').open(encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            if (row.get('output_filename') or '').strip() == page and \
               (row.get('status') or '').strip() == 'active':
                return (row.get('event_id') or '').strip()
    return None


def rebuild_all():
    for page in page_names():
        eid = event_for(page)
        csv_path = ROOT / 'data' / f'{eid}_merged.csv'
        if not eid or not csv_path.exists():
            print(f'  skip {page}: no CSV to build from')
            continue
        r = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'build_v2.py'),
                            '--event', eid, '--csv', str(csv_path),
                            '--out', str(ROOT / page)],
                           cwd=ROOT, capture_output=True, text=True)
        print(f'  {"ok  " if not r.returncode else "FAIL"} {page}')
    refreeze()


def refreeze():
    """A finished event's footer says 'Données figées'. A rebuild destroys it."""
    for page in page_names():
        prev = git('show', f'origin/main:{page}')
        if prev.returncode:
            continue
        frozen = subprocess.run(
            [sys.executable, str(ROOT / 'scripts' / 'stamp_footer.py'), '-',
             '--read-frozen'], cwd=ROOT, input=prev.stdout,
            capture_output=True, text=True).stdout.strip()
        if frozen:
            subprocess.run([sys.executable, str(ROOT / 'scripts' / 'stamp_footer.py'),
                            str(ROOT / page), '--frozen', frozen],
                           cwd=ROOT, capture_output=True, text=True)
            print(f'  re-froze {page} ({frozen})')


def main():
    report_only = '--check' in sys.argv
    files = conflicted()
    if files:
        print(f'{len(files)} conflicted generated file(s); taking origin/main\'s copy')
        if not report_only:
            for f in files:
                git('checkout', '--theirs', '--', f)
                git('add', '--', f)
    else:
        print('no conflicted generated files')

    ok, out = stamps_current()
    if ok:
        print('\ncheck_build_stamp: pages match the current shared assets.')
        print('NOT REBUILDING - a rebuild would move the footer clock and the')
        print('build stamp and change nothing else, which is churn this script')
        print('exists to stop producing.')
        return 0

    print('\ncheck_build_stamp: the pages are NOT built from the current shared')
    print('assets, so a shared asset moved on this branch. Rebuilding:')
    for line in out.splitlines():
        if 'FAIL' in line:
            print(f'  {line.strip()}')
    if report_only:
        print('  (--check: nothing rebuilt)')
        return 1
    rebuild_all()
    ok, _ = stamps_current()
    print('\ncheck_build_stamp after rebuild:', 'GREEN' if ok else 'STILL RED')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
