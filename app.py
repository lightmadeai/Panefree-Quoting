import os
import re
import sys
import json
import shutil
import threading
import time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)


# ---------------------------------------------------------------------------
# Hotfix-4 T1: Sentry SDK initialization.
#
# Init MUST happen before `Flask(__name__)` so the Flask integration's
# patches are in place when routes register. SENTRY_DSN unset = full
# no-op (the SDK detects missing DSN and silently does nothing) — keeps
# dev/test runs from polluting the dashboard.
#
# Two custom `before_send` behaviors (Inquisitor C1 + general PII hygiene):
#   1. PII scrub: replace any request-context field named password /
#      csrf_token / customer_email / customer_phone / customer_address
#      with "[scrubbed]" before transmit. Defense in depth — Sentry's
#      default scrubbers already catch `password`, but the customer_*
#      fields are app-specific and need explicit handling.
#   2. 500-events/hour rate cap: in-process token bucket per worker.
#      If a Day-1 bug triggers a loop, the dashboard stays useful
#      instead of being flooded out of the free-tier quota.
#
# `release` is set to the git SHA exposed via /health (T2). Falls back
# to "dev" when the VERSION file doesn't exist (i.e. local runs).
# ---------------------------------------------------------------------------
try:
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration
except ImportError:  # pragma: no cover — sentry-sdk is in requirements.txt
    sentry_sdk = None
    FlaskIntegration = None

_SENTRY_PII_FIELDS = frozenset({
    "password", "csrf_token",
    "customer_email", "customer_phone", "customer_address",
})

# In-process rate limiter for Sentry events. Token bucket: refill 500
# events/hour = 1 event every 7.2s. Per-worker (multi-worker prod will
# get a slightly higher effective cap, which is acceptable — the goal
# is "dashboard usable under error storm," not exact quota math).
_SENTRY_RATE_CAP_PER_HOUR = 500
_SENTRY_TOKEN_REFILL_INTERVAL_S = 3600.0 / _SENTRY_RATE_CAP_PER_HOUR
_sentry_rate_state = {
    "tokens": float(_SENTRY_RATE_CAP_PER_HOUR),  # start full
    "last_refill": time.monotonic(),
}
_sentry_rate_lock = threading.Lock()
_sentry_drops_since_log = 0


def _sentry_before_send(event, hint):
    """
    Runs on every event Sentry is about to ship. Two passes:

      1. Scrub PII from request context. Sentry's default scrubbers catch
         password / authorization / cookies; we extend to the app-specific
         customer_* fields.
      2. Token-bucket rate limit per worker. If we're over 500/hr, drop
         the event and (periodically) log how many we've dropped.
    """
    # ---- PII scrub ----
    req = event.get("request") or {}
    for bucket in ("data", "query_string", "headers", "cookies"):
        val = req.get(bucket)
        if isinstance(val, dict):
            for k in list(val.keys()):
                if k.lower() in _SENTRY_PII_FIELDS:
                    val[k] = "[scrubbed]"

    # ---- Rate limit ----
    global _sentry_drops_since_log
    with _sentry_rate_lock:
        now = time.monotonic()
        elapsed = now - _sentry_rate_state["last_refill"]
        refill = elapsed / _SENTRY_TOKEN_REFILL_INTERVAL_S
        if refill > 0:
            _sentry_rate_state["tokens"] = min(
                float(_SENTRY_RATE_CAP_PER_HOUR),
                _sentry_rate_state["tokens"] + refill,
            )
            _sentry_rate_state["last_refill"] = now
        if _sentry_rate_state["tokens"] < 1.0:
            _sentry_drops_since_log += 1
            # Periodic local log so ops sees the drop volume — don't
            # send this to Sentry (that would defeat the rate limit).
            if _sentry_drops_since_log == 1 or _sentry_drops_since_log % 100 == 0:
                # logger is set up later in this module; use stderr-print
                # as a fallback since this hook runs throughout the lifetime.
                sys.stderr.write(
                    f"[SENTRY-RATE-LIMITED] dropped {_sentry_drops_since_log} "
                    f"events since last log (cap={_SENTRY_RATE_CAP_PER_HOUR}/hr)\n"
                )
            return None
        _sentry_rate_state["tokens"] -= 1.0
        _sentry_drops_since_log = 0

    return event


def _read_version_sha():
    """Read git SHA from VERSION file written by deploy. Falls back to
    'dev' for local runs. Shared by Sentry release tag + /health (T2)."""
    try:
        with open(os.path.join(project_root, "VERSION"), "r") as f:
            return f.read().strip() or "dev"
    except (OSError, IOError):
        return "dev"


_SENTRY_DSN = os.environ.get("SENTRY_DSN")
if _SENTRY_DSN and sentry_sdk is not None:
    sentry_sdk.init(
        dsn=_SENTRY_DSN,
        integrations=[FlaskIntegration()] if FlaskIntegration else [],
        traces_sample_rate=0.1,  # 10% — free-tier budget-friendly
        release=_read_version_sha(),
        send_default_pii=False,  # we send what we want via before_send
        before_send=_sentry_before_send,
    )


def _user_pdf_dir(user_id):
    """
    Per-user PDF storage directory. The /download route only ever reads
    from <OUTPUT_DIR>/<current_user.id>/, so cross-tenant filename guesses
    can't escape the caller's own bucket — the user_id never appears in
    URLs, it's pulled from the session.

    BUG-008 fix (Sprint 4): pre-fix, the download route served any file in
    project_root, exposing sovereign.db and source files to any logged-in
    user. Per-user buckets contain only PDFs that user has generated.

    Hotfix-2 T3: directory mode locked to 0o700 (owner-only). The app user
    is the only legitimate reader anyway — PDFs flow through /download,
    which round-trips through Flask, not a static file server. Existing
    dirs (pre-Hotfix-2) get tightened on first touch via the explicit
    os.chmod below. On Windows the chmod is effectively a no-op (NTFS ACLs
    own the actual permissions); the umask-default 0o777 there is fine
    because the test environment isn't shared-host.
    """
    import config as _config
    d = os.path.join(_config.OUTPUT_DIR, str(int(user_id)))
    os.makedirs(d, mode=0o700, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except (OSError, NotImplementedError):
        # Windows + some filesystems reject the chmod silently. The
        # makedirs() mode flag already covers the create case; the chmod
        # is a tightening pass for dirs created pre-Hotfix-2 on POSIX.
        pass
    return d

from flask import (
    Flask, render_template, request, send_file, jsonify,
    redirect, url_for, flash, abort
)
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
import stripe

import config
import mailer
from engine import calculate_quote
from generator import (
    generate_document, derive_doc_code,
    DEFAULT_QUOTE_FOOTER, DEFAULT_INVOICE_FOOTER, DEFAULT_PHONE_NUMBER,
    INVOICE_PREFIX_DEFAULT, INVOICE_PREFIX_MAX,
)
from models import db, User, Transaction, PricingProfile, Quote, ContactSubmission
from notices import build_soft_cap_notice, build_soft_cap_warning, build_rate_limit_notice

app = Flask(__name__)
app.config.from_object(config)
app.secret_key = config.SECRET_KEY

# Session timeout. PERMANENT_SESSION_LIFETIME comes in via from_object(config)
# above (defined in config.py — Hotfix-1 T2 raised the cap from 24h to 7d).
# Only takes effect when `session.permanent = True` — set in /register and
# /login after a successful auth. After the configured idle window the
# cookie expires and the user is forced through /login again.

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

# Hotfix-2 T2: CSRF protection on all state-changing POSTs.
#
# Every <form method=POST> in templates must include
#   <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
# AJAX calls must send the same token via the `X-CSRFToken` request header.
# A `<meta name="csrf-token" content="{{ csrf_token() }}">` element in each
# template's <head> exposes the token to the inline JS that wires the
# fetch() calls.
#
# /webhook/stripe is explicitly @csrf.exempt'd below — Stripe signs the
# request body with HMAC and cannot provide a session-scoped CSRF token,
# so layering both protections would only break the integration.
#
# WTF_CSRF_DISABLED env kill switch:
#   The test suite (testing/stress_probe.py, test_sprint*.py, etc.) was
#   written pre-CSRF and POSTs forms without tokens. Rather than refactor
#   every test, the server can be started with WTF_CSRF_DISABLED=1 to
#   bypass CSRF for the duration of the test run. This is a TEST-ONLY
#   escape hatch — production MUST NOT set this var. CSRF correctness is
#   verified independently by the smoke check in DEPLOYMENT.md §2.8.
if os.environ.get("WTF_CSRF_DISABLED", "").lower() in ("1", "true", "yes"):
    app.config["WTF_CSRF_ENABLED"] = False
    app.logger.warning(
        "[CSRF] disabled via WTF_CSRF_DISABLED env — TEST USE ONLY. "
        "Production deploys MUST NOT set this variable."
    )

# Hotfix-3 T1: loud warning when MAIL_DISABLED is set so production
# misconfiguration is impossible to miss in the boot log. Same shape
# as the CSRF warning above.
if config.MAIL_DISABLED:
    app.logger.warning(
        "[MAIL] disabled via MAIL_DISABLED env — TEST USE ONLY. "
        "Production deploys MUST NOT set this variable."
    )
elif not config.POSTMARK_SERVER_TOKEN and not config.DEV_MODE:
    # In prod (DEV_MODE unset, MAIL_DISABLED unset), missing Postmark
    # token is a hard config error — the verification email path is
    # unreachable, so no new user can satisfy the email_verified gate.
    # Fail loud at boot rather than silently ship an unusable build.
    app.logger.error(
        "[MAIL] POSTMARK_SERVER_TOKEN is not set and we are not in DEV_MODE/"
        "MAIL_DISABLED — /register will accept signups but no verification "
        "emails will be delivered. Set POSTMARK_SERVER_TOKEN or restart "
        "with DEV_MODE=1 / MAIL_DISABLED=1 for non-prod runs."
    )
csrf = CSRFProtect(app)

# Hotfix-2 T4 (part 1): rate limiting on auth + state-changing routes.
#
# No global default — only the @limiter.limit decorators below apply.
# Storage is in-memory (single-process); Sprint 5 will swap to Redis when
# we deploy multi-worker. IP key uses get_remote_address, which reads
# request.remote_addr. Behind a reverse proxy that needs ProxyFix middleware
# to honor X-Forwarded-For — see DEPLOYMENT.md §11 (Sprint 5 ops).
#
# Local tests opt out via RATELIMIT_DISABLED=1 (mirrors WTF_CSRF_DISABLED's
# pattern) so the locust + stress_probe harness doesn't trip the limits
# during high-rate runs.
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
    enabled=os.environ.get("RATELIMIT_DISABLED", "").lower() not in ("1", "true", "yes"),
)

# Hotfix-6 T1: ProxyFix for reverse proxy headers.
#
# Without this, request.remote_addr = proxy IP, which means the rate
# limiter gates the entire site on one global bucket. x_for=1 means
# one trusted proxy layer (Render / nginx / Caddy). See DEPLOYMENT.md §8.
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

# Hotfix-2 T4 (part 2): security response headers via Flask-Talisman.
#
# CSP allowlist matches the third-party assets actually loaded:
#   - cdn.tailwindcss.com (script)            — base styling JIT
#   - fonts.googleapis.com (style)            — Google Fonts CSS
#   - fonts.gstatic.com (font)                — Google Fonts files
#   - js.stripe.com (script + frame)          — Stripe Checkout JS + iframe
#   - api.stripe.com (connect)                — Stripe API from JS
# style-src needs 'unsafe-inline' because templates use <style> blocks.
# script-src does NOT — and there are no inline <script> blocks that
# would need it (all our inline JS lives at file scope; the CSP nonce
# pattern is overkill for this size of app).
#
# force_https mirrors the cookie-SECURE gate from T1: prod redirects HTTP
# -> HTTPS, dev (DEV_MODE=1) skips the redirect so plain-HTTP localhost
# still works.
_TALISMAN_CSP = {
    "default-src": "'self'",
    "script-src": ["'self'", "cdn.tailwindcss.com", "js.stripe.com"],
    "style-src": ["'self'", "'unsafe-inline'", "fonts.googleapis.com"],
    "font-src": ["'self'", "fonts.gstatic.com"],
    "img-src": ["'self'", "data:"],
    "connect-src": ["'self'", "api.stripe.com"],
    "frame-src": ["js.stripe.com"],
    "frame-ancestors": "'none'",
    "base-uri": "'self'",
    "form-action": ["'self'", "checkout.stripe.com"],
}
Talisman(
    app,
    content_security_policy=_TALISMAN_CSP,
    force_https=not config.DEV_MODE,
    strict_transport_security=not config.DEV_MODE,
    strict_transport_security_max_age=31536000,  # 1 year
    strict_transport_security_include_subdomains=True,
    referrer_policy="strict-origin-when-cross-origin",
    session_cookie_secure=False,  # T1 already manages this via config.py
    frame_options="DENY",
)

if config.STRIPE_SECRET_KEY:
    stripe.api_key = config.STRIPE_SECRET_KEY


@app.context_processor
def inject_support_email():
    """
    Sprint 4 T5: surface SUPPORT_EMAIL into every Jinja render so the
    site-wide footer, account page, contact CTA, and error pages can
    show the same address. Sourced from config (env-configurable per
    deployment) — never hardcoded in templates.
    """
    return {"support_email": config.SUPPORT_EMAIL}


@app.errorhandler(404)
def _err_404(e):
    """Friendly 404 with a contact route. Falls back to plain text if the
    template hasn't shipped yet."""
    try:
        return render_template("404.html"), 404
    except Exception:
        return f"404 — page not found. Need help? Contact {config.SUPPORT_EMAIL}", 404


@app.errorhandler(500)
def _err_500(e):
    """Friendly 500 with a contact route. App-side rollback already happened
    upstream via the route's own try/except — this is purely the customer-
    facing page."""
    try:
        return render_template("500.html"), 500
    except Exception:
        return f"500 — internal error. Please try again, or contact {config.SUPPORT_EMAIL}", 500


@login_manager.user_loader
def load_user(user_id):
    # BUG-003 (Sprint 4): no longer auto-seeds starter profiles. New users
    # are routed through /profiles/new via the index redirect — they own
    # the act of creating their first profile, which doubles as onboarding.
    # Existing users keep whatever profiles they already have; only the
    # auto-seed for an empty profile table was removed.
    return db.session.get(User, int(user_id))


_SCHEMA_TABLE_ALLOWLIST = frozenset({"users", "quotes"})


def _ensure_table_columns(table_name, additions):
    """
    SQLite lacks ALTER TABLE ... ADD COLUMN IF NOT EXISTS, and db.create_all()
    only creates missing tables — not missing columns. This runs once at boot
    and additively patches columns added after a table was first created.

    Hotfix-2 T3 hardening: `table_name` is interpolated into raw SQL via
    f-string (necessary — SQL parameter binding doesn't work for DDL
    identifiers), so it MUST be an allowlisted constant. If a future
    refactor turns this into a CLI tool or admin-facing helper, the
    allowlist check below blocks SQLi at the helper boundary even if the
    caller forgets to validate. Not user-reachable today; defense in depth
    for tomorrow.
    """
    if table_name not in _SCHEMA_TABLE_ALLOWLIST:
        raise ValueError(
            f"_ensure_table_columns: '{table_name}' not in allowlist "
            f"{sorted(_SCHEMA_TABLE_ALLOWLIST)}. Refusing to interpolate "
            f"unvetted identifier into DDL."
        )
    existing = {row[1] for row in db.session.execute(text(f"PRAGMA table_info({table_name})")).fetchall()}
    for col, ddl in additions:
        if col not in existing:
            db.session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col} {ddl}"))
    db.session.commit()


def _ensure_starting_credit_floor():
    """
    One-time top-up: bump any existing user under STARTING_CREDITS up to it.
    Idempotent — re-runs are no-ops once everyone is at-or-above. Runs at
    boot rather than via a versioned-migration table because the project is
    pre-launch and lift-from-5-to-10 is a one-shot courtesy. If admin
    tooling later starts deliberately setting balances below the floor,
    this needs a stronger guard (e.g., a `received_topup` flag).
    """
    db.session.execute(
        text("UPDATE users SET credit_balance = :n WHERE credit_balance < :n"),
        {"n": config.STARTING_CREDITS},
    )
    db.session.commit()


def _backfill_email_verified():
    """
    Grandfather pre-Sprint-3 users as email-verified. Identifies them by
    the absence of a verification token (Sprint 3 registration generates
    a token; older users have none). Idempotent — re-runs only touch rows
    still in the pre-Sprint-3 state. New post-Sprint-3 unverified users
    have a token, so this never wrongly verifies them.
    """
    db.session.execute(text(
        "UPDATE users SET email_verified = 1 "
        "WHERE email_verified = 0 AND email_verification_token IS NULL"
    ))
    db.session.commit()


with app.app_context():
    db.create_all()
    _ensure_table_columns("users", [
        ("business_name", "TEXT"),
        ("phone_number", "TEXT"),
        ("quote_footer_text", "TEXT"),
        ("invoice_footer_text", "TEXT"),
        # Per-user sequential invoice counter (Feature 2). Default 1 so the
        # first claim returns 1 and post-increment leaves 2 for next time.
        ("next_invoice_number", "INTEGER NOT NULL DEFAULT 1"),
        # Per-user invoice prefix (Feature 3). DEFAULT 'INV-' preserves the
        # original Feature 2 hardcoded behavior for users who never customize.
        ("invoice_prefix", "TEXT NOT NULL DEFAULT 'INV-'"),
        # Per-user sequential quote counter (BUG-007, Sprint 4). Mirrors
        # next_invoice_number — the counter sits on User, claimed once at
        # /generate time and snapshotted onto Quote.quote_number. Default 1
        # so the first quote a user generates renders as Q-000001. Existing
        # users get the column with default 1; their pre-Sprint-4 quotes
        # show the legacy hash code as before (since Quote.quote_number
        # remains NULL for those rows).
        ("next_quote_number", "INTEGER NOT NULL DEFAULT 1"),
        # Per-user quote prefix (BUG-007). Default 'Q-' is the same kind of
        # back-compat default invoice_prefix uses. Snapshotted onto Quote
        # at claim time so a later prefix change doesn't retroactively
        # rename existing quotes — same stability rule as invoices.
        ("quote_prefix", "TEXT NOT NULL DEFAULT 'Q-'"),
        # Subscription columns. UNIQUE on subscription_id is created as a
        # separate index below — SQLite's ALTER TABLE ADD COLUMN cannot
        # apply UNIQUE in-place. All three are nullable: existing users
        # (non-subscribers) carry NULLs and the reserve bypass treats NULL
        # subscription_status as "no active sub, fall through to credits".
        ("subscription_status", "TEXT"),
        ("subscription_id", "TEXT"),
        ("subscription_current_period_end", "DATETIME"),
        # Pending cancellation flag. NOT NULL with a default so existing
        # rows backfill cleanly to False; SQLite accepts BOOLEAN as an
        # INTEGER alias and stores 0/1 — Python sees True/False via
        # SQLAlchemy's Boolean type.
        ("cancel_at_period_end", "BOOLEAN NOT NULL DEFAULT 0"),
        # Login lockout (T4). Defaults backfill cleanly to "no failures,
        # not locked" for existing users.
        ("failed_login_attempts", "INTEGER NOT NULL DEFAULT 0"),
        ("locked_until", "DATETIME"),
        # Email verification (T4). New users get email_verified=False at
        # registration; pre-Sprint-3 users are grandfathered to True via
        # _backfill_email_verified() so the gate doesn't lock them out.
        ("email_verified", "BOOLEAN NOT NULL DEFAULT 0"),
        ("email_verification_token", "TEXT"),
        ("email_verification_token_expires", "DATETIME"),
        # Hotfix-3 T3: password reset tokens. Mirror the email_verification
        # columns; same shape, separate column so a reset-link click can't
        # accidentally satisfy the email-verification gate (different
        # security domains: verify proves you own the email, reset proves
        # you can read the inbox NOW).
        ("password_reset_token", "TEXT"),
        ("password_reset_token_expires", "DATETIME"),
    ])
    db.session.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_users_email_verification_token "
        "ON users(email_verification_token)"
    ))
    db.session.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_users_password_reset_token "
        "ON users(password_reset_token)"
    ))
    db.session.commit()
    db.session.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_subscription_id "
        "ON users(subscription_id)"
    ))
    db.session.commit()
    _ensure_table_columns("quotes", [
        ("customer_name", "TEXT"),
        ("customer_address", "TEXT"),
        ("customer_email", "TEXT"),
        ("customer_phone", "TEXT"),
        # Cached claimed invoice number (Feature 2). Nullable: a Quote that
        # is never rendered as an INVOICE never gets one. Set once, never
        # changed — the gap-free monotonic invariant lives in the User
        # counter, this column just memoizes the claim per Quote.
        ("invoice_number", "INTEGER"),
        # Snapshot of User.invoice_prefix at claim time (Feature 3).
        # Nullable: null for non-invoiced quotes and pre-Feature-3 invoices
        # (those fall back to "INV-" via the generator default — see
        # generator.generate_document). Once set, never changes.
        ("invoice_prefix", "TEXT"),
        # Sequential quote number (BUG-007, Sprint 4). Claimed once at
        # /generate time; mirrors invoice_number's lifecycle on the quote
        # side. Nullable for back-compat: pre-Sprint-4 quotes have NULL
        # here and the generator falls back to the legacy hash doc_code
        # so old PDFs re-render with the same identifier they had before.
        ("quote_number", "INTEGER"),
        # Snapshot of User.quote_prefix at claim time (BUG-007). Same
        # stability invariant as invoice_prefix: once set, never changes.
        ("quote_prefix", "TEXT"),
    ])
    _ensure_starting_credit_floor()
    _backfill_email_verified()


# ---------- Profile helpers (engine-agnostic controller layer) ----------

def _load_seed_price_sheet():
    with open(config.SEED_PRICE_SHEET_PATH, "r") as f:
        return json.load(f)


def ensure_default_profiles_for_user(user):
    """
    Seeds a new user's profile table from the packaged price_sheet.json.
    Idempotent — does nothing if the user already has profiles.
    """
    if PricingProfile.query.filter_by(user_id=user.id).first():
        return

    seed = _load_seed_price_sheet()
    active = seed.get("active_profile")
    for name, price_data in seed.get("profiles", {}).items():
        profile = PricingProfile(
            user_id=user.id,
            name=name,
            price_data=price_data,
            is_default=(name == active),
        )
        db.session.add(profile)
    db.session.commit()


def get_user_profile_registry(user, preferred_name=None):
    """
    Build a registry dict in the shape calculate_quote() expects,
    using the user's DB profiles — never the static JSON.
    """
    profiles = PricingProfile.query.filter_by(user_id=user.id).all()
    registry = {"profiles": {p.name: p.price_data for p in profiles}}

    active = None
    if preferred_name and any(p.name == preferred_name for p in profiles):
        active = preferred_name
    else:
        default = next((p for p in profiles if p.is_default), None)
        active = default.name if default else (profiles[0].name if profiles else None)

    registry["active_profile"] = active
    return registry, profiles


def set_default_profile(user, profile_id):
    """Atomically flip the default flag. Only one default per user."""
    db.session.execute(
        text("UPDATE pricing_profiles SET is_default = 0 WHERE user_id = :uid"),
        {"uid": user.id},
    )
    db.session.execute(
        text("UPDATE pricing_profiles SET is_default = 1 WHERE id = :pid AND user_id = :uid"),
        {"pid": profile_id, "uid": user.id},
    )
    db.session.commit()


def apply_callout_override(registry, profile_id, callout_override):
    """
    Controller-layer callout override injection. The engine's API doesn't
    expose a callout_override param, so we swap the value in a cloned
    profile dict before passing the registry to calculate_quote().
    Keeps the engine pure.
    """
    if not callout_override:
        return registry
    if not profile_id or profile_id not in registry["profiles"]:
        return registry
    try:
        new_fee = float(callout_override)
    except (TypeError, ValueError):
        return registry
    # Clone the profile dict so we don't mutate the SQLAlchemy-tracked JSON.
    profile_copy = dict(registry["profiles"][profile_id])
    profile_copy["base_callout_fee"] = new_fee
    registry["profiles"][profile_id] = profile_copy
    return registry


# ---------- Quote persistence + rehydration (Heresy #11 fix) ----------

LABEL_MAX_LEN = 80
FOOTER_MAX_LEN = 200
CUSTOMER_NAME_MAX = 100
CUSTOMER_ADDR_MAX = 200
CUSTOMER_EMAIL_MAX = 254  # RFC 5321 max length
CUSTOMER_PHONE_MAX = 30
# Hotfix-1 T4 — caps for fields that previously had only `.strip()` and no
# length bound, opening a small DOS / DB-bloat surface. Truncated silently
# via _sanitize_storage (matches existing customer_* behavior). Sized to
# accommodate realistic input plus generous slack — a real business name
# never approaches 200 chars, but truncation at 200 still produces something
# usable rather than rejecting the whole form.
BUSINESS_NAME_MAX = 200
PROFILE_NAME_MAX = LABEL_MAX_LEN          # profile labels follow the quote-label cap
CONTACT_COMPANY_MAX = 200
CONTACT_VOLUME_MAX = 200
CONTACT_GROWTH_MAX = 2000                 # notes/description tier per spec
CONTACT_EMAIL_MAX = CUSTOMER_EMAIL_MAX    # same RFC ceiling
# Invoice prefix raw-input cap (Feature 3). One char less than the
# stored INVOICE_PREFIX_MAX (=12) so sanitize_invoice_prefix can
# auto-append a "-" without exceeding the column-level cap.
INVOICE_PREFIX_INPUT_MAX = INVOICE_PREFIX_MAX - 1
# Allowed chars: letters, digits, space, ampersand, period, dash. The
# {0,11} cap matches INVOICE_PREFIX_INPUT_MAX. Empty is intentionally
# allowed — user spec'd "0 chars OK" for naked-number rendering.
_INVOICE_PREFIX_RE = re.compile(r"^[A-Za-z0-9 &.\-]{0," + str(INVOICE_PREFIX_INPUT_MAX) + r"}$")


def _sanitize_storage(raw, max_len):
    """
    Storage-layer sanitize: trim, collapse whitespace, cap length.
    Latin-1 stripping is intentionally NOT done here so the DB keeps full
    unicode (smart quotes, etc.) for display in forms. The generator runs
    a Latin-1 strip as defense in depth before rendering. Heresy #10.
    """
    if not raw:
        return ""
    cleaned = " ".join(str(raw).split())
    return cleaned[:max_len]


def sanitize_label(raw):
    return _sanitize_storage(raw, LABEL_MAX_LEN)


def sanitize_footer(raw):
    return _sanitize_storage(raw, FOOTER_MAX_LEN)


def sanitize_invoice_prefix(raw):
    """
    Validate + normalize a user-supplied invoice prefix (Feature 3).

    Returns the normalized prefix on success, or None on validation
    failure (caller should flash an error and abort the save). Empty
    string is a valid input — user spec'd "0 chars OK" for callers who
    want bare numeric IDs like "000042".

    Pipeline:
      1. Trim leading/trailing whitespace from raw input.
      2. Reject anything outside [A-Za-z0-9 &.-] or longer than
         INVOICE_PREFIX_INPUT_MAX (currently 11).
      3. If non-empty AND last char is alphanumeric, auto-append "-" so
         the number doesn't smush into the prefix. The 11-char input cap
         leaves exactly the 1 char of headroom this auto-append needs,
         keeping the final stored value <= INVOICE_PREFIX_MAX (=12).

    Auto-append rule rationale: typing "ACME" should produce "ACME-000042",
    not "ACME000042". But typing "ACME-" or "Q3.2026 " or "ACME&CO " (all
    already ending in a separator-ish char) leaves the prefix alone — we
    only add the dash when the last char is alphanumeric.
    """
    if raw is None:
        return None
    trimmed = raw.strip()
    if not _INVOICE_PREFIX_RE.match(trimmed):
        return None
    if trimmed and trimmed[-1].isalnum():
        trimmed = trimmed + "-"
    return trimmed


def render_footer_template(template, doc_type, phone_number):
    """
    Substitute {{phone}} and {{date}} placeholders in a footer template.

    Substitution lives in the controller so the generator stays a Pure View
    (no datetime calls, no fallback logic). NULL/empty `template` falls back
    to the sovereign default for the doc_type.

    {{date}} is context-aware:
      QUOTE   -> today + 7 days (the existing quote-expiration semantic)
      INVOICE -> today (issue date; the original invoice footer didn't use
                 a date, but if a user adds {{date}} they get a sensible one)
    """
    doc_type = (doc_type or "QUOTE").upper()
    if not template:
        template = DEFAULT_INVOICE_FOOTER if doc_type == "INVOICE" else DEFAULT_QUOTE_FOOTER

    phone = (phone_number or DEFAULT_PHONE_NUMBER).strip() or DEFAULT_PHONE_NUMBER
    if doc_type == "INVOICE":
        date_value = datetime.now().strftime("%Y-%m-%d")
    else:
        date_value = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

    return (
        template
        .replace("{{phone}}", phone)
        .replace("{{date}}", date_value)
    )


def _serialize_for_json(obj):
    """Recursively convert Decimals to strings so round-trip is lossless."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _serialize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize_for_json(v) for v in obj]
    return obj


def _rehydrate_decimals(obj, decimal_keys):
    """Walk a snapshot-shaped dict and re-Decimal known numeric fields."""
    calc = obj.get("calculation", {})
    for k in ("subtotal_panes", "subtotal_addons", "final_before_tax", "tax_amount", "grand_total"):
        if k in calc and calc[k] is not None:
            calc[k] = Decimal(str(calc[k]))
    for item in obj.get("line_items", []):
        if "cost" in item and item["cost"] is not None:
            item["cost"] = Decimal(str(item["cost"]))
    return obj


def load_quote_snapshot(quote):
    """Return a snapshot dict ready to pass to generate_document()."""
    raw = dict(quote.quote_data or {})
    return _rehydrate_decimals(raw, None)


def _claim_invoice_number(quote):
    """
    Atomically claim the next sequential invoice number for this quote's
    owner and persist it on the Quote row (Feature 2: tax/legal compliance —
    invoice numbers must be sequential and gap-free).

    Idempotent: if the quote already has an invoice_number, return it
    unchanged. This is what makes re-renders of the same invoice show the
    same number (a downloader hitting refresh, the user re-printing months
    later, etc.) — the gap-free invariant lives on User.next_invoice_number,
    this column just memoizes the per-quote claim.

    Concurrency: the increment is a single UPDATE statement, so there is no
    read-then-write window where two requests could both observe the same
    next_invoice_number. SQLite serializes writes per-database via file
    lock, so two simultaneous claims queue rather than collide. The pattern
    is also race-safe on Postgres (UPDATE acquires a row lock for the txn).

    Failure semantics: this commits before generate_document runs. If PDF
    rendering then fails, the claim is *kept* (the next claim will get
    n+2). We optimize for "never reuse a number" over "no gaps from failed
    renders" — gaps are auditable as render failures; reuse is fraud.
    """
    if quote.invoice_number is not None:
        return quote.invoice_number

    # Atomic post-increment + prefix snapshot. We bump first, then read
    # back the new counter alongside the user's current invoice_prefix in
    # one SELECT — both pieces of identifying info land on the Quote row
    # in the same commit. Doing the bump first means we never need a
    # SELECT...FOR UPDATE equivalent (which SQLite doesn't have) — the
    # UPDATE itself is the serialization point.
    #
    # Prefix snapshot (Feature 3) is what makes invoice IDs stable across
    # later prefix changes: a user who issues INV-000005 and then changes
    # their setting to ACME- will see new invoices come out ACME-000006,
    # but re-renders of the original still read INV-000005 because that
    # value is frozen on the Quote row.
    db.session.execute(
        text("UPDATE users SET next_invoice_number = next_invoice_number + 1 "
             "WHERE id = :uid"),
        {"uid": quote.user_id},
    )
    row = db.session.execute(
        text("SELECT next_invoice_number, invoice_prefix FROM users "
             "WHERE id = :uid"),
        {"uid": quote.user_id},
    ).first()
    claimed = row[0] - 1
    # Belt-and-suspenders fallback: column is NOT NULL DEFAULT 'INV-' so
    # this should never be None in practice, but if a row somehow predates
    # the migration we still get a sane prefix instead of a crash.
    prefix = row[1] if row[1] is not None else INVOICE_PREFIX_DEFAULT

    quote.invoice_number = claimed
    quote.invoice_prefix = prefix
    db.session.commit()
    return claimed


def _claim_quote_number(quote):
    """
    Atomically claim the next sequential quote number for this quote's owner
    and persist it on the Quote row. Same atomic-UPDATE pattern as
    _claim_invoice_number — bump first, read back, snapshot prefix.

    Quote numbers are NOT a legal/tax compliance artifact (only invoice
    numbers are), but we apply the same gap-aware semantics for consistency
    and so that "Q-000004" reads naturally to a customer whose previous
    quote was Q-000003. Idempotent: if the quote already has a number,
    return it. Failure semantics mirror the invoice path: claim is kept
    even if downstream PDF render fails (we'd rather see a gap than reuse
    a number).
    """
    if quote.quote_number is not None:
        return quote.quote_number, quote.quote_prefix or "Q-"

    db.session.execute(
        text("UPDATE users SET next_quote_number = next_quote_number + 1 "
             "WHERE id = :uid"),
        {"uid": quote.user_id},
    )
    row = db.session.execute(
        text("SELECT next_quote_number, quote_prefix FROM users "
             "WHERE id = :uid"),
        {"uid": quote.user_id},
    ).first()
    claimed = row[0] - 1
    prefix = row[1] if row[1] is not None else "Q-"

    quote.quote_number = claimed
    quote.quote_prefix = prefix
    db.session.commit()
    return claimed, prefix


# ---------- Internal benchmark (Heresy #9 — informational only) ----------

BENCHMARK_MIN_HISTORY = 3       # total user quotes required before any benchmark shows
BENCHMARK_BAND = Decimal("0.25")  # ±25% pane-count band counts as "similar size"


def compute_internal_benchmark(user, current_pane_count, current_price):
    """
    Per-user, per-job-size average $/pane across the user's own history.
    Returns dict(avg_per_pane, current_per_pane, sample_size) or None.
    Engine stays agnostic — this reads only the Quote table.
    """
    if current_pane_count <= 0:
        return None

    total_history = Quote.query.filter_by(user_id=user.id).count()
    if total_history <= BENCHMARK_MIN_HISTORY:
        return None

    low = int(current_pane_count * (1 - float(BENCHMARK_BAND)))
    high = int(current_pane_count * (1 + float(BENCHMARK_BAND))) + 1
    if low < 1:
        low = 1

    similar = Quote.query.filter(
        Quote.user_id == user.id,
        Quote.pane_count >= low,
        Quote.pane_count <= high,
        Quote.pane_count > 0,
    ).all()
    if not similar:
        return None

    total_ppp = Decimal("0")
    for q in similar:
        total_ppp += Decimal(q.final_price) / Decimal(q.pane_count)
    avg_ppp = (total_ppp / Decimal(len(similar))).quantize(Decimal("0.01"))

    current_ppp = (Decimal(str(current_price)) / Decimal(current_pane_count)).quantize(Decimal("0.01"))
    return {
        "avg_per_pane": avg_ppp,
        "current_per_pane": current_ppp,
        "sample_size": len(similar),
    }


# ---------- Auth ----------

PASSWORD_MAX_LEN = 128


def _issue_verification_token(user):
    """
    Generate a fresh verification token for `user`, persist it on the row,
    and commit. Used by both /register (first-time) and /resend-verification
    (re-issue). Token is 32-char uuid hex; expires 24h from issue.

    Returns the token string so the caller can build the verify URL without
    a second DB round-trip.
    """
    token = uuid.uuid4().hex
    user.email_verification_token = token
    user.email_verification_token_expires = datetime.utcnow() + timedelta(hours=24)
    db.session.commit()
    return token


def _notify_admin(alert_tag, subject_summary, body_markdown):
    """
    Hotfix-3 T5: route an operational alert to ADMIN_EMAIL via the
    same Postmark backend used for user-facing transactional mail.
    Sites that call this also log structured tags (e.g. [CREDIT-REFUND-FAILED])
    so the log + email are redundant — log for forensic depth, email so
    the operator notices same-day instead of when they next tail the log.

    Returns the mailer result (True/False) but callers SHOULD NOT branch
    on it — admin alerts are best-effort by design; a failed alert send
    must not cascade and break the primary flow (refund, delete, etc).
    """
    return mailer.send_email(
        to=config.ADMIN_EMAIL,
        subject=f"[{alert_tag}] {subject_summary}",
        html_body=render_template(
            "email/admin_alert.html",
            alert_tag=alert_tag,
            subject_summary=subject_summary,
            body_markdown=body_markdown,
        ),
        text_body=render_template(
            "email/admin_alert.txt",
            alert_tag=alert_tag,
            subject_summary=subject_summary,
            body_markdown=body_markdown,
        ),
    )


def _send_verification_email(user, token):
    """
    Send the email-verification message to `user`. Returns True on success,
    False on send failure (mailer never raises, so neither do we).

    The verify URL log line is kept as a fallback for ops debugging — if a
    customer reports the email never arrived, ops can pull the most-recent
    verify URL from the gunicorn log without needing DB access. Logged at
    INFO so it's visible in normal log retention but doesn't trip Sentry
    alerts. Postmark dashboard is the canonical record of delivery.
    """
    verify_url = url_for("verify_email", token=token, _external=True)
    app.logger.info(
        "[EMAIL-VERIFICATION] issued for user_id=%s email=%s verify_url=%s",
        user.id, user.email, verify_url,
    )
    html_body = render_template(
        "email/verify.html",
        verify_url=verify_url,
        support_email=config.SUPPORT_EMAIL,
    )
    text_body = render_template(
        "email/verify.txt",
        verify_url=verify_url,
        support_email=config.SUPPORT_EMAIL,
    )
    return mailer.send_email(
        to=user.email,
        subject="Verify your Panefree Quotes email",
        html_body=html_body,
        text_body=text_body,
    )


def _password_strength_error(password):
    """T4 password rules: ≥8 chars AND ≥1 digit. Returns the error message
    to flash, or None if the password passes. Pure helper for testability.

    Hotfix-2 T3: upper-bounded at PASSWORD_MAX_LEN (128) to close the
    pbkdf2 DoS surface. werkzeug.security uses 600k iterations of pbkdf2-
    sha256; on a 4KB password that's a multi-second hash, which a single
    attacker can use to saturate the auth path with a small number of
    requests. 128 chars is well above any realistic human password
    (longest in the haveibeenpwned dump of 600M is ~80) and well below
    the DoS threshold. Rejecting (rather than truncating) is the safer
    choice because truncation silently collides distinct passwords."""
    if len(password) > PASSWORD_MAX_LEN:
        return f"Password is too long (max {PASSWORD_MAX_LEN} characters)."
    if len(password) < 8:
        return "Password must be at least 8 characters long."
    if not any(c.isdigit() for c in password):
        return "Password must include at least one number."
    return None


@app.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("register.html")

        pw_error = _password_strength_error(password)
        if pw_error:
            flash(pw_error, "error")
            return render_template("register.html")

        if User.query.filter_by(email=email).first():
            flash("That email is already registered.", "error")
            return render_template("register.html")

        # Hotfix-3 T2: real verification email via Postmark. Pre-Hotfix-3
        # the verify URL was only logged; users could never satisfy the
        # email_verified gate unless ops manually pulled the log line.
        user = User(
            email=email,
            credit_balance=config.STARTING_CREDITS,
            email_verified=False,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()  # commit before _issue_verification_token so user.id exists

        # Hotfix-4 T3: happy-path log for the signup funnel. Lets ops
        # answer "how many signups happened today" from logs without
        # touching the DB, and pairs with [EMAIL-VERIFICATION] /
        # [LOGIN-SUCCESS] for a complete user-lifecycle trail.
        app.logger.info(
            "[REGISTER-SUCCESS] user_id=%s email=%s", user.id, user.email,
        )

        # BUG-003 (Sprint 4): new users no longer get auto-seeded starter
        # profiles. The first hit to "/" redirects them into /profiles/new
        # so the first profile creation IS the onboarding step.
        token = _issue_verification_token(user)
        sent = _send_verification_email(user, token)
        login_user(user)
        # DO NOT REMOVE — required for PERMANENT_SESSION_LIFETIME to apply.
        # Flask only honors the configured lifetime when session.permanent is
        # True; without this, cookies fall back to browser-session scope and
        # the 7-day cap (config.py) becomes a no-op.
        from flask import session as _session
        _session.permanent = True
        if sent:
            flash(
                "Account created. Check your email for a verification link "
                "before generating quotes.",
                "success",
            )
        else:
            # Send failed but user row + token persist — they can click the
            # resend banner from the EMAIL_NOT_VERIFIED page. Don't roll back
            # the registration; losing the account on a transient email
            # outage is worse than the inconvenience of one resend click.
            flash(
                "Account created, but we couldn't send your verification "
                "email just now. Try the resend link, or contact support if "
                "the problem persists.",
                "error",
            )
        return redirect(url_for("index"))

    return render_template("register.html")


LOGIN_LOCKOUT_THRESHOLD = 5
LOGIN_LOCKOUT_MINUTES = 15


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        user = User.query.filter_by(email=email).first()
        now = datetime.utcnow()

        # Lockout check first — even a correct password is rejected during
        # the cooldown window (otherwise the lockout has no teeth).
        if user and user.locked_until and user.locked_until > now:
            wait = int((user.locked_until - now).total_seconds() / 60) + 1
            flash(
                f"Account temporarily locked after too many failed sign-ins. "
                f"Try again in {wait} minute{'' if wait == 1 else 's'}.",
                "error",
            )
            return render_template("login.html")

        if not user or not user.check_password(password):
            # Increment fail counter on a known user; unknown email gets the
            # generic "invalid" without revealing whether the email exists.
            if user:
                user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
                if user.failed_login_attempts >= LOGIN_LOCKOUT_THRESHOLD:
                    user.locked_until = now + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
                    user.failed_login_attempts = 0  # consumed → reset
                db.session.commit()
            flash("Invalid email or password.", "error")
            return render_template("login.html")

        # Successful login — reset both counter and lockout.
        user.failed_login_attempts = 0
        user.locked_until = None
        db.session.commit()

        # BUG-003 (Sprint 4): no auto-seed at login either. Users without
        # any profiles get bounced to /profiles/new by the index route.
        login_user(user)
        # DO NOT REMOVE — required for PERMANENT_SESSION_LIFETIME to apply.
        # See /register for the full rationale.
        from flask import session as _session
        _session.permanent = True
        # Hotfix-4 T3: happy-path log for forensic depth. Pairs with the
        # implicit auth-failure path (Flask-Login redirect to /login) so
        # ops can see a "user X logged in at T" trail without needing
        # Sentry depth on every successful auth.
        app.logger.info(
            "[LOGIN-SUCCESS] user_id=%s email=%s", user.id, user.email,
        )
        return redirect(url_for("index"))

    return render_template("login.html")


@app.route("/verify/<token>")
@limiter.limit("10 per minute")
def verify_email(token):
    """One-use verification link. Tokens are 32-char uuid hex; expire 24h
    after registration. Used token is cleared so re-clicks fail (loud is
    better than silent — the user knows the link only works once)."""
    user = User.query.filter_by(email_verification_token=token).first()
    if not user:
        flash("Verification link is invalid or has already been used.", "error")
        return redirect(url_for("login"))
    if user.email_verification_token_expires and \
            user.email_verification_token_expires < datetime.utcnow():
        flash("Verification link has expired. Sign in to request a new one.", "error")
        return redirect(url_for("login"))
    user.email_verified = True
    user.email_verification_token = None
    user.email_verification_token_expires = None
    db.session.commit()
    flash("Email verified — you can now generate quotes.", "success")
    return redirect(url_for("index"))


@app.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("3 per hour", methods=["POST"])
def forgot_password():
    """
    Hotfix-3 T3: password reset request.

    On POST: ALWAYS flashes the same success message regardless of
    whether the email exists. This is the standard pattern to close
    the enumeration vector — an attacker can't probe which addresses
    are registered by watching for different responses.

    If the email DOES match a user, we issue a 1-hour reset token and
    email the link. If not, we silently do nothing (no DB write, no
    email send). The 1-hour window is tighter than the 24h verify
    expiry because reset links are higher-value and short windows
    limit the blast radius if the email gets forwarded.

    Rate-limited 3/hour/IP via Flask-Limiter to slow down enumeration
    attempts that try thousands of emails looking for response timing
    deltas.
    """
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        user = User.query.filter_by(email=email).first() if email else None
        if user:
            token = uuid.uuid4().hex
            user.password_reset_token = token
            user.password_reset_token_expires = datetime.utcnow() + timedelta(hours=1)
            db.session.commit()
            reset_url = url_for("reset_password", token=token, _external=True)
            app.logger.info(
                "[PASSWORD-RESET] issued for user_id=%s email=%s reset_url=%s",
                user.id, user.email, reset_url,
            )
            mailer.send_email(
                to=user.email,
                subject="Reset your Panefree Quotes password",
                html_body=render_template(
                    "email/reset.html",
                    reset_url=reset_url,
                    support_email=config.SUPPORT_EMAIL,
                ),
                text_body=render_template(
                    "email/reset.txt",
                    reset_url=reset_url,
                    support_email=config.SUPPORT_EMAIL,
                ),
            )
        else:
            # No-op for unknown emails. Log the attempt at INFO so abuse
            # patterns are visible (high volume of unknown-email resets
            # = enumeration probe), but DON'T differentiate the response.
            app.logger.info(
                "[PASSWORD-RESET] requested for unknown email=%r (no-op)",
                email,
            )

        # Same flash regardless of whether email existed.
        flash(
            "If that email is registered, we've sent a reset link. Check "
            "your inbox (and spam folder).",
            "success",
        )
        return redirect(url_for("login"))

    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def reset_password(token):
    """
    Hotfix-3 T3: password reset completion.

    Token validation: pulls the user by token, checks expiry. If either
    fails, the form 404s (rather than 400) — 404 vs 400 doesn't leak
    whether a specific token previously existed; the user just retries
    the /forgot-password flow.

    On successful POST: validates the new password against
    _password_strength_error, sets it via set_password (rotates the
    hash), clears the reset token, logs the user in, redirects to /.

    Rotating password_hash invalidates any existing Flask-Login session
    cookies on next request — sufficient session-invalidation for v1.
    Explicit server-side session storage is a Sprint 8+ candidate.
    """
    user = User.query.filter_by(password_reset_token=token).first()
    if not user:
        abort(404)
    if not user.password_reset_token_expires or \
            user.password_reset_token_expires < datetime.utcnow():
        # Expired tokens get the same 404 — don't differentiate between
        # "never existed" and "expired" via response code.
        abort(404)

    if request.method == "POST":
        password = request.form.get("password") or ""
        pw_error = _password_strength_error(password)
        if pw_error:
            flash(pw_error, "error")
            return render_template("reset_password.html")

        user.set_password(password)
        user.password_reset_token = None
        user.password_reset_token_expires = None
        # Reset clears the login-lockout counter (the user has proven
        # mailbox control, which is at least as strong as a successful
        # login for unlock purposes).
        user.failed_login_attempts = 0
        user.locked_until = None
        db.session.commit()

        app.logger.info(
            "[PASSWORD-RESET] completed for user_id=%s email=%s",
            user.id, user.email,
        )

        # Log them in immediately so they don't have to type the new
        # password they just chose.
        login_user(user)
        from flask import session as _session
        _session.permanent = True
        flash("Password updated. You're signed in.", "success")
        return redirect(url_for("index"))

    return render_template("reset_password.html")


@app.route("/resend-verification", methods=["POST"])
@login_required
@limiter.limit("3 per hour")
def resend_verification():
    """
    Hotfix-3 T2 (Inquisitor C1): logged-in-only resend of the verification
    email. No email parameter — the user must already be authenticated as
    the address they want re-verified. This closes the enumeration vector
    (an anonymous /resend?email=... would let an attacker probe which
    addresses are registered).

    No-op for already-verified users — they just get a redirect to /.
    Rate-limited 3/hour/IP via Flask-Limiter (Hotfix-2 T4).
    """
    user = db.session.get(User, current_user.id)
    if user.email_verified:
        flash("Your email is already verified.", "info")
        return redirect(url_for("index"))

    token = _issue_verification_token(user)
    sent = _send_verification_email(user, token)
    if sent:
        flash(
            "Verification email sent. Check your inbox (and spam folder) — "
            "the link expires in 24 hours.",
            "success",
        )
    else:
        flash(
            "We couldn't send the verification email just now. Try again "
            "in a few minutes, or contact support.",
            "error",
        )
    return redirect(url_for("index"))


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ---------- Core quoting ----------

@app.route("/")
@login_required
def index():
    registry, profiles = get_user_profile_registry(current_user)

    # BUG-003 (Sprint 4): zero-profile users get bounced to /profiles/new.
    # Pre-Sprint-4, signup auto-seeded a "starter" profile so the quote
    # form always had something to render. Since new users no longer get
    # any seeded profiles, the first profile creation IS the onboarding —
    # users land on the profile form before they can quote, with their own
    # rates rather than placeholder rates that would have led to bad first
    # quotes anyway. Existing users with profiles see no behavior change.
    if not profiles:
        flash(
            "Welcome — let's set up your first pricing profile. "
            "Once it's saved you'll be quoting in seconds.",
            "info",
        )
        return redirect(url_for("profile_new"))

    current_profile_data = registry["profiles"].get(registry["active_profile"], {})
    return render_template(
        "index.html",
        profiles=[p.name for p in profiles],
        profiles_data=registry["profiles"],
        active_profile=registry["active_profile"],
        current_profile_data=current_profile_data,
        credit_packs=config.CREDIT_PACKS,
    )


def _parse_quote_form():
    if request.is_json:
        return request.json

    panes = {
        "floor1": int(request.form.get("floor1", 0)),
        "floor2": int(request.form.get("floor2", 0)),
        "floor3": int(request.form.get("floor3", 0)),
    }
    addons = request.form.getlist("addon")
    profile_id = request.form.get("profile_id")

    overrides = {
        "floor1": request.form.get("override_floor1"),
        "floor2": request.form.get("override_floor2"),
        "floor3": request.form.get("override_floor3"),
    }
    overrides = {k: v for k, v in overrides.items() if v}

    addon_overrides = {}
    for addon in addons:
        override_key = f"override_addon_{addon.replace(' ', '_')}"
        val = request.form.get(override_key)
        if val:
            addon_overrides[addon] = val

    # Tax UI is a percentage (e.g. "8.5" for 8.5%). Convert to the decimal
    # the engine expects. A bare `tax_override` (raw decimal) is still accepted
    # as a fallback for non-browser callers.
    tax_override_decimal = request.form.get("tax_override")
    tax_pct = request.form.get("tax_override_percent")
    if tax_pct:
        try:
            tax_override_decimal = str(float(tax_pct) / 100.0)
        except ValueError:
            pass

    return {
        "panes": panes,
        "add_ons": addons,
        "profile_id": profile_id,
        "overrides": overrides,
        "addon_overrides": addon_overrides,
        "tax_override": tax_override_decimal,
        "callout_override": request.form.get("callout_override"),
        "label": request.form.get("label"),
        "customer_name": request.form.get("customer_name"),
        "customer_address": request.form.get("customer_address"),
        "customer_email": request.form.get("customer_email"),
        "customer_phone": request.form.get("customer_phone"),
    }


@app.route("/calculate", methods=["POST"])
@login_required
def calculate():
    data = _parse_quote_form()
    registry, profiles = get_user_profile_registry(current_user, preferred_name=data.get("profile_id"))
    if not data.get("profile_id"):
        data["profile_id"] = registry["active_profile"]

    registry = apply_callout_override(registry, data.get("profile_id"), data.get("callout_override"))

    try:
        snapshot = calculate_quote(data, registry)
        if not request.is_json:
            current_profile_data = registry["profiles"].get(registry["active_profile"], {})
            pane_count = sum(int(v) for v in snapshot["input"]["panes"].values())
            benchmark = compute_internal_benchmark(
                current_user,
                pane_count,
                snapshot["calculation"]["grand_total"],
            )
            return render_template(
                "index.html",
                result=snapshot,
                profiles=[p.name for p in profiles],
                profiles_data=registry["profiles"],
                active_profile=registry["active_profile"],
                current_profile_data=current_profile_data,
                credit_packs=config.CREDIT_PACKS,
                benchmark=benchmark,
                submitted_label=sanitize_label(data.get("label")),
                submitted_customer_name=_sanitize_storage(data.get("customer_name"), CUSTOMER_NAME_MAX),
                submitted_customer_address=_sanitize_storage(data.get("customer_address"), CUSTOMER_ADDR_MAX),
                submitted_customer_email=_sanitize_storage(data.get("customer_email"), CUSTOMER_EMAIL_MAX),
                submitted_customer_phone=_sanitize_storage(data.get("customer_phone"), CUSTOMER_PHONE_MAX),
            )
        return jsonify({"status": "success", "calculation": snapshot["calculation"]})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/generate", methods=["POST"])
@login_required
def generate():
    """
    Reserve -> Generate -> Refund on Failure (Heresy #1 fix).
    Active subscribers bypass the credit reserve entirely; past_due falls
    through to credits as a grace mechanism. Heresy #12 fix: subscription
    state is read off a fresh User load, never the cached current_user.
    """
    data = request.get_json(silent=True) or _parse_quote_form()
    registry, _ = get_user_profile_registry(current_user, preferred_name=data.get("profile_id"))
    if not data.get("profile_id"):
        data["profile_id"] = registry["active_profile"]
    registry = apply_callout_override(registry, data.get("profile_id"), data.get("callout_override"))

    # Heresy #12: never trust current_user.subscription_* — go through the
    # session. The reserve bypass keys off period_end (the timestamp Stripe
    # owns), not on status alone, so a stale "active" status with an
    # expired period_end correctly falls through to the credit path.
    user = db.session.get(User, current_user.id)
    now = datetime.utcnow()
    is_subscriber = (
        user.subscription_status == "active"
        and user.subscription_current_period_end is not None
        and user.subscription_current_period_end > now
    )

    # Email verification gate (T4). Subscribers are NOT exempt — otherwise
    # a stolen-card subscription is an abuse vector. Fires before rate
    # limit / reserve so unverified users don't burn either.
    if not user.email_verified:
        return jsonify({
            "status": "error",
            "code": "EMAIL_NOT_VERIFIED",
            "message": (
                "Verify your email address before generating quotes. "
                "Check the verification link from your registration email."
            ),
        }), 403

    if not is_subscriber:
        # Rolling 60-min rate limit (active subscribers exempt — they've
        # paid for unlimited and the bypass logic upstream skips this gate).
        # Past_due subscribers reach this path and ARE rate-limited, which
        # is intentional: an account in dunning shouldn't double as a quote
        # firehose.
        window_start = now - timedelta(hours=1)
        recent_count = Quote.query.filter(
            Quote.user_id == user.id,
            Quote.created_at >= window_start,
        ).count()
        if recent_count >= config.RATE_LIMIT_QUOTES_PER_HOUR:
            oldest = Quote.query.filter(
                Quote.user_id == user.id,
                Quote.created_at >= window_start,
            ).order_by(Quote.created_at.asc()).first().created_at
            notice = build_rate_limit_notice(
                recent_count, config.RATE_LIMIT_QUOTES_PER_HOUR, oldest, now,
            )
            return jsonify({"status": "error", **notice}), 429

    if is_subscriber:
        # Subscription bypass — no credit decrement, no commit needed.
        reserved = 1
    else:
        # Atomic reserve (past_due subscribers reach this path too).
        reserved = db.session.execute(
            text(
                "UPDATE users SET credit_balance = credit_balance - 1 "
                "WHERE id = :uid AND credit_balance > 0"
            ),
            {"uid": current_user.id},
        ).rowcount
        db.session.commit()

    if reserved == 0:
        return jsonify({
            "status": "error",
            "code": "NO_CREDITS",
            "message": (
                "You've used all your free credits. Buy more (from $8.99) "
                "or subscribe to Annual Unlimited for unlimited quotes."
            ),
            "redirect": url_for("top_up"),
        }), 402

    try:
        snapshot = calculate_quote(data, registry)
        # `/generate` only ever produces a QUOTE. Invoice rendering is a
        # separate, free, ownership-checked path (Heresy #7): it consumes a
        # stored Quote row rather than fresh form data, so users can't
        # launder unlimited free PDFs through this endpoint by setting
        # ?type=INVOICE.
        doc_type = "QUOTE"
        filename = f"{doc_type.lower()}_{uuid.uuid4().hex[:6]}.pdf"
        output_path = os.path.join(_user_pdf_dir(current_user.id), filename)
        label = sanitize_label(data.get("label"))
        customer_name = _sanitize_storage(data.get("customer_name"), CUSTOMER_NAME_MAX)
        customer_address = _sanitize_storage(data.get("customer_address"), CUSTOMER_ADDR_MAX)
        customer_email = _sanitize_storage(data.get("customer_email"), CUSTOMER_EMAIL_MAX)
        customer_phone = _sanitize_storage(data.get("customer_phone"), CUSTOMER_PHONE_MAX)
        pane_count = sum(int(v) for v in snapshot["input"]["panes"].values())

        # Insert the Quote row up-front so we have an autoincrement id to
        # derive a stable doc_code from. `flush()` assigns the id without
        # committing — if PDF rendering fails below, rollback undoes this
        # insert in lockstep with the credit refund (Heresy #1 symmetry).
        quote = Quote(
            user_id=current_user.id,
            label=label,
            final_price=Decimal(str(snapshot["calculation"]["grand_total"])),
            pane_count=pane_count,
            quote_data=_serialize_for_json(snapshot),
            customer_name=customer_name or None,
            customer_address=customer_address or None,
            customer_email=customer_email or None,
            customer_phone=customer_phone or None,
        )
        db.session.add(quote)
        db.session.flush()

        # BUG-007 (Sprint 4): claim the sequential Q-NNNNNN before render.
        # Pattern mirrors the existing invoice claim — atomic UPDATE on
        # User.next_quote_number, snapshot prefix onto Quote.quote_prefix.
        # Done after the flush so quote.id exists; done before render so the
        # PDF carries the number on the first emit (no follow-up commits).
        q_num, q_prefix = _claim_quote_number(quote)

        generate_document(
            snapshot,
            doc_type=doc_type,
            output_path=output_path,
            business_name=current_user.business_name,
            phone_number=current_user.phone_number,
            label=label,
            doc_code=derive_doc_code(quote.id),
            quote_number=q_num,
            quote_prefix=q_prefix,
            quote_footer=render_footer_template(
                current_user.quote_footer_text, "QUOTE", current_user.phone_number,
            ),
            invoice_footer=render_footer_template(
                current_user.invoice_footer_text, "INVOICE", current_user.phone_number,
            ),
            customer_name=customer_name,
            customer_address=customer_address,
            customer_email=customer_email,
            customer_phone=customer_phone,
        )
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        if not is_subscriber:
            # Symmetric refund. Subscribers had nothing reserved, so skip.
            #
            # Hotfix-1 T5 (OBS-002): wrap the refund itself in try/except so
            # a failure here (DB lock, connection drop, disk full mid-commit,
            # whatever) doesn't propagate up and 500 the caller. The user
            # already paid the cost of a failed quote — they should not also
            # eat a 500. The quote rollback above succeeded; the worst case
            # if the refund silently fails is one missing credit, which is
            # recoverable manually from the transactions table.
            #
            # Retry strategy: deliberately none. A single retry inside the
            # request would block the response on the same flake; a queued
            # retry is over-engineered for a credit count. We log loudly so
            # ops can spot a pattern and credit-back from the audit trail.
            try:
                db.session.execute(
                    text(
                        "UPDATE users SET credit_balance = credit_balance + 1 "
                        "WHERE id = :uid"
                    ),
                    {"uid": current_user.id},
                )
                db.session.commit()
            except Exception as refund_err:
                db.session.rollback()
                app.logger.error(
                    "[CREDIT-REFUND-FAILED] user_id=%s after /generate failure: "
                    "original_error=%r refund_error=%r — credit may be lost; "
                    "manual reconciliation required.",
                    current_user.id, str(e), str(refund_err),
                )
                # Hotfix-3 T5: also email admin same-day so the manual
                # reconciliation actually happens rather than waiting on
                # someone tailing the log. Best-effort — failure here is
                # logged via mailer's own [EMAIL-SEND-FAILED] tag but
                # MUST NOT raise (we're already in an exception handler
                # for the refund failure).
                _notify_admin(
                    alert_tag="CREDIT-REFUND-FAILED",
                    subject_summary=f"Manual reconcile needed for user {current_user.id}",
                    body_markdown=(
                        f"User_id: {current_user.id}\n"
                        f"Email: {current_user.email}\n"
                        f"\n"
                        f"The /generate path failed AND the credit refund\n"
                        f"path also failed. The user has been charged a\n"
                        f"credit for a quote they did not receive.\n"
                        f"\n"
                        f"Original error: {e!r}\n"
                        f"Refund error:   {refund_err!r}\n"
                        f"\n"
                        f"Action: manually +1 credit_balance on user_id\n"
                        f"  {current_user.id} via sqlite3 / admin tooling.\n"
                    ),
                )
        return jsonify({"status": "error", "message": str(e)}), 400

    response = {
        "status": "success",
        "file": filename,
        "download_url": url_for("download", filename=filename),
        "credits_remaining": current_user.credit_balance,
        "quote_id": quote.id,
        "invoice_url": url_for("quote_render_pdf", quote_id=quote.id, type="INVOICE"),
    }

    if is_subscriber:
        # Soft-cap notice: informational only, does not block. period_start
        # is approximated as period_end - 365d since we don't store it
        # separately (annual sub — drift of leap seconds is irrelevant for
        # an informational threshold). Counts the just-created quote.
        period_start = user.subscription_current_period_end - timedelta(days=365)
        quote_count = Quote.query.filter(
            Quote.user_id == user.id,
            Quote.created_at >= period_start,
        ).count()
        # Two tiers (Sprint 4 T1):
        #   80%-99%  -> soft_cap_warning   (heads-up, no CTA)
        #   >=100%   -> soft_cap_notice    (full CTA pointing at /contact)
        # Mutually exclusive by construction (build_soft_cap_warning returns
        # None at >= threshold), but checking warning first means a single
        # response never carries both.
        warning = build_soft_cap_warning(quote_count, config.SOFT_CAP_THRESHOLD)
        if warning:
            response["soft_cap_warning"] = warning
        else:
            notice = build_soft_cap_notice(
                quote_count, config.SOFT_CAP_THRESHOLD, url_for("contact"),
            )
            if notice:
                response["soft_cap_notice"] = notice

    return jsonify(response)


@app.route("/download/<filename>")
@login_required
def download(filename):
    """
    Serve a generated PDF from the caller's per-user bucket.

    BUG-008 fix (Sprint 4): pre-fix, this route served any file in
    project_root by name — `sovereign.db`, source files, anything. The
    fix pins lookups to <OUTPUT_DIR>/<current_user.id>/<basename>:

      - basename() strips path traversal (`..`, leading slash)
      - the user_id comes from the session, not the URL, so a leaked
        filename from user A is unreachable when user B is logged in
      - the bucket directory only ever contains PDFs this user generated,
        so even an exact filename match can't escape sandbox

    404 (not 403) on miss — don't leak whether the filename exists for
    another user.
    """
    safe_name = os.path.basename(filename)
    full_path = os.path.join(_user_pdf_dir(current_user.id), safe_name)
    if not os.path.isfile(full_path):
        abort(404)
    return send_file(full_path, as_attachment=True)


# ---------- Profile CRUD ----------

@app.route("/profiles")
@login_required
def profiles_list():
    profiles = PricingProfile.query.filter_by(user_id=current_user.id).order_by(PricingProfile.id).all()
    return render_template("profiles.html", profiles=profiles)


@app.route("/profiles/new", methods=["GET", "POST"])
@login_required
def profile_new():
    if request.method == "POST":
        form = request.form
        # Hotfix-1 T4: cap profile name at the label tier so a multi-MB
        # name can't bloat the pricing_profiles table.
        name = _sanitize_storage(form.get("name"), PROFILE_NAME_MAX)

        def render_form_with_error(msg):
            flash(msg, "error")
            return render_template("profile_new.html", form=form)

        if not name:
            return render_form_with_error("Profile name is required.")

        if PricingProfile.query.filter_by(user_id=current_user.id, name=name).first():
            return render_form_with_error(f"A profile named '{name}' already exists.")

        try:
            price_data = {
                "base_pane_rate": float(form["base_rate"]),
                "base_callout_fee": float(form["callout"]),
                "tax_rate": float(form["tax"]) / 100.0,
                "story_surcharges": {
                    "floor1": float(form["floor1_mult"]),
                    "floor2": float(form["floor2_mult"]),
                    "floor3": float(form["floor3_mult"]),
                },
                "add_on_rates": {
                    "Screen Cleaning": float(form["screen_rate"]),
                    "Track Cleaning": float(form["track_rate"]),
                    "Hard Water Treatment": float(form["hardwater_rate"]),
                },
            }
        except (KeyError, ValueError):
            return render_form_with_error("All numeric fields must be valid numbers.")

        try:
            calculate_quote(
                {"panes": {"floor1": 1}, "add_ons": [], "profile_id": "_probe_",
                 "overrides": {}, "addon_overrides": {}, "tax_override": None},
                {"profiles": {"_probe_": price_data}},
            )
        except Exception as e:
            return render_form_with_error(f"Profile failed validation: {e}")

        p = PricingProfile(
            user_id=current_user.id,
            name=name,
            price_data=price_data,
            is_default=False,
        )
        db.session.add(p)
        db.session.commit()

        if form.get("make_default"):
            set_default_profile(current_user, p.id)

        flash(f"Profile '{name}' created.", "success")
        return redirect(url_for("profiles_list"))

    return render_template("profile_new.html", form={})


@app.route("/api/profiles/create", methods=["POST"])
@login_required
def api_profile_create():
    """JSON endpoint for inline profile creation from the quote form."""
    data = request.get_json(silent=True) or {}
    # Hotfix-1 T4: cap as on the HTML route — same tier, same rationale.
    name = _sanitize_storage(data.get("name"), PROFILE_NAME_MAX)
    price_data = data.get("price_data")
    make_default = bool(data.get("make_default"))

    if not name:
        return jsonify({"status": "error", "message": "Name is required."}), 400
    if not isinstance(price_data, dict):
        return jsonify({"status": "error", "message": "price_data must be an object."}), 400

    # Block duplicate names for this user
    if PricingProfile.query.filter_by(user_id=current_user.id, name=name).first():
        return jsonify({"status": "error", "message": f"A profile named '{name}' already exists."}), 400

    # Validate shape by running a dry calc
    try:
        calculate_quote(
            {"panes": {"floor1": 1}, "add_ons": [], "profile_id": "_probe_",
             "overrides": {}, "addon_overrides": {}, "tax_override": None},
            {"profiles": {"_probe_": price_data}},
        )
    except Exception as e:
        return jsonify({"status": "error", "message": f"Validation failed: {e}"}), 400

    p = PricingProfile(
        user_id=current_user.id,
        name=name,
        price_data=price_data,
        is_default=False,
    )
    db.session.add(p)
    db.session.commit()

    if make_default:
        set_default_profile(current_user, p.id)

    return jsonify({
        "status": "success",
        "profile": {"id": p.id, "name": p.name, "is_default": make_default},
    })


@app.route("/profiles/<int:profile_id>/default", methods=["POST"])
@login_required
def profile_set_default(profile_id):
    p = PricingProfile.query.filter_by(id=profile_id, user_id=current_user.id).first()
    if not p:
        abort(404)
    set_default_profile(current_user, profile_id)
    flash(f"Default profile set to '{p.name}'.", "success")
    return redirect(url_for("profiles_list"))


@app.route("/profiles/<int:profile_id>/delete", methods=["POST"])
@login_required
def profile_delete(profile_id):
    p = PricingProfile.query.filter_by(id=profile_id, user_id=current_user.id).first()
    if not p:
        abort(404)
    if p.is_default:
        flash("Cannot delete the default profile. Set another default first.", "error")
        return redirect(url_for("profiles_list"))
    db.session.delete(p)
    db.session.commit()
    flash(f"Profile '{p.name}' deleted.", "success")
    return redirect(url_for("profiles_list"))


# ---------- Quote history + invoice conversion ----------

@app.route("/history")
@login_required
def history():
    quotes = (
        Quote.query
        .filter_by(user_id=current_user.id)
        .order_by(Quote.created_at.desc())
        .limit(50)
        .all()
    )
    return render_template("history.html", quotes=quotes)


@app.route("/quotes/<int:quote_id>/pdf", methods=["POST"])
@login_required
def quote_render_pdf(quote_id):
    """
    Re-render a stored quote as either a QUOTE or INVOICE PDF.
    FREE — no credit charged. The credit was paid at /generate time
    and the stored snapshot is immutable, so this is just a view.

    Ownership is enforced (Heresy #8): the filter pins the row to the
    current user, making cross-tenant regen impossible.
    """
    q = Quote.query.filter_by(id=quote_id, user_id=current_user.id).first()
    if not q:
        abort(404)

    doc_type = (request.args.get("type") or request.form.get("type") or "QUOTE").upper()
    if doc_type not in ("QUOTE", "INVOICE"):
        doc_type = "QUOTE"

    snapshot = load_quote_snapshot(q)
    filename = f"{doc_type.lower()}_{uuid.uuid4().hex[:6]}.pdf"
    output_path = os.path.join(_user_pdf_dir(current_user.id), filename)

    # Sequential number for INVOICE only (Feature 2). QUOTE keeps the
    # opaque hash from derive_doc_code — quotes aren't legally binding,
    # so we don't burn a number on them, and the hash avoids leaking the
    # user's quote count. The claim is idempotent: re-rendering the same
    # quote-as-invoice always shows the same INV-NNNNNN.
    invoice_num = _claim_invoice_number(q) if doc_type == "INVOICE" else None

    try:
        generate_document(
            snapshot,
            doc_type=doc_type,
            output_path=output_path,
            business_name=current_user.business_name,
            phone_number=current_user.phone_number,
            label=q.label,
            doc_code=derive_doc_code(q.id),
            invoice_number=invoice_num,
            # Snapshotted prefix from claim time (Feature 3). For QUOTE
            # renders this is None and the generator ignores it. For
            # legacy invoices issued before Feature 3, q.invoice_prefix
            # is null and the generator falls back to INVOICE_PREFIX_DEFAULT.
            invoice_prefix=q.invoice_prefix,
            # BUG-007 (Sprint 4): pass the snapshotted quote number so
            # QUOTE re-renders show the same Q-NNNNNN they had on first
            # emit. Pre-Sprint-4 quotes have q.quote_number=None and the
            # generator falls back to the legacy doc_code hash for them.
            quote_number=q.quote_number,
            quote_prefix=q.quote_prefix,
            quote_footer=render_footer_template(
                current_user.quote_footer_text, "QUOTE", current_user.phone_number,
            ),
            invoice_footer=render_footer_template(
                current_user.invoice_footer_text, "INVOICE", current_user.phone_number,
            ),
            customer_name=q.customer_name,
            customer_address=q.customer_address,
            customer_email=q.customer_email,
            customer_phone=q.customer_phone,
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

    if request.is_json or request.headers.get("Accept") == "application/json":
        return jsonify({
            "status": "success",
            "file": filename,
            "download_url": url_for("download", filename=filename),
            "doc_type": doc_type,
        })
    return redirect(url_for("download", filename=filename))


# ---------- JSON API ----------

@app.route("/api/credits")
@login_required
def api_credits():
    return jsonify({
        "credit_balance": current_user.credit_balance,
    })


# ---------- Stripe ----------

@app.route("/top-up")
@login_required
def top_up():
    simulator_active = config.DEV_MODE and not config.STRIPE_SECRET_KEY
    return render_template(
        "top_up.html",
        credit_packs=config.CREDIT_PACKS,
        annual=config.ANNUAL_SUBSCRIPTION,
        soft_cap=config.SOFT_CAP_THRESHOLD,
        publishable_key=config.STRIPE_PUBLISHABLE_KEY,
        simulator_active=simulator_active,
    )


_APP_BOOT_TIME = time.monotonic()
_APP_VERSION = _read_version_sha()


@app.route("/health")
@csrf.exempt
@limiter.exempt
def health():
    """
    Hotfix-4 T2: lightweight health endpoint for external uptime monitors
    (UptimeRobot, etc.) and orchestrator readiness probes.

    Returns JSON:
      {"status": "ok",        "db": "ok",   "version": "<sha>", "uptime_s": N}   # 200
      {"status": "degraded",  "db": "fail", "version": "<sha>", "uptime_s": N}   # 503

    Intentionally does NOT touch Stripe / Postmark / Sentry — those are
    external dependencies whose failures aren't application failures. The
    page can still render and most user flows still work even if Stripe
    is having an incident. UptimeRobot watches the app's own health;
    Sentry's own dashboard / status page is the source for SaaS health.

    No auth, no CSRF, no rate limit — the orchestrator and UptimeRobot
    both need to hit this on every probe cycle without state. Talisman's
    default response headers still apply.

    DB check is a `SELECT 1`. Sub-50ms p95 in normal conditions.
    """
    db_ok = True
    try:
        db.session.execute(text("SELECT 1")).scalar()
    except Exception:
        db_ok = False

    uptime_s = int(time.monotonic() - _APP_BOOT_TIME)
    payload = {
        "status": "ok" if db_ok else "degraded",
        "db": "ok" if db_ok else "fail",
        "version": _APP_VERSION,
        "uptime_s": uptime_s,
    }
    status_code = 200 if db_ok else 503
    return jsonify(payload), status_code


@app.route("/dev/sentry-test")
def dev_sentry_test():
    """
    Hotfix-4 T1: deliberate exception trigger to verify the Sentry
    integration is live. Hard-gated identically to /dev/grant-credits:
    404s unless DEV_MODE is set AND Stripe is NOT configured. Production
    with real Stripe keys cannot expose this route even if DEV_MODE leaks.

    Returns nothing useful — the side effect is the Sentry event. Verify
    by hitting this URL while DEV_MODE=1 and SENTRY_DSN points at a real
    project; the error should appear in the dashboard within ~60s.
    """
    if not config.DEV_MODE or config.STRIPE_SECRET_KEY:
        abort(404)
    raise RuntimeError("sentry test — deliberate exception (Hotfix-4 T1)")


@app.route("/dev/grant-credits", methods=["POST"])
@login_required
def dev_grant_credits():
    """
    Dev-only simulator. Mirrors the webhook's credit-grant logic so the full
    buy-button-to-credit-badge flow is clickable without Stripe.

    Hard-gated: 404s unless DEV_MODE is explicitly set AND Stripe is NOT configured.
    This means a production deployment with real Stripe keys cannot expose this
    route even if DEV_MODE leaks into its environment.
    """
    if not config.DEV_MODE or config.STRIPE_SECRET_KEY:
        abort(404)

    pack_id = request.form.get("pack")
    pack = config.CREDIT_PACKS.get(pack_id)
    if not pack:
        flash("Unknown pack.", "error")
        return redirect(url_for("top_up"))

    credits = pack["credits"]
    fake_session_id = f"dev_sim_{uuid.uuid4().hex}"

    tx = Transaction(
        user_id=current_user.id,
        amount=Decimal(pack["price_cents"]) / Decimal(100),
        credits_added=credits,
        stripe_tx_id=fake_session_id,
    )
    db.session.add(tx)
    db.session.execute(
        text("UPDATE users SET credit_balance = credit_balance + :n WHERE id = :uid"),
        {"n": credits, "uid": current_user.id},
    )
    db.session.commit()

    flash(
        f"[DEV] Simulated purchase: {credits} credits added "
        f"(${pack['price_cents']/100:.0f} — no real charge).",
        "success",
    )
    return redirect(url_for("top_up"))


@app.route("/checkout", methods=["POST"])
@login_required
@limiter.limit("10 per minute")
def checkout():
    if not config.STRIPE_SECRET_KEY:
        return jsonify({"status": "error", "message": "Stripe is not configured on this server."}), 503

    pack_id = request.form.get("pack") or request.json.get("pack")

    if pack_id == "annual":
        annual = config.ANNUAL_SUBSCRIPTION
        try:
            session = stripe.checkout.Session.create(
                mode="subscription",
                payment_method_types=["card"],
                client_reference_id=str(current_user.id),
                metadata={"user_id": str(current_user.id), "product": "annual"},
                # subscription_data.metadata is what the later
                # customer.subscription.* and invoice.* events carry.
                # Top-level checkout metadata does NOT propagate to those
                # objects, so duplicate the user_id here for race recovery.
                subscription_data={
                    "metadata": {"user_id": str(current_user.id), "product": "annual"},
                },
                line_items=[{
                    "quantity": 1,
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": annual["price_cents"],
                        "recurring": {"interval": annual["interval"]},
                        "product_data": {"name": annual["name"]},
                    },
                }],
                success_url=f"{config.APP_BASE_URL}/checkout/success?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{config.APP_BASE_URL}/top-up",
            )
            return redirect(session.url, code=303)
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    pack = config.CREDIT_PACKS.get(pack_id)
    if not pack:
        return jsonify({"status": "error", "message": "Unknown credit pack."}), 400

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            client_reference_id=str(current_user.id),
            metadata={"user_id": str(current_user.id), "pack_id": pack_id, "credits": str(pack["credits"])},
            line_items=[{
                "quantity": 1,
                "price_data": {
                    "currency": "usd",
                    "unit_amount": pack["price_cents"],
                    "product_data": {"name": f"{pack['name']} — {pack['credits']} quote credits"},
                },
            }],
            success_url=f"{config.APP_BASE_URL}/checkout/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{config.APP_BASE_URL}/top-up",
        )
        return redirect(session.url, code=303)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/checkout/success")
@login_required
def checkout_success():
    flash("Payment received — credits will appear once Stripe confirms the charge.", "success")
    return redirect(url_for("index"))


@app.route("/account/billing-portal", methods=["POST"])
@login_required
def billing_portal():
    """
    Hands the subscriber off to Stripe's hosted Billing Portal — payment
    method updates, cancel-at-period-end, and invoice history live there
    rather than being reimplemented locally. Customer ID is resolved by
    fetching the subscription (we don't store it as its own column).
    """
    if not config.STRIPE_SECRET_KEY:
        flash("Stripe is not configured on this server.", "error")
        return redirect(url_for("account"))
    user = db.session.get(User, current_user.id)
    if not user.subscription_id:
        flash("No active subscription on file.", "error")
        return redirect(url_for("account"))
    try:
        sub = stripe.Subscription.retrieve(user.subscription_id)
        portal = stripe.billing_portal.Session.create(
            customer=sub["customer"],
            return_url=f"{config.APP_BASE_URL}/account",
        )
        return redirect(portal.url, code=303)
    except Exception as e:
        flash(f"Could not open billing portal: {e}", "error")
        return redirect(url_for("account"))


# ---------- Custom-plan intake (soft-cap CTA target) ----------

@app.route("/contact", methods=["GET", "POST"])
@login_required
@limiter.limit("5 per minute", methods=["POST"])
def contact():
    """
    Custom-plan intake form. Linked from the soft-cap CTA in /generate
    responses. Persists to ContactSubmission and logs a notification line —
    no email backend yet (deferred per Sprint 3 scope).
    """
    if request.method == "POST":
        # Hotfix-1 T4: cap each field at its tier (label/short/notes/email).
        # Truncation is silent — the form has no per-field hint, so silently
        # storing the first N chars beats rejecting outright and losing the
        # rest of the submission.
        company_name = _sanitize_storage(request.form.get("company_name"), CONTACT_COMPANY_MAX)
        current_volume = _sanitize_storage(request.form.get("current_volume"), CONTACT_VOLUME_MAX)
        expected_growth = _sanitize_storage(request.form.get("expected_growth"), CONTACT_GROWTH_MAX)
        email = _sanitize_storage(request.form.get("email"), CONTACT_EMAIL_MAX).lower()

        # Field-by-field required check so the error names what's missing.
        missing = [name for name, v in [
            ("Company name", company_name),
            ("Current quote volume", current_volume),
            ("Expected growth", expected_growth),
            ("Email", email),
        ] if not v]
        if missing:
            flash(f"Required: {', '.join(missing)}.", "error")
            return render_template(
                "contact.html",
                company_name=company_name, current_volume=current_volume,
                expected_growth=expected_growth, email=email,
            )

        # Minimal email shape check — full validation lives in Stripe/SES later.
        if "@" not in email or "." not in email.split("@", 1)[-1]:
            flash("Please provide a valid email address.", "error")
            return render_template(
                "contact.html",
                company_name=company_name, current_volume=current_volume,
                expected_growth=expected_growth, email=email,
            )

        sub = ContactSubmission(
            user_id=current_user.id,
            company_name=company_name,
            current_volume=current_volume,
            expected_growth=expected_growth,
            email=email,
        )
        db.session.add(sub)
        db.session.commit()

        # Hotfix-3 T5: admin notification via Postmark. Log line is still
        # emitted as forensic backup — the email gives the operator
        # same-day awareness so high-volume inquiries don't sit unread.
        app.logger.info(
            "[CONTACT-SUBMISSION] from user_id=%s (%s): company=%r, "
            "volume=%r, growth=%r, contact_email=%r",
            current_user.id, current_user.email,
            company_name, current_volume, expected_growth, email,
        )
        _notify_admin(
            alert_tag="CONTACT-SUBMISSION",
            subject_summary=f"Custom plan inquiry from {company_name}",
            body_markdown=(
                f"From user_id: {current_user.id}\n"
                f"Account email: {current_user.email}\n"
                f"Reply-to email: {email}\n"
                f"\n"
                f"Company: {company_name}\n"
                f"Current volume: {current_volume}\n"
                f"Expected growth: {expected_growth}\n"
                f"\n"
                f"Submitted at: {datetime.utcnow().isoformat()}Z\n"
            ),
        )

        flash("Thanks — we'll be in touch shortly about your custom plan.", "success")
        return redirect(url_for("contact"))

    return render_template("contact.html")


def _handle_payment_checkout(session_obj):
    """
    Credit-pack checkout completed. Inserts a Transaction row and bumps
    credit_balance. Idempotent via UNIQUE(stripe_tx_id) on Transaction.
    """
    session_id = session_obj["id"]
    user_id = session_obj.get("client_reference_id") or (session_obj.get("metadata") or {}).get("user_id")
    credits_str = (session_obj.get("metadata") or {}).get("credits", "0")
    amount_total = session_obj.get("amount_total", 0) or 0

    try:
        user_id_int = int(user_id)
        credits = int(credits_str)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Missing user_id or credits metadata."}), 400

    user = db.session.get(User, user_id_int)
    if not user:
        return jsonify({"status": "error", "message": "Unknown user."}), 404

    tx = Transaction(
        user_id=user.id,
        amount=Decimal(amount_total) / Decimal(100),
        credits_added=credits,
        stripe_tx_id=session_id,
    )
    db.session.add(tx)
    try:
        db.session.execute(
            text("UPDATE users SET credit_balance = credit_balance + :n WHERE id = :uid"),
            {"n": credits, "uid": user.id},
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        # Duplicate webhook delivery — already credited. Safe to ack.
        return jsonify({"status": "ok", "duplicate": True}), 200

    return jsonify({"status": "ok", "credits_added": credits}), 200


def _resolve_user_from_subscription(sub_id):
    """
    Look up the User linked to a Stripe subscription. Falls back to the
    subscription's metadata.user_id if subscription_id isn't yet stored
    on a User row — this heals races where invoice.payment_succeeded
    arrives before checkout.session.completed has bound the sub to the
    user. When the metadata path resolves the user, we also write
    subscription_id back so subsequent events take the fast path.
    """
    user = User.query.filter_by(subscription_id=sub_id).first()
    if user:
        return user
    try:
        sub = stripe.Subscription.retrieve(sub_id)
    except Exception:
        return None
    user_id = (sub.get("metadata") or {}).get("user_id")
    if not user_id:
        return None
    try:
        user = db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None
    if user and not user.subscription_id:
        # Self-heal the link so subsequent events resolve via the index.
        user.subscription_id = sub_id
    return user


def _handle_subscription_checkout(session_obj):
    """
    Subscription checkout completed. Marks the user active, records the
    Stripe subscription ID, and stores current_period_end (fetched from
    Stripe — the checkout session payload doesn't include it). The first
    invoice.payment_succeeded fires separately and records the Transaction.
    """
    user_id = session_obj.get("client_reference_id") or (session_obj.get("metadata") or {}).get("user_id")
    sub_id = session_obj.get("subscription")
    if not user_id or not sub_id:
        return jsonify({"status": "error", "message": "Missing user_id or subscription on session."}), 400
    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Bad user_id metadata."}), 400
    user = db.session.get(User, user_id_int)
    if not user:
        return jsonify({"status": "error", "message": "Unknown user."}), 404

    try:
        sub = stripe.Subscription.retrieve(sub_id)
    except Exception as e:
        # Stripe API hiccup — return 5xx so Stripe retries. We must have
        # period_end before flipping status to active, otherwise the
        # reserve bypass (period_end > utcnow) would silently fail open.
        return jsonify({"status": "error", "message": f"Subscription fetch failed: {e}"}), 503

    period_end = datetime.utcfromtimestamp(sub["current_period_end"])
    user.subscription_status = "active"
    user.subscription_id = sub_id
    user.subscription_current_period_end = period_end
    try:
        db.session.commit()
    except IntegrityError:
        # Another User already linked to this subscription_id — should not
        # happen in normal flow, but UNIQUE catches it. Ack to stop retries.
        db.session.rollback()
        return jsonify({"status": "ok", "duplicate": True}), 200
    return jsonify({"status": "ok", "subscription": "active"}), 200


def _handle_subscription_updated(sub):
    """
    Subscription state transitions. Idempotent — same event delivered N
    times produces the same final row state. Cancel-at-period-end is
    surfaced through the cancel_at_period_end flag: status stays "active",
    the user keeps unlimited access through period_end, but the UI swaps
    "Renews on" for "Cancels on". The eventual sub.deleted event flips
    status to "canceled" and clears the flag when the period elapses.
    """
    user = User.query.filter_by(subscription_id=sub["id"]).first()
    if not user:
        return jsonify({"status": "ignored", "reason": "no matching user"}), 200

    status = sub.get("status")
    if status in ("active", "trialing"):
        user.subscription_status = "active"
    elif status in ("past_due", "unpaid"):
        user.subscription_status = "past_due"
    elif status == "canceled":
        user.subscription_status = "canceled"
    # Anything else (incomplete, incomplete_expired) leaves status unchanged —
    # those represent failed initial setup, not transitions of an active sub.

    # Track the pending-cancel signal. Stripe sends `cancel_at_period_end`
    # as a Boolean on every sub.updated; a user can also undo a scheduled
    # cancel via the Billing Portal, which arrives as the same event with
    # the flag flipped back to False — so we mirror it unconditionally.
    user.cancel_at_period_end = bool(sub.get("cancel_at_period_end"))

    period_end = sub.get("current_period_end")
    if period_end:
        user.subscription_current_period_end = datetime.utcfromtimestamp(period_end)
    db.session.commit()
    return jsonify({"status": "ok"}), 200


def _handle_subscription_deleted(sub):
    """
    Subscription terminated. period_end is intentionally NOT touched —
    a canceled-but-paid user keeps unlimited access through the billing
    period they already paid for (cancel-at-period-end pattern). The
    cancel_at_period_end flag resets to False here so a future re-subscribe
    starts cleanly in the renewing state.
    """
    user = User.query.filter_by(subscription_id=sub["id"]).first()
    if not user:
        return jsonify({"status": "ignored", "reason": "no matching user"}), 200
    user.subscription_status = "canceled"
    user.cancel_at_period_end = False
    db.session.commit()
    return jsonify({"status": "ok"}), 200


def _handle_invoice_paid(invoice):
    """
    Subscription invoice paid (initial OR renewal). Extends period_end
    and inserts a Transaction with the invoice ID as the dedup key —
    Heresy #13: replayed renewal webhooks must not create duplicate
    Transaction rows. Same UNIQUE(stripe_tx_id) guard as credit packs.
    """
    sub_id = invoice.get("subscription")
    if not sub_id:
        # One-off invoices are not tied to a subscription; ignore.
        return jsonify({"status": "ignored", "reason": "non-subscription invoice"}), 200
    user = _resolve_user_from_subscription(sub_id)
    if not user:
        return jsonify({"status": "ignored", "reason": "no matching user"}), 200

    invoice_id = invoice["id"]
    amount_paid = invoice.get("amount_paid", 0) or 0

    try:
        sub = stripe.Subscription.retrieve(sub_id)
    except Exception as e:
        return jsonify({"status": "error", "message": f"Subscription fetch failed: {e}"}), 503
    new_period_end = datetime.utcfromtimestamp(sub["current_period_end"])

    tx = Transaction(
        user_id=user.id,
        amount=Decimal(amount_paid) / Decimal(100),
        credits_added=0,  # Subscriptions grant no credits — bypass is via period_end.
        stripe_tx_id=invoice_id,
    )
    db.session.add(tx)
    try:
        user.subscription_status = "active"
        user.subscription_current_period_end = new_period_end
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        # Duplicate invoice — already processed. Ack stops Stripe retries.
        return jsonify({"status": "ok", "duplicate": True}), 200
    return jsonify({"status": "ok", "renewed_through": new_period_end.isoformat()}), 200


def _handle_invoice_failed(invoice):
    """
    Subscription invoice failed (declined card, etc.). Marks past_due —
    the reserve bypass falls through to the credit reserve, giving users
    a grace mechanism: they can spend credits while the dunning flow runs.
    """
    sub_id = invoice.get("subscription")
    if not sub_id:
        return jsonify({"status": "ignored", "reason": "non-subscription invoice"}), 200
    user = User.query.filter_by(subscription_id=sub_id).first()
    if not user:
        return jsonify({"status": "ignored", "reason": "no matching user"}), 200
    user.subscription_status = "past_due"
    db.session.commit()
    return jsonify({"status": "ok"}), 200


@app.route("/webhook/stripe", methods=["POST"])
@csrf.exempt
def stripe_webhook():
    """
    Signature-verified, idempotent fan-out. Handles credit-pack purchases,
    annual subscription signups, renewals, status changes, and failures.
    Each handler is idempotent on its own; the dispatcher just routes.
    """
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature", "")

    if not config.STRIPE_WEBHOOK_SECRET:
        return jsonify({"status": "error", "message": "Webhook secret not configured."}), 503

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, config.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        return jsonify({"status": "error", "message": str(e)}), 400

    event_type = event["type"]
    event_obj = event["data"]["object"]

    # Hotfix-4 T3: log every signature-verified webhook event we receive.
    # Pairs with the [STRIPE-CANCEL-FAILED] / Transaction-dedup paths to
    # give ops a full audit trail of "what Stripe told us." event_id
    # included so we can match against Stripe Dashboard's event log.
    app.logger.info(
        "[STRIPE-WEBHOOK] type=%s event_id=%s",
        event_type, event.get("id"),
    )

    if event_type == "checkout.session.completed":
        if event_obj.get("mode") == "subscription":
            return _handle_subscription_checkout(event_obj)
        return _handle_payment_checkout(event_obj)
    if event_type == "customer.subscription.updated":
        return _handle_subscription_updated(event_obj)
    if event_type == "customer.subscription.deleted":
        return _handle_subscription_deleted(event_obj)
    if event_type == "invoice.payment_succeeded":
        return _handle_invoice_paid(event_obj)
    if event_type == "invoice.payment_failed":
        return _handle_invoice_failed(event_obj)

    return jsonify({"status": "ignored", "type": event_type}), 200


# ---------- Account settings (business name, phone) ----------

@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    if request.method == "POST":
        # Validate the invoice prefix BEFORE touching anything else: if
        # it's malformed we abort the whole save so the user doesn't get
        # a half-applied update where some fields landed and the prefix
        # silently rejected. Empty string is valid (renders bare numbers);
        # only invalid characters or over-length input return None here.
        prefix_raw = request.form.get("invoice_prefix", "")
        sanitized_prefix = sanitize_invoice_prefix(prefix_raw)
        if sanitized_prefix is None:
            flash(
                "Invoice prefix invalid: only letters, numbers, space, "
                "and & . - allowed (max " + str(INVOICE_PREFIX_INPUT_MAX)
                + " chars). Other settings were not saved.",
                "error",
            )
            return redirect(url_for("account"))

        user = db.session.get(User, current_user.id)
        # Hotfix-1 T4: cap before .strip() so a 50KB business_name can't sit
        # in memory longer than necessary. _sanitize_storage handles both
        # the trim and the cap.
        business_name = _sanitize_storage(request.form.get("business_name"), BUSINESS_NAME_MAX)
        phone_number = _sanitize_storage(request.form.get("phone_number"), CUSTOMER_PHONE_MAX)
        quote_footer = sanitize_footer(request.form.get("quote_footer_text"))
        invoice_footer = sanitize_footer(request.form.get("invoice_footer_text"))
        user.business_name = business_name or None
        user.phone_number = phone_number or None
        # Empty string -> NULL so the generator falls back to the sovereign
        # defaults instead of rendering a blank footer.
        user.quote_footer_text = quote_footer or None
        user.invoice_footer_text = invoice_footer or None
        # Invoice prefix: store the sanitized value as-is (including empty
        # string for bare-number rendering). Column is NOT NULL so we
        # cannot store None — the empty-string case is the user's explicit
        # opt-in to "no prefix". Stable across re-renders of past invoices
        # because Quote.invoice_prefix is snapshotted at claim time.
        user.invoice_prefix = sanitized_prefix
        db.session.commit()
        flash("Account details saved.", "success")
        return redirect(url_for("account"))
    return render_template(
        "account.html",
        default_quote_footer=DEFAULT_QUOTE_FOOTER,
        default_invoice_footer=DEFAULT_INVOICE_FOOTER,
        invoice_prefix_default=INVOICE_PREFIX_DEFAULT,
        invoice_prefix_input_max=INVOICE_PREFIX_INPUT_MAX,
    )


# ---------- Account deletion (Hotfix-3 T4) ----------

@app.route("/account/delete", methods=["GET", "POST"])
@login_required
def account_delete():
    """
    Hotfix-3 T4 (Inquisitor C2): self-serve account deletion.

    Hard delete, not soft delete. GDPR Article 17 ("right to erasure")
    requires deletion without undue delay; soft delete is a compliance
    liability unless justified by legitimate interest (which we don't have
    for the user-row + quote history). Stripe Dashboard remains the
    canonical record of historic billing, which is the only data we have
    a legitimate-interest argument to retain anyway.

    Order of operations (intentional):
      1. POST validates the confirmation email matches current_user.email.
         Wrong email -> flash + re-render. Closes the misclick path.
      2. Best-effort Stripe subscription cancel. Failure is logged + admin
         alerted, but does NOT block the deletion — the user has the
         legal right to leave regardless of whether Stripe's API hiccups.
      3. logout_user() BEFORE DB delete so Flask-Login doesn't try to
         touch a soon-to-be-deleted row mid-request.
      4. Snapshot the email + sub_id BEFORE the User row goes away.
      5. db.session.delete(user) cascades through profiles, quotes,
         transactions, contact_submissions (all set in models.py).
      6. shutil.rmtree the per-user PDF bucket. Errors here are non-fatal
         (the bucket is regeneratable from DB; gone-from-DB means gone).
      7. Send the account-closed confirmation email (best-effort).
      8. Audit log `[ACCOUNT-DELETED]` carries the snapshot data so
         post-hoc forensics has something to grep on.
    """
    user = db.session.get(User, current_user.id)
    had_subscription = user.subscription_status in ("active", "past_due")

    if request.method == "POST":
        confirm = (request.form.get("confirm_email") or "").strip().lower()
        if confirm != user.email.lower():
            flash(
                "The email you typed didn't match your account email. "
                "Account NOT deleted.",
                "error",
            )
            return render_template("account_delete.html")

        # Snapshot for audit log + closed-email — these reads must happen
        # before the delete clears the row.
        deleted_email = user.email
        deleted_uid = user.id
        sub_id = user.subscription_id

        # Best-effort Stripe sub cancel. Don't block delete on failure.
        if sub_id and config.STRIPE_SECRET_KEY:
            try:
                stripe.Subscription.delete(sub_id)
            except Exception as e:
                app.logger.error(
                    "[STRIPE-CANCEL-FAILED] user_id=%s sub_id=%s error=%r — "
                    "proceeding with delete; manual reconcile needed",
                    deleted_uid, sub_id, str(e),
                )
                _notify_admin(
                    alert_tag="STRIPE-CANCEL-FAILED",
                    subject_summary=f"Manual Stripe cancel needed for sub {sub_id}",
                    body_markdown=(
                        f"User_id (deleted): {deleted_uid}\n"
                        f"Email (deleted):   {user.email}\n"
                        f"Stripe sub_id:     {sub_id}\n"
                        f"\n"
                        f"The user has self-deleted their account, but the\n"
                        f"Stripe subscription cancel API call failed:\n"
                        f"  {e!r}\n"
                        f"\n"
                        f"Action: log in to Stripe Dashboard and cancel the\n"
                        f"subscription manually. The user has no app account\n"
                        f"anymore, so they cannot self-cancel via the\n"
                        f"Billing Portal.\n"
                    ),
                )

        # Log out the session BEFORE deleting the row — Flask-Login
        # otherwise tries to load the (deleted) user on the next
        # before_request hook and 500s.
        logout_user()

        # Cascade delete via SQLAlchemy relationships (models.py).
        db.session.delete(user)
        db.session.commit()

        # PDF bucket cleanup — non-fatal on error; the bucket is purely a
        # cache of DB-derivable content.
        try:
            pdf_dir = os.path.join(config.OUTPUT_DIR, str(deleted_uid))
            if os.path.isdir(pdf_dir):
                shutil.rmtree(pdf_dir, ignore_errors=True)
        except Exception as e:
            app.logger.warning(
                "[ACCOUNT-DELETE-PDF-CLEANUP] user_id=%s error=%r — "
                "DB row gone but PDF dir may persist; safe to ignore",
                deleted_uid, str(e),
            )

        # Confirmation email — best-effort. The user can't reach support
        # via the now-deleted account, but they can still see the closed
        # confirmation in their inbox.
        mailer.send_email(
            to=deleted_email,
            subject="Your Panefree Quotes account is closed",
            html_body=render_template(
                "email/account_closed.html",
                closed_email=deleted_email,
                support_email=config.SUPPORT_EMAIL,
                had_subscription=had_subscription,
            ),
            text_body=render_template(
                "email/account_closed.txt",
                closed_email=deleted_email,
                support_email=config.SUPPORT_EMAIL,
                had_subscription=had_subscription,
            ),
        )

        app.logger.info(
            "[ACCOUNT-DELETED] user_id=%s email=%s sub_id=%s had_subscription=%s",
            deleted_uid, deleted_email, sub_id, had_subscription,
        )

        flash(
            "Your account is closed. We've sent a confirmation email to "
            f"{deleted_email}.",
            "success",
        )
        return redirect(url_for("register"))

    return render_template("account_delete.html")


# ---------- Legacy settings route — redirect to the new profile UI ----------

@app.route("/settings")
@login_required
def settings():
    return redirect(url_for("profiles_list"))


# ---------- Legal page routes (Hotfix-6 T1) ----------
#
# Static HTML served from the legal/ directory. These route to the
# Termly-generated policy documents required for production.
# Post-launch (P4): swap these for Termly JS embed + cookie consent banner.

LEGAL_DIR = os.path.join(project_root, "legal")


@app.route("/legal/privacy")
def legal_privacy():
    """Privacy Policy — required for production (H01 legal blocker)."""
    path = os.path.join(LEGAL_DIR, "privacy-policy.html")
    if not os.path.exists(path):
        abort(404)
    with open(path, "r", encoding="utf-8") as f:
        return f.read(), 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/legal/terms")
def legal_terms():
    """Terms of Service — required for production (H02 legal blocker)."""
    path = os.path.join(LEGAL_DIR, "terms-of-service.html")
    if not os.path.exists(path):
        abort(404)
    with open(path, "r", encoding="utf-8") as f:
        return f.read(), 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/legal/cookies")
def legal_cookies():
    """Cookie Policy — required for production (H03 legal blocker)."""
    path = os.path.join(LEGAL_DIR, "cookie-policy.html")
    if not os.path.exists(path):
        abort(404)
    with open(path, "r", encoding="utf-8") as f:
        return f.read(), 200, {"Content-Type": "text/html; charset=utf-8"}


if __name__ == "__main__":
    app.run(debug=True, port=5001)
