---
sprint: 4
project: window-quoting
audit_type: redraft-carry-forward-note
written_by: Jade
created: 2026-05-06
---

# Sprint 4 Redraft — Carry-Forward Audit Note

## Why This Exists
The original Sprint 4 pre-audit (`audits/sprint-4-pre-audit.md`, 2026-05-03) approved the *original* overweight draft. On 2026-05-05, the sprint was materially redrafted — split into Sprint 4 (code-side) and Sprint 5 (deployment cutover). The May 3 audit did not review the redrafted scope.

## Scope Delta (Original → Redraft)

| Item | Original (May 3 audited) | Redraft (May 5) | Material? |
|------|--------------------------|-----------------|-----------|
| T3 | Production Stripe Integration (live keys, real purchase) | Deployment Documentation + Env Templates (docs only, no live keys) | ✅ Yes — live key swap removed |
| T4 | Production Deployment Checklist (full deployment) | Final Polish + Contact Email | ✅ Yes — deployment ops removed |
| T5 | Final Polish + Contact Email + Release Notes | Release Notes + Changelog Finalization (T4 drafts, T5 finalizes) | ⚠️ Partial — split & deduped |
| New scope | — | 80% soft-warning tier in `notices.py` | ✅ New addition |
| New scope | — | Remove soft-cap display from `top_up.html` pricing card | ✅ New addition |
| Moved to Sprint 5 | — | Live Stripe key swap, HTTPS enforcement, real deployment, visual QA, monitoring, DB backup, SEO | ✅ Major scope removal |

## Carry-Forward Assessment

**The redrafted Sprint 4 is a *subset* of the originally audited sprint, plus two clearly scoped additions.**

- All high-risk items (live Stripe, deployment ops, real-card testing) were **removed** — these were the items the May 3 audit flagged (R3: `app.run(debug=True)`, R4: rollback plan for live keys). With live keys gone, those remarks no longer apply to Sprint 4.
- The two additions (80% soft-warning tier, pricing card soft-cap removal) are straightforward, bounded changes with clear acceptance criteria. Neither introduces architectural risk.
- T4/T5 overlap has been resolved: T4 = draft RELEASE_NOTES + CHANGELOG, T5 = finalize both.

**Verdict: Carry-forward is valid.** The redrafted Sprint 4 is strictly less risky than the audited version. The May 3 audit's non-blocking remarks about live keys (R3, R4) migrate to Sprint 5. No fresh pre-audit required.

## Caveats
- If Sprint 5 inherits the live-key work, Inquisitor should pre-audit Sprint 5 with those remarks in scope
- T1 dependency on Chris's manual walkthrough (`sprint-4-notes.md`) remains unchanged — kickoff is gated on Chris