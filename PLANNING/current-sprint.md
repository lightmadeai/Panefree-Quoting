---
label: (no active sprint)
project: window-quoting
phase: post-launch (Hotfix 8 closed)
status: idle — awaiting next sprint adoption
last_completed: hotfix-8 (DONE 2026-05-19, Inquisitor post-audit pending)
launch_marker: v1.0.0 on commit 7210991 (live at https://panefreequoting.com)
next_up: hotfix-9 (Tailwind CDN migration + mobile nav drawer) — Inquisitor re-audit pending
---

# Current Sprint: None — Hotfix 8 Closed

Hotfix 8 (CSP / viewport / gunicorn) shipped and verified live 2026-05-19. No sprint is currently active.

## Pipeline Status
- **Hotfix-2 through Hotfix-8:** ALL DONE, post-audits PASS for H2-H7; H8 post-audit pending
- **v1.0.0:** ✅ LIVE at https://panefreequoting.com
- **Next sprint:** `drafts/hotfix-9.md` (Tailwind CDN migration + mobile nav drawer) — `audit_status: pending_reaudit` after Bug 5 was folded in 2026-05-19

## Recent close-outs
- `PLANNING/done/hotfix-8.md` — CSP unsafe-inline / viewport meta / gunicorn docstring
- `PLANNING/notes/hotfix-8-notes.md` — execution notes (sprint dispatched out-of-band by Sonnet 4.6 via openclaw; Opus close-out)
- `MAINTENANCE_LOG.md` — Bug 2 root-cause entry (CSP blocking inline scripts)

## Tracked for next sprint
See `PLANNING/drafts/hotfix-9.md`:
- Bug 3: Tailwind CDN → compiled CSS migration
- Bug 5: Mobile nav overflow — hamburger menu + slide-out drawer via `static/js/nav.js` (CSP-safe externalized JS)
- Bug 3/Bug 5 ordering: T6 (nav fix) runs AFTER T3 (CDN migration) so any new Tailwind classes are in the compiled output

When ready:
1. Chris dispatches Inquisitor for re-audit of Hotfix 9 (Bug 5 was not in original audit scope)
2. On approval, Jade promotes `drafts/hotfix-9.md` → `current-sprint.md`
3. Cut `sprint-9` branch off `master`
