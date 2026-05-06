---
sprint: 4
project: window-quoting
created: 2026-05-06
---

# Sprint 4 — Manual Walkthrough Notes

Bug log from Chris's manual walkthrough (T1 input). Format: severity, what broke, root cause, fix.

---

## BUG-001 — Signup crashes with IntegrityError on `users.total_recovered_value`

**Severity:** P0 (signup fully broken — blocks all new accounts)
**Found:** During first signup attempt (`astrophysicalchris@gmail.com`)

**Symptom:**
```
sqlalchemy.exc.IntegrityError: (sqlite3.IntegrityError) NOT NULL constraint failed: users.total_recovered_value
```
on `INSERT INTO users (...)` from the signup route. The INSERT column list omits `total_recovered_value`.

**Root cause:**
Orphaned schema. The `total_recovered_value` column was added to the `users` table in Sprint 1 (per `AUDIT_LOG.md` and `SPRINT_1_PORT.md`), but was later removed from the SQLAlchemy `User` model in `models.py` during a refactor. The DB column survived as `NUMERIC(12, 2) NOT NULL` with **no `DEFAULT` clause**, so any INSERT that doesn't explicitly set it (which the model can no longer do) violates the constraint.

**Fix:**
Dropped the orphan column from `sovereign.db`:
```sql
ALTER TABLE users DROP COLUMN total_recovered_value;
```
- SQLite 3.50.4 supports `DROP COLUMN` natively (3.35+).
- Pre-fix DB backed up to `sovereign.db.bak-pre-sprint4`.
- Code path needs no change — model already excludes the column.

**Verification:** Schema confirmed clean post-drop; signup retried below.

**Follow-up for Sprint 4 closeout:**
- Add a note to `DEPLOYMENT.md` (T3) about running schema parity checks against the model before deploys.
- Consider an Alembic / migration tooling story for Sprint 5 to prevent future drift.

---

## BUG-002 — Free credit count mismatch (copy vs code)

**Severity:** P1
**Found:** Signup screen
**Symptom:** Signup page copy says "5 free credits"; actual starting `credit_balance` is 10.
**Decision:** Keep 10, update copy to match (more headroom for first-impression moment).
**Fix scope:** Find the signup template / marketing copy and update string. Verify no other places reference "5 free credits".

---

## BUG-003 — Starter profiles should be removed; new-user landing is disorienting

**Severity:** P1 (UX, blocks first-quote success)
**Found:** Post-signup
**Symptom:** New users land on the quote page with no profile context (no business name, footer, invoice prefix). The "starter profiles" feature populates pre-built example profiles that aren't useful.
**Decision:**
- Remove starter profiles entirely on signup (new users start with zero profiles).
- Route new users to the account/profile page on first login instead of `/generate`. Force a minimum profile setup before they can quote.
- Tutorial / onboarding walkthrough deferred — possible Sprint 5+ enhancement, not in scope here.
**Fix scope:** Signup flow + post-login redirect logic. Possibly a `first_login` flag on `User`, or just check whether they have any profiles.

---

## BUG-004 — Quote form data lost when user navigates to buy credits mid-quote

**Severity:** P1 (real abandonment risk)
**Found:** Quote flow
**Symptom:** User filling out a quote runs out of credits, clicks "buy credits", returns to `/generate`, and finds the form blank. They have to re-enter everything.
**Fix:** Persist form values in `sessionStorage` (or server-side session) when navigating away from `/generate` mid-fill. Restore on return. Clear after successful quote generation.
**Out of scope here:** Persisting across browser sessions or across devices — sessionStorage / Flask session is enough.

---

## BUG-005 — Email verification gate not visibly enforced (observation)

**Severity:** P2 (observation; cannot fully test until `SUPPORT_EMAIL` configured in T4)
**Found:** Post-signup
**Symptom:** Couldn't confirm whether `/generate` actually blocks unverified accounts because the verification email path isn't operational yet.
**Action:** Re-test once T4 wires `SUPPORT_EMAIL` env var and verification email send.

---

## BUG-006 — Quote PDF line items all show "Custom Rate" instead of computed prices

**Severity:** P1 (visible on customer-facing PDF)
**Found:** Generated quote PDF
**Symptom:** Every line item ("Floor 1 - 4 Panes", "Floor 2 - 4 Panes", "Add-on: Screen Cleaning", etc.) shows "(Custom Rate)" in the Description column instead of the actual line total / unit price.
**Suspected cause:** PDF template (likely `generator.py` or a `templates/*.html` for PDF) is rendering the rate-source label rather than the computed price field.
**Fix scope:** Inspect quote PDF generator, switch to rendering the actual computed line total.

---

## BUG-007 — Quote ID is a random hash, Invoice ID is sequential — inconsistent and confusing

**Severity:** P2 (UX / reconciliation clarity)
**Found:** Generated quote → converted to invoice
**Symptom:** Quote PDFs are named with a random slug (`quote_a8bcbd.pdf`) but the converted invoice gets `INV-000004`. Two different identifier schemes for the same logical document.
**Decision:** Add a sequential display ID to quotes (e.g. `Q-000004`). Keep the random slug as the URL/file slug for un-guessability. On Q→I conversion, carry the sequential number forward (Q-000004 → INV-000004).
**Fix scope:** Add `next_quote_number` + `quote_prefix` (default `Q-`) to `User`, similar to existing invoice fields. Update quote PDF rendering and history list to show the sequential number prominently. Keep file slug for URL.
**Note:** Mirrors the existing invoice prefix customization feature.

---

# Programmatic stress + security probe (Claude, T2 input)

Probe script: `testing/stress_probe.py`. Run against the live dev server while Chris was away.

## BUG-008 — 🔥 P0 SECURITY: arbitrary authenticated file download via `/download/<filename>`

**Severity:** P0 (critical — pre-launch blocker)
**Found:** Programmatic probe (P1)

**Symptom:** Any authenticated user can download arbitrary files from `project_root` by name. The route only does `os.path.basename(filename)` (which prevents path traversal) but performs **no ownership check** and no allowlist on filenames.

**Verified live:**
```
GET /download/sovereign.db    -> 200  (86,016 bytes)   ← entire SQLite DB (all users, password hashes, Stripe IDs, transactions)
GET /download/app.py          -> 200  (69,810 bytes)   ← full source
GET /download/config.py       -> 200  (3,803  bytes)
GET /download/models.py       -> 200  (9,338  bytes)
GET /download/.env            -> 500  (no file present)
```

**Exploit:** Anyone who can register an account (free) can exfiltrate the entire user database, including all bcrypt password hashes, customer emails, and Stripe transaction history. They can also pull source code to look for further vulnerabilities.

**Root cause** (`app.py:931-935`):
```python
@app.route("/download/<filename>")
@login_required
def download(filename):
    safe_name = os.path.basename(filename)
    return send_file(os.path.join(project_root, safe_name), as_attachment=True)
```

**Fix scope:**
- Restrict downloads to PDF files **owned by the current user**.
- Easiest: store generated PDFs in `project_root/quotes/<user_id>/` and validate the path is inside the caller's own directory.
- Or: persist a `Download` row mapping random tokens → (user_id, filename) and serve via token, checking ownership.
- Or simpler still: derive filename strictly as `quote_<user_id>_<quote_id>.pdf` and validate the prefix at download time.
- Either way, also: move all generated PDFs out of `project_root` to a dedicated `output/` (or even `instance/`) directory so an accidentally-vulnerable handler can never reach `app.py`, `sovereign.db`, etc.

**Severity rationale for prelaunch:** the DB exfil is enough on its own — bcrypt hashes are slow but offline-crackable, especially against weak passwords. Customer email lists are also a privacy/compliance issue (CASL/CAN-SPAM exposure if leaked).

---

## Probe results — pass

| Probe | Result | Notes |
|---|---|---|
| **P5** Email-verification gate | ✅ PASS | unverified `/generate` → 403 `EMAIL_NOT_VERIFIED`; verified → 200 |
| **P6** Rate limit (10/hr) | ✅ PASS | 11th and 12th calls → 429 exactly as designed |
| **P8** Negative pane count | ✅ PASS | engine rejects → 400 with clear message |
| **P11** SQL injection on `/login` | ✅ PASS | all payloads return 200 (login form re-render with "Invalid"); SQLAlchemy parameterization holds |
| **P12** `/dev/grant-credits` gate | ✅ PASS | 404 in non-DEV_MODE |

---

## BUG-009 (observation) — Garbage / oversized inputs land in DB unsanitized

**Severity:** P3 (defense-in-depth, not exploitable today)
**Found:** Probe P9/P10

**Symptom:** Submitting a 10kB label and emoji+`<script>` payloads in customer fields returns 200 and produces a valid PDF. Inspecting code: `_sanitize_storage` length-caps customer fields server-side, but the raw Unicode is stored in the DB. PDF render strips non-latin via `encode("latin-1", "ignore")`. Templates use Jinja autoescape, so stored XSS is not reachable in HTML views today.

**Action:** Not a Sprint 4 fix; confirm the input-cap layer covers `label` (which is sanitized via `sanitize_label`) and re-test if the history page ever adds `|safe` or a custom HTML preview of customer fields.

---

## OBS-001 — Pre-filled override values trigger spurious "(Custom Rate)" labels (root cause of BUG-006)

`templates/index.html:203-205` writes `override_floor1/2/3` with the computed `base_rate × surcharge` whenever the active profile changes. Any non-empty value in `overrides` is treated by `engine.py:81` as a custom rate, so accepting defaults still produces "(Custom Rate)" on every line item.

**Fix options (rank order):**
1. **Don't pre-fill** override fields. Use `placeholder` to display the default rate but leave `value=""`. User types only when they want to override.
2. Pre-fill but compare submitted value to the default; only mark as overridden if it differs (post-submit comparison in `_parse_quote_form` or up-front in JS).
3. Add an explicit "use custom rate" toggle per row.

I'd go with option 1 — minimal code change, matches the natural mental model. Option 2 is fine but adds a comparison surface that can drift.

---

## OBS-002 — Credit-reserve refund is non-atomic with the Quote rollback

If `generate_document` raises and the refund `UPDATE` itself fails (DB locked, disk full, etc.), the user permanently loses a credit. Edge-case, low probability, but worth a comment / retry. Sprint 4 not required; flag for Sprint 5 reliability.

---

## OBS-003 — Session lifetime defaults to 31 days

No `PERMANENT_SESSION_LIFETIME` set in `config.py`, and `_session.permanent = True` is set on both register and login. Flask's default is 31 days. For a payments app this is on the long end. Suggest explicit `PERMANENT_SESSION_LIFETIME = timedelta(days=7)` or similar in `config.py`. Not a Sprint 4 must-fix; surface to Jade.

---

# Summary for Chris (when back)

**Bug count: 9 (1 P0, 5 P1, 1 P2, 2 P3/observations)**

| ID | Sev | Area | One-line |
|---|---|---|---|
| BUG-001 | P0 | DB schema | Orphan column blocked signup — **FIXED** during walkthrough |
| BUG-002 | P1 | Copy | "5 free credits" copy mismatches `STARTING_CREDITS = 10` |
| BUG-003 | P1 | Onboarding | Drop starter profiles; route new users to account page first |
| BUG-004 | P1 | UX | Quote form data lost on credit-purchase round trip |
| BUG-005 | P2 | Email | Verification gate untested live (waits on `SUPPORT_EMAIL`) |
| BUG-006 | P1 | PDF | All line items show "(Custom Rate)" — frontend pre-fill bug |
| BUG-007 | P2 | UX | Quote ID / Invoice ID schemes inconsistent — add `Q-NNNNNN` |
| **BUG-008** | **P0** | **Security** | **Arbitrary file download — anyone can grab `sovereign.db`** |
| BUG-009 | P3 | Hardening | Unicode/oversize inputs stored raw (not exploitable today) |
| OBS-002 | P3 | Reliability | Credit-refund non-atomic with rollback |
| OBS-003 | P3 | Hardening | 31-day session lifetime by default — consider 7d |

Single must-stop-the-presses item: **BUG-008**. Everything else fits comfortably into Sprint 4's bug-fix scope.
