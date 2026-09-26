"""Short process-local cache for the public platform health.

Clients ask for health when the app opens and on every reconnect, so an outage
turns into a burst of identical aggregate queries against a database that is
already struggling. The value is global (no user, account or authorization
data), and at most HEALTH_TTL_SECONDS of staleness is harmless next to its own
15-minute incident window.

- Key: none, one value per process. Max entries: 1.
- Invalidation: TTL only. A new incident shows up within the TTL.
- Multi-worker: every process keeps its own copy; they can differ for up to
  the TTL.
- Cold start / failure: a miss queries the database; errors are not cached.
- Metrics: hit/miss/failure counters, logged on each miss (at most once per
  TTL per process) and returned in the response as `cache`.
"""

import logging

from backend.core.ttl_cache import TTLValue
from backend.product_ops import service

logger = logging.getLogger(__name__)
HEALTH_TTL_SECONDS = 15


platform_health_cache = TTLValue("platform_health", HEALTH_TTL_SECONDS, lambda: service.platform_health())


def cached_platform_health():
    misses = platform_health_cache.misses
    value = platform_health_cache.get()
    stats = platform_health_cache.stats()
    if stats["misses"] != misses:
        logger.info("platform_health cache miss stats=%s", stats)
    return {**value, "cache": {"ttl_seconds": stats["ttl_seconds"], "age_seconds": stats["age_seconds"]}}
