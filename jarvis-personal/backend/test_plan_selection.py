"""Plan choice persists before navigation and pending checkout does not grant access."""
from contextlib import contextmanager

import pytest

from backend.auth import saas
from backend.product_ops import service as billing
from fastapi import HTTPException


@pytest.mark.parametrize("plan", ["basic", "vip"])
def test_no_off_store_checkout_after_promotion(monkeypatch, plan):
    monkeypatch.setattr(billing, "launch_promotion_status", lambda: {"active": False})
    monkeypatch.setattr(billing, "get_connection", lambda: pytest.fail("Checkout must not write a SINPE order"))
    with pytest.raises(HTTPException) as error:
        billing.create_checkout(plan, accepted=True, consent_version="2026-09-23-v3")
    assert error.value.status_code == 503
    assert "Google Play" in error.value.detail


class _Result:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self):
        self.plan = "free"
        self.plan_selected = False
        self.commits = 0

    def execute(self, query, params=()):
        sql = " ".join(query.lower().split())
        if sql.startswith("select id from plans"):
            return _Result({"id": params[0]})
        if sql.startswith("insert into account_subscriptions"):
            self.plan = params[1]
        if sql.startswith("update accounts set plan_selected=true"):
            self.plan_selected = True
        return _Result()

    def commit(self):
        self.commits += 1


@pytest.mark.parametrize("code", ["free", "basic", "vip"])
def test_selected_plan_is_active_after_save_and_fresh_status(monkeypatch, code):
    connection = _Connection()

    @contextmanager
    def database():
        yield connection

    def identity(user):
        return {**user, "plan_selected": connection.plan_selected,
                "subscription": {"plan": connection.plan, "status": "active"}}

    monkeypatch.setattr(saas, "get_connection", database)
    monkeypatch.setattr(billing, "get_connection", database)
    monkeypatch.setattr(saas, "get_current_user", lambda: {"role": "user", "account_id": "account"})
    monkeypatch.setattr(saas, "get_current_account_id", lambda: "account")
    monkeypatch.setattr(billing, "get_current_account_id", lambda: "account")
    monkeypatch.setattr(saas, "enrich_identity", identity)
    monkeypatch.setattr(billing, "ensure_schema", lambda conn: None)
    monkeypatch.setattr(billing, "record_event", lambda *args: None)
    monkeypatch.setattr(billing, "launch_promotion_status", lambda: {"active": True})

    response = saas.select_plan(code)
    assert response["status"] == ("ok" if code == "free" else "promotion_active")
    assert response["profile"]["subscription"] == {"plan": code, "status": "active"}
    assert response["profile"]["plan_selected"] is True
    assert saas.get_onboarding_status()["profile"]["subscription"]["plan"] == code
    assert connection.commits > 0


def test_payment_pending_keeps_plan_unselected(monkeypatch):
    monkeypatch.setattr(saas, "get_current_user", lambda: {"role": "user", "account_id": "account"})
    monkeypatch.setattr(saas, "enrich_identity", lambda user: {**user, "plan_selected": False,
                                                           "subscription": {"plan": "free", "status": "active"}})
    monkeypatch.setattr(billing, "create_checkout", lambda *args: {"status": "payment_pending", "order": {"plan_code": "vip"}})
    response = saas.select_plan("vip", True)
    assert response["status"] == "payment_pending"
    assert response["profile"]["plan_selected"] is False
