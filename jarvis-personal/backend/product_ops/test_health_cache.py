import asyncio
import logging
import threading
import time

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.core import ttl_cache
from backend.core.ttl_cache import TTLValue
from backend import main
from backend.product_ops import health_cache, routes, service


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


# --- Route contract: authentication first, then the one global value --------

AUTH = {"Authorization": "Bearer test-token"}
USERS = {
    "user": {"id": 50, "account_id": "account-u", "workspace_id": "workspace-u", "role": "user", "email": "u@example.com"},
    "owner": {"id": 1, "account_id": "account-o", "workspace_id": "workspace-o", "role": "owner", "email": "o@example.com"},
}
GLOBAL_HEALTH = {"status": "degraded", "active_incidents": 3, "occurrences": 7, "affected_accounts": 2,
                 "last_incident_at": None, "checked_at": "2026-01-01T00:00:00+00:00"}


@pytest.fixture
def health_loader(monkeypatch):
    calls = []
    monkeypatch.setattr(service, "platform_health", lambda: calls.append(1) or dict(GLOBAL_HEALTH))
    monkeypatch.setattr(main, "disabled_feature_for_request", lambda *_a, **_k: None)
    health_cache.platform_health_cache.clear()
    yield calls
    health_cache.platform_health_cache.clear()


def client_as(monkeypatch, role):
    def authenticate(_token):
        if role is None:
            raise HTTPException(401, "invalid session")
        return USERS[role]
    monkeypatch.setattr(main, "authenticate_access_token", authenticate)
    return TestClient(main.app, raise_server_exceptions=False)


def test_a_warm_cache_never_answers_without_a_valid_session(monkeypatch, health_loader):
    assert client_as(monkeypatch, "user").get("/product-ops/health", headers=AUTH).status_code == 200
    assert health_loader == [1]

    no_header = client_as(monkeypatch, "user").get("/product-ops/health")
    rejected = client_as(monkeypatch, None).get("/product-ops/health", headers=AUTH)

    assert no_header.status_code == 401 and rejected.status_code == 401
    assert "status" not in no_header.json() and "status" not in rejected.json()
    assert "/product-ops/health" not in main.PUBLIC_PATHS
    assert health_loader == [1]


def test_users_and_owner_get_the_same_global_value_with_no_caller_data(monkeypatch, health_loader):
    user = client_as(monkeypatch, "user").get("/product-ops/health", headers=AUTH)
    owner = client_as(monkeypatch, "owner").get("/product-ops/health", headers=AUTH)

    assert user.status_code == owner.status_code == 200
    assert health_loader == [1]
    strip = lambda body: {key: value for key, value in body.items() if key != "cache"}
    assert strip(user.json()) == strip(owner.json()) == GLOBAL_HEALTH
    for caller in USERS.values():
        for value in (caller["account_id"], caller["workspace_id"], caller["email"]):
            assert value not in user.text and value not in owner.text


def test_platform_health_reads_no_caller_context_and_returns_only_aggregates(monkeypatch):
    queries = []

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def commit(self): pass
        def execute(self, query, params=None):
            queries.append((query, params))
            row = {"active_incidents": 1, "occurrences": 4, "affected_accounts": 1,
                   "critical_accounts": 0, "last_incident_at": None}
            return type("Result", (), {"fetchone": lambda _self: row})()

    def no_caller(*_args, **_kwargs):
        raise AssertionError("platform health must not read the caller's identity")

    for name in ("get_current_user", "get_current_account_id", "get_current_workspace_id"):
        monkeypatch.setattr(service, name, no_caller)
    monkeypatch.setattr(service, "get_connection", lambda: Connection())
    monkeypatch.setattr(service, "ensure_schema", lambda _conn: None)

    health = service.platform_health()

    assert set(health) == {"status", "active_incidents", "occurrences", "affected_accounts", "last_incident_at", "checked_at"}
    assert all(isinstance(health[key], int) for key in ("active_incidents", "occurrences", "affected_accounts"))
    # One unparameterised aggregate: nothing in it can depend on who is asking.
    [(query, params)] = queries
    assert params is None and "%s" not in query and "COUNT(DISTINCT account_id)" in query


def test_a_miss_wave_logs_one_line(monkeypatch, caplog, health_loader):
    release = threading.Event()
    monkeypatch.setattr(service, "platform_health", lambda: release.wait(10) and (health_loader.append(1) or dict(GLOBAL_HEALTH)))
    caplog.set_level(logging.INFO, logger=health_cache.__name__)
    barrier = threading.Barrier(20)

    def call():
        barrier.wait(10)
        routes.health()

    threads = [threading.Thread(target=call, daemon=True) for _ in range(20)]
    for thread in threads:
        thread.start()
    cache, idle, deadline = health_cache.platform_health_cache, threading.Event(), time.monotonic() + 3
    while cache.hits + cache.misses < 20 and time.monotonic() < deadline:
        idle.wait(0.001)
    release.set()
    for thread in threads:
        thread.join(10)

    assert health_loader == [1]
    assert [record.getMessage().split(" stats=")[0] for record in caplog.records] == ["platform_health cache miss"]


def test_a_slow_health_load_does_not_block_the_event_loop(monkeypatch, health_loader):
    release = threading.Event()
    started = threading.Event()

    def slow_health():
        started.set()
        release.wait(10)
        return dict(GLOBAL_HEALTH)

    monkeypatch.setattr(service, "platform_health", slow_health)
    monkeypatch.setattr(main, "authenticate_access_token", lambda _token: USERS["user"])

    async def scenario():
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            health = asyncio.create_task(client.get("/product-ops/health", headers=AUTH))
            assert await asyncio.to_thread(started.wait, 10)
            # The health load is parked in the thread pool; the loop still serves others.
            other = await asyncio.wait_for(client.get("/status"), timeout=10)
            still_loading = not health.done()
            release.set()
            return other, still_loading, await health

    other, still_loading, health = asyncio.run(scenario())
    assert other.status_code == 200 and still_loading
    assert health.status_code == 200 and health.json()["status"] == "degraded"
