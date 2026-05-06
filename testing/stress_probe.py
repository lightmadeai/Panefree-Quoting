"""
Sprint 4 T2 + T3 — programmatic stress + security probe.
Runs against http://127.0.0.1:5001 and exercises the full surface looking
for cracks. Findings are printed to stdout and consolidated by a human into
testing/stress-test-results.md.

Probes:
  P1  Arbitrary file download (sovereign.db, app.py, config.py)
  P5  Email-verification gate (unverified user → 403)
  P6  Rate limit (free user, 11 quotes/hr → 429 on 11th)
  P8  Negative pane counts via JSON
  P9  Unicode / control-char injection in label, customer fields
  P10 Excessive-length inputs (10kB email, label, footer)
  P11 SQL injection probe on email field at /login
  P12 /dev/grant-credits without DEV_MODE — should 404
  P13 BUG-006 fix: line items with default rates do NOT contain "(Custom Rate)"
  P14 BUG-007 fix: new quote response carries quote_id and the row has Q-NNNNNN
  P15 BUG-003 fix: brand-new user (no profiles) is redirected from "/" to /profiles/new
  P16 BUG-008 fix: cross-tenant /download cannot reach another user's PDF
"""

import os, sys, time, json, sqlite3, requests, secrets

BASE = "http://127.0.0.1:5001"
DB   = os.path.join(os.path.dirname(__file__), "..", "sovereign.db")

def section(s):
    print(f"\n=== {s} ===")

def fresh_user_session(email_prefix="probe"):
    """Register a new user, return an authenticated requests.Session."""
    s = requests.Session()
    email = f"{email_prefix}_{secrets.token_hex(4)}@probe.test"
    pw    = "TestPassword!9999"
    r = s.post(f"{BASE}/register", data={"email": email, "password": pw}, allow_redirects=True)
    if r.status_code >= 400:
        raise RuntimeError(f"register failed: {r.status_code} {r.text[:200]}")
    return s, email, pw

def verify_user(email):
    """Verify the user directly in the DB (skips email plumbing)."""
    c = sqlite3.connect(DB)
    c.execute("UPDATE users SET email_verified=1, email_verification_token=NULL WHERE email=?", (email,))
    c.commit(); c.close()

def reset_rate_limit(email):
    """Wipe quotes for this user so we can re-test rate limit cleanly."""
    c = sqlite3.connect(DB)
    c.execute("DELETE FROM quotes WHERE user_id=(SELECT id FROM users WHERE email=?)", (email,))
    c.commit(); c.close()

def restock_credits(email, n=100):
    c = sqlite3.connect(DB)
    c.execute("UPDATE users SET credit_balance=? WHERE email=?", (n, email))
    c.commit(); c.close()

def make_default_profile(session, name="Residential_Standard"):
    """BUG-003 (Sprint 4) removed starter-profile auto-seeding, so probes
    that need a working /generate must explicitly create one first."""
    return session.post(f"{BASE}/api/profiles/create", json={
        "name": name, "make_default": True,
        "price_data": {
            "base_pane_rate": 5.0, "base_callout_fee": 75.0, "tax_rate": 0.085,
            "story_surcharges": {"floor1": 1.0, "floor2": 1.25, "floor3": 1.5},
            "add_on_rates": {"Screen Cleaning": 2.0, "Track Cleaning": 1.5, "Hard Water Treatment": 3.0},
        },
    })

# ------------------------------------------------------------------ P1
def p1_arbitrary_file_download():
    section("P1: arbitrary file download via /download/<filename>")
    s, email, _ = fresh_user_session("p1")
    targets = ["sovereign.db", "app.py", "config.py", "models.py", ".env"]
    for t in targets:
        r = s.get(f"{BASE}/download/{t}", allow_redirects=False)
        size = len(r.content) if r.status_code == 200 else 0
        print(f"  GET /download/{t:15s} -> {r.status_code}  ({size} bytes)")
    # Also try a path-traversal attempt; basename strips it but log result
    r = s.get(f"{BASE}/download/../../etc/passwd", allow_redirects=False)
    print(f"  GET /download/../../etc/passwd -> {r.status_code}")

# ------------------------------------------------------------------ P5
def p5_email_verification_gate():
    section("P5: email verification gate")
    s, email, _ = fresh_user_session("p5")
    # NOT verified yet — profile not needed because gate fires before engine
    r = s.post(f"{BASE}/generate", data={
        "floor1": 5, "profile_id": "Residential_Standard"
    })
    body = r.json() if "json" in r.headers.get("Content-Type", "") else {}
    print(f"  unverified /generate -> {r.status_code} code={body.get('code')}")
    verify_user(email)
    make_default_profile(s)  # BUG-003: must create profile post-Sprint-4
    r = s.post(f"{BASE}/generate", data={
        "floor1": 5, "profile_id": "Residential_Standard"
    })
    body = r.json() if "json" in r.headers.get("Content-Type", "") else {}
    print(f"  verified /generate   -> {r.status_code} status={body.get('status')}")

# ------------------------------------------------------------------ P6
def p6_rate_limit():
    section("P6: rate limit (10/hr free user)")
    s, email, _ = fresh_user_session("p6")
    verify_user(email)
    make_default_profile(s)
    restock_credits(email, 50)
    reset_rate_limit(email)
    statuses = []
    for i in range(12):
        r = s.post(f"{BASE}/generate", data={
            "floor1": 1, "profile_id": "Residential_Standard"
        })
        statuses.append(r.status_code)
    print(f"  12 quote attempts -> codes: {statuses}")
    # Expect first 10 -> 200, 11 & 12 -> 429
    n_429 = sum(1 for c in statuses if c == 429)
    print(f"  429 count: {n_429} (expected 2)")

# ------------------------------------------------------------------ P8
def p8_negative_panes():
    section("P8: negative pane count (engine validation)")
    s, email, _ = fresh_user_session("p8")
    verify_user(email)
    make_default_profile(s)
    restock_credits(email)
    r = s.post(f"{BASE}/generate", json={
        "panes": {"floor1": -50, "floor2": 0, "floor3": 0},
        "add_ons": [], "profile_id": "Residential_Standard",
        "overrides": {}, "addon_overrides": {}
    })
    print(f"  negative panes -> {r.status_code}")
    print(f"  body: {r.text[:300]}")

# ------------------------------------------------------------------ P9 / P10
def p9_p10_garbage_inputs():
    section("P9/P10: unicode + oversized input fields")
    s, email, _ = fresh_user_session("p910")
    verify_user(email)
    make_default_profile(s)
    restock_credits(email)
    huge_label = "A" * 10000
    weird = "💀" * 50 + "<script>alert(1)</script>" + "ñ" * 100
    r = s.post(f"{BASE}/generate", json={
        "panes": {"floor1": 1, "floor2": 0, "floor3": 0},
        "add_ons": [], "profile_id": "Residential_Standard",
        "overrides": {}, "addon_overrides": {},
        "label": huge_label,
        "customer_name": weird,
        "customer_address": weird,
        "customer_email": weird + "@x.com",
        "customer_phone": weird,
    })
    print(f"  garbage payload -> {r.status_code}")
    if r.status_code == 200:
        print(f"  -> snapshot accepted, file: {r.json().get('file')}")

# ------------------------------------------------------------------ P11
def p11_sql_injection_login():
    section("P11: SQL injection probes on /login email field")
    payloads = [
        "' OR '1'='1",
        "admin'--",
        "x'; DROP TABLE users;--",
        "x' UNION SELECT 1,email,password_hash,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20 FROM users--",
    ]
    for p in payloads:
        r = requests.post(f"{BASE}/login", data={"email": p, "password": "x"}, allow_redirects=False)
        # Should always be a redirect/render with the standard "invalid" message,
        # never a 5xx (which would suggest the parameterized query failed).
        print(f"  payload={p[:30]!r:35s} -> {r.status_code}")

# ------------------------------------------------------------------ P12
def p12_dev_grant_credits_in_prod():
    section("P12: /dev/grant-credits when Stripe is not configured")
    s, email, _ = fresh_user_session("p12")
    r = s.post(f"{BASE}/dev/grant-credits", data={"pack": "starter"}, allow_redirects=False)
    print(f"  /dev/grant-credits -> {r.status_code}")
    # If DEV_MODE is unset and STRIPE_SECRET_KEY also unset, behavior depends on
    # the gate: route asks for `DEV_MODE and not STRIPE_SECRET_KEY` -> if DEV_MODE
    # is False the route 404s. Confirm.

# ------------------------------------------------------------------ P13
def p13_no_custom_rate_on_defaults():
    """BUG-006 verification: a quote built with default rates must not
    contain '(Custom Rate)' in any line item. Exercises the engine path
    via /generate, then re-renders the saved Quote row to check the
    snapshot it actually persisted."""
    section("P13: BUG-006 fix — no spurious '(Custom Rate)' on defaults")
    s, email, _ = fresh_user_session("p13")
    verify_user(email)
    # Need a profile — register no longer auto-seeds, so create one.
    # Use the JSON profile-create API. Need a default profile to enable
    # /generate to find a profile_id.
    p = s.post(f"{BASE}/api/profiles/create", json={
        "name": "TestRes",
        "make_default": True,
        "price_data": {
            "base_pane_rate": 5.0,
            "base_callout_fee": 75.0,
            "tax_rate": 0.085,
            "story_surcharges": {"floor1": 1.0, "floor2": 1.25, "floor3": 1.5},
            "add_on_rates": {"Screen Cleaning": 2.0, "Track Cleaning": 1.5, "Hard Water Treatment": 3.0},
        },
    })
    if p.status_code != 200:
        print(f"  setup failed: {p.status_code} {p.text[:200]}"); return
    restock_credits(email)
    # Empty overrides → engine should treat as default
    r = s.post(f"{BASE}/generate", json={
        "panes": {"floor1": 5, "floor2": 3, "floor3": 0},
        "add_ons": ["Screen Cleaning"],
        "profile_id": "TestRes",
        "overrides": {}, "addon_overrides": {},
    })
    if r.status_code != 200:
        print(f"  generate failed: {r.status_code} {r.text[:200]}"); return
    body = r.json()
    quote_id = body.get("quote_id")
    # Pull the saved snapshot from the DB
    c = sqlite3.connect(DB)
    row = c.execute("SELECT quote_data FROM quotes WHERE id=?", (quote_id,)).fetchone()
    c.close()
    snapshot = json.loads(row[0]) if row else {}
    line_items = snapshot.get("line_items", [])
    custom_count = sum(1 for li in line_items if "Custom Rate" in li.get("description", ""))
    print(f"  line items: {len(line_items)}, with '(Custom Rate)': {custom_count}")
    print(f"  PASS" if custom_count == 0 else f"  FAIL — defaults still tagged as custom")

# ------------------------------------------------------------------ P14
def p14_sequential_quote_id():
    """BUG-007 verification: new quote rows have Q-NNNNNN persisted."""
    section("P14: BUG-007 fix — sequential Q- quote numbers")
    s, email, _ = fresh_user_session("p14")
    verify_user(email)
    s.post(f"{BASE}/api/profiles/create", json={
        "name": "TestRes",
        "make_default": True,
        "price_data": {
            "base_pane_rate": 5.0, "base_callout_fee": 75.0, "tax_rate": 0.085,
            "story_surcharges": {"floor1": 1.0, "floor2": 1.25, "floor3": 1.5},
            "add_on_rates": {"Screen Cleaning": 2.0, "Track Cleaning": 1.5, "Hard Water Treatment": 3.0},
        },
    })
    restock_credits(email)
    rs = []
    for _i in range(3):
        r = s.post(f"{BASE}/generate", json={
            "panes": {"floor1": 1, "floor2": 0, "floor3": 0}, "add_ons": [],
            "profile_id": "TestRes", "overrides": {}, "addon_overrides": {},
        })
        rs.append(r.json().get("quote_id"))
    c = sqlite3.connect(DB)
    nums = []
    for qid in rs:
        row = c.execute("SELECT quote_number, quote_prefix FROM quotes WHERE id=?", (qid,)).fetchone()
        nums.append(row)
    c.close()
    print(f"  quote rows: {nums}")
    pass_ok = all(n is not None and n[0] is not None for n in nums) and \
              [n[0] for n in nums] == [1, 2, 3]
    print(f"  PASS" if pass_ok else "  FAIL — numbers not sequential or missing")

# ------------------------------------------------------------------ P15
def p15_zero_profile_redirect():
    """BUG-003 verification: a new user with no profiles gets bounced
    from / to /profiles/new."""
    section("P15: BUG-003 fix — new users redirected to /profiles/new")
    s, email, _ = fresh_user_session("p15")
    verify_user(email)
    r = s.get(f"{BASE}/", allow_redirects=False)
    loc = r.headers.get("Location", "")
    print(f"  GET / -> {r.status_code}  Location: {loc}")
    pass_ok = r.status_code in (301, 302, 303) and "profiles/new" in loc
    print(f"  PASS" if pass_ok else "  FAIL — expected redirect to /profiles/new")

# ------------------------------------------------------------------ P16
def p16_cross_tenant_download():
    """BUG-008 verification: even if user A learns user B's PDF filename,
    user A cannot fetch it. Sealed by per-user output buckets."""
    section("P16: BUG-008 fix — cross-tenant /download blocked")
    # User A: register, make a profile, generate a PDF, capture filename
    sA, emailA, _ = fresh_user_session("p16a")
    verify_user(emailA)
    sA.post(f"{BASE}/api/profiles/create", json={
        "name": "P", "make_default": True,
        "price_data": {
            "base_pane_rate": 5.0, "base_callout_fee": 75.0, "tax_rate": 0.085,
            "story_surcharges": {"floor1": 1.0, "floor2": 1.25, "floor3": 1.5},
            "add_on_rates": {"Screen Cleaning": 2.0, "Track Cleaning": 1.5, "Hard Water Treatment": 3.0},
        },
    })
    restock_credits(emailA)
    rA = sA.post(f"{BASE}/generate", json={
        "panes": {"floor1": 1, "floor2": 0, "floor3": 0}, "add_ons": [],
        "profile_id": "P", "overrides": {}, "addon_overrides": {},
    })
    file_a = rA.json().get("file")
    print(f"  user A generated: {file_a}")

    # User A can download their own file
    rOwn = sA.get(f"{BASE}/download/{file_a}", allow_redirects=False)
    print(f"  user A own file -> {rOwn.status_code}")

    # User B registers, tries to fetch user A's PDF by name
    sB, emailB, _ = fresh_user_session("p16b")
    verify_user(emailB)
    rCross = sB.get(f"{BASE}/download/{file_a}", allow_redirects=False)
    print(f"  user B cross-tenant -> {rCross.status_code}")

    # User B also tries to fetch sovereign.db / app.py
    rDb = sB.get(f"{BASE}/download/sovereign.db", allow_redirects=False)
    rApp = sB.get(f"{BASE}/download/app.py", allow_redirects=False)
    print(f"  user B /download/sovereign.db -> {rDb.status_code}")
    print(f"  user B /download/app.py       -> {rApp.status_code}")

    pass_ok = (rOwn.status_code == 200) and \
              (rCross.status_code == 404) and \
              (rDb.status_code == 404) and (rApp.status_code == 404)
    print(f"  PASS" if pass_ok else "  FAIL")


# ------------------------------------------------------------------ runner
PROBES = [
    p1_arbitrary_file_download,
    p5_email_verification_gate,
    p6_rate_limit,
    p8_negative_panes,
    p9_p10_garbage_inputs,
    p11_sql_injection_login,
    p12_dev_grant_credits_in_prod,
    p13_no_custom_rate_on_defaults,
    p14_sequential_quote_id,
    p15_zero_profile_redirect,
    p16_cross_tenant_download,
]

if __name__ == "__main__":
    for fn in PROBES:
        try:
            fn()
        except Exception as e:
            print(f"  !! probe {fn.__name__} crashed: {e}")
    print("\ndone.")
