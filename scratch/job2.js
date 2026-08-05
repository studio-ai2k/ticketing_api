const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');
const { CHROME, installMock } = require('./mock');
const FILE = process.argv[2] || 'budget_pa_x_e6c350be_BUILD60.html';
const DIR = 'shots';
fs.mkdirSync(DIR, { recursive: true });

const shot = async (locator, name) => { await locator.screenshot({ path: `${DIR}/${name}.png` }); console.log('  shot ->', name); };

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 2 });
  await installMock(page);
  await page.goto('file://' + path.resolve(FILE), { waitUntil: 'networkidle' });
  await page.waitForFunction(() => typeof REC !== 'undefined' && REC.length > 0);
  const report = {};

  // ============ 1. RECETTE DRAWER — MANUELLE (€ left of input) ============
  await page.evaluate(() => { openRecLigne(0,0,false);
    const t=document.querySelector('.ed-tab[data-edpane="integrations"]'); if(t) edTab(t); });
  await page.click('.encsrc .seg-opt[data-mode="man"]');
  await page.keyboard.type('4200');           // fix in action: caret already in field
  await page.waitForTimeout(250);
  await shot(page.locator('.encsrc'), '1_recette_manuelle');
  report.manuelle = await page.evaluate(()=>{
    const cur=document.querySelector('.encsrc-manual .cur'), inp=document.getElementById('encsrc-man-input');
    return { euroFontSize:getComputedStyle(cur).fontSize, inputFontSize:getComputedStyle(inp).fontSize,
      euroPE:getComputedStyle(cur).pointerEvents, value:inp.value };
  });
  await page.evaluate(()=>closeDrawer());
  await page.waitForTimeout(60);

  // ============ 2. RÉELLES DRAWER — NOTE TAB (read-only note, NOT the glossary) ============
  // with a note
  await page.evaluate(() => {
    const d = DEPTS.find(x=>x.id==='production'); d.sections[0].lines[0].obs = 'Devis relancé le 12/03. Attente retour régie — prévoir marge +5% carburant.';
    openReelDrawer('production',0,0);
  });
  await page.click('.reel-tab[data-pane="notes"]');
  await page.waitForTimeout(200);
  await shot(page.locator('.reel-pane[data-pane="notes"]'), '2a_reelles_note');
  report.noteWith = await page.evaluate(()=>{
    const p=document.querySelector('.reel-pane[data-pane="notes"]');
    return { text:(p.querySelector('textarea')||{}).value||null, hasGlossary:/Externe|Inter-soci|Intra/.test(p.textContent) };
  });
  await page.evaluate(()=>closeDrawer());
  await page.waitForTimeout(60);
  // without a note -> "Aucune note"
  await page.evaluate(() => {
    const d = DEPTS.find(x=>x.id==='production'); d.sections[0].lines[0].obs = '';
    openReelDrawer('production',0,0);
    const b=[...document.querySelectorAll('.reel-tab')].find(t=>t.dataset.pane==='notes'); reelTab(b);
  });
  await page.waitForTimeout(200);
  await shot(page.locator('.reel-pane[data-pane="notes"]'), '2b_reelles_note_empty');
  report.noteEmpty = await page.evaluate(()=>document.querySelector('.reel-pane[data-pane="notes"]').textContent.replace(/\s+/g,' ').trim());
  await page.evaluate(()=>closeDrawer());
  await page.waitForTimeout(60);

  // ============ 3. DEVIS "LIEN OU NOTE" — URL / note / <b>test / empty ============
  await page.evaluate(() => {
    openEditLigne('production',0,0);
    const t=[...document.querySelectorAll('.ed-tab')].find(x=>x.dataset.edpane==='devis'); if(t) edTab(t);
  });
  await page.waitForTimeout(150);
  // Build 4 expanded devis rows, one per lien state, into the devis pane list.
  report.devisEscape = await page.evaluate(() => {
    const pane = document.querySelector('.ed-pane[data-edpane="devis"]');
    const states = [
      { lbl:'URL',        lien:'https://drive.google.com/devis-scene-042' },
      { lbl:'Note libre', lien:'Devis papier reçu en main propre — à scanner' },
      { lbl:'<b>test',    lien:'<b>test' },
      { lbl:'(vide)',     lien:'' },
    ];
    const rows = states.map((s,i)=> _devisRowHTML({ fournisseur:'Fournisseur '+s.lbl, ht:3300, tva:'0.2',
      statut:'recu', date:'2026-03-0'+(i+1), ref:'REF-'+i, lien:s.lien }, i))
      .join('');
    const host = document.createElement('div');
    host.style.cssText = 'padding:16px;display:flex;flex-direction:column;gap:12px;background:var(--bg,#0c0c12)';
    host.innerHTML = rows;
    host.querySelectorAll('.split-row').forEach(r=>r.classList.add('expanded'));
    pane.innerHTML = ''; pane.appendChild(host);
    // escaping check: the <b>test row's Lien cell must contain literal text, no real <b> element
    const rowsEls = host.querySelectorAll('.split-row');
    const lienCellOf = (r)=>[...r.querySelectorAll('.dt-kv .kv')].find(kv=>kv.querySelector('.k')&&kv.querySelector('.k').textContent==='Lien');
    const btRow = rowsEls[2], btCell = lienCellOf(btRow).querySelector('.v');
    const urlCell = lienCellOf(rowsEls[0]).querySelector('.v');
    const emptyCell = lienCellOf(rowsEls[3]).querySelector('.v');
    return {
      bt_text: btCell.textContent, bt_hasBoldEl: !!btCell.querySelector('b'), bt_innerHTML: btCell.innerHTML,
      url_isLink: !!urlCell.querySelector('a'), url_linkText: (urlCell.querySelector('a')||{}).textContent,
      empty_text: emptyCell.textContent.trim(),
    };
  });
  await page.waitForTimeout(150);
  await shot(page.locator('.ed-pane[data-edpane="devis"]'), '3_devis_lien_states');
  await page.evaluate(()=>closeDrawer());
  await page.waitForTimeout(60);

  // ============ 4. COURBE "Consommation dans le temps" — n=0 / n=1 no budget / n=2 ============
  const renderCourbe = async (opts, name) => {
    await page.evaluate((o) => {
      openReelDrawer('production',0,0);
      document.getElementById('reel-pane-courbe').innerHTML = courbe(o);
    }, opts);
    await page.waitForTimeout(300);
    await shot(page.locator('#reel-pane-courbe'), name);
    await page.evaluate(()=>closeDrawer());
    await page.waitForTimeout(60);
  };
  await renderCourbe({ points: [], ceiling: 0, mode:'depense' }, '4a_courbe_n0_empty');
  await renderCourbe({ points: [{date:'05/03/26', cum:1800, amt:1800, fourn:'Scène Pro'}], ceiling: 0, mode:'depense' }, '4b_courbe_n1_nobudget');
  await renderCourbe({ points: [
      {date:'05/03/26', cum:1800, amt:1800, fourn:'Scène Pro'},
      {date:'19/03/26', cum:4200, amt:2400, fourn:'Barrières Loc'}], ceiling: 0, mode:'depense' }, '4c_courbe_n2_curve');

  // n=1 no-budget: measure the dot's vertical position (should be ~55% down from top of chart area)
  report.courbe_n1_dotPct = await page.evaluate(() => {
    document.getElementById('drawer-body') || openReelDrawer('production',0,0);
    openReelDrawer('production',0,0);
    document.getElementById('reel-pane-courbe').innerHTML = courbe({ points:[{date:'05/03/26',cum:1800,amt:1800,fourn:'X'}], ceiling:0, mode:'depense' });
    const dot = document.querySelector('#reel-pane-courbe circle:last-of-type');
    const cy = parseFloat(dot.getAttribute('cy'));
    // chart area: top=16, base=224, span=208
    return { cy, pctFromTop: Math.round((cy-16)/208*100) };
  });
  await page.evaluate(()=>closeDrawer());

  // reste-à-décaisser doubling check: engagé scenario (n=2 with engage) — count occurrences
  report.resteCheck = await page.evaluate(() => {
    openReelDrawer('production',0,0);
    document.getElementById('reel-pane-courbe').innerHTML = courbe({
      points:[{date:'05/03/26',cum:1800,amt:1800,fourn:'A'},{date:'19/03/26',cum:4200,amt:2400,fourn:'B'}],
      ceiling:0, engage:9000, mode:'depense' });
    const pane = document.getElementById('reel-pane-courbe');
    const callouts = pane.querySelectorAll('.cx-callout').length;
    const txt = pane.textContent;
    const count = (txt.match(/reste à décaisser/g)||[]).length;
    return { calloutEls: callouts, resteMentions: count };
  });
  await page.evaluate(()=>closeDrawer());

  console.log('\n=== JOB 2 assertions ===');
  console.log(JSON.stringify(report, null, 2));
  await browser.close();
})();
