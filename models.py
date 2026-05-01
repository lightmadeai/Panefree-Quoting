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
    credit_balance = db.Column(db.Integer, nullable=False, default=5)
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    transactions = db.relationship("Transaction", backref="user", lazy=True)
    profiles = db.relationship("PricingProfile", backref="user", lazy=True, cascade="all, delete-orphan")

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
    # Full input+calculation snapshot. Decimal values are stored as strings
    # inside this JSON so rehydration is lossless (Heresy #11).
    quote_data = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
