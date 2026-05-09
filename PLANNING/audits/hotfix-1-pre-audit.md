# Hotfix-1 Pre-Audit Report

**Auditor:** The Inquisitor
**Date:** 2026-05-07
**Manifest:** `PLANNING/sprints/HOTFIX_1_MANIFEST.md`
**Phase:** Stabilize (§13 compliant)

---

## Checklist

### ✅ ≤ 5 tasks
5 tasks (T1–T5). PASS.

### ✅ All acceptance criteria falsifiable
Each task has concrete test steps with expected outcomes. PASS.

### ✅ No P0/P1 items skipped
Backlog `P2` and `P3` items are correctly mapped:
- T1 → P2 (BUG-005 re-test)
- T2 → P3 (OBS-003)
- T3 → P2 (Inquisitor R1/R2)
- T4 → P3 (BUG-009 follow-up)
- T5 → P3 (OBS-002)
All P0/P1 items were resolved in Sprint 4. Backlog is empty above P2. PASS.

### ✅ Ops items correctly excluded
Out-of-scope list matches Ops tier items from backlog. No Ops items in hotfix. PASS.

### ✅ Phase label is `stabilize`
Both manifest and current-sprint show `phase: stabilize`. PASS.

### ⚠️ T1 dependency on SUPPORT_EMAIL (Sprint 4 T5)
`SUPPORT_EMAIL` is wired in `config.py` line 67: `os.environ.get("SUPPORT_EMAIL", "support@windowquoting.com")`. Default value present. Dependency satisfied. PASS.

### ✅ No overlap between tasks
T1 (email verification), T2 (session lifetime), T3 (PDF migration), T4 (input sanitization), T5 (credit atomicity) — all distinct. PASS.

---

## Pre-Audit Remarks (Non-Blocking)

### R1: T2 — Session lifetime is currently 24h, not 31 days
The manifest says "defaults to 31 days" but `config.py` line 57 shows `PERMANENT_SESSION_LIFETIME = timedelta(hours=24)`. Sprint 4 already set this to 24h. T2 asks for 7 days. This is a valid hardening step, but the manifest description is stale — the current value is 24h, not 31 days. The change is `timedelta(hours=24)` → `timedelta(days=7)`.

### R2: T2 — `_session.permanent = True` is required
Lines 657 and 716 set `_session.permanent = True`. Flask only applies `PERMANENT_SESSION_LIFETIME` when `session.permanent` is True. The manifest says "Remove `_session.permanent = True` if `PERMANENT_SESSION_LIFETIME` already controls session duration" — but removal would break session expiry entirely. Keep it, add the comment explaining why.

### R3: T3 — Output directory already partially set up
`.gitignore` already includes `output/` and `*.bak` (lines 17, 25-26). Sprint 4 BUG-008 fix already routes PDFs to `output/quotes/<user_id>/`. T3's acceptance criteria "verify path" and "verify .gitignore includes output/" may already be satisfied. Verify before building.

### R4: T5 — Credit refund is already partially symmetric
Lines 1029-1031 show a symmetric refund: `UPDATE users SET credit_balance = credit_balance + 1 WHERE id = :uid`. The manifest asks for wrapping in try/except and adding a comment. The current implementation does the refund inside the rollback handler — if the refund UPDATE fails, the session is already rolled back. The risk is low but real: a failed refund after a rollback means the user lost a credit. The manifest's request is valid.

### R5: T4 — `sanitize_label` covers quote labels and contact labels
Lines 865 and 972 show `sanitize_label` applied to `data.get("label")`. Need to verify it also covers profile settings fields and any other free-text entry points.

---

## Verdict: **CONDITIONAL PASS** ✅

All 7 checklist items PASS. 5 non-blocking remarks for implementation awareness. No blockers.

---

*🕵️‍♂️⚖️ Logic is the only law. Inefficiency is heresy.*