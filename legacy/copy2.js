
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROME });
  const ctx = await b.newContext({ viewport:{width:1200,height:900} });
  const p = await ctx.newPage();
  await p.goto(process.env.URL);
  await p.evaluate(() => { const i=document.getElementById('db-pw-input');
    if(i) i.value='festipass'; if(typeof dbSubmit==='function') dbSubmit(); });
  await p.waitForTimeout(1500);
  for (const n of await p.evaluate(() => Object.keys(CMAP))) {
    await p.evaluate(async nm => { await pickCmp(nm); }, n);
    await p.waitForTimeout(320);
    const r = await p.evaluate(() => {
      const note = document.querySelector('#suivi .sec-note');
      const s = SERIES[CMAP[CSEL].id];
      const cells = [...document.querySelectorAll('#suivi .sv:not(.sv-solo) .sv-l .sv-n')];
      return { live: !!(s && s.live),
               says: /édition EN COURS/.test(note ? note.textContent : ''),
               dash: cells.filter(x => x.textContent.trim() === '—').length,
               rows: cells.length };
    });
    console.log(`${n.padEnd(26)} live=${r.live?'Y':'n'}  copy=${r.says?'SHOWN':'-    '}  em-dash ${r.dash}/${r.rows}`);
  }
  await p.evaluate(async () => { await pickCmp('Elektric Park 2026'); });
  await p.waitForTimeout(300);
  await p.evaluate(async () => { await pickMode('days_since_launch'); });
  await p.waitForTimeout(500);
  console.log('\nsame live candidate under days_since_launch: copy=' +
    await p.evaluate(() => { const n=document.querySelector('#suivi .sec-note');
      return /édition EN COURS/.test(n?n.textContent:'') ? 'SHOWN' : 'hidden'; }) +
    '  em-dash ' + await p.evaluate(() => {
      const c=[...document.querySelectorAll('#suivi .sv:not(.sv-solo) .sv-l .sv-n')];
      return c.filter(x=>x.textContent.trim()==='—').length + '/' + c.length; }));
  await b.close();
})();
