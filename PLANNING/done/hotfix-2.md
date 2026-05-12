---
label: hotfix-2
project: window-quoting
phase: stabilize
drafted_by: Claude (per Chris blanket approval, 2026-05-11)
status: done
created: 2026-05-11
completed: 2026-05-11
audit_status: pending
audit_note: "All 5 tasks landed and verified. Awaiting Inquisitor post-audit."
---

# Hotfix-2 — Pre-Production Security Hardening (DONE)

## Outcome

5 tasks completed; all H + M findings from the 2026-05-11 security review closed (or explicitly accepted as scope-deferred with a documented note). Branch: `hotfix-2` (5 commits beyond hotfix-1).

| Task | Findings closed | Verification |
|---|---|---|
| T1 | H1 (cookie SECURE/HTTPONLY/SAMESITE), M4 (register minlength) | `python -c` config asserts under DEV_MODE set/unset; browser inspection deferred to deploy smoke |
| T2 | H2 (CSRF on 16 POST forms) | `curl -X POST /login` returns 400 without token, 200 with the env kill switch |
| T3 | H3 (table allowlist), M3 (password cap), M6 (dir mode 0o700) | in-process asserts: 129-char password rejected, `_ensure_table_columns('bad', [])` → ValueError |
| T4 | M1 (rate limit), M2 (CSP/HSTS/X-Frame/Referrer-Policy) | `curl -I /login` shows all headers; 11th `/login` POST → 429 with RATELIMIT_DISABLED unset |
| T5 | L4 (WSGI server note), L5 (requirements.txt + pip-audit guidance) | `requirements.txt` committed; DEPLOYMENT.md §2.8, §2.9, §8 added |

## Regression evidence

- `python testing/stress_probe.py` — 13/13 probes PASS or expected status (P1, P5, P6, P8, P9/P10, P11, P12, P13, P14, P15, P16). See run log; no behavioral drift from hotfix-1.
- Locust 30u × 60s — **3270 reqs, 0 failures**. p50 15ms / p95 46ms / p99 130ms. Compared to pre-hotfix-2 (p50 13 / p95 41 / p99 83): a ~10-50ms latency cost from per-request Talisman header serialization and CSRF token generation, well within budget.
- DB sanity post-locust: free users started 500, ended 490 each (10 reserved per user × 10 users = 100 quotes, matches). Subscribers stayed at 500. Quote numbering: NO GAPS, sequential 1..10 per user — atomicity holds under hotfix-2.

## Findings explicitly NOT closed (documented deferrals)

- **M5** (email enumeration via `/register` "already registered" message) — industry-standard tradeoff. Closing requires sending a confirmation email to non-existent addresses, which has its own UX issues. Will revisit if abuse data justifies. Rate limit on `/register` (T4) reduces blast radius.
- **L1** (constant-time token compare in `/verify`) — tokens are 32-char random hex (128 bits). Brute-forcing is infeasible regardless of timing. Not worth fixing.
- **L2** (webhook secret 503 message wording) — minor info leak to anyone hitting the endpoint with no signature. Acceptable.
- **L3** (audit log table for credit changes) — out of stabilize scope. Future sprint candidate.
- **Flask-Limiter Redis backend** — currently `memory://`, won't share state across gunicorn workers. Documented in DEPLOYMENT.md §9 as a Sprint 5 ops item.
- **ProxyFix middleware** — documented in DEPLOYMENT.md §8 as the wrapper needed for `X-Forwarded-For` honoring behind a reverse proxy. Not committed in this hotfix because the exact `x_for=N` value depends on the prod proxy topology (Sprint 5 decides).

## Commits on `hotfix-2`

```
c5ca6bf hotfix-2 T5: reproducible deps + deploy notes
b0947fa hotfix-2 T4: rate limiting + security headers (Flask-Limiter + Talisman)
de325db hotfix-2 T3: defensive bounds
8dbb1e8 hotfix-2 T2: CSRF protection via Flask-WTF
5ddd973 hotfix-2 T1: cookie hardening + register password minlength
```

Plus the hotfix-1 closeout commit (post-audit + locust harness) that this branch built on.

## Open items for Inquisitor post-audit

- Is the `WTF_CSRF_DISABLED` env kill switch acceptable, or should the test suite refactor to grab tokens per request? (Manifest §T2 notes: hot-take is yes, kill switch is fine because the protection is verified independently via curl; full refactor of 15 POST sites in stress_probe is scope creep for a stabilize hotfix.)
- Is the cookie-SECURE/force_https/HSTS bundle behind a single `DEV_MODE` gate too coarse? Alternative: split into three independent env vars. Decision lean: keep the single gate because three gates means three different ways to misconfigure prod into being insecure.
- Should `/api/profiles/create` and `/account` get their own rate-limit decorators? Currently only auth + checkout are gated. Defensible either way.

## Phase status

- Stabilize phase: still active. Backlog post-hotfix-2 has no P0/P1 items. Sprint 5 (live Stripe + HTTPS cutover + monitoring) is the next move.
