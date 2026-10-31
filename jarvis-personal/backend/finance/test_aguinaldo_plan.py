"""AG-1 — the aguinaldo split: December first, then the Salvavidas to one month, then high-cost debt
(highest rate first), then the rest. Every colón is assigned once; unknown is never zero. Synthetic data."""
from backend.finance import aguinaldo_plan


def _amounts(plan):
    return {item["key"]: item["amount"] for item in plan["items"]}


def test_with_costly_debt_december_then_one_month_then_the_most_expensive_debt():
    plan = aguinaldo_plan.build(500_000, {"current_amount": 100_000, "monthly_base": 300_000}, [
        {"id": 1, "name": "Tarjeta", "remaining_amount": 400_000, "interest_rate": 48},
        {"id": 2, "name": "Préstamo", "remaining_amount": 2_000_000, "interest_rate": 14},
    ])
    assert _amounts(plan) == {"december": 75_000, "salvavidas": 200_000, "debt-1": 225_000}
    assert sum(item["amount"] for item in plan["items"]) == 500_000


def test_without_costly_debt_the_rest_fills_the_salvavidas_to_three_months_then_goals():
    plan = aguinaldo_plan.build(600_000, {"current_amount": 250_000, "monthly_base": 100_000}, [])
    assert _amounts(plan) == {"december": 120_000, "salvavidas": 50_000, "goals": 430_000}


def test_a_debt_is_never_paid_more_than_what_is_owed():
    plan = aguinaldo_plan.build(400_000, {"current_amount": 900_000, "monthly_base": 100_000},
                                [{"id": 3, "name": "Tarjeta", "remaining_amount": 50_000, "interest_rate": 30}])
    assert _amounts(plan)["debt-3"] == 50_000
    assert sum(item["amount"] for item in plan["items"]) == 400_000


def test_unknown_is_never_zero():
    plan = aguinaldo_plan.build(300_000, {"current_amount": None, "monthly_base": 100_000},
                                [{"id": 4, "name": "Sin tasa", "remaining_amount": 100_000, "interest_rate": None}])
    assert "salvavidas" not in _amounts(plan), "an unknown balance is not filled blindly"
    assert plan["unknown_rates"] == ["Sin tasa"] and "debt-4" not in _amounts(plan)
    assert aguinaldo_plan.build(None, {}, []) is None and aguinaldo_plan.build(0, {}, []) is None
