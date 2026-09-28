# Database connections (FastAPI on Render → Supavisor → Postgres)

## Audited architecture (2026-09-25)

**Driver and style.**
- `psycopg2` (synchronous).
- FastAPI runs the `def` endpoints in its thread pool.
- Every database access goes through `backend.core.database.get_connection()` (~300 call sites), used as a context manager: one transaction per `with` block. Nested blocks inside a request are normal.

**How production connects.** `DATABASE_URL` points at Supabase's **Supavisor in transaction mode** (port 6543), as `postgres`.
- **Supavisor logs** (read-only check): every backend connection is `mode: transaction`. Backups, migrations and read-only scripts use session mode.
- **Postgres** sees the backend as `application_name = 'Supavisor'`. Supavisor itself sees the client's `dincr-backend`. See the #245 residual risk: `application_name` is not a security boundary.
- **`max_connections` = 60** on the Postgres server. Supavisor owns the server-side pool, so client connections never map 1:1 to Postgres connections.

**Before this change.**
- Every `get_connection()` opened a new TCP + TLS + SCRAM connection to Supavisor and closed it at the end of the block. There was no pool in the app.
- Supavisor logged ~7,400 client authentications in 24 h, and ~2,300 in 30 minutes of manual smoke tests.

## Final architecture

**Who pools what.**

| Layer | Pooling | Limit |
|---|---|---|
| Postgres | — | `max_connections` 60 |
| Supavisor (transaction mode) | Server connections, one per transaction while it runs | Supabase plan pool size |
| Backend process | **Reuse of idle client connections** (`_IdleConnections` in `backend/core/database.py`) | `DINCR_DB_POOL_MAX_IDLE` idle per process |

**Not a second blocking pool.** An idle client connection in transaction mode holds no Postgres connection, so there is no harmful double pooling.
- Acquiring **never waits**. If no idle connection is free, a new one opens exactly as before. Nested `get_connection()` calls therefore cannot deadlock on an exhausted pool.
- Concurrency stays bounded by the thread pool and by Supavisor, as it was.

**Settings** (environment variables; the defaults suit one Render instance):

| Variable | Default | Meaning |
|---|---|---|
| `DINCR_DB_POOL_MAX_IDLE` | 8 | Idle connections kept per process. `0` turns reuse off (the previous behavior). |
| `DINCR_DB_POOL_IDLE_SECONDS` | 300 | An idle connection unused for this long is closed (swept on every acquire and release). |
| `DINCR_DB_POOL_MAX_AGE_SECONDS` | 600 | A connection older than this is not kept when it is released, and is swept while idle. A connection in use is never interrupted. |

**Health and failure behavior.**
- **On release:** any open transaction is rolled back. Uncommitted work and `set_config(..., true)` never reach the next caller, and Supavisor never keeps a server connection pinned by an idle transaction. A connection that is closed, in an unknown state, or in autocommit is discarded.
- **Dead connection** (pooler restart, network): TCP keepalives detect it. If a reused connection fails on its **first** statement, before anything ran in that transaction, it is replaced once and the statement runs again. A failure after the first statement is never retried, so no write can run twice.
- **Use after release fails.** A late `execute`, `commit` or `rollback` on a block that already ended raises `InterfaceError`. That connection may already be running another request's transaction.
- **Fork safety.** A forked child forgets the parent's idle sockets without closing them.
- **Keyed by DSN and `application_name`.** A script (`dincr-script`) never receives a backend (`dincr-backend`) connection. The #245 delete guard relies on that name.

**Multiple workers.**
- The cache is per process. Each uvicorn worker keeps at most `DINCR_DB_POOL_MAX_IDLE` idle client connections, which are cheap for Supavisor.
- Peak client connections equal the peak of concurrent `get_connection()` blocks, as before this change.

**Migrations and scripts.** `apply_migration.py`, `db_backup_verify.py` and the read-only checks open their own direct `psycopg2` connections, through Supavisor's session mode or directly. They do not use this cache.

**Observability.**
- `connection_pool_stats()` returns counts for opened, reused, returned, discarded and idle. They appear under `database_connections` in the Owner dashboard (`GET /product-ops/owner/dashboard`, Owner only; counts only), together with `reconnected`, the count of dead idle connections that were replaced. Each replacement also logs one line with no DSN or host.
- Supavisor logs show the client authentications per minute.

## Measured effect (local benchmark, `get_connection()` plus one query)

Measured through a local proxy that adds network delay, against local Postgres without TLS, 40 iterations each:

| Delay per direction | Reuse off, p50 | Reuse on, p50 |
|---|---|---|
| 2 ms | 33.8 ms | 19.9 ms |
| 10 ms | 110.6 ms | 74.8 ms |
| 35 ms | 310.2 ms | 226.3 ms |

In production, TLS and SCRAM add more round trips to the handshake that reuse avoids, so the saving per `get_connection()` is larger. The load test (section 7 of the pre-launch block) measures the whole application.

## Before enabling in production

- Check the Supabase plan's Supavisor client-connection limit against `DINCR_DB_POOL_MAX_IDLE` × workers × instances, doubled during a deploy overlap, plus peak concurrency.
- Confirm the Render start command (number of workers, whether `--preload` is used).

## Rollback

Set `DINCR_DB_POOL_MAX_IDLE=0` on Render and restart. No code or database change is needed.
