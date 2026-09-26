import threading
import time

import pytest

from backend.core import ttl_cache
from backend.core.ttl_cache import TTLValue
from backend.product_ops import health_cache, routes


class Clock:
    def __init__(self): self.now = 1000.0
    def __call__(self): return self.now


@pytest.fixture
def clock(monkeypatch):
    fake = Clock()
    monkeypatch.setattr(ttl_cache, "monotonic", fake)
    return fake


def test_value_is_reused_within_the_ttl_and_reloaded_after(clock):
    calls = []
    cache = TTLValue("t", 15, lambda: calls.append(1) or len(calls))
    assert cache.get() == 1
    clock.now += 14.9
    assert cache.get() == 1
    clock.now += 0.2
    assert cache.get() == 2
    assert cache.stats() | {"age_seconds": None} == {
        "name": "t", "ttl_seconds": 15, "age_seconds": None, "hits": 1, "misses": 2, "failures": 0,
    }


def test_failures_are_not_cached(clock):
    outcomes = iter([RuntimeError("db down"), {"status": "operational"}])

    def load():
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    cache = TTLValue("t", 15, load)
    with pytest.raises(RuntimeError):
        cache.get()
    assert cache.get() == {"status": "operational"}
    assert cache.stats()["failures"] == 1


def test_clear_forces_a_reload(clock):
    calls = []
    cache = TTLValue("t", 15, lambda: calls.append(1) or len(calls))
    cache.get()
    cache.clear()
    assert cache.get() == 2


def test_concurrent_cold_misses_run_one_load():
    calls = []
    started = threading.Event()

    def slow_load():
        calls.append(1)
        started.set()
        time.sleep(0.05)
        return {"status": "operational"}

    cache = TTLValue("t", 15, slow_load)
    threads = [threading.Thread(target=cache.get) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(calls) == 1
    assert cache.stats()["hits"] == 19


def test_health_route_serves_the_cached_global_value(monkeypatch, clock):
    calls = []

    def platform_health():
        calls.append(1)
        return {"status": "degraded", "active_incidents": 2, "affected_accounts": 2}

    monkeypatch.setattr(health_cache.service, "platform_health", platform_health)
    health_cache.platform_health_cache.clear()
    try:
        first = routes.health()
        second = routes.health()
    finally:
        health_cache.platform_health_cache.clear()
    assert len(calls) == 1
    assert first["status"] == second["status"] == "degraded"
    assert second["cache"] == {"ttl_seconds": health_cache.HEALTH_TTL_SECONDS, "age_seconds": 0.0}
    assert not {"email", "account_id", "workspace_id"} & set(second)
