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

  // ---- recette drawer: where is ef-nom, is it visible? sample activeElement over time ----
  await page.evaluate(() => openRecLigne(0,0,false));
  const rec = { samples: [] };
  for (const t of [5, 30, 60, 85, 110, 150]) {
    await page.waitForTimeout(t - (rec.samples.length? [5,30,60,85,110,150][rec.samples.length-1]:0));
    rec.samples.push({ t, active: await page.evaluate(()=>document.activeElement && (document.activeElement.id||document.activeElement.tagName)) });
  }
  rec.efNom = await page.evaluate(()=>{
    const e = document.getElementById('ef-nom');
    if(!e) return {exists:false};
    const pane = e.closest('.ed-pane');
    return { exists:true, paneEdpane: pane && pane.dataset.edpane, paneOn: pane && pane.classList.contains('on'),
      offsetParentNull: e.offsetParent===null, display: getComputedStyle(pane).display };
  });
  await page.evaluate(()=>closeDrawer());
  await page.waitForTimeout(50);

  // ---- dépense drawer: ef-nom IS visible? open dépense, sample activeElement ----
  await page.evaluate(() => openEditLigne('production', 0, 0));
  const dep = { samples: [] };
  for (const t of [5, 30, 60, 85, 110, 150]) {
    await page.waitForTimeout(t - (dep.samples.length? [5,30,60,85,110,150][dep.samples.length-1]:0));
    dep.samples.push({ t, active: await page.evaluate(()=>document.activeElement && (document.activeElement.id||document.activeElement.tagName)) });
  }
  dep.efNom = await page.evaluate(()=>{
    const e = document.getElementById('ef-nom');
    if(!e) return {exists:false};
    const pane = e.closest('.ed-pane');
    return { exists:true, paneEdpane: pane && pane.dataset.edpane, paneOn: pane && pane.classList.contains('on'),
      offsetParentNull: e.offsetParent===null };
  });

  console.log(JSON.stringify({ rec, dep }, null, 2));
  await browser.close();
})();
