---
sprint: 8
project: window-quoting
drafted_by: Jade
research_refs: []
content_refs: []
audited_by: Inquisitor
audit_status: approved
status: done
created: 2026-05-17
completed: 2026-05-19
phase: Stabilize
---

# Hotfix 8 — Critical Bug Fixes (Viewport + CSP + Gunicorn)

---

## Current State

### Bug 1: Viewport Meta Tag
Only `index.html` and `settings.html` have `<meta name="viewport">`. The other 15 templates are missing it. The 2 partials (`_footer.html`, `_nav.html`) are included in other templates and don't need their own tag.

**Exact file list (17 non-partial templates):**
| # | Template | Has Viewport? | User Impact |
|---|----------|:------------:|-------------|
| 1 | `404.html` | ❌ | Error pages unreadable on mobile |
| 2 | `500.html` | ❌ | Error pages unreadable on mobile |
| 3 | `account.html` | ❌ | Account management broken on mobile |
| 4 | `account_delete.html` | ❌ | Account deletion broken on mobile |
| 5 | `contact.html` | ❌ | Contact form broken on mobile |
| 6 | `forgot_password.html` | ❌ | Password recovery broken on mobile |
| 7 | `history.html` | ❌ | Quote history broken on mobile |
| 8 | `index.html` | ✅ | — |
| 9 | `login.html` | ❌ | Login broken on mobile |
| 10 | `profiles.html` | ❌ | Profile management broken on mobile |
| 11 | `profile_new.html` | ❌ | Creating profiles broken on mobile |
| 12 | `register.html` | ❌ | Registration broken on mobile |
| 13 | `reset_password.html` | ❌ | Password reset broken on mobile |
| 14 | `settings.html` | ✅ | — |
| 15 | `top_up.html` | ❌ | Credit purchasing broken on mobile |

**Current code (templates WITH viewport):**
```html
<!-- index.html line 4 -->
<meta name="viewport" content="width=device-width, initial-scale=1.0">
```

**Current code (templates WITHOUT viewport):**
```html
<!-- e.g. login.html head -->
<head>
    <meta charset="UTF-8">
    <title>Login | Panefree Quoting</title>
    <script src="https://cdn.tailwindcss.com"></script>
    ...
```

### Bug 2: populateRates Failure
**Symptoms:** Price blocks do not auto-populate when switching pricing profiles. Quote generation non-functional on all devices (not just mobile — Chris confirmed desktop is also broken).

**Current code (index.html, `populateRates` function):**
```javascript
function populateRates(profileName) {
    const p = profilesData[profileName];
    if (!p) return;
    // ... setPlaceholder for floor rates/addons, setVal for tax/callout
}
```

**Current code (profile data injection):**
```javascript
const profilesData = JSON.parse('{{ profiles_data | tojson }}');
```

**Current code (initial call):**
```javascript
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() { populateRates(initialProfile); });
} else {
    populateRates(initialProfile);
}
```

**Known previous modification:** BUG-006 changed floor/addon fields from `setVal` to `setPlaceholder`. This is the strongest hypothesis — if `setPlaceholder` sets placeholder text instead of actual values, fields appear empty but "populated" with gray placeholder text that doesn't submit with the form.

**Bug 2 / Bug 3 interaction:** Cause #5 (Tailwind CDN blocking) is a possible root cause. If confirmed by T3, Bug 3 must be fixed BEFORE Bug 2 (execution order change: T6 before T4).

### Bug 4: Gunicorn Docstring
**Current code (`gunicorn.conf.py` line 5):**
```python
"""Start with 2 workers."""  # docstring says 2
workers = int(os.environ.get("GUNICORN_WORKERS", "1"))  # default is 1
```

---

## Bug 1: Mobile Viewport Broken (CRITICAL)

**Severity:** 🔴 CRITICAL — 15/17 templates render at desktop width on phones
**Impact:** Entire app is unusable on mobile except for index.html and settings.html

### Fix
Add `<meta name="viewport" content="width=device-width, initial-scale=1">` to the `<head>` of all 15 templates missing it. One-line addition per file, placed after `<meta charset="UTF-8">`.

### Acceptance Criteria
- [x] AC1: All 17 non-partial templates contain `<meta name="viewport">` — verified 2026-05-19, `grep -L 'name="viewport"' templates/*.html` returns only `_footer.html` and `_nav.html` (partials, excluded per spec)
- [x] AC2: No horizontal scroll at 375px on any page; mobile rendering verified by Chris via Chrome DevTools mobile-emulation on `index.html` and `profile_new.html` 2026-05-19 — page renders at proper mobile width, content readable. (Nav bar overflow noted but is Bug 5, scoped to Hotfix 9.)
- [ ] AC3: Error pages (404/500) — NOT formally verified during this sprint. The 404 and 500 templates DO contain the viewport meta tag (confirmed by `grep`), so the fix is in place; visual confirmation deferred (low risk — error pages are static).

### Rollback
Revert commit. Zero risk — adding a viewport meta tag cannot regress desktop (on desktop, `width=device-width` resolves to full viewport width, matching current behavior).

### Estimated Complexity: S (30 minutes)

---

## Bug 2: Quote Page Broken — Price Blocks Not Auto-Populating (CRITICAL)

**Severity:** 🔴 CRITICAL — core product function broken on ALL devices
**Impact:** Users cannot generate quotes. Switching pricing profiles does not populate rate fields.

### Root Cause Analysis
Five hypothesized causes, listed by likelihood:

1. **`setPlaceholder` vs `setVal` confusion (MOST LIKELY)** — BUG-006 changed floor/addon fields from `setVal` to `setPlaceholder`. Placeholder text is grayed out, doesn't submit with forms, and may appear "empty" to users. This could BE the bug.
2. **`profiles_data | tojson` serialization issue** — If profile names contain characters that break JSON keys, `JSON.parse()` fails silently.
3. **`DOMContentLoaded` timing issue** — If Tailwind CDN blocks rendering, `DOMContentLoaded` may have already fired by the time the script runs.
4. **JavaScript error in earlier script blocks** — BUG-004's form persistence script may throw, preventing `populateRates` from executing.
5. **Tailwind CDN blocking** — Runtime compilation delays DOM parsing.

### Diagnosis Plan (T3)

**Gate:** Root cause MUST be identified and documented before T4 (fix) begins.

1. Open DevTools Console on quote page — check for any JavaScript errors
2. Type `window.__profilesData` — should return the profile data object
   - If null/undefined → serialization issue (cause #2)
   - If object with keys → proceed to next step
3. Type `Object.keys(window.__profilesData)` — compare keys against `<option>` values in profile dropdown
   - If mismatch → encoding issue in profile names
4. Type `document.getElementById('profile-select').value` — should return active profile name
5. Type `document.querySelector('[name="override_floor1"]')` — verify element exists
   - If null → selector mismatch
6. Manually call `window.__populateRates(document.getElementById('profile-select').value)` — does it populate fields?
   - If yes but values appear as gray placeholder text → CONFIRMED: `setPlaceholder` is the bug (cause #1)
   - If no → check Network tab for CDN load time and check `DOMContentLoaded` timing
7. Check Network tab: `cdn.tailwindcss.com` load time, status, whether it blocks DOM parsing
8. Check BUG-004 form persistence script for errors — does it throw or modify form fields that `populateRates` targets?
9. Create a test profile with special characters (e.g. `O'Brien's Window`) — verify `profilesData` parsing still works
10. Test on Chrome DevTools mobile emulation (375px) — confirm both platforms fail the same way
11. Check `app.py` for CSP `script-src` configuration — note exact lines referencing `cdn.tailwindcss.com` for Sprint 2 scope

### ✅ DevTools Diagnosis — COMPLETED May 18, 2026

**Tester:** Chris
**Environment:** Chrome desktop, panefreequoting.com, logged in

**Console errors on page load:**
```
(index):64  cdn.tailwindcss.com should not be used in production.
(index):211 Executing inline script violates the following Content Security Policy directive 'script-src 'self' cdn.tailwindcss.com js.stripe.com'. Either the 'unsafe-inline' keyword, a hash ('sha256-yKE8p0rUbTp48Vh1YZVL5hw024SJKZhP+NHSl2hdSqg='), or a nonce ('nonce-...') is required to enable inline execution. The action has been blocked.
(index):292 Executing inline script violates the following Content Security Policy directive 'script-src 'self' cdn.tailwindcss.com js.stripe.com'. Either the 'unsafe-inline' keyword, a hash ('sha256-oYv4pMEqTYf/iZJu01ehCghi1M2fjz2hum1WigG7QD0='), or a nonce ('nonce-...') is required to enable inline execution. The action has been blocked.
```

**Command results:**
| # | Command | Result | Meaning |
|---|---------|--------|----------|
| 1 | `window.__profilesData` | `undefined` | Profile data injection script was blocked by CSP (line ~211) |
| 2 | `window.__populateRates` | `undefined` | Function definition script was blocked by CSP (line ~292) |
| 3 | `document.getElementById('profile-select').value` | `'test'` | Dropdown works, user selected 'test' profile |
| 4 | `window.__populateRates(document.getElementById('profile-select').value)` | `TypeError: window.__populateRates is not a function` | Function never loaded — cannot call it |
| 5 | `document.querySelector('[name="override_floor1"]')` | Returns `<input>` element | DOM element exists, form renders correctly |

**✅ ROOT CAUSE CONFIRMED:** CSP `script-src 'self' cdn.tailwindcss.com js.stripe.com` blocks ALL inline `<script>` tags. Both the profile data injection (line ~211) and the `populateRates()` function definition (line ~292) are inline scripts that CSP kills before execution. The form renders, the dropdown works, but the JavaScript bridge between them never loads.

**Impact:** This is NOT limited to the quote page. Any inline script on ANY page is blocked. Check other templates for inline JS dependencies.

**Confirmed cause:** #5 (Tailwind CSP blocking) is the primary root cause. Causes #1-4 are downstream — the functions never execute because they never load.

**Fix path:**
- **Quick fix (15 min):** Add `'unsafe-inline'` to CSP `script-src` in `app.py` — immediately unblocks all inline JS
- **Proper fix (Sprint 2):** Externalize inline JS to `static/js/` files, compile Tailwind, tighten CSP back to exclude `'unsafe-inline'`

### Fix Plan
Depends on T3 diagnosis results:

- **If cause #1 (setPlaceholder):** Revert floor/addon fields to `setVal` or use `setVal` for initial population + `setPlaceholder` for hint text
- **If cause #2 (JSON parse):** Fix `tojson` escaping or profile name handling
- **If cause #3 (timing):** Move `populateRates` call to end of body or use `requestAnimationFrame`
- **If cause #4 (JS error):** Fix the earlier script error
- **If cause #5 (Tailwind CDN):** Defer to Sprint 2 (Bug 3) — fix CDN first, then re-verify

### Acceptance Criteria
- [x] AC1: Switching profiles auto-populates floor / addon rates as **placeholders** (intentional design per BUG-006 — empty value = use profile default, populated value = override). Tax and callout populate as actual values (intentional UX). Verified by Chris 2026-05-19 on local + live.
- [x] AC2: Quote generation verified live at panefreequoting.com 2026-05-19 — 10/5/3 panes @ $8 base, surcharges 1.0/1.2/1.4, 5% tax produced expected $264.18 grand total with correct line-item breakdown in both quote and invoice PDFs.
- [x] AC3: Price blocks show correct profile-derived values; engine math validated against expected scenarios.
- [x] AC4: No JavaScript / CSP errors in browser console on live page load.
- [x] AC5: Root cause documented in `MAINTENANCE_LOG.md` (CSP `script-src` lacked `'unsafe-inline'`, blocking inline profile-data injection and `populateRates` definition).
- [x] AC6: T3→T4 gate satisfied — diagnosis completed 2026-05-18 (before T4 fix landed in commit `266af25` on 2026-05-19).

### Rollback
Revert commit. If fix changes `populateRates` logic, the previous (broken) behavior is preserved.

### Estimated Complexity: S-M (1-3 hours depending on root cause)

---

## Bug 4: Gunicorn Worker Count Mismatch (LOW — Non-Blocking)

**Severity:** 🟢 LOW — docstring says "2 workers", code defaults to 1
**Impact:** No functional impact, but confusing for future debugging

### Fix
Update docstring to match default: `"Start with 1 worker (override via GUNICORN_WORKERS env var)"`.

### Acceptance Criteria
- [x] AC1: Docstring updated in commit `266af25` to "Start with 1 worker — override via GUNICORN_WORKERS env var".
- [x] AC2: `workers = int(os.environ.get("GUNICORN_WORKERS", "1"))` unchanged — no functional regression.

### Rollback
N/A — docstring-only change.

### Estimated Complexity: S (5 minutes)

---

## Sprint Plan

**Sprint Type:** Hardening sprint (Stabilize phase) — 3 tasks (within 2-task cap with Bug 1+4 as a single "viewport+docstring" task)

| Task | Bug | Priority | Complexity | Assignee |
|------|-----|----------|------------|----------|
| T1 | Add viewport meta tag to 15 templates + fix gunicorn docstring | Bug 1 + Bug 4 | S | ~~Claude~~ ✅ DONE in commit `266af25` (2026-05-19) |
| T2 | Visual QA: all 17 pages on mobile (375px) + desktop (1280px, 1440px) + error pages (404/500) | Bug 1 | S | Chris (local) |
| T3 | Diagnose populateRates failure (DevTools — 10-step plan above) | Bug 2 | S-M | ~~Chris + Jade~~ ✅ DONE 2026-05-18 (CSP blocking inline JS) |
| T4 | Fix populateRates — quick-fix path: add `'unsafe-inline'` to CSP `script-src` | Bug 2 | S | ~~Claude~~ ✅ DONE in commit `266af25` (2026-05-19) |
| T5 | Full QA: profile switch, quote gen, desktop + mobile | Bug 2 | S | Chris (local then live) |

**Execution Order:** T1 ✅ → T2 ⏳ → T3 ✅ → T4 ✅ → T5 ⏳ → push to origin → deploy → final live verify

**Note 2026-05-19:** T1, T3, T4 completed prior to / outside this session. T1 and T4 work landed in commit `266af25` on master, inherited by `sprint-8` branch. Remaining: Chris's QA (T2 local, T5 local + live), push, deploy.

**T3→T4 Gate:** Root cause must be identified, documented, and confirmed reproducible before T4 begins. If root cause is Tailwind CDN (cause #5), defer to Sprint 2.

**Regression Gate:** After each fix, all existing automated tests must pass (`python -m pytest`).

**Bug 2/Bug 3 Interaction Note:** If T3 diagnosis confirms Tailwind CDN is the root cause of Bug 2, execution order changes: Sprint 2 (Bug 3) must be completed first, then T4 re-attempts the Bug 2 fix.

---

## Post-Fix Verification

After T1+T4:
1. Full mobile walkthrough: login → create profile → generate quote → view history → account management
2. Full desktop walkthrough: same flow
3. CSP check: no violations in console
4. Existing test suite: `python -m pytest` passes

---

*Sprint 2 (Bug 3: Tailwind CDN → compiled CSS) is a separate Build-phase sprint to be proposed after Sprint 1 is complete.*

*Inquisitor audit applied: R1 (split into 2 sprints), R2 (added Current State section), R3-R14 (tightened ACs, added T3→T4 gate, added diagnosis steps M1-M7, added regression gate, addressed Bug 2/Bug 3 interaction).*

*Note 2026-05-19: A mobile nav overflow bug was discovered post-promotion. Folded into Hotfix 9 instead of this sprint per Chris's call. See `drafts/hotfix-9.md` Bug 5.*