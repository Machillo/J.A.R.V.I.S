"""Patrimonio → Proyecciones are never built on an unknown (UX-14, UNKNOWN ≠ 0).

A projection needs the monthly margin (income, essential expenses, every debt payment) and today's
cash (confirmed balances or declared savings). With all of them known it keeps the 1, 3, 6 and
12-month points; with any missing, `projections` is empty and `projection_status.missing` names the
inputs with the codes Hoy already uses. The recommended debt plan adds the margin to the payments,
so it is not recommended from an unknown margin either. All data is synthetic.

Default synthetic profile (test_mail_preserves_financial_state): declared salary 1.000.000,
essentials 400.000, savings 300.000, one card with balance 500.000 and a 50.000 monthly payment →
margin 550.000.
"""
import pytest

from backend.user_product.test_vip_command_center_hoy_unknown import _own_debts, _profile, ledger  # noqa: F401 (fixture)
from backend.user_product.test_vip_command_center_unknown_not_zero import _center


def _incomplete(center, missing):
    assert center["projections"] == []
    assert center["projection_status"] == {"complete": False, "missing": missing}


def test_fully_known_inputs_project_1_3_6_and_12_months(ledger):
    center = _center()
    assert center["projection_status"] == {"complete": True, "missing": []}
    assert [point["months"] for point in center["projections"]] == [1, 3, 6, 12]
    six = next(point for point in center["projections"] if point["months"] == 6)
    assert six["cash"] == 300000 + 550000 * 6
    assert six["debt"] == 500000 - 50000 * 6
    assert six["net_worth"] == six["cash"] - six["debt"]


def test_unknown_income_projects_nothing(ledger):
    _profile(ledger).update({"fixed_monthly_salary": None})
    _incomplete(_center(), ["income"])


def test_unknown_essential_expenses_project_nothing(ledger):
    _profile(ledger).update({"essential_monthly_expenses": None})
    _incomplete(_center(), ["essential_expenses"])


def test_a_declared_zero_of_essential_expenses_is_a_known_zero(ledger):
    _profile(ledger).update({"essential_monthly_expenses": 0})
    center = _center()
    assert center["projection_status"]["complete"] is True
    assert center["projections"][0]["cash"] == 300000 + 950000


def test_unknown_savings_project_nothing(ledger):
    # Without confirmed balances, undeclared savings are an unknown starting cash, not ₡0.
    _profile(ledger).update({"liquid_savings": None})
    _incomplete(_center(), ["savings"])


def test_an_unknown_debt_payment_projects_nothing(ledger):
    _own_debts(ledger)[0]["monthly_payment"] = 0  # how create_user_debt stores an unknown payment
    _incomplete(_center(), ["debt_payments"])


def test_several_missing_inputs_are_all_named_in_order(ledger):
    _profile(ledger).update({"fixed_monthly_salary": None, "essential_monthly_expenses": None, "liquid_savings": None})
    _own_debts(ledger)[0]["monthly_payment"] = 0
    _incomplete(_center(), ["income", "essential_expenses", "debt_payments", "savings"])


@pytest.mark.parametrize("change", [
    {"fixed_monthly_salary": None},
    {"essential_monthly_expenses": None},
    {"liquid_savings": None},
])
def test_no_projected_figure_is_ever_made_from_an_unknown(ledger, change):
    _profile(ledger).update(change)
    center = _center()
    figures = [point.get(key) for point in center["projections"] for key in ("cash", "debt", "net_worth")]
    assert figures == []  # not ₡0, not a fallback: no figure at all


def test_the_debt_plan_is_not_recommended_from_an_unknown_margin(ledger):
    assert _center()["debt_planner"]["recommended"] is not None
    _profile(ledger).update({"essential_monthly_expenses": None})
    assert _center()["debt_planner"]["recommended"] is None


def test_unknown_savings_alone_keep_the_debt_plan(ledger):
    # The plan needs the margin, not the starting cash.
    _profile(ledger).update({"liquid_savings": None})
    assert _center()["debt_planner"]["recommended"] is not None
