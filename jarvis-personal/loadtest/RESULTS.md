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
