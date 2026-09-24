"""Synthetic financial profiles for the Users strategy engine (Basic + VIP).

Every profile is fictitious and reproducible. The battery checks priorities,
invariants (no negative or impossible amounts, allocations never exceed the
margin, cents rounding), threshold crossings, input-order independence and
that ES/EN only change wording. Rules that look improvable are documented as
strict xfail proposals: changing them is a financial decision that needs
human approval (see docs/finance/strategy-profile-audit.md).
"""
from __future__ import annotations

import itertools
import random
from datetime import date

import pytest

from backend.core.i18n import use_language
from backend.user_product import strategy_engine as se
from backend.user_product.service import _monthly_income_estimate


def debt(id_, remaining, payment, rate=None, day=15, name=None):
    return {"id": id_, "name": name or f"Deuda {id_}", "remaining_amount": remaining,
            "monthly_payment": payment, "interest_rate": rate, "payment_day": day}


def goal(id_, target, current=0, priority="medium", target_date=None):
    return {"id": id_, "name": f"Meta {id_}", "target_amount": target, "current_amount": current,
            "priority": priority, "target_date": target_date}


def profile(income, essentials, savings=0, emergency_target=None, debts=(), goals=(),
            preference="balanced", discretionary=0, pay_frequency="monthly"):
    return {
        "monthly_income_estimate": income, "essential_monthly_expenses": essentials,
        "liquid_savings": savings, "emergency_fund_target": emergency_target,
        "strategy_preference": preference, "discretionary_monthly_minimum": discretionary,
        "pay_frequency": pay_frequency, "debts": list(debts), "goals": list(goals),
    }


# Amounts in CRC. Essentials of 600k => a 3-month emergency target of 1.8M.
PROFILES = {
    "over_indebted": profile(900_000, 600_000, 50_000, 1_800_000, [
        debt(1, 3_500_000, 220_000, 42), debt(2, 1_200_000, 150_000, 36), debt(3, 800_000, 90_000)]),
    "manageable_debt": profile(1_500_000, 600_000, 900_000, 1_800_000, [debt(1, 2_000_000, 120_000, 18)]),
    "no_debt": profile(1_200_000, 600_000, 400_000, 1_800_000),
    "no_emergency_fund": profile(1_100_000, 600_000, 0, 1_800_000, [debt(1, 900_000, 80_000, 24)]),
    "partial_emergency_fund": profile(1_100_000, 600_000, 900_000, 1_800_000),
    "healthy_emergency_fund": profile(1_300_000, 600_000, 2_000_000, 1_800_000),
    "good_saver": profile(2_000_000, 700_000, 3_000_000, 2_100_000, goals=[goal(1, 5_000_000, 1_000_000, "high")]),
    "variable_income": profile(_monthly_income_estimate({"income_type": "hourly", "hourly_rate": 3_500, "hours_per_day": 6, "work_days_per_week": 5}),
                               400_000, 100_000, 1_200_000, [debt(1, 500_000, 45_000, 30)]),
    "low_income_high_essentials": profile(450_000, 430_000, 20_000, 1_290_000, [debt(1, 300_000, 35_000, 48)]),
    "high_income_poor_liquidity": profile(4_000_000, 1_500_000, 150_000, 4_500_000, [debt(1, 25_000_000, 450_000, 9)]),
    "high_net_worth_illiquid": profile(1_800_000, 900_000, 60_000, 2_700_000, [debt(1, 40_000_000, 600_000, 8)]),
    "expensive_debt_with_savings": profile(1_400_000, 600_000, 3_000_000, 1_800_000, [debt(1, 1_000_000, 70_000, 52)]),
    "multiple_debts": profile(1_600_000, 650_000, 300_000, 1_950_000, [
        debt(1, 400_000, 40_000, 22, day=5), debt(2, 1_500_000, 110_000, 38, day=20),
        debt(3, 250_000, 30_000, None, day=10), debt(4, 2_000_000, 95_000, 38, day=12)]),
    "goals_competing_with_debt": profile(1_700_000, 700_000, 500_000, 2_100_000, [debt(1, 1_200_000, 90_000, 30)],
                                        goals=[goal(1, 1_000_000, 0, "critical", "2027-06-30"), goal(2, 800_000, 100_000, "low")],
                                        preference="goals", discretionary=50_000),
    "stable": profile(1_500_000, 650_000, 2_000_000, 1_950_000, goals=[goal(1, 3_000_000, 500_000)]),
    "wealth_building_ready": profile(3_000_000, 900_000, 6_000_000, 2_700_000, preference="balanced", discretionary=150_000),
}

TOLERANCE = 0.02  # rounding each bucket to cents may drift by a cent or two


def _amounts(allocations):
    return [a["amount"] for a in allocations]


def assert_basic_invariants(snapshot, result, extra=0):
    assert result["status"] in {"needs_income", "critical", "healthy", "tight"}
    for amount in _amounts(result["allocations"]):
        assert amount > 0 and round(amount, 2) == amount, "no zero/negative/sub-cent allocations"
    if result["status"] in {"needs_income", "critical"}:
        assert result["allocations"] == [] and result["projection"] is None
        return
    assert result["strategic_margin"] >= 0
    total = sum(_amounts(result["allocations"]))
    assert total <= result["strategic_margin"] + se._money(extra) + TOLERANCE, "never allocate money the user doesn't have"
    target = result["target_debt"]
    if target:
        assert target["remaining_amount"] > 0
        projection = result["projection"]
        if projection and projection["months"] is not None and projection["baseline_months"] is not None:
            assert projection["months"] <= projection["baseline_months"], "extra payments never slow a payoff"


def assert_vip_invariants(snapshot, result):
    if result["status"] in {"needs_income", "critical"}:
        assert result["vip_allocations"] == result["allocations"] == []
        return
    amounts = _amounts(result["vip_allocations"])
    assert all(a >= 0 and round(a, 2) == a for a in amounts)
    assert sum(amounts) <= result["strategic_margin"] + TOLERANCE
    if result["strategic_margin"] > 0:
        assert sum(amounts) >= result["strategic_margin"] - TOLERANCE, "VIP assigns the whole margin, including flex"
    buckets = [a["bucket"] for a in result["vip_allocations"]]
    assert len(buckets) == len(set(buckets)), "one line per bucket"
    for line in result["vip_allocations"]:
        if line["bucket"] == "debt_extra":
            assert any(d["id"] == line["debt_id"] and se._money(d["remaining_amount"]) > 0 for d in snapshot["debts"])
    emergency = next((a for a in result["vip_allocations"] if a["bucket"] == "emergency"), None)
    if emergency:
        gap = se._money(snapshot["emergency_fund_target"]) - se._money(snapshot["liquid_savings"])
        assert emergency["amount"] <= gap + TOLERANCE, "never overfund the emergency target"


def assert_paycheck_invariants(plan):
    assert plan["unassigned"] >= 0
    assert all(e["amount"] > 0 for e in plan["envelopes"])


@pytest.mark.parametrize("name", PROFILES)
def test_every_profile_respects_invariants(name):
    snapshot = PROFILES[name]
    basic = se.build_basic_strategy(snapshot)
    assert_basic_invariants(snapshot, basic)
    vip = se.build_vip_strategy(snapshot)
    assert_vip_invariants(snapshot, vip)
    insights = se.build_vip_insights(snapshot, vip)
    assert insights["total_debt"] == round(sum(d["remaining_amount"] for d in snapshot["debts"]), 2)
    if basic["status"] not in {"critical", "needs_income"}:
        assert_paycheck_invariants(se.build_paycheck_plan(basic, snapshot["pay_frequency"]))
        assert_paycheck_invariants(se.build_paycheck_plan(vip, snapshot["pay_frequency"], vip=True))


EXPECTED_PRIORITY = {
    "over_indebted": ("critical", "stabilize"),
    "manageable_debt": ("healthy", "debt"),
    "no_debt": ("healthy", "emergency"),
    "no_emergency_fund": ("healthy", "debt"),
    "partial_emergency_fund": ("healthy", "emergency"),
    "healthy_emergency_fund": ("healthy", "emergency"),
    "good_saver": ("healthy", "emergency"),
    "variable_income": ("healthy", "debt"),
    "low_income_high_essentials": ("critical", "stabilize"),
    "high_income_poor_liquidity": ("healthy", "debt"),
    "high_net_worth_illiquid": ("healthy", "debt"),
    "expensive_debt_with_savings": ("healthy", "debt"),
    "multiple_debts": ("healthy", "debt"),
    "goals_competing_with_debt": ("healthy", "debt"),
    "stable": ("healthy", "emergency"),
    "wealth_building_ready": ("healthy", "emergency"),
}


@pytest.mark.parametrize("name", PROFILES)
def test_profile_priorities_are_pinned(name):
    """Characterization: a change here is a change in financial advice and needs review."""
    result = se.build_basic_strategy(PROFILES[name])
    assert (result["status"], result["priority"]) == EXPECTED_PRIORITY[name]


def test_over_indebted_gets_no_extra_payments_and_the_real_deficit():
    result = se.build_basic_strategy(PROFILES["over_indebted"])
    assert result["strategic_margin"] == 900_000 - 600_000 - 460_000
    assert result["allocations"] == []
    vip = se.build_vip_strategy(PROFILES["over_indebted"])
    assert vip["vip_allocations"] == [] and vip["director_mode"] is True


def test_low_income_with_high_essentials_never_gets_impossible_advice():
    result = se.build_basic_strategy(PROFILES["low_income_high_essentials"])
    assert result["status"] == "critical"
    assert result["allocations"] == []
    insights = se.build_vip_insights(PROFILES["low_income_high_essentials"])
    assert "negative_margin" in {a["code"] for a in insights["alerts"]}


def test_multiple_debts_target_highest_known_rate_then_earliest_due_date():
    result = se.build_basic_strategy(PROFILES["multiple_debts"])
    # Debts 2 and 4 share 38% APR; debt 4 is due earlier (day 12 < 20).
    assert result["target_debt"]["id"] == 4
    assert "apr_missing" in {a["code"] for a in se.build_vip_insights(PROFILES["multiple_debts"])["alerts"]}


def test_basic_reserve_is_capped_while_debt_exists():
    result = se.build_basic_strategy(PROFILES["no_emergency_fund"])
    reserve = next(a["amount"] for a in result["allocations"] if a["bucket"] == "emergency")
    extra = next(a["amount"] for a in result["allocations"] if a["bucket"] == "debt_extra")
    assert reserve == pytest.approx(min(result["strategic_margin"] * 0.20, 1_100_000 * 0.10), abs=0.01)
    assert reserve + extra == pytest.approx(result["strategic_margin"], abs=0.01)


def test_vip_goal_preference_ranks_critical_dated_goal_first():
    result = se.build_vip_strategy(PROFILES["goals_competing_with_debt"])
    goal_line = next(a for a in result["vip_allocations"] if a["bucket"] == "goal")
    assert goal_line["goal_id"] == 1
    personal = next(a for a in result["vip_allocations"] if a["bucket"] == "personal")
    assert personal["amount"] == 50_000


@pytest.mark.parametrize("preference", ["debt", "emergency", "goals", "balanced"])
def test_every_vip_preference_assigns_the_whole_margin(preference):
    snapshot = {**PROFILES["goals_competing_with_debt"], "strategy_preference": preference}
    assert_vip_invariants(snapshot, se.build_vip_strategy(snapshot))


def test_strategy_changes_exactly_when_the_margin_crosses_zero():
    base = profile(1_000_000, 600_000, 0, 1_800_000, [debt(1, 1_000_000, 400_000, 20)])
    assert se.build_basic_strategy(base)["status"] == "tight"
    assert se.build_basic_strategy({**base, "monthly_income_estimate": 999_999.99})["status"] == "critical"
    healthy = se.build_basic_strategy({**base, "monthly_income_estimate": 1_000_000.01})
    assert healthy["status"] == "healthy" and healthy["strategic_margin"] == 0.01


def test_emergency_allocation_near_the_target():
    snapshot = profile(1_000_000, 500_000, 1_450_000, 1_500_000)
    # Basic without debt sends the whole margin to "savings / emergency", even past the target (proposal P1).
    basic = se.build_basic_strategy(snapshot)
    assert [(a["bucket"], a["amount"]) for a in basic["allocations"]] == [("emergency", 500_000)]
    # VIP caps the emergency line at the remaining gap and leaves the rest flexible.
    vip = se.build_vip_strategy(snapshot)
    assert next(a["amount"] for a in vip["vip_allocations"] if a["bucket"] == "emergency") == 50_000
    assert_vip_invariants(snapshot, vip)


def test_missing_data_is_warned_never_invented():
    snapshot = profile(900_000, None, 0, None, [debt(1, 500_000, None, None)])
    result = se.build_basic_strategy(snapshot)
    assert len(result["warnings"]) == 3
    assert result["minimum_debt_payments"] == 0
    assert se.build_vip_insights(snapshot)["emergency_months"] is None


def test_zero_income_needs_income_everywhere():
    snapshot = profile(0, 300_000, 100_000, 900_000, [debt(1, 100_000, 10_000, 20)])
    assert se.build_basic_strategy(snapshot)["status"] == "needs_income"
    assert se.build_vip_strategy(snapshot)["vip_allocations"] == []
    assert "income_missing" in {a["code"] for a in se.build_vip_insights(snapshot)["alerts"]}


def test_payment_below_interest_never_projects_a_payoff():
    assert se._months_to_payoff(1_000_000, 10_000, 24) is None  # 2%/month interest = 20k > 10k
    assert se._months_to_payoff(1_000_000, 0, 24) is None
    assert se._months_to_payoff(0, 10_000, 24) == 0
    assert se._months_to_payoff(120_000, 10_000, None) == 12


def test_hourly_income_estimate_uses_52_weeks_over_12_months():
    assert _monthly_income_estimate({"income_type": "hourly", "hourly_rate": 3_500, "hours_per_day": 6, "work_days_per_week": 5}) == round(3_500 * 6 * 5 * 52 / 12, 2)
    assert _monthly_income_estimate({"income_type": "fixed", "fixed_monthly_salary": "750000.456"}) == 750_000.46
    assert _monthly_income_estimate(None) == 0


@pytest.mark.parametrize("name", ["multiple_debts", "goals_competing_with_debt", "over_indebted"])
def test_input_order_never_changes_the_strategy(name):
    snapshot = PROFILES[name]
    expected_basic = se.build_basic_strategy(snapshot)
    expected_vip = se.build_vip_strategy(snapshot)
    rng = random.Random(7)
    for _ in range(6):
        shuffled = {**snapshot, "debts": rng.sample(snapshot["debts"], len(snapshot["debts"])),
                    "goals": rng.sample(snapshot["goals"], len(snapshot["goals"]))}
        assert se.build_basic_strategy(shuffled) == expected_basic
        assert se.build_vip_strategy(shuffled)["vip_allocations"] == expected_vip["vip_allocations"]


def test_exact_ties_are_broken_by_the_oldest_record_whatever_the_order():
    twins = [debt(7, 500_000, 50_000, 30, day=10), debt(3, 500_000, 50_000, 30, day=10)]
    for order in itertools.permutations(twins):
        snapshot = profile(1_200_000, 500_000, 1_000_000, 1_500_000, list(order))
        assert se.build_basic_strategy(snapshot)["target_debt"]["id"] == 3
        assert se.build_vip_strategy(snapshot)["target_debt"]["id"] == 3


def test_vip_ignores_paid_off_debts():
    snapshot = profile(1_200_000, 500_000, 1_500_000, 1_500_000, [debt(1, 0, 90_000, 60), debt(2, 400_000, 40_000, 20)])
    vip = se.build_vip_strategy(snapshot)
    debt_line = next(a for a in vip["vip_allocations"] if a["bucket"] == "debt_extra")
    assert debt_line["debt_id"] == 2


def test_scenario_is_pure_and_moves_the_margin_by_the_inputs():
    snapshot = PROFILES["manageable_debt"]
    before = repr(snapshot)
    scenario = se.build_vip_scenario(snapshot, monthly_income_change=100_000, monthly_expense_change=30_000, one_time_extra=-5)
    assert repr(snapshot) == before, "simulation never mutates the real snapshot"
    assert scenario["delta"]["strategic_margin"] == 70_000
    assert scenario["inputs"]["one_time_extra"] == 0, "negative windfalls are clamped"


@pytest.mark.parametrize("frequency, periods", [("weekly", 52 / 12), ("biweekly", 26 / 12), ("monthly", 1), (None, 1)])
def test_paycheck_plan_splits_the_month_by_pay_frequency(frequency, periods):
    strategy = se.build_basic_strategy(PROFILES["manageable_debt"])
    plan = se.build_paycheck_plan(strategy, frequency)
    assert plan["estimated_paycheck"] == round(1_500_000 / periods, 2)
    assert sum(e["amount"] for e in plan["envelopes"]) + plan["unassigned"] == pytest.approx(plan["estimated_paycheck"], abs=0.05)


def test_goal_monthly_need_counts_whole_months_and_never_divides_by_zero():
    ref = date(2026, 9, 24)
    assert se._goal_monthly_need(goal(1, 1_200_000, 0, target_date="2027-09-30"), ref) == 100_000
    assert se._goal_monthly_need(goal(1, 1_200_000, 0, target_date="2026-09-30"), ref) == 1_200_000
    assert se._goal_monthly_need(goal(1, 1_200_000, 0, target_date="not-a-date"), ref) is None


@pytest.mark.parametrize("name", PROFILES)
def test_language_changes_wording_never_numbers(name):
    snapshot = PROFILES[name]

    def numbers(result):
        return {k: v for k, v in result.items() if k not in {"recommendation", "warnings", "director_note"}} | {
            "allocations": [(a["bucket"], a["amount"]) for a in result.get("allocations", [])],
            "vip_allocations": [(a["bucket"], a["amount"]) for a in result.get("vip_allocations", [])],
        }

    with use_language("es"):
        es = se.build_vip_strategy(snapshot)
    with use_language("en"):
        en = se.build_vip_strategy(snapshot)
    assert numbers(es) == numbers(en)


# --- Proposals that need human approval (strict xfail documents the gap) ---

@pytest.mark.xfail(strict=True, reason="P1 (HUMAN GATE): with no debt and a full emergency fund, Basic still says to strengthen the emergency fund")
def test_p1_full_emergency_fund_without_debt_moves_beyond_emergency():
    result = se.build_basic_strategy(PROFILES["wealth_building_ready"])
    assert result["priority"] != "emergency"


@pytest.mark.xfail(strict=True, reason="P2 (HUMAN GATE): savings far above the emergency target are never suggested against very expensive debt")
def test_p2_excess_savings_are_considered_for_expensive_debt():
    result = se.build_basic_strategy(PROFILES["expensive_debt_with_savings"])
    assert any(a.get("source") == "excess_savings" for a in result["allocations"])
