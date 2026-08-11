/*
 * Behavioural check for the Suivi comparison selector.
 *
 *   NODE_PATH=<dir with playwright> node verify/check_selector.js <file.html> [width]
 *
 * Needs playwright and the preinstalled chromium; it is therefore NOT wired
 * into verify/assert_redesign.sh, which must run with nothing but bash and
 * python. Run it by hand, or from a workflow that installs playwright, after
 * any change to the renderer.
 *
 * Exits non-zero on any failure. Prints one line per assertion.
 *
 * WHY THIS EXISTS
 * ---------------
 * The selector shipped with every Diff on the page wrong by six orders of
 * magnitude, and three passing checks did not notice:
 *
 *   - "restore is exact" passed, because restore replays saved HTML rather
 *     than recomputing. It never enters the renderer at all.
 *   - "em dash count" passed, because uncovered rows were genuinely dashed.
 *   - "no page errors" passed, because 1357402 - 203 is perfectly valid
 *     arithmetic.
 *
 * All three verified the ROUND TRIP. None verified the OUTPUT. So these
 * assertions look at what a reader would actually see after switching.
 */

const { chromium } = require('playwright');
const path = require('path');

const CHROME = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';

(async () => {
  const file = path.resolve(process.argv[2]);
  const width = parseInt(process.argv[3] || '1280', 10);
  const browser = await chromium.launch({ executablePath: CHROME });
  const page = await browser.newPage({ viewport: { width, height: 1000 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  // Chart.js is a CDN dependency and cannot load offline. Stub the global
  // rather than letting the page throw - a chart error would mask, or be
  // mistaken for, a selector error. Nothing here touches charts.
  await page.route('**/chart*.js', r => r.fulfill({
    contentType: 'text/javascript',
    body: 'window.Chart=function(){return{destroy:function(){},update:function(){}}};'
        + 'Chart.defaults={color:"",borderColor:"",font:{}};'
        + 'Chart.register=function(){};Chart.getChart=function(){};',
  }));
  await page.goto('file://' + file);
  await page.waitForTimeout(500);
  const pw = await page.$('input[type=password]');
  if (pw) { await pw.fill('festipass'); await pw.press('Enter'); await page.waitForTimeout(200); }

  const result = await page.evaluate(async () => {
    const fails = [];
    const items = [...document.querySelectorAll('.cmp-item')];
    if (!items.length) return { fails: ['no .cmp-item in the menu'], picked: null };
    const refBtn = items.find(b => b.querySelector('.cmp-ref'));
    const other = items.find(b => b !== refBtn);
    const name = other.querySelector('span').childNodes[0].textContent.trim();

    document.getElementById('cmp-trigger').click();
    other.click();
    await new Promise(r => setTimeout(r, 250));

    const count = el => {
      if (!el) return null;
      const v = el.getAttribute('data-n');
      return v === null || v === '' ? null : parseInt(v, 10);
    };

    // 1. A Diff can never exceed the larger of the two counts it comes from.
    //    This is the assertion that would have caught 1357402 - 203.
    let checked = 0;
    for (const row of document.querySelectorAll('#suivi-jour .dtl-row[data-cur]')) {
      const diffEl = row.querySelector('.dtl-center .dtl-diff');
      const pct = row.querySelector('.dtl-center .dtl-pct');
      if (!diffEl) continue;
      const l = count(row.querySelector('.dtl-left .dtl-sales'));
      const r = count(row.querySelector('.dtl-right .dtl-sales'));
      const shownTxt = diffEl.textContent.trim();
      // A DIFF MUST BE ABSENT WHERE ITS OPERAND IS ABSENT, and this used to
      // `continue` past exactly that case. "diff === right - left" cannot catch
      // it: null coerces to 0, 0 is a legal count, and the subtraction stays
      // internally consistent while the rendered number is one side restated.
      // Two implementations agreeing, both wrong - the same shape as the
      // exact_date spec.
      //
      // WHAT THIS DOES AND DOES NOT COVER, said out loud rather than left to
      // look like coverage. The legacy renderer has no candidate switcher, so
      // every LIVED row carries both sides - 557 of 557 operands populated on
      // epk - and it cannot produce the defect at all. The defect is a v2
      // phenomenon and its real guard is the rendered-cell assertion in
      // check_b1_switch, on the path where it actually lives. This one bites if
      // the legacy table ever gains a lived row with a missing side.
      //
      // The detection PATH is exercised on every run even so: future rows do
      // have absent operands, this branch reaches them, and it read their cell
      // text. Confirmed by the guard firing on the real page before the
      // countdown exclusion below existed - which is the negative test earning
      // its keep in the other direction, since that first version failed a
      // correct artefact.
      if (l === null || r === null) {
        // `J−25` and `J+1` are not diffs. A future row carries the countdown in
        // this cell and the event days themselves read `J+1`/`J+2`, so a row
        // with no current-side figure is expected there and its cell is out of
        // scope: a countdown, not a comparison.
        if (shownTxt && !/^[—–-]$/.test(shownTxt) && !/^J\s*[+−–-]\s*\d+$/.test(shownTxt)) {
          fails.push(`diff "${shownTxt}" rendered against an absent operand ` +
                     `(left ${l}, right ${r}) on ${row.getAttribute('data-cur')}`);
          break;
        }
        continue;
      }
      // The `%` filter comes AFTER the absence check, deliberately. It used to
      // come first, and it skips precisely the rows this is about: when the
      // reference is absent the percentage renders an em-dash, so every row
      // with a missing operand was dropped before any assertion saw it. The
      // first version of this guard sat below that filter and was dead code for
      // its own case - caught by the constructed negative test, not by reading.
      if (!pct || !/%$/.test(pct.textContent)) continue;
      const shown = parseInt(shownTxt.replace(/[^0-9-]/g, ''), 10);
      if (!Number.isFinite(shown)) continue;
      checked++;
      if (shown !== r - l) {
        fails.push(`diff ${shown} != ${r} - ${l} on ${row.getAttribute('data-cur')}`);
        break;
      }
      if (Math.abs(shown) > Math.max(Math.abs(l), Math.abs(r))) {
        fails.push(`diff ${shown} exceeds both counts (${l}, ${r})`);
        break;
      }
    }
    if (!checked) fails.push('no comparable rows found to check the Diff on');

    // 2. Nothing the renderer reads may hold two numbers in its text. Any
    //    element carrying data-n must have data-n === its own leading number,
    //    even when a revenue span sits beside it.
    for (const el of document.querySelectorAll('#sec-suivi .dtl-sales[data-n]')) {
      const attr = el.getAttribute('data-n');
      if (attr === '') continue;
      const lead = (el.firstChild && el.firstChild.textContent || '').replace(/[^0-9]/g, '');
      if (lead !== attr) {
        fails.push(`data-n="${attr}" but leading text is "${lead}"`);
        break;
      }
      if (el.querySelector('.dtl-rev') && /[0-9].*[€].*[0-9]/.test(el.textContent)) {
        // Not a failure in itself - it is exactly why data-n exists - but the
        // element must never be the source of a number.
        if (el.textContent.replace(/[^0-9]/g, '') === attr) {
          fails.push(`textContent of .dtl-sales is parseable as ${attr}, ` +
                     `which invites the bug data-n exists to prevent`);
          break;
        }
      }
    }

    // 3. Every left-hand column header must name the selected candidate.
    const labels = [...document.querySelectorAll('#sec-suivi .dtl-col-label')]
      .filter(e => !e.classList.contains('center') && !e.classList.contains('right'));
    if (!labels.length) fails.push('no left .dtl-col-label found');
    for (const l of labels) {
      if (!l.textContent.includes(name)) {
        fails.push(`column header "${l.textContent}" does not name "${name}"`);
        break;
      }
    }

    // 4. Restoring the reference must put every header back.
    document.getElementById('cmp-trigger').click();
    refBtn.click();
    await new Promise(r => setTimeout(r, 200));
    for (const l of labels) {
      if (l.textContent !== l._orig) {
        fails.push(`header "${l.textContent}" not restored (was "${l._orig}")`);
        break;
      }
    }
    return { fails, picked: name, rowsChecked: checked, labels: labels.length };
  });

  const fails = result.fails.concat(errors.map(e => 'page error: ' + e));
  const tag = path.basename(file);
  if (result.picked) {
    console.log(`  ${tag}: selected "${result.picked}", ` +
                `${result.rowsChecked} diff row(s), ${result.labels} column header(s)`);
  }
  fails.forEach(f => console.log(`  FAIL  ${tag}: ${f}`));
  if (!fails.length) console.log(`  ok    ${tag}: selector output is consistent`);
  await browser.close();
  process.exit(fails.length ? 1 : 0);
})();
