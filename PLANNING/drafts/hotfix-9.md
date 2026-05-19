---
sprint: 9
project: window-quoting
drafted_by: Jade
research_refs: []
content_refs: []
audited_by: Inquisitor
audit_status: pending_reaudit
status: draft
created: 2026-05-17
revised: 2026-05-19
phase: Build
---

# Hotfix 9 — Tailwind CDN Migration + Mobile Nav (Blocked behind Hotfix 8)

*Revised 2026-05-19: Bug 5 (mobile nav overflow) folded in from post-promotion Hotfix-8 addition. Sent back for re-audit by Chris.*

---

## Current State

### Bug 3: Tailwind CDN in Production

All 17 templates load `<script src="https://cdn.tailwindcss.com">`. This is the development-only CDN build. It:
- Compiles Tailwind in the browser at runtime (~300KB JS download + compile time)
- Requires `cdn.tailwindcss.com` in CSP `script-src` (widens attack surface)
- Is noticeably slower on mobile devices

**Current code (in all 17 templates):**
```html
<script src="https://cdn.tailwindcss.com"></script>
```

**CSP configuration (in `app.py`):**
```python
# Contains cdn.tailwindcss.com in script-src - exact line TBD, needs enumeration
```

### Bug 5: Mobile Nav Bar Overflow (added 2026-05-19, post-Hotfix-8-promotion)

**Discovered:** Chris on Android Chrome viewing `panefreequoting.com` after Hotfix 8 was promoted to ACTIVE. The bug only manifests on real mobile devices viewing `index.html` (which already has a viewport meta tag — so this is independent of Bug 1).

**Symptoms:** On mobile widths (~375-414px), the top nav row in `_nav.html` does not collapse or wrap. The right-side links (`Account`, `Buy Credits`, `Sign out`) overflow the viewport and are clipped behind a fade — mobile users cannot reach account management, top-up, or sign out from the nav.

**Affected partial:** `templates/_nav.html` (included by all 17 templates — single-file fix covers every page).

**Likely cause:** Nav uses a single-row horizontal flex layout sized for desktop. No mobile breakpoint, no hamburger pattern, no `flex-wrap`, no `overflow-x-auto` fallback.

**Sprint placement rationale:** Originally added to Hotfix 8 post-promotion, then moved here so Inquisitor can re-audit the addition without blocking Hotfix 8 execution.

---

## Bug 3: Tailwind CDN → Compiled CSS (MEDIUM)

**Severity:** 🟡 MEDIUM - performance and security improvement, not a bug
**Impact:** Slower page loads, wider CSP attack surface, runtime compilation on mobile

### Fix
1. Create `tailwind.config.js` and `package.json` in project root
2. Configure content paths to scan all template HTML files
3. Add `safelist` for any dynamically-constructed Tailwind classes (audit templates for `class="...{{ variable }}..."` patterns or JavaScript class construction)
4. Compile Tailwind to static CSS: `npx tailwindcss -i ./static/input.css -o ./static/output.css --minify`
5. Replace all `<script src="https://cdn.tailwindcss.com"></script>` with `<link rel="stylesheet" href="/static/output.css">` in all 17 templates
6. Remove `cdn.tailwindcss.com` from CSP `script-src` in `app.py`
7. Add Render build step: `npm run build:css`
8. Document build step in `DEPLOYMENT.md`

### Dynamic Class Audit (Required Before Fix)
Search all templates for:
- `class="...{{ variable }}..."` patterns
- JavaScript that constructs class names dynamically
- Any class used in conditional logic (e.g., `classList.add()`, `className = ...`)

Add all found classes to `tailwind.config.js` safelist.

### Acceptance Criteria
- [ ] AC1: `grep -r 'cdn.tailwindcss.com' templates/` returns zero results
- [ ] AC2: CSP `script-src` no longer includes `cdn.tailwindcss.com` - verified by checking response headers
- [ ] AC3: All 17 non-partial templates pass visual comparison against pre-migration screenshots at 375px (mobile) and 1280px (desktop) - no styling differences
- [ ] AC4: All dynamically-constructed Tailwind classes are present in compiled CSS output (verified by checking safelist classes appear in `output.css`)
- [ ] AC5: Page load time improved - baseline measurement taken on `index.html` before migration using browser DevTools Network tab (DOMContentLoaded + Load times), then compared after migration
- [ ] AC6: Build step documented in `DEPLOYMENT.md`
- [ ] AC7: `python -m pytest` passes after migration

### Rollback Plan
If compiled CSS is missing classes or styling breaks:
1. Revert the commit (all 17 template changes + CSP change)
2. Re-enable CDN `<script>` tags
3. Add `cdn.tailwindcss.com` back to CSP `script-src`
4. Rediagnose: check `tailwind.config.js` content paths and safelist

### CSP File Enumeration
CSP configuration is in `app.py` - the exact line(s) containing `cdn.tailwindcss.com` will be enumerated during T3 diagnosis (Sprint 1) and confirmed before this sprint begins.

### Estimated Complexity: M (4-6 hours including dynamic class audit, template changes, CSP update, visual regression testing, and Render build step)

---

## Bug 5: Mobile Nav Bar Overflow (HIGH)

**Severity:** 🟠 HIGH — every mobile user loses access to Account / Buy Credits / Sign out from the nav
**Impact:** Mobile users cannot reach account management, credit top-up, or sign-out via primary navigation. Workaround (URL-typing) is unreasonable for a public quoting tool.

### Fix Plan
Edit `templates/_nav.html` plus a new `static/js/nav.js` to add a **hamburger menu + slide-out drawer** at narrow viewports.

**Why hamburger, not flex-wrap:** Chris's mobile QA on 2026-05-19 showed the nav has too many items (Quote, History, Profiles, Account, Buy Credits, email address display, Sign out) to wrap cleanly. Flex-wrap would produce a 3-row stack that consumes ~30% of the viewport height before any content renders. A drawer keeps the mobile nav to a single header row.

**Approach:**
1. Below `md` breakpoint (Tailwind `< md:`, i.e. < 768px), hide the inline link list. Show: brand on the left, credits pill, hamburger icon on the right.
2. Above `md`, hide the hamburger and show the inline link list (current desktop layout, unchanged).
3. Tapping the hamburger opens a slide-out drawer from the right covering ~80% width, containing the full link list + email + Sign out.
4. Drawer state toggled by a small script in `static/js/nav.js` (NOT inline — must survive Hotfix 9 T3 CSP tightening that removes `unsafe-inline`).
5. Close on: tap outside drawer, tap a link, or press Escape.

**CSP interaction:** During Hotfix 9, T3 removes `unsafe-inline` from CSP. T6 (this fix) must ship its JS in `static/js/nav.js` so it's `'self'`-sourced. If T6 ships *before* T3, the script still works under the looser CSP; T3 then tightens around it.

### Bug 3 / Bug 5 Interaction
Bug 5 fix should land AFTER Bug 3 (Tailwind CDN → compiled CSS) within this sprint, because:
- Bug 3 changes which Tailwind classes are available (compiled vs runtime CDN)
- Any new utility classes added to `_nav.html` (e.g. `flex-wrap`, responsive variants like `md:flex-nowrap`) must be in the compiled CSS output or in the safelist
- Adding Bug 5 classes BEFORE Bug 3 risks them being purged during the CDN migration

### Acceptance Criteria
- [ ] AC1: At 375px and 414px viewports, the nav header fits in a single row: brand + credits pill + hamburger icon. No clipped items.
- [ ] AC2: Tapping the hamburger opens a drawer containing all nav items (`Quote`, `History`, `Profiles`, `Account`, `Buy Credits`, user email, `Sign out`) — every item is tappable with a ≥44px touch target.
- [ ] AC3: Drawer closes on: tap outside, tap a nav link, press Escape.
- [ ] AC4: Desktop nav (≥ 768px) layout is visually unchanged from current production — hamburger is hidden, inline links are shown.
- [ ] AC5: Fix lives in `_nav.html` + `static/js/nav.js` only. No edits to the 17 page templates. No inline `<script>` tags.
- [ ] AC6: Any new Tailwind utility classes (e.g. `md:hidden`, `md:flex`, transform/translate classes for drawer slide) appear in compiled `output.css` or in the safelist — verified by `grep` of `output.css`.
- [ ] AC7: After Hotfix 9 T3 tightens CSP (removes `unsafe-inline`), drawer toggle still works — verified by checking browser console for CSP violations.
- [ ] AC8: Tested on a real Android Chrome device by Chris.

### Rollback
Revert commit. Single-file change to a partial. Zero blast radius beyond the nav.

### Estimated Complexity: S-M (60-90 minutes — hamburger button, drawer markup, `static/js/nav.js` for toggle + outside-click + Escape, two breakpoint visibility classes)

---

## Sprint Plan

**Sprint Type:** Build sprint (infrastructure change)
**Duration:** 1 sprint (1 day)

| Task | Bug | Priority | Complexity | Assignee |
|------|-----|----------|------------|----------|
| T1 | Dynamic class audit - search templates for dynamically-constructed classes (include `_nav.html` flex-wrap classes for Bug 5) | Bug 3 + Bug 5 | S | Jade |
| T2 | Set up Tailwind build pipeline (`tailwind.config.js`, `package.json`, safelist) + Render build step + document in DEPLOYMENT.md | Bug 3 | M | Claude |
| T3 | Replace CDN `<script>` with compiled `<link>` in all 17 templates + update CSP: remove `cdn.tailwindcss.com` from `script-src` | Bug 3 | M | Claude |
| T4 | Visual regression: compare all 17 pages at 375px and 1280px against pre-migration screenshots | Bug 3 | S | Chris |
| T5 | Performance comparison: measure page load before/after on index.html | Bug 3 | S | Chris |
| T6 | Fix mobile nav: hamburger + slide-out drawer in `_nav.html` + new `static/js/nav.js` (CSP-safe, externalized script). Verify new Tailwind classes are in compiled CSS. | Bug 5 | S-M | Claude |
| T7 | Mobile nav QA: real Android device, 320px/375px/414px/768px/1280px — all links reachable, no clipping | Bug 5 | S | Chris |

**Execution Order:** T1 → T2 → T3 → T4 → T5 → T6 → T7

**Bug 3/Bug 5 ordering:** T6 (nav fix) runs AFTER T3 (CDN migration) so any new Tailwind classes used in `_nav.html` are guaranteed to be in the compiled output.

**Regression Gate:** `python -m pytest` must pass after each task.

---

*This sprint is blocked behind Sprint 1 (Bug 1 + Bug 2 + Bug 4). If Bug 2's root cause is confirmed as Tailwind CDN blocking, this sprint becomes urgent and may be reprioritized.*

*Inquisitor re-audit applied: N1 (Sprint 2 task cap reduced to 5 by merging T3+T4 and T2+T5), N2 (CSP documentation step added to Sprint 1 T3). Prior audit: R1 (separated from hardening sprint), R4 (falsifiable ACs), R5 (baseline measurement), R6 (rollback plan), R7 (dynamic class audit), R8 (CSP file enumeration), R14 (regression gate).*

*2026-05-19 revision: Bug 5 (mobile nav overflow) added — discovered post-Hotfix-8 promotion. Task count expanded from 5 to 7. `audit_status` reset to `pending_reaudit` — Inquisitor needs to re-bless before this sprint begins.*

*2026-05-19 update (post Hotfix-8 T2 QA): Bug 5 fix path locked to hamburger + drawer (not flex-wrap). Chris's mobile QA confirmed the nav has too many items to wrap cleanly. JS must be externalized to `static/js/nav.js` so it survives T3's CSP tightening. Complexity bumped S → S-M.*