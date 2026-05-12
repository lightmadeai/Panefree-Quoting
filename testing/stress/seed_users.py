"""
Seed N=20 stress-test users directly into sovereign.db:
  - 10 free-tier   (email_verified=1, credit_balance=500)
  - 10 subscriber  (email_verified=1, subscription_status='active',
                    subscription_current_period_end = now + 365d)
Each user gets a default PricingProfile so /generate has something to render.

Emails follow the pattern stress_NN@locust.test so cleanup_users.py can wipe
them without touching real users. Idempotent — re-running upserts.

Run from the project root:  python testing/stress/seed_users.py
"""
import os, sys, sqlite3, json
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
DB   = os.path.join(ROOT, "sovereign.db")

PASSWORD = "StressTest!9999"
N_FREE = 10
N_SUB  = 10

DEFAULT_PRICE_DATA = {
    "base_pane_rate": 7.0,
    "base_callout_fee": 50.0,
    "tax_rate": 0.085,
    "story_surcharges": {"floor1": 1.0, "floor2": 1.25, "floor3": 1.5},
    "add_on_rates": {
        "Screen Cleaning": 3.0,
        "Track Cleaning": 2.0,
        "Hard Water Treatment": 5.0,
    },
}

def upsert_user(cur, email, *, subscriber):
    pw_hash = generate_password_hash(PASSWORD)
    now = datetime.utcnow()
    sub_end = now + timedelta(days=365) if subscriber else None
    cur.execute("SELECT id FROM users WHERE email = ?", (email,))
    row = cur.fetchone()
    if row:
        uid = row[0]
        cur.execute(
            "UPDATE users SET password_hash=?, credit_balance=?, "
            "email_verified=1, email_verification_token=NULL, "
            "subscription_status=?, subscription_current_period_end=? "
            "WHERE id=?",
            (
                pw_hash,
                500,
                "active" if subscriber else None,
                sub_end.isoformat() if sub_end else None,
                uid,
            ),
        )
    else:
        cur.execute(
            "INSERT INTO users (email, password_hash, credit_balance, "
            "email_verified, subscription_status, "
            "subscription_current_period_end, cancel_at_period_end, "
            "failed_login_attempts, next_invoice_number, invoice_prefix, "
            "next_quote_number, quote_prefix, created_at) "
            "VALUES (?, ?, ?, 1, ?, ?, 0, 0, 1, 'INV-', 1, 'Q-', ?)",
            (
                email,
                pw_hash,
                500,
                "active" if subscriber else None,
                sub_end.isoformat() if sub_end else None,
                now.isoformat(),
            ),
        )
        uid = cur.lastrowid
    cur.execute("SELECT 1 FROM pricing_profiles WHERE user_id=? AND name='Stress Default'", (uid,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO pricing_profiles (user_id, name, price_data, is_default, created_at) "
            "VALUES (?, ?, ?, 1, ?)",
            (uid, "Stress Default", json.dumps(DEFAULT_PRICE_DATA), now.isoformat()),
        )
    return uid

def main():
    if not os.path.exists(DB):
        print(f"DB not found at {DB}", file=sys.stderr); sys.exit(1)
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()
    created = []
    for i in range(1, N_FREE + 1):
        email = f"stress_free_{i:02d}@locust.test"
        uid = upsert_user(cur, email, subscriber=False)
        created.append((email, uid, "free"))
    for i in range(1, N_SUB + 1):
        email = f"stress_sub_{i:02d}@locust.test"
        uid = upsert_user(cur, email, subscriber=True)
        created.append((email, uid, "sub"))
    conn.commit()
    conn.close()
    print(f"Seeded {len(created)} users (password: {PASSWORD})")
    for email, uid, tier in created:
        print(f"  id={uid:>4}  {tier:>4}  {email}")

if __name__ == "__main__":
    main()
