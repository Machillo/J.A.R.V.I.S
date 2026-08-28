# Performance and cleanup checkpoint

This baseline intentionally contains only JARVIS Users Basic modules.

Performance changes:
- Reuses PostgreSQL connections through a thread-safe local connection pool.
- Reuses the HTTP session used to validate Supabase tokens.
- Caches only a successfully verified Supabase identity for a short TTL; profile status and subscription are still read from PostgreSQL on each authenticated request.
- Auth profile/subscription work is performed with one pooled DB connection instead of several new connections.
- Finance summary uses one SQL round trip instead of four sequential queries.
- Authentication runs in a worker thread so blocking network/database I/O does not block FastAPI's event loop.
- React StrictMode was removed from the local entrypoint to avoid duplicate development-only API calls.
- New income/expense/overtime rows are inserted into UI state immediately after a successful POST instead of re-fetching all three lists.

No database migration is required for these performance changes.
