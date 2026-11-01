"""The Owner's locked savings blocks once created at the bank: stored, reserved by the plan, and left out
of the next proposal (synthetic data only)."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException

from backend.ai import owner_commitments, owner_debt_block_store as store
from backend.ai import strategy_dashboard as sd
from backend.ai.test_owner_exact_distribution import _as, _total, owner_inputs  # noqa: F401
from backend.finance import debt_savings_blocks

TODAY = date(2026, 11, 2)   # Monday; the paydays are Thursdays
DEBTS = [{"id": 1, "name": "Préstamo sintético", "remaining_amount": 900_000},
         {"id": 2, "name": "Tarjeta sintética", "remaining_amount": 300_000},
         {"id": 3, "name": "Pagada", "remaining_amount": 0}]
BLOCK = {"debt_id": 1, "weekly_amount": 10_000, "start_date": "2026-11-05", "term_months": 6}


@pytest.fixture
def saved(monkeypatch):
    """The workspace's preference in memory; get_debts answers only this workspace's debts."""
    preferences = {}
    monkeypatch.setattr(store, "get_preference", lambda key, default=None: preferences.get(key, default))
    monkeypatch.setattr(store, "set_preference", lambda key, value: preferences.__setitem__(key, value))
    monkeypatch.setattr(store, "get_debts", lambda: [dict(debt) for debt in DEBTS])
    monkeypatch.setattr(store, "costa_rica_today", lambda: TODAY)
    return preferences


def test_a_block_created_at_the_bank_is_stored_with_its_maturity(saved):
    block = store.create_block(dict(BLOCK))["block"]
    assert (block["debt_name"], block["maturity_date"], block["term_months"]) == ("Préstamo sintético", "2027-05-05", 6)
    assert (block["contributions_total"], block["total_at_maturity"], block["saved_so_far"]) == (26, 260_000, 0)
    assert store.stored_blocks()[0]["id"] == block["id"]


def test_the_banks_minimum_applies_only_to_its_term(saved):
    assert store.create_block({**BLOCK, "term_months": 3, "weekly_amount": 3750})["block"]["term_months"] == 3
    assert store.create_block({**BLOCK, "debt_id": 2, "weekly_amount": 3000})["block"]["weekly_amount"] == 3000


def test_one_block_per_debt_at_a_time(saved):
    store.create_block(dict(BLOCK))
    with pytest.raises(HTTPException) as error:
        store.create_block(dict(BLOCK))      # a double tap or a retry never makes two
    assert error.value.status_code == 409 and len(store.stored_blocks()) == 1
    assert store.create_block({**BLOCK, "debt_id": 2})["block"]["debt_id"] == 2


@pytest.mark.parametrize("change, status", [
    ({"debt_id": 99}, 404),              # not a debt of this workspace
    ({"debt_id": 3}, 404),               # already paid
    ({"weekly_amount": 0}, 422), ({"weekly_amount": -500}, 422), ({"weekly_amount": "abc"}, 422),
    ({"term_months": 2}, 422), ({"term_months": 61}, 422), ({"term_months": 6.5}, 422),
    ({"term_months": 3, "weekly_amount": 3000}, 422),   # the bank asks at least ₡3 750 a contribution for 3 months
    ({"start_date": "2026-09-01"}, 422), ({"start_date": "2027-03-01"}, 422), ({"start_date": "mañana"}, 422),
])
def test_an_invalid_block_is_refused_and_nothing_is_stored(saved, change, status):
    with pytest.raises(HTTPException) as error:
        store.create_block({**BLOCK, **change})
    assert error.value.status_code == status and store.stored_blocks() == []


def test_cancelling_removes_only_that_block(saved):
    first = store.create_block(dict(BLOCK))["block"]["id"]
    second = store.create_block({**BLOCK, "debt_id": 2})["block"]["id"]
    store.cancel_block(first)
    assert [block["id"] for block in store.stored_blocks()] == [second]
    with pytest.raises(HTTPException) as error:
        store.cancel_block("not-a-block")
    assert error.value.status_code == 404


def test_progress_counts_the_paydays_already_passed_never_the_banks_interest():
    block = store.normalize({"blocks": [{"id": "b1", **BLOCK, "maturity_date": "2027-05-05"}]})[0]
    progress = store.with_progress(block, date(2026, 11, 20))     # 5, 12 and 19 November
    assert (progress["contributions_done"], progress["saved_so_far"], progress["next_date"]) == (3, 30_000, "2026-11-26")
    assert store.with_progress(block, date(2027, 5, 5))["matured"] is True
    assert store.active([block], date(2027, 5, 5)) == []


def test_a_corrupt_stored_block_is_ignored_never_guessed():
    raw = {"blocks": [{"id": "b1", "debt_id": 1, "weekly_amount": "x", "start_date": "2026-11-05", "maturity_date": "2027-05-05"},
                      {"id": "b2", "debt_id": 1, "weekly_amount": 100, "start_date": "2027-05-05", "maturity_date": "2026-11-05"},
                      "not a block"]}
    assert store.normalize(raw) == [] and store.normalize(None) == []


def test_the_next_proposal_uses_only_what_is_left_and_skips_a_debt_with_a_block():
    debts = [{"id": 1, "name": "A", "remaining_amount": 1_000_000, "interest_rate": 24, "minimum_payment": 40_000, "payoff_month": 20},
             {"id": 2, "name": "B", "remaining_amount": 2_000_000, "interest_rate": 30, "minimum_payment": 60_000, "payoff_month": 30}]
    result = debt_savings_blocks.propose(today=TODAY, safe_monthly_attack=60_000, probable_monthly_attack=60_000, debts=debts,
                                         committed_weekly=10_000, blocked_debt_ids={1})
    assert result["weekly_safe_amount"] == 3_500 and result["proposal"]["debt"]["id"] == 2
    everything = debt_savings_blocks.propose(today=TODAY, safe_monthly_attack=60_000, probable_monthly_attack=60_000,
                                             debts=debts, committed_weekly=13_500, blocked_debt_ids={1})
    assert everything["status"] == "no_surplus"


def test_block_contributions_come_out_of_the_debt_attack_first():
    amounts, taken = owner_commitments.absorb({"fondo_de_emergencia": 20_000, "ataque_de_deuda": 30_000, "vida_controlada": 9_000},
                                              40_000, owner_commitments.BLOCK_ABSORB_ORDER)
    assert taken == 40_000 and amounts["ataque_de_deuda"] == 0 and amounts["vida_controlada"] == 0
    assert amounts["fondo_de_emergencia"] == 19_000


def test_only_the_block_contributions_still_to_come_in_the_cycle_count():
    block = store.normalize({"blocks": [{"id": "b1", **BLOCK, "maturity_date": "2027-05-05", "debt_name": "Préstamo"}]})[0]
    cycle = {"cycle": {"start": "2026-10-06", "end": "2026-11-20"}}
    # 5, 12 and 19 November from today (Monday 2 November).
    assert owner_commitments.block_savings([block], cycle, TODAY) == {
        "amount": 30_000, "count": 3, "blocks": [{"debt_name": "Préstamo", "count": 3, "amount": 30_000}]}
    assert owner_commitments.block_savings([block], cycle, date(2026, 11, 21))["amount"] == 0


def test_the_plan_sets_the_blocks_aside_before_distributing(owner_inputs, monkeypatch):
    class Today(date):
        @classmethod
        def today(cls):
            return TODAY
    monkeypatch.setattr(sd, "date", Today)
    monkeypatch.setattr(sd, "_safe_cycle_report", lambda: {
        "income": {"expected_total": 900_000.0, "received_from_transactions": 0},
        "expenses": {"spending_only": 120_000.0}, "debts": {"payments_current_period": 0},
        "cycle": {"start": "2026-10-06", "end": "2026-11-20"}})
    without = _as("owner", sd.build_local_strategy_blueprint)
    owner_inputs["blocks"] = [{"id": "b1", **BLOCK, "maturity_date": "2027-05-05", "debt_name": "Préstamo"}]
    result = _as("owner", sd.build_local_strategy_blueprint)
    assert result["debt_savings_blocks"]["amount"] == 30_000
    taken = result["debt_savings_blocks"]["taken_from_distribution"]
    assert taken > 0 and _total(result["allocation_items"]) == round(_total(without["allocation_items"]) - taken, 2)
    assert any(w["code"] == "debt_savings_blocks" for w in result["distribution_warnings"])
