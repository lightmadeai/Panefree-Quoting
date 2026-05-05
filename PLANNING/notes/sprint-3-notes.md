# Sprint 3 Execution Notes

Started: 2026-05-03 (Claude Code, branch `sprint-3`, base `master` @ 4dc8640)

Sprint-1 + Sprint-2 are merged to master. Clean cumulative base.

## Pre-execution decisions (Thorn confirmed at "go" time)

- **T2 one-time top-up migration**: implementing as written. Project not deployed → empty users table → no-op in practice. Code path stays correct against any future populated DB.
- **T4 email verification gates active subscribers too.** Without this, a stolen-card subscription is an abuse vector. If post-audit prefers exempting subscribers, easy revert.
- **T4 verification email backend**: defers to a console log of the verification URL (mirrors the dev-mode pattern used by `dev_grant_credits` and T3's contact-form notification). Real email delivery is out of scope across the entire sprint.
- **T4 task weight**: flagged at sprint-start as overweight (5 sub-features under one acceptance block: password rules, lockout, email verification, token storage, session timeout). Thorn opted to proceed rather than send back to Jade. Captured here for post-audit consideration of whether T4 should split into 4–5 tasks for future sprints with similar shape.

## Decisions / deferrals

**T1 — soft-cap CTA wiring discovered to need the same URL split as T3.** The Sprint-2 helper took `contact_email` and built `mailto:{email}`. Sprint 3 T3 makes `/contact` the new CTA target. Refactored `build_soft_cap_notice` to take `contact_url` directly (caller picks). Drops `contact_email` from the payload. Sprint-2 tests updated accordingly. Frontend doesn't yet consume `soft_cap_notice` — confirmed via grep — so no rendering breakage.

**T1 — past_due subscribers ARE rate-limited.** Manifest doesn't explicitly say. My read: an account in dunning shouldn't double as a quote firehose. Active subscribers (only) get the bypass. Captured in code comment + dedicated test.

**T2 — floor migration uses `WHERE balance < N` not a `received_topup` flag.** Pre-launch project, no admin tooling sets balances below 10 today. If that ever changes the migration would re-bump them on every boot — needs a stronger guard then. Documented in CLAUDE.md "Free tier" section.

**T3 — `/contact` requires login.** Manifest doesn't specify. Reasoning: the soft-cap CTA fires only for active subscribers (who are by definition logged in). Anonymous public marketing-form access is a different use case worth its own sprint if needed.

**T3 — admin notification is `app.logger.info()`, not `print()`.** Cleaner (respects log levels, can be redirected to a file later) and consistent with how Flask conventionally surfaces operational events. A future "deliver via email" sprint replaces this line, not the surrounding logic.

**T4 — password rule is min: ≥8 chars + ≥1 digit (no upper-case / special-char requirements).** Manifest specified exactly that. Resisted scope creep — adding "must have uppercase" or "must have symbol" without manifest approval would be improvising scope.

**T4 — login lockout consumes the counter into a `locked_until` and resets to 0.** When the 5th failure fires the lockout, `failed_login_attempts` resets to 0 and `locked_until` carries the cooldown. Successful login after cooldown also resets. The alternative (keep counter at 5 + cooldown) would lock the user permanently after the next single failure post-cooldown. This way a user gets a fresh 5-strike budget once their lockout expires.

**T4 — unknown-email login attempt does not reveal that the email isn't registered.** Both "wrong password for known user" and "no such user" return the generic "Invalid email or password." Standard credential-stuffing defense.

**T4 — verification email backend is a console log (`app.logger.info("[EMAIL-VERIFICATION] ...")`).** Real delivery is out of scope per manifest's punt on email backend (T3 phrasing). Future sprint swaps the log line for a real send.

**T4 — subscribers MUST verify email.** Pre-execution decision confirmed by Thorn. Without this, a stolen-card subscription is an abuse vector. Test `test_subscriber_also_must_verify` enforces.

**T4 — pre-Sprint-3 users grandfathered as verified via `_backfill_email_verified()`.** The backfill identifies them by `email_verification_token IS NULL` (Sprint-3 registration generates a token; older users have none). Idempotent. Project not deployed → no users → no-op in practice; the code path is correct against any future populated DB.

**T4 — task weight (flagged at sprint-start) confirmed in retrospect.** T4 ended up as 5 model column adds + 4 route changes + 1 new route + 1 Flask config line + 13 unit tests. Roughly equal to T1+T2 combined. Recommend the post-audit pass through this task with an eye on whether the 5-sub-feature shape held together cleanly or should split next time.

**Test helpers updated to satisfy T4 password rules + auto-verify users.** Both `test_sprint3.py` (legacy, pytest-style) and `test_sprint3_pipeline.py` (new, unittest-style) helpers updated. Default password `"pw12345"` (7 chars, fails T4) → `"pw1234567"` (passes). Helpers auto-verify the user post-registration so existing tests don't have to navigate the verification flow. Tests that specifically need an unverified user pass `verify=False`.

## Verification performed

- `python -m py_compile` on all modified `.py` files: clean.
- **49 tests** in `test_sprint2.py` + `test_sprint3_pipeline.py` (unittest): all pass.
- **7 legacy tests** in `test_sprint3.py` (pytest): all pass after helper update.
- **Total: 56 tests across the project** — all green.
- Migration tested implicitly via the integration test setup (each test boots fresh app → migration runs → user inserts succeed).
- Dev server not running this sprint (was killed at end of Sprint 2 merge). Static checks above + integration tests are the verification surface.

## Open questions surfaced during execution

- **Should `/contact` allow anonymous submissions?** Currently `@login_required`. Marketing might want a public version for cold leads. Flag for product discussion, not a code question.
- **Should the verification token grant a "resend" option?** Currently expired = "sign in to request a new one" but there's no UI flow for re-issuing. Future sprint: add a "Resend verification email" button on /account or via an /resend-verification route.
- **Should T4's session timeout (24h) be tunable via config?** Hardcoded right now. If someone wants 7-day sessions for an admin role later, this needs to move to a config var.

