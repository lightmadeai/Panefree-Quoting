# Sprint Pipeline Protocol — Canonical Reference

**Steward:** Inquisitor (protocol edits require Inquisitor approval; Jade proposes changes via `drafts/protocol-change-N.md`)
**Sponsor:** Thorn (Chris)
**Adopted:** 2026-05-01
**Last updated:** 2026-05-03

---

## 0. Priority Queue

When multiple projects have sprints ready for execution, they execute in priority order:

1. **Window Quoting** (live revenue software — always first)
2. **Budget Tracker** (pre-launch — on deck)
3. **All other projects** (in order of revenue proximity)

If Window Quoting needs a Sprint 4+, it takes the queue over Budget Tracker Sprint 1.

---

## 1. Folder Structure

```
projects/<project>/PLANNING/
  README.md                  # symlink → shared/PLANNING-PROTOCOL.md (this file)
  current-sprint.md          # the ONE active sprint Claude is executing
  drafts/                    # Jade drafts here
  research/                  # Solis publishes here (sprint-scoped)
  content/                   # Luna publishes here (sprint-scoped)
  audits/                    # Inquisitor publishes here
  done/                      # archived completed sprints
  notes/                     # per-sprint notes from Claude (sprint-N-notes.md)
```

## 2. Lifecycle

1. Jade drafts in `drafts/sprint-N.md` (status: `draft`)
2. Solis publishes research → Jade links by file path in `research_refs`
3. Luna publishes copy → Jade links by file path in `content_refs`
4. **Inquisitor pre-audits the draft.** Updates `audit_status` to `approved` or `rejected`. **Sprint cannot move forward without this.**
5. On approval, Jade renames `drafts/sprint-N.md` → `current-sprint.md`
6. Thorn launches Claude Code, which reads `current-sprint.md` and executes
7. Claude appends decisions/deferrals to `notes/sprint-N-notes.md` as it works
8. On completion, Claude moves to `done/sprint-N.md` on a `sprint-N` git branch
9. **Inquisitor post-audits.** Reads `done/sprint-N.md`, `notes/sprint-N-notes.md`, and the actual git diff. Writes report to `audits/sprint-N-audit.md`
10. **Inquisitor promotes the next approved sprint.** If the next sprint in the pipeline has `audit_status: approved` and `status: approved` (or `ready`), Inquisitor renames `drafts/sprint-N+1.md` → `current-sprint.md`, updates its `status` to `ready`, and alerts Thorn that Claude can be launched. This eliminates the bottleneck where Jade's rename step was not being executed promptly.
11. Jade uses Inquisitor's audit to plan sprint N+2 (or further)

## 3. Sprint Manifest Format

```markdown
---
sprint: N
project: <codename>
drafted_by: Jade
research_refs: [research/sprint-N-<topic>.md]
content_refs: [content/sprint-N-<topic>.md]
audited_by: Inquisitor
audit_status: draft        # draft | pending | approved | rejected
status: draft              # draft | ready | in-progress | done | contested | aborted
created: YYYY-MM-DD
---

# Sprint N — <one-line goal>

## Why
[1-2 sentences linking to research/business reasoning]

## Goals
- Measurable goal 1
- Measurable goal 2

## Tasks
- [ ] **T1: <task>**
  - touches: `<file path(s)>`
  - acceptance: <falsifiable criterion — how we know it's done>

## Out of scope
- [explicit non-goals — protect against drift]

## Open questions
- [things Claude should ask before acting]

## definition of done
- All tasks checked
- `npm run build` clean (or project equivalent)
- Commit on `sprint-N` branch
- `notes/sprint-N-notes.md` updated
```

## 4. Role Boundaries

| Agent | Writes to | Reads from | Forbidden |
|---|---|---|---|
| Jade | `drafts/`, promotes to `current-sprint.md` | everything | editing `audits/`, `research/`, `content/`, code |
| Solis | `research/` (sprint-scoped filenames) | sprint drafts when asked | sprint manifests, `audits/`, code |
| Luna | `content/` (sprint-scoped filenames) | sprint drafts when asked | sprint manifests, `audits/`, code |
| Inquisitor | `audits/`, `current-sprint.md` (promotion only), plus `audit_status` and `status` fields on drafts | everything (drafts, research, content, done sprints, git diffs) | code, drafts (except status field) |
| Claude Code | `current-sprint.md` (status updates), `notes/`, `done/`, the actual code | everything | other agents' folders |

**Project-local `CLAUDE.md`.** Each project may have a `CLAUDE.md` file in its root, owned by the project owner (per `shared/projects.md`). It is **project-local context, not protocol content** — typical contents include a pointer to `PLANNING/README.md`, project-specific quirks (tech stack, business pivots, naming sensitivities), and slash command reminders. It is **not hardlinked** to any canonical; per-project drift is expected because the content is by definition project-specific. Claude Code reads this file automatically when launched in that project.

## 5. Hard Rules

### 5.1 Task cap
Maximum **5 tasks per sprint**. If more are needed, decompose into multiple sprints. Inquisitor rejects any draft exceeding this cap.

### 5.2 Falsifiable acceptance criteria
Every task MUST have an `acceptance:` field that is testable and objective. No "improve UX" — instead "login flow completes in <3s with no console errors." Inquisitor rejects non-falsifiable criteria.

### 5.3 Sprint-scoped filenames
All files in `research/`, `content/`, and `drafts/` are prefixed with sprint number:
- `research/sprint-N-<topic>.md`
- `content/sprint-N-<topic>.md`
- `drafts/sprint-N.md`

This eliminates collision risk across concurrent or sequential sprints.

### 5.4 Pull-based publishing
Solis and Luna publish to `PLANNING/` lanes ONLY when a sprint draft references their lane. Proactive research/content stays in their agent workspace (`memory/cells/`) until Jade links it into a sprint.

### 5.5 Serial execution per project
One `current-sprint.md` per project at a time. Multiple projects CAN run in parallel (different `PLANNING/` trees). Within one project, serial only.

### 5.6 Sprint numbering
Jade owns the sprint counter. `next_sprint` number is tracked in this file (see below). Jade increments on promotion from draft to current.

### 5.7 Audit SLA
Inquisitor pre-audits within **4 hours** during active hours (08:00-23:00 Pacific). Outside active hours, audits queue for the next active window. No SLA clock for side hustle bandwidth — this is a target, not a contract.

### 5.8 RAM coordination
Jade heartbeat pauses during active Claude execution. No concurrent Inquisitor heavy ops (audits, large reads) while Claude Code is mid-sprint. Daily Purge at 2AM is safe — no sprints should be active during quiet hours.

## 6. Status Definitions

| Status | Meaning | Who sets it | Next states |
|--------|---------|-------------|-------------|
| `draft` | Jade is drafting, not ready for audit | Jade | `pending` |
| `pending` | Draft complete, awaiting Inquisitor pre-audit | Jade | `approved`, `rejected` |
| `approved` | Inquisitor pre-audit passed, ready for execution | Inquisitor | `ready` |
| `ready` | Promoted to `current-sprint.md`, awaiting Claude launch | Jade | `in-progress` |
| `in-progress` | Claude is executing | Claude | `done`, `aborted` |
| `done` | Claude completed execution | Claude | `contested` (if post-audit fails) |
| `contested` | Inquisitor post-audit found drift from spec | Inquisitor | remediation sprint drafted by Jade |
| `aborted` | Mid-sprint cancellation (exam, machine issues, priority change) | Thorn | Inquisitor still post-audits |

## 7. Audit Failure Recovery (Contested Sprints)

When Inquisitor post-audits and finds Claude drifted from spec:
1. Sprint moves to `done/sprint-N.md` with `status: contested`
2. Inquisitor writes `audits/sprint-N-audit.md` with `verdict: reject` and remediation spec
3. Jade drafts remediation sprint (`sprint-N.1`) referencing the contested sprint and audit
4. Thorn approves the remediation plan before Claude executes
5. **Claude does NOT self-repair.** No unilateral fixes on contested sprints.

## 8. Git Branch Discipline

- **Create:** Claude creates `sprint-N` branch on sprint start
- **Merge:** Thorn merges after Inquisitor post-audit approval
- **Purge:** Inquisitor purges stale branches (>7 days with no corresponding `current-sprint.md`) during daily audit

## 9. Sprint Aborts

If a sprint needs to stop mid-execution:
1. Thorn declares abort
2. Sprint moves to `done/sprint-N.md` with `status: aborted` and a note explaining why
3. Inquisitor still post-audits to capture what was completed before abort
4. Jade uses abort audit to plan next sprint (resume or restructure)

## 10. Project Naming Convention

- **Folder names** use hyphens for multi-word: `one-line`, `bom-to-bin`, `resumeforge`
- **Python entry points** are named after the project (`bom_to_bin.py`), not `main.py`
- **Flutter/Next.js** follow their own conventions (acceptable)
- **Every project** has a `PROJECT.md` in the root declaring codename, type, entry point, description, owner, status
- **Sprint pipeline** uses codenames, not marketing names
- **Registry paths** in `shared/projects.md` are **`~/`-relative** (e.g., `~/projects/budget-tracker`, `~/.openclaw/workspace/projects/window-quoting`). Tooling resolves these by expanding `~` to the user's home directory. This gives `/pipeline-status` and slash commands deterministic resolution across the two project trees (`~/projects/` for Thorn-owned coding projects, `~/.openclaw/workspace/` for agent-owned ones).

## 11. Inter-Agent Communication

Per `shared/world-model.md` Inter-Agent Communication SOP. Key points:
- Route directly to agents via Discord ping or `sessions_send` — no subagent proxies
- Solis/Luna reachable via `sessions_send` until bot IDs assigned
- CC Chris only if he was the original initiator, even through a proxy
- If Inquisitor is the disputed party, Jade escalates directly to Chris

## 12. Protocol Distribution

This file is the **canonical source**. Project `PLANNING/README.md` files are **hardlinks** to this file. Do NOT edit project-local copies — edit `shared/PLANNING-PROTOCOL.md` and changes propagate via hardlink.

**§12.1 Mandatory Relink After Edit**
After any edit to `shared/PLANNING-PROTOCOL.md`, the editor MUST run `scripts/relink-protocol.ps1` to restore hardlink integrity. This is a mandatory step in the protocol-change workflow, equivalent to running validation after a config change. Most modern editors and tools (Edit, vim, sed -i, VSCode) perform atomic replacement (write-to-temp → rename-over-original), which breaks hardlinks by creating a new inode. The relink script detects drift and repairs it.

A daily cron job (Protocol Integrity Check, 5AM Pacific) also verifies hardlink integrity and alerts #turing-temple on drift.

When adding a new project to the sprint pipeline:
1. Create the `PLANNING/` directory structure (drafts, research, content, audits, done, notes)
2. Create a hardlink: `mklink /H <project>\PLANNING\README.md <workspace-root>\shared\PLANNING-PROTOCOL.md`
3. Create `PROJECT.md` in the project root
4. Register the project in `shared/projects.md`
5. Add the project path to `scripts/relink-protocol.ps1` `$projectPaths` array
6. Run `scripts/relink-protocol.ps1` to verify

---

## Sprint Counter

`next_sprint: 5`

<!-- Protocol v1.1 — 2026-05-02 — Canonical source at shared/PLANNING-PROTOCOL.md
     v1.1: §4 adds CLAUDE.md role note; §10 adds registry path convention.
     Per Inquisitor verdict on Tooling Bundle Audit (2026-05-02). -->

*(Jade increments this number when promoting a draft to `current-sprint.md`)*