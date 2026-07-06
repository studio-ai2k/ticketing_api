const { chromium } = require('playwright');
const path = require('path');
const { CHROME, installMock } = require('./mock');
const FILE = process.argv[2];

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await installMock(page);
  await page.goto('file://' + path.resolve(FILE), { waitUntil: 'networkidle' });
  await page.waitForFunction(() => typeof REC !== 'undefined' && REC.length > 0);
  const R = {};

  // open drawer, go to integrations, click Saisie manuelle segment
  await page.evaluate(() => { openRecLigne(0,0,false);
    const t=document.querySelector('.ed-tab[data-edpane="integrations"]'); if(t) edTab(t); });
  await page.click('.encsrc .seg-opt[data-mode="man"]');
  await page.waitForTimeout(250);

  // (1) TYPE WITHOUT CLICKING — the core repro. Should now land in the input.
  R.focusAfterSwitch = await page.evaluate(()=>document.activeElement && (document.activeElement.id||document.activeElement.tagName));
  await page.keyboard.type('1500');
  await page.waitForTimeout(40);
  R.typeWithoutClick = await page.evaluate(()=>({value:document.getElementById('encsrc-man-input').value,
    active:document.activeElement&&(document.activeElement.id||document.activeElement.tagName)}));

  // (2) mission diagnostic
  R.diag = await page.evaluate(() => {
    const i = document.getElementById('encsrc-man-input'); const r=i.getBoundingClientRect();
    const hit = document.elementFromPoint(r.left+r.width/2, r.top+r.height/2); i.focus();
    return { hitIsInput:hit===i, hitId:hit&&hit.id, pointerEvents:getComputedStyle(i).pointerEvents,
      focusLanded:document.activeElement===i, paneAnim:getComputedStyle(i.closest('.encsrc-mode')).animationName };
  });

  // (3) clear + click-then-type still works
  await page.evaluate(()=>{const i=document.getElementById('encsrc-man-input'); i.value=''; i.dispatchEvent(new Event('input',{bubbles:true}));});
  await page.click('#encsrc-man-input');
  await page.keyboard.type('789');
  R.clickThenType = await page.evaluate(()=>document.getElementById('encsrc-man-input').value);

  // (4) tx / api modes unaffected (no error, panes toggle)
  await page.evaluate(()=>encsrcMode('tx'));
  R.txMode = await page.evaluate(()=>({txOn:document.querySelector('.encsrc-mode[data-mode="tx"]').classList.contains('on'),
    active:document.activeElement&&(document.activeElement.id||document.activeElement.tagName)}));
  await page.evaluate(()=>encsrcMode('api'));
  R.apiMode = await page.evaluate(()=>document.querySelector('.encsrc-mode[data-mode="api"]').classList.contains('on'));

  // (5) restore path: seed man value, close, reopen -> restore to man (integrations hidden -> focus no-op, no error)
  await page.evaluate(()=>{encsrcMode('man'); const i=document.getElementById('encsrc-man-input'); i.value='300'; i.dispatchEvent(new Event('input',{bubbles:true}));});
  await page.waitForTimeout(40);
  await page.evaluate(()=>closeDrawer());
  await page.waitForTimeout(50);
  R.restoreNoError = await page.evaluate(()=>{ try { openRecLigne(0,0,false); return 'ok'; } catch(e){ return 'ERR:'+e.message; } });
  R.restoredMan = await page.evaluate(()=>document.querySelector('.encsrc-mode[data-mode="man"]').classList.contains('on'));

  console.log(JSON.stringify(R, null, 2));
  await browser.close();
})();
