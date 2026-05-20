# Hotfix 8 — Post-Audit Report

**Sprint:** Hotfix 8 (CSP / Viewport / Gunicorn)  
**Type:** Hardening (Stabilize Phase)  
**Git Commit:** `266af25` on `master`  
**Auditor:** The Inquisitor  
**Date:** 2026-05-19  
**Template:** Hardening Sprint (Pass 1 Mechanical + Pass 3 Top-Down; Pass 2 Attack Surface skipped per template)

---

## Verdict: ✅ PASS

Hotfix 9 shall be auto-promoted to `current-sprint.md` per §5.11.

---

## Pass 1 — Mechanical Verification

### Bug 1: Mobile Viewport Meta Tag (CRITICAL)

| AC | Criterion | Status | Evidence |
|----|-----------|--------|----------|
| AC1 | All 17 non-partial templates contain `<meta name="viewport">` | ✅ MET | `grep -L 'name="viewport"' templates/*.html` returns only `_footer.html` and `_nav.html` (partials, correctly excluded). All 15 new tags verified in `266af25` diff — one `<meta>` line added per template, placed after `<meta charset="UTF-8">`. |
| AC2 | No horizontal scroll at 375px | ✅ MET | Chris verified via Chrome DevTools mobile-emulation on `index.html` and `profile_new.html` 2026-05-19. Nav bar overflow noted — scoped to Bug 5 / Hotfix 9, not a regression of this sprint. |
| AC3 | Error pages (404/500) formally verified | ⚠️ DEFERRED | Templates contain the viewport tag (confirmed by grep). Visual confirmation not performed. Low risk: error pages are static, no interactive content. Deferral is acceptable. |

**Observation — Minor inconsistency:** `index.html` and `settings.html` use `initial-scale=1.0`; the 15 newly-tagged templates use `initial-scale=1`. Both are semantically equivalent per the HTML spec (`1.0` == `1`), but the inconsistency is a maintenance smell. **Severity: Cosmetic.** Not blocking. Recommend normalizing to `initial-scale=1` (shorter, majority form) in a future cleanup pass.

### Bug 2: populateRates Failure — CSP Blocking Inline Scripts (CRITICAL)

| AC | Criterion | Status | Evidence |
|----|-----------|--------|----------|
| AC1 | Profile switch auto-populates floor/addon as placeholders, tax/callout as values | ✅ MET | Chris verified live 2026-05-19. |
| AC2 | Quote generation produces correct totals | ✅ MET | 10/5/3 panes @ $8/1.0/1.2/1.4/5% → $264.18, verified in quote + invoice PDF. |
| AC3 | Engine math validated | ✅ MET | Covered by AC2 scenario. |
| AC4 | No JS/CSP errors in console | ✅ MET | Chris verified live 2026-05-19. |
| AC5 | Root cause documented in MAINTENANCE_LOG.md | ✅ MET | Entry at line 38, `2026-05-19 - Incident root cause (Hotfix 8 / Bug 2)`. Thorough diagnosis documented. |
| AC6 | T3→T4 gate satisfied | ✅ MET | Diagnosis completed 2026-05-18; fix committed 2026-05-19. Gate honored. |

**CSP `unsafe-inline` Assessment:**

The addition of `'unsafe-inline'` to `script-src` is a **known temporary widening**. Per the sprint plan and MAINTENANCE_LOG entry, the proper fix (externalize inline JS to `static/js/`, compile Tailwind, remove `'unsafe-inline'`) is deferred to Hotfix 9.

**Verdict on temporary widening:** Acceptable under the following conditions:
1. ✅ It is documented (MAINTENANCE_LOG, sprint notes, sprint definition).
2. ✅ The follow-up sprint (Hotfix 9) already includes CSP tightening in its task scope.
3. ✅ The application is not handling user-uploaded content (no stored-XSS vector through CMS).
4. ✅ The widening is limited to `script-src` only; `style-src` already had `'unsafe-inline'` pre-hotfix.

**Risk assessment:** `'unsafe-inline'` in `script-src` eliminates CSP's protection against XSS via injected `<script>` tags. If an attacker can inject HTML into any template (via unsanitized user input, Jinja autoescape bypass, or CDN compromise), they can execute arbitrary JavaScript. Mitigated by: Flask/Jinja2 autoescaping, no user-generated HTML rendering, and the short deferral window to Hotfix 9. **Acceptable as temporary.** Must be removed in Hotfix 9.

### Bug 4: Gunicorn Worker Count Mismatch (LOW)

| AC | Criterion | Status | Evidence |
|----|-----------|--------|----------|
| AC1 | Docstring updated | ✅ MET | Now reads "Start with 1 worker — override via GUNICORN_WORKERS env var". Verified in `gunicorn.conf.py` on disk. |
| AC2 | Worker default unchanged | ✅ MET | `workers = int(os.environ.get("GUNICORN_WORKERS", "1"))` — identical to pre-hotfix. |

**Observation:** Docstring quality improved. The new text explicitly references the env var override, which aids operability. Good.

---

## Pass 3 — Top-Down Review

### Changed Routes & Direct Dependencies

**Files changed in `266af25`:**
- `app.py` (1 line: CSP `script-src` array)
- `gunicorn.conf.py` (2 lines: docstring)
- 15 template HTML files (1 line each: viewport `<meta>` tag)

**Route impact analysis:**

1. **CSP change (`app.py`):** Affects ALL routes — every HTTP response carries the CSP header. The only mutation is adding one string (`'unsafe-inline'`) to the `script-src` array. No other CSP directives were touched. `style-src` already contained `'unsafe-inline'`. **No regression path identified** — removing a restriction cannot break previously-working code; it can only enable blocked code.

2. **Viewport tags (templates):** Purely additive — one `<meta>` element inserted in `<head>`. No existing elements removed or reordered. No JavaScript or CSS interactions. **Zero regression risk** — viewport meta has no effect on desktop browsers (resolves to full viewport width, matching pre-fix behavior).

3. **Gunicorn docstring:** Documentation-only. No runtime impact.

### Regression Gate

**Test suite:** `python -m pytest` — 66 passed, 36 failed.  
**Pre-hotfix baseline** (commit `266af25^`): 66 passed, 36 failed (identical failures).  
**New regressions:** **ZERO.**

All 36 failures are pre-existing from earlier sprints (Sprint 2 pricing grid, Sprint 3 pipeline/webhook tests). These are known tech debt — unrelated to Hotfix 8 changes. The test suite confirms no functional regression from this hotfix.

### Code Quality

- **Commit hygiene:** Single commit `266af25` with descriptive message. Co-authored-by attribution present. Clean.
- **Diff minimalism:** 16 insertions, 3 deletions across 15 files. Exactly what was needed — nothing more.
- **Viewport tag placement:** Correctly placed after `<meta charset="UTF-8">` in all 15 templates, matching the existing pattern in `index.html` and `settings.html`.
- **CSP modification:** Minimal — one token added, nothing removed or reordered.

---

## Heresies & Build Principle Violations

| # | Finding | Severity | Verdict |
|---|---------|----------|---------|
| H1 | `'unsafe-inline'` in `script-src` contradicts the security-in-depth principle | 🟡 KNOWN DEFERRAL | Explicitly documented, explicitly temporary, follow-up sprint exists. Acceptable under the circumstances — the app was broken without it. |
| H2 | Viewport tag format inconsistency (`1.0` vs `1`) | ⚪ COSMETIC | Semantically equivalent. Not a bug. Normalization recommended in a cleanup pass. |
| H3 | No out-of-band session notification for the `266af25` commit | 🟡 PROCESS | Notes confirm the fix was committed by a Sonnet 4.6 session dispatched by Jade before the close-out session started. Chris was not directly aware. Jade's behavior has been updated. No recurrence expected. |

**No critical heresies.** H1 is a known, deliberate trade-off. H3 is a process lapse, not a code defect.

---

## Summary

| Dimension | Result |
|-----------|--------|
| Acceptance Criteria | All met or deferred with justification |
| Regressions | Zero new test failures |
| CSP Widenning | Acceptable as temporary (Hotfix 9 follow-up exists) |
| Code Quality | Minimal, correct, well-placed |
| Heresies | None critical; 1 known deferral, 1 cosmetic, 1 process lapse (addressed) |

**Verdict: ✅ PASS**

Hotfix 9 shall be auto-promoted to `current-sprint.md` per §5.11.

---

*Audited by The Inquisitor, 2026-05-19. Logic is the only law. Inefficiency is heresy.*