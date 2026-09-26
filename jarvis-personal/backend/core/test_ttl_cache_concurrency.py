"""Threaded contract of TTLValue: one load per miss wave, shared failures, no leaks.

Deterministic: loaders block on events the test releases, and the test waits
for observable conditions (never for a fixed amount of time).
"""

import gc
import threading
import time
import weakref

import pytest

from backend.core import ttl_cache
from backend.core.ttl_cache import TTLValue

WORKERS = 20
TIMEOUT = 10


class Clock:
    def __init__(self): self.now = 1000.0
    def __call__(self): return self.now


@pytest.fixture
def clock(monkeypatch):
    fake = Clock()
    monkeypatch.setattr(ttl_cache, "monotonic", fake)
    return fake


def wait_until(condition, message):
    idle = threading.Event()
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        if condition():
            return
        idle.wait(0.001)
    raise AssertionError(message)


class BlockingLoader:
    """Counts calls and holds every call until the test releases it."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0
        self.entered = threading.Event()
        self.release = threading.Event()

    def __call__(self):
        self.calls += 1
        outcome = self.outcomes[min(self.calls, len(self.outcomes)) - 1]
        self.entered.set()
        assert self.release.wait(TIMEOUT), "loader was never released"
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def run_concurrently(cache, count=WORKERS):
    """Start `count` callers together; return (threads, results) to join later."""
    barrier = threading.Barrier(count)
    results = [None] * count

    def call(index):
        barrier.wait(TIMEOUT)
        try:
            results[index] = ("ok", cache.get())
        except Exception as exc:  # noqa: BLE001 - the test inspects what each caller saw
            results[index] = ("error", exc)

    threads = [threading.Thread(target=call, args=(index,), daemon=True) for index in range(count)]
    for thread in threads:
        thread.start()
    return threads, results


def join_all(threads):
    for thread in threads:
        thread.join(TIMEOUT)
    assert not any(thread.is_alive() for thread in threads), "a caller is stuck (deadlock)"


def test_cold_misses_run_one_load_then_warm_hits_run_none(clock):
    loader = BlockingLoader([{"status": "operational"}])
    cache = TTLValue("t", 15, loader)

    threads, results = run_concurrently(cache)
    assert loader.entered.wait(TIMEOUT)
    wait_until(lambda: cache.hits == WORKERS - 1, "the other callers never joined the running load")
    loader.release.set()
    join_all(threads)

    assert loader.calls == 1
    assert results == [("ok", {"status": "operational"})] * WORKERS

    threads, results = run_concurrently(cache)
    join_all(threads)
    assert loader.calls == 1
    assert results == [("ok", {"status": "operational"})] * WORKERS
    assert cache.stats() | {"age_seconds": None} == {
        "name": "t", "ttl_seconds": 15, "age_seconds": None, "hits": 2 * WORKERS - 1, "misses": 1, "failures": 0,
    }


def test_expiry_under_concurrency_runs_exactly_one_refresh(clock):
    loader = BlockingLoader([{"version": 1}, {"version": 2}])
    cache = TTLValue("t", 15, loader)
    loader.release.set()
    assert cache.get() == {"version": 1}

    loader.release.clear()
    clock.now += 15
    threads, results = run_concurrently(cache)
    wait_until(lambda: loader.calls == 2, "no refresh started after expiry")
    wait_until(lambda: cache.hits == WORKERS - 1, "the other callers never joined the refresh")
    loader.release.set()
    join_all(threads)

    assert loader.calls == 2
    assert results == [("ok", {"version": 2})] * WORKERS
    assert cache.get() == {"version": 2}
    assert loader.calls == 2


def test_waiters_share_the_single_failed_load_and_the_next_call_recovers(clock):
    failure = RuntimeError("database unavailable")
    loader = BlockingLoader([failure, {"status": "operational"}])
    cache = TTLValue("t", 15, loader)

    threads, results = run_concurrently(cache)
    assert loader.entered.wait(TIMEOUT)
    wait_until(lambda: cache.hits == WORKERS - 1, "the other callers never joined the failing load")
    loader.release.set()
    join_all(threads)

    # One database attempt for the whole wave; every caller sees the same error.
    assert loader.calls == 1
    assert all(kind == "error" and exc is failure for kind, exc in results)
    assert cache.stats()["failures"] == 1
    # The failure is not cached and nothing stays locked: the next call reloads.
    assert cache._lock.acquire(timeout=1)
    cache._lock.release()
    assert cache.get() == {"status": "operational"}
    assert loader.calls == 2
    assert cache.get() == {"status": "operational"}
    assert loader.calls == 2


def test_read_reports_the_age_of_the_value_it_returns(clock):
    versions = iter(range(1, 10))
    cache = TTLValue("t", 15, lambda: {"version": next(versions)})

    assert cache.read() == ({"version": 1}, 0.0, True)
    clock.now += 4
    assert cache.read() == ({"version": 1}, 4.0, False)
    clock.now += 10.5
    assert cache.read() == ({"version": 1}, 14.5, False)
    clock.now += 1
    assert cache.read() == ({"version": 2}, 0.0, True)


def test_repeated_reloads_keep_one_value_and_no_threads_or_errors(clock):
    class Value:
        pass

    produced = []

    def load():
        value = Value()
        produced.append(weakref.ref(value))
        if len(produced) % 3 == 0:
            raise RuntimeError("transient")
        return value

    cache = TTLValue("t", 15, load)
    threads_before = threading.active_count()
    for _ in range(300):
        clock.now += 15
        try:
            cache.get()
        except RuntimeError:
            pass
    gc.collect()

    alive = [ref for ref in produced if ref() is not None]
    assert len(alive) == 1 and alive[0]() is cache._value
    assert cache._load is None
    assert threading.active_count() == threads_before
    assert set(vars(cache)) == {
        "name", "ttl_seconds", "_loader", "_lock", "_value", "_loaded_at", "_load", "hits", "misses", "failures",
    }
