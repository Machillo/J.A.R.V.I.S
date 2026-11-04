"""The Owner's distribution as an analysis of his month. Synthetic data only, no database."""
from __future__ import annotations

import pytest

from backend.ai import owner_analysis as oa
from backend.ai import strategy_dashboard as sd
from backend.ai.owner_distribution import debt_attack_targets

EXPENSIVE = {"id": 1, "name": "Tarjeta cara", "remaining_amount": 600_000, "interest_rate": 35, "monthly_payment": 30_000}
SMALL_ZERO = {"id": 2, "name": "Cuota chica", "remaining_amount": 50_000, "interest_rate": 0, "monthly_payment": 5_000}
BIG_CHEAP = {"id": 3, "name": "Préstamo grande", "remaining_amount": 3_000_000, "interest_rate": 9, "monthly_payment": 65_000}
DEBTS = [EXPENSIVE, SMALL_ZERO, BIG_CHEAP]


def month(income=500_000, lived=100_000, spent=0.0, yield_=None):
    return oa.OwnerMonth(income=income, installments=100_000, fixed_expenses=200_000, lived_variable=lived,
                         spent_this_cycle=spent, net_dividend_yield=yield_)


def decide(remaining=100_000, a_month=None, debts=DEBTS, savings=1_000_000, base=300_000, target=1, mini=150_000, apr=35.0):
    return oa.decide(remaining, a_month or month(), debts, savings, base, target, mini, apr)


def amounts(decision, remaining=100_000):
    return {key: round(value * remaining, 2) for key, value in decision["weights"].items()}


def test_a_negative_month_pays_first_what_relieves_it_most():
    decision = decide(a_month=month(income=350_000))
    assert decision["analysis"]["margin"] < 0 and decision["analysis"]["order"] == "relief"
    assert decision["analysis"]["debt_order"][0] == SMALL_ZERO["id"], "10% of its balance a month frees more than the expensive one"
    assert "alivia" in decision["reason"] and SMALL_ZERO["name"] in decision["reason"]


def test_a_month_that_covers_itself_pays_the_highest_rate_first():
    decision = decide(a_month=month(income=600_000))
    assert decision["analysis"]["margin"] > 0 and decision["analysis"]["order"] == "rate"
    assert decision["analysis"]["debt_order"][0] == EXPENSIVE["id"]


def test_living_costs_still_to_come_go_first_not_a_fixed_percentage():
    assert amounts(decide(a_month=month(lived=60_000, spent=20_000)))["life"] == 40_000
    assert amounts(decide(a_month=month(lived=60_000, spent=90_000)))["life"] == 0, "already spent: nothing is reserved again"
    only_life = amounts(decide(a_month=month(lived=500_000)))
    assert only_life["life"] == 100_000 and only_life["debt"] == 0, "it never promises more than there is"


def test_unknown_living_costs_keep_the_old_share_and_say_so():
    decision = decide(a_month=month(lived=None))
    assert amounts(decision)["life"] == pytest.approx(15_000)
    assert decision["analysis"]["lived_variable_known"] is False and decision["analysis"]["lived_variable"] is None
    assert "todavía no se conocen" in decision["reason"]


def test_the_salvavidas_stays_on_course_and_the_rest_goes_to_debts():
    split = amounts(decide(a_month=month(lived=0), savings=60_000, base=300_000, mini=150_000))
    assert split["emergency"] == 15_000, "a sixth of what is missing for the mini fund"
    assert split["debt"] == 85_000 and split["investment"] == 0


def test_with_a_full_salvavidas_all_of_the_rest_attacks_debts():
    split = amounts(decide(a_month=month(lived=0), savings=1_000_000))
    assert split["emergency"] == 0 and split["debt"] == 100_000


@pytest.mark.parametrize("label,apr,savings,yield_", [
    ("expensive debt", 35.0, 1_000_000, 50.0),
    ("ten percent", 10.0, 1_000_000, 50.0),
    ("unknown rate", None, 1_000_000, 50.0),
    ("under 3 months", 5.0, 899_999, 50.0),
    ("no dividend plan", 5.0, 1_000_000, None),
    ("the debt costs more than the dividend", 5.0, 1_000_000, 2.8),
])
def test_investing_with_debts_stays_closed(label, apr, savings, yield_):
    decision = decide(a_month=month(lived=0, yield_=yield_), apr=apr, savings=savings)
    assert decision["investment_allowed"] is False and amounts(decision)["investment"] == 0, label


def test_investing_opens_only_when_it_beats_every_rate_with_3_months_saved():
    decision = decide(a_month=month(lived=0, yield_=2.8), debts=[SMALL_ZERO], apr=0.0, savings=900_000)
    assert decision["investment_allowed"] is True and amounts(decision)["investment"] == 100_000


def test_without_debts_a_month_saved_builds_wealth_and_less_fills_the_salvavidas():
    assert amounts(decide(a_month=month(lived=0), debts=[], apr=0.0, savings=400_000))["investment"] == 100_000
    split = amounts(decide(a_month=month(lived=0), debts=[], apr=0.0, savings=200_000))
    assert split["emergency"] == 100_000 and split["investment"] == 0


@pytest.mark.parametrize("income,lived,savings,debts,apr", [
    (350_000, 100_000, 0, DEBTS, 35.0), (600_000, None, 60_000, DEBTS, 35.0), (900_000, 0, 1_000_000, [SMALL_ZERO], 0.0), (900_000, 0, 200_000, [], 0.0),
])
@pytest.mark.parametrize("remaining", [0.01, 7_531.37, 100_000, 2_500_000])
def test_every_colon_has_a_destination(income, lived, savings, debts, apr, remaining):
    weights = decide(remaining, month(income=income, lived=lived), debts, savings=savings, apr=apr)["weights"]
    assert sum(weights.values()) == pytest.approx(1) and all(value >= 0 for value in weights.values())


def test_the_comparison_shows_what_each_order_costs():
    compared = decide()["analysis"]["compared"]
    assert compared["rate"]["interest"] < compared["relief"]["interest"]
    assert compared["relief"]["installments_after_a_year"] <= compared["rate"]["installments_after_a_year"]


def test_a_projection_that_never_ends_is_unknown():
    never = oa.project([{"id": 1, "remaining_amount": 1_000_000, "interest_rate": 40, "monthly_payment": 100}], oa.rate_order, 0)
    assert never == {"months": None, "interest": None, "installments_after_a_year": None}


def test_the_engine_uses_the_analysis_only_when_it_gets_his_month():
    kwargs = {"available_before_allocation": 100_000, "debts": DEBTS, "goal_reserves": {}, "savings_total": 1_000_000, "emergency_monthly_base": 300_000}
    table = sd._build_dynamic_director_allocation(**kwargs)
    assert table["owner_analysis"] is None and table["allocation_amounts"]["vida_controlada"] == 15_000, "Users keep the table"
    his = sd._build_dynamic_director_allocation(**kwargs, owner_month=month(lived=40_000), salvavidas_target_months=1)
    assert his["owner_analysis"]["order"] == "rate" and his["allocation_amounts"]["vida_controlada"] == 40_000
    assert sum(his["allocation_amounts"].values()) == pytest.approx(100_000)


def test_no_surplus_stays_cash_protection():
    his = sd._build_dynamic_director_allocation(available_before_allocation=0, debts=DEBTS, goal_reserves={}, savings_total=0,
                                                emergency_monthly_base=300_000, owner_month=month())
    assert his["mode"] == "cash_protection" and his["owner_analysis"] is None


def test_what_confirm_records_follows_the_same_order():
    targets, left = debt_attack_targets(DEBTS, 60_000, [2, 1, 3])
    assert [row["debt_id"] for row in targets] == [2, 1] and targets[0]["amount"] == 50_000 and left == 0
    assert debt_attack_targets(DEBTS, 60_000)[0][0]["debt_id"] != 2, "without an analysis, the strategy's own order"


def test_the_debt_cascade_follows_the_same_order():
    timeline, _months, _pool = sd._simulate_debt_cascade(DEBTS, recurring_monthly_extra=10_000, owner_rules=True, order_ids=[2, 1, 3])
    assert timeline[0]["name"] == SMALL_ZERO["name"]


class FakeConn:
    def __init__(self, rows):
        self.rows = list(rows)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params):
        assert "workspace_id=%s" in sql and params[0] == "ws-synthetic"
        return self

    def fetchone(self):
        return self.rows.pop(0)


def _lived(monkeypatch, rows):
    from datetime import date

    monkeypatch.setattr(sd, "get_connection", lambda: FakeConn(rows))
    return sd._owner_lived_variable("ws-synthetic", 100_000, date(2026, 11, 4))


def test_living_costs_are_the_median_so_one_trip_does_not_set_them(monkeypatch):
    rows = [{"total": 300_000, "rows_seen": 40}, {"total": 900_000, "rows_seen": 40}, {"total": 400_000, "rows_seen": 40}]
    assert _lived(monkeypatch, rows) == 300_000


def test_months_without_real_activity_do_not_count_and_too_few_are_unknown(monkeypatch):
    rows = [{"total": 5_000, "rows_seen": 2}, {"total": 400_000, "rows_seen": 40}, {"total": 0, "rows_seen": 0}]
    assert _lived(monkeypatch, rows) is None
    rows = [{"total": 5_000, "rows_seen": 2}, {"total": 400_000, "rows_seen": 40}, {"total": 200_000, "rows_seen": 40}]
    assert _lived(monkeypatch, rows) == 200_000


def test_fixed_expenses_above_what_was_recorded_never_read_as_negative_spending(monkeypatch):
    rows = [{"total": 50_000, "rows_seen": 20}, {"total": 60_000, "rows_seen": 20}, {"total": 70_000, "rows_seen": 20}]
    assert _lived(monkeypatch, rows) == 0
