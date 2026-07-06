# FIX-2 + deploy-look report — Build 60

**Base:** `budget_pa_x_04495da6_BUILD59.html` (md5 `04495da65d48ba354e543c6aa618f8fd`)
**Patched:** `budget_pa_x_e6c350be_BUILD60.html` (md5 `e6c350beaa0d59f9372a45ac95bb8d77`)
**Diff:** one hunk, +4 lines inside `encsrcMode()` (L3369). No frozen leaf touched. Stays unsealed.

Rendered in real headless Chromium (Playwright, pre-installed chromium-1194) with a mocked
`/api/*` contract (one recette line + one dépense line). Harness in `scratch/`.

---

## JOB 1 — the "won't let me type" bug

### Diagnostic (real Chromium)

Running the mission's `elementFromPoint` probe with the Intégrations tab active and the manual
pane visible, the input itself is **healthy**:

```
hitIsInput   : true          (elementFromPoint at the input centre === the input)
pointerEvents: auto
focusLanded  : true          (i.focus() lands)
paneAnim     : eFade         paneTransform: none
```

So **neither** the overlay branch (`hitIsInput === false`) nor a focus-*steal* fires. I chased the
suspected `ef-nom` autofocus (`setTimeout(… ef-nom.focus(), 80)`, L3907) and it is a **dead no-op in
edit mode**: `ef-nom` lives in the `reglages` pane, which is `display:none` on open (default tab =
Détails / Intégrations), so `.focus()` never moves focus. `document.activeElement` stays `BODY`
through the whole 80 ms window. Not the culprit.

### Actual repro (the geometry jsdom couldn't see was a red herring — it's a focus-placement bug)

Driving the **real user path** — open recette drawer → Intégrations tab → click the **"Saisie
manuelle"** segment → type without first clicking the field:

```
BASE (Build 59):
  focus after switching to manual : BUTTON      ← the seg-opt just clicked keeps focus
  type "1500" (no manual click)   : value=""    ← keystrokes swallowed  → "won't let me type"
```

`encsrcMode('man')` reveals the input but **never puts the caret in it**; focus stays on the segment
button (or on `BODY` when the mode is restored at open). The now-visible field looks focusable but
eats every keystroke until the user explicitly clicks into it.

### The fix (minimal, at the manual-input site)

`encsrcMode()` — after the pane toggle/sync, focus the manual input when `man` becomes active:

```js
// FIX-2: switching to Saisie manuelle must place the caret in the manual input. Otherwise focus
// stays on the segment button just clicked (or on BODY when the mode is restored at open) and the
// now-visible field silently swallows keystrokes — the "won't let me type" bug. Hidden pane → no-op.
if (mode === 'man'){ const _mi = document.getElementById('encsrc-man-input'); if (_mi) _mi.focus(); }
```

`focus()` on a hidden field (the restore-at-open case, where the Intégrations pane isn't shown yet)
is a silent no-op, so there is no scroll-jump or side effect on the tx/api modes.

### Passing type-test evidence (Build 60)

```
focus after switching to manual : encsrc-man-input   ← caret now lands
type "1500" (no manual click)   : value="1500"       ← FIXED
mission diagnostic              : hitIsInput=true, focusLanded=true, paneAnim=eFade
click-then-type                 : "789"   (still works)
tx / api modes                  : toggle fine, no error
restore-at-open (man seeded)    : reopens ok, restoredMan=true, no error
```

Watched pass in Chromium — see `scratch/verify.js`.

### Seal / scope

- Diff = the 4 lines above only; everything else byte-identical (`diff` in the commit).
- None of the 9 frozen leaves (`assignedCard`, `money2`, `tcFoot`, `transactionCard`, `expandRow`,
  `txCountHeader`, `_reelCls`, `_reelTxToCard`, `formatQontoDate`) touched — all live at L4746+, far
  from the edit site. File stays unsealed. (No `seal_boundary.js` shipped in the repo to run.)

---

## JOB 2 — deploy-look screenshots (`shots/`)

| # | file | verdict |
|---|------|---------|
| 1 | `1_recette_manuelle.png` | Manuelle pane. **€ sits left of the input, small (13 px) — not oversized**; input is 16 px, right-aligned; `.cur` is `pointer-events:none`. Screenshot shows `4200` typed straight after the segment click (the fix in action). |
| 2a | `2a_reelles_note.png` | Réelles **Note tab = the line's note, read-only** ("Devis relancé le 12/03…"). `hasGlossary=false` — **not** the Externe/Intra/Inter glossary. |
| 2b | `2b_reelles_note_empty.png` | No note → **"Aucune note"**. |
| 3 | `3_devis_lien_states.png` | Devis "Lien ou note": **URL → clickable "Ouvrir le devis"**; plain note → text; **`<b>test` → rendered literally** (`innerHTML` = `&lt;b&gt;test`, no `<b>` element, not bold); empty → **em-dash**. |
| 4a | `4a_courbe_n0_empty.png` | n=0 → "Aucune dépense reliée pour l'instant", stats all `—`. |
| 4b | `4b_courbe_n1_nobudget.png` | **The key one.** 1 transaction, no budget → the point sits **mid-chart**, not pinned to the top. Dot `cy=109.6` on the `top=16 / base=224 / span=208` axis = **55 % up from the base** (45 % from top), exactly the `yMax = maxCum/0.55` guard. |
| 4c | `4c_courbe_n2_curve.png` | n=2 → rising cumulative curve, Première/Dernière/Pic stats. 0→1→2 escalation visible across 4a/4b/4c. |

**reste-à-décaisser doubling check** (n=2 with `engage`): `.cx-callout` count = **1** (callout not
doubled). The string "reste à décaisser" appears twice total, but in two *distinct* components — the
chart callout ("… sur devis signés") and the "Rythme" stats cell — by design, not a duplicated callout.

### Deploy-look that looked slightly off
- The Manuelle **€** glyph is anchored a touch **high** (top-left of the field) rather than vertically
  centred on the input, because `.encsrc-manual .cur { top:50% }` is measured against the whole group
  (label + input), not the input alone. It's small and unobtrusive — reads fine — but if a pixel-tight
  pass wants it dead-centre on the field, that's the one nit. **Not** the typing bug; left untouched
  (JOB 2 is observe-only).
