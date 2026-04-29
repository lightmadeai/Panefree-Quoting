import os

project_root = os.path.dirname(os.path.abspath(__file__))

SECRET_KEY = os.environ.get("SRE_SECRET_KEY", "sre_secret_key_change_me_in_prod")
DATABASE_PATH = os.path.join(project_root, "sovereign.db")
SQLALCHEMY_DATABASE_URI = f"sqlite:///{DATABASE_PATH}"
SQLALCHEMY_TRACK_MODIFICATIONS = False

STARTING_CREDITS = 5

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
CREDIT_PACKS = {
    "starter": {"name": "Starter",  "credits": 10,  "price_cents": 1000},
    "pro":     {"name": "Pro",      "credits": 50,  "price_cents": 4000},
    "studio":  {"name": "Studio",   "credits": 200, "price_cents": 12000},
}

# Seed file — used only to populate a new user's default profiles.
# Runtime reads come from the pricing_profiles table, never this file.
SEED_PRICE_SHEET_PATH = os.path.join(project_root, "price_sheet.json")
