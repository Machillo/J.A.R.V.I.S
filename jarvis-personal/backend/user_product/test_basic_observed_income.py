"""Basic Strategy income sources: declared first; without it, the observed income.

- A declared income stays the primary source (the historical Basic contract).
- Without one, the shared income policy's observed baseline (recorded income and
  recurring items, the Home reading) lets Basic plan instead of answering zeros.
- The observed income is only read: nothing is written to financial_profiles.
- The answer says which source it used, so the apps can label an estimate.
Synthetic data; no database.
"""
from __future__ import annotations

import pytest

from backend.auth.current_user import reset_current_user, set_current_user
from backend.user_product import income_policy, service

SNAPSHOT = {
    "monthly_income_estimate": 0.0, "essential_monthly_expenses": 300000, "liquid_savings": 100000,
    "emergency_fund_target": None, "strategy_preference": None, "discretionary_monthly_minimum": None,
    "pay_frequency": "monthly", "payday_note": None,
    "debts": [{"id": 1, "name": "Tarjeta Sintética", "remaining_amount": 400000, "monthly_payment": 40000,
               "interest_rate": 30, "payment_day": 5}],
    "goals": [],
}


class _ReadOnlyConn:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def execute(self, query, params=()):
        self.log.append(query)
        raise AssertionError("the Basic strategy runs only the stubbed loaders")

    def commit(self):
        self.log.append("COMMIT")


@pytest.fixture
def basic(monkeypatch):
    calls = {"policy": None, "sql": []}
    monkeypatch.setattr(service, "require_feature", lambda _feature: None)
    monkeypatch.setattr(service, "get_connection", lambda: _ReadOnlyConn(calls["sql"]))

    def strategy(snapshot=None, policy_income=0.0, policy_source="none"):
        monkeypatch.setattr(service, "_strategy_snapshot", lambda: dict(snapshot or SNAPSHOT))

        def load(conn, *, account_id, workspace_id, today=None):
            calls["policy"] = (account_id, workspace_id)
            return {"policy": "income-policy-v1", "monthly_income": policy_income, "source": policy_source}
        monkeypatch.setattr(income_policy, "load_income_baseline", load)
        token = set_current_user({"id": 3, "account_id": "acc-basic", "workspace_id": "ws-basic", "role": "user"})
        try:
            return service.get_strategy_basic()
        finally:
            reset_current_user(token)
    return strategy, calls


def test_a_declared_income_is_the_primary_source(basic):
    strategy, calls = basic
    result = strategy({**SNAPSHOT, "monthly_income_estimate": 800000}, policy_income=999999, policy_source="recorded")
    assert result["income_source"] == "declared" and result["monthly_income"] == 800000
    assert calls["policy"] is None  # the observed income is not even read


def test_without_a_declared_income_basic_plans_with_the_observed_income(basic):
    strategy, calls = basic
    result = strategy(policy_income=650000, policy_source="recorded")
    assert result["status"] != "needs_income" and result["monthly_income"] == 650000
    assert result["income_source"] == "observed"
    assert result["income_basis"] == {"source": "observed", "policy": "income-policy-v1", "observed_source": "recorded"}
    assert calls["policy"] == ("acc-basic", "ws-basic")  # this account/workspace only
    assert calls["sql"] == []  # read only: nothing is written back as if it were declared


def test_without_any_income_basic_still_asks_for_it(basic):
    strategy, _calls = basic
    result = strategy(policy_income=0, policy_source="none")
    assert result["status"] == "needs_income" and result["monthly_income"] == 0
    assert result["income_source"] == "none"
