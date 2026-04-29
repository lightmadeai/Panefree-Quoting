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
    # Full input+calculation snapshot. Decimal values are stored as strings
    # inside this JSON so rehydration is lossless (Heresy #11).
    quote_data = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
