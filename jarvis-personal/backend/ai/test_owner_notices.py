"""What a notice says: the change, where the money goes and what the automatic savings do (synthetic)."""
from __future__ import annotations

import pytest

from backend.ai.owner_notices import _changed, _destination, savings_decision


def test_a_lower_installment_says_what_it_freed():
    title, changed, freed = _changed({"debt_name": "Tarjeta", "old_payment": "30000", "new_payment": 24000})
    assert "Tarjeta" in title and freed == 6000
    assert "₡30.000" in changed and "₡24.000" in changed and "₡6.000" in changed


def test_a_shorter_term_frees_nothing_and_says_so():
    _, changed, freed = _changed({"debt_name": "Préstamo", "old_payment": 30000, "new_payment": None, "old_installments": 12, "new_installments": 8})
    assert freed is None and "8" in changed and "12" in changed


@pytest.mark.parametrize("facts", [
    {"debt_name": "A", "old_payment": 100, "new_payment": 200},    # it went up: nothing freed
    {"debt_name": "A", "old_payment": None, "new_payment": 200},   # the old one is unknown: nothing invented
])
def test_nothing_is_called_freed_without_a_known_drop(facts):
    assert _changed(facts)[2] is None


def test_the_money_goes_where_the_strategy_attacks():
    blueprint = {"allocation_items": [{"key": "vida_controlada"}, {"key": "ataque_de_deuda", "target_name": "Tarjeta BAC"}]}
    assert "Tarjeta BAC" in _destination(blueprint, 6000)
    assert _destination(blueprint, None) is None, "nothing freed: nowhere to go"
    assert "estrategia" in _destination({"allocation_items": []}, 6000), "no target: never one invented"


def proposal(mode):
    return {"status": "proposal", "committed_weekly": 12500,
            "proposal": {"mode": mode, "weekly_amount": 1500, "term_months": 6, "debt": {"name": "Préstamo"}}}


def test_the_savings_decision_follows_the_engine():
    yes = savings_decision(proposal("block"))
    assert yes["decision"] == "yes" and "₡1.500" in yes["text"] and "Préstamo" in yes["text"] and "₡12.500" in yes["text"]
    assert savings_decision(proposal("presave"))["decision"] == "partial"


@pytest.mark.parametrize("status", ["short_debts_only", "pay_directly", "no_surplus", "no_debts"])
def test_not_for_now_always_says_why(status):
    decision = savings_decision({"status": status})
    assert decision["decision"] == "no" and decision["text"].startswith("De momento no: ") and len(decision["text"]) > 20


def test_an_unknown_answer_is_not_a_decision():
    assert savings_decision({"status": "something_new"})["decision"] == "unknown"
