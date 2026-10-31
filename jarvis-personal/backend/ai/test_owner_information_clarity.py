"""The Owner's figures keep one meaning across screens (Owner information clarity).

- The Owner strategy says which dates its cycle and card statement cover (from the same cycle
  report, nothing recalculated); unknown periods stay unknown (None), never invented.
Synthetic data only; loaders are stubbed and any database access fails.
"""
from __future__ import annotations

import pytest

from backend.ai import strategy_dashboard as sd
from backend.auth.current_user import reset_current_user, set_current_user

def _no_query(*_a, **_k):
    raise AssertionError("not expected in this test")


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
        "cycle": {"start": "2026-10-05", "end": "2026-11-05", "end_exclusive": "2026-11-06"},
        "expense_cycle": {"start": "2026-09-21", "end": "2026-10-21", "end_exclusive": "2026-10-22"},
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
    monkeypatch.setattr(sd.owner_commitments, "manual_expenses", lambda *_a: {"total": 0.0, "count": 0})
    monkeypatch.setattr(sd, "_fetch_distributable_cash", lambda *_a: 0.0)
    monkeypatch.setattr(sd, "_fetch_active_financial_goals", lambda *_a: [])
    monkeypatch.setattr(sd, "_fetch_investment_portfolio", lambda *_a, **_k: {})
    return cycle


def test_the_owner_strategy_says_which_dates_it_covers(owner_strategy):
    result = _as("owner", sd.build_local_strategy_blueprint)
    assert result["cycle_period"] == {"start": "2026-10-05", "end": "2026-11-05"}
    assert result["card_statement_period"] == {"start": "2026-09-21", "end": "2026-10-21"}


def test_an_unread_cycle_has_no_invented_dates(owner_strategy):
    owner_strategy["value"] = {}
    result = _as("owner", sd.build_local_strategy_blueprint)
    assert result["cycle_period"] is None and result["card_statement_period"] is None


def test_the_periods_are_only_added_alongside_the_figures(owner_strategy, monkeypatch):
    with_periods = _as("owner", sd.build_local_strategy_blueprint)
    monkeypatch.setattr(sd, "_period", lambda _section: None)
    without = _as("owner", sd.build_local_strategy_blueprint)
    for key in ("allocation_base_amount", "allocation_items", "distribution_formula", "safe_to_spend", "monthly_income"):
        assert with_periods[key] == without[key], key
