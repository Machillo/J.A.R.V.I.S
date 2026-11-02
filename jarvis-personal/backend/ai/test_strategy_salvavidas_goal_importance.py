"""Goals funded by importance and the staged Salvavidas recommendation (synthetic data).

Essential goals due within a year are funded once one month of Salvavidas is protected, even with
expensive debt; important ones wait for no debt at 20% or more; nice-to-haves for no debt at 10% or
more. The Salvavidas goal is recommended from 1 to 3 months with no debt at 20% or more, and from
3 to 6 with none at 10% or more: only a recommendation, never a change.
"""
from datetime import date

import pytest

from backend.ai import strategy_dashboard as sd
from backend.goals.strategy import build_goal_portfolio, goal_importance

TODAY = date(2026, 11, 2)


def goal(priority, target_date="2027-06-30", goal_id=1, **extra):
    return {"id": goal_id, "name": f"Meta {goal_id}", "priority": priority, "target_date": target_date,
            "remaining_amount": 600_000, "monthly_required": 75_000, "status": "active", **extra}


def portfolio(goals, apr, protected=True):
    return build_goal_portfolio(goals, available=200_000, one_month_protected=protected, highest_debt_apr=apr, today=TODAY)


@pytest.mark.parametrize(("priority", "expected"), [
    ("critical", "essential"), ("high", "essential"), ("medium", "important"), (None, "important"), ("low", "nice"),
])
def test_priority_reads_as_importance(priority, expected):
    assert goal_importance(priority) == expected


def test_an_essential_goal_due_within_a_year_is_funded_even_with_expensive_debt():
    result = portfolio([goal("high")], apr=36.0)
    assert result["active_goal"]["id"] == 1 and result["goal_allocation"] == 75_000
    # Even an unknown debt rate does not hold it back: it can't wait for the debts.
    assert portfolio([goal("high")], apr=None)["goal_allocation"] == 75_000


def test_an_essential_goal_still_needs_one_month_of_salvavidas():
    result = portfolio([goal("high")], apr=36.0, protected=False)
    assert result["active_goal"] is None and result["items"][0]["blocked_by"]


def test_a_far_essential_goal_waits_like_an_important_one():
    assert portfolio([goal("high", target_date="2028-06-30")], apr=24.0)["active_goal"] is None
    assert portfolio([goal("high", target_date=None)], apr=24.0)["active_goal"] is None
    assert portfolio([goal("high", target_date="2028-06-30")], apr=15.0)["goal_allocation"] == 75_000


def test_an_important_goal_waits_for_no_debt_at_20_percent():
    assert portfolio([goal("medium")], apr=20.0)["active_goal"] is None
    assert portfolio([goal("medium")], apr=15.0)["goal_allocation"] == 75_000
    assert portfolio([goal("medium")], apr=None)["active_goal"] is None


def test_a_nice_to_have_waits_for_no_debt_at_10_percent():
    assert portfolio([goal("low")], apr=15.0)["active_goal"] is None
    assert portfolio([goal("low")], apr=8.0)["goal_allocation"] == 75_000


def test_the_more_important_goal_is_funded_first():
    goals = [goal("low", target_date="2027-01-31", goal_id=1), goal("high", target_date="2027-09-30", goal_id=2)]
    assert portfolio(goals, apr=0.0)["active_goal"]["id"] == 2
    # An explicit funding order still wins over importance.
    goals[0]["funding_order"] = 1
    assert portfolio(goals, apr=0.0)["active_goal"]["id"] == 1


def director(savings, debts, months, base=500_000.0, rates_known=True):
    return sd._build_dynamic_director_allocation(
        available_before_allocation=100_000, debts=debts, goal_reserves={}, savings_total=savings,
        emergency_monthly_base=base, rates_known=rates_known, salvavidas_target_months=months,
    )["emergency"]


def debt(rate):
    return {"id": 9, "name": "Préstamo", "remaining_amount": 1_000_000, "interest_rate": rate, "monthly_payment": 50_000}


def test_one_month_reached_and_no_debt_at_20_recommends_three_months():
    fund = director(500_000, [debt(15.0)], 1)
    assert fund["target_months"] == 1 and fund["recommended_target_months"] == 3 and "3" in fund["recommendation"]


def test_no_raise_from_one_month_with_debt_at_20_or_before_reaching_it():
    assert director(500_000, [debt(20.0)], 1)["recommended_target_months"] is None
    assert director(400_000, [debt(5.0)], 1)["recommended_target_months"] is None


def test_three_months_reached_needs_no_debt_at_10_to_recommend_six():
    assert director(1_500_000, [debt(15.0)], 3)["recommended_target_months"] is None
    assert director(1_500_000, [debt(8.0)], 3)["recommended_target_months"] == 6
    assert director(1_500_000, [], 3)["recommended_target_months"] == 6


def test_no_recommendation_when_unknown_or_already_at_six():
    assert director(500_000, [debt(None)], 1, rates_known=False)["recommendation"] is None
    assert director(500_000, [], None)["recommendation"] is None
    assert director(3_000_000, [], 6)["recommended_target_months"] is None
    assert director(500_000, [], 1, base=0)["recommended_target_months"] is None
