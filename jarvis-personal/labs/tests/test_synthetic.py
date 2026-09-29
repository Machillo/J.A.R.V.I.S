"""Synthetic datasets: deterministic, invented, within the real column limits, Decimal only."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from labs import billing, limits, synthetic


def _money_values(dataset):
    for user in dataset.users:
        for table, rows in user.rows.items():
            for row in rows:
                for column, value in row.items():
                    if (table, column) in limits.COLUMNS and value is not None:
                        yield table, column, value


@pytest.mark.parametrize("scenario", synthetic.SCENARIOS)
def test_same_seed_same_data_other_seed_other_data(scenario):
    a, b = synthetic.build(scenario, seed=11, heavy_count=300), synthetic.build(scenario, seed=11, heavy_count=300)
    assert [(u.account_id, u.rows) for u in a.users] == [(u.account_id, u.rows) for u in b.users]
    c = synthetic.build(scenario, seed=12, heavy_count=300)
    assert [u.account_id for u in a.users] != [u.account_id for u in c.users]


@pytest.mark.parametrize("scenario", synthetic.SCENARIOS)
def test_users_are_synthetic_and_never_owner(scenario):
    for user in synthetic.build(scenario, heavy_count=100).users:
        assert user.email.endswith("@labs.invalid")
        assert user.identity()["role"] == "user"
        assert user.plan in synthetic.PLANS


@pytest.mark.parametrize("scenario", ("normal", "heavy", "edge"))
def test_money_is_decimal_and_within_each_columns_limit(scenario):
    for table, column, value in _money_values(synthetic.build(scenario, heavy_count=500)):
        assert isinstance(value, Decimal), (table, column)
        assert abs(value) <= limits.max_for(table, column), (table, column)
        assert value == value.quantize(limits.step_for(table, column)), (table, column)


def test_scenarios_cover_the_requested_cases():
    normal = synthetic.build("normal")
    assert {u.plan for u in normal.users} == set(synthetic.PLANS)
    assert {u.base_currency for u in normal.users} == {"CRC", "USD"}
    assert any(d["next_payment_date"] < synthetic.TODAY for u in normal.users for d in u.rows["debts"])  # overdue debt
    assert any(g["status"] == "completed" for u in normal.users for g in u.rows["financial_goals"])
    assert synthetic.build("empty").users[0].rows == {}
    assert len(synthetic.build("heavy").users[0].rows["transactions"]) == 5000
    edge = synthetic.build("edge").users[0].rows
    amounts = {r["description"]: r["amount"] for r in edge["transactions"]}
    assert amounts["MONTO MINIMO"] == Decimal("0.01")
    assert amounts["MAXIMO TRANSACCION"] == Decimal("9999999999.99")  # NUMERIC(12,2), not the 14,2 of expenses
    assert edge["expenses"][0]["amount"] == Decimal("999999999999.99")
    assert date(2028, 2, 29).isoformat() in {r["transaction_date"] for r in edge["transactions"]}
    broken = synthetic.build("broken")
    assert len(broken.invalid_rows) >= 5


def test_limits_follow_the_numeric_types():
    assert limits.numeric_max(12, 2) == Decimal("9999999999.99")
    assert limits.numeric_max(14, 6) == Decimal("99999999.999999")
    assert limits.overflow_for("transactions", "amount") == Decimal("10000000000.00")
    assert limits.max_for("finva_email_candidates", "amount") == Decimal("9999999999999999.99")


def test_billing_simulation_never_grants_an_unverified_paid_plan():
    today = date(2026, 9, 15)
    plans = {(s.plan, s.state): s.effective_plan(today) for s in billing.catalog(today)}
    assert plans[("vip", "verification_failed")] == "free"
    assert plans[("vip", "expired")] == "free"
    assert plans[("vip", "cancelled")] == "vip"  # paid through the end of the period
    assert plans[("vip", "pending_downgrade")] == "vip"  # keeps every benefit until the stored end
    later = date(2026, 10, 1)
    after = {(s.plan, s.state): s.effective_plan(later) for s in billing.catalog(today)}
    assert after[("vip", "pending_downgrade")] == "free"  # a pending paid plan without a store purchase is Free
    assert after[("vip", "cancelled")] == "free"
