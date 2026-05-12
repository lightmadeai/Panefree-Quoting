import os
from datetime import timedelta

project_root = os.path.dirname(os.path.abspath(__file__))

SECRET_KEY = os.environ.get("SRE_SECRET_KEY", "sre_secret_key_change_me_in_prod")
DATABASE_PATH = os.path.join(project_root, "sovereign.db")
SQLALCHEMY_DATABASE_URI = f"sqlite:///{DATABASE_PATH}"
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Session timeout (Hotfix-1 T2). Flask reads this via app.config.from_object()
# and applies it to any session marked .permanent = True (set in /register
# and /login). Hotfix-1 raised the previous 24h value to 7 days so users
# don't get bounced mid-week. Tunable here only — do not redeclare in app.py.
PERMANENT_SESSION_LIFETIME = timedelta(days=7)

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
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:5001")

# Dev-only: when DEV_MODE=1 AND Stripe is NOT configured, the top-up page
# exposes a simulator that grants credits without Stripe. Both conditions
# must hold — the simulator route 404s if Stripe keys are present, so a
# real deployment can't accidentally expose it by forgetting to flip the flag.
DEV_MODE = os.environ.get("DEV_MODE", "").lower() in ("1", "true", "yes")

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
SUPPORT_EMAIL = os.environ.get("SUPPORT_EMAIL", "support@windowquoting.com")

# Per-account rate limit. Free users (and past_due subscribers, who fall
# through to the credit path) are capped at this many /generate calls per
# rolling 60-minute window. Active subscribers are exempt — they bypass
# the credit reserve already and the rate limit follows the same gate.
# Tunable via env so we can dial it post-launch without a redeploy.
RATE_LIMIT_QUOTES_PER_HOUR = int(os.environ.get("RATE_LIMIT_QUOTES_PER_HOUR", "10"))

# Seed file — used only to populate a new user's default profiles.
# Runtime reads come from the pricing_profiles table, never this file.
SEED_PRICE_SHEET_PATH = os.path.join(project_root, "price_sheet.json")
