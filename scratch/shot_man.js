const { chromium } = require('playwright');
const path = require('path');
const { CHROME, installMock } = require('./mock');
const FILE = process.argv[2] || 'budget_pa_x_04495da6_BUILD59.html';
const OUT = process.argv[3] || 'scratch/man_pane.png';

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await installMock(page);
  await page.goto('file://' + path.resolve(FILE), { waitUntil: 'networkidle' });
  await page.waitForFunction(() => typeof REC !== 'undefined' && REC.length > 0);

  await page.evaluate(() => { openRecLigne(0,0,false);
    const t=document.querySelector('.ed-tab[data-edpane="integrations"]'); if(t) edTab(t); });
  await page.click('.encsrc .seg-opt[data-mode="man"]');
  await page.waitForTimeout(250);

  // realistic: click into the field, type char-by-char with delay
  await page.click('#encsrc-man-input');
  await page.keyboard.type('4200', { delay: 80 });
  await page.waitForTimeout(100);
  const typed = await page.evaluate(()=>({value:document.getElementById('encsrc-man-input').value,
    active:document.activeElement && (document.activeElement.id||document.activeElement.tagName)}));
  console.log('TYPE TEST:', JSON.stringify(typed));

  // screenshot just the encsrc block
  const el = await page.$('.encsrc');
  await el.screenshot({ path: OUT });
  console.log('shot ->', OUT);
  await browser.close();
})();
