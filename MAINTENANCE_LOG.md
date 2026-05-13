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
