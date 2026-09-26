# Load test results — pre-launch block (2026-09-25)

**Environment:** local and isolated (see README.md).
- One uvicorn worker, 120 synthetic users (40% Free, 30% Basic, 30% VIP).
- Database latency 5 ms per direction, Auth stand-in +30 ms.
- Stages of 10 / 25 / 50 / 100 concurrent virtual users, 60 s each, 1–3 s of think time.
- The same seeded data in every run.

**Absolute numbers are indicative** (one laptop, no TLS, no Supavisor); compare the runs with each other.

## Before (`origin/main` 5f2e36f): `results/baseline-origin-main.json`

| Users | req/s | p50 | p95 | p99 | 5xx / timeouts | Postgres conns (idle in tx) | Backend CPU |
|---|---|---|---|---|---|---|---|
| 10 | 2.6 | 3.6 s | 4.5 s | 6.9 s | 0 | 11 (10) | 9% |
| 25 | 2.7 | 9.0 s | 9.9 s | 15.6 s | 0 | 24 (16) | 15% |
| 50 | 2.7 | 18.6 s | 21.5 s | 30.0 s | 7 | 42 (33) | 18% |
| 100 | 2.9 | 30 s (timeout) | 30 s | 30 s | **259 (100%)** | — | 13% |

**Diagnosis:**
- Throughput stays near **2.7 req/s whatever the load**, while CPU never passes 18%. The work is serialized, not starved.
- `auth_middleware` (async) ran authentication synchronously on the event loop: the Supabase HTTP call plus 3 transactions and 14 statements, including 2 writes per request.
- So every request of the process waited for every other request's authentication.
- Setting up the 120 synthetic users took 11 minutes for the same reason.

## Fixes, measured

1. **Authentication off the event loop** (`perf/auth-off-event-loop`): authentication, feature-flag lookup and idempotency I/O run in the thread pool. A regression test shows `/status` waited 2.43 s behind six slow authentications before, and now answers at once.
2. **Reuse of authenticated database connections** (#252).
3. **No redundant identity writes** (`perf/auth-off-event-loop`): when the identity is already bound to the same Auth user with the same role and was seen in the last 5 minutes, the two `last_login_at` updates are skipped. The binding checks still run.

**After fixes 1 and 2** (every open PR of the block integrated): `results/after-event-loop-and-reuse.json`

| Users | req/s | p50 | p95 | p99 | 5xx / timeouts | Postgres conns (idle in tx) | Backend CPU |
|---|---|---|---|---|---|---|---|
| 10 | 10.1 | 458 ms | 716 ms | 1.8 s | 0 | 11 (7) | 19% |
| 25 | 25.0 | 458 ms | 697 ms | 1.9 s | 0 | 20 | 35% |
| 50 | 51.1 | 434 ms | 684 ms | 1.7 s | 0 | 41 | 35% |
| 100 | 80.7 | 689 ms | 1.27 s | 2.0 s | 0 | 41 (38) | 38% |

**After fixes 1, 2 and 3:** `results/after-all-fixes.json`

| Users | req/s | p50 | p95 | p99 | 5xx / timeouts | Postgres conns | Backend CPU |
|---|---|---|---|---|---|---|---|
| 10 | 10.0 | 474 ms | 745 ms | 2.0 s | 0 | 11 | 17% |
| 25 | 24.8 | 452 ms | 711 ms | 1.9 s | 0 | 20 | 32% |
| 50 | 51.1 | 410 ms | 680 ms | 1.7 s | 0 | 41 | 32% |
| 100 | **83.0** | **635 ms** | **1.21 s** | **1.9 s** | **0** | 41 | 38% |

**At 100 concurrent users:**
- 28× the throughput (2.9 → 83 req/s).
- p50 from a 30 s timeout to 0.63 s.
- Errors from 100% to 0.

Fix 3 alone is modest here (about −8% p50 at 100 users). The harness does not issue one user's requests in parallel, which is where the removed row locks hurt most.

## Remaining bottlenecks (measured, not changed in this block)

1. **Per-request database round trips.** A typical screen costs 5 transaction blocks and 21–28 statements.
   - `_subscription` (plan state) runs **4 times per request**: 12 statements, from `enrich_identity` and `require_feature`.
   - Reusing the row read inside the request would save ~6 round trips (~60 ms at 10 ms RTT).
   - Deferred: it touches `backend/auth/saas.py`, which #248 and #253 also change.
2. **`/user-product/vip/strategy-dashboard`:** 32 transaction blocks and 84 statements, p50 ~1.9 s. It is the slowest screen, a query-per-period pattern (12× salary sums).
3. **Saturation at 100 users: the thread pool.**
   - Postgres connections flatten at 41, which is the anyio default of 40 threads plus the sampler.
   - Almost all of them are *idle in transaction*: read-only blocks keep their transaction open until the block ends, which includes Python work and network waits.
   - **This matters most in production.** In Supavisor transaction mode, every open transaction pins a server connection, so the effective concurrency is the plan's Supavisor pool size, not the 40 threads.
   - **Before raising the thread pool:**
     - read the Supavisor pool size for the plan;
     - consider autocommit (or short explicit transactions) for read-only blocks;
     - add `idle_in_transaction_session_timeout` for the app role.
4. **Auth HTTP call.** Every request calls Supabase `/auth/v1/user` (30 ms here). Verifying the Supabase JWT locally with JWKS, plus a short cache, would remove it. That is a security-sensitive change and needs its own review.

## Repeat before a release

Follow README.md. Run the before/after on the same seeded database, and compare p50/p95 and errors at 100 users with the numbers above.

# Revalidation — 2026-09-26 (after the block's merges)

The same harness, settings and seeded data as above.

**Code:**
- `origin/main` `ccbd3b0`, which includes #253 and #260;
- versus the same main with #255 (auth off the event loop, synced with #260) and #252 (connection reuse) merged locally.

**Pool sizes:** `DINCR_DB_POOL_MAX_IDLE` 0 (reuse off), 8 (default) and 16.

**New measurement: connection churn.** New Postgres sessions per second, sampled every 0.5 s from `pg_stat_activity`. It is the local proxy for the rate of new authenticated connections Supavisor would see. At 0 the sampler undercounts, because many sessions last less than 0.5 s.

**The idle 8 and idle 16 runs were repeated.** The first attempts overlapped other work on the machine, which added isolated p99 outliers. Reports: `results/revalidation-2026-09-26-*.json`.

| Run | Users | req/s | p50 | p95 | p99 | 5xx / timeouts | PG conns (idle in tx) | New conns/s | CPU | RSS |
|---|---|---|---|---|---|---|---|---|---|---|
| main | 10 | 2.7 | 3.6 s | 4.5 s | 4.5 s | 0 | 7 (6) | 4.6 | 12% | 90 MB |
| main | 50 | 2.7 | 18.1 s | 21.2 s | 30.0 s | 9 | 42 (41) | 4.2 | 20% | 91 MB |
| main | 100 | 3.2 | 30 s | 30 s | 30 s | **292 (100%)** | 2 | 3.4 | 15% | 88 MB |
| reuse off (0) | 50 | 48.7 | 464 ms | 713 ms | 2.1 s | **205** | 38 (24) | ≥44.7 | 39% | 106 MB |
| reuse off (0) | 100 | 68.7 | 512 ms | 1.42 s | 2.2 s | **2 817** | 38 (30) | ≥34.6 | 87% | 117 MB |
| idle 8 | 10 | 10.1 | 453 ms | 715 ms | 1.87 s | 0 | 11 (7) | 2.1 | 17% | 92 MB |
| idle 8 | 50 | 50.8 | 423 ms | 677 ms | 1.75 s | 0 | 40 (31) | 5.7 | 43% | 93 MB |
| idle 8 | 100 | 80.9 | 668 ms | 1.23 s | 2.0 s | 0 | 41 (34) | 6.4 | 52% | 87 MB |
| idle 16 | 10 | 10.1 | 452 ms | 722 ms | 1.88 s | 0 | 12 (7) | 2.0 | 19% | 100 MB |
| idle 16 | 50 | 51.5 | 426 ms | 683 ms | 1.76 s | 0 | 41 (26) | 3.1 | 45% | 93 MB |
| idle 16 | 100 | **81.6** | **677 ms** | **1.21 s** | **2.0 s** | **0** | 41 (36) | **2.7** | 55% | 96 MB |

`GET /auth/me` p50 at 100 users:
- main: 30 s (timeouts);
- idle 8: 0.62 s;
- idle 16: 0.60 s.

That includes the 30 ms Auth stand-in.

**Findings:**
1. **Main is still serialized:** about 3 req/s whatever the load, and every request times out at 100 users. #255 and #252 remain release-blocking for any real concurrency.
2. **Without reuse, the process runs out of connections.** Every DB block opens a TCP connection. At 50–100 users the machine ran out of ephemeral ports (`Errno 49`), giving 205 and then 2 817 errors. In production the same churn would hit Supavisor as one TLS handshake and one authentication per block.
3. **Pool sizing:** 8 and 16 give the same latency and throughput. 16 halves the churn at 50–100 users (2.7–3.1/s vs 5.7–6.4/s).
   - **Recommendation:** `DINCR_DB_POOL_MAX_IDLE=16` per worker, provided that `instances × workers × 16` stays well under the plan's Supavisor **client** connection limit.
   - The code default stays 8.
4. **Idle in transaction** stays high: 34–36 of 41 connections at 100 users.
   - In Supavisor transaction mode, each open transaction pins a server connection. Effective concurrency is therefore the plan's pool size, not the 40 threads.
   - The application role (#276) ends such sessions after 60 s.
   - **Next steps (not in this block):** autocommit, or short transactions, for read-only blocks.

**HUMAN-ONLY facts needed to finish the sizing:**
- Render's instance count and workers per instance;
- the Supabase plan's Supavisor pool size and max client connections;
- the actual round trip from Render to Supavisor (the proxy assumes 10 ms).
