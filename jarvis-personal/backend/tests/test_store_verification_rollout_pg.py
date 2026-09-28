"""The rollout of store verification, state by state, with this PR's code as dincr_app.

B: code deployed, switch off, neither migration applied -> store paths 503, no access
   to the new schema, the rest (the entitlement reader) unchanged.
C: 20260926160000 applied -> schema present, the runtime still has no access, switch off.
   Switching on too early fails closed (permission denied), writing nothing.
D: 20260926161000 applied -> the runtime has its access, but the switch is still off:
   applying a migration never turns store verification on.
E: a human sets DINCR_STORE_VERIFICATION_ENABLED=1 -> store verification works.
(A, the code before this PR, is what main already runs; 160000 is additive, see
test_store_verification_expand_pg.) Synthetic data only.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.core import database
from backend.product_ops import store_routes, store_verification
from backend.product_ops.service import has_store_entitlement
from backend.tests.test_dincr_app_role_pg import ACC_A, ROOT, _postflight, env  # noqa: F401
from backend.tests.test_store_verification_expand_pg import (  # noqa: F401
    EXPAND, TABLES, before_store_verification,
)

psycopg2 = pytest.importorskip("psycopg2")

ACTIVATION = ROOT / "migrations" / "20260926161000_store_verification_activation.sql"
PATHS = ("/customer-token", "/apple/notifications", "/google/notifications", "/cron")


@pytest.fixture
def runtime(before_store_verification, monkeypatch):
    """This PR's code connected as dincr_app, counting every connection it opens."""
    params = before_store_verification["as_app"]().connection.get_dsn_parameters()
    monkeypatch.setattr(database, "DATABASE_URL", f"host={params['host']} port={params['port']} "
                                                  f"dbname={params['dbname']} user=dincr_app")
    opened: list[str] = []
    real = database.get_connection

    def counted():
        opened.append("connection")
        return real()

    monkeypatch.setattr(store_verification, "get_connection", counted)
    monkeypatch.setattr(store_verification, "get_current_account_id", lambda: ACC_A)
    monkeypatch.setenv("DINCR_STORE_CRON_SECRET", "synthetic-cron-secret")
    monkeypatch.delenv("DINCR_STORE_VERIFICATION_ENABLED", raising=False)  # never configured: off
    app = FastAPI()
    app.include_router(store_routes.router)
    return {**before_store_verification, "opened": opened, "client": TestClient(app, raise_server_exceptions=False)}


def _all_store_paths_are_off(runtime):
    for path in PATHS:
        response = runtime["client"].post("/product-ops/billing/store" + path, json={"signedPayload": "x" * 40},
                                          headers={"X-Cron-Secret": "synthetic-cron-secret"})
        assert response.status_code == 503, path
    assert runtime["opened"] == []


def _the_rest_works():
    with database.get_connection() as conn:
        assert has_store_entitlement(conn, ACC_A) is True
        conn.rollback()


def test_each_rollout_state_is_safe_and_only_a_human_turns_it_on(runtime, monkeypatch):
    owner = runtime["owner"]

    # B: deployed, switch off, no migration.
    owner.execute("SELECT count(*) FROM unnest(%s::text[]) t WHERE to_regclass('public.' || t) IS NOT NULL", (list(TABLES),))
    assert owner.fetchone() == (0,)
    _all_store_paths_are_off(runtime)
    _the_rest_works()

    # C: 160000 applied; switch still off.
    owner.execute(EXPAND.read_text(encoding="utf-8"))
    owner.execute(_postflight(EXPAND))
    assert owner.fetchall() == []
    _all_store_paths_are_off(runtime)
    _the_rest_works()
    # Switched on too early, it fails closed and writes nothing.
    monkeypatch.setenv("DINCR_STORE_VERIFICATION_ENABLED", "1")
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        store_verification.my_customer_token()
    monkeypatch.delenv("DINCR_STORE_VERIFICATION_ENABLED")
    owner.execute("SELECT count(*) FROM store_customer_tokens")
    assert owner.fetchone() == (0,)
    runtime["opened"].clear()

    # D: 161000 applied; the switch is not turned on by it.
    owner.execute(ACTIVATION.read_text(encoding="utf-8"))
    owner.execute(_postflight(ACTIVATION))
    assert owner.fetchall() == []
    assert store_verification.verification_enabled() is False
    _all_store_paths_are_off(runtime)
    _the_rest_works()

    # E: a human turns it on; store verification works.
    monkeypatch.setenv("DINCR_STORE_VERIFICATION_ENABLED", "1")
    token = runtime["client"].post("/product-ops/billing/store/customer-token")
    assert token.status_code == 200 and token.json()["token"]
    assert store_verification.my_customer_token() == token.json()  # stable, read back through RLS
    with pytest.raises(HTTPException) as refused:
        store_verification.lapse_cron("wrong")
    assert refused.value.status_code == 403
    assert store_verification.lapse_cron("synthetic-cron-secret")["status"] == "OK"
    _the_rest_works()
