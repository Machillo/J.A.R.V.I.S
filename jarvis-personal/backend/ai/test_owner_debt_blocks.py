"""GET /jarvis/premium/debt-savings-blocks: Owner only, from the Owner's own strategy (synthetic data).

The route's writes are covered by the GET gate (tests/test_get_routes_are_read_only.py); this checks
who reaches it and that the strategy's numbers are the ones the engine receives.
"""
from __future__ import annotations

from datetime import date

import pytest

from backend.ai import owner_debt_blocks, strategy_dashboard

DEBTS = [{"id": 1, "name": "Préstamo sintético", "remaining_amount": 1_500_000, "total_amount": 2_000_000,
          "monthly_payment": 60_000, "interest_rate": 30, "payment_day": 5}]
BLUEPRINT = {"recurring_monthly_income": 500_000, "base_estimated_extra_cash": 80_000, "recurring_debt_attack_extra": 50_000,
             "salvavidas": {"auto_contribution": {"enabled": True, "amount": 2500, "frequency": "weekly",
                                                  "start_date": "2026-11-05", "end_date": None}}}


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient

    from backend import main

    calls = []
    role = {"value": "owner"}
    monkeypatch.setattr(main, "authenticate_access_token",
                        lambda _token: {"id": 7, "email": "owner@example.test", "role": role["value"], "status": "active",
                                        "account_id": "acc-test", "workspace_id": "ws-test", "plan": "vip"})
    monkeypatch.setattr(main, "disabled_feature_for_request", lambda *_a, **_k: None)
    monkeypatch.setattr(strategy_dashboard, "_owner_strategy_blueprint", lambda: calls.append("blueprint") or dict(BLUEPRINT))
    monkeypatch.setattr(owner_debt_blocks, "get_debts", lambda: [dict(debt) for debt in DEBTS])
    monkeypatch.setattr(owner_debt_blocks, "average_income", lambda *_a: (620_000.0, False))
    monkeypatch.setattr(owner_debt_blocks, "costa_rica_today", lambda: date(2026, 11, 2))
    monkeypatch.setattr(owner_debt_blocks, "get_current_workspace_id", lambda: "ws-test")
    client = TestClient(main.app)
    client.role, client.calls = role, calls
    return client


PATH = "/jarvis/premium/debt-savings-blocks"
HEADERS = {"Authorization": "Bearer synthetic"}


def test_the_owner_gets_a_block_from_the_strategy(client):
    response = client.get(PATH, headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    # 50 000 of attack; the Salvavidas (10 833/month) comes out of the other 30 000 first.
    assert data["safe_monthly_attack"] == 50_000 and data["weekly_safe_amount"] == 11_500
    assert data["automatic_savings_monthly"] == round(2500 * 52 / 12, 2)
    # 120 000 above the base salary, 50/80 of it to the attack: only the term uses it.
    assert data["probable_monthly_attack"] == 125_000
    assert data["status"] == "proposal" and data["proposal"]["debt"]["id"] == 1
    assert data["proposal"]["weekly_amount"] <= data["weekly_safe_amount"]


@pytest.mark.parametrize("role", ["user", "admin"])
def test_anyone_but_the_owner_is_refused_before_anything_runs(client, role):
    client.role["value"] = role
    assert client.get(PATH, headers=HEADERS).status_code == 403
    assert client.calls == []
