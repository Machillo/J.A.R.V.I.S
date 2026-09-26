"""Short process-local cache for the public platform health.

Clients ask for health when the app opens and on every reconnect, so an outage
turns into a burst of identical aggregate queries against a database that is
already struggling. The value is global (no user, account or authorization
data), and at most HEALTH_TTL_SECONDS of staleness is harmless next to its own
15-minute incident window.

- Key: none, one value per process. Max entries: 1.
- Invalidation: TTL only. A new incident shows up within the TTL.
- Multi-worker: every process keeps its own copy; they can differ for up to
  the TTL. With N workers on M instances there can be up to N x M loads per
  TTL window: about one load per process per TTL, not one per platform.
- Concurrency: simultaneous misses in a process share one load and its
  outcome, success or error. A caller waits for that load at most
  HEALTH_WAIT_SECONDS, then gets an error (5xx). A load stuck longer than that
  (a hung connection) is replaced by the next caller, so the cache heals when
  the database recovers.
- Cold start / failure: a miss queries the database; errors are not cached.
- Metrics: hit/miss/failure counters (no user data), logged once per load
  that this process runs. The response carries only `cache.ttl_seconds` and
  `cache.age_seconds`.
"""

import logging

from backend.core.ttl_cache import TTLValue
from backend.product_ops import service

logger = logging.getLogger(__name__)
HEALTH_TTL_SECONDS = 15
HEALTH_WAIT_SECONDS = 5


platform_health_cache = TTLValue(
    "platform_health", HEALTH_TTL_SECONDS, lambda: service.platform_health(), wait_timeout=HEALTH_WAIT_SECONDS,
)


def cached_platform_health():
    value, age, loaded = platform_health_cache.read()
    if loaded:
        logger.info("platform_health cache miss stats=%s", platform_health_cache.stats())
    return {**value, "cache": {"ttl_seconds": HEALTH_TTL_SECONDS, "age_seconds": round(age, 1)}}
