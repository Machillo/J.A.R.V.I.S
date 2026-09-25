"""DINCR load test: synthetic Free/Basic/VIP users against a LOCAL backend, in stages.

Never point this at production. It refuses any base URL that is not localhost.

    python loadtest/run_load.py --base http://127.0.0.1:8790 --users 120 --stages 10,25,50,100 \
        --stage-seconds 60 --db dincr_load --out loadtest/results/<name>.json

Setup (once per database): every synthetic user signs in through the real API (the
local Auth stub answers for tokens "loadtest-<n>"), accepts the legal documents,
completes the profile, picks a plan (40% Free, 30% Basic, 30% VIP) and onboarding,
then creates debts, income, expenses, a goal and (Basic/VIP) a budget.

Each stage runs N concurrent virtual users. A virtual user loops like the app: open
the app (/auth/me), its plan's dashboard, movements, debts, goals and plan screens,
with 1-3 s of think time, and some controlled writes (an expense, a budget save).
Measured: requests/s, p50/p95/p99 per endpoint and overall, errors, timeouts,
Postgres connections (pg_stat_activity) and backend CPU / memory (ps).
"""
from __future__ import annotations

import argparse
import http.client
import json
import random
import statistics
import subprocess
import threading
import time
from collections import defaultdict

from urllib.parse import urlsplit

PLANS = ("free",) * 4 + ("basic",) * 3 + ("vip",) * 3
TIMEOUT = 30


class Client:
    def __init__(self, base: str, token: str):
        parts = urlsplit(base)
        if parts.hostname not in {"127.0.0.1", "localhost"}:
            raise SystemExit("run_load.py only targets a local backend")
        self.host, self.port, self.token = parts.hostname, parts.port or 80, token
        self.conn = None

    def call(self, method: str, path: str, body=None) -> tuple[int, float, bytes]:
        payload = json.dumps(body).encode() if body is not None else None
        headers = {"Authorization": f"Bearer {self.token}", "Accept-Language": "es"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        started = time.perf_counter()
        for attempt in range(2):
            try:
                if self.conn is None:
                    self.conn = http.client.HTTPConnection(self.host, self.port, timeout=TIMEOUT)
                self.conn.request(method, path, body=payload, headers=headers)
                response = self.conn.getresponse()
                data = response.read()
                return response.status, (time.perf_counter() - started) * 1000, data
            except (TimeoutError, OSError, http.client.HTTPException) as exc:
                self.conn = None
                if isinstance(exc, TimeoutError) or attempt:
                    return (599 if isinstance(exc, TimeoutError) else 598), (time.perf_counter() - started) * 1000, b""
        return 598, (time.perf_counter() - started) * 1000, b""


def setup_user(base: str, n: int) -> str:
    client, plan = Client(base, f"loadtest-{n}"), PLANS[n % len(PLANS)]
    steps = [
        ("GET", "/auth/me", None),
        ("POST", "/auth/legal/accept", {"accept_terms": True, "accept_privacy": True,
                                        "terms_version": "2026-09-23-v3", "privacy_version": "2026-09-25-v4"}),
        ("POST", "/auth/profile-setup", {"display_name": f"Carga {n}", "usage_goal": "control"}),
        ("POST", "/auth/plan", {"plan": plan}),
        ("POST", "/auth/onboarding", {"income_type": "fixed", "work_days_per_week": 5, "pay_frequency": "monthly",
                                      "fixed_monthly_salary": 850000, "essential_monthly_expenses": 400000,
                                      "strategy_preference": "balanced"}),
        ("POST", "/user-product/finance/income", {"amount": 850000, "description": "Salario sintético", "category": "salario"}),
        ("POST", "/user-product/finance/debts", {"name": "Tarjeta sintética", "remaining_amount": 350000, "monthly_payment": 45000,
                                                 "interest_rate": 38, "payment_day": 15, "debt_type": "credit_card"}),
        ("POST", "/user-product/finance/debts", {"name": "Préstamo sintético", "remaining_amount": 1200000, "monthly_payment": 65000,
                                                 "interest_rate": 18, "payment_day": 5, "debt_type": "personal_loan"}),
        ("POST", "/user-product/goals", {"name": "Fondo sintético", "target_amount": 500000}),
    ]
    steps += [("POST", "/user-product/finance/expenses", {"amount": 5000 + 1000 * i, "description": f"Gasto sintético {i}",
                                                          "category": "alimentacion"}) for i in range(5)]
    if plan in {"basic", "vip"}:
        steps.append(("PUT", "/user-product/basic/budget", {"items": [{"category": "alimentacion", "monthly_limit": 150000},
                                                                      {"category": "transporte", "monthly_limit": 60000}]}))
    for method, path, body in steps:
        status, _, data = client.call(method, path, body)
        if status >= 400 and path != "/auth/plan":
            raise RuntimeError(f"setup {n} {method} {path} -> {status} {data[:160]!r}")
    return plan


SCREENS = {
    "free": ["/user-product/free/dashboard", "/user-product/free/movements", "/user-product/finance/debts",
             "/user-product/goals", "/user-product/finance/summary"],
    "basic": ["/user-product/basic/dashboard", "/user-product/free/movements", "/user-product/basic/budget",
              "/user-product/finance/debts", "/user-product/goals", "/user-product/finance/strategy-basic"],
    "vip": ["/user-product/vip/command-center", "/user-product/free/movements", "/user-product/basic/budget",
            "/user-product/finance/debts", "/user-product/finance/strategy-vip", "/user-product/vip/strategy-dashboard"],
}


def virtual_user(base, n, plan, stop, results, think):
    client, rng = Client(base, f"loadtest-{n}"), random.Random(n)
    while not stop.is_set():
        calls = [("GET", "/auth/me", None)] + [("GET", path, None) for path in rng.sample(SCREENS[plan], 3)]
        if rng.random() < 0.10:
            calls.append(("POST", "/user-product/finance/expenses",
                          {"amount": rng.randint(1000, 20000), "description": "Carga sintética", "category": "alimentacion"}))
        if plan != "free" and rng.random() < 0.03:
            calls.append(("PUT", "/user-product/basic/budget", {"items": [{"category": "alimentacion", "monthly_limit": rng.randint(100000, 200000)}]}))
        for method, path, body in calls:
            if stop.is_set():
                break
            status, ms, _ = client.call(method, path, body)
            results.append((time.time(), f"{method} {path}", status, ms))
        stop.wait(rng.uniform(*think))


def sample_resources(db, backend_pid, stop, samples):
    while not stop.is_set():
        row = {"t": time.time()}
        try:
            out = subprocess.run(["psql", "-X", "-At", "-d", db, "-c",
                                  "SELECT count(*), count(*) FILTER (WHERE state='active'), count(*) FILTER (WHERE state LIKE 'idle in transaction%') "
                                  "FROM pg_stat_activity WHERE datname=current_database()"],
                                 capture_output=True, text=True, timeout=5).stdout.strip().split("|")
            row.update(pg_total=int(out[0]), pg_active=int(out[1]), pg_idle_in_tx=int(out[2]))
        except Exception:
            pass
        if backend_pid:
            try:
                cpu, rss = subprocess.run(["ps", "-o", "%cpu=,rss=", "-p", str(backend_pid)], capture_output=True, text=True,
                                          timeout=5).stdout.split()
                row.update(cpu_pct=float(cpu), rss_mb=round(int(rss) / 1024, 1))
            except Exception:
                pass
        samples.append(row)
        stop.wait(2)


def percentile(values, q):
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(q * len(ordered)))], 1) if ordered else None


def summarize(results, seconds):
    by_endpoint = defaultdict(list)
    for _, endpoint, status, ms in results:
        by_endpoint[endpoint].append((status, ms))
    all_ms = [ms for *_, ms in results]
    errors = sum(1 for _, _, status, _ in results if status >= 500)
    return {
        "requests": len(results), "rps": round(len(results) / seconds, 1),
        "p50_ms": percentile(all_ms, 0.50), "p95_ms": percentile(all_ms, 0.95), "p99_ms": percentile(all_ms, 0.99),
        "error_rate": round(errors / max(1, len(results)), 4), "errors_5xx": errors,
        "status_4xx": sum(1 for _, _, status, _ in results if 400 <= status < 500),
        "timeouts": sum(1 for _, _, status, _ in results if status == 599),
        "endpoints": {
            endpoint: {"n": len(items), "p50_ms": percentile([ms for _, ms in items], 0.5),
                       "p95_ms": percentile([ms for _, ms in items], 0.95), "p99_ms": percentile([ms for _, ms in items], 0.99),
                       "errors": sum(1 for status, _ in items if status >= 500)}
            for endpoint, items in sorted(by_endpoint.items(), key=lambda kv: -statistics.median([ms for _, ms in kv[1]]))
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default="http://127.0.0.1:8790")
    parser.add_argument("--users", type=int, default=120)
    parser.add_argument("--stages", default="10,25,50,100")
    parser.add_argument("--stage-seconds", type=int, default=60)
    parser.add_argument("--think", default="1,3")
    parser.add_argument("--db", default="dincr_load")
    parser.add_argument("--backend-pid", type=int, default=0)
    parser.add_argument("--skip-setup", action="store_true")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    think = tuple(float(v) for v in args.think.split(","))

    plans = {}
    if args.skip_setup:
        plans = {n: PLANS[n % len(PLANS)] for n in range(args.users)}
    else:
        started = time.time()
        threads, errors = [], []
        def setup(n):
            try:
                plans[n] = setup_user(args.base, n)
            except Exception as exc:  # reported, stops the run
                errors.append(str(exc))
        for n in range(args.users):
            thread = threading.Thread(target=setup, args=(n,))
            thread.start()
            threads.append(thread)
            if len(threads) % 10 == 0:
                for t in threads[-10:]:
                    t.join()
        for thread in threads:
            thread.join()
        if errors:
            raise SystemExit("setup failed: " + errors[0])
        print(f"setup: {args.users} synthetic users in {time.time() - started:.1f}s")

    report = {"stages": [], "config": vars(args)}
    for concurrency in (int(v) for v in args.stages.split(",")):
        stop, results, samples = threading.Event(), [], []
        sampler = threading.Thread(target=sample_resources, args=(args.db, args.backend_pid, stop, samples))
        sampler.start()
        users = [threading.Thread(target=virtual_user, args=(args.base, n, plans[n], stop, results, think))
                 for n in range(concurrency)]
        begun = time.time()
        for user in users:
            user.start()
        time.sleep(args.stage_seconds)
        stop.set()
        for user in users:
            user.join()
        sampler.join()
        elapsed = time.time() - begun
        stage = {"concurrency": concurrency, "seconds": round(elapsed, 1), **summarize(results, elapsed),
                 "pg_connections_max": max((s.get("pg_total", 0) for s in samples), default=None),
                 "pg_active_max": max((s.get("pg_active", 0) for s in samples), default=None),
                 "pg_idle_in_tx_max": max((s.get("pg_idle_in_tx", 0) for s in samples), default=None),
                 "backend_cpu_pct_max": max((s.get("cpu_pct", 0) for s in samples), default=None),
                 "backend_rss_mb_max": max((s.get("rss_mb", 0) for s in samples), default=None)}
        report["stages"].append(stage)
        print(f"{concurrency:>4} VUs  {stage['rps']:>6} req/s  p50 {stage['p50_ms']} ms  p95 {stage['p95_ms']} ms  "
              f"p99 {stage['p99_ms']} ms  5xx {stage['errors_5xx']}  timeouts {stage['timeouts']}  "
              f"pg max {stage['pg_connections_max']}  cpu max {stage['backend_cpu_pct_max']}%")
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1, default=str)


if __name__ == "__main__":
    main()
