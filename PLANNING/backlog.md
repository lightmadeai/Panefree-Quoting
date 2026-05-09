# Window Quoting — Stabilization Backlog

Last updated: 2026-05-06

## P2 — Should Fix Before Launch
- [ ] BUG-005: Re-test email verification gate now that SUPPORT_EMAIL is wired (T5 deliverable)
- [ ] Inquisitor R1: Legacy PDFs in `project_root/` will 404 after merge — write one-time migration script for any existing user PDFs
- [ ] Inquisitor R2: Add `output/` directory setup step to DEPLOYMENT.md

## P3 — Defense-in-Depth
- [ ] BUG-009: Garbage/oversized inputs stored raw in DB — confirm `sanitize_label` covers all entry points, add server-side length caps if gaps exist
- [ ] OBS-002: Credit-refund non-atomic with quote rollback — add retry/comment on failed refund UPDATE
- [ ] OBS-003: Session lifetime defaults to 31 days — set explicit `PERMANENT_SESSION_LIFETIME = timedelta(days=7)` in `config.py`

## Ops — Deployment Tasks (pull after P2s clear)
- [ ] Live Stripe key swap (test → live)
- [ ] HTTPS enforcement (infrastructure config)
- [ ] Production deployment (live environment)
- [ ] Manual visual QA (requires human eyes — Chris walkthrough)
- [ ] Monitoring/alerting setup
- [ ] DB backup (one-time operational action)
- [ ] SEO / marketing landing page
- [ ] Alembic migration tooling (prevent future schema drift like BUG-001)