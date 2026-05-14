# Hotfix-7 Execution Notes

**Branch:** `master` (direct commits, single-operator launch session)
**Executor:** Claude (Chris co-driving)
**Per:** Claude-drafted proposal, Chris-authorized direct execution
  (formal Jade adoption skipped given launch-timing pressure)
**Inquisitor post-audit:** PASS, 0 blocking, 5 non-blocking remarks
  (2026-05-14, `hotfix-7-post-audit.md`)
**Condition C3:** SATISFIED — launch gate cleared
**Launch session:** 2026-05-14 afternoon (CDT)
**v1.0.0 tag:** applied 2026-05-14 ~14:50 CDT on commit `7210991`

---

## Scope reality vs. proposal

Per the H7 proposal, T1-T8. What actually shipped:

- ✅ **T1** — `LAUNCH.md` (commit `a4fac4b`)
- ✅ **T2** — DNS flip to `panefreequoting.com` (executed at launch)
- ✅ **T3** — Brand rename "Panefree Quotes" → "Panefree Quoting" (commit `9244f92`, plus launch-day span-fix in `7210991`)
- ✅ **T4** — Email-verified gate on `/checkout` (commit `9244f92`)
- ⏭️ **T5** — Tailwind CDN → compiled CSS (deferred per Inquisitor's accepted R1 recommendation; in post-launch.md)
- ⏳ **T6** — UptimeRobot monitors (apparently set up out-of-band — confirmed via UptimeRobot HEAD requests in launch-day logs; need to verify monitor configuration matches what was intended)
- ✅ **T7** — Stripe webhook regression test (commit `cc8991c`, 6/6 passing)
- ✅ **T8** — 30-min active watch + v1.0.0 tag (executed at launch; this notes file)

Plus the H6 carry-forward heresies cleared in burst-1 (commit `77d4908`):
- H05 — uncommitted legal files committed and deployed
- H06 — Privacy Policy blank appeals email filled
- H07 — Privacy Policy truncated `/contac` URL fixed

---

## Launch-day timeline (CDT)

| Time | Event |
|---|---|
| ~12:30 PM | H7 post-audit committed (`ecb7968`) — Inquisitor PASS verdict |
| ~12:35 PM | R4 fix landed (`current-sprint.md` adopted_by reconciliation) |
| ~1:30 PM | §1 Go/No-Go checklist run — all green |
| ~1:50 PM | Render Custom Domain added: `panefreequoting.com` + `www` |
| ~1:55 PM | Cloudflare DNS records added (CNAMEs, DNS-only / gray cloud) |
| ~2:05 PM | Render verified DNS, Let's Encrypt cert provisioning began |
| ~2:15 PM | Certs ACTIVE for both apex + www |
| ~2:20 PM | `/health` + 3 legal routes confirmed 200 on production domain (via curl --resolve, local DNS still propagating) |
| ~2:25 PM | `APP_BASE_URL` Render env var updated to `https://panefreequoting.com` |
| ~2:30 PM | Stripe webhook endpoint URL updated to `https://panefreequoting.com/webhook/stripe` (whsec_ unchanged) |
| ~2:35 PM | Smoke test (LAUNCH.md §2.10) — signup with non-account email, verification email arrived, checkout redirect to Stripe confirmed |
| ~2:40 PM | **Smoke test caught visible brand misses** — login/forgot/register/reset_password pages said "Quote Studio"; _nav.html said "Panefree Quotes". Strings were split across `<span>` tags so the H3 literal grep missed them. |
| ~2:43 PM | Brand fix swept across 5 templates (`7210991`) |
| ~2:48 PM | Render redeployed, all routes still 200, brand text verified correct in browser |
| ~2:50 PM | **`v1.0.0` tagged on `7210991` and pushed to origin** |
| ~2:50 PM | Watch window §3 started |
| ~3:00 PM | 15-min pulse — `/health` 200, CPU 0.026% baseline, no errors |
| ~3:20 PM | 30-min pulse — all 5 pass criteria green. Watch CLOSED. |

---

## Decisions, deferrals, and things future-me should know

### T1 — LAUNCH.md

- **391 lines** — long for a v1, but the audit gate weight and "first launch we've ever done" justify the verbosity. Future launches can use this as a template with shorter customizations.
- **§9 C3 satisfaction statement** is the critical structural element — it makes the audit gate explicit and unambiguous so a future, hurried Chris doesn't skip it.
- **Section 8 (post-launch priorities)** intentionally lives in LAUNCH.md so launch-day Chris doesn't conflate them with watch-window action items. Different mental mode.

### T3 — Brand rename (and the gotcha)

- The original H3 sweep used `git grep -F "Panefree Quotes"` to find 42 matches across 27 files. **It did not match the 5 instances where the brand was split across nested `<span>` tags** (e.g., `Panefree<span class="text-blue-400"> Quotes</span>`).
- Caught during launch-day smoke test. Fix in `7210991` — pattern-specific replacement, not a literal grep.
- **Lesson:** brand rename sweeps should grep for both the flat string AND for the visible-text fragments split by HTML markup. Or: render every page in a browser and eyeball it before claiming completion.

### T4 — Email-verified gate

- Used `flash + redirect`, not the JSON 403 pattern from `/generate` (line 1496). Correct for the form-POST shape of `/checkout`.
- `db.session.get(User, current_user.id)` re-fetches to get a fresh `email_verified` value (rather than relying on cached `current_user` which could be stale within a long session).
- Verified in Inquisitor post-audit T4 evidence section.

### T5 — Tailwind deferred

- Inquisitor's pre-audit R1 explicitly recommended deferral. LAUNCH.md §8 (post-launch priorities) lists it. Tracked in `post-launch.md` 🟣 carry-forward section.
- The `cdn.tailwindcss.com` script is a JIT compiler in the browser — security tradeoff is real, but the alternative requires a Node build step + Render's build command changes + a `package.json` for a Flask project. Worth doing in the first cleanup sprint, not blocking launch.

### T6 — UptimeRobot

- Apparently **already configured** out-of-band (visible in launch-day logs as `UptimeRobot/2.0` HEAD requests every ~5 min).
- Current target appears to be the root `/`, which 302s to `/login` — both return non-error codes so the monitor reports success. **Improvement opportunity:** retarget at `/health` for cleaner signal (a 200 from `/health` confirms DB connectivity, where a 302 from `/` only confirms the WSGI process is alive).
- Backup heartbeat URL also not yet configured. Tracked in post-launch.md.

### T7 — Stripe webhook regression test

- 6/6 passing locally (`pytest testing/test_stripe_webhook.py -v`).
- Uses real `StripeObject` via `stripe.Event.construct_from()` — this is the design choice that makes the test actually guard against H6's bug class. Dict fixtures would silently pass even if `event.get(...)` were reintroduced.
- Pre-flight sanity assertion (`isinstance(event, StripeObject)`) is documented in the test itself so future maintainers don't replace the fixture with a dict thinking they're simplifying.
- **Manual TODO (low priority):** wire `pytest testing/` into CI when CI exists. Right now the project has no CI runner — tests are run on-demand. For v1 launch this is acceptable; pre-customer phase.

### T8 — Watch window

- Watch was uneventful. Standard internet background noise (UptimeRobot probes, Go/okhttp bot scanners) and zero customer traffic (no marketing campaign live yet).
- Favicon 404s observed (`/favicon.ico`, `/favicon.png`) — browser auto-requests, we don't serve either. Tracked as a cosmetic post-launch task.
- **Critical observation:** CPU baseline 0.026% on a Render Starter instance is wildly under-utilized. Single-worker gunicorn + memory-storage rate limiter is honestly overkill for current traffic. Bump triggers in post-launch.md (20+ paying customers OR p95 >500ms) remain correct — don't pre-optimize.

---

## What surfaced in execution that didn't fit a numbered task

### Mid-launch redeploy 502 spike (false alarm)

When I pushed the post-audit commit (`ecb7968`), Render auto-deployed it (even though the diff was planning-only files). My automated `/health` curl during §1 caught a 502 mid-redeploy. Chris confirmed via Render Events tab that a deploy was in progress; ~90 seconds later all routes were 200 again.

**Implication for future launches:** every push triggers a Render redeploy, even non-code commits. Keep planning/audit pushes outside the launch window if possible, or accept the brief 502 gap. In our case it was 90 seconds with zero customers — no impact.

### Launch SHA rollback target was `ecb7968`, not `7210991`

Per LAUNCH.md §2.1, the launch SHA was recorded at the start of the flip. We picked `ecb7968` (the post-audit commit) before realizing the brand-span-fix would also need to ship. After the brand fix landed (`7210991`), the **actual launch tag** went on `7210991`, and the Tier 1 rollback target conceptually became `ecb7968`.

In a rollback scenario, deploying `ecb7968` would restore the audit-passed state minus the visible brand fix — which is functionally complete and audit-clean, just cosmetically inconsistent. Acceptable rollback target.

### UptimeRobot already monitoring

We hadn't intentionally configured it during this sprint, but `UptimeRobot/2.0` HEAD requests show up in launch-day logs every ~5 min. Either Chris or Jade set this up earlier and didn't track it. **Effectively closes part of T6.** Need to confirm the configuration:
- What URL is being monitored?
- What's the alert email?
- Is the heartbeat URL for backup script set up too?

---

## Non-blocking remarks from H7 post-audit — disposition

| ID | Remark | Disposition |
|---|---|---|
| R1 | Tailwind CDN deferred | In `post-launch.md`, scheduled for first cleanup sprint |
| R2 | `gunicorn.conf.py` docstring lies about "2 workers" | In `post-launch.md` |
| R3 | Cookie Policy `__cfduid` deprecated | In `post-launch.md` (Termly + manual HTML fix) |
| R4 | `current-sprint.md` `adopted_by: pending` | **Closed** in commit `ecb7968` — frontmatter reconciled |
| R5 | `EMAIL_FROM_NAME` Render env var manual update | **Closed** before DNS flip (verified via screenshot during §1) |

---

## Files changed in H7 (this sprint)

Commits on `master` in chronological order:

1. `77d4908` — burst-1: legal cleanup + audit artifacts (H05/H06/H07)
2. `9244f92` — burst-2: H02 email-verified gate + H03 brand rename
3. `cc8991c` — T7: Stripe webhook regression test
4. `a4fac4b` — T1: LAUNCH.md
5. `d1b737b` — post-launch.md additions
6. `ecb7968` — post-audit landed + R4 reconciliation
7. `7210991` — launch-day brand fix (span-broken strings)
8. **`v1.0.0` tag on `7210991`** — production launch marker

---

## Carry-forward from prior hotfixes — status

Most of these were tracked in H6 close-out notes; updating for H7 disposition:

- **H3 R1:** `.env.example` missing H3 env vars — CLOSED (all H3 vars present)
- **H3 R2:** `test_account_lifecycle.py` doesn't exist — STILL OWED (`post-launch.md`)
- **H5 R1:** `[BACKUP-*]` tags not in DEPLOYMENT.md log catalog — STILL OWED (`post-launch.md`)
- **H5 R2:** Real B2 round-trip not exercised in-sprint — STILL OWED; will validate on first scheduled backup run post-launch
- **H5 R3:** Schema dumps accumulate without prune — STILL OWED, negligible
- **H5 R4:** No app-level functional restore test — STILL OWED (`post-launch.md`)
- **H6 R1:** Test fixtures use dict, not real StripeObject — **CLOSED** in H7 T7 (`cc8991c`)
- **H6 R2:** `LAUNCH.md` not written — **CLOSED** in H7 T1 (`a4fac4b`)

---

## Open questions for Inquisitor (none requiring immediate response)

1. Is the H7 → v1.0.0 → watch close-out a satisfactory close to the Stabilize phase, or should there be a phase boundary marker / formal phase transition entry in the project registry?
2. For the next sprint (cleanup / post-launch), should the prefix continue as `hotfix-N` or shift to `sprint-N+1` numbering now that we're past launch? `Hotfix-` semantics imply stabilization; future sprints will mix stabilize-class + feature-class work.
3. Worth a brief retro on the H3 brand rename gap (span-broken strings escaping the literal grep)? The lesson is generalizable to future brand work, and Inquisitor's role includes process improvements.

---

## Launch is live.

`https://panefreequoting.com` — production. `v1.0.0` tagged on `7210991`.

End of execution notes.
