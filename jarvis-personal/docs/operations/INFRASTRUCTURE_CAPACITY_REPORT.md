# Infrastructure capacity report

Scope: the DINCR backend on Render with Supabase Postgres through Supavisor. This covers #252 (connection reuse) and #255 (authentication off the event loop) as one capacity system.

Capacity is expressed as **concurrency, throughput, latency, errors and saturation**, never as registered users.

Every figure carries a tag:
- **VERIFIED**: read from production or the code;
- **MEASURED**: from the local load harness;
- **CALCULATED**: derived from the tagged figures;
- **ASSUMED**: a documented default, not read from the account;
- **UNKNOWN**: needs a human with dashboard access.

## 1. Facts

| Fact | Value | Tag |
|---|---|---|
| Postgres `max_connections` | 60 (3 reserved for superusers) | VERIFIED 2026-09-26 (`pg_settings`) |
| Supabase services' own connections at rest | 4 (PostgREST, exporter, admin, mgmt API) | VERIFIED 2026-09-26 (`pg_stat_activity`) |
| `idle_in_transaction_session_timeout` | 0 (off) | VERIFIED. #276 sets 60 s for `dincr_app` |
| `authenticator` role | `statement_timeout=8s`, `lock_timeout=8s` | VERIFIED |
| Supavisor mode used by the backend | transaction mode | ASSUMED from `docs/operations/database-connections.md`. Confirm the port (6543) of `DATABASE_URL` on Render |
| Supavisor pool size (server connections) | ? | UNKNOWN: Dashboard → Database → Connection pooling |
| Supavisor max client connections | ? (≈200 for a 60-connection compute size) | UNKNOWN / ASSUMED from Supabase's compute table |
| Render start command, workers, instances, autoscaling | ? | UNKNOWN: no `render.yaml`/Procfile in the repo |
| Render deploy overlap | old and new instance both up during a zero-downtime deploy | ASSUMED (Render default) |
| Threads per process for sync work | 40 (AnyIO default; the code never changes it) | VERIFIED |
| `DINCR_DB_POOL_MAX_IDLE` | code default 8; Render value ? | VERIFIED / UNKNOWN |
| DB connections one request holds at once | **1** (no nested `get_connection` on hot paths) | VERIFIED (code trace, §3) |
| Transaction open during an HTTP call | **none** (Supabase Auth is called before any connection opens; account deletion calls Auth after its commit) | VERIFIED (code trace) |
| Round trips of an authenticated GET before its own query | ≈30, in ≈5 transactions | CALCULATED from the code |

## 2. Load results (local harness, `loadtest/`)

Setup:
- one uvicorn worker, 120 synthetic users, 1–3 s think time, 60 s per stage;
- Auth stand-in at +30 ms.

The macOS runs used a 10 ms DB round trip (latency proxy). The Windows run is recorded without the proxy and without the CPU sampler (`backend_pid` 0), so it has no CPU/RSS figures. Absolute numbers are indicative. Compare the runs with each other.

**Before (main, serialized auth), macOS:** about 2.7 req/s at every load level. p50 was 9 s at 25 users and 18 s at 50 users; at 100 users, **100% of requests timed out**.

**#252 + #255, `DINCR_DB_POOL_MAX_IDLE=8`:**

| Users | req/s | p50 | p95 | p99 | errors | PG conns (idle in tx) | Source |
|---|---|---|---|---|---|---|---|
| 10 | 15.9 | 125 ms | 361 ms | 601 ms | 0 | 9 (3) | Windows `windows-combo-252-255-idle8-r2.json` |
| 25 | 42.3 | 98 ms | 239 ms | 344 ms | 0 | 10 (7) | Windows |
| 50 | 79.1 | 115 ms | 431 ms | 668 ms | 0 | 41 (28) | Windows |
| 100 | 74.6 | 810 ms | 1.42 s | 2.14 s | **0** | 41 (33) | Windows |
| 100 | 80.9 | 668 ms | 1.23 s | 2.0 s | 0 | 41 (34) | macOS (10 ms RTT) `revalidation-2026-09-26-int-idle8-r2.json` |

The first Windows run (`windows-combo-252-255-idle8.json`) had 1.7% 5xx at 50 users and 18% at 100 users. Those came from the **harness**: the Auth stand-in kept the default listen backlog of 5 and refused bursts. `auth_stub.py` now uses a backlog of 256. The second run is clean.

**Reuse off (`=0`), macOS:** 205 errors at 50 users and 2 817 at 100 users. Every block opened a new TCP connection, which exhausted ephemeral ports. Reuse is required.

## 3. Root causes, classified

| Symptom (before) | Class | Explanation |
|---|---|---|
| Throughput flat near 2.7 req/s; p50 of 9 s / 18 s / 30 s | **F** (auth, fixed by #255) | `auth_middleware` ran Supabase verification plus 3 transactions synchronously on the event loop, so every request waited for everyone's authentication |
| Collapse at 100 users (100% timeouts) | **F**, then **H** | Serialized auth; requests queued past the harness's 30 s client timeout |
| Connection errors with reuse off | **I**/**C** (fixed by #252) | Each `get_connection` opened a new connection |
| ≈33 of 41 sessions *idle in transaction* at 100 users | **D + G, magnified by A** | See below |
| Plateau near 75–80 req/s and 41 sessions at 100 users | **B / H** | One process with 40 threads; 41 = 40 threads plus the sampler |

**Why the sessions sit idle in transaction.** psycopg2 is not in autocommit mode.
- Each block runs BEGIN → n statements → COMMIT/ROLLBACK.
- Between two statements the server waits for the client, and it reports that wait as *idle in transaction*.
- An authenticated request spends about 30 round trips in about 5 short transactions:
  - `get_allowed_user_by_email`;
  - the identity block;
  - `enrich_identity`, which calls `_subscription` twice;
  - `require_feature`, which calls `_subscription` again;
  - then the endpoint's own query.
- Each statement executes in under 1 ms, but each round trip costs 10 ms through the proxy. So a session is idle in transaction about 90% of the time, and **active** stays between 3 and 6.

What this is **not**:
- **not a leak:** `release` rolls back and discards anything that is not idle; `test_connection_reuse_pg.py` covers this;
- **not nesting:** a request holds at most one connection (E ruled out);
- **not a network call inside a transaction:** Auth is called before any connection opens.

**Why it matters in production.** In Supavisor transaction mode, each open transaction pins one **server** connection. The DB time a request pins is roughly (round trips × Render→Supavisor RTT) + execution. The fix is to shorten transactions, not to keep them open longer.

## 4. Connection model

Per process, with W workers and I instances:
- client connections ≤ 40 threads borrowing at once + 1 background thread (idle-cache connections are part of the same 40, never extra);
- the idle cache keeps ≤ `DINCR_DB_POOL_MAX_IDLE` of them open between requests.

```
Supavisor clients ≤ I × W × 41 × (2 during a deploy overlap) + cron/scheduler calls + 2 (migration/admin, direct)
Postgres backends ≤ Supavisor pool size + direct (migrations, admin, backups ≈ 2) + Supabase services (≈ 4–10)
                  ≤ 57  (60 − 3 superuser-reserved)
```

| Scenario | Supavisor clients | Postgres backends | Tag |
|---|---|---|---|
| I=1, W=1, steady | ≤ 41 | pool + ≈ 8 | CALCULATED |
| I=1, W=1, deploy overlap | ≤ 82 | pool + ≈ 8 | CALCULATED |
| I=1, W=2, deploy overlap | ≤ 164 (under the ≈200 assumed) | pool + ≈ 8 | CALCULATED |
| I=2, W=2, deploy overlap | ≤ 328: **over** ≈200 | — | CALCULATED: not allowed without a larger compute size |

**`DINCR_DB_POOL_MAX_IDLE`:**
- It bounds only the connections kept open **between** requests. In transaction mode an idle client holds no server connection.
- At 8 per process it adds nothing above the 41-per-process ceiling.
- Measured: 8 and 16 give the same latency; 16 halves reconnect churn. 0 fails under load.
- **The default of 8 is supported by the evidence.** It stays 8. Raise it to 16 only when W × I × 41 × 2 stays under the client limit.

## 5. First bottleneck and envelopes

**FIRST BOTTLENECK (measured): the single backend process.** Between 50 and 100 users:
- throughput stops growing (79 → 75 req/s);
- p50 grows 7× (115 → 810 ms);
- DB *active* sessions stay at 6 or fewer.

Requests queue for the 40 threads, and each thread spends most of its time waiting on DB round trips. In production, with an unknown pool size and RTT, **the Supavisor pool may bind first**:

```
pinned DB time per request T ≈ 35 round trips × RTT;   server-pool bound ≈ pool size / T
RTT 1 ms → T ≈ 35 ms → pool 15 ≈ 430 req/s      RTT 5 ms → T ≈ 175 ms → pool 15 ≈ 85 req/s     (CALCULATED)
```

| Level | Envelope | Basis |
|---|---|---|
| **CURRENT** (I=1, W=1 assumed; #252 + #255 merged) | ≤ **50 concurrent active users ≈ 50–80 req/s**, p95 < 0.5 s | MEASURED locally. The Render→Supavisor RTT and pool size are UNKNOWN, so treat 50 as the ceiling until measured |
| **NEXT** (W=2 on the same instance, or I=2 × W=1) | ≈ 100 concurrent, p95 < 1 s | CALCULATED; needs clients ≤ 164 and a checked pool size |
| **GROWTH** | > 150 concurrent | Needs fewer round trips per request (§6) and a larger compute size / Supavisor client limit before more processes |

## 6. Scaling actions and triggers

| Trigger (sustained 10 min) | Action |
|---|---|
| Backend p95 > 1 s, or p50 > 3× baseline, with DB CPU < 50% | Add a worker (W=2) **after** checking I × W × 41 × 2 < Supavisor client limit |
| Supavisor client connections > 70% of the limit | Do not add processes. Upgrade compute (the client limit follows compute size) |
| Postgres backends > 45 of 60, or Supavisor client wait/queue observed | Raise the Supavisor pool size to at most 80% of `max_connections` minus services (≈ 40), or upgrade compute |
| Any session idle in transaction > 5 s in `pg_stat_activity` | Investigate that code path. Set `idle_in_transaction_session_timeout` (the #276 app role has 60 s) |
| 503 rate > 1% | Check Supabase Auth status (429/5xx now answer 503, never a sign-out) and the DB |
| Backend RSS > 70% of the instance memory, or growth across a run | Investigate before scaling; measured RSS is ≈ 90–120 MB per process |
| Notification cron: jobs in `retry`/`sending` older than 1 h | Check the push service and the scheduler (#264) |

**NEXT SCALING ACTION (code, no new infrastructure):** cut round trips per request.
- Run one-statement reads in autocommit, which goes from 3 round trips to 1.
- Compute `_subscription` once per request instead of 3–4 times.
- Return the already-enriched user from `/auth/me`.
- Fetch the 12 months of `_ledger_totals` in one query.

Each change needs its own PR with a before/after load run. Redis, Celery, asyncpg or a new architecture are **not** justified by the evidence.

## 7. Failure behaviour

| Case | Behaviour | Evidence |
|---|---|---|
| Supabase Auth 4xx | 401 (the session is invalid) | `test_supabase_outage_is_not_a_sign_out.py` |
| Supabase Auth 429/5xx, timeout, connection error | 503, retryable, never a sign-out | same (#255) |
| Slow authentication | Other requests are not stalled | `test_auth_off_event_loop.py` |
| Dead idle pooled connection (pooler restart, idle kill) | Replaced once on its first statement; a failure after the first statement is never retried | `test_connection_reuse_pg.py` (unit, real PG) |
| Uncommitted work or local settings | Never reach the next borrower | same |
| Saturation at 100 users | Latency grows; 0 errors, 0 cross-workspace mixing | load runs + the tenancy test suites |
| Pooler restart **under load**, recovery after load | **NOT VALIDATED** under load (mechanism unit-tested only) | — |

## 8. Observability gaps

- **Available:** pool counters (`connection_pool_stats`, in the product-ops health payload); `strategy_dashboard_complete elapsed_ms`; mail-sync `duration_ms` (PostHog allowlist, no content).
- **Missing in the app:**
  - request latency percentiles, 5xx/429/503 rates per route;
  - DB connection counts over time;
  - job and queue health (notification jobs by status).
- **These rely on Render metrics and the Supabase Observability reports.** Confirm who watches them.
- Add a notification-job status count to the Owner status endpoint before relying on the cron.
- Never log request bodies, tokens, emails or amounts.

## 9. Human actions to close UNKNOWNs

1. **Render:** record the start command, `WEB_CONCURRENCY`/workers, instance count, autoscaling, and `DINCR_DB_POOL_MAX_IDLE`.
2. **Supabase:** record the compute size, the Supavisor pool size and the max client connections, and confirm that `DATABASE_URL` uses port 6543 (transaction mode).
3. **RTT:** measure the Render→Supavisor round trip, for example with `SELECT 1` timed from a Render shell, 20 samples. Put it into §5.
