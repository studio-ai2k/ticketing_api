# Nav Shell Alignment — Spec for CC2

## Objective
Make the ticketing dashboard nav look **pixel-identical** to BudgetFlow's nav. All changes are post-processing on the generated HTML (in `scripts/postprocess_html.py`). Do NOT modify `run.py`, `dashboard_template.html`, or any shared file.

## Reference files in this package
- `budget_event.html` — the source of truth. The nav in this file is what ours must look like.
- `chrome.css` — shared nav styles (for reference only — we hardcode, not link)
- `current_nav.html` — extracted current ticketing nav (what you're replacing)
- `target_nav.html` — extracted BudgetFlow nav (what ours must match)
- `switcher.js` — the exact switcher toggle IIFE to inject
- `switcher.css` — the exact sw-* CSS rules to inject

---

## CHANGE 1: Session switcher — replace `<select>` with dropdown menu

### What to remove
The current session switcher uses a hidden `<select>` overlay:
```html
<div class="nav-sw">
  <div class="nav-sw-av">...</div>
  <div>
    <div style="display:flex;align-items:center;gap:5px">
      <span style="font-size:13px;font-weight:600;color:#fff">{{EVENT_SHORT_NAME}}</span>
      <span style="width:5px;height:5px;...">●</span>
    </div>
    <div style="font-size:10px;color:var(--text-dim);margin-top:3px">{{EVENT_CODE}} · {{J_MINUS_LABEL}}</div>
  </div>
  <svg>chevron</svg>
  <select class="session-sw">...</select>   ← REMOVE THIS
</div>
```

### What to replace it with
```html
<div class="nav-sw sw-wrap" style="position:relative">
  <div class="sw-trigger" data-sw-trigger>
    <div class="nav-sw-av"><img src="{{POSTER_URL}}" alt="{{EVENT_SHORT_INITIALS}}" onerror="this.style.display='none';this.parentNode.textContent='{{EVENT_SHORT_INITIALS}}'"></div>
    <div>
      <div class="nav-sw-name">{{EVENT_SHORT_NAME}}<span class="dot"></span></div>
      <div class="nav-sw-sub">{{EVENT_CODE}} · {{J_MINUS_LABEL}}</div>
    </div>
    <svg class="sw-chev" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="var(--text-dim)" stroke-width="2.5" style="margin-left:2px"><path d="M6 9l6 6 6-6"/></svg>
  </div>
  <div class="sw-menu left" role="menu" aria-label="Changer de session">
    {{SESSION_MENU_ITEMS}}
  </div>
</div>
```

### SESSION_MENU_ITEMS format
Each event in the switcher becomes a `.sw-item`. The active event gets `.active` + checkmark:
```html
<a class="sw-item active" role="menuitem" href="epk.html">
  <span class="sw-label">Elektric Park 2026<span class="sw-sub">EPK 050926 · J-30</span></span>
  <svg class="sw-check" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6L9 17l-5-5"/></svg>
</a>
<a class="sw-item" role="menuitem" href="bordeaux.html">
  <span class="sw-label">Bordeaux Juin 2026<span class="sw-sub">Événement</span></span>
</a>
```

### How to generate the menu items in post-processing
The current HTML already has `<option>` elements from `run.py`'s `{{SESSION_SWITCHER_OPTIONS}}`. Parse those to build the `.sw-item` list:
- Each `<option value="filename.html">Event Name</option>` becomes an `<a class="sw-item" href="filename.html">`
- The option with `selected` attribute gets `.active` class + the checkmark SVG
- The `.sw-sub` text can be "Événement" for all items (or parse from the option text if it contains a code)

### CSS to inject
All rules from `switcher.css` in this package. Inject into the existing `<style>` block in the HTML, after the existing `.nav-sw` rules. The injected rules override the inline-style approach with proper classes.

**IMPORTANT:** Also remove the `.session-sw` CSS rule (the hidden select overlay style):
```css
/* REMOVE THIS */
.session-sw { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0.01; cursor: pointer; z-index: 2; font-size: 16px; }
```

### JS to inject
The full IIFE from `switcher.js` in this package. Inject before `</body>`. This handles:
- Click on `.sw-trigger` toggles dropdown open/close
- Click outside closes dropdown
- Escape key closes dropdown
- Floating menu repositions on scroll/resize (escapes `.nav` overflow clip)

---

## CHANGE 2: Module dropdown — add to the right side of nav

### What exists now
No module dropdown. Just the in-module buttons (Billetterie, Détails).

### What to add
A module-switcher dropdown on the RIGHT side of the nav, positioned BEFORE the user avatar, inside the `margin-left:auto` wrapper. The exact HTML is in `module_dropdown.html` in this package.

Layout after change:
```
[Event ▼]   Billetterie  Détails          [Billetterie ▼] [👤]
 left        middle (in-module)            right (module dropdown + avatar)
```

### Implementation
Replace the current `margin-left:auto` wrapper (which will contain just the avatar after Change 3) with:
```html
<div style="margin-left:auto;display:flex;align-items:center;gap:10px">
  <!-- MODULE DROPDOWN (from module_dropdown.html) -->
  {paste full content of module_dropdown.html here}
  <!-- USER AVATAR -->
  <div class="nav-user" title="Compte" style="margin-left:0">...</div>
</div>
```

The dropdown uses the same `.sw-wrap` / `.sw-trigger` / `.sw-menu` component as the session switcher — the toggle JS from `switcher.js` handles BOTH dropdowns (it targets any `[data-sw-trigger]`).

### CSS to inject (in addition to Change 1's CSS)
The module-specific rules are at the bottom of `switcher.css`:
```css
.sw-item.disabled{cursor:default;color:var(--text-dim)}
.sw-item.disabled:hover{background:transparent;color:var(--text-dim)}
.sw-ico{width:16px;height:16px;flex-shrink:0;opacity:.8}
.mod-trigger{padding:6px 10px;border-radius:8px;border:1px solid rgba(255,255,255,.07);background:var(--surface-2)}
.mod-trigger:hover{border-color:rgba(255,255,255,.14)}
.mod-name{font-size:12px;font-weight:600;color:#fff;white-space:nowrap}
.pill{margin-left:auto;font-size:10px;font-weight:600;padding:2px 8px;border-radius:999px;background:var(--surface-2);border:1px solid var(--border-h);color:var(--text-dim);white-space:nowrap}
.pill.soon{color:var(--amber);border-color:rgba(251,191,36,0.25)}
.pill.unset{color:var(--text-dim)}
```

### Module items (static for now)
- **Événements** — disabled, "bientôt" pill (no events page exists yet for billetterie)
- **Budgetflow** — disabled, "non configuré" pill (no cross-link mapping yet)
- **Billetterie** ✓ — active, green checkmark (this is us)
- **Demande d'Achat** — disabled, "bientôt" pill
- **Partenaires** — disabled, "bientôt" pill

When cross-module links are ready, the disabled items become `<a>` tags with real hrefs.

### Keep the in-module buttons
"Billetterie" and "Détails" buttons in the MIDDLE of the nav stay exactly as they are. They are NOT part of the module dropdown — they control in-page navigation (`goPage()`). Do not remove or move them.

---

## CHANGE 3: User avatar — add to far right

### What to add
Insert this wrapper AFTER the last module button (before the closing `</div>` of `.nav-top`):
```html
<div style="margin-left:auto;display:flex;align-items:center;gap:10px">
  <div class="nav-user" title="Compte" style="margin-left:0"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg></div>
</div>
```

### CSS to inject
The `.nav-user` rule from `chrome.css`:
```css
.nav-user{margin-left:auto;width:36px;height:36px;border-radius:50%;background:var(--surface-2);border:1px solid rgba(255,255,255,.08);display:flex;align-items:center;justify-content:center;cursor:pointer;color:var(--text-muted);transition:opacity .15s;flex-shrink:0}
.nav-user:hover{opacity:.8}
```
Add the mobile override too:
```css
@media(max-width:480px){ .nav-user{width:30px;height:30px} }
```

---

## CHANGE 4: Minor alignment fixes

### max-width
Current ticketing uses `max-width: 980px`. BudgetFlow uses `max-width: 1020px`.
In the injected CSS, override:
```css
.nav-top{max-width:1020px}
.dept-tabs{max-width:1020px}
```

### .dt active state
Current uses `border-bottom-color: var(--day-0)`. BudgetFlow uses `border-bottom: 2px solid #fff; background: rgba(255,255,255,.06)`.
Override:
```css
.dt.on{color:#fff;font-weight:600;border-bottom:2px solid #fff;background:rgba(255,255,255,.06)}
```

---

## Implementation approach

All changes go in `scripts/postprocess_html.py` as a new function (e.g. `align_nav_shell(html)`), called alongside the existing "Mettre à jour" removal and footer change.

The function:
1. Injects the sw-* CSS into the `<style>` block
2. Injects the `.nav-user` CSS into the `<style>` block
3. Injects the max-width and .dt overrides into the `<style>` block
4. Removes the `.session-sw` CSS rule
5. Replaces the `.nav-sw` HTML block with the `.sw-wrap` pattern
6. Parses the existing `<option>` elements to build `.sw-item` menu entries
7. Adds the "Budget" placeholder button
8. Adds the `.nav-user` avatar
9. Injects the switcher toggle IIFE before `</body>`

### Order of operations
Existing post-processing steps run first (footer change, "Mettre à jour" removal, localStorage auth). Nav alignment runs last on the result.

### Test
After implementation, verify in the generated HTML:
- `.sw-wrap` class present on the session switcher
- `.sw-menu` with `.sw-item` entries (one per active event)
- `.sw-check` SVG on the active event only
- `.nav-user` avatar present
- No `<select class="session-sw">` anywhere
- No `.session-sw` CSS rule
- Clicking the switcher area opens the dropdown (not a native select)
- Escape closes it
- Click outside closes it

---

## What NOT to change
- `run.py` — do not modify
- `dashboard_template.html` — do not modify
- `.dept-tabs` section tabs — keep as-is (they're already the right pattern)
- The `goPage('billetterie')` / `goPage('details')` JS — keep as-is
- Any content below the nav — this spec is nav shell ONLY
