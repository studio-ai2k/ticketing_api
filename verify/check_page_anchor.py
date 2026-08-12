#!/usr/bin/env python3
"""
The page is a COMPLETE dashboard, and it is the page it claims to be.

    python3 verify/check_page_anchor.py              # every pass-0 page
    python3 verify/check_page_anchor.py <page.html>  # one page, for the shell gate

WHY THIS EXISTS
---------------
Measured on the gate as it stood: **174 of `assert_redesign.sh`'s 396
assertions pass against six ZERO-BYTE files** carrying the right names. Run it
yourself - create the six names empty and point the gate at them.

That is not a quirk of one badly written line. Most of a markup gate is
necessarily ABSENCE assertions - no `.details-toggle`, no `Outfit`, no `🎟`, no
`../` - and every absence holds on a page that contains nothing. So does every
count-derived assertion whose baseline is itself derived from the page: the
`.ac-t` check computes `want = days + 5` from the page's own `.q-card` count,
and on a page with no day cards it wants 5, finds 5, and passes. It passes on
pass-0 pages TODAY for that reason and for no other.

This matters at cutover specifically. Production ships its body as static
markup - 2716 `<div>`s on rennes - and pass-0 builds the body at runtime from
`const D`, shipping 67. So the pass-0 pages the gate is being repointed at are
exactly the artefact on which the absence half is vacuous. A gate made green
against them would report the same 174 passes and mean nothing by any of them.

An absence assertion is only worth the artefact it ran against. This states
what that artefact must be, so the rest has something to be true OF. It is
therefore the FIRST thing the gate runs on each page, and a page that fails it
is not asserted further - a vacuous pass printed beside a real failure is how
396 green lines came to describe six empty files.

WHAT IT DOES NOT DO
-------------------
It does not check the body. It cannot: post-cutover there is no static body to
check, which is the finding that reshaped P4. Body assertions belong in the
browser-driven checks (`check_v2_behaviour.py`, `check_selector.js`), which are
deliberately outside this gate because it must run on bash and python alone.
This asserts the page is whole and is itself. That is the precondition, not the
coverage.
"""

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from pages import pass0_pages   # noqa: E402 - CUTOVER 6.3, one page list

STYLE_RE = re.compile(r'<style>.*?</style>', re.DOTALL)
# Both stamp forms. Production carries `<!-- shared:… -->` and pass 0 carries
# `<!-- shared-v2:… -->` (P1), and the anchor holds on either pipeline: its
# claim is "this page was built and stamped", not "which builder".
STAMP_RE = re.compile(r'<!-- shared(?:-v2)?:[0-9a-f]{12} -->')
PAYLOAD_RE = re.compile(r'const D=(\{.*?\});\s*\n', re.DOTALL)
FOOTER = 'class="pg-footer'


def config_ids():
    """{output_filename: event_id} for every ACTIVE row."""
    out = {}
    with (ROOT / 'event_config.csv').open(encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            if (row.get('status') or '').strip() != 'active':
                continue
            name = (row.get('output_filename') or '').strip()
            if name:
                out[name] = (row.get('event_id') or '').strip()
    return out


def anchor_problems(path, ids=None):
    """Every way `path` fails to be a complete, self-identifying dashboard.

    Returns a list of reasons - ALL of them, not the first. A page that is
    truncated is usually several things at once, and reporting one at a time
    turns one broken artefact into several rounds.
    """
    ids = config_ids() if ids is None else ids
    why = []
    try:
        html = Path(path).read_text(encoding='utf-8')
    except OSError as exc:
        return [f'unreadable: {exc}']

    if not html.strip():
        return ['the file is empty']
    # TERMINATION, not size. A byte threshold is a number someone picks; this
    # says the document ended where a document ends. A truncated write - the
    # realistic failure, since every page here is written by a build - loses the
    # tail and fails this while still being hundreds of kilobytes.
    if not html.rstrip().endswith('</html>'):
        why.append(f'does not end with </html> (ends {html.rstrip()[-40:]!r}) '
                   f'- the document is truncated')

    n = len(STYLE_RE.findall(html))
    if n != 1:
        why.append(f'{n} <style> element(s), want 1')

    n = len(STAMP_RE.findall(html))
    if n != 1:
        why.append(f'{n} build stamp comment(s), want 1 - an unstamped page was '
                   f'not built by a pipeline this repo audits')

    n = html.count(FOOTER)
    if n != 2:
        why.append(f'{n} {FOOTER}" element(s), want 2')

    # IDENTITY (§5.1). "A complete page" is not enough: bordeaux_oct shipped
    # complete, and carrying epk's name and dates (check_v2_identity). This is
    # the cheap half of that - the page's own payload must name the event its
    # config row names.
    m = PAYLOAD_RE.search(html)
    if not m:
        # Name the pipeline rather than the symptom. Production pages carry no
        # `const D=` at all - measured, zero on all six - so pointing this gate
        # at the retiring pipeline produces six identical "no payload" lines
        # that read as a broken check. They are a misaimed one.
        if re.search(r'<!-- shared:[0-9a-f]{12} -->', html):
            why.append('this is a PRODUCTION-pipeline page (it carries '
                       '`<!-- shared:… -->` and no `const D=`). This gate '
                       'asserts pass-0 pages; run it without a directory '
                       'argument and pages.pass0_dir() will find them.')
        else:
            why.append('no `const D=` payload - this gate asserts pass-0 pages, '
                       'and a page without a payload is not one')
    else:
        want = ids.get(Path(path).name)
        if want is None:
            why.append(f'no ACTIVE event_config row owns {Path(path).name!r}')
        else:
            try:
                got = json.loads(m.group(1)).get('id')
            except ValueError as exc:
                why.append(f'`const D=` is not parseable JSON: {exc}')
            else:
                if got != want:
                    why.append(f'payload id is {got!r}, config says {want!r}')
    return why


def main():
    ids = config_ids()
    if len(sys.argv) > 1:
        # Per-page mode, for assert_redesign.sh: reasons on stderr so the shell
        # can show them, count on stdout so the shell can test it.
        why = anchor_problems(sys.argv[1], ids)
        for w in why:
            print(w, file=sys.stderr)
        print(len(why))
        return 0

    pages = pass0_pages()
    failed = 0
    for p in pages:
        why = anchor_problems(p, ids)
        if why:
            failed += 1
            print(f'  FAIL  {p.name}:')
            for w in why:
                print(f'          {w}')
        else:
            print(f'  ok    {p.name}: whole, stamped, and its own event')
    print()
    if failed:
        print(f'FAILED: {failed} of {len(pages)} page(s) are not a complete '
              f'dashboard. Every absence assertion in assert_redesign.sh is '
              f'vacuous on such a page, so those results mean nothing until '
              f'this passes.')
        return 1
    print(f'{len(pages)} page(s) anchored - absence assertions have an artefact')
    return 0


if __name__ == '__main__':
    sys.exit(main())
