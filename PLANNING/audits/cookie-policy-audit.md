---
label: cookie-policy-audit
project: window-quoting
auditor: inquisitor
date: 2026-05-13
verdict: CONDITIONAL PASS
blocking_count: 2
nonblocking_count: 5
---

# Cookie Policy Legal Audit (H03 Blocker Resolution)

**Auditor:** The Inquisitor
**Date:** 2026-05-13
**File:** `projects/window-quoting/legal/cookie-policy.html`
**Source:** Termly default template with Panefree Quoting business details
**Verdict:** ⚠️ CONDITIONAL PASS — 2 blocking findings must be resolved before production, 5 non-blocking remarks.

---

## 1. H03 Resolution Check

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Cookie Policy document exists | ✅ PASS | `legal/cookie-policy.html` present, 9,796 bytes, valid HTML |
| Covers cookie categories | ✅ PASS | Explains first-party vs third-party, essential vs non-essential |
| User control mechanisms | ✅ PASS | Cookie Preference Center, browser controls, DNT section |
| Contact information | ✅ PASS | support@panefreequoting.com + postal address (1448 Geary Cir SE, Albany, OR 97322) |
| Last updated date | ✅ PASS | "Last updated May 13, 2026" |

**H03 baseline: The Cookie Policy EXISTS and covers the required disclosures.** However, two blocking issues prevent full clearance.

---

## 2. Blocking Findings

### B1: Privacy Policy "Cookie Notice" Links Point to Wrong Page

**Severity:** 🔴 BLOCKING

The Privacy Policy (section 5, "DO WE USE COOKIES AND OTHER TRACKING TECHNOLOGIES?") references the Cookie Policy twice as "Cookie Notice." Both links resolve to:

```
https://panefreequoting.com/legal/privacy
```

This is the PP's own URL, NOT the separate Cookie Policy page. The PP is self-referencing instead of linking to `/legal/cookies` (or `/legal/cookie-policy`).

**Impact:** Users reading the PP's cookie section and clicking "Cookie Notice" land back on the PP, never reaching the actual Cookie Policy. This defeats the purpose of having a separate Cookie Policy.

**Fix:** In `privacy-policy.html`, update both "Cookie Notice" links from:
- `https://panefreequoting.com/legal/privacy` → `https://panefreequoting.com/legal/cookies` (or the actual route)

Note: Termly templates embed these links as `bdt` question blocks — the `href` may need to be updated in the Termly dashboard rather than manually in the HTML, since Termly regenerates from its platform. If manual edit, search for both occurrences of `https://panefreequoting.com/legal/privacy` that appear immediately after the text "Cookie Notice".

### B2: Cookie Policy Mentions "Advertising" and "Targeted Advertising" — Contradicts "Essential Cookies Only" Design

**Severity:** 🔴 BLOCKING

The Cookie Policy contains multiple references to advertising and targeted advertising:
- "Third parties serve cookies through our Website for **advertising**, analytics, and other purposes."
- "Do you serve targeted advertising?" — Entire section dedicated to targeted advertising
- "Third parties may serve cookies on your computer... to serve advertising through our Website"
- Links to Digital Advertising Alliance opt-out pages (3 links)
- "Cookie Preference Center" — references a preference center that allows selecting which categories to accept/reject

The Privacy Policy section 5 also states: "We also permit third parties and service providers to use online tracking technologies on our Services for **analytics and advertising**, including to help manage and display advertisements, to tailor advertisements to your interests."

**This directly contradicts**:
- `README.md`: "Essential cookies only (session + CSRF)"
- The app's actual design: Flask-Login session cookie + CSRF token — no analytics, no advertising cookies

**Impact:** Legal exposure. Claiming to serve advertising cookies when you don't is misleading. Claiming essential-only when the policy says advertising is a contradiction. Either representation creates compliance risk under GDPR (lawful basis), CCPA (disclosure accuracy), and PIPEDA.

**Fix (two options):**
1. **Preferred (matches actual design):** Edit the Cookie Policy to remove all references to advertising, analytics cookies, and the "Cookie Preference Center." State clearly that Panefree Quoting uses **essential cookies only** (session + CSRF) and does not use advertising or analytics cookies. Remove the DAA opt-out links. Remove the "Do you serve targeted advertising?" section.
2. **Alternative:** If advertising cookies are planned for post-launch, add a clear disclaimer: "As of launch, Panefree Quoting uses essential cookies only. Advertising and analytics cookies may be introduced in future updates, at which point this policy will be updated and a consent banner will be provided."

---

## 3. Non-Blocking Remarks

### R1: Cookie Preference Center Doesn't Exist Yet

The Cookie Policy references a "Cookie Preference Center" multiple times, but no such UI exists in the app. The README notes this is deferred to P4 (Termly JS embed + consent banner).

**Assessment:** Acceptable for launch IF the Cookie Policy is updated to reflect essential-only cookies (which removes the need for a preference center). If advertising/analytics sections remain, the preference center must exist before production. Blocking finding B2 resolves this.

### R2: Flash Cookies / LSO Section Is Outdated

The Cookie Policy includes a section on "Flash Cookies or Local Shared Objects" with links to macromedia.com Flash Player settings panels. Flash was deprecated in 2020 and is no longer supported by any major browser. This section is technically irrelevant.

**Assessment:** Low risk. Not harmful to include (it's a Termly default), but looks outdated. Consider removing in a future update. Not blocking.

### R3: Web Beacons / Tracking Pixels Section

The Cookie Policy mentions "web beacons (sometimes called tracking pixels or clear gifs)" and says "We may use other, similar technologies from time to time." Panefree Quoting currently does not use tracking pixels.

**Assessment:** Consistent with the Termly template. Acceptable as a forward-looking disclosure, but combined with B2, creates an impression of more tracking than actually occurs. If B2 is fixed to "essential only," this section should be toned down accordingly.

### R4: No Cookie-Specific Table of Cookies

Best practice for Cookie Policies under GDPR/CCPA is to include a specific table listing every cookie name, purpose, duration, and category. The current policy is generic — it explains cookie types conceptually but doesn't enumerate Panefree Quoting's actual cookies.

**Assessment:** For a v1 launch with essential-only cookies, this is acceptable. The two cookies (session + CSRF) are standard and don't require granular disclosure. Add a specific table in P4 when the consent banner is implemented.

### R5: Cross-Document Navigation

The Cookie Policy does not link back to the Privacy Policy or Terms of Service. The PP links to "Cookie Notice" (wrongly, per B1). The ToS was not checked for cookie-related cross-references.

**Assessment:** Add a brief "See also: [Privacy Policy](/legal/privacy) | [Terms of Service](/legal/terms)" footer to the Cookie Policy. Ensure ToS cross-references the Cookie Policy correctly.

---

## 4. Consistency Check

| Check | Status | Notes |
|-------|--------|-------|
| Business name (Panefree Quoting) | ✅ Consistent | All three documents match |
| Email (support@panefreequoting.com) | ✅ Consistent | All three documents match |
| Address (1448 Geary Cir SE, Albany, OR 97322) | ✅ Consistent | All three documents match |
| Website URL (panefreequoting.com) | ✅ Consistent | All three documents match |
| Third-party processor references | ⚠️ Partial | Cookie Policy doesn't enumerate Stripe/Postmark/Sentry/Backblaze/Cloudflare as cookie sources (acceptable — they set their own cookies on their own domains) |
| "Essential cookies only" design | ❌ CONTRADICTS | Cookie Policy and PP both mention advertising/analytics cookies that don't exist (B2) |
| PP → Cookie Policy link | ❌ WRONG | Both "Cookie Notice" links point to PP itself (B1) |

---

## 5. Verdict

| Category | Count |
|----------|-------|
| 🔴 Blocking | 2 |
| 🟡 Non-Blocking | 5 |
| ✅ H03 Baseline | Resolved — document exists and covers required disclosures |

**Verdict: ⚠️ CONDITIONAL PASS**

The Cookie Policy document resolves the H03 blocker (document existence and coverage). However, two blocking issues must be fixed before production:

1. **B1:** Fix PP's "Cookie Notice" links to point to `/legal/cookies` instead of `/legal/privacy`
2. **B2:** Resolve the "essential cookies only" vs "advertising cookies" contradiction — either edit the Cookie Policy and PP to state essential-only, or add a disclaimer about future advertising cookies

Once B1 and B2 are resolved, **all three legal blockers (H01, H02, H03) are cleared for H6 DNS flip.**