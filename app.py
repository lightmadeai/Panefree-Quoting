import os
import sys
import json
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from flask import (
    Flask, render_template, request, send_file, jsonify,
    redirect, url_for, flash, abort
)
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
import stripe

import config
from engine import calculate_quote
from generator import (
    generate_document, derive_doc_code,
    DEFAULT_QUOTE_FOOTER, DEFAULT_INVOICE_FOOTER, DEFAULT_PHONE_NUMBER,
)
from models import db, User, Transaction, PricingProfile, Quote

app = Flask(__name__)
app.config.from_object(config)
app.secret_key = config.SECRET_KEY

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

if config.STRIPE_SECRET_KEY:
    stripe.api_key = config.STRIPE_SECRET_KEY


@login_manager.user_loader
def load_user(user_id):
    user = db.session.get(User, int(user_id))
    # Idempotent — no-op once profiles exist. Protects users whose session
    # predates Sprint 2 (registered before profile seeding was added).
    if user:
        ensure_default_profiles_for_user(user)
    return user


def _ensure_user_columns():
    """
    SQLite lacks ALTER TABLE ... ADD COLUMN IF NOT EXISTS, and db.create_all()
    only creates missing tables — not missing columns. This runs once at boot
    and additively patches columns added after initial users-table creation.
    """
    existing = {row[1] for row in db.session.execute(text("PRAGMA table_info(users)")).fetchall()}
    additions = [
        ("business_name", "TEXT"),
        ("phone_number", "TEXT"),
        ("quote_footer_text", "TEXT"),
        ("invoice_footer_text", "TEXT"),
    ]
    for col, ddl in additions:
        if col not in existing:
            db.session.execute(text(f"ALTER TABLE users ADD COLUMN {col} {ddl}"))
    db.session.commit()


with app.app_context():
    db.create_all()
    _ensure_user_columns()


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


def sanitize_label(raw):
    """Trim, strip newlines/control chars, cap length. Heresy #10."""
    if not raw:
        return ""
    cleaned = " ".join(str(raw).split())
    return cleaned[:LABEL_MAX_LEN]


def sanitize_footer(raw):
    """
    Storage-layer sanitize for the user-editable footer templates. Mirrors
    sanitize_label (Heresy #10) — trim, collapse whitespace, length-cap.
    Latin-1 stripping is left to the generator's defense-in-depth pass so
    the DB keeps full unicode (smart quotes etc.) for display in the form.
    """
    if not raw:
        return ""
    cleaned = " ".join(str(raw).split())
    return cleaned[:FOOTER_MAX_LEN]


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

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("register.html")

        if User.query.filter_by(email=email).first():
            flash("That email is already registered.", "error")
            return render_template("register.html")

        user = User(email=email, credit_balance=config.STARTING_CREDITS)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        ensure_default_profiles_for_user(user)
        login_user(user)
        return redirect(url_for("index"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash("Invalid email or password.", "error")
            return render_template("login.html")

        ensure_default_profiles_for_user(user)
        login_user(user)
        return redirect(url_for("index"))

    return render_template("login.html")


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
            )
        return jsonify({"status": "success", "calculation": snapshot["calculation"]})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/generate", methods=["POST"])
@login_required
def generate():
    """Reserve -> Generate -> Refund on Failure (Heresy #1 fix)."""
    data = request.get_json(silent=True) or _parse_quote_form()
    registry, _ = get_user_profile_registry(current_user, preferred_name=data.get("profile_id"))
    if not data.get("profile_id"):
        data["profile_id"] = registry["active_profile"]
    registry = apply_callout_override(registry, data.get("profile_id"), data.get("callout_override"))

    # Atomic reserve
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
            "message": "You've run out of credits.",
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
        output_path = os.path.join(project_root, filename)
        label = sanitize_label(data.get("label"))
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
        )
        db.session.add(quote)
        db.session.flush()

        generate_document(
            snapshot,
            doc_type=doc_type,
            output_path=output_path,
            business_name=current_user.business_name,
            phone_number=current_user.phone_number,
            label=label,
            doc_code=derive_doc_code(quote.id),
            quote_footer=render_footer_template(
                current_user.quote_footer_text, "QUOTE", current_user.phone_number,
            ),
            invoice_footer=render_footer_template(
                current_user.invoice_footer_text, "INVOICE", current_user.phone_number,
            ),
        )
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        db.session.execute(
            text("UPDATE users SET credit_balance = credit_balance + 1 WHERE id = :uid"),
            {"uid": current_user.id},
        )
        db.session.commit()
        return jsonify({"status": "error", "message": str(e)}), 400

    return jsonify({
        "status": "success",
        "file": filename,
        "download_url": url_for("download", filename=filename),
        "credits_remaining": current_user.credit_balance,
        "quote_id": quote.id,
        "invoice_url": url_for("quote_render_pdf", quote_id=quote.id, type="INVOICE"),
    })


@app.route("/download/<filename>")
@login_required
def download(filename):
    safe_name = os.path.basename(filename)
    return send_file(os.path.join(project_root, safe_name), as_attachment=True)


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
        name = (form.get("name") or "").strip()

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
    name = (data.get("name") or "").strip()
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
    output_path = os.path.join(project_root, filename)

    try:
        generate_document(
            snapshot,
            doc_type=doc_type,
            output_path=output_path,
            business_name=current_user.business_name,
            phone_number=current_user.phone_number,
            label=q.label,
            doc_code=derive_doc_code(q.id),
            quote_footer=render_footer_template(
                current_user.quote_footer_text, "QUOTE", current_user.phone_number,
            ),
            invoice_footer=render_footer_template(
                current_user.invoice_footer_text, "INVOICE", current_user.phone_number,
            ),
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
        publishable_key=config.STRIPE_PUBLISHABLE_KEY,
        simulator_active=simulator_active,
    )


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
def checkout():
    if not config.STRIPE_SECRET_KEY:
        return jsonify({"status": "error", "message": "Stripe is not configured on this server."}), 503

    pack_id = request.form.get("pack") or request.json.get("pack")
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


@app.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    """
    Signature-verified, idempotent credit grant.
    Heresy candidate: double-credit on replay — blocked by UNIQUE(stripe_tx_id).
    """
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature", "")

    if not config.STRIPE_WEBHOOK_SECRET:
        return jsonify({"status": "error", "message": "Webhook secret not configured."}), 503

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, config.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        return jsonify({"status": "error", "message": str(e)}), 400

    if event["type"] != "checkout.session.completed":
        return jsonify({"status": "ignored", "type": event["type"]}), 200

    session_obj = event["data"]["object"]
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

    # Atomic credit + transaction insert guarded by UNIQUE(stripe_tx_id).
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


# ---------- Account settings (business name, phone) ----------

@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    if request.method == "POST":
        user = db.session.get(User, current_user.id)
        business_name = (request.form.get("business_name") or "").strip()
        phone_number = (request.form.get("phone_number") or "").strip()
        quote_footer = sanitize_footer(request.form.get("quote_footer_text"))
        invoice_footer = sanitize_footer(request.form.get("invoice_footer_text"))
        user.business_name = business_name or None
        user.phone_number = phone_number or None
        # Empty string -> NULL so the generator falls back to the sovereign
        # defaults instead of rendering a blank footer.
        user.quote_footer_text = quote_footer or None
        user.invoice_footer_text = invoice_footer or None
        db.session.commit()
        flash("Account details saved.", "success")
        return redirect(url_for("account"))
    return render_template(
        "account.html",
        default_quote_footer=DEFAULT_QUOTE_FOOTER,
        default_invoice_footer=DEFAULT_INVOICE_FOOTER,
    )


# ---------- Legacy settings route — redirect to the new profile UI ----------

@app.route("/settings")
@login_required
def settings():
    return redirect(url_for("profiles_list"))


if __name__ == "__main__":
    app.run(debug=True, port=5001)
