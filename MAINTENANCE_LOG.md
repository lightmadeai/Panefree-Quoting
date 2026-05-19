# Maintenance Log

Source of truth for "when did we last check X." Operator (Thorn for v1)
appends one entry per scheduled maintenance pass per the cadence in
`DEPLOYMENT.md` §10.3. Skipped entries become visible gaps.

Entry format:

```
## YYYY-MM-DD — <cadence> (<operator initials>)
- What was done (one bullet per category)
- Anomalies / surprises (if any)
- Follow-up items filed (if any)
```

Add new entries at the **top** so the most recent is always visible
without scrolling. Markdown is rendered by GitHub / Codeberg / etc. if
the repo is mirrored anywhere.

Cadences (per DEPLOYMENT.md §10.3):

- **Weekly** (Monday): Sentry skim, gunicorn 5xx skim, Stripe failed
  payments, signup/quote volume glance. ~15-30 min.
- **Monthly** (1st of month): `pip-audit --strict`, dep bumps,
  `stress_probe.py`, locust, redeploy, Sentry quota review. ~1-2 hours.
- **Quarterly** (Jan/Apr/Jul/Oct 1st): full regression + backup restore
  drill + Stripe tax/payout review + DEPLOYMENT.md re-read. ~2-4 hours.
- **Annually** (January): major-version upgrades, TLS verify, full
  security review, backup archival. ~1 day.

---

<!--
Entries appear below this comment. Top = most recent. First real entry
will be the first Monday after launch.
-->

## 2026-05-19 — Incident root cause (Hotfix 8 / Bug 2) (TM)

- **What broke:** Pricing-profile switching did not auto-populate rate fields on `index.html` (quote page). Profile dropdown was responsive, but the JavaScript that injected the profile data (`window.__profilesData`) and defined `window.__populateRates` never executed. Reported by Chris 2026-05-17; failed on all devices.
- **Root cause:** CSP `script-src` directive in `app.py` was `'self' cdn.tailwindcss.com js.stripe.com` — no `'unsafe-inline'` and no nonce/hash whitelisting. Two inline `<script>` blocks in `index.html` (one writing `window.__profilesData = JSON.parse(...)` at ~line 211, one defining `populateRates()` at ~line 292) were silently blocked by the browser at parse time. The form rendered, the dropdown change-handler bound, but the bridge between them never loaded. Diagnosed via DevTools console showing "Executing inline script violates the following Content Security Policy directive" errors, and `window.__profilesData === undefined`, `window.__populateRates === undefined`.
- **Fix shipped:** Commit `266af25` (2026-05-19) added `'unsafe-inline'` to CSP `script-src`. Quick-fix path per Hotfix 8 sprint plan. Verified live at panefreequoting.com.
- **Anomalies / surprises:** The `setPlaceholder` design that originally raised suspicion (BUG-006 / Sprint 4 change) turned out to be intentional and correct — the bug was upstream in CSP, not in the populateRates internals.
- **Follow-up items filed:** Proper fix (externalize inline scripts to `static/js/`, then tighten CSP back to remove `'unsafe-inline'`) deferred to Hotfix 9 / Bug 3 (Tailwind CDN migration sprint) — T3 of Hotfix 9 already covers CSP tightening.
