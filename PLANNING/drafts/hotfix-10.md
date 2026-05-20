---
sprint: 10
project: window-quoting
drafted_by: Jade
research_refs: []
content_refs: []
audited_by: Inquisitor
audit_status: approved-with-modifications
status: draft
created: 2026-05-19
revised: 2026-05-19 (v2 — Inquisitor C1, C3, C4, C5 incorporated)
phase: Stabilize
---

# Hotfix 10 — CSP Hardening: Externalize Inline Scripts + Remove `unsafe-inline`

*Extracted from Hotfix 9 per Inquisitor re-audit (C1: removing `unsafe-inline` without externalizing scripts recreates H8 Bug 2 regression). v2 incorporates Inquisitor pre-audit modifications C1 (static/js directory), C3 (defer script ordering), C4 (remove redundant DOMContentLoaded guards), C5 (update DEPLOYMENT.md CSP verification).*

---

## Current State

Hotfix 8 added `'unsafe-inline'` to CSP `script-src` as a temporary fix to unblock `populateRates()` and other inline scripts. This is a security gap — `unsafe-inline` negates most CSP protection against XSS.

`index.html` contains **4 inline `<script>` blocks** that must be externalized before `unsafe-inline` can be safely removed:

| Line | Script Purpose | Target File |
|------|----------------|-------------|
| 194 | Form state persistence (BUG-004, Sprint 4) | `static/js/quote-form.js` |
| 275 | Profile data loading + `populateRates()` (153 lines, contains 3 logical units: `populateRates()`, `initialPopulate`, new-profile IIFE) | `static/js/profile-loader.js` |
| 559 | POST→GET URL rewrite (`history.replaceState`) | `static/js/quote-form.js` (merged with block 1) |
| 620 | PDF download + invoice conversion button logic | `static/js/pdf-download.js` |

No other templates contain inline `<script>` blocks (verified by `Select-String` across all templates). The `<script type="application/json">` blocks at lines 193 and 605 are data containers, not executable JS — CSP `script-src` does not apply to them.

**After this sprint:** CSP `script-src` will be `'self' https://js.stripe.com` — no wildcards, no `unsafe-inline`, no CDN domains. Minimum viable CSP.

**Out of scope:** `style-src` `'unsafe-inline'` remains (required for inline `<style>body { font-family: 'Inter', sans-serif; }</style>` in all 15 templates). Removal requires nonce/hash-based approach — future hardening sprint.

---

## Tasks

- [ ] **T1: Externalize inline scripts from `index.html`**
  - touches: `templates/index.html`, `static/js/quote-form.js`, `static/js/profile-loader.js`, `static/js/pdf-download.js`
  - assignee: Claude
  - acceptance:
    1. `static/js/` directory created with three files: `quote-form.js`, `profile-loader.js`, `pdf-download.js`
    2. All 4 inline `<script>` blocks extracted to the 3 external JS files (blocks 1+3 → `quote-form.js`, block 2 → `profile-loader.js`, block 4 → `pdf-download.js`)
    3. `index.html` contains zero inline `<script>` blocks with executable code — verified by `grep -c "<script>" templates/index.html` returning 0 (or only external `<script src="...">` tags and `<script type="application/json">` data blocks)
    4. Each external JS file loaded via `<script defer src="{{ url_for('static', filename='js/...') }}">` at end of `<body>`, in this order: `quote-form.js` → `profile-loader.js` → `pdf-download.js` (conditional: `{% if result %}`). This guarantees `window.__clearQuoteDraft` is defined before `pdf-download.js` executes.
    5. `ls static/js/quote-form.js static/js/profile-loader.js static/js/pdf-download.js` passes — all three files exist
    6. All three files return HTTP 200 via Flask `/static/js/...`
    7. Redundant `DOMContentLoaded`/`readyState` guards removed from extracted code (unnecessary with `defer` — scripts execute after DOM parse)
    8. Quote form state persistence works identically (populate, save, restore)
    9. `populateRates()` fires correctly and prices populate
    10. URL rewrite after POST still replaces `/quote` with clean URL
    11. PDF download button functions correctly

- [ ] **T2: Remove `unsafe-inline` from CSP**
  - touches: `app.py` (Talisman CSP config)
  - assignee: Claude
  - acceptance:
    1. CSP `script-src` no longer contains `'unsafe-inline'` — verified by checking response headers
    2. CSP `script-src` contains `'self' https://js.stripe.com` only
    3. No CSP violations in browser console on ANY page (all 15 templates + partials)
    4. Quote form fully functional end-to-end (select → price → submit → PDF)

- [ ] **T3: Full regression: test suite + CSP verification**
  - touches: none (QA only)
  - assignee: Claude + Chris
  - acceptance:
    1. `python -m pytest` passes with no new failures
    2. CSP response header verified on every route: `script-src` = `'self' https://js.stripe.com` (no `unsafe-inline`, no `cdn.tailwindcss.com`)
    3. No CSP violations in browser console on any page
    4. Real browser test: quote form, PDF download, payment flow all functional

- [ ] **T4: Chris QA — functional + visual regression**
  - touches: none (QA only)
  - assignee: Chris
  - acceptance:
    1. All 15 pages render correctly (no visual regression)
    2. Quote form end-to-end works: select service → see prices → submit → receive PDF
    3. No browser console errors on any page

- [ ] **T5: Update DEPLOYMENT.md + security docs**
  - touches: `DEPLOYMENT.md`
  - assignee: Claude
  - acceptance:
    1. `DEPLOYMENT.md` updated with external JS file structure in Section 3 (file system layout)
    2. `DEPLOYMENT.md` Section 2.8 CSP verification updated: expected `script-src` value is now `'self' https://js.stripe.com` (not the old value with `unsafe-inline` and `cdn.tailwindcss.com`)
    3. CSP policy documented with current `script-src` allowlist
    4. If `SECURITY.md` exists, CSP section updated to reflect tightened policy and timeline (HF2 added `unsafe-inline` temporarily; HF10 removed it after externalization)

---

**Sprint type:** Stabilize (security hardening)
**Estimated complexity:** M (script externalization must preserve exact behavior — 153-line block 2 is the risk)
**Rollback:** Re-add `'unsafe-inline'` to CSP, re-inline scripts in `index.html`.

**Dependency:** Hotfix 9a must be complete (Tailwind CDN already removed from CSP).

**Security significance:** This sprint closes the last known CSP `script-src` gap. After HF10, `script-src` = `'self' https://js.stripe.com` — no wildcards, no `unsafe-inline`, no CDN domains.

**Known future hardening:** `style-src` `'unsafe-inline'` removal requires nonce/hash approach for inline `<style>` blocks — separate sprint.