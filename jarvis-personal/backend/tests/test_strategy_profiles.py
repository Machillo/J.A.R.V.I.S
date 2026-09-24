"""Synthetic financial profiles for the Users strategy engine (Basic + VIP).

Every profile is fictitious and reproducible. The battery checks priorities,
invariants (no negative or impossible amounts, allocations never exceed the
margin, cents rounding), threshold crossings, input-order independence and
that ES/EN only change wording. It also covers the approved P1 (beyond a
complete emergency fund) and P2 (optional excess-savings suggestion, APR >= 20 %)
rules. Any further rule change is a financial decision that needs human
approval (see docs/finance/strategy-profile-audit.md).
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
    known_target = se._money(snapshot.get("emergency_fund_target")) > 0
    if known_target and not any(se._money(d["remaining_amount"]) > 0 for d in snapshot["debts"]):
        gap = max(se._money(snapshot["emergency_fund_target"]) - se._money(snapshot["liquid_savings"]), 0)
        emergency = sum(a["amount"] for a in result["allocations"] if a["bucket"] == "emergency")
        assert emergency <= gap + TOLERANCE, "never allocate beyond the real emergency gap"
    for action in result["optional_actions"]:
        assert action["source"] == "excess_savings" and action["optional"] is True and action["executes"] is False
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
    "healthy_emergency_fund": ("healthy", "wealth_building"),  # P1: fund complete, no goals
    "good_saver": ("healthy", "goals"),                        # P1: fund complete, active goal
    "variable_income": ("healthy", "debt"),
    "low_income_high_essentials": ("critical", "stabilize"),
    "high_income_poor_liquidity": ("healthy", "debt"),
    "high_net_worth_illiquid": ("healthy", "debt"),
    "expensive_debt_with_savings": ("healthy", "debt"),
    "multiple_debts": ("healthy", "debt"),
    "goals_competing_with_debt": ("healthy", "debt"),
    "stable": ("healthy", "goals"),                            # P1
    "wealth_building_ready": ("healthy", "wealth_building"),   # P1
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
    # P1: Basic fills only the real 50k gap; the rest goes to wealth building (no goals).
    basic = se.build_basic_strategy(snapshot)
    assert [(a["bucket"], a["amount"]) for a in basic["allocations"]] == [("emergency", 50_000), ("wealth_building", 450_000)]
    assert basic["priority"] == "emergency", "the fund is still incomplete this month"
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
        return {k: v for k, v in result.items() if k not in {"recommendation", "warnings", "director_note", "optional_actions"}} | {
            "optional_actions": [{k: v for k, v in act.items() if k not in {"label", "explanation"}} for act in result.get("optional_actions", [])],
            "allocations": [(a["bucket"], a["amount"]) for a in result.get("allocations", [])],
            "vip_allocations": [(a["bucket"], a["amount"]) for a in result.get("vip_allocations", [])],
        }

    with use_language("es"):
        es = se.build_vip_strategy(snapshot)
    with use_language("en"):
        en = se.build_vip_strategy(snapshot)
    assert numbers(es) == numbers(en)


# --- P1: complete emergency fund without debt ---

def _no_debt(savings, target=1_800_000, goals=()):
    return profile(1_500_000, 600_000, savings, target, goals=list(goals))


GOAL = goal(1, 1_000_000, 200_000, "high", "2027-12-31")


def test_p1_incomplete_fund_without_debt_still_builds_the_fund():
    result = se.build_basic_strategy(_no_debt(1_000_000, goals=[GOAL]))
    assert result["priority"] == "emergency"
    assert result["allocations"][0] == {"bucket": "emergency", "label": result["allocations"][0]["label"], "amount": 800_000}
    assert [a["bucket"] for a in result["allocations"]] == ["emergency", "goal"], "the margin beyond the gap is not forced into the fund"


@pytest.mark.parametrize("savings", [1_800_000, 2_500_000], ids=["exactly_complete", "above_target"])
def test_p1_complete_fund_with_goals_moves_to_goals(savings):
    result = se.build_basic_strategy(_no_debt(savings, goals=[GOAL]))
    assert result["priority"] == "goals"
    assert all(a["bucket"] != "emergency" for a in result["allocations"])
    goal_line = next(a for a in result["allocations"] if a["bucket"] == "goal")
    assert goal_line == {"bucket": "goal", "label": goal_line["label"], "amount": 800_000, "goal_id": 1}, "capped at the goal's remaining gap"
    assert next(a for a in result["allocations"] if a["bucket"] == "wealth_building")["amount"] == 100_000


def test_p1_one_colon_short_is_still_incomplete():
    result = se.build_basic_strategy(_no_debt(1_799_999.99, goals=[GOAL]))
    assert result["priority"] == "emergency"
    assert next(a for a in result["allocations"] if a["bucket"] == "emergency")["amount"] == 0.01


def test_p1_complete_fund_without_goals_moves_to_wealth_building():
    result = se.build_basic_strategy(_no_debt(2_000_000))
    assert result["priority"] == "wealth_building"
    assert [(a["bucket"], a["amount"]) for a in result["allocations"]] == [("wealth_building", 900_000)]
    text = result["recommendation"].lower()
    for product in ("etf", "acción", "acciones", "cripto", "bono", "fondo de inversión", "rendimiento"):
        assert product not in text, "no specific products or returns"


def test_p1_completed_goals_do_not_count_as_pending():
    done = goal(2, 500_000, 500_000)
    assert se.build_basic_strategy(_no_debt(2_000_000, goals=[done]))["priority"] == "wealth_building"


def test_p1_complete_fund_with_active_debt_keeps_the_debt_logic():
    snapshot = {**_no_debt(2_000_000, goals=[GOAL]), "debts": [debt(1, 900_000, 80_000, 24)]}
    result = se.build_basic_strategy(snapshot)
    assert result["priority"] == "debt"
    assert result["target_debt"]["id"] == 1
    assert [a["bucket"] for a in result["allocations"]] == ["debt_extra"]


def test_p1_unknown_target_is_never_treated_as_complete():
    result = se.build_basic_strategy(_no_debt(5_000_000, target=None))
    assert result["priority"] == "emergency", "unknown is not zero"


@pytest.mark.parametrize("savings, goals, expected", [
    (1_000_000, [GOAL], "emergency"), (1_800_000, [GOAL], "goals"), (2_000_000, [], "wealth_building"),
])
def test_p1_basic_and_vip_agree(savings, goals, expected):
    snapshot = _no_debt(savings, goals=goals)
    vip = se.build_vip_strategy(snapshot)
    assert se.build_basic_strategy(snapshot)["priority"] == vip["priority"] == expected
    gap = max(1_800_000 - savings, 0)
    assert sum(a["amount"] for a in vip["vip_allocations"] if a["bucket"] == "emergency") <= gap
    assert_vip_invariants(snapshot, vip)


@pytest.mark.parametrize("savings, goals", [(1_000_000, [GOAL]), (1_800_000, [GOAL]), (2_000_000, [])])
def test_p1_language_never_changes_decisions_or_numbers(savings, goals):
    snapshot = _no_debt(savings, goals=goals)

    def decision():
        result = se.build_basic_strategy(snapshot)
        return result["priority"], [(a["bucket"], a["amount"], a.get("goal_id")) for a in result["allocations"]]

    with use_language("es"):
        es = decision()
    with use_language("en"):
        en = decision()
    assert es == en


def test_p1_starter_reserve_plus_fund_never_exceeds_the_gap():
    # Savings below 10% of income: the starter reserve and the fund line together fill exactly the gap.
    snapshot = profile(1_500_000, 600_000, 50_000, 400_000, goals=[GOAL])
    result = se.build_basic_strategy(snapshot)
    emergency = [a["amount"] for a in result["allocations"] if a["bucket"] == "emergency"]
    assert emergency == [100_000, 250_000] and sum(emergency) == 350_000
    assert next(a for a in result["allocations"] if a["bucket"] == "goal")["amount"] == 550_000


def test_p1_money_runs_out_across_several_goals_in_priority_order():
    goals = [goal(3, 300_000, 0, "low"), goal(1, 500_000, 0, "critical", "2027-01-31"), goal(2, 400_000, 100_000, "high")]
    result = se.build_basic_strategy(_no_debt(2_000_000, goals=goals))
    assert [(a["bucket"], a.get("goal_id"), a["amount"]) for a in result["allocations"]] == [
        ("goal", 1, 500_000), ("goal", 2, 300_000), ("goal", 3, 100_000)], "no wealth line until every goal is funded"


def test_p1_extra_monthly_simulation_follows_the_same_order():
    result = se.build_basic_strategy(_no_debt(1_000_000, goals=[GOAL]), extra_monthly=100_000)
    assert [(a["bucket"], a["amount"]) for a in result["allocations"]] == [("emergency", 800_000), ("goal", 200_000)]


@pytest.mark.parametrize("name", PROFILES)
def test_p1_goal_lines_are_capped_and_wealth_comes_last(name):
    snapshot = PROFILES[name]
    result = se.build_basic_strategy(snapshot)
    gaps = {g["id"]: g["target_amount"] - g["current_amount"] for g in snapshot["goals"]}
    for line in result["allocations"]:
        if line["bucket"] == "goal":
            assert line["amount"] <= gaps[line["goal_id"]] + TOLERANCE
    if any(a["bucket"] == "wealth_building" for a in result["allocations"]):
        funded = {a["goal_id"]: a["amount"] for a in result["allocations"] if a["bucket"] == "goal"}
        assert all(abs(funded.get(gid, 0) - gap) <= TOLERANCE for gid, gap in gaps.items() if gap > 0)


def test_p1_unknown_essentials_never_become_long_term_money():
    snapshot = {**_no_debt(2_000_000), "essential_monthly_expenses": None}
    result = se.build_basic_strategy(snapshot)
    assert result["priority"] == "complete_profile"
    assert all(a["bucket"] != "wealth_building" for a in result["allocations"])
    assert [a["bucket"] for a in result["allocations"]] == ["flex"]
    with_goal = se.build_basic_strategy({**snapshot, "goals": [GOAL]})
    assert with_goal["priority"] == "goals" and all(a["bucket"] != "wealth_building" for a in with_goal["allocations"])


def test_every_status_returns_optional_actions():
    for snapshot in (profile(0, 100, 0, 1_000), PROFILES["over_indebted"], PROFILES["no_debt"]):
        assert se.build_basic_strategy(snapshot)["optional_actions"] == []


# --- P2: excess savings vs. very expensive debt (optional recommendation) ---
# Approved v1 threshold: known nominal APR >= 20.0 % (inclusive), CRC and USD alike.
TEST_THRESHOLD = se.HIGH_COST_DEBT_APR_THRESHOLD
EXPENSIVE = debt(1, 1_000_000, 70_000, 52)


def _p2(savings, debts, target=1_800_000):
    return profile(1_400_000, 600_000, savings, target, list(debts))


def test_p2_uses_the_approved_20_percent_threshold():
    assert se.HIGH_COST_DEBT_APR_THRESHOLD == 20.0


@pytest.mark.parametrize("savings", [0, 1_000_000, 1_800_000])
def test_p2_never_touches_savings_at_or_below_the_target(savings):
    assert se.excess_savings_opportunity(_p2(savings, [EXPENSIVE]), TEST_THRESHOLD) is None


def test_p2_computes_the_excess_and_keeps_the_fund_complete():
    action = se.excess_savings_opportunity(_p2(2_300_000, [EXPENSIVE]), TEST_THRESHOLD)
    assert action["excess_savings"] == 500_000
    assert action["amount"] == 500_000, "capped at the excess when the debt is larger"
    assert action["savings_after"] == 1_800_000 >= action["emergency_fund_target"]


def test_p2_caps_at_the_debt_balance_when_the_excess_is_larger():
    action = se.excess_savings_opportunity(_p2(3_000_000, [EXPENSIVE]), TEST_THRESHOLD)
    assert action["excess_savings"] == 1_200_000
    assert action["amount"] == 1_000_000
    assert action["savings_after"] == 2_000_000


def test_p2_ignores_debts_with_unknown_or_lower_rates():
    debts = [debt(1, 900_000, 60_000, None), debt(2, 400_000, 30_000, 12)]
    assert se.excess_savings_opportunity(_p2(3_000_000, debts), TEST_THRESHOLD) is None


@pytest.mark.parametrize("rate, eligible", [(19.99, False), (20.0, True), (20.01, True)])
def test_p2_threshold_boundary_is_inclusive_at_20_percent(rate, eligible):
    snapshot = _p2(3_000_000, [debt(1, 500_000, 40_000, rate)])
    assert (se.excess_savings_opportunity(snapshot) is not None) is eligible
    assert bool(se.build_basic_strategy(snapshot)["optional_actions"]) is eligible, "production default, no override"


@pytest.mark.parametrize("rate", [None, 0])
def test_p2_debt_with_unknown_rate_is_never_eligible(rate):
    # The snapshot query turns a stored 0 into NULL (unknown); both must stay ineligible.
    snapshot = _p2(3_000_000, [debt(1, 500_000, 40_000, None if rate == 0 else rate, name="Tarjeta")])
    assert se.excess_savings_opportunity(snapshot) is None
    assert se.build_basic_strategy(snapshot)["optional_actions"] == []


def test_p2_picks_the_eligible_debt_deterministically_in_any_order():
    debts = [debt(3, 200_000, 20_000, 36, day=20), debt(1, 900_000, 60_000, None), debt(4, 300_000, 25_000, 48, day=25),
             debt(2, 250_000, 25_000, 48, day=10), debt(5, 100_000, 10_000, 12)]
    for order in itertools.permutations(debts):
        action = se.excess_savings_opportunity(_p2(2_300_000, list(order)), TEST_THRESHOLD)
        assert action["debt_id"] == 2, "highest known rate, then earliest due day"
        assert action["amount"] == 250_000


def test_p2_does_not_mutate_the_snapshot_or_monthly_allocations(monkeypatch):
    snapshot = _p2(2_300_000, [EXPENSIVE])
    before = repr(snapshot)
    without = se.build_basic_strategy(snapshot)
    monkeypatch.setattr(se, "HIGH_COST_DEBT_APR_THRESHOLD", TEST_THRESHOLD)
    with_rule = se.build_basic_strategy(snapshot)
    assert repr(snapshot) == before, "no side effects on the input"
    assert with_rule["allocations"] == without["allocations"], "the monthly plan is unchanged"
    assert with_rule["strategic_margin"] == without["strategic_margin"]
    [action] = with_rule["optional_actions"]
    assert (action["source"], action["optional"], action["executes"], action["type"]) == ("excess_savings", True, False, "one_time_extra_payment")
    assert all("source" not in a for a in with_rule["allocations"]), "clearly separate from the monthly margin"
    assert se.build_vip_strategy(snapshot)["optional_actions"] == with_rule["optional_actions"]


def test_p2_money_already_set_aside_for_goals_is_not_excess():
    goals = [goal(1, 900_000, 300_000), goal(2, 500_000, 100_000)]
    snapshot = {**_p2(2_300_000, [EXPENSIVE]), "goals": goals}
    action = se.excess_savings_opportunity(snapshot, TEST_THRESHOLD)
    assert action["reserved_for_goals"] == 400_000
    assert action["excess_savings"] == 100_000 and action["amount"] == 100_000
    assert se.excess_savings_opportunity({**snapshot, "liquid_savings": 2_200_000}, TEST_THRESHOLD) is None


def test_p2_is_not_offered_when_the_month_is_tight_or_critical(monkeypatch):
    monkeypatch.setattr(se, "HIGH_COST_DEBT_APR_THRESHOLD", TEST_THRESHOLD)
    tight = profile(670_000, 600_000, 3_000_000, 1_800_000, [EXPENSIVE])  # margin exactly 0
    critical = profile(600_000, 600_000, 3_000_000, 1_800_000, [EXPENSIVE])
    assert se.build_basic_strategy(tight)["status"] == "tight"
    assert se.build_basic_strategy(tight)["optional_actions"] == []
    assert se.build_basic_strategy(critical)["optional_actions"] == []


def test_p2_copy_warns_about_irreversibility_and_fees():
    text = se.excess_savings_opportunity(_p2(2_300_000, [EXPENSIVE]), TEST_THRESHOLD)["explanation"]
    assert "no se puede revertir" in text and "comisiones" in text and "DINCR no mueve dinero" in text
    assert "gastos próximos" in text and "confirmá que no necesitás ese excedente" in text


def test_p2_unknown_target_never_creates_an_excess():
    assert se.excess_savings_opportunity(_p2(9_000_000, [EXPENSIVE], target=None), TEST_THRESHOLD) is None


def test_p2_language_never_changes_the_amounts(monkeypatch):
    monkeypatch.setattr(se, "HIGH_COST_DEBT_APR_THRESHOLD", TEST_THRESHOLD)
    snapshot = _p2(2_300_000, [EXPENSIVE])
    with use_language("es"):
        es = se.build_basic_strategy(snapshot)["optional_actions"][0]
    with use_language("en"):
        en = se.build_basic_strategy(snapshot)["optional_actions"][0]
    strip = lambda a: {k: v for k, v in a.items() if k not in {"label", "explanation"}}
    assert strip(es) == strip(en)


def test_p2_is_active_for_expensive_debt_with_excess_savings_in_production():
    result = se.build_basic_strategy(PROFILES["expensive_debt_with_savings"])
    [action] = result["optional_actions"]
    assert (action["source"], action["debt_id"], action["amount"]) == ("excess_savings", 1, 1_000_000)
    assert action["savings_after"] == 2_000_000 >= 1_800_000
    vip = se.build_vip_strategy(PROFILES["expensive_debt_with_savings"])
    assert vip["optional_actions"] == result["optional_actions"]
    assert all(a["bucket"] != "excess_savings" and "source" not in a for a in vip["vip_allocations"])


@pytest.mark.parametrize("name", PROFILES)
def test_p2_never_changes_monthly_allocations_or_margin(name, monkeypatch):
    snapshot = PROFILES[name]
    active = se.build_basic_strategy(snapshot), se.build_vip_strategy(snapshot)
    monkeypatch.setattr(se, "HIGH_COST_DEBT_APR_THRESHOLD", None)
    disabled = se.build_basic_strategy(snapshot), se.build_vip_strategy(snapshot)
    strip = lambda r: {k: v for k, v in r.items() if k != "optional_actions"}
    assert strip(active[0]) == strip(disabled[0]) and strip(active[1]) == strip(disabled[1])
