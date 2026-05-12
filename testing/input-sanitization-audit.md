# Input Sanitization Audit — BUG-009 follow-up

**Sprint:** Hotfix-1 (Stabilize Phase) — T4
**Date:** 2026-05-09 03:06 UTC
**Driver:** `testing/input_sanitization_audit.py`
**Overall verdict:** **PASS ✅**

## Pre-hotfix gaps (identified during audit)

Five free-text entry points were `.strip()`-only with no length cap, leaving DB-bloat / DOS surface:

| Route | Field | Pre-fix | Post-fix |
|---|---|---|---|
| `/account` | `business_name` | unbounded | `BUSINESS_NAME_MAX = 200` |
| `/account` | `phone_number` | unbounded | `CUSTOMER_PHONE_MAX = 30` |
| `/contact` | `company_name` | unbounded | `CONTACT_COMPANY_MAX = 200` |
| `/contact` | `current_volume` | unbounded | `CONTACT_VOLUME_MAX = 200` |
| `/contact` | `expected_growth` | unbounded | `CONTACT_GROWTH_MAX = 2000` |
| `/contact` | `email` | unbounded | `CONTACT_EMAIL_MAX = 254` (RFC 5321) |
| `/profiles/new` | `name` (HTML) | unbounded | `PROFILE_NAME_MAX = 80` |
| `/api/profiles/create` | `name` (JSON) | unbounded | `PROFILE_NAME_MAX = 80` |

All gaps now route through `_sanitize_storage()` (trim → whitespace-collapse → cap), matching the existing Sprint 4 customer-field pattern.

## Cap test results (10KB payload at every cap)

| Route | Field | Cap | Stored | Behavior | Verdict |
|---|---|---:|---:|---|---|
| `POST /account` | `business_name` | 200 | 200 | truncated silently | PASS |
| `POST /account` | `phone_number` | 30 | 30 | truncated silently | PASS |
| `POST /account` | `quote_footer_text` | 200 | 200 | truncated silently | PASS |
| `POST /account` | `invoice_footer_text` | 200 | 200 | truncated silently | PASS |
| `POST /account` | `invoice_prefix (rejected, prior state preserved)` | 11 | 4 | form-level reject + flash; prior 'INV-' kept | PASS |
| `POST /contact` | `company_name` | 200 | 200 | truncated silently | PASS |
| `POST /contact` | `current_volume` | 200 | 200 | truncated silently | PASS |
| `POST /contact` | `expected_growth` | 2000 | 2000 | truncated silently | PASS |
| `POST /contact` | `email` | 254 | 254 | truncated silently | PASS |
| `POST /profiles/new` | `name (HTML)` | 80 | 80 | truncated silently | PASS |
| `POST /api/profiles/create` | `name (JSON)` | 80 | 80 | truncated silently | PASS |
| `POST /generate` | `label` | 80 | 80 | truncated silently (existing) | PASS |
| `POST /generate` | `customer_name` | 100 | 100 | truncated silently (existing) | PASS |
| `POST /generate` | `customer_address` | 200 | 200 | truncated silently (existing) | PASS |
| `POST /generate` | `customer_email` | 254 | 254 | truncated silently (existing) | PASS |
| `POST /generate` | `customer_phone` | 30 | 30 | truncated silently (existing) | PASS |

## sanitize_label coverage (T4 acceptance question)

`sanitize_label` itself is only used on `Quote.label`. The broader `_sanitize_storage()` (which `sanitize_label` is a thin wrapper around) now covers every customer-facing free-text field after this hotfix. The pattern is consistent: trim, collapse whitespace, cap.

## Out of scope / deferred

- **Login/register password length.** Werkzeug's `generate_password_hash` accepts arbitrary input; a 1MB password could spike CPU. Not in T4 scope; flag for a future hotfix as a low-priority DOS hardening item.
- **Login/register email.** DB has `UNIQUE` on `users.email` with no length cap; oversized email would land but with the uniqueness gate already absorbing duplicates. Same scope note as password — defer.

## Conclusion
All audited entry points enforce server-side length caps. BUG-009 follow-up resolved.

**Backlog status:** P3 — BUG-009 follow-up → can be checked off in `PLANNING/backlog.md`.
