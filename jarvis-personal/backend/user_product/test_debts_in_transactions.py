"""Debts shown in Movimientos (Transactions) are the Debts screen's own data.

The Transactions area adds no endpoint, table or copy: it calls the same
GET /user-product/finance/debts (list_user_debts) as Plan -> Debts. These tests pin
that it is one route, that reading it never writes or recalculates a debt, and that
each workspace only sees its own debts. Synthetic data only.
"""
import inspect

import pytest

from backend.auth.current_user import reset_current_user, set_current_user
from backend.tests.test_read_surfaces_are_read_only import ReadOnlyLedger
from backend.user_product import routes, service
from backend.user_product.test_mail_preserves_financial_state import ACCOUNT, OTHER_WORKSPACE, WORKSPACE


@pytest.fixture
def ledger(monkeypatch):
    db = ReadOnlyLedger()
    monkeypatch.setattr(service, "get_connection", db.connect)
    return db


def _as(workspace, account=ACCOUNT):
    return set_current_user({"id": 41, "account_id": account, "workspace_id": workspace, "role": "user"})


def test_one_debt_list_route_serves_both_screens():
    debt_routes = [r for r in routes.router.routes if getattr(r, "path", "").endswith("/finance/debts") and "GET" in r.methods]
    assert len(debt_routes) == 1
    assert debt_routes[0].endpoint is routes.debts_list
    assert "list_user_debts()" in inspect.getsource(routes.debts_list)


def test_reading_debts_from_transactions_is_read_only_and_idempotent(ledger, monkeypatch):
    monkeypatch.setattr(routes, "require_feature", lambda *_args: None)
    before = ledger.state
    token = _as(WORKSPACE)
    try:
        reads = [routes.debts_list() for _ in range(3)]  # opening Transactions, Debts, Transactions again
    finally:
        reset_current_user(token)
    assert ledger.writes == []
    assert ledger.state == before  # no recalculation, deletion or recreation
    assert reads[0] == reads[1] == reads[2]
    assert len(ledger.state["debts"]) == 2  # nothing duplicated


def test_each_workspace_only_sees_its_own_debts(ledger, monkeypatch):
    monkeypatch.setattr(routes, "require_feature", lambda *_args: None)
    token = _as(WORKSPACE)
    try:
        own = routes.debts_list()
    finally:
        reset_current_user(token)
    token = _as(OTHER_WORKSPACE, account="account-ajena")
    try:
        other = routes.debts_list()
    finally:
        reset_current_user(token)
    assert [d["id"] for d in own] == [7]
    assert [d["id"] for d in other] == [8]
    assert {d["workspace_id"] for d in own} == {WORKSPACE}
