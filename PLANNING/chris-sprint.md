---
label: chris-sprint
project: window-quoting
phase: stabilize
purpose: "Chris's personal checklist — everything only Chris can do before production launch"
owner: Chris
created: 2026-05-12
status: active
---

# 🏁 Chris-Sprint — Your Production Readiness Checklist

Everything here requires your hands. No agent can do these for you.
Check items off as you go — I'll track progress from the side.

---

## 🔥 Phase 1: Accounts & Credentials (Do First — Unblocks H3+)

- [x] **Postmark account** — Live server created, API token saved, sender signature verified
  - _Needed by: Hotfix-3 T1 (email backend)_
  - _Free tier: 100 emails/month_

- [x] **Sentry account** — Signed up, DSN saved
  - _Needed by: Hotfix-4 T1 (error tracking)_
  - _Free tier: 5k errors/month_

- [x] **UptimeRobot account** — Signed up, no config needed until /health is deployed
  - _Needed by: Hotfix-4 T4 (ops runbook)_
  - _Free tier: 50 monitors_

- [x] **Backblaze B2 bucket** — Account created, bucket provisioned, keyID + applicationKey saved locally
  - _Needed by: Hotfix-5 T1 (backup destination)_
  - _Free tier: 10GB storage_

---

## 🌐 Phase 2: Domain & DNS (After H3 merges)

- [ ] **Register domain** (if not done) — point DNS at hosting provider
- [x] **DKIM record** — Added and verified in Postmark
- [x] **Return-Path record** — Added and verified in Postmark
- [x] **SPF record** — TXT record added (Postmark handles automatically but explicit record helps deliverability)
- [x] **DMARC record** — TXT record added on `_dmarc`
- [ ] **Point DNS at Render** — Add A/CNAME record for hosting (done during H6 deploy)

---

## 💳 Phase 3: Stripe Live Mode (After H3 + H4 merge)

- [ ] **Generate live API keys** — In Stripe Dashboard, create restricted keys scoped to this app's webhook endpoint (NOT Resumeforge keys)
- [ ] **Configure live webhook** — Add endpoint `https://<prod-domain>/webhook/stripe` in live mode. Save the `whsec_...` signing secret.
- [ ] **Link business bank account** — Confirm payout schedule in Stripe Dashboard
- [ ] **Test live checkout** — Buy Starter pack ($8.99) with your personal card after H6 deploy
- [ ] **Refund test charges** — Via Stripe Dashboard. Document transaction IDs in hotfix-6 notes.

---

## 🛡️ Phase 4: Legal & Compliance (Before DNS flip)

- [x] **Privacy Policy** — Drafted via Termly, saved to `legal/privacy-policy.html` ✅
- [x] **Terms of Service** — Drafted via Termly, saved to `legal/terms-of-service.html` ✅
- [ ] **Cookie Policy** — Chris creating later today
- [ ] **Inquisitor legal review** — Task queued in inquisitor/inbox. Audit both documents before production
- [ ] **Integrate into app** — Termly embed (primary) + local HTML fallback. H6 task
- [ ] **Review DEPLOYMENT.md** — Skim the pre-flight checklist so you know what to verify on launch day

_Termly annual plan: $144/year — covers all SaaS products_
_Embed approach: Termly Pro embed (auto-updating) with local HTML files as fallback_

---

## 🚀 Phase 5: Launch Day (After Inquisitor PASS on H6)

- [ ] **Set all production env vars** in hosting secrets store (T2 in H6 — full list in draft)
- [ ] **Confirm dev-mode flags are ABSENT**: `DEV_MODE`, `WTF_CSRF_DISABLED`, `RATELIMIT_DISABLED`, `MAIL_DISABLED` must NOT be set
- [ ] **Run pre-flight smoke** — DEPLOYMENT.md §2.1-2.9 all green
- [ ] **Flip DNS** (or toggle on PaaS)
- [ ] **30-minute watch** — Sentry, /health, gunicorn logs, Stripe Dashboard all open
- [ ] **First real sign-up** — Create a test account with a different email, verify email delivery
- [ ] **Tag v1.0.0** on master

---

## 📋 Quick Reference: What Depends on What

```
Postmark ─────┐
              ├─→ H3 (Email) ─→ H4 (Observability) ─→ H5 (Backups) ─→ H6 (Launch)
Sentry ───────┤
B2 Bucket ────┘
                                                        
Domain/DNS ──────────────────────────────────────→ H6 (Launch)
Stripe Live Keys ────────────────────────────────→ H6 (Launch)  
Legal Pages ─────────────────────────────────────→ H6 (Launch)
```

**Your critical path:** Postmark + Sentry + B2 → (wait for H3-H5 code) → Domain/DNS + Stripe + Legal → Launch

Get Phase 1 done first — everything else waits on code from H3-H5, but those accounts don't need code to set up.

---

_Last updated: 2026-05-12 by Jade_