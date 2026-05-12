from datetime import datetime
from decimal import Decimal
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.Text, unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    credit_balance = db.Column(db.Integer, nullable=False, default=10)
    # Subscription state. NULL = no subscription history; non-NULL takes
    # values "active", "past_due", or "canceled". The /generate reserve
    # bypass keys off `subscription_current_period_end`, not this field
    # alone — see Heresy #12 (lapsed-but-cached subscriber).
    subscription_status = db.Column(db.Text, nullable=True)
    # Stripe subscription ID. UNIQUE: blocks the double-subscribe race
    # (same sub linked to two users) — same idempotency pattern as
    # Transaction.stripe_tx_id. NULL for non-subscribers; SQLite's UNIQUE
    # admits multiple NULLs by default, which is what we want.
    subscription_id = db.Column(db.Text, nullable=True, unique=True)
    # UTC. Sole field consulted by the reserve bypass to decide whether
    # paid access is still active. Persists past status="canceled" so a
    # canceled-but-paid user keeps unlimited access through their billing
    # period (Stripe pattern: cancel-at-period-end).
    subscription_current_period_end = db.Column(db.DateTime, nullable=True)
    # Pending cancellation flag. True when the user has scheduled a cancel
    # via the Stripe Billing Portal but the billing period hasn't elapsed
    # yet — they still have unlimited access, but the UI says "Cancels on
    # {date}" instead of "Renews on {date}". Resets to False when the sub
    # actually terminates (sub.deleted webhook), so a future re-subscribe
    # starts in the renewing state.
    cancel_at_period_end = db.Column(db.Boolean, nullable=False, default=False)
    # Login lockout (T4 abuse-prevention). Count resets to 0 on successful
    # login; locked_until is the wall-clock time at which the lockout
    # expires. NULL means "never been locked".
    failed_login_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    # Email verification gate. Required before /generate succeeds —
    # subscribers included (no exemption; otherwise stolen-card subs are
    # an abuse vector). Token is a 32-char uuid hex; expires 24h after
    # registration. Pre-Sprint-3 users are grandfathered as verified via
    # _backfill_email_verified() at boot.
    email_verified = db.Column(db.Boolean, nullable=False, default=False)
    email_verification_token = db.Column(db.Text, nullable=True, index=True)
    email_verification_token_expires = db.Column(db.DateTime, nullable=True)
    # Hotfix-3 T3: password reset tokens. Same shape as the email
    # verification token (32-char uuid hex, single-use, expires) but with
    # a tighter 1-hour expiry — reset links are higher-value and
    # short-lived limits the blast radius if a user forwards the email.
    # Indexed for the lookup-by-token query in /reset-password/<token>.
    password_reset_token = db.Column(db.Text, nullable=True, index=True)
    password_reset_token_expires = db.Column(db.DateTime, nullable=True)
    business_name = db.Column(db.Text, nullable=True)
    phone_number = db.Column(db.Text, nullable=True)
    # NULL means "use sovereign default"; non-NULL is the user's customized
    # template, possibly containing {{phone}} / {{date}} placeholders that
    # the controller substitutes before rendering. Generator stays a Pure View.
    quote_footer_text = db.Column(db.Text, nullable=True)
    invoice_footer_text = db.Column(db.Text, nullable=True)
    # Per-user counter for legally-compliant gap-free invoice numbers.
    # Claimed and incremented atomically the first time a Quote is rendered
    # as an INVOICE (see app.py:_claim_invoice_number). Quote.invoice_number
    # caches the claimed value so re-renders are idempotent. Starts at 1;
    # never decreases (gap = audit red flag). No rollover at any width: the
    # display pad in generator.py is min-width, not max-width.
    next_invoice_number = db.Column(db.Integer, nullable=False, default=1)
    # Per-user prefix on the rendered invoice ID (Feature 3). Default
    # "INV-" preserves the original hardcoded behavior for users who
    # never customize. Snapshotted onto Quote.invoice_prefix at claim
    # time so later changes don't retroactively rename existing invoices
    # — legal-identifier stability matters more than display consistency
    # across a prefix change. Validation lives in app.sanitize_invoice_prefix.
    invoice_prefix = db.Column(db.Text, nullable=False, default="INV-")
    # Per-user sequential quote counter (BUG-007, Sprint 4). Bumped via the
    # same pattern as next_invoice_number — atomic UPDATE in
    # _claim_quote_number, snapshotted onto Quote.quote_number at /generate.
    next_quote_number = db.Column(db.Integer, nullable=False, default=1)
    # Per-user quote prefix (BUG-007). Default 'Q-' so users who never
    # customize get the standard Q-NNNNNN format. Snapshotted at claim time
    # for stability across later prefix changes.
    quote_prefix = db.Column(db.Text, nullable=False, default="Q-")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Hotfix-3 T4 (Inquisitor C2): all child rows cascade-delete with the
    # user. Hard delete is the GDPR-compliant default; Stripe Dashboard
    # remains the canonical source of historic billing records.
    transactions = db.relationship(
        "Transaction", backref="user", lazy=True,
        cascade="all, delete-orphan",
    )
    profiles = db.relationship(
        "PricingProfile", backref="user", lazy=True,
        cascade="all, delete-orphan",
    )
    quotes = db.relationship(
        "Quote", backref="user", lazy=True,
        cascade="all, delete-orphan",
    )
    contact_submissions = db.relationship(
        "ContactSubmission", backref="user", lazy=True,
        cascade="all, delete-orphan",
    )

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)


class Transaction(db.Model):
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    credits_added = db.Column(db.Integer, nullable=False, default=0)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    # UNIQUE: Stripe event idempotency guard — blocks replayed webhooks.
    stripe_tx_id = db.Column(db.Text, unique=True)


class PricingProfile(db.Model):
    __tablename__ = "pricing_profiles"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.Text, nullable=False)
    price_data = db.Column(db.JSON, nullable=False)
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ContactSubmission(db.Model):
    """
    Custom-plan intake from the soft-cap CTA. Persisted only — no email
    delivery yet (deferred per Sprint 3 scope). Admin notification is a
    structured log line; future sprint adds actual delivery.
    """
    __tablename__ = "contact_submissions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    company_name = db.Column(db.Text, nullable=False)
    # Free-text — could be a number ("~1500"), a range ("1k-2k"), or a
    # description ("highly variable seasonal"). Don't constrain the shape;
    # downstream sales conversation parses it.
    current_volume = db.Column(db.Text, nullable=False)
    expected_growth = db.Column(db.Text, nullable=False)
    # Reply-to address; intentionally NOT defaulted from User.email so the
    # sender can route replies to a different inbox if they want.
    email = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class Quote(db.Model):
    __tablename__ = "quotes"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    label = db.Column(db.Text, nullable=False, default="")
    final_price = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    pane_count = db.Column(db.Integer, nullable=False, default=0)
    # Customer ("Bill To") fields rendered on the PDF. All nullable for
    # back-compat with quotes created before this column existed; the
    # generator falls back to the legacy `label` if customer_name is empty.
    customer_name = db.Column(db.Text, nullable=True)
    customer_address = db.Column(db.Text, nullable=True)
    customer_email = db.Column(db.Text, nullable=True)
    customer_phone = db.Column(db.Text, nullable=True)
    # Sequential invoice number, claimed once on first INVOICE render via
    # an atomic UPDATE on the User row (see app.py:_claim_invoice_number).
    # Null until then — quotes that are only ever rendered as QUOTE PDFs
    # stay null forever, which is correct (only invoices need the legal
    # number). Format on PDF: "INV-000001" (zero-padded to 6 digits, but
    # the column itself has no width cap; integer can grow indefinitely).
    invoice_number = db.Column(db.Integer, nullable=True)
    # Snapshot of User.invoice_prefix at the moment invoice_number was
    # claimed (Feature 3). Null for: (a) quotes never converted to invoices,
    # (b) invoices issued before Feature 3 shipped — those fall back to
    # "INV-" via the generator's default. Once non-null, never changes:
    # re-renders of the same invoice always show the same prefix, even if
    # the user later changes their account setting. This is the legal
    # invariant that makes invoice IDs stable across a prefix change.
    invoice_prefix = db.Column(db.Text, nullable=True)
    # Sequential quote number (BUG-007, Sprint 4). Claimed at /generate time
    # for new quotes; null for pre-Sprint-4 quotes (the generator falls back
    # to the legacy hash code for those, so re-renders stay stable).
    quote_number = db.Column(db.Integer, nullable=True)
    # Snapshot of User.quote_prefix at claim time (BUG-007). Once set, never
    # changes — same stability invariant as invoice_prefix.
    quote_prefix = db.Column(db.Text, nullable=True)
    # Full input+calculation snapshot. Decimal values are stored as strings
    # inside this JSON so rehydration is lossless (Heresy #11).
    quote_data = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
