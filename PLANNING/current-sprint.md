---
label: hotfix-2
project: window-quoting
phase: stabilize
drafted_by: Claude (per Chris blanket approval, 2026-05-11)
status: done
created: 2026-05-11
completed: 2026-05-11
audit_status: pending
audit_note: "Drafted + executed in one session per Chris's blanket approval (2026-05-11). All 5 tasks landed, smoke-tested via curl + python -c assertions, regression-verified via stress_probe (13/13 PASS) and locust (3270 reqs, 0 failures, no quote-number gaps). Awaiting Inquisitor post-audit verdict."
---

# Hotfix-2 — Pre-Production Security Hardening

**Full manifest:** `PLANNING/sprints/HOTFIX_2_MANIFEST.md`

## Tasks (Summary)
- **T1:** Cookie hardening (SECURE/HTTPONLY/SAMESITE) + register.html minlength fix
- **T2:** CSRF protection via Flask-WTF (all forms + AJAX X-CSRFToken)
- **T3:** Defensive bounds (table allowlist + password cap + dir mode 0o700)
- **T4:** Rate limiting (Flask-Limiter on auth routes) + security headers (Flask-Talisman + CSP)
- **T5:** Reproducible deps (requirements.txt) + DEPLOYMENT.md addenda

## Phase
Stabilize — pre-prod security hardening per 2026-05-11 audit

## Key References
- Security review transcript: 2026-05-11 conversation
- Locust stress test results: `testing/stress/run1_stats.csv` (5057 reqs, 0 failures)
- Branch from hotfix-1 (Hotfix-1 done/approved 2026-05-08)
