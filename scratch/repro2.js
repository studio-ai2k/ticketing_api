const { chromium } = require('playwright');
const path = require('path');
const { CHROME, installMock } = require('./mock');

const FILE = process.argv[2] || 'budget_pa_x_04495da6_BUILD59.html';

async function openMan(page) {
  await page.evaluate(() => {
    openRecLigne(0, 0, false);
    const t = document.querySelector('.ed-tab[data-edpane="integrations"]');
    if (t) edTab(t);
  });
}

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await installMock(page);
  await page.goto('file://' + path.resolve(FILE), { waitUntil: 'networkidle' });
  await page.waitForFunction(() => typeof REC !== 'undefined' && REC.length > 0, { timeout: 8000 });

  const results = {};

  // ---- Scenario A: fresh open, switch to man by CLICK, type immediately (no wait) ----
  await openMan(page);
  await page.evaluate(() => encsrcMode('man'));
  // focus + type immediately (within the 80ms focus-steal window)
  await page.evaluate(() => document.getElementById('encsrc-man-input').focus());
  await page.keyboard.type('11');
  await page.waitForTimeout(150);
  results.A_clickThenTypeImmediate = await page.evaluate(() => ({
    value: document.getElementById('encsrc-man-input').value,
    active: document.activeElement && (document.activeElement.id || document.activeElement.tagName),
  }));
  await page.evaluate(() => closeDrawer());
  await page.waitForTimeout(60);

  // ---- Scenario B: seed a saved man value, close, REOPEN (restore→man), type immediately ----
  // seed value
  await openMan(page);
  await page.evaluate(() => {
    encsrcMode('man');
    const i = document.getElementById('encsrc-man-input');
    i.value = '250'; i.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await page.waitForTimeout(60);
  await page.evaluate(() => closeDrawer());
  await page.waitForTimeout(60);
  // reopen: encsrcRestore should restore man mode automatically
  await page.evaluate(() => {
    openRecLigne(0, 0, false);
    const t = document.querySelector('.ed-tab[data-edpane="integrations"]');
    if (t) edTab(t);
  });
  results.B_restoredModeAtOpen = await page.evaluate(() => {
    const man = document.querySelector('.encsrc-mode[data-mode="man"]');
    return { manOn: man && man.classList.contains('on'), active: document.activeElement && (document.activeElement.id||document.activeElement.tagName) };
  });
  // now focus the input and type immediately (0ms after tab shown)
  await page.evaluate(() => document.getElementById('encsrc-man-input').focus());
  await page.keyboard.type('99');
  await page.waitForTimeout(200);
  results.B_restoreThenType = await page.evaluate(() => ({
    value: document.getElementById('encsrc-man-input').value,
    active: document.activeElement && (document.activeElement.id || document.activeElement.tagName),
  }));

  // ---- Scenario C: open, click man, DON'T focus manually — just type via keyboard.press right after,
  //      checking what has focus at 20/60/100/120ms after open ----
  await page.evaluate(() => closeDrawer());
  await page.waitForTimeout(60);
  const focusTrace = [];
  await page.evaluate(() => { window.__ft = []; openRecLigne(0,0,false);
    const t=document.querySelector('.ed-tab[data-edpane="integrations"]'); if(t) edTab(t);
    encsrcMode('man'); document.getElementById('encsrc-man-input').focus();
  });
  for (const t of [10, 40, 70, 90, 120, 160]) {
    await page.waitForTimeout(t - (focusTrace.length ? [10,40,70,90,120,160][focusTrace.length-1] : 0));
    focusTrace.push({ t, active: await page.evaluate(() => document.activeElement && (document.activeElement.id||document.activeElement.tagName)) });
  }
  results.C_focusTrace = focusTrace;

  console.log(JSON.stringify(results, null, 2));
  await browser.close();
})();
