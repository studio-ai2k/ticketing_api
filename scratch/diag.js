const { chromium } = require('playwright');
const path = require('path');
const { CHROME, installMock } = require('./mock');

const FILE = process.argv[2] || 'budget_pa_x_04495da6_BUILD59.html';

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const logs = [];
  page.on('console', m => logs.push(`[${m.type()}] ${m.text()}`));
  page.on('pageerror', e => logs.push(`[pageerror] ${e.message}`));
  await installMock(page);

  const fileUrl = 'file://' + path.resolve(FILE);
  await page.goto(fileUrl, { waitUntil: 'networkidle' });

  // Wait for REC to load, then open the recette edit drawer directly.
  await page.waitForFunction(() => typeof REC !== 'undefined' && REC.length > 0, { timeout: 8000 });
  await page.evaluate(() => { openRecLigne(0, 0, false); });

  // Switch to Intégrations tab so the encsrc pane is visible, then to manual mode.
  await page.evaluate(() => {
    const t = document.querySelector('.ed-tab[data-edpane="integrations"]');
    if (t) edTab(t);
    encsrcMode('man');
  });

  // Let the 80ms focus timer + animations settle, mimicking a real user who
  // opens the drawer and then reaches for the field.
  await page.waitForTimeout(400);

  const diag = await page.evaluate(() => {
    const i = document.getElementById('encsrc-man-input');
    if (!i) return { error: 'no input' };
    const r = i.getBoundingClientRect();
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    i.focus();
    return {
      hitIsInput: hit === i,
      hitTag: hit && hit.outerHTML.slice(0, 160),
      hitId: hit && hit.id,
      hitClass: hit && hit.className,
      pointerEvents: getComputedStyle(i).pointerEvents,
      focusLanded: document.activeElement === i,
      activeEl: document.activeElement && (document.activeElement.id || document.activeElement.tagName),
      paneAnim: getComputedStyle(i.closest('.encsrc-mode')).animationName,
      paneTransform: getComputedStyle(i.closest('.encsrc-mode')).transform,
      rect: { left: r.left, top: r.top, w: r.width, h: r.height },
    };
  });

  // Type test: focus the input, then type through the keyboard (real key events).
  await page.evaluate(() => document.getElementById('encsrc-man-input').focus());
  await page.keyboard.type('123');
  await page.waitForTimeout(50);
  const typed = await page.evaluate(() => ({
    value: document.getElementById('encsrc-man-input').value,
    activeAfter: document.activeElement && (document.activeElement.id || document.activeElement.tagName),
  }));

  // Also test the "type immediately after open" sequence (focus-steal window).
  await page.evaluate(() => { closeDrawer && closeDrawer(); });
  await page.waitForTimeout(50);
  await page.evaluate(() => {
    openRecLigne(0, 0, false);
    const t = document.querySelector('.ed-tab[data-edpane="integrations"]');
    if (t) edTab(t);
    encsrcMode('man');
    document.getElementById('encsrc-man-input').focus();
  });
  // type during the 80ms focus-steal window (immediately)
  await page.keyboard.type('789');
  await page.waitForTimeout(200);
  const typedEarly = await page.evaluate(() => ({
    value: document.getElementById('encsrc-man-input').value,
    activeAfter: document.activeElement && (document.activeElement.id || document.activeElement.tagName),
  }));

  console.log(JSON.stringify({ diag, typed, typedEarly }, null, 2));
  if (logs.length) console.log('--- page logs ---\n' + logs.join('\n'));
  await browser.close();
})();
