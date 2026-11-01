"""Debt what-if scenarios: pay a debt off, make an extra payment, take a new debt. Read-only and
deterministic; every figure is the monthly money left after essentials and debt payments (the
strategy's margin). Synthetic data only."""
from __future__ import annotations

import copy

import pytest

from backend.user_product.debt_scenarios import DebtScenarioError, build_debt_scenario


def snapshot(**overrides):
    base = {
        "monthly_income_estimate": 900_000,
        "essential_monthly_expenses": 400_000,
        "liquid_savings": 1_000_000,
        "emergency_fund_target": 0,
        "debts": [
            {"id": 1, "name": "Tarjeta A", "remaining_amount": 600_000, "monthly_payment": 60_000, "interest_rate": 36, "debt_type": "credit_card"},
            {"id": 2, "name": "Préstamo B", "remaining_amount": 2_400_000, "monthly_payment": 100_000, "interest_rate": 18, "debt_type": "loan"},
        ],
        "goals": [],
    }
    base.update(overrides)
    return base


def test_leftover_is_income_minus_essentials_minus_debt_payments():
    result = build_debt_scenario(snapshot(), "pay_off", debt_id=1)
    assert result["monthly_leftover"]["current"] == 900_000 - 400_000 - 60_000 - 100_000


def test_paying_a_debt_off_frees_its_monthly_payment():
    result = build_debt_scenario(snapshot(), "pay_off", debt_id=1)
    assert result["monthly_leftover"] == {"current": 340_000, "scenario": 400_000, "change": 60_000}
    assert result["one_time_amount"] == 600_000
    assert result["liquid_savings_after"] == 400_000
    assert result["payoff"]["interest"] > 0, "the interest it would still have cost"


def test_an_extra_payment_shows_both_lender_policies():
    result = build_debt_scenario(snapshot(), "extra_payment", debt_id=2, amount=600_000)
    lower, shorter = result["options"]["lower_installment"], result["options"]["shorter_term"]
    # Lower installment: same remaining term, smaller payment, more left each month.
    assert 0 < lower["monthly_payment"] < 100_000
    assert lower["monthly_leftover"] == round(340_000 + (100_000 - lower["monthly_payment"]), 2)
    # Shorter term: same payment, fewer months, less interest; the month is unchanged.
    assert shorter["monthly_payment"] == 100_000
    assert shorter["monthly_leftover"] == 340_000
    assert shorter["months_saved"] > 0 and shorter["interest_saved"] > 0
    assert result["one_time_amount"] == 600_000
    assert result["liquid_savings_after"] == 400_000


def test_a_new_debt_takes_its_payment_out_of_the_month():
    declared = build_debt_scenario(snapshot(), "new_debt", amount=1_000_000, monthly_payment=50_000, name="Moto")
    assert declared["monthly_leftover"] == {"current": 340_000, "scenario": 290_000, "change": -50_000}
    assert declared["debt"]["monthly_payment_source"] == "declared"
    computed = build_debt_scenario(snapshot(), "new_debt", amount=1_200_000, annual_rate=0, term_months=24)
    assert computed["debt"]["monthly_payment"] == 50_000
    assert computed["debt"]["monthly_payment_source"] == "computed"
    assert computed["monthly_leftover"]["scenario"] == 290_000
    with_interest = build_debt_scenario(snapshot(), "new_debt", amount=1_200_000, annual_rate=24, term_months=24)
    assert with_interest["debt"]["monthly_payment"] > 50_000


def test_unknown_income_leaves_the_month_unknown_never_zero():
    result = build_debt_scenario(snapshot(monthly_income_estimate=0), "pay_off", debt_id=1)
    assert result["monthly_leftover"] == {"current": None, "scenario": None, "change": None}
    assert result["one_time_amount"] == 600_000


def test_an_unknown_payment_or_rate_is_never_made_up():
    debts = snapshot()["debts"]
    no_payment = snapshot(debts=[{**debts[0], "monthly_payment": None}, debts[1]])
    result = build_debt_scenario(no_payment, "pay_off", debt_id=1)
    assert result["monthly_leftover"]["change"] is None and result["monthly_leftover"]["scenario"] is None
    no_rate = snapshot(debts=[debts[0], {**debts[1], "interest_rate": None}])
    extra = build_debt_scenario(no_rate, "extra_payment", debt_id=2, amount=600_000)
    assert extra["options"]["lower_installment"]["monthly_payment"] is None
    assert extra["options"]["shorter_term"]["interest_saved"] is None
    assert extra["warnings"], "it says what is missing"


def test_unknown_savings_leave_the_balance_after_unknown():
    result = build_debt_scenario(snapshot(liquid_savings=None), "pay_off", debt_id=1)
    assert result["liquid_savings_after"] is None


def test_extra_payment_bounds_and_inputs_are_validated():
    with pytest.raises(DebtScenarioError) as covers:
        build_debt_scenario(snapshot(), "extra_payment", debt_id=1, amount=600_000)
    assert covers.value.code == "covers_debt"
    for kwargs, code in [
        ({"kind": "pay_off"}, "debt_required"),
        ({"kind": "pay_off", "debt_id": 99}, "debt_not_found"),
        ({"kind": "extra_payment", "debt_id": 1}, "amount_required"),
        ({"kind": "new_debt", "amount": 500_000}, "payment_or_terms_required"),
        ({"kind": "new_debt", "amount": 500_000, "annual_rate": 12}, "payment_or_terms_required"),
    ]:
        with pytest.raises(DebtScenarioError) as error:
            build_debt_scenario(snapshot(), **kwargs)
        assert error.value.code == code


def test_scenarios_never_change_the_snapshot():
    data = snapshot()
    before = copy.deepcopy(data)
    for kwargs in ({"kind": "pay_off", "debt_id": 1}, {"kind": "extra_payment", "debt_id": 2, "amount": 100_000},
                   {"kind": "new_debt", "amount": 100_000, "monthly_payment": 10_000}):
        build_debt_scenario(data, **kwargs)
    assert data == before


def test_the_same_inputs_give_the_same_answer_in_both_languages():
    from backend.core.i18n import use_language

    numbers, texts = [], []
    for language in ("es", "en"):
        with use_language(language):
            result = build_debt_scenario(snapshot(), "extra_payment", debt_id=2, amount=300_000)
        numbers.append((result["monthly_leftover"], result["options"], result["one_time_amount"]))
        texts.append(result["explanation"])
    assert numbers[0] == numbers[1]
    assert texts[0] != texts[1], "only the words change"


def test_explanations_carry_no_amounts():
    # Amounts are fields the app formats (₡350.000 in Spanish); a number inside a sentence would not be.
    for kwargs in ({"kind": "pay_off", "debt_id": 1}, {"kind": "extra_payment", "debt_id": 2, "amount": 300_000},
                   {"kind": "new_debt", "amount": 1_000_000, "monthly_payment": 50_000}):
        assert not any(ch.isdigit() for ch in build_debt_scenario(snapshot(), **kwargs)["explanation"])


# The endpoint: the caller's own workspace snapshot, behind the VIP feature, read-only.
from fastapi import HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from backend.user_product import debt_scenarios  # noqa: E402
from backend.user_product.models import DebtScenarioRequest  # noqa: E402


@pytest.fixture
def endpoint(monkeypatch):
    calls = {"features": []}
    monkeypatch.setattr("backend.auth.saas.require_feature", lambda code: calls["features"].append(code) or True)
    # The workspace-scoped snapshot: only this workspace's debts are in it.
    monkeypatch.setattr("backend.user_product.service._strategy_snapshot", lambda: snapshot())
    return calls


def test_the_endpoint_is_behind_the_vip_strategy_feature(endpoint):
    result = debt_scenarios.simulate_debt_scenario(DebtScenarioRequest(kind="pay_off", debt_id=1))
    assert endpoint["features"] == ["strategy_vip"]
    assert result["monthly_leftover"]["change"] == 60_000


def test_a_debt_of_another_workspace_is_not_found(endpoint):
    # Debt 99 belongs to someone else: it is not in the caller's snapshot, so it is never used.
    with pytest.raises(HTTPException) as error:
        debt_scenarios.simulate_debt_scenario(DebtScenarioRequest(kind="pay_off", debt_id=99))
    assert error.value.status_code == 404 and error.value.detail["code"] == "debt_not_found"


def test_unusable_inputs_are_a_422_with_a_stable_code(endpoint):
    with pytest.raises(HTTPException) as error:
        debt_scenarios.simulate_debt_scenario(DebtScenarioRequest(kind="extra_payment", debt_id=1, amount=900_000))
    assert error.value.status_code == 422 and error.value.detail["code"] == "covers_debt"


def test_the_request_refuses_non_finite_or_unknown_inputs():
    for bad in ({"kind": "pay_off", "debt_id": 1, "amount": float("nan")}, {"kind": "new_debt", "amount": float("inf")},
                {"kind": "mortgage"}, {"kind": "new_debt", "amount": 10, "term_months": 0}, {"kind": "pay_off", "debt_id": 0}):
        with pytest.raises(ValidationError):
            DebtScenarioRequest(**bad)


# Refinance one debt / consolidate several into one loan: today's payments, months and interest
# against the new loan's; a fee is borrowed and counted as a cost; unknowns stay unknown.
def test_refinancing_at_a_lower_rate_frees_money_and_saves_interest():
    result = build_debt_scenario(snapshot(), "refinance", debt_id=1, annual_rate=18, term_months=12)
    comparison = result["comparison"]
    assert comparison["current"]["monthly_payment"] == 60_000
    new = comparison["scenario"]["monthly_payment"]
    assert 0 < new < 60_000 and result["monthly_leftover"]["change"] == round(60_000 - new, 2)
    assert comparison["scenario"]["months"] == 12
    assert comparison["total_saved"] > 0, "a lower rate costs less interest"
    assert result["debt"]["id"] == 1 and result["debts"][0]["name"] == "Tarjeta A"


def test_a_fee_is_borrowed_and_counted_as_a_cost():
    free = build_debt_scenario(snapshot(), "refinance", debt_id=1, annual_rate=18, term_months=12)
    paid = build_debt_scenario(snapshot(), "refinance", debt_id=1, annual_rate=18, term_months=12, amount=50_000)
    assert paid["debt"]["remaining_amount"] == 650_000
    assert paid["comparison"]["scenario"]["fee"] == 50_000
    assert paid["comparison"]["total_saved"] < free["comparison"]["total_saved"] - 50_000


def test_consolidating_two_debts_into_one_payment():
    result = build_debt_scenario(snapshot(), "consolidate", debt_ids=[1, 2], annual_rate=15, term_months=48)
    assert result["debt"]["remaining_amount"] == 3_000_000 and result["debt"]["id"] is None
    assert [debt["name"] for debt in result["debts"]] == ["Tarjeta A", "Préstamo B"]
    assert result["comparison"]["current"]["monthly_payment"] == 160_000
    assert result["monthly_leftover"]["change"] == round(160_000 - result["comparison"]["scenario"]["monthly_payment"], 2)


def test_consolidating_needs_two_debts_and_terms():
    with pytest.raises(DebtScenarioError) as one:
        build_debt_scenario(snapshot(), "consolidate", debt_ids=[1, 1], annual_rate=15, term_months=48)
    assert one.value.code == "debts_required"
    with pytest.raises(DebtScenarioError) as terms:
        build_debt_scenario(snapshot(), "refinance", debt_id=1)
    assert terms.value.code == "terms_required"
    with pytest.raises(DebtScenarioError) as other:
        build_debt_scenario(snapshot(), "consolidate", debt_ids=[1, 99], annual_rate=15, term_months=48)
    assert other.value.code == "debt_not_found", "a debt outside the caller's snapshot is never used"


def test_an_unknown_rate_leaves_the_interest_comparison_unknown():
    debts = copy.deepcopy(snapshot()["debts"])
    debts[0]["interest_rate"] = None
    result = build_debt_scenario(snapshot(debts=debts), "refinance", debt_id=1, annual_rate=18, term_months=12)
    assert result["comparison"]["current"]["interest"] is None and result["comparison"]["total_saved"] is None
    assert result["comparison"]["scenario"]["monthly_payment"] is not None, "the new loan is still known"
    assert any("tasa" in warning or "rate" in warning for warning in result["warnings"])
