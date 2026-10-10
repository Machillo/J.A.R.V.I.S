"""UNKNOWN ≠ 0 in the guided budget (Plan → Tu plan del mes → Presupuesto, Basic).

With no declared income and no recurring income, the proposal used to be built from an income of 0:
"Disponible para categorías ₡0" and five ₡0 limits presented as DINCR's advice. Now an unknown
income leaves the amount available, the proposed limits and their total unknown (null). A declared
0 is still a known 0, a known income gives exactly the same proposal as before (same shares), and
the user's own limits are always shown as saved. Synthetic data.
"""
from __future__ import annotations

import pytest

from backend.user_product import basic_service


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class _Conn:
    def __init__(self, *, debts=0, recurring=(), items=(), spent=()):
        self.debts, self.recurring, self.items, self.spent = debts, list(recurring), list(items), list(spent)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params=()):
        if "SUM(monthly_payment)" in query:
            return _Rows([{"total": self.debts}])
        if "FROM finva_recurring_items" in query:
            return _Rows(self.recurring)
        if "FROM finva_budget_items" in query:
            return _Rows(self.items)
        if "GROUP BY category" in query:
            return _Rows(self.spent)
        raise AssertionError(query[:80])


def _budget(monkeypatch, profile, **conn):
    monkeypatch.setattr(basic_service, "get_current_account_id", lambda: "account-a")
    monkeypatch.setattr(basic_service, "get_current_workspace_id", lambda: "workspace-a")
    monkeypatch.setattr(basic_service, "get_connection", lambda: _Conn(**conn))
    monkeypatch.setattr(basic_service, "_basic_tables_ready", lambda *_args: True)
    monkeypatch.setattr(basic_service, "_profile", lambda *_args: profile)
    return basic_service.get_guided_budget()


def test_an_unknown_income_proposes_nothing_instead_of_zero_limits(monkeypatch):
    budget = _budget(monkeypatch, {})
    assert budget["income"] is None
    assert budget["available_for_categories"] is None
    assert budget["is_proposal"] is True
    assert [item["monthly_limit"] for item in budget["items"]] == [None] * 5, "no ₡0 limit as advice"
    assert [item["remaining"] for item in budget["items"]] == [None] * 5
    assert budget["total_budgeted"] is None


@pytest.mark.parametrize("profile", [
    {"income_type": "fixed", "fixed_monthly_salary": None},
    {"income_type": "hourly", "hourly_rate": 4000, "hours_per_day": None, "work_days_per_week": 5},
])
def test_a_profile_with_a_missing_figure_is_an_unknown_income(monkeypatch, profile):
    assert _budget(monkeypatch, profile)["income"] is None


def test_a_declared_zero_is_a_known_zero(monkeypatch):
    budget = _budget(monkeypatch, {"income_type": "fixed", "fixed_monthly_salary": 0})
    assert budget["income"] == 0 and budget["available_for_categories"] == 0
    assert [item["monthly_limit"] for item in budget["items"]] == [0.0] * 5


def test_a_known_income_gives_the_same_proposal_as_before(monkeypatch):
    budget = _budget(monkeypatch, {"income_type": "fixed", "fixed_monthly_salary": 800000}, debts=100000)
    assert budget["income"] == 800000 and budget["available_for_categories"] == 700000
    limits = {item["category"]: item["monthly_limit"] for item in budget["items"]}
    assert limits == {"Comida": 315000.0, "Transporte": 140000.0, "Personal": 105000.0, "Ahorro y metas": 105000.0, "Otros": 35000.0}
    assert budget["total_budgeted"] == 700000.0


def test_recurring_income_is_a_known_income(monkeypatch):
    budget = _budget(monkeypatch, {}, recurring=[{"amount": 500000, "frequency": "monthly", "item_type": "income"}])
    assert budget["income"] == 500000 and budget["available_for_categories"] == 500000


def test_the_users_own_limits_are_shown_as_saved_even_with_an_unknown_income(monkeypatch):
    budget = _budget(monkeypatch, {}, items=[{"category": "Comida", "monthly_limit": 150000, "is_system": False}],
                     spent=[{"category": "Comida", "amount": 40000}])
    assert budget["is_proposal"] is False
    assert budget["items"][0]["monthly_limit"] == 150000 and budget["items"][0]["remaining"] == 110000
    assert budget["total_budgeted"] == 150000
    assert budget["available_for_categories"] is None, "what is free from an unknown income stays unknown"
