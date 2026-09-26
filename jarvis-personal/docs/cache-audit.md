# In-memory cache audit

Which repeated reads are worth an in-memory cache, and which must never have one.

The backend runs as several Render processes, and possibly several instances. An in-memory cache is **process-local**: each process has its own copy, copies can differ for up to the TTL, and a restart empties them. No cache here gives cross-process consistency. Nothing in this audit needs Redis.

## Rules

A value may be cached only if all of these hold:
- it is global or safely scoped;
- it is not user financial data, identity, permissions, entitlements or mailbox ownership;
- being stale for the TTL is harmless;
- it is read often enough to matter.

Failures are never cached.

## Decisions

| Candidate | Where | Decision | Why |
|---|---|---|---|
| Platform health | `GET /product-ops/health` → `platform_health()` | **Cached, 15 s** (`product_ops/health_cache.py`) | Global, no user data. Clients call it on launch and **on every reconnect**, so an outage turns into a burst of identical aggregate queries against a struggling database. 15 s of staleness is small next to its 15-minute incident window. |
| Feature flags | `core/feature_flags.py` | Already cached, 30 s, cleared in-process on Owner update | Read on every request by the flag middleware. Unchanged. Global kill switches, not per-user entitlements. Exception to "failures are never cached": when the read fails it caches the safe defaults for 30 s, by design. |
| Release policy | `GET /product-ops/release-policy` | **Not cached** | One indexed single-row read per app launch. Negligible gain, and caching would delay a forced update. |
| Plans list | `GET /auth/plans` | **Not cached** | Read only on plan screens. Negligible gain, and it sits next to entitlement state. |
| Store catalog | `GET /product-ops/billing/store/catalog` | **Not cached** | Built from environment variables, with no database read. |
| Category catalog | `finance/category_catalog.py` | Not needed | Static Python data. |
| Subscription / plan state (`_subscription`, `require_feature`) | per request | **Never cache** | Entitlement and authorization: stale state grants or denies access wrongly. It is the largest measured per-request cost (loadtest/RESULTS.md); the fix is to reuse the row within one request, which is outside this audit. |
| Authenticated identity, Supabase user lookup | `auth_middleware` | **Never cache here** | Identity and security. Any change belongs with the auth work and its own security review. |
| Balances, transactions, debts, goals, totals, strategy and dashboards | Users finance reads | **Never cache** | Stale financial truth. The slow strategy dashboard needs query work, not a cache. |
| Mailbox connections, candidates | mail | **Never cache** | Ownership and review state. |

## The platform health cache

- **Key:** none; there is one value per process. **Max entries:** 1.
- **TTL:** 15 s. **Invalidation:** TTL only. A new incident shows up within 15 s.
- **Concurrency:** simultaneous misses in a process share one load and its outcome. If that load fails, every caller waiting on it gets the same error (one database attempt, not one per waiter), and the next call retries. The loader runs outside the lock.
- **Multi-worker:** each process has its own copy, and they can differ for up to 15 s (one worker may answer `operational` while another still answers `degraded`). Health only drives an informational banner and the support screen; nothing uses it for billing, entitlements, security or data writes.
- **Cold start:** the first call queries the database.
- **Failure:** a database error propagates as before and is not cached, so the next call retries.
- **Metrics:**
  - hit, miss and failure counters (no user data) are logged once per load this process runs, which is at most about once per 15 s per process;
  - the response carries `cache.ttl_seconds` and `cache.age_seconds`.
- **Expected effect:**
  - about one health aggregate per process per 15 s under normal operation, instead of one per launch or reconnect. With N workers on M instances that is up to N x M loads per 15 s, not one for the whole platform;
  - under a reconnect storm of N clients in 15 s, database reads drop from N to about 1 per process. No latency improvement has been measured.
