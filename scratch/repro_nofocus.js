const { chromium } = require('playwright');
const path = require('path');
const { CHROME, installMock } = require('./mock');
const FILE = process.argv[2] || 'budget_pa_x_04495da6_BUILD59.html';

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await installMock(page);
  await page.goto('file://' + path.resolve(FILE), { waitUntil: 'networkidle' });
  await page.waitForFunction(() => typeof REC !== 'undefined' && REC.length > 0);

  // realistic user: open recette drawer, go to Intégrations, click "Saisie manuelle"
  await page.evaluate(() => { openRecLigne(0,0,false);
    const t=document.querySelector('.ed-tab[data-edpane="integrations"]'); if(t) edTab(t); });
  await page.click('.encsrc .seg-opt[data-mode="man"]');
  await page.waitForTimeout(250);

  const beforeType = await page.evaluate(()=>({
    active: document.activeElement && (document.activeElement.id||document.activeElement.tagName),
    manInputExists: !!document.getElementById('encsrc-man-input'),
  }));

  // USER TYPES WITHOUT CLICKING THE FIELD (they just switched to manual and start typing)
  await page.keyboard.type('1500');
  await page.waitForTimeout(50);
  const afterType = await page.evaluate(()=>({
    value: document.getElementById('encsrc-man-input').value,
    active: document.activeElement && (document.activeElement.id||document.activeElement.tagName),
  }));

  console.log(JSON.stringify({ beforeType, afterType }, null, 2));
  await browser.close();
})();
