# DINCR load test (~100 concurrent users)

A reproducible load test of the real backend, **isolated from production**.
- **Backend:** a local backend process running the branch under test.
- **Database:** a local PostgreSQL built from the production **schema** plus catalog rows only (plans, features, categories, release policies). Every user and every financial row is **synthetic**, created through the API.
- **Auth:** a local stand-in for Supabase Auth.
- **Network:** a TCP proxy that adds network latency to the database.

`run_load.py` refuses any base URL other than `127.0.0.1` / `localhost`. Never point any part of this at production.

## Files

| File | Role |
|---|---|
| `prepare_db.sh` | Builds the database: public schema + catalog rows from a `pg_dump -Fc` file, Supabase stubs (auth, Vault, roles), all feature flags enabled, optional newer migrations. Prints `personal rows (must be 0)`. |
| `auth_stub.py` | Answers `GET /auth/v1/user` for tokens `loadtest-<n>` (synthetic Google identities `loadtest-<n>@example.test`). `AUTH_STUB_DELAY_MS` models the real network call. |
| `latency_proxy.py` | Adds `PROXY_DELAY_MS` per direction between the backend and Postgres. |
| `start_backend.sh` | Starts the backend with a clean environment against the load database. |
| `run_load.py` | Seeds N synthetic users through the API, then runs the stages and writes a JSON report. |

## Workload

- **Users:** 120 synthetic users: 40% Free, 30% Basic, 30% VIP (paid plans through the launch promotion).
- **Setup, per user:** sign in (`/auth/me`), accept the legal documents, profile, plan, onboarding, income, 2 debts, a goal, 5 expenses, and a budget for Basic/VIP.
- **Virtual user loop:**
  - open the app (`/auth/me`), then 3 of their plan's screens (dashboard, movements, budget, debts, goals, strategy);
  - 1–3 s of think time;
  - 10% of loops add an expense; 3% of Basic/VIP loops save the budget.
- **Stages:** 10 → 25 → 50 → 100 concurrent users, 60 s each.
- **Measured:** requests/s; p50, p95 and p99 overall and per endpoint; 5xx; timeouts; Postgres connections (total, active, idle in transaction); backend CPU and RSS.

## Run it

```bash
export PATH=/opt/homebrew/opt/postgresql@17/bin:$PATH
PY=<python with backend/requirements.txt installed>
DINCR_SCHEMA_DUMP=<BACKUP_VERIFIED dump.pgc> PYTHON=$PY ./loadtest/prepare_db.sh dincr_load
psql -d postgres -c "CREATE DATABASE dincr_load_template TEMPLATE dincr_load"   # reusable clean copy
AUTH_STUB_DELAY_MS=30 $PY loadtest/auth_stub.py &
PROXY_DELAY_MS=5 $PY loadtest/latency_proxy.py &
PYTHON=$PY ./loadtest/start_backend.sh &
$PY loadtest/run_load.py --users 120 --stages 10,25,50,100 --stage-seconds 60 \
    --backend-pid $(pgrep -f "uvicorn backend.main:app" | head -1) --out loadtest/results/<name>.json
```

- **Comparing two branches on the same data:** after the first run's setup, copy the seeded database (`CREATE DATABASE dincr_load_seeded TEMPLATE dincr_load`).
- **For each branch:**
  1. recreate `dincr_load` from `dincr_load_seeded`;
  2. apply that branch's new migrations;
  3. start its backend;
  4. run with `--skip-setup`.

## Assumptions to keep in mind

- **Database latency:** the proxy adds 5 ms per direction (10 ms round trip), a same-region cloud hop. Adjust it to what Render → Supavisor shows.
- **No TLS, no Supavisor:** local Postgres is direct, so the production handshake is cheaper here than in production. That means connection reuse gains are **understated** here.
- **Auth:** the stub adds 30 ms per request to model the Supabase `/auth/v1/user` call.
- **One uvicorn worker and one machine:** the load generator shares the CPU with the backend. Absolute numbers are indicative; compare runs, not absolute values.

## Results

Reports are in `loadtest/results/`. The before/after comparison for the pre-launch block is in `loadtest/RESULTS.md`.
