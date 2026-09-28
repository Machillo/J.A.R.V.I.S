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

    # One database attempt for the whole wave; every caller sees that error.
    assert loader.calls == 1
    assert sum(exc is failure for _, exc in results) == 1
    assert all(kind == "error" and (exc is failure or exc.__cause__ is failure) for kind, exc in results)
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
        "name", "ttl_seconds", "wait_timeout", "_loader", "_lock", "_value", "_loaded_at", "_load",
        "hits", "misses", "failures",
    }


class HangingFirstLoader:
    """First call hangs until released (a half-open connection); later calls answer at once."""

    def __init__(self):
        self.calls = 0
        self.entered = threading.Event()
        self.release = threading.Event()

    def __call__(self):
        self.calls += 1
        call = self.calls
        if call == 1:
            self.entered.set()
            assert self.release.wait(TIMEOUT), "hung load was never released"
        return {"version": call}


def start_leader(cache):
    outcome = {}

    def lead():
        outcome["value"] = cache.get()

    thread = threading.Thread(target=lead, daemon=True)
    thread.start()
    return thread, outcome


def test_a_waiter_of_a_hung_load_gives_up_after_the_wait_timeout(clock):
    loader = HangingFirstLoader()
    cache = TTLValue("t", 15, loader, wait_timeout=0.2)
    leader, _ = start_leader(cache)
    assert loader.entered.wait(TIMEOUT)

    started = time.monotonic()
    with pytest.raises(ttl_cache.TTLLoadTimeout):
        cache.get()
    assert time.monotonic() - started < TIMEOUT
    # The waiter leaves the leader's load alone: still in flight, not replaced.
    assert cache._load is not None and loader.calls == 1

    loader.release.set()
    leader.join(TIMEOUT)
    assert cache.get() == {"version": 1} and loader.calls == 1


def test_a_load_stuck_past_the_wait_timeout_is_replaced_and_the_cache_heals(clock):
    loader = HangingFirstLoader()
    cache = TTLValue("t", 15, loader, wait_timeout=5)
    leader, outcome = start_leader(cache)
    assert loader.entered.wait(TIMEOUT)
    hung_load = cache._load

    clock.now += 5  # the database is back; the first load is still stuck
    assert cache.read() == ({"version": 2}, 0.0, True)
    assert loader.calls == 2 and cache._load is None

    # The stuck load finally returns: its caller gets its own value, but it
    # neither overwrites the newer value nor touches the in-flight slot.
    loader.release.set()
    leader.join(TIMEOUT)
    assert outcome["value"] == {"version": 1}
    assert hung_load.done.is_set() and cache._load is None
    assert cache.get() == {"version": 2} and loader.calls == 2


class GatedLoader:
    """Every call blocks on its own gate and answers what the test sets for it."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0
        self.entered = [threading.Event() for _ in self.outcomes]
        self.gates = [threading.Event() for _ in self.outcomes]

    def __call__(self):
        index = self.calls
        self.calls += 1
        self.entered[index].set()
        assert self.gates[index].wait(TIMEOUT), f"load {index + 1} was never released"
        if isinstance(self.outcomes[index], BaseException):
            raise self.outcomes[index]
        return self.outcomes[index]


def start_caller(cache):
    outcome = {}

    def call():
        try:
            outcome["value"] = cache.read()
        except Exception as exc:  # noqa: BLE001 - the test inspects what the caller saw
            outcome["error"] = exc

    thread = threading.Thread(target=call, daemon=True)
    thread.start()
    return thread, outcome


def _stuck_then_replacement(clock, stuck_outcome):
    """Load 1 hangs; past the wait timeout load 2 replaces it. Both are left in flight."""
    loader = GatedLoader([stuck_outcome, {"version": 2}])
    cache = TTLValue("t", 15, loader, wait_timeout=5)
    first, first_outcome = start_caller(cache)
    assert loader.entered[0].wait(TIMEOUT)
    stuck = cache._load
    clock.now += 5
    second, second_outcome = start_caller(cache)
    assert loader.entered[1].wait(TIMEOUT)
    replacement = cache._load
    assert replacement is not stuck and loader.calls == 2
    return loader, cache, (first, first_outcome), (second, second_outcome), replacement


@pytest.mark.parametrize("stuck_outcome", [{"version": 1}, RuntimeError("stuck load failed late")])
def test_a_stuck_load_finishing_while_its_replacement_runs_changes_nothing(clock, stuck_outcome):
    """Two loaders in flight at once: the stuck one ends first (success or failure). It
    must not store its value, free the replacement's slot or touch its loaded_at; only
    the replacement's result is kept, and the counters record exactly two loads."""
    loader, cache, (first, first_outcome), (second, second_outcome), replacement = \
        _stuck_then_replacement(clock, stuck_outcome)

    loader.gates[0].set()
    first.join(TIMEOUT)
    assert not first.is_alive()
    if isinstance(stuck_outcome, BaseException):
        assert first_outcome["error"] is stuck_outcome
    else:
        assert first_outcome["value"] == ({"version": 1}, 0.0, True)  # its own caller only
    assert cache._load is replacement  # the replacement still owns the slot
    assert cache._value is None and cache._loaded_at is None  # nothing stored

    clock.now += 1
    loader.gates[1].set()
    second.join(TIMEOUT)
    assert second_outcome["value"] == ({"version": 2}, 0.0, True)
    assert cache._value == {"version": 2} and cache._loaded_at == clock.now and cache._load is None
    assert cache.get() == {"version": 2} and loader.calls == 2
    failed = 1 if isinstance(stuck_outcome, BaseException) else 0
    assert (cache.misses, cache.failures, cache.hits) == (2, failed, 1)


def test_a_replacement_that_fails_leaves_no_value_and_the_next_call_retries(clock):
    """The replacement fails while the stuck load is still in flight: nothing is cached,
    the slot is freed, and the stuck load finishing later still cannot store its value."""
    loader, cache, (first, first_outcome), (second, second_outcome), _ = \
        _stuck_then_replacement(clock, {"version": 1})
    loader.outcomes[1] = RuntimeError("replacement failed")

    loader.gates[1].set()
    second.join(TIMEOUT)
    assert isinstance(second_outcome["error"], RuntimeError)
    assert cache._load is None and cache._value is None and cache._loaded_at is None

    loader.gates[0].set()
    first.join(TIMEOUT)
    assert first_outcome["value"][0] == {"version": 1}
    assert cache._value is None and cache._loaded_at is None and cache._load is None
    assert (cache.misses, cache.failures) == (2, 1)


def test_clear_during_a_load_does_not_let_that_load_repopulate_the_cache(clock):
    """clear() is an invalidation: a load that started before it must not store its
    (possibly pre-invalidation) value afterwards. Its own caller still gets it."""
    loader = GatedLoader([{"version": 1}, {"version": 2}])
    cache = TTLValue("t", 15, loader, wait_timeout=5)
    first, first_outcome = start_caller(cache)
    assert loader.entered[0].wait(TIMEOUT)

    cache.clear()
    loader.gates[0].set()
    first.join(TIMEOUT)
    assert first_outcome["value"] == ({"version": 1}, 0.0, True)
    assert cache._value is None and cache._loaded_at is None and cache._load is None

    loader.gates[1].set()
    assert cache.get() == {"version": 2} and loader.calls == 2
