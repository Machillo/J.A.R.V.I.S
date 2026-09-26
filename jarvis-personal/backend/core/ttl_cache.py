"""One process-local value, reloaded at most once per TTL.

Only for global, non-user, non-authorization data whose staleness for a few
seconds is harmless. Every Render process and instance keeps its own copy: this
is not a shared cache and gives no cross-process consistency.
"""

from __future__ import annotations

import threading
from time import monotonic
from typing import Any, Callable


class TTLValue:
    def __init__(self, name: str, ttl_seconds: float, loader: Callable[[], Any]):
        self.name = name
        self.ttl_seconds = ttl_seconds
        self._loader = loader
        self._lock = threading.Lock()
        self._value: Any = None
        self._loaded_at: float | None = None
        self.hits = 0
        self.misses = 0
        self.failures = 0

    def get(self) -> Any:
        # The lock also makes concurrent misses wait for one load instead of
        # all hitting the database at once.
        with self._lock:
            now = monotonic()
            if self._loaded_at is not None and now - self._loaded_at < self.ttl_seconds:
                self.hits += 1
                return self._value
            self.misses += 1
            try:
                value = self._loader()
            except Exception:
                # A failure is never cached: the next call tries again.
                self.failures += 1
                raise
            self._value, self._loaded_at = value, monotonic()
            return value

    def clear(self) -> None:
        with self._lock:
            self._value, self._loaded_at = None, None

    def stats(self) -> dict[str, Any]:
        with self._lock:
            age = None if self._loaded_at is None else round(monotonic() - self._loaded_at, 1)
            return {
                "name": self.name, "ttl_seconds": self.ttl_seconds, "age_seconds": age,
                "hits": self.hits, "misses": self.misses, "failures": self.failures,
            }
