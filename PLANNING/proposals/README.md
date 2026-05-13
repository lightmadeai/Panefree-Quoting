# Claude Proposals — for Jade

Per §4 role boundaries, `drafts/` is Jade's lane. This folder holds
Claude-authored sprint proposals that Jade can review, adopt verbatim
into `drafts/`, modify, reject, or ignore. Nothing here counts as an
active sprint until Jade promotes it.

Workflow:
1. Claude drafts a proposal here (`hotfix-N.md`, `sprint-N-ops.md`, etc.).
2. Jade reads the proposal; if she takes ownership, she copies/moves it
   to `drafts/sprint-N.md` (or `drafts/hotfix-N.md`) and edits as needed.
3. Inquisitor pre-audits the version in `drafts/` — NOT the version
   here. The proposal in this folder is informational only.
4. After Jade adopts, the proposal file here can be deleted or kept
   as a record of where the draft started.

## Current proposals (2026-05-12)

These were drafted in response to the pre-launch readiness review.
Sequencing matters — H3's email backend is a dependency of H4 and H5.

- `hotfix-3.md` — User access lifecycle: email backend, password reset,
  account deletion. **Launch blocker** — current build cannot deliver
  verification emails, so no new user can satisfy the `email_verified`
  gate that blocks `/generate`.
- `hotfix-4.md` — Observability: Sentry, /health, structured log audit,
  ops runbook.
- `hotfix-5.md` — Backups: automated daily DB backup, retention policy,
  restore drill.
- `sprint-5-ops.md` — Production cutover. Gunicorn + ProxyFix, prod env
  vars, live Stripe smoke, launch checklist. Last sprint before live.

Open question for Jade + Inquisitor: §13 currently defines only Build
and Stabilize phases. The ops sprint either needs a §13 amendment
adding an Ops phase, or it gets relabeled `hotfix-6` and runs as the
final stabilize hotfix. Claude leans toward the latter (lower ceremony,
work is stabilize-flavored).
