import os
from datetime import timedelta

project_root = os.path.dirname(os.path.abspath(__file__))

SECRET_KEY = os.environ.get("SRE_SECRET_KEY", "sre_secret_key_change_me_in_prod")
DATABASE_PATH = os.environ.get("DATABASE_PATH", os.path.join(project_root, "sovereign.db"))
SQLALCHEMY_DATABASE_URI = f"sqlite:///{DATABASE_PATH}"
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Session timeout (Hotfix-1 T2). Flask reads this via app.config.from_object()
# and applies it to any session marked .permanent = True (set in /register
# and /login). Hotfix-1 raised the previous 24h value to 7 days so users
# don't get bounced mid-week. Tunable here only — do not redeclare in app.py.
PERMANENT_SESSION_LIFETIME = timedelta(days=7)

# Session cookie flags (Hotfix-2 T1). HTTPONLY blocks JS access to the
# session cookie (XSS mitigation, defense in depth — autoescape already
# blocks injection at the Jinja layer). SAMESITE=Lax blocks cross-site
# POSTs from carrying the cookie, which is the cheap-and-effective CSRF
# brake (Hotfix-2 T2 adds proper CSRF tokens on top). SECURE means the
# cookie is only sent over HTTPS — required in prod, but breaks local dev
# over plain http://127.0.0.1, so it's gated on DEV_MODE.
#
# IMPORTANT: do NOT set DEV_MODE=1 in production. The simulator route is
# also gated on DEV_MODE, and turning it on would also disable the cookie
# SECURE flag — both are "fail-loud-if-misconfigured" gates that share
# the same kill switch.
_DEV_MODE = os.environ.get("DEV_MODE", "").lower() in ("1", "true", "yes")
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not _DEV_MODE

# Generated PDFs live here, segregated by user ID. The download route
# (BUG-008 fix, Sprint 4) only ever reads from <OUTPUT_DIR>/<current_user.id>/,
# so a filename leaked to user A is unreachable as user B and the directory
# never contains source code or DB files.
OUTPUT_DIR = os.path.join(project_root, "output")

# Free-tier allotment granted at registration. Existing users below this
# floor are bumped up at app boot via _ensure_starting_credit_floor() — a
# one-time courtesy when the threshold is raised in a future sprint.
STARTING_CREDITS = 10

# --- Stripe (Sprint 2) ---
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
APP_BASE_URL = os.environ.get("APP_BASE_URL", "https://panefreequoting.com")

# Dev-only: when DEV_MODE=1 AND Stripe is NOT configured, the top-up page
# exposes a simulator that grants credits without Stripe. Both conditions
# must hold — the simulator route 404s if Stripe keys are present, so a
# real deployment can't accidentally expose it by forgetting to flip the flag.
# Also disables SESSION_COOKIE_SECURE so local http://127.0.0.1 dev works
# (see the SESSION_COOKIE_* block above). Mirror of _DEV_MODE for the
# public-facing config.DEV_MODE name used by routes.
DEV_MODE = _DEV_MODE

# Credit packs — inline pricing, no pre-created Stripe Prices needed.
# Per-quote economics (intentional ladder; high-volume users converge on
# annual once their per-quote spend would exceed it):
#   Starter:  $8.99 / 10   = $0.90 per quote (—)
#   Pro:      $39   / 50   = $0.78 per quote (13% off Starter)
#   Studio:   $69   / 100  = $0.69 per quote (23% off Starter)
#   Annual:   $179 / 1000-soft-cap = ~$0.18 per quote (97%+ off Starter)
# Soft-cap is informational, not enforced — the annual tier remains
# advertised as "unlimited" while flagging the high-volume CTA path.
CREDIT_PACKS = {
    "starter": {"name": "Starter",  "credits": 10,   "price_cents": 899},
    "pro":     {"name": "Pro",      "credits": 50,   "price_cents": 3900},
    "studio":  {"name": "Studio",   "credits": 100,  "price_cents": 6900},
}

# Annual unlimited subscription tier. Distinct shape from CREDIT_PACKS — no
# `credits` field, has an `interval`. Intentionally a separate dict so a
# typo in the request body can never trip the credit-pack lookup into
# vending an annual subscription, or vice versa.
ANNUAL_SUBSCRIPTION = {
    "name": "Annual Unlimited",
    "price_cents": 17900,
    "interval": "year",
}

# Soft-cap notification threshold for annual subscribers — informational
# only, does NOT throttle generation. At-or-above the threshold the
# /generate response carries a CTA pointing high-volume users toward a
# custom-plan conversation rather than throttling them. Configurable via
# env so the threshold can be tuned post-launch without a redeploy.
SOFT_CAP_THRESHOLD = int(os.environ.get("SOFT_CAP_THRESHOLD", "1000"))

# Contact address surfaced in the soft-cap CTA. Configurable so different
# environments (test/staging/prod) can route the conversation differently.
# Default matches the production domain (Hotfix-4 T0 — branding pass after
# panefreequoting.com was locked in 2026-05-12).
SUPPORT_EMAIL = os.environ.get("SUPPORT_EMAIL", "support@panefreequoting.com")

# ---------------------------------------------------------------------------
# Hotfix-3 — Email backend (Postmark)
# ---------------------------------------------------------------------------
# mailer.py reads these at every send call (not cached) so individual tests
# can monkeypatch via os.environ. Production sets them once via the hosting
# provider's secrets store.
#
# POSTMARK_SERVER_TOKEN — from the "Server Tokens" tab of the Postmark
# server (NOT the account API token). Scoped to one server so it can be
# rotated independently.
#
# EMAIL_FROM — must match a Postmark-verified sender signature OR a
# verified sender domain. Postmark rejects sends from unverified addresses.
#
# EMAIL_FROM_NAME — friendly display name. Postmark composes the final
# From header as "Panefree Quoting <support@panefreequoting.com>" when both
# are set.
#
# ADMIN_EMAIL — destination for ops alerts (refund failures, contact
# submissions, backup failures from Hotfix-5). Defaults to SUPPORT_EMAIL
# so single-operator setups don't need to set both.
POSTMARK_SERVER_TOKEN = os.environ.get("POSTMARK_SERVER_TOKEN")
# Hotfix-4 T0: defaults aligned with production domain panefreequoting.com
# and the user-visible "Panefree Quoting" brand name (matches templates'
# nav + page titles). Internal codename "window-quoting" stays unchanged
# in folder paths, log tags, and the Stripe metadata fields.
EMAIL_FROM = os.environ.get("EMAIL_FROM", "support@panefreequoting.com")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "Panefree Quoting")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", SUPPORT_EMAIL)

# MAIL_DISABLED — test-only kill switch, same pattern as WTF_CSRF_DISABLED
# and RATELIMIT_DISABLED. When set, mailer.send_email() becomes a no-op
# that logs `[MAIL-DISABLED]` and returns True. Production MUST NOT set
# this — app.py emits a loud warning at boot when it's set, and the
# pre-flight check (DEPLOYMENT.md §2.1) catches it via env grep.
MAIL_DISABLED = os.environ.get("MAIL_DISABLED", "").lower() in ("1", "true", "yes")

# Per-account rate limit. Free users (and past_due subscribers, who fall
# through to the credit path) are capped at this many /generate calls per
# rolling 60-minute window. Active subscribers are exempt — they bypass
# the credit reserve already and the rate limit follows the same gate.
# Tunable via env so we can dial it post-launch without a redeploy.
RATE_LIMIT_QUOTES_PER_HOUR = int(os.environ.get("RATE_LIMIT_QUOTES_PER_HOUR", "10"))

# Seed file — used only to populate a new user's default profiles.
# Runtime reads come from the pricing_profiles table, never this file.
SEED_PRICE_SHEET_PATH = os.path.join(project_root, "price_sheet.json")
