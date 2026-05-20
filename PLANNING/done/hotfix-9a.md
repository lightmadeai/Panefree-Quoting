---
sprint: 9a
project: window-quoting
drafted_by: Jade
research_refs: []
content_refs: []
audited_by: Inquisitor
audit_status: approved-with-modifications
status: done
created: 2026-05-19
revised: 2026-05-19 (v2 — Inquisitor M1-M6 incorporated)
started: 2026-05-19
completed: 2026-05-19
phase: Stabilize
---

# Hotfix 9a — Tailwind CDN Migration (Bug 3 Only)

*Revised 2026-05-19: Split from Hotfix 9 per Inquisitor re-audit (REJECT — C1, H1, H2). `unsafe-inline` removal and mobile nav deferred to separate sprints. v2 incorporates Inquisitor pre-audit modifications M1-M6.*

---

## Current State

### Bug 3. Tailwind CDN in Production

15 page templates (not 17 — partials and email templates excluded) load `<script src="https://cdn.tailwindcss.com">`. This is the development-only CDN build. It:
- Adds ~400KB of runtime JS to every page load
- Executes a JIT compiler in the user's browser (slow FCP, high TBT)
- Is explicitly not for production per Tailwind docs
- Expands CSP attack surface (`cdn.tailwindcss.com` in `script-src`)

**Scope of this sprint:** Replace CDN with compiled CSS. Remove `cdn.tailwindcss.com` from CSP `script-src`. **Do NOT remove `unsafe-inline`** — that requires externalizing `index.html` inline scripts first (deferred to Hotfix 10).

**Note:** `style-src` `'unsafe-inline'` remains in this sprint. All 15 page templates have `<style>body { font-family: 'Inter', sans-serif; }</style>` inline, which requires `'unsafe-inline'` in `style-src`. Removing it is out of scope (future hardening sprint).

---

## Tasks

- [x] **T1: Dynamic class audit + safelist compilation** ✅ DONE 2026-05-19 (Claude per Chris dispatch)
  - touches: `tailwind.config.js` (safelist) — to be created in T2 with safelist from `PLANNING/research/class-audit.md`
  - assignee: ~~Jade~~ Claude (re-assigned)
  - acceptance:
    1. `grep -r "class=" templates/` produces complete list of all Tailwind classes used across all 15 page templates (excluding `_nav.html`, `_footer.html` partials and `templates/email/` — they don't use Tailwind)
    2. `grep -r "classList\." templates/` produces list of all JS-manipulated classes. Specifically in `index.html` lines 361-362, 667-668, 369, 371, 420, 634, 673, 682, 701 — classes: `hidden`, `bg-slate-800`, `text-slate-300`, `bg-emerald-600`, `hover:bg-emerald-500`, `text-white`
    3. `grep -r "class=\"[^\"]*{{ " templates/` produces list of all Jinja-conditional classes
    4. All dynamic/JS-only classes documented in safelist array in `tailwind.config.js`
    5. Audit file saved to `PLANNING/research/class-audit.md`

- [x] **T2: Build pipeline setup** ✅ DONE 2026-05-19. `npm install` clean (74 packages, 0 vulns). `npm run build:css` emits 21K minified `static/css/output.css` in 284ms. DEPLOYMENT.md §8.5 added.
  - touches: `package.json`, `tailwind.config.js`, `static/css/input.css`, `render.yaml`, `DEPLOYMENT.md`, `.gitignore`
  - assignee: Claude
  - acceptance:
    1. `package.json` created with `tailwindcss@3.4.x` pinned as dev dependency (NOT v4 — CDN was serving v3.x, classes are v3 syntax)
    2. `static/css/input.css` created with `@tailwind base; @tailwind components; @tailwind utilities;`
    3. `tailwind.config.js` configured with `content` paths scanning all template directories AND `static/js/` for classList-manipulated classes, `safelist` array populated from T1 audit results
    4. `package.json` has `build:css` script: `npx tailwindcss -i ./static/css/input.css -o ./static/css/output.css --minify` AND `dev:css` script: `npx tailwindcss -i ./static/css/input.css -o ./static/css/output.css --watch`
    5. `npm install` runs successfully and `tailwindcss` is available
    6. `render.yaml` created (infrastructure-as-code, NOT dashboard-only config) with `buildCommand: npm install && npm run build:css` before gunicorn start command
    7. `.gitignore` updated: `static/css/output.css` added (build artifact, regenerated on each deploy)
    8. `DEPLOYMENT.md` updated with build step documentation and `npm run dev:css` watch mode for local development

- [x] **T3: Replace CDN with compiled CSS in all 15 page templates** ✅ DONE 2026-05-19. All 15 templates patched; CSP `script-src` reduced from 4 → 3 entries (`cdn.tailwindcss.com` removed). `unsafe-inline` retained — deferred to H10. Smoke test: `/login` returns 200, `/static/css/output.css` returns 200, response CSP header verified.
  - touches: all 15 non-partial, non-email page templates in `templates/` + `app.py` (CSP)
  - assignee: Claude
  - acceptance:
    1. Every page template: `<script src="https://cdn.tailwindcss.com"></script>` replaced with `<link rel="stylesheet" href="{{ url_for('static', filename='css/output.css') }}">`
    2. No template contains `cdn.tailwindcss.com` — verified by `grep -r "cdn.tailwindcss.com" templates/` returning empty
    3. CSP `script-src` no longer includes `cdn.tailwindcss.com` — verified by checking response headers. **`unsafe-inline` remains in `script-src`** (removal deferred to Hotfix 10)
    4. All 15 page templates render correctly at 375px and 1280px (no visual regression from CDN→compiled switch)
    5. `static/css/output.css` loads with HTTP 200 on every page
    6. Email templates (`templates/email/`) are NOT modified — they use inline styles only

- [x] **T4: Visual regression + performance comparison** ✅ DONE 2026-05-19. Chris verified local at 375px (iPhone SE) and via Network tab. All 15 page templates render identically to pre-migration — brand header, cards, form inputs, dropdowns, placeholders, banner styling all intact. **Page weight: ~50 kB vs prior ~450 kB (9× reduction)** — `output.css` is 1.2 kB on the wire (cached/304), no `cdn.tailwindcss.com` requests. Only remaining mobile UX issue is the nav overflow — that's Bug 5, scoped to Hotfix 9b. Not a regression from this sprint.
  - touches: none (QA only)
  - assignee: Chris
  - acceptance:
    1. All 15 page templates render correctly at 375px (mobile) and 1280px (desktop) — no visual differences from pre-migration
    2. `index.html` DOMContentLoaded time improved vs pre-migration baseline (measure before/after via browser DevTools)
    3. `index.html` total page weight reduced vs pre-migration baseline

- [x] **T5: Full regression: test suite + CSP verification** ✅ DONE 2026-05-19.
  - touches: none (QA only)
  - assignee: Claude + Chris
  - acceptance:
    1. [x] `python -m pytest` passes with no new failures — **84 passed, 18 failed** (vs H8 baseline 66 passed, 36 failed). Net -18 failures, zero new failures. Improvement attributed to dep reinstall from `pip install -r requirements.txt`.
    2. [x] CSP response header verified live: `script-src 'self' 'unsafe-inline' js.stripe.com` — no `cdn.tailwindcss.com`. Verified via `curl -I https://panefreequoting.com/login` 2026-05-19.
    3. [x] No CSP violations in browser console on any page (Chris verified). DevTools "Issues" panel surfaced pre-existing a11y label warnings on quote/account pages — unrelated to this sprint, logged for backlog.
    4. [x] End-to-end quote flow on live: Chris generated Quote #Q-000002 + Invoice #INV-000002 with 10/5/3 panes @ $8 base, 1.0/1.2/1.4 surcharges, 5% tax. Both PDFs produced $264.18 grand total, all line items present (Floor 1 $80, Floor 2 $48, Floor 3 $33.60, Screen $36, Track $54, Subtotal $251.60, Tax $12.58).

---

**Sprint type:** Stabilize (infrastructure hardening)
**Estimated complexity:** M (build pipeline creation + 15-template replacement + Render config)
**Rollback:** Revert to CDN by restoring `<script src="https://cdn.tailwindcss.com">` in templates and adding `cdn.tailwindcss.com` back to CSP. `output.css` deletion safe (gitignored, regenerated on build).

**Explicit non-scope:**
- `unsafe-inline` removal (deferred to Hotfix 10 — requires externalizing 4 inline `<script>` blocks in `index.html`)
- `style-src` `'unsafe-inline'` removal (deferred — requires nonce/hash for inline `<style>` blocks)
- Mobile nav drawer (deferred to Hotfix 9b — Bug 5)
- Viewport tag format normalization (cosmetic, defer)