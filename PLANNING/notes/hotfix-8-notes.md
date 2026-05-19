# Hotfix-8 Execution Notes

**Branch:** `sprint-8` (cut off `master` 2026-05-19, code fix `266af25` was already on `master` from out-of-band execution — see surprises)
**Executor:** Claude Opus 4.7 (Chris co-driving close-out) + Claude Sonnet 4.6 (out-of-band fix execution via openclaw-dispatched session, see surprises)
**Per:** Stabilize-sprint draft by Jade, Inquisitor third-pass APPROVED, promoted to `current-sprint.md` 2026-05-19
**Inquisitor post-audit:** PENDING — Chris to dispatch after this close-out
**v1.0.0 fix-commit:** `266af25` on `master`, pushed `f2203cb..266af25` 2026-05-19, deployed to https://panefreequoting.com

---

## Completed: 2026-05-19

## Scope reality vs. plan

| Task | Bug | Status |
|---|---|---|
| T1 | Viewport meta on 15 templates + gunicorn docstring | ✅ shipped in `266af25` |
| T2 | Mobile/desktop visual QA | ✅ Chris, local + live via Chrome DevTools 2026-05-19 |
| T3 | Diagnose populateRates failure | ✅ Chris 2026-05-18 — CSP blocking inline scripts |
| T4 | Fix populateRates (quick-fix path: `'unsafe-inline'` in CSP) | ✅ shipped in `266af25` |
| T5 | Full QA: profile switch, quote gen, desktop + mobile | ✅ Chris on live 2026-05-19 — 10/5/3 panes @ $8/1.0/1.2/1.4/5% returned correct $264.18 |

## Three-bullet summary

- **What was done:** CSP `'unsafe-inline'` quick-fix unblocked inline scripts on `index.html`, restoring profile-driven rate auto-population and quote generation. Viewport meta tags added to all 15 affected templates restored mobile rendering. Gunicorn docstring corrected. All shipped in one commit, deployed to live, verified by Chris.
- **What was deferred:** Bug 1 AC3 (404/500 formal visual verification) — templates have viewport meta, low risk. Bug 5 (mobile nav overflow) discovered post-promotion 2026-05-19, folded into Hotfix 9 with hamburger+drawer fix path (CSP-safe externalized JS). Proper CSP tightening (remove `'unsafe-inline'`, externalize inline scripts to `static/js/`) deferred to Hotfix 9 T3.
- **What surprised:** (1) The fix was already committed (`266af25`) before this close-out session started. It was made by a Sonnet 4.6 session dispatched by Jade via openclaw — Chris was not directly aware and the work was billed outside subscription. Jade's behavior has been updated. (2) The `setPlaceholder` design that originally raised suspicion (BUG-006 / Sprint 4) was intentional and correct — empty value = profile default, populated value = override. The real bug was upstream in CSP. (3) The "callout fee = minimum charge floor" engine semantics (`max(callout, work)`) surprised Chris during QA — first numbers looked like just-callout because work total was below the $75 floor; bigger jobs work correctly. Naming/UX nit logged for post-launch consideration.
