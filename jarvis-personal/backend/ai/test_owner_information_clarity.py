"""The Owner's figures keep one meaning across screens (Owner information clarity).

- JARVIS > Análisis financiero: "Gastos por mes" and "Ingresos y gastos" read the same Owner ledger
  months (owner_ledger), computed once per request; Users keep their own series.
- The Owner strategy says which dates its cycle and card statement cover (from the same cycle
  report, nothing recalculated); unknown periods stay unknown (None), never invented.
Synthetic data only; loaders are stubbed and any database access fails.
"""
from __future__ import annotations

import pytest

from backend.ai import strategy_dashboard as sd
from backend.auth.current_user import reset_current_user, set_current_user
from backend.transactions import analyzer

FLOW = [
    {"month": "2026-09", "income": 900000.0, "expenses": 410000.0, "monthly_balance": 300000.0, "complete": True},
    {"month": "2026-10", "income": 450000.0, "expenses": 125000.5, "monthly_balance": 200000.0, "complete": False},
]


def _no_query(*_a, **_k):
    raise AssertionError("not expected in this test")


def _stub_analysis(monkeypatch, owner: bool, flow_calls: list):
    monkeypatch.setattr(analyzer, "owner_context", lambda: owner)
    monkeypatch.setattr(analyzer, "get_monthly_flow", lambda: flow_calls.append(1) or [dict(m) for m in FLOW])
    monkeypatch.setattr(analyzer, "get_transaction_summary", lambda: {})
    monkeypatch.setattr(analyzer, "get_top_expense_categories", lambda: [])
    monkeypatch.setattr(analyzer, "get_expenses_by_category_and_month", lambda: [])
    monkeypatch.setattr(analyzer, "get_spending_breakdown", lambda: {})


def test_the_owner_expenses_by_month_are_the_flow_months(monkeypatch):
    calls: list = []
    _stub_analysis(monkeypatch, owner=True, flow_calls=calls)
    monkeypatch.setattr(analyzer, "get_expenses_by_month", _no_query)  # the old expense-rows-only series
    result = analyzer.get_transaction_analysis()
    assert result["expenses_by_month"] == [{"month": "2026-09", "total": 410000.0}, {"month": "2026-10", "total": 125000.5}]
    assert [m["expenses"] for m in result["monthly_flow"]] == [m["total"] for m in result["expenses_by_month"]]
    assert calls == [1], "the ledger months are computed once per request"


def test_users_keep_their_expenses_by_month(monkeypatch):
    calls: list = []
    _stub_analysis(monkeypatch, owner=False, flow_calls=calls)
    monkeypatch.setattr(analyzer, "get_expenses_by_month", lambda: [{"month": "2026-10", "total": 99.0}])
    assert analyzer.get_transaction_analysis()["expenses_by_month"] == [{"month": "2026-10", "total": 99.0}]


# --- Owner strategy periods ------------------------------------------------------------------

def _as(role, fn):
    token = set_current_user({"id": 7, "account_id": "acc-test", "workspace_id": "ws-test", "role": role})
    try:
        return fn()
    finally:
        reset_current_user(token)


@pytest.fixture
def owner_strategy(monkeypatch):
    cycle = {"value": {
        "cycle": {"start": "2026-10-06", "end": "2026-11-05", "end_exclusive": "2026-11-06"},
        "expense_cycle": {"start": "2026-09-21", "end": "2026-10-20", "end_exclusive": "2026-10-21"},
        "income": {"expected_total": 900000, "received_from_transactions": 0},
        "expenses": {"spending_only": 100000}, "debts": {"payments_current_period": 0},
    }}
    monkeypatch.setattr(sd, "get_connection", _no_query)
    monkeypatch.setattr(sd, "get_debts", lambda: [])
    monkeypatch.setattr(sd, "get_financial_summary", lambda: {})
    monkeypatch.setattr(sd, "calculate_monthly_salary_projection", lambda: {"results": {"base_net": 900000}})
    monkeypatch.setattr(sd, "_safe_cycle_report", lambda: cycle["value"])
    monkeypatch.setattr(sd, "_get_strategy_living_expenses", lambda *_a: {"fixed_living_total": 0})
    monkeypatch.setattr(sd, "get_salvavidas_state", lambda: {"current_amount": 0, "monthly_base": 300000})
    monkeypatch.setattr(sd, "_fetch_post_cut_expenses", lambda *_a: {"total": 0})
    monkeypatch.setattr(sd, "_pending_mandatory_fixed_expenses", lambda *_a: {"total": 0})
    monkeypatch.setattr(sd, "_fetch_distributable_cash", lambda *_a: 0.0)
    monkeypatch.setattr(sd, "_fetch_active_financial_goals", lambda *_a: [])
    monkeypatch.setattr(sd, "_fetch_investment_portfolio", lambda *_a, **_k: {})
    return cycle


def test_the_owner_strategy_says_which_dates_it_covers(owner_strategy):
    result = _as("owner", sd.build_local_strategy_blueprint)
    assert result["cycle_period"] == {"start": "2026-10-06", "end": "2026-11-05"}
    assert result["card_statement_period"] == {"start": "2026-09-21", "end": "2026-10-20"}


def test_an_unread_cycle_has_no_invented_dates(owner_strategy):
    owner_strategy["value"] = {}
    result = _as("owner", sd.build_local_strategy_blueprint)
    assert result["cycle_period"] is None and result["card_statement_period"] is None


def test_the_periods_never_change_a_figure(owner_strategy, monkeypatch):
    with_periods = _as("owner", sd.build_local_strategy_blueprint)
    monkeypatch.setattr(sd, "_period", lambda _section: None)
    without = _as("owner", sd.build_local_strategy_blueprint)
    for key in ("allocation_base_amount", "allocation_items", "distribution_formula", "safe_to_spend", "monthly_income"):
        assert with_periods[key] == without[key], key
