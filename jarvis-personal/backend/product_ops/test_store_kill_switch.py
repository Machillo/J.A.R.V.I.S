"""Store verification kill switch: off unless DINCR_STORE_VERIFICATION_ENABLED=1.

While off, every store verification path answers 503 before any database access.
The tripwire below replaces every way this code can reach PostgreSQL (the backend's
get_connection, as imported by the store modules, and psycopg2.connect itself) and
records each attempt, so "answers 503 but queried the database first" fails here.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import psycopg2
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.core import database
from backend.product_ops import store_routes, store_verification

PREFIX = "/product-ops/billing/store"
REQUESTS = {  # path -> a well-formed body, so only the switch can stop it
    "/customer-token": None,
    "/apple/transactions": {"signed_transaction": "x" * 40},
    "/google/purchases": {"purchase_token": "synthetic-token", "product_id": "finva.vip.monthly"},
    "/apple/notifications": {"signedPayload": "x" * 40},
    "/google/notifications": {"message": {"data": "e30=", "messageId": "1"}},
    "/cron": None,
}
HANDLERS = {
    "/customer-token": "my_customer_token",
    "/apple/transactions": "verify_apple_transaction",
    "/google/purchases": "verify_google_purchase",
    "/apple/notifications": "apple_notification",
    "/google/notifications": "google_notification",
    "/cron": "lapse_cron",
}
CALLS = {
    "my_customer_token": (),
    "verify_apple_transaction": ("x" * 40,),
    "verify_google_purchase": ("synthetic-token", "finva.vip.monthly"),
    "apple_notification": ("x" * 40,),
    "google_notification": ("Bearer synthetic", {"message": {"data": "e30=", "messageId": "1"}}),
    "lapse_cron": ("synthetic-cron-secret",),
}
OFF_VALUES = [None, "", "0", "false", "true", "yes", "on", " 1", "1 ", "01"]


@pytest.fixture
def tripwire(monkeypatch):
    attempts: list[str] = []

    def trip(name):
        def blocked(*_args, **_kwargs):
            attempts.append(name)
            raise AssertionError(f"database access while store verification is off: {name}")
        return blocked

    monkeypatch.setattr(database, "get_connection", trip("database.get_connection"))
    monkeypatch.setattr(store_verification, "get_connection", trip("store_verification.get_connection"))
    monkeypatch.setattr(psycopg2, "connect", trip("psycopg2.connect"))
    monkeypatch.setenv("DINCR_STORE_CRON_SECRET", "synthetic-cron-secret")  # the cron would pass its own check
    return attempts


def _switch(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("DINCR_STORE_VERIFICATION_ENABLED", raising=False)
    else:
        monkeypatch.setenv("DINCR_STORE_VERIFICATION_ENABLED", value)


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(store_routes.router)
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("path", list(REQUESTS))
@pytest.mark.parametrize("value", OFF_VALUES)
def test_every_store_path_answers_503_without_touching_the_database_while_off(monkeypatch, tripwire, path, value):
    _switch(monkeypatch, value)
    reached = []
    monkeypatch.setattr(store_verification, HANDLERS[path], lambda *a, **k: reached.append(path))
    response = _client().post(PREFIX + path, json=REQUESTS[path],
                              headers={"Authorization": "Bearer synthetic", "X-Cron-Secret": "synthetic-cron-secret"})
    assert response.status_code == 503
    assert reached == [] and tripwire == []


@pytest.mark.parametrize("path", ["/apple/transactions", "/google/purchases", "/apple/notifications"])
def test_the_switch_answers_before_the_body_is_even_validated(monkeypatch, tripwire, path):
    _switch(monkeypatch, None)
    response = _client().post(PREFIX + path, json={"unexpected": True})
    assert response.status_code == 503 and tripwire == []


@pytest.mark.parametrize("name", list(CALLS))
@pytest.mark.parametrize("value", [None, "0", "true"])
def test_each_entry_point_checks_the_switch_itself_before_any_database_access(monkeypatch, tripwire, name, value):
    """Defence in depth: a caller that bypasses the router is refused as well."""
    _switch(monkeypatch, value)
    with pytest.raises(HTTPException) as refused:
        getattr(store_verification, name)(*CALLS[name])
    assert refused.value.status_code == 503
    assert tripwire == []


@pytest.mark.parametrize("path", list(REQUESTS))
def test_with_the_switch_on_each_path_reaches_its_normal_handler(monkeypatch, path):
    _switch(monkeypatch, "1")
    reached = []
    monkeypatch.setattr(store_verification, HANDLERS[path], lambda *a, **k: reached.append(path) or {"status": "reached"})
    response = _client().post(PREFIX + path, json=REQUESTS[path])
    assert response.status_code == 200 and response.json() == {"status": "reached"}
    assert reached == [path]


def test_with_the_switch_on_the_entry_points_run_their_normal_checks(monkeypatch, tripwire):
    """On, the cron reaches its own secret check (403 for a wrong one), still before the database."""
    _switch(monkeypatch, "1")
    with pytest.raises(HTTPException) as refused:
        store_verification.lapse_cron("wrong")
    assert refused.value.status_code == 403 and tripwire == []


def test_every_mounted_store_path_is_behind_the_switch():
    from backend import main

    mounted = [route for route in main.app.routes if getattr(route, "path", "").startswith(PREFIX + "/")]
    verification = [route for route in mounted if route.endpoint.__module__ == store_routes.__name__]
    assert {route.path for route in verification} == {PREFIX + path for path in REQUESTS}
    for route in verification:
        assert store_verification.require_enabled in [dep.call for dep in route.dependant.dependencies], route.path
    # The existing store catalog / entitlement reads (store_subscriptions only) keep working.
    others = {route.path for route in mounted} - {route.path for route in verification}
    assert others == {PREFIX + "/catalog", PREFIX + "/entitlement"}
    for route in mounted:
        if route.path in others:
            assert store_verification.require_enabled not in [dep.call for dep in route.dependant.dependencies]


IMPORT_PROBE = """
import psycopg2
from backend.core import database
attempts = []
psycopg2.connect = lambda *a, **k: attempts.append("psycopg2.connect")
database.get_connection = lambda *a, **k: attempts.append("database.get_connection")
import backend.product_ops.store_routes, backend.product_ops.store_state
import backend.product_ops.store_apple, backend.product_ops.store_google
print("attempts=%d" % len(attempts))
"""


def test_importing_the_store_modules_touches_no_database():
    """A fresh interpreter, so the imports really run (and nothing else is reloaded)."""
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run([sys.executable, "-c", IMPORT_PROBE], cwd=root, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip().splitlines()[-1] == "attempts=0"
