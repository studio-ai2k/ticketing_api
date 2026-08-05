// Shared mock API routing + helpers for the budget _x harness.
const CHROME = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';

// One recette category with one row (has a name → encsrc key resolves).
// est_ht so the line has a prévu; reel_ht so encaissé shows a number.
function recettesJSON() {
  return {
    data: [
      { section: 'BILLETTERIE', ligne: 'Prévente Dice', qte: 500, pu: 25,
        est_ht: 12500, tva: '0.2', reel_ht: 8000, statut: 'EN COURS', _row: 2 },
    ],
  };
}

// One dépense dept with one section + one line so the budget renders.
function budgetJSON() {
  return {
    data: {
      PRODUCTION: [
        { section: 'GÉNÉRAL', ligne: 'Régie générale', observations: '',
          typ: 'G', tva: '0.2', est_ht: 4000, rh: 'C', reel_ht: 1200,
          statut: 'EN COURS', _row: 2 },
      ],
    },
  };
}

async function installMock(page) {
  await page.route('**/api/**', async (route) => {
    const url = route.request().url();
    let body = { data: [] };
    if (url.includes('/api/recettes')) body = recettesJSON();
    else if (url.includes('/api/budget')) body = budgetJSON();
    else if (url.includes('/api/unmatched')) body = { data: [] };
    else if (url.includes('/api/qonto-raw')) body = { data: [] };
    else if (url.includes('/api/match-log')) body = { data: [] };
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });
  });
}

module.exports = { CHROME, installMock, recettesJSON, budgetJSON };
