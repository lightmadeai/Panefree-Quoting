# Release Notes — Panefree Quotes v1.0

**Release date:** 2026-05-06 (code-side ready; production cutover in Sprint 5)
**Audience:** customers, sales conversations, public release page

This is the first public release. The four sprints in the planning pipeline (1 → 2 → 3 → 4) brought the product from a single-tenant quote tool to a multi-user SaaS with payments, abuse prevention, and the security and operational hardening required for paying customers. The headline features below are written for an external reader; the engineering detail lives in [CHANGELOG.md](CHANGELOG.md).

---

## Headline features

### Pricing that scales with you
Four tiers, transparent per-quote pricing, no surprise overage fees:

| Tier | Price | Credits | Per quote | Best for |
|---|---|---|---|---|
| Starter | $8.99 | 10 | $0.90 | Trial / one-off jobs |
| Pro | $39 | 50 | $0.78 (13% off Starter) | Active sole operators |
| Studio | $69 | 100 | $0.69 (23% off Starter) | Small crew |
| Annual Unlimited | $179/yr | Unlimited quotes | ~$0.18 (97%+ off Starter) | High-volume operators |

Credit packs are one-time purchases that never expire. The annual tier is a recurring subscription billed yearly through Stripe. Switching between them is straightforward — your remaining credits are preserved if you start an annual subscription, and resume if you let it lapse.

### Annual Unlimited subscription with cancel-at-period-end
Subscribe through Stripe, manage everything (payment method, cancellation, invoice history) through Stripe's hosted Billing Portal. If you cancel mid-period, your access continues through the end of your billing date — the UI shows "Cancels on YYYY-MM-DD" so you always know where you stand. Re-subscribing at any time picks up where you left off.

### Email verification + free tier
- **10 free quote credits** at signup so you can evaluate the product before paying.
- **Email verification required** before generating your first quote — protects your account and prevents abuse.
- **One-time profile setup** at signup gets you to your first real quote in minutes, with your own pricing rather than placeholder defaults.

### Built-in abuse prevention
- **10 quotes per hour rate limit** for free users — generous for evaluation, prevents script abuse.
- **Active subscribers are exempt** — unlimited means unlimited.
- **Login lockout** after 5 wrong passwords (15-minute cooldown) protects against credential stuffing.
- **24-hour session timeout** so an unattended browser doesn't leave your account exposed.

### Quotes and invoices that look professional
- **Sequential `Q-NNNNNN` quote numbers** — your customers see "Quote Q-000004", not a random hash. Easy to reference in conversations and reconcile against your records.
- **Sequential `INV-NNNNNN` invoice numbers** — gap-free and tax/legally compliant. Issuing an invoice claims the next number atomically; re-printing the same invoice always shows the same number.
- **Customer "Bill To" block** with name, address, email, phone — looks like an invoice from any professional service business.
- **Customizable per-account branding**: business name, phone number, quote/invoice footers (with `{{phone}}` / `{{date}}` placeholders), and invoice prefix (default `INV-`, customizable per-account).
- **PDFs render with proper line items, real prices, and totals** — no spurious "(Custom Rate)" tags on default-priced lines (fixed in v1.0).

### Multiple pricing profiles
Save unlimited pricing profiles per account — Residential Standard, Commercial High-Rise, Storefront Maintenance, whatever shapes your business. Switch profiles per quote. Set one as default. Update rates without ever touching past quotes (each quote stores its pricing snapshot).

### Tax and callout fee overrides
Per-quote overrides for tax rate (e.g., crossing a county line) and callout fee (after-hours, large jobs). Stored on the quote so re-renders match the original.

### 50-quote history with one-click re-render
Every quote you generate is preserved. Re-render any past quote as a quote PDF or convert it to an invoice — both are free, no credits charged. The pricing data is snapshotted at generate-time, so re-rendering an old quote always produces the original PDF even if your rates have changed since.

### Custom-plan intake for high-volume customers
At very high quote volumes (1,000+/year on the annual tier), the app surfaces a heads-up at 80% and a contact CTA at 100% — not a paywall, just a polite "let's talk about a custom plan if your volume keeps growing." The intake form captures company, current volume, expected growth, and a reply-to address so we can have a real conversation rather than auto-bill you into a higher tier.

### Security model
- **Per-user PDF storage**: every PDF is stored in a per-user bucket, and the download route only ever resolves files inside the caller's own bucket. Even if someone learned another user's PDF filename, they couldn't fetch it. This was hardened in v1.0 (Sprint 4 BUG-008 fix) before any paying customer touches the system.
- **Stripe webhook signature verification** ensures payment events are genuinely from Stripe.
- **Idempotent payment handling** — Stripe's webhook retries can't duplicate-credit a customer; UNIQUE constraints on Stripe IDs catch replays.
- **Concurrency-safe credit reserve** — racing requests can never spend the same credit twice.

---

## What's NOT in v1.0 (planned for Sprint 5)

- Live Stripe key swap and real-card validation — v1.0 ships with test-mode Stripe; live cutover is Sprint 5.
- HTTPS enforcement at the infrastructure level.
- Production monitoring / alerting (uptime, payment failure rate).
- A sent verification email — currently the verify link is logged server-side; Sprint 5 wires it through a real email backend.

These are deployment-side items; the app code is ready for them and they don't change the customer-facing feature set.

---

## Support

Questions, custom plans, or trouble signing in: see the contact link at the bottom of any page (configured per-deployment via `SUPPORT_EMAIL`).
