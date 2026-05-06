# Sprint 4 — Stress Test Results

**Sprint:** 4
**Branch:** `sprint-4`
**Date:** 2026-05-06
**Probe:** `testing/stress_probe.py` against live dev server (`http://127.0.0.1:5001`)

---

## Summary

| Metric | Pre-fix | Post-fix |
|---|---|---|
| Probes run | 7 | 11 |
| Probes passing | 6 | 11 |
| Critical (P0) findings | 1 — BUG-008 | 0 |
| High (P1) findings | 0 | 0 |
| Verification probes added (T3) | n/a | 4 |

All bugs from the manual walkthrough (T1) and the original stress probe pass have verified fixes. No new findings surfaced during this re-run.

---

## Pre-fix vs Post-fix — verbatim probe output

### P1 — Arbitrary file download via `/download/<filename>`

**Pre-fix (BUG-008 confirmed P0):**
```
GET /download/sovereign.db -> 200 (86,016 bytes)
GET /download/app.py       -> 200 (69,810 bytes)
GET /download/config.py    -> 200 (3,803 bytes)
GET /download/models.py    -> 200 (9,338 bytes)
```
Any authenticated user could exfiltrate the DB and source files.

**Post-fix:**
```
GET /download/sovereign.db -> 404
GET /download/app.py       -> 404
GET /download/config.py    -> 404
GET /download/models.py    -> 404
GET /download/.env         -> 404
GET /download/../../etc/passwd -> 404
```
Sealed. Per-user PDF buckets (`output/<user_id>/`) make these paths unreachable from the route.

---

### P5 — Email verification gate
```
unverified /generate -> 403 code=EMAIL_NOT_VERIFIED
verified /generate   -> 200 status=success
```
Pass (unchanged from pre-fix).

### P6 — Rate limit (10/hr free user)
```
12 quote attempts -> codes: [200,200,200,200,200,200,200,200,200,200,429,429]
429 count: 2 (expected 2)
```
Pass — first 10 succeed, 11th and 12th rate-limited.

### P8 — Negative pane count
```
negative panes -> 400 "Pane count for floor1 cannot be negative."
```
Pass — engine validation rejects.

### P9/P10 — Unicode + 10kB inputs
```
garbage payload -> 200 (file: quote_76890d.pdf)
```
Accepted. Latin-1 strip in PDF render + Jinja autoescape in templates means no exploit reachable. Defense-in-depth observation, not a bug.

### P11 — SQL injection on `/login`
```
' OR '1'='1                  -> 200 (login form re-render)
admin'--                     -> 200
x'; DROP TABLE users;--      -> 200
x' UNION SELECT ... FROM users-- -> 200
```
Pass — SQLAlchemy parameterization holds; users table intact post-run.

### P12 — `/dev/grant-credits` gate
```
/dev/grant-credits -> 404
```
Pass — route is hard-gated by `DEV_MODE and not STRIPE_SECRET_KEY`.

---

## New verification probes (T3)

### P13 — BUG-006 fix: defaults no longer flagged as "(Custom Rate)"
```
line items: 4, with '(Custom Rate)': 0
PASS
```
Generated a quote with a fully-default profile and inspected the persisted snapshot. Zero line items contain `(Custom Rate)` — pre-fix every item carried it because the frontend pre-populated `.value` on override fields. Post-fix the override inputs use `.placeholder`, so `engine.py` only sees overrides the user explicitly typed.

### P14 — BUG-007 fix: sequential `Q-NNNNNN` quote numbers
```
quote rows: [(1, 'Q-'), (2, 'Q-'), (3, 'Q-')]
PASS
```
Three back-to-back `/generate` calls produced quote_number=1, 2, 3 with prefix `Q-`, claimed atomically via `_claim_quote_number()`. Mirrors the existing invoice-number pattern; gap-aware, idempotent.

### P15 — BUG-003 fix: new users redirected to `/profiles/new`
```
GET / -> 302  Location: /profiles/new
PASS
```
A freshly-registered user with zero profiles gets bounced from the index route, with the onboarding flash. First profile creation IS the onboarding step.

### P16 — BUG-008 fix: cross-tenant download blocked
```
user A generated: quote_a00696.pdf
user A own file               -> 200
user B cross-tenant fetch     -> 404
user B /download/sovereign.db -> 404
user B /download/app.py       -> 404
PASS
```
User A can download their own PDF. User B, knowing the exact filename, cannot. Source files and the DB are unreachable from any logged-in account.

---

## How this works (BUG-008 architecture note)

PDFs are now stored at:
```
output/<user_id>/quote_<rand>.pdf
output/<user_id>/invoice_<rand>.pdf
```

The `/download/<filename>` route resolves the file inside `_user_pdf_dir(current_user.id)` only:

- The user_id never appears in the URL — it's pulled from the session.
- `os.path.basename(filename)` strips path traversal (`..`, leading `/`).
- The bucket directory only contains PDFs that user has generated.
- A leaked filename from user A doesn't help user B: B's bucket doesn't contain that file → 404.
- The directory does not contain `sovereign.db`, `app.py`, `.env`, or any source — only generated PDFs.

This is multiple-defense-in-depth: even if `os.path.basename` were bypassed somehow, the per-user prefix would still block escape. The `404` (rather than `403`) on misses also avoids leaking whether a filename exists for some other user.

---

## Reproduction

```
# from project root
python app.py &              # start dev server
python testing/stress_probe.py
```

The probe is idempotent — it creates fresh test users (`probe_<hex>@probe.test`) on each run, so it can be re-run without DB cleanup. Test users accumulate in the DB over time; nuke periodically with:
```
sqlite3 sovereign.db "DELETE FROM users WHERE email LIKE '%@probe.test';"
```

---

## Items still open (post-Sprint-4 follow-ups)

These are flagged in `PLANNING/notes/sprint-4-notes.md` and intentionally **not** in Sprint 4 scope:

- **OBS-002** Credit-refund non-atomic with the Quote rollback on PDF failure. Edge-case; Sprint 5 reliability candidate.
- **OBS-003** 31-day session lifetime. Already addressed: `PERMANENT_SESSION_LIFETIME = timedelta(hours=24)` is set in `app.py`.
- **BUG-009** Raw Unicode in DB columns (defense-in-depth only — no exploit reachable today).
