"""One process-local value, reloaded at most once per TTL.

Only for global, non-user, non-authorization data whose staleness for a few
seconds is harmless. Every Render process and instance keeps its own copy: this
is not a shared cache and gives no cross-process consistency.
"""

from __future__ import annotations

import threading
from time import monotonic
from typing import Any, Callable


class TTLLoadTimeout(TimeoutError):
    """The shared in-flight load did not finish within the wait timeout."""


class TTLLoadFailed(RuntimeError):
    """The shared in-flight load failed; the original error is the cause."""


class _Load:
    """One in-flight load, shared by every caller that arrives while it runs."""

    def __init__(self, started_at: float):
        self.started_at = started_at
        self.done = threading.Event()
        self.value: Any = None
        self.error: BaseException | None = None
        self.loaded_at = 0.0


class TTLValue:
    def __init__(self, name: str, ttl_seconds: float, loader: Callable[[], Any], wait_timeout: float = 5.0):
        self.name = name
        self.ttl_seconds = ttl_seconds
        self.wait_timeout = wait_timeout
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

        A caller waits for someone else's load at most `wait_timeout` seconds,
        then raises TTLLoadTimeout. A load running longer than that is treated
        as stuck (for example a half-open connection): the next caller starts
        a new one, so the cache heals once the database answers again, and the
        stuck load can no longer overwrite the value or the in-flight slot.
        """
        with self._lock:
            now = monotonic()
            if self._loaded_at is not None and now - self._loaded_at < self.ttl_seconds:
                self.hits += 1
                return self._value, now - self._loaded_at, False
            load = self._load
            leader = load is None or now - load.started_at >= self.wait_timeout
            if leader:
                load = self._load = _Load(now)
                self.misses += 1
            else:
                self.hits += 1
        if not leader:
            if not load.done.wait(self.wait_timeout):
                raise TTLLoadTimeout(f"{self.name}: shared load still running after {self.wait_timeout}s")
            if load.error is not None:
                raise TTLLoadFailed(f"{self.name}: shared load failed") from load.error
            return load.value, max(0.0, monotonic() - load.loaded_at), False
        try:
            value = self._loader()
        except BaseException as exc:
            load.error = exc
            with self._lock:
                self.failures += 1
                if self._load is load:
                    self._load = None
            raise
        else:
            with self._lock:
                load.value, load.loaded_at = value, monotonic()
                if self._load is load:
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
