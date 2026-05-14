# Panefree — Post-Launch Roadmap

Created: 2026-05-14
Status: Planning

---

## 🔴 Launch Day Checklist
These must happen the day we flip the DNS switch:

- [ ] **Stripe live key swap** — test → live keys in production config
- [ ] **HTTPS enforcement** — confirm infrastructure-level redirect
- [ ] **Production deployment** — push to live environment
- [ ] **Manual visual QA** — Chris walkthrough of live site
- [ ] **Monitoring/alerting setup** — uptime + error tracking
- [ ] **DB backup** — one-time operational action, confirm B2 bucket

---

## 🟡 Near-Term (Week 1-2 Post-Launch)

### Bugs & Test Debt
- [ ] **Account lifecycle test** — dedicated `test_account_lifecycle.py` for password reset + deletion flows
- [ ] **Fix `test_soft_cap_cta_points`** — seed a pricing profile before `/generate` so the test passes

### Infrastructure
- [ ] **Alembic migration tooling** — prevent future schema drift (like BUG-001)
- [ ] **Real B2 round-trip verification** — confirm backup restore works with production data
- [ ] **Backup tags in log catalog** — add structured tags for backup events

---

## 🟢 P4 — Post-Launch Enhancements

### Dynamic Add-Ons
- [ ] Render quote form add-ons dynamically from profile `add_on_rates` keys
- [ ] Add/remove rows in profile editor for custom add-ons
- [ ] Support arbitrary add-on names and prices (engine already handles this — UI + profile management only)

### Logo & Branding
- [ ] **Commission logo** — 4-pane window + sparkle, SVG + PNG deliverables (Fiverr)
- [ ] Integrate logo into navbar, PDF quotes, and invoice templates

### Legal & Compliance
- [ ] **Termly CMP integration** — proper consent management platform (currently a stub)
- [ ] **PP Section 5 ad language** — review and update ad/analytics cookie references

---

## 🔵 Future Considerations (No Timeline Yet)
- [ ] SEO / marketing landing page
- [ ] Stripe billing info update (currently pointing to ResumeForge)
- [ ] Cookie: `__cfduid` deprecation cleanup
- [ ] Browser cookie control stub → functional preference center

---

*Add items as they come up. Mark with your initials when you pick something up (e.g., `CJ` for Chris, `J` for Jade).*

---

## 🟣 Hotfix-7 Carry-Forward (added 2026-05-14 by Claude)

Items surfaced during Hotfix-6 / Hotfix-7 work that didn't fit the launch sprint but should land in the first post-launch cleanup.

### Code hygiene
- [ ] **`gunicorn.conf.py` docstring fix** — line 5 says "Start with 2 workers" but `workers = int(os.environ.get("GUNICORN_WORKERS", "1"))` defaults to 1. Comment + code disagree. (Inquisitor H7 R2 / H6 R5, non-blocking.)
- [ ] **Per-product Stripe statement descriptor** — add `payment_intent_data={"statement_descriptor_suffix": "PANEFREE"}` to `/checkout` route's `stripe.checkout.Session.create()` call (both payment and subscription branches). Pair with a shortened-descriptor `LIGHTMADE` in Stripe Settings so customers see `LIGHTMADE* PANEFREE` on card statements instead of just `LIGHTMADE SOFTWARE`. Required code change is ~3 lines, with a Stripe Dashboard config step.
- [ ] **Verify `LIGHTMADE SOFTWARE` actually appears on a real card statement** — descriptor changes can take up to 24h to propagate to card networks. Check 1-2 days after first real charge.

### Security / perf
- [ ] **Tailwind CDN → compiled CSS** (H7 T5, deferred per Inquisitor R1) — 15 templates still load `<script src="https://cdn.tailwindcss.com">`. Removing the CDN from `script-src` tightens CSP. Requires `tailwind.config.js`, `package.json`, build step on Render. Non-blocking but security/perf win.
- [ ] **App-level functional restore test** (H5 R4) — exercise the backup → restore flow end-to-end against a real B2 round-trip, not just the script-level test we have.

### Ops / monitoring
- [ ] **UptimeRobot monitors** — `https://panefreequoting.com/health` (5-min interval) + backup heartbeat URL. Can only be configured after DNS flip stabilizes (the production URL must resolve first). H7 T6.
- [ ] **`v1.0.0` tag confirmation** — applied during launch per LAUNCH.md §2.11. Confirm visible at github.com/lightmadeai/Panefree-Quoting/tags.
- [ ] **Monitoring agent** (Chris's pending project) — automated site-watch agent referenced in LAUNCH.md §6 "Future state."
- [ ] **Email-blast agent** (Chris's pending project) — incident notification agent for customer comms when there are customers to notify.

### Scaling trigger (revisit when signal arrives)
- [ ] **Redis + multi-worker gunicorn** — provision Upstash free tier (10K commands/day), set `REDIS_URL` env, update Flask-Limiter `storage_uri`, bump `GUNICORN_WORKERS=2`. **Trigger:** 20+ paying customers OR sustained Sentry p95 > 500ms, whichever first. Not before — single-worker is honestly fine for v1 traffic.

### Personal / operational hygiene (Chris)
- [ ] **Migrate secrets from `C:\Users\Thorn\secrets\panefree-prod.txt` to a password manager** (Bitwarden free tier recommended). Interim file is acceptable but not durable.
- [ ] **Move local working dir out of OneDrive sync path** — currently `C:\Users\Thorn\OneDrive\Desktop\Claude` is auto-synced to Microsoft. Files outside `\OneDrive\` are not synced. Project itself is already outside (`.openclaw\workspace\projects\`), but desktop secrets and notes can leak via OneDrive.
- [ ] **Buy `lightmadesoftware.com` umbrella domain** — Stripe business name now `Lightmade Software`. Lock in the matching domain (~$15/yr Cloudflare/Namecheap) before someone else does. No need to build on it yet — just own it.

### Webhook regression test status
- [x] **Stripe webhook regression test** (H7 T7) — `testing/test_stripe_webhook.py`, 6/6 passing, guards the H6 bug class (`StripeObject.get()` AttributeError). Done in hotfix-7 commit `cc8991c`.

---

## Status of original Launch Day Checklist (as of 2026-05-14)

Reconciling Jade's pre-H6 checklist against what's actually been completed:

- [x] Stripe live key swap — done in H6 T2 (rk_live + pk_live + whsec on Render)
- [x] HTTPS enforcement — done in H2 T4 (Talisman + Render TLS)
- [x] Production deployment — done in H6 (Render service live at panefree-quoting.onrender.com)
- [ ] Manual visual QA — pending; will execute in LAUNCH.md §2.10 smoke test
- [ ] Monitoring/alerting setup — Sentry done in H4 T1; UptimeRobot pending (see above)
- [ ] DB backup — B2 bucket configured, app key set, scripts in place; round-trip not yet exercised in prod (paired with H5 R2 above)