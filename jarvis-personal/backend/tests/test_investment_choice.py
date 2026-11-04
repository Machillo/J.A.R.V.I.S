"""A VIP chooses whether investing is in their plan: off until they turn it on. Synthetic data only."""
import pytest
from fastapi import HTTPException

from backend.ai import strategy_dashboard as sd
from backend.user_product import investment_choice as ic

NO_DEBT = {"available_before_allocation": 100_000, "debts": [], "goal_reserves": {}, "savings_total": 400_000, "emergency_monthly_base": 300_000}


def test_with_no_choice_made_it_is_off(monkeypatch):
    monkeypatch.setattr(ic, "get_preference", lambda *_a: {})
    assert ic.wants_investing() is False and ic.get_choice() == {"wants_investing": False}


@pytest.mark.parametrize("stored", [None, "yes", 1, {"wants_investing": "true"}, {"wants_investing": 1}])
def test_anything_but_an_explicit_yes_is_off(monkeypatch, stored):
    monkeypatch.setattr(ic, "get_preference", lambda *_a: stored)
    assert ic.wants_investing() is False


def test_a_choice_is_saved_as_given(monkeypatch):
    saved = {}
    monkeypatch.setattr(ic, "set_preference", lambda key, value: saved.update({key: value}))
    assert ic.update_choice({"wants_investing": True}) == {"wants_investing": True}
    assert saved == {"investment_choice": {"wants_investing": True}}


@pytest.mark.parametrize("payload", [{}, {"wants_investing": "true"}, {"wants_investing": None}, {"wants_investing": 1}])
def test_a_save_refuses_what_is_not_a_choice(payload):
    with pytest.raises(HTTPException) as refused:
        ic.update_choice(payload)
    assert refused.value.status_code == 422


def test_off_gives_investing_nothing_and_every_colon_a_destination():
    off = sd._build_dynamic_director_allocation(**NO_DEBT, investing_wanted=False)
    assert off["investment_allowed"] is False and off["allocation_amounts"]["inversion"] == 0
    assert sum(off["allocation_amounts"].values()) == pytest.approx(100_000)


def test_on_keeps_what_the_strategy_already_allowed():
    on = sd._build_dynamic_director_allocation(**NO_DEBT, investing_wanted=True)
    assert on["investment_allowed"] is True and on["allocation_amounts"]["inversion"] > 0


def test_turning_it_on_never_opens_investing_when_the_rules_do_not_allow_it():
    debts = [{"remaining_amount": 500_000, "interest_rate": 30, "monthly_payment": 30_000}]
    on = sd._build_dynamic_director_allocation(**{**NO_DEBT, "debts": debts}, investing_wanted=True)
    assert on["investment_allowed"] is False and on["allocation_amounts"]["inversion"] == 0
