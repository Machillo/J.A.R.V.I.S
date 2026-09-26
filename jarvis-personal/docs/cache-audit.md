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
| Feature flags | `core/feature_flags.py` | Already cached, 30 s, cleared in-process on Owner update | Read on every request by the flag middleware. Unchanged. |
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
- **Concurrency:** a lock collapses simultaneous misses into one database query.
- **Multi-worker:** each process has its own copy, and they can differ for up to 15 s.
- **Cold start:** the first call queries the database.
- **Failure:** a database error propagates as before and is not cached, so the next call retries.
- **Metrics:**
  - hit, miss and failure counters are logged on each miss, which happens at most once per 15 s per process;
  - the response carries `cache.ttl_seconds` and `cache.age_seconds`.
- **Expected effect:**
  - per process, at most one health aggregate every 15 s, instead of one per launch or reconnect;
  - under a reconnect storm of N clients in 15 s, database reads drop from N to 1 per process.
