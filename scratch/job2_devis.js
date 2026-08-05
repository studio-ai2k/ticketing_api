const { chromium } = require('playwright');
const path = require('path');
const { CHROME, installMock } = require('./mock');
const FILE = process.argv[2] || 'budget_pa_x_e6c350be_BUILD60.html';

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const page = await browser.newPage({ viewport: { width: 900, height: 1400 }, deviceScaleFactor: 2 });
  await installMock(page);
  await page.goto('file://' + path.resolve(FILE), { waitUntil: 'networkidle' });
  await page.waitForFunction(() => typeof REC !== 'undefined' && REC.length > 0);

  await page.evaluate(() => {
    const states = [
      { lbl:'URL → « Ouvrir le devis » (cliquable)', lien:'https://drive.google.com/devis-scene-042' },
      { lbl:'Note libre → texte',                     lien:'Devis papier reçu en main propre — à scanner' },
      { lbl:'<b>test → littéral (échappé, pas gras)',  lien:'<b>test' },
      { lbl:'Vide → tiret cadratin',                   lien:'' },
    ];
    const wrap = document.createElement('div');
    wrap.style.cssText = 'position:fixed;inset:0;z-index:99999;overflow:auto;background:var(--bg,#0c0c12);padding:24px;display:flex;flex-direction:column;gap:20px;font-family:Inter,sans-serif';
    wrap.innerHTML = states.map((s,i)=>
      `<div><div style="font-size:12px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:#8b8b9a;margin-bottom:8px">${_esc(s.lbl)}</div>`
      + _devisRowHTML({ fournisseur:'Scène Pro SARL', ht:3300, tva:'0.2', statut:'recu', date:'2026-03-0'+(i+1), ref:'SP-04'+i, lien:s.lien }, i)
      + `</div>`).join('');
    document.body.appendChild(wrap);
    wrap.querySelectorAll('.split-row').forEach(r=>{ r.classList.add('expanded'); r.style.setProperty('--rc-exp','100vh'); });
    window.__wrap = wrap;
  });
  await page.waitForTimeout(300);
  await page.evaluate(()=>window.__wrap.scrollTo(0,0));
  await page.locator('#\\30').first; // noop
  await page.screenshot({ path: 'shots/3_devis_lien_states.png', fullPage: false });
  console.log('devis shot done');
  await browser.close();
})();
