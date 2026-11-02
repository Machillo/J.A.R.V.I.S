"""The voluntary complementary pension in the strategy (the Owner's rule, 2026-11-01), synthetic data.

It complements the state pension, so it stays small, and it never competes with expensive debt:
- not while any debt costs 20% a year or more, nor before the Salvavidas covers a month, nor while
  a dated goal is being protected;
- with cheaper debt left, 5% of what is split, out of the debt attack;
- with no debt, 10% of what is split, out of investment.
"""
from __future__ import annotations

import pytest

from backend.ai.strategy_dashboard import PENSION_MAX_DEBT_APR, _build_dynamic_director_allocation


def director(debts, savings=300_000, base=100_000, goals=None):
    return _build_dynamic_director_allocation(available_before_allocation=base, debts=debts, goal_reserves=goals or {},
                                              savings_total=savings, emergency_monthly_base=250_000)


def debt(rate, remaining=500_000):
    return {"id": 1, "name": "Préstamo sintético", "remaining_amount": remaining, "monthly_payment": 20_000, "interest_rate": rate}


@pytest.mark.parametrize("rate", [35.76, 20.0])
def test_expensive_debt_keeps_every_colon_on_the_debt(rate):
    result = director([debt(rate)])
    assert result["mode"] == "debt_attack" and result["pension_allowed"] is False
    assert result["allocation_amounts"]["pension_complementaria"] == 0
    assert any("20%" in reason for reason in result["pension_blockers"])


def test_cheaper_debt_and_a_month_of_safety_start_a_small_pension_out_of_the_debt_attack():
    without = director([debt(PENSION_MAX_DEBT_APR + 15)])
    result = director([debt(15.0)])
    amounts = result["allocation_amounts"]
    assert result["pension_allowed"] is True and amounts["pension_complementaria"] == 5_000
    assert amounts["ataque_de_deuda"] == without["allocation_amounts"]["ataque_de_deuda"] - 5_000
    assert sum(amounts.values()) == pytest.approx(100_000)


def test_no_pension_before_a_month_of_safety():
    result = director([debt(15.0)], savings=100_000)
    assert result["pension_allowed"] is False and result["allocation_amounts"]["pension_complementaria"] == 0


def test_no_pension_while_a_dated_goal_is_protected(monkeypatch):
    from backend.ai import strategy_dashboard

    goal = {"id": 9, "name": "Viaje sintético"}
    monkeypatch.setattr(strategy_dashboard, "build_goal_portfolio",
                        lambda *_a, **_k: {"active_goal": goal, "goal_allocation": 30_000, "items": [goal]})
    result = director([debt(15.0)])
    assert result["mode"] == "goal_protection" and result["pension_allowed"] is False
    assert result["allocation_amounts"]["pension_complementaria"] == 0


def test_without_debt_ten_percent_goes_to_the_pension_out_of_investment():
    amounts = director([])["allocation_amounts"]
    assert amounts["pension_complementaria"] == 10_000 and amounts["inversion"] == 45_000


def test_an_unknown_rate_never_starts_the_pension():
    result = _build_dynamic_director_allocation(available_before_allocation=100_000, debts=[debt(15.0)], goal_reserves={},
                                                savings_total=300_000, emergency_monthly_base=250_000, rates_known=False)
    assert result["pension_allowed"] is False
