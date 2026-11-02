"""Tu plan del mes (Owner): every commitment the app knows about comes out before distributing.

- every active fixed expense that is not a debt is part of the plan's living costs and is reserved
  while pending (not only house and phone line);
- expenses recorded by hand reduce what can be distributed;
- the Salvavidas automatic contributions still to come in the cycle are already out: the
  distribution says only what to move on top of them (example: 20 800 for the Salvavidas with
  10 800 automatic → move 10 000).

Synthetic data only; the engine's loaders are stubbed (owner_inputs).
"""
from __future__ import annotations

from datetime import date

import pytest

from backend.ai import owner_commitments
from backend.ai import strategy_dashboard as sd
from backend.ai.test_owner_exact_distribution import CASH, INCOME_LEFT, OBLIGATIONS, _as, _total, owner_inputs  # noqa: F401

WEEKLY = {"enabled": True, "amount": 2500, "frequency": "weekly", "start_date": "2026-10-03"}


def _today(monkeypatch, value):
    class Today(date):
        @classmethod
        def today(cls):
            return value
    monkeypatch.setattr(sd, "date", Today)


def _cycle(monkeypatch, end="2026-11-05"):
    monkeypatch.setattr(sd, "_safe_cycle_report", lambda: {
        "income": {"expected_total": INCOME_LEFT, "received_from_transactions": 0},
        "expenses": {"spending_only": 120_000.0}, "debts": {"payments_current_period": 0},
        "cycle": {"start": "2026-10-06", "end": end}, "expense_cycle": {"start": "2026-09-22", "end": "2026-10-21"}})


def _with_plan(monkeypatch, state, plan=WEEKLY):
    monkeypatch.setattr(sd, "get_salvavidas_state",
                        lambda: {"current_amount": state["savings"], "monthly_base": state["monthly_base"], "auto_contribution": plan})


# The automatic contributions: arithmetic ------------------------------------------------------

def test_the_automatic_part_comes_out_of_the_salvavidas_share_first():
    amounts, taken = owner_commitments.absorb({"fondo_de_emergencia": 20_800, "ataque_de_deuda": 50_000, "vida_controlada": 9_000}, 10_800)
    assert taken == 10_800 and amounts["fondo_de_emergencia"] == 10_000, "move 10 000 on top of the automatic 10 800"
    assert amounts["ataque_de_deuda"] == 50_000 and amounts["vida_controlada"] == 9_000


def test_when_the_automatic_part_is_bigger_free_money_pays_for_it_and_the_goal_keeps_its_share():
    amounts, taken = owner_commitments.absorb(
        {"meta_prioritaria": 5_000, "fondo_de_emergencia": 4_000, "vida_controlada": 3_000, "inversion": 0, "ataque_de_deuda": 20_000}, 10_000)
    assert taken == 10_000
    assert amounts == {"meta_prioritaria": 5_000, "fondo_de_emergencia": 0, "vida_controlada": 0, "inversion": 0,
                       "metas_o_inversion": 0, "ataque_de_deuda": 17_000}


def test_nothing_to_take_from_is_never_negative():
    amounts, taken = owner_commitments.absorb({"meta_prioritaria": 5_000}, 10_000)
    assert taken == 0 and amounts["meta_prioritaria"] == 5_000 and all(value >= 0 for value in amounts.values())


def test_only_the_contributions_still_to_come_in_the_cycle_count():
    salvavidas = {"auto_contribution": WEEKLY}
    cycle = {"cycle": {"start": "2026-10-06", "end": "2026-11-05"}}
    # Saturdays from 3 Oct: 31 Oct (today) and nothing else before 5 Nov.
    assert owner_commitments.automatic_savings(salvavidas, cycle, date(2026, 10, 31))["amount"] == 2_500
    # From 10 Oct: 10, 17, 24 and 31 Oct.
    assert owner_commitments.automatic_savings(salvavidas, cycle, date(2026, 10, 10))["amount"] == 10_000
    assert owner_commitments.automatic_savings({"auto_contribution": {**WEEKLY, "enabled": False}}, cycle, date(2026, 10, 10))["amount"] == 0
    assert owner_commitments.automatic_savings({}, cycle, date(2026, 10, 10))["amount"] == 0


# The plan ----------------------------------------------------------------------------------

def test_the_distribution_already_counts_the_automatic_saving(owner_inputs, monkeypatch):
    _today(monkeypatch, date(2026, 10, 10))
    _cycle(monkeypatch)
    without = _as("owner", sd.build_local_strategy_blueprint)
    _with_plan(monkeypatch, owner_inputs)
    result = _as("owner", sd.build_local_strategy_blueprint)
    share = lambda r, key: next((item["amount"] for item in r["allocation_items"] if item["key"] == key), 0.0)  # noqa: E731
    assert result["automatic_savings"]["amount"] == 10_000
    assert share(result, "fondo_de_emergencia") == round(share(without, "fondo_de_emergencia") - 10_000, 2)
    assert _total(result["allocation_items"]) == round(_total(without["allocation_items"]) - 10_000, 2)
    assert result["allocation_base_amount"] == round(without["allocation_base_amount"] - 10_000, 2)
    warning = next(w for w in result["distribution_warnings"] if w["code"] == "automatic_savings")
    assert "₡10.000" in warning["message"] and "₡2.500" in warning["message"]


def test_the_exact_amount_is_distributed_whole_and_the_salvavidas_share_counts_last_months_automatic_saving(owner_inputs, monkeypatch):
    """The Owner's rule (2026-11-01): the exact amount is the month before's leftover, distributed on the
    1st, all of it. The Salvavidas already got that month's automatic contributions (Saturdays from
    3 Oct: 3, 10, 17, 24 and 31 October = 5 × ₡2 500), so its share goes down by them and that money
    goes to the debts, never out of the amount."""
    _today(monkeypatch, date(2026, 11, 1))
    _cycle(monkeypatch, end="2026-12-05")
    without = _as("owner", sd.get_owner_exact_distribution, 250_000, "CRC")["strategy"]
    _with_plan(monkeypatch, owner_inputs)
    result = _as("owner", sd.get_owner_exact_distribution, 250_000, "CRC")["strategy"]
    share = lambda r, key: next((item["amount"] for item in r["allocation_items"] if item["key"] == key), 0.0)  # noqa: E731
    assert _total(result["allocation_items"]) == 250_000, "every cent of the amount typed"
    assert result["automatic_savings"]["amount"] == 12_500 and result["automatic_savings"]["month"] == "2026-10"
    moved = result["automatic_savings"]["moved_from_salvavidas"]
    assert moved == min(12_500, share(without, "fondo_de_emergencia")) and moved > 0
    assert share(result, "fondo_de_emergencia") == round(share(without, "fondo_de_emergencia") - moved, 2)
    assert share(result, "ataque_de_deuda") == round(share(without, "ataque_de_deuda") + moved, 2)
    assert result["automatic_savings"]["taken_from_distribution"] == 0
    assert any(w["code"] == "automatic_savings_received" for w in result["distribution_warnings"])


def test_the_month_before_counts_four_or_five_paydays():
    weekly = {"enabled": True, "amount": 2500, "frequency": "weekly", "start_date": "2026-10-29"}
    # Started Thursday 29 October: one contribution in October, four in November (5, 12, 19, 26).
    assert owner_commitments.last_month_automatic_savings({"auto_contribution": weekly}, date(2026, 11, 1))["amount"] == 2_500
    assert owner_commitments.last_month_automatic_savings({"auto_contribution": weekly}, date(2026, 12, 1))["amount"] == 10_000
    # December has five Thursdays (3, 10, 17, 24, 31).
    assert owner_commitments.last_month_automatic_savings({"auto_contribution": weekly}, date(2027, 1, 1))["amount"] == 12_500
    assert owner_commitments.last_month_automatic_savings({}, date(2026, 12, 1))["amount"] == 0


def test_expenses_recorded_by_hand_reduce_what_is_distributed(owner_inputs, monkeypatch):
    _cycle(monkeypatch)
    before = _as("owner", sd.build_local_strategy_blueprint)
    monkeypatch.setattr(sd.owner_commitments, "manual_expenses", lambda *_a: {"total": 35_000.0, "count": 2})
    after = _as("owner", sd.build_local_strategy_blueprint)
    assert after["available_before_goals"] == round(before["available_before_goals"] - 35_000, 2)
    assert after["monthly_expenses"] == round(before["monthly_expenses"] + 35_000, 2)


def test_every_fixed_expense_that_is_not_a_debt_is_reserved(monkeypatch):
    rows = [
        {"id": 1, "name": "Casa", "category": "Vivienda", "expected_amount": 200_000, "frequency": "monthly", "interval_months": 1},
        {"id": 2, "name": "Internet", "category": "Servicios", "expected_amount": 25_000, "frequency": "monthly", "interval_months": 1},
        {"id": 3, "name": "Seguro anual", "category": "Seguros", "expected_amount": 120_000, "frequency": "monthly", "interval_months": 12},
        {"id": 4, "name": "Préstamo sintético", "category": "Deudas", "expected_amount": 100_000, "frequency": "monthly", "interval_months": 1},
    ]

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def execute(self, *_a):
            return type("Rows", (), {"fetchall": lambda _self: rows})()

    monkeypatch.setattr(sd, "get_connection", Connection)
    living = sd._get_strategy_living_expenses("ws-test", [{"name": "Préstamo sintético"}])
    assert living["fixed_living_total"] == 200_000 + 25_000 + 10_000, "the debt is already in debts; a yearly bill counts by month"
    assert owner_commitments.fixed_expense_ids(living) == {1, 2, 3}


@pytest.mark.parametrize("amount,text", [(10_800, "₡10.800"), (2_500, "₡2.500"), (1_234_567.4, "₡1.234.567")])
def test_colones_read_like_the_app(amount, text):
    assert owner_commitments.colones(amount) == text


def test_a_pending_fixed_expense_is_reserved_even_if_the_salvavidas_does_not_protect_it(monkeypatch):
    status = {"items": [
        {"fixed_expense": {"id": 2, "name": "Internet"}, "due_this_month": True, "due_date": "2026-10-15", "status": "pending", "expected_amount": 25_000},
        {"fixed_expense": {"id": 5, "name": "Gimnasio"}, "due_this_month": True, "due_date": "2026-10-20", "status": "paid", "expected_amount": 30_000},
        {"fixed_expense": {"id": 9, "name": "Otro"}, "due_this_month": True, "due_date": "2026-10-20", "status": "pending", "expected_amount": 7_000},
    ]}
    monkeypatch.setattr(sd, "get_fixed_expense_status", lambda _month: status)
    cycle = {"cycle": {"start": "2026-10-06", "end": "2026-11-05"}}
    before = sd._pending_mandatory_fixed_expenses(cycle, {"mandatory_expenses": []})
    after = sd._pending_mandatory_fixed_expenses(cycle, {"mandatory_expenses": []}, {2, 5})
    assert before["total"] == 0, "before: only what the Salvavidas protects"
    assert after["total"] == 25_000 and [item["id"] for item in after["items"]] == [2], "a paid one is not reserved twice"
