# Sprint 1 Execution Notes

Started: 2026-05-03 (Claude Code, branch `sprint-1`)

## Parked — for post-sprint consideration (Thorn, 2026-05-03)

Thorn pasted an alternative tier table during sprint-start. **Do not act on this during Sprint 1** — manifest values remain authoritative. Captured here so it isn't lost:

| Tier      | Price   | Credits        | $/Credit    | Discount |
| --------- | ------- | -------------- | ----------- | -------- |
| Starter   | $8.99   | 10             | $0.90       | —        |
| Pro       | $39     | 50             | $0.78       | 13%      |
| Studio    | $69     | 100            | $0.69       | 23%      |
| Unlimited | $179/yr | 1,000 softcap  | ~$0.015/mo  | 97%+     |

Deltas vs. shipped/manifest:
- Credit bundle prices differ: Starter $9.99→$8.99 (and 8→10 credits), Pro $49→$39, Studio $79→$69
- Annual sub: $149/yr (manifest) → $179/yr
- Soft cap: 500 (manifest) → 1,000

Sprint 1 implements `$149/yr` and `SOFT_CAP_THRESHOLD=500` per manifest. If Thorn wants the new numbers, raise after post-audit (Sprint 1.x or Sprint 2).

## Decisions / deferrals

**T1 — UNIQUE on `subscription_id`** SQLite's `ALTER TABLE ADD COLUMN` cannot apply a UNIQUE constraint in-place. Resolved by adding the column without UNIQUE and creating a `CREATE UNIQUE INDEX IF NOT EXISTS` on the same column right after. SQLAlchemy `unique=True` on the model is preserved so fresh `db.create_all()` deployments still get UNIQUE on the column itself.

**T2 — billing portal route was new, not "existing".** Manifest T5 says the portal call wires into "the existing `stripe.billing_portal.sessions.create()` call". No such call existed in `app.py` pre-sprint — confirmed via grep. Implemented as a new `/account/billing-portal` POST route invoked by the Manage subscription button. Behavior matches the acceptance criterion; the manifest wording was inaccurate.

**T2 — period_end fetch on subscription checkout.** `checkout.session.completed` (mode=subscription) does not carry `current_period_end`; only the subscription ID. Resolved by calling `stripe.Subscription.retrieve(sub_id)` inside the handler. If that fetch fails the handler returns 503 so Stripe retries — we deliberately refuse to flip `subscription_status="active"` without a valid period_end, because the reserve bypass would silently fail open against `None > utcnow`.

**T2 — race recovery for invoice-before-checkout.** `invoice.payment_succeeded` can in principle arrive before `checkout.session.completed` finishes binding the subscription to a User row. Added `_resolve_user_from_subscription(sub_id)` which falls back to `subscription_data.metadata.user_id` (set explicitly in `/checkout`) and self-heals by writing `user.subscription_id` once resolved. Avoids a window where the initial renewal Transaction would be lost.

**T3 — soft-cap period boundary.** No `subscription_period_start` column exists, so the cap window is approximated as `period_end - 365 days`. Annual sub → drift is negligible; informational notice anyway. If we later add monthly tiers this approximation no longer holds and a proper `period_start` column should be added.

**T3 — Heresy #12 spec literal-vs-defensive.** Spec says `db.session.get(User, current_user.id)` which, given SQLAlchemy's identity map, returns the same instance as the proxy if it's already attached. Followed the spec literally — the discipline is to never read sub state off a LocalProxy, even if the underlying object identity is the same. A stricter fresh-read (`session.refresh()` or `populate_existing=True`) is out of scope here.

**T4 — cancel-at-period-end UX gap.** A subscriber who clicks Cancel in Stripe Portal stays in `status="active"` with `cancel_at_period_end=true` until the period elapses. We don't store `cancel_at_period_end` (no column), so the nav badge and account section keep saying "renews {date}" when it actually expires. Surfacing the cancel-pending state would require either an extra column or a per-render Stripe call. Out of scope per manifest.

## Verification performed

- `python -m py_compile` on all modified `.py` files: clean.
- T1 SQL migration tested against an isolated SQLite DB seeded with the legacy `users` shape — three columns added, pre-existing rows preserved, UNIQUE(subscription_id) blocks duplicate non-NULL values, multiple NULLs allowed, `IF NOT EXISTS` makes the index creation idempotent.
- T4 Jinja templates rendered with `StrictUndefined` against four user states (no sub, active, past_due, canceled) × two contexts (real Stripe + simulator) — 16/16 pass with no missing context vars.
- Full Flask runtime startup NOT verified — Flask is not installed in any local Python on this machine and there is no project venv. Static checks above are the strongest signal available locally; first real-Stripe deploy is the integration-test gate.

## Open questions surfaced during execution

(none — implementation followed manifest. Open questions in the manifest itself are unchanged.)

