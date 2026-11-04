"""The Owner's distribution as an analysis of his month. Synthetic data only, no database."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.ai import owner_analysis as oa
from backend.ai import strategy_dashboard as sd
from backend.ai.owner_distribution import debt_attack_targets

EXPENSIVE = {"id": 1, "name": "Tarjeta cara", "remaining_amount": 600_000, "interest_rate": 35, "monthly_payment": 30_000}
SMALL_ZERO = {"id": 2, "name": "Cuota chica", "remaining_amount": 50_000, "interest_rate": 0, "monthly_payment": 5_000}
BIG_CHEAP = {"id": 3, "name": "Préstamo grande", "remaining_amount": 3_000_000, "interest_rate": 9, "monthly_payment": 65_000}
DEBTS = [EXPENSIVE, SMALL_ZERO, BIG_CHEAP]


def month(income=500_000, lived=100_000, spent=0.0, yield_=None, necessary=None):
    return oa.OwnerMonth(income=income, installments=100_000, fixed_expenses=200_000, lived_variable=lived,
                         spent_this_cycle=spent, net_dividend_yield=yield_, lived_necessary=necessary)


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


def test_necessary_costs_still_to_come_go_first_above_his_free_money():
    assert amounts(decide(a_month=month(necessary=60_000, spent=20_000)))["life"] == 40_000
    assert amounts(decide(a_month=month(necessary=500_000)))["life"] == 100_000, "it never promises more than there is"
    assert amounts(decide(a_month=month(necessary=500_000)))["debt"] == 0


def test_his_free_money_is_always_kept():
    assert amounts(decide(a_month=month(necessary=60_000, spent=90_000)))["life"] == pytest.approx(15_000)
    assert amounts(decide(a_month=month(necessary=0)))["life"] == pytest.approx(15_000)


def test_choices_count_in_the_margin_but_are_not_reserved():
    decision = decide(a_month=month(income=500_000, lived=300_000, necessary=50_000))
    assert decision["analysis"]["margin"] == -100_000 and decision["analysis"]["order"] == "relief"
    assert amounts(decision)["life"] == 50_000, "the trips of other months are not set aside"


def test_unknown_living_costs_keep_the_old_share_and_say_so():
    decision = decide(a_month=month(lived=None))
    assert amounts(decision)["life"] == pytest.approx(15_000)
    assert decision["analysis"]["lived_variable_known"] is False and decision["analysis"]["lived_variable"] is None
    assert "todavía no se conocen" in decision["reason"]


def test_the_salvavidas_stays_on_course_and_the_rest_goes_to_debts():
    split = amounts(decide(a_month=month(lived=0), savings=60_000, base=300_000, mini=150_000))
    assert split["emergency"] == 15_000, "a sixth of what is missing for the mini fund"
    assert split["life"] == pytest.approx(15_000) and split["debt"] == pytest.approx(70_000) and split["investment"] == 0


def test_with_a_full_salvavidas_all_of_the_rest_attacks_debts():
    split = amounts(decide(a_month=month(lived=0), savings=1_000_000))
    assert split["emergency"] == 0 and split["debt"] == pytest.approx(85_000)


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
    assert decision["investment_allowed"] is True and amounts(decision)["investment"] == pytest.approx(85_000)


def test_without_debts_a_month_saved_builds_wealth_and_less_fills_the_salvavidas():
    assert amounts(decide(a_month=month(lived=0), debts=[], apr=0.0, savings=400_000))["investment"] == pytest.approx(85_000)
    split = amounts(decide(a_month=month(lived=0), debts=[], apr=0.0, savings=200_000))
    assert split["emergency"] == pytest.approx(85_000) and split["investment"] == 0


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
    his = sd._build_dynamic_director_allocation(**kwargs, owner_month=month(lived=40_000, necessary=40_000), salvavidas_target_months=1)
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
    def __init__(self, months):
        self.months = list(months)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params):
        assert "workspace_id=%s" in sql and params[0] == "ws-synthetic"
        return self

    def fetchall(self):
        return [{"category": category, "seen": seen, "total": total} for category, seen, total in self.months.pop(0)]


def _lived(monkeypatch, months, fixed=frozenset({"suscripciones"})):
    from datetime import date

    monkeypatch.setattr(sd, "get_connection", lambda: FakeConn(months))
    return sd._owner_lived_spending("ws-synthetic", set(fixed), date(2026, 11, 4))


FOOD, TRIP, SUBS = ("Comida", 20, 100_000), ("Viajes y turismo", 20, 150_000), ("Suscripciones", 20, 50_000)


def test_living_costs_are_the_median_so_one_trip_does_not_set_them(monkeypatch):
    months = [[FOOD], [FOOD, ("Viajes y turismo", 20, 900_000)], [("Comida", 20, 200_000), TRIP]]
    assert _lived(monkeypatch, months) == (350_000, 100_000)


def test_fixed_expenses_and_debts_are_left_out_by_category(monkeypatch):
    months = [[FOOD, SUBS, ("Vivienda", 1, 100_000)], [FOOD, SUBS, ("Vivienda", 1, 100_000)], [FOOD, SUBS]]
    assert _lived(monkeypatch, months, {"suscripciones", "vivienda"}) == (100_000, 100_000)


def test_a_fixed_expense_never_recorded_does_not_shrink_what_he_lived(monkeypatch):
    assert _lived(monkeypatch, [[FOOD, TRIP], [FOOD, TRIP], [FOOD, TRIP]]) == (250_000, 100_000)


def test_months_without_real_activity_do_not_count_and_too_few_are_unknown(monkeypatch):
    quiet = [("Comida", 2, 5_000)]
    assert _lived(monkeypatch, [quiet, [FOOD], []]) == (None, None)
    assert _lived(monkeypatch, [quiet, [FOOD], [("Comida", 20, 300_000)]]) == (200_000, 200_000)


def test_his_usual_month_reads_the_fixed_categories_the_living_expenses_return(monkeypatch):
    """The real shape of `_get_strategy_living_expenses`, so a renamed key can't silently count a fixed expense as lived."""
    from backend.ai import owner_debt_blocks

    seen = {}
    monkeypatch.setattr(owner_debt_blocks, "average_income", lambda *_a: (480_000.0, False))
    monkeypatch.setattr(sd, "get_preference", lambda *_a: {})
    monkeypatch.setattr(sd, "_owner_lived_spending", lambda _w, fixed, _t: seen.update(fixed=fixed) or (300_000.0, 80_000.0))
    source = Path(sd.__file__).read_text(encoding="utf-8")
    assert '"included_fixed": included' in source, "the key this test relies on"
    usual = sd._owner_usual_month("ws", 400_000.0, 100_000.0, {"fixed_living_total": 200_000, "included_fixed": [{"category": "Vivienda"}]}, 10_000.0)
    assert seen["fixed"] == {"vivienda"}
    assert (usual.income, usual.fixed_expenses, usual.lived_variable, usual.lived_necessary) == (480_000.0, 200_000, 300_000.0, 80_000.0)
