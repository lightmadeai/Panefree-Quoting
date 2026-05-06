---
sprint: 4
project: window-quoting
drafted_by: Jade
status: done
created: 2026-05-05
depends_on: sprint-3-completion
audit_status: approved
redirected: true
redirected_reason: "Original Sprint 4 was overweight with operational tasks that Claude cannot verify. Redrafted into Sprint 4 (code-side) and Sprint 5 (deployment cutover). Rebalanced 2026-05-06: T1 split into critical fixes + UX fixes, T4/T5 merged into docs + polish."
---

# Sprint 4 — Code-Side Ship Readiness

**Full manifest:** `PLANNING/sprints/SPRINT_4_MANIFEST.md`

## Tasks (Summary)
- **T1: Critical Security + Core Bug Fixes** — BUG-008 (P0 file download), BUG-006 (Custom Rate), BUG-002 (credit copy), soft-cap frontend removal, 80% warning tier
- **T2: UX Flow Fixes** — BUG-003 (starter profiles/redirect), BUG-004 (form persistence), BUG-007 (sequential quote IDs)
- **T3: Programmatic Stress Test + Verification** — Re-run probe, verify all T1/T2 fixes, create stress-test-results.md
- **T4: Deployment Documentation + Environment Templates** — DEPLOYMENT.md, .env.example, schema parity docs
- **T5: Final Polish + Release Documentation** — Debug cleanup, SUPPORT_EMAIL, contact email, RELEASE_NOTES, CHANGELOG

## Key References
- Bug findings: `PLANNING/notes/sprint-4-notes.md`
- Post-audit verdict: CONTESTED (zero code changes applied — this sprint has not been executed yet)
- Sprint 3 merge: commit `0e43594`