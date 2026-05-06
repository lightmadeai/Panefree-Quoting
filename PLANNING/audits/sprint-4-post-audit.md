---
sprint: 4
project: window-quoting
audit_type: post-audit
written_by: Inquisitor
created: 2026-05-06
verdict: passed
---

# Sprint 4 Post-Audit (Second) — Execution Verification

## Executive Summary

**Verdict: PASSED.** All five tasks have been executed. Commits exist on branch `sprint-4` with real code changes (1,371 insertions across 26 files). BUG-008 (P0 security) is fixed and verified via stress probe cross-tenant test. All T1–T5 acceptance criteria are met.

This is a full pass — no criticals, no blockers. Two non-blocking remarks below.

## Commit Evidence

Five commits on `sprint-4` branch, ordered by task:

| Commit | Message | Task |
|--------|---------|------|
| `bf9259a` | Sprint 4 T1: security fix + soft-cap UX changes | T1 |
| `7d02f18` | Sprint 4 T2: UX flow fixes | T2 |
| `f42db9c` | Sprint 4 T3: stress test re-run + results | T3 |
| `c47ec06` | Sprint 4 T4: deployment docs + schema-parity lesson | T4 |
| `bb80109` | Sprint 4 T5: contact email plumbing + release notes | T5 |

## Task-by-Task Verification

### T1: Critical Security + Core Bug Fixes — ✅ PASS

| Criterion | Status | Evidence |
|-----------|--------|----------|
| BUG-008 (P0): `/download/<filename>` restricted to user's PDF bucket | ✅ FIXED | `_user_pdf_dir(current_user.id)` + `os.path.basename()` + `abort(404)` on miss. `sovereign.db`, `app.py`, `config.py`, `models.py` all return 404. Cross-tenant test (P16) confirms user B cannot fetch user A's files. |
| BUG-006 (P1): "(Custom Rate)" on default line items | ✅ FIXED | `setPlaceholder` replaces `setVal` for override_floor1/2/3 and addon surcharge fields. `.value` stays empty unless user explicitly types. |
| BUG-002 (P1): "5 free" → "10 free" in signup copy | ✅ FIXED | `templates/register.html` now reads "10 free quote credits". |
| Soft-cap threshold removed from pricing card | ✅ DONE | `templates/top_up.html` line 121: threshold display removed. "Unlimited quotes" only. `soft_cap` variable still in context for subscriber banner. |
| 80% soft-warning tier in `notices.py` | ✅ DONE | `build_soft_cap_warning()` added. Integer arithmetic (`threshold * 8 // 10`). Returns None at ≥100% so caller falls through to existing `build_soft_cap_notice`. Mutually exclusive by construction. |
| Zero P0 bugs remaining | ✅ MET | Stress probe P1 (arbitrary file download) now returns 404 for all system files. Cross-tenant test passes. |

### T2: UX Flow Fixes — ✅ PASS

| Criterion | Status | Evidence |
|-----------|--------|----------|
| BUG-003 (P1): Remove starter profiles, redirect to `/profiles/new` | ✅ FIXED | `ensure_default_profiles_for_user` removed from `register`, `login`, `load_user`. Index route checks `if not profiles: redirect(url_for("profile_new"))`. Onboarding flash added. |
| BUG-004 (P1): Persist quote form in `sessionStorage` | ✅ FIXED | `save()` on debounced input (200ms), `restore()` on page load, `clearDraft()` on successful generate. Server-rendered values take precedence (no clobber). `sessionStorage` scoping = wiped on tab close. |
| BUG-007 (P2): Sequential `Q-NNNNNN` quote numbers | ✅ FIXED | `_claim_quote_number()` atomically claims from `User.next_quote_number`. New columns: `users.next_quote_number`, `users.quote_prefix`, `quotes.quote_number`, `quotes.quote_prefix`. History list shows blue badge. Generator renders `QUOTE #Q-000001` for new quotes; NULL falls back to legacy hash for pre-Sprint-4 rows. |

### T3: Stress Test + Verification — ✅ PASS

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Stress probe re-run after fixes | ✅ DONE | 11 probes, all pass. Pre-fix vs post-fix comparison in results file. |
| BUG-008 fix verified (403/404 on system files) | ✅ 404 on `sovereign.db`, `app.py`, `config.py`, `models.py`, `.env`, `../../etc/passwd` |
| BUG-006 fix verified (no "(Custom Rate)") | ✅ P13: `line items: 4, with '(Custom Rate)': 0` |
| BUG-002 fix verified ("10 free") | ✅ Implicitly verified in code diff |
| 80% soft-warning verified | ✅ Logic in `notices.py` + `app.py` generate route; integer boundary computed correctly |
| 100% soft-cap CTA still fires | ✅ Unchanged code path; `build_soft_cap_notice` called when `quote_count >= threshold` |
| Rate limiting verified | ✅ P6: 10 pass, 11th+ → 429 |
| Cancel-at-period-end verified | ✅ P5 unchanged |
| Email verification gate verified | ✅ P5 unchanged |
| `testing/stress-test-results.md` standalone | ✅ 170 lines, pre/post comparison, architecture note |

### T4: Deployment Documentation — ✅ PASS

| Criterion | Status | Evidence |
|-----------|--------|----------|
| `DEPLOYMENT.md` with step-by-step guide | ✅ 188 lines. Env vars, pre-flight checks, DB backup, schema parity, rollback plan, BUG-008 architecture note. |
| `.env.example` with all variables | ✅ 61 lines. Every required + optional var documented. SECRET_KEY generation guidance included. |
| Cryptographically random SECRET_KEY placeholder | ✅ Comment: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| Live vs test mode variable docs | ✅ `DEV_MODE`, `STRIPE_*`, `APP_BASE_URL` all documented with mode-specific guidance |
| BUG-001 schema parity lesson | ✅ Section 2.4: SQLAlchemy `inspect()` comparison. Section 5: "total_recovered_value" recurrence prevention. |
| `PROJECT.md` and `CLAUDE.md` current | ✅ `CLAUDE.md` updated with new columns, onboarding flow, PDF storage architecture |

### T5: Final Polish + Release Documentation — ✅ PASS

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Remove `console.log` / `print` debug statements | ✅ Clean. No stray `print()` in `app.py`. No `console.log` in `templates/index.html`. |
| Wire `SUPPORT_EMAIL` env variable | ✅ `config.SUPPORT_EMAIL` + `inject_support_email` context processor. All templates reference `{{ support_email }}`. |
| Contact email in footer, account, error pages | ✅ `_footer.html` included on all pages. `account.html` gains "Need help?" line. `404.html` + `500.html` new templates with contact CTA. |
| `/contact` form persists to DB | ✅ Unchanged (Sprint 3 deliverable, still functional) |
| Soft-cap CTA routes to `/contact` | ✅ `url_for("contact")` passed to `build_soft_cap_notice` (Sprint 3 change, unchanged) |
| `RELEASE_NOTES.md` | ✅ 78 lines. Customer-facing. Covers v1.0 features across Sprints 1–4. Publication-ready. |
| `CHANGELOG.md` through Sprint 4 | ✅ 42 new entries. Sprint 4 section comprehensive: security, added, changed, fixed, migration notes, test counts. Publication-ready. |

## Remarks (Non-Blocking)

### 🟡 R1: Legacy PDF Migration Path

Pre-Sprint-4 PDFs stored in `project_root/` are now unreachable from the `/download` route (which only resolves inside `_user_pdf_dir`). The CHANGELOG migration note mentions this: *"Legacy PDFs in `project_root/` from prior testing are now unreachable from the download route (which is the intended outcome). Optional cleanup: `rm project_root/quote_*.pdf project_root/invoice_*.pdf`."*

This is correct for a pre-production codebase. However, if any real user PDFs exist in `project_root/` (from manual testing or early demos), they'll become 404s after deployment. The migration note should recommend a one-time copy:

```bash
# Move legacy PDFs into per-user buckets (run once after deploy)
for f in project_root/quote_*.pdf project_root/invoice_*.pdf; do
  # Extract user_id from quote snapshot or filename convention
done
```

Since no paying customers exist yet, this is informational only. **Not blocking.**

### 🟡 R2: `output/` Directory Not Pre-Created

`_user_pdf_dir()` calls `os.makedirs(d, exist_ok=True)` on first use, so the directory is created on demand. `.gitignore` now includes `output/`. This is clean. However, `DEPLOYMENT.md` doesn't explicitly mention the `output/` directory requirement — it's implied by the env-var table (`OUTPUT_DIR`) but not called out in the deployment steps. Minor documentation gap. **Not blocking.**

## Summary

| Task | Verdict | Criticals | Remarks |
|------|---------|-----------|---------|
| T1: Security + Core Bugs | ✅ PASS | 0 | BUG-008 sealed, BUG-006/002 fixed, soft-cap UX done |
| T2: UX Flow Fixes | ✅ PASS | 0 | BUG-003/004/007 all fixed with back-compat |
| T3: Stress Test + Verification | ✅ PASS | 0 | 11/11 probes pass, standalone results file |
| T4: Deployment Docs | ✅ PASS | 0 | DEPLOYMENT.md + .env.example comprehensive |
| T5: Final Polish + Release Docs | ✅ PASS | 0 | Debug clean, contact email wired, docs publication-ready |

**Sprint 4 is cleared for merge to master.** No blockers, no criticals. Two non-blocking remarks (R1: legacy PDF migration, R2: output/ dir in deploy docs) are optional follow-ups.

The sprint-4 branch is ready for Chris to review and merge at his convenience.