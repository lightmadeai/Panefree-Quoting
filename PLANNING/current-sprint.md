---
label: (no active sprint)
project: window-quoting
phase: post-launch (Hotfix 9a closed)
status: idle — awaiting next sprint adoption
last_completed: hotfix-9a (DONE 2026-05-19, Inquisitor post-audit pending)
launch_marker: v1.0.0 on commit 7210991 (live at https://panefreequoting.com)
next_up: hotfix-9b (mobile nav drawer) — in `drafts/hotfix-9b.md`, pending pre-audit
---

# Current Sprint: None — Hotfix 9a Closed

Hotfix 9a (Tailwind CDN → compiled CSS) shipped and verified live 2026-05-19. No sprint is currently active.

## Pipeline Status
- **Hotfix-2 through Hotfix-9a:** all DONE (H8 post-audit PASS; H9a post-audit pending)
- **v1.0.0:** ✅ LIVE at https://panefreequoting.com — page weight reduced ~9× by Tailwind compile
- **Next sprints in flight:**
  - `drafts/hotfix-9b.md` — Mobile nav drawer (Bug 5). Depends on H9a (now closed). Pending Inquisitor pre-audit.
  - `drafts/hotfix-10.md` — CSP hardening (externalize index.html inline scripts + remove `unsafe-inline`). Depends on H9a. Pending Inquisitor pre-audit.

## Recent close-outs
- `PLANNING/done/hotfix-9a.md` — Tailwind CDN migration; CSP `cdn.tailwindcss.com` removed; build pipeline via Render dashboard buildCommand (render.yaml in repo but not active — flagged for future Blueprint conversion)
- `PLANNING/notes/hotfix-9a-notes.md` — execution notes
- `PLANNING/research/class-audit.md` — T1 deliverable (safelist source-of-truth)

## Known follow-ups
- **render.yaml not auto-active on existing Render service** — dashboard buildCommand manually updated to `pip install -r requirements.txt && npm install && npm run build:css`. render.yaml lives in repo as documentation + Blueprint-ready config for any future fresh service. Worth proper Blueprint conversion in a low-priority infra sprint.
- **A11y label warnings on quote / account pages** (20 + 5 instances) — pre-existing, surfaced during H9a live QA. Logged for post-launch backlog.
- **Bug 1 AC3 (404/500 visual verification)** — still deferred from H8.

When ready for H9b / H10:
1. Inquisitor pre-audits each draft
2. On approval, Jade promotes the draft → `current-sprint.md`
3. Cut a new sprint branch off `master`
