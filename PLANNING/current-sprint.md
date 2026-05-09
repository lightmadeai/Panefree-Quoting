---
label: hotfix-1
project: window-quoting
phase: stabilize
drafted_by: Jade
status: in-progress
created: 2026-05-06
audit_status: approved
audit_note: "Inquisitor pre-audit verdict CONDITIONAL PASS (audits/hotfix-1-pre-audit.md, 2026-05-07) — 5 non-blocking remarks, no blockers. Status flipped from pending → approved by Claude on execution start."
---

# Hotfix-1 — Email Verification + Deployment Polish

**Full manifest:** `PLANNING/sprints/HOTFIX_1_MANIFEST.md`

## Tasks (Summary)
- **T1:** Verify email verification gate (BUG-005 re-test)
- **T2:** Session lifetime hardening — 7-day max (OBS-003)
- **T3:** Legacy PDF migration script + output directory docs (Inquisitor R1/R2)
- **T4:** Input sanitization audit (BUG-009 follow-up)
- **T5:** Credit refund atomicity (OBS-002)

## Phase
Stabilize — backlog items pulled from `PLANNING/backlog.md`

## Key References
- Sprint 4 notes: `PLANNING/notes/sprint-4-notes.md`
- Sprint 4 post-audit: CONTESTED (1st), PASSED (2nd)
- Branch from master (Sprint 4 merge)