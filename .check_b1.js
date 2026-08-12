
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROME });
  const out = [];
  for (const spec of process.argv.slice(2)) {
    const [url] = spec.split('|');
    const ctx = await b.newContext({ viewport: { width: 1200, height: 900 } });
    const p = await ctx.newPage();
    const errs = [];
    p.on('pageerror', e => errs.push(String(e).slice(0, 200)));
    await p.goto(url, { waitUntil: 'load' });
    await p.evaluate(() => {
      const i = document.getElementById('db-pw-input');
      if (i) i.value = 'festipass';
      if (typeof dbSubmit === 'function') dbSubmit();
    });
    await p.waitForTimeout(300);

    const names = await p.evaluate(() =>
      (typeof CMAP === 'undefined' ? [] : Object.keys(CMAP)));
    const modes = await p.evaluate(() =>
      (typeof AMODES === 'undefined' ? ['j_minus'] : AMODES.map(m => m.k)));
    const picks = {};
    // MODE OUTSIDE, candidate inside. pickMode re-applies the current
    // candidate, so setting the mode first and then walking the menu exercises
    // both entry points into applySeries rather than only pickCmp's.
    for (const mode of modes) {
    await p.evaluate(async (m) => { await pickMode(m); }, mode);
    await p.waitForTimeout(200);
    for (const n of names) {
      await p.evaluate(async (nm) => { await pickCmp(nm); }, n);
      await p.waitForTimeout(250);
      // The WEEKLY column, read the same way. It was outside every selector
      // this check used - `.sv-l` reaches both grains, but only one grain is
      // ever rendered, and nothing here had switched it. "45 comparisons, row
      // for row" was true of the daily column and silent about the other half.
      const readCol = () => {
        const rows = [...document.querySelectorAll('#suivi .sv:not(.sv-solo)')];
        const num = s => s.replace(/[^0-9]/g, '');
        return rows.map(r => {
          const l = r.querySelector('.sv-l');
          if (!l) return null;
          const d = l.querySelector('.sv-d'), q = l.querySelector('.sv-n');
          const nn = q ? q.cloneNode(true) : null;
          if (nn) nn.querySelectorAll('span').forEach(s => s.remove());
          const txt = nn ? nn.textContent.trim() : '';
          const df = r.querySelector('.sv-c .sv-df');
          return [d ? d.textContent.trim() : '', txt === '—' ? '—' : num(txt),
                  df ? df.textContent.trim() : null];
        }).filter(Boolean);
      };
      await p.evaluate(() => grain('semaine'));
      await p.waitForTimeout(200);
      const weekly = await p.evaluate(readCol);
      await p.evaluate(() => grain('jour'));
      await p.waitForTimeout(200);
      picks[n] = await p.evaluate(() => {
        const rows = [...document.querySelectorAll('#suivi .sv:not(.sv-solo)')];
        const num = s => s.replace(/[^0-9]/g, '');
        return {
          err: (document.querySelector('#suivi .empty-t') || {}).textContent || null,
          rows: rows.map(r => {
            const l = r.querySelector('.sv-l');
            if (!l) return null;
            const d = l.querySelector('.sv-d'), n = l.querySelector('.sv-n');
            const nn = n ? n.cloneNode(true) : null;
            if (nn) nn.querySelectorAll('span').forEach(s => s.remove());
            const txt = nn ? nn.textContent.trim() : '';
            const df = r.querySelector('.sv-c .sv-df');
            return [d ? d.textContent.trim() : '', txt === '—' ? '—' : num(txt),
                    df ? df.textContent.trim() : null];
          }).filter(Boolean),
          header: (document.querySelector('#suivi .sv-h span') || {}).textContent,
        };
      });
      picks[n].weekly = weekly;
      picks[mode + '\u0000' + n] = picks[n];
    }
    }
    out.push({ url, names, modes, picks, errors: errs });
    await ctx.close();
  }
  console.log('@@' + JSON.stringify(out));
  await b.close();
})();
