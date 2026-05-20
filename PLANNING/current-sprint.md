---
sprint: 9a
project: window-quoting
drafted_by: Jade
research_refs: []
content_refs: []
audited_by: Inquisitor
audit_status: approved-with-modifications
status: draft
created: 2026-05-19
revised: 2026-05-19 (v2 — Inquisitor M1-M6 incorporated)
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

- [ ] **T1: Dynamic class audit + safelist compilation**
  - touches: `tailwind.config.js` (safelist)
  - assignee: Jade
  - acceptance:
    1. `grep -r "class=" templates/` produces complete list of all Tailwind classes used across all 15 page templates (excluding `_nav.html`, `_footer.html` partials and `templates/email/` — they don't use Tailwind)
    2. `grep -r "classList\." templates/` produces list of all JS-manipulated classes. Specifically in `index.html` lines 361-362, 667-668, 369, 371, 420, 634, 673, 682, 701 — classes: `hidden`, `bg-slate-800`, `text-slate-300`, `bg-emerald-600`, `hover:bg-emerald-500`, `text-white`
    3. `grep -r "class=\"[^\"]*{{ " templates/` produces list of all Jinja-conditional classes
    4. All dynamic/JS-only classes documented in safelist array in `tailwind.config.js`
    5. Audit file saved to `PLANNING/research/class-audit.md`

- [ ] **T2: Build pipeline setup**
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

- [ ] **T3: Replace CDN with compiled CSS in all 15 page templates**
  - touches: all 15 non-partial, non-email page templates in `templates/`
  - assignee: Claude
  - acceptance:
    1. Every page template: `<script src="https://cdn.tailwindcss.com"></script>` replaced with `<link rel="stylesheet" href="{{ url_for('static', filename='css/output.css') }}">`
    2. No template contains `cdn.tailwindcss.com` — verified by `grep -r "cdn.tailwindcss.com" templates/` returning empty
    3. CSP `script-src` no longer includes `cdn.tailwindcss.com` — verified by checking response headers. **`unsafe-inline` remains in `script-src`** (removal deferred to Hotfix 10)
    4. All 15 page templates render correctly at 375px and 1280px (no visual regression from CDN→compiled switch)
    5. `static/css/output.css` loads with HTTP 200 on every page
    6. Email templates (`templates/email/`) are NOT modified — they use inline styles only

- [ ] **T4: Visual regression + performance comparison**
  - touches: none (QA only)
  - assignee: Chris
  - acceptance:
    1. All 15 page templates render correctly at 375px (mobile) and 1280px (desktop) — no visual differences from pre-migration
    2. `index.html` DOMContentLoaded time improved vs pre-migration baseline (measure before/after via browser DevTools)
    3. `index.html` total page weight reduced vs pre-migration baseline

- [ ] **T5: Full regression: test suite + CSP verification**
  - touches: none (QA only)
  - assignee: Claude + Chris
  - acceptance:
    1. `python -m pytest` passes with no new failures (same 36 pre-existing, 66 passes as H8 baseline)
    2. CSP response header verified: `script-src` contains `'self' 'unsafe-inline' https://js.stripe.com` but NOT `cdn.tailwindcss.com`
    3. No CSP violations in browser console on any page
    4. Quote form fully functional end-to-end (select service → get price → submit → PDF download)

---

**Sprint type:** Stabilize (infrastructure hardening)
**Estimated complexity:** M (build pipeline creation + 15-template replacement + Render config)
**Rollback:** Revert to CDN by restoring `<script src="https://cdn.tailwindcss.com">` in templates and adding `cdn.tailwindcss.com` back to CSP. `output.css` deletion safe (gitignored, regenerated on build).

**Explicit non-scope:**
- `unsafe-inline` removal (deferred to Hotfix 10 — requires externalizing 4 inline `<script>` blocks in `index.html`)
- `style-src` `'unsafe-inline'` removal (deferred — requires nonce/hash for inline `<style>` blocks)
- Mobile nav drawer (deferred to Hotfix 9b — Bug 5)
- Viewport tag format normalization (cosmetic, defer)