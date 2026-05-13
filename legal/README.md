# Legal Documents

Source-of-truth legal documents for Panefree Quoting.

## Files
- `privacy-policy.html` — Privacy Policy (Termly-generated) ✅
- `terms-of-service.html` — Terms of Service (Termly-generated) ✅
- `cookie-policy.html` — Cookie Policy (Termly-generated) ✅

## Status
- [x] Privacy Policy drafted via Termly
- [x] Terms of Service drafted via Termly
- [x] Cookie Policy drafted via Termly
- [x] Files saved to legal/ directory (HTML format)
- [x] Cookie Policy converted from .txt to .html (2026-05-13)
- [ ] Inquisitor legal review (H01-H03 blockers)
- [ ] Integrated into app routes (`/legal/privacy`, `/legal/terms`, `/legal/cookies`)

## Notes
- Termly annual plan: $144/year — covers unlimited documents across all SaaS products
- All documents are full HTML with embedded CSS — render-ready for the website
- Key legal details configured:
  - 18+ only (no under-18 targeting)
  - GDPR + CCPA + PIPEDA coverage
  - Payment via Stripe (card data never touches our servers)
  - Essential cookies only (session + CSRF)
  - Dispute resolution: Informal negotiation (30 days) → Arbitration (Oregon, Linn County)
  - Liability limited to amount paid by user
  - 1-year statute of limitations
  - Contact methods: email + contact form (satisfies FL/NE/TX)
  - Third-party processors: Stripe, Postmark, Sentry, Backblaze B2, Cloudflare
- All documents need Inquisitor audit before production deployment
- Post-launch P4: swap static HTML for Termly JS embed + cookie consent banner