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

  // open recette drawer -> integrations tab -> man mode (via real segment button click)
  await page.evaluate(() => { openRecLigne(0,0,false);
    const t=document.querySelector('.ed-tab[data-edpane="integrations"]'); if(t) edTab(t); });
  // click the "Saisie manuelle" segment button like a user
  await page.click('.encsrc .seg-opt[data-mode="man"]');
  await page.waitForTimeout(300);

  // full element stack at several x-fractions of the input
  const stack = await page.evaluate(() => {
    const i = document.getElementById('encsrc-man-input');
    const r = i.getBoundingClientRect();
    const at = (fx) => {
      const x = r.left + r.width*fx, y = r.top + r.height/2;
      const els = document.elementsFromPoint(x, y);
      return { fx, top: els[0] && (els[0].id||els[0].className||els[0].tagName),
               stack: els.slice(0,4).map(e=> e.id? '#'+e.id : (e.className? '.'+String(e.className).split(' ')[0] : e.tagName)) };
    };
    return { rect:{left:r.left,top:r.top,w:r.width,h:r.height}, points:[0.05,0.2,0.5,0.8,0.95].map(at) };
  });

  // REAL mouse click at center, then keyboard type
  const r = stack.rect;
  await page.mouse.click(r.left + r.w/2, r.top + r.h/2);
  await page.waitForTimeout(30);
  const afterClick = await page.evaluate(()=>({active: document.activeElement && (document.activeElement.id||document.activeElement.tagName)}));
  await page.keyboard.type('456');
  await page.waitForTimeout(50);
  const typed = await page.evaluate(()=>({ value: document.getElementById('encsrc-man-input').value,
    active: document.activeElement && (document.activeElement.id||document.activeElement.tagName)}));

  console.log(JSON.stringify({ stack, afterClick, typed }, null, 2));
  await browser.close();
})();
