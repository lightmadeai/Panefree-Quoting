# Window Quoting — Stabilization Backlog

Last updated: 2026-05-06

## P2 — Should Fix Before Launch
- [x] BUG-005: Re-test email verification gate now that SUPPORT_EMAIL is wired (T5 deliverable) — Hotfix-1 T1, see `testing/bug-005-verification-test.md`
- [x] Inquisitor R1: Legacy PDFs in `project_root/` will 404 after merge — write one-time migration script for any existing user PDFs (Hotfix-1 T3, `scripts/migrate-pdfs.py`)
- [x] Inquisitor R2: Add `output/` directory setup step to DEPLOYMENT.md (Hotfix-1 T3, §2.5)

## P3 — Defense-in-Depth
- [x] BUG-009: Garbage/oversized inputs stored raw in DB — confirm `sanitize_label` covers all entry points, add server-side length caps if gaps exist (Hotfix-1 T4; gaps closed at /account business_name+phone, /contact 4 fields, /profiles/new + /api/profiles/create name)
- [ ] Pre-existing test failure: `test_sprint3_pipeline.TestContactIntake.test_soft_cap_cta_points_at_contact_route` returns 400 ("Invalid pricing profile: None") — test predates BUG-003 (Sprint 4) auto-seed removal, needs to seed a profile before /generate. Found while running regressions during Hotfix-1 T4. Not caused by hotfix changes.
- [x] OBS-002: Credit-refund non-atomic with quote rollback — add retry/comment on failed refund UPDATE (Hotfix-1 T5; try/except + [CREDIT-REFUND-FAILED] log; deliberately no retry)
- [x] OBS-003: Session lifetime defaults to 31 days — set explicit `PERMANENT_SESSION_LIFETIME = timedelta(days=7)` in `config.py` (Hotfix-1 T2; actual prior value was 24h in app.py, moved to config.py)

## Ops — Deployment Tasks (pull after P2s clear)
- [ ] Live Stripe key swap (test → live)
- [ ] HTTPS enforcement (infrastructure config)
- [ ] Production deployment (live environment)
- [ ] Manual visual QA (requires human eyes — Chris walkthrough)
- [ ] Monitoring/alerting setup
- [ ] DB backup (one-time operational action)
- [ ] SEO / marketing landing page
- [ ] Alembic migration tooling (prevent future schema drift like BUG-001)