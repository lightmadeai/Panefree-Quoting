"""
Stress-test locustfile. Run after seeding stress users.

  python testing/stress/seed_users.py
  python testing/stress/run_server.py   (in another terminal)
  locust -f testing/stress/locustfile.py --host=http://127.0.0.1:5001 \
         --headless -u 30 -r 5 -t 90s

Each virtual user:
  - is randomly assigned a seeded free/sub account (round-robin via class counter)
  - logs in once on_start (session cookie sticks via HttpUser's session)
  - runs weighted tasks: /, /calculate, /generate, /history, /account, /top-up
  - /generate is the heavy path — exercises credit reserve, rate limit, PDF
    rendering, per-user filename isolation
"""
import itertools, random, threading
from locust import HttpUser, task, between, events

PASSWORD = "StressTest!9999"
N_FREE = 10
N_SUB  = 10

_assign_lock = threading.Lock()
_assigner = itertools.cycle(
    [f"stress_free_{i:02d}@locust.test" for i in range(1, N_FREE + 1)] +
    [f"stress_sub_{i:02d}@locust.test"  for i in range(1, N_SUB + 1)]
)

def _next_email():
    with _assign_lock:
        return next(_assigner)

QUOTE_FORM = {
    "floor1": "5",
    "floor2": "3",
    "floor3": "0",
    "addon": "Screen Cleaning",
    "label": "stress-quote",
    "customer_name": "Stress Customer",
    "customer_address": "123 Load St",
    "customer_email": "load@test.example",
    "customer_phone": "555-0100",
}


class QuotingUser(HttpUser):
    wait_time = between(0.2, 0.8)
    abstract = False

    def on_start(self):
        self.email = _next_email()
        # Pull /login first to get a cookie / CSRF-less form prerequisite (none here)
        self.client.get("/login")
        with self.client.post(
            "/login",
            data={"email": self.email, "password": PASSWORD},
            allow_redirects=False,
            catch_response=True,
            name="/login",
        ) as r:
            if r.status_code not in (302, 303):
                r.failure(f"login {self.email} returned {r.status_code}")
            else:
                r.success()

    @task(5)
    def index(self):
        self.client.get("/", name="/")

    @task(4)
    def calculate(self):
        form = dict(QUOTE_FORM)
        form["floor1"] = str(random.randint(1, 8))
        form["floor2"] = str(random.randint(0, 5))
        self.client.post("/calculate", data=form, name="/calculate")

    @task(3)
    def generate(self):
        """Heavy path — credit reserve, PDF render, file write."""
        form = dict(QUOTE_FORM)
        form["floor1"] = str(random.randint(1, 6))
        with self.client.post(
            "/generate",
            data=form,
            name="/generate",
            catch_response=True,
        ) as r:
            # 200=success, 402=NO_CREDITS, 429=rate-limited — all are
            # legitimate outcomes under load. Only 5xx or 403 (verification)
            # would be a real defect for our seeded users.
            if r.status_code in (200, 402, 429):
                r.success()
            elif r.status_code == 403:
                r.failure(f"403 on /generate for {self.email}: {r.text[:120]}")
            else:
                r.failure(f"unexpected {r.status_code}: {r.text[:200]}")

    @task(2)
    def history(self):
        self.client.get("/history", name="/history")

    @task(1)
    def account(self):
        self.client.get("/account", name="/account")

    @task(1)
    def top_up(self):
        self.client.get("/top-up", name="/top-up")


@events.quitting.add_listener
def _summary(environment, **kw):
    s = environment.stats.total
    print("\n========================================")
    print(f"Total requests : {s.num_requests}")
    print(f"Failures       : {s.num_failures}")
    print(f"Median (ms)    : {s.median_response_time}")
    print(f"p95    (ms)    : {s.get_response_time_percentile(0.95)}")
    print(f"p99    (ms)    : {s.get_response_time_percentile(0.99)}")
    print(f"RPS            : {s.total_rps:.2f}")
    print("========================================\n")
