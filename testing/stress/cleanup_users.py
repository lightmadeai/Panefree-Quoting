"""
Delete the seeded stress users + their cascading rows + their per-user PDF
dirs. Safe to run multiple times.

Run from project root:  python testing/stress/cleanup_users.py
"""
import os, sys, sqlite3, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
DB   = os.path.join(ROOT, "sovereign.db")
OUT  = os.path.join(ROOT, "output")

def main():
    if not os.path.exists(DB):
        print(f"DB not found at {DB}", file=sys.stderr); sys.exit(1)
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()
    cur.execute("SELECT id, email FROM users WHERE email LIKE 'stress_%@locust.test'")
    victims = cur.fetchall()
    if not victims:
        print("No stress users found.")
        conn.close(); return
    ids = [u[0] for u in victims]
    placeholders = ",".join("?" * len(ids))
    cur.execute(f"DELETE FROM quotes WHERE user_id IN ({placeholders})", ids)
    cur.execute(f"DELETE FROM contact_submissions WHERE user_id IN ({placeholders})", ids)
    cur.execute(f"DELETE FROM transactions WHERE user_id IN ({placeholders})", ids)
    cur.execute(f"DELETE FROM pricing_profiles WHERE user_id IN ({placeholders})", ids)
    cur.execute(f"DELETE FROM users WHERE id IN ({placeholders})", ids)
    conn.commit()
    conn.close()
    for uid in ids:
        d = os.path.join(OUT, str(uid))
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
    print(f"Deleted {len(victims)} stress users and their data.")

if __name__ == "__main__":
    main()
