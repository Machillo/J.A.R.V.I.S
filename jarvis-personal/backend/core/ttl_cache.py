"""One process-local value, reloaded at most once per TTL.

Only for global, non-user, non-authorization data whose staleness for a few
seconds is harmless. Every Render process and instance keeps its own copy: this
is not a shared cache and gives no cross-process consistency.
"""

from __future__ import annotations

import threading
from time import monotonic
from typing import Any, Callable


class _Load:
    """One in-flight load, shared by every caller that arrives while it runs."""

    def __init__(self):
        self.done = threading.Event()
        self.value: Any = None
        self.error: BaseException | None = None
        self.loaded_at = 0.0


class TTLValue:
    def __init__(self, name: str, ttl_seconds: float, loader: Callable[[], Any]):
        self.name = name
        self.ttl_seconds = ttl_seconds
        self._loader = loader
        self._lock = threading.Lock()
        self._value: Any = None
        self._loaded_at: float | None = None
        self._load: _Load | None = None
        self.hits = 0
        self.misses = 0
        self.failures = 0

    def get(self) -> Any:
        return self.read()[0]

    def read(self) -> tuple[Any, float, bool]:
        """Return (value, its age in seconds, whether this call ran the loader).

        Concurrent misses share one load and its outcome, success or error, so a
        failing database is queried once per wave instead of once per waiter.
        The loader runs outside the lock. A failure is never cached: the next
        call after it tries again.
        """
        with self._lock:
            now = monotonic()
            if self._loaded_at is not None and now - self._loaded_at < self.ttl_seconds:
                self.hits += 1
                return self._value, now - self._loaded_at, False
            load, leader = self._load, self._load is None
            if leader:
                load = self._load = _Load()
                self.misses += 1
            else:
                self.hits += 1
        if not leader:
            load.done.wait()
            if load.error is not None:
                raise load.error
            return load.value, max(0.0, monotonic() - load.loaded_at), False
        try:
            value = self._loader()
        except BaseException as exc:
            load.error = exc
            with self._lock:
                self.failures += 1
                self._load = None
            raise
        else:
            with self._lock:
                load.value, load.loaded_at = value, monotonic()
                self._value, self._loaded_at, self._load = value, load.loaded_at, None
            return value, 0.0, True
        finally:
            load.done.set()

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
