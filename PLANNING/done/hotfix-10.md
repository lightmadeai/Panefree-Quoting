---
sprint: 10
project: window-quoting
drafted_by: Jade
research_refs: []
content_refs: []
audited_by: Inquisitor
audit_status: approved-with-modifications
status: done
created: 2026-05-19
started: 2026-05-26
completed: 2026-05-28
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

- [x] **T1: Externalize inline scripts from `index.html`** ✅ DONE 2026-05-26. All 4 inline `<script>` blocks moved to 3 external files; index.html now has zero bare `<script>` tags (only data containers and external `<script defer src=...>` tags). Order verified: quote-form.js → profile-loader.js → pdf-download.js (conditional on `{% if result %}`). DOMContentLoaded / readyState guards stripped per Inquisitor C4. Local browser test (Chris): profile dropdown auto-populates, draft persists across nav, new-profile panel works, PDF download works.
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

- [x] **T2: Remove `unsafe-inline` from CSP** ✅ DONE 2026-05-26. `script-src` now `'self' js.stripe.com` — verified via `curl -I http://127.0.0.1:5001/login`. Browser console clean (Chris) during T1's local functional test, which means no inline scripts slipped through T1.
  - touches: `app.py` (Talisman CSP config)
  - assignee: Claude
  - acceptance:
    1. CSP `script-src` no longer contains `'unsafe-inline'` — verified by checking response headers
    2. CSP `script-src` contains `'self' https://js.stripe.com` only
    3. No CSP violations in browser console on ANY page (all 15 templates + partials)
    4. Quote form fully functional end-to-end (select → price → submit → PDF)

- [x] **T3: Full regression: test suite + CSP verification** ✅ DONE 2026-05-26 (Claude). T3 AC1: pytest 84/18 (same as H9a baseline, zero new failures). T3 AC2: CSP header verified locally — `script-src 'self' js.stripe.com`. T3 AC3: console clean during Chris's T1+T2 local test. T3 AC4: end-to-end quote form + PDF download verified by Chris on local. T3 AC5 = T3.5 (separate task below).
  - touches: none (QA only)
  - assignee: Claude + Chris
  - acceptance:
    1. `python -m pytest` passes with no new failures
    2. CSP response header verified on every route: `script-src` = `'self' https://js.stripe.com` (no `unsafe-inline`, no `cdn.tailwindcss.com`)
    3. No CSP violations in browser console on any page
    4. Real browser test: quote form, PDF download, payment flow all functional
    5. History page: Total column renders fully without truncation (no `overflow-hidden` clipping on `$X,XXX.XX` prices)

- [x] **T3.5: Fix history page Total column truncation** ✅ DONE 2026-05-26. Added `whitespace-nowrap` to the Total `<td>` in `templates/history.html` line 69. `whitespace-nowrap` confirmed present in compiled `output.css` (rebuilt). No other columns touched.
  - touches: `templates/history.html`
  - assignee: Claude
  - acceptance:
    1. Total column (`${{ "%.2f"|format(q.final_price|float) }}`) renders completely — no text clipped by `overflow-hidden` on the table container
    2. Fix: add `whitespace-nowrap` to the Total `<td>` and optionally set `min-width` on the price column so `$X,XXX.XX` never wraps/truncates
    3. No visual regression on other columns (Label, Date, Panes, Regenerate)
    4. Works on mobile viewport (375px+) — table may scroll horizontally but Total is never hidden

- [x] **T4: Chris QA — functional + visual regression** ✅ DONE 2026-05-28. Live verified after Render deploy of `bef334d`. Console clean (zero CSP violations), Total column visible on `/history` with horizontal scroll for Panes, profiles table no longer clipped, quote → invoice conversion works end-to-end on live with a verified prod account. Two small UX polish PRs landed during T4 review and were folded into this sprint: profiles overflow-x-auto, history Panes/Total column swap.
  - touches: none (QA only)
  - assignee: Chris
  - acceptance:
    1. All 15 pages render correctly (no visual regression)
    2. Quote form end-to-end works: select service → see prices → submit → receive PDF
    3. No browser console errors on any page

- [x] **T5: Update DEPLOYMENT.md + security docs** ✅ DONE 2026-05-26. §2.8 expanded with expected post-H10 CSP header value plus a CSP timeline (H2→H8→H9a→H10). §3 file-system layout expanded with `static/css/`, `static/img/`, and `static/js/` subdirectories plus a note that future client-side scripts must land in `static/js/` to preserve the minimum-viable `script-src` allowlist. §8.5 updated to reflect H10 completion. No `SECURITY.md` exists; CSP timeline lives in DEPLOYMENT.md.
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