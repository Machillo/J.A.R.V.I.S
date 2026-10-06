"""The VIP lifecycle never reads an unknown debt interest rate as 0% (debts.interest_rate_known).

/user-product/vip/lifecycle/{state,monthly-review,proactive-advisor} all build their current state
with `financial_lifecycle.state.build_financial_state`, which asks the advisor for canonical rates
(`compute_advisor_strategy(canonical_rates=True)`). With an unknown rate the advisor names no
rate-based debt target, keeps goals and investing waiting instead of assuming cheap debt, and
reports the existing `debt_rates_missing` data issue; a known 0% stays 0%. The Owner's advisor and
its daily history keep the default (the raw stored rate). Inputs are the read-purity harness's
synthetic services; the debt strategies are the real engine over synthetic rows.
"""
from __future__ import annotations

import datetime as dt

import pytest

from backend.advisor import core
from backend.finance import daily_history, strategic_engine
from backend.financial_lifecycle import snapshots, state
from backend.tests import p02_parity_harness as harness

NOW = dt.datetime.now(dt.timezone.utc).isoformat()
ACCOUNTS = [{"account_name": "Cuenta sintética", "balance_crc": 2_000_000, "include_in_net_worth": True,
             "account_type": "checking", "balance_as_of": NOW, "source": "manual"}]
CARD = {"id": 1, "name": "Tarjeta sintética", "debt_type": "credit_card", "remaining_amount": 500_000,
        "monthly_payment": 30_000, "interest_rate": 30, "interest_rate_known": True}
# A loan whose 0 was never confirmed (the old "no rate given → 0"): unknown, never 0%.
LOAN = {"id": 2, "name": "Préstamo sintético", "debt_type": "loan", "remaining_amount": 900_000,
        "monthly_payment": 40_000, "interest_rate": 0, "interest_rate_known": None}
FLOW = {"status": "OK", "averages": {"income": 900_000, "net_operational": 200_000}}
UNKNOWN_ISSUE = "debt_rates_missing"
RATE_BLOCKER = "falta la tasa de interés de una deuda"


@pytest.fixture
def lifecycle(monkeypatch):
    """Install the synthetic services around the real debt strategies over `rows`."""

    def install(rows):
        public = [{k: v for k, v in row.items() if k != "interest_rate_known"} for row in rows]
        harness.install(monkeypatch, harness.new_store(), debts=public, accounts=ACCOUNTS)
        monkeypatch.setattr(strategic_engine, "_fetch_debts",
                            lambda rate_flag=False: [dict(row) if rate_flag else
                                                     {k: v for k, v in row.items() if k != "interest_rate_known"} for row in rows])
        monkeypatch.setattr(core, "calculate_debt_strategies", strategic_engine.calculate_debt_strategies)
        # One month of Salvavidas and a healthy score, so the debt-rate gates are the ones that decide.
        protected = {"coverage_months": 1.2, "monthly_base": 450_000, "current_amount": 540_000, "target_months": 6}
        for module in (core, state):
            monkeypatch.setattr(module, "get_salvavidas_state", lambda: dict(protected), raising=False)
        monkeypatch.setattr(core, "get_financial_deterioration", lambda: {"health": "stable", "primary_cause": None})
        # The real health score over synthetic flow and Salvavidas inputs.
        monkeypatch.setattr(strategic_engine, "get_monthly_financial_flow", lambda: dict(FLOW))
        monkeypatch.setattr(strategic_engine, "calculate_emergency_fund", lambda: {"current": 540_000, "monthly_base": 450_000})
        monkeypatch.setattr(core, "calculate_financial_health_score", strategic_engine.calculate_financial_health_score)

    return install


def _users():
    return core.compute_advisor_strategy(canonical_rates=True)


def _issues(strategy):
    return {issue["code"] for issue in strategy["data_quality"]["issues"]}


def test_an_unknown_rate_names_no_rate_based_debt_target(lifecycle):
    lifecycle([CARD, LOAN])
    strategy = _users()
    assert strategy["debt_target"] is None  # the 30% card is not "first" next to an unknown rate
    assert not any(action["type"] == "debt" for action in strategy["action_plan"])
    assert UNKNOWN_ISSUE in _issues(strategy)


def test_goals_and_investing_never_assume_an_unknown_rate_is_cheap(lifecycle):
    lifecycle([CARD, LOAN])
    strategy = _users()
    assert {item["blocked_by"] for item in strategy["goal_portfolio"]["items"]} == {RATE_BLOCKER}
    assert strategy["goal_portfolio"]["active_goal"] is None
    assert RATE_BLOCKER in strategy["investment"]["blockers"] and not strategy["investment"]["prudent"]


def test_a_known_zero_percent_is_still_zero(lifecycle):
    lifecycle([CARD, {**LOAN, "interest_rate_known": True}])
    strategy = _users()
    assert UNKNOWN_ISSUE not in _issues(strategy)  # a confirmed 0% is not a missing rate
    assert strategy["debt_target"]["id"] == 1  # 30% before a real 0%
    assert RATE_BLOCKER not in strategy["investment"]["blockers"]


def test_known_rates_keep_the_previous_behaviour(lifecycle):
    lifecycle([CARD, {**LOAN, "interest_rate": 12}])
    assert harness.without_volatile(_users()) == harness.without_volatile(core.compute_advisor_strategy())


def test_the_owner_advisor_keeps_the_stored_rate(lifecycle):
    lifecycle([CARD, LOAN])
    owner = core.compute_advisor_strategy()
    assert owner["debt_target"]["id"] == 1  # as before: the raw 0 ranks the loan last
    assert {item["blocked_by"] for item in owner["goal_portfolio"]["items"]} != {RATE_BLOCKER}
    assert RATE_BLOCKER not in owner["investment"]["blockers"]


@pytest.mark.parametrize("read", ["state", "monthly_review", "proactive_advisor"])
def test_every_lifecycle_read_uses_the_canonical_rates(lifecycle, monkeypatch, read):
    lifecycle([CARD, LOAN])

    class NoSnapshots:
        def execute(self, *_a):
            return type("R", (), {"fetchall": lambda self: [], "fetchone": lambda self: None})()

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(snapshots, "get_connection", NoSnapshots)
    monkeypatch.setattr(snapshots, "get_current_workspace_id", lambda: harness.WORKSPACE)
    calls, states = [], []
    advisor, build = core.compute_advisor_strategy, state.build_financial_state
    monkeypatch.setattr(state, "compute_advisor_strategy", lambda **kw: calls.append(kw) or advisor(**kw))
    monkeypatch.setattr(snapshots, "build_financial_state", lambda: states.append(build()) or states[-1])
    {"state": lambda: states.append(state.build_financial_state()),
     "monthly_review": lambda: snapshots.get_monthly_review(dt.date.today().strftime("%Y-%m")),
     "proactive_advisor": snapshots.get_proactive_advisor}[read]()
    assert calls and all(kw == {"canonical_rates": True} for kw in calls)
    assert states and all(current["debt"]["target"] is None for current in states)  # no target from an unknown rate
    assert all(current["health"]["data_status"] == "review" for current in states)
    assert all(current["strategy"]["next_action"]["type"] != "debt" for current in states)


def test_the_owner_daily_history_keeps_the_default_advisor(monkeypatch):
    calls = []
    monkeypatch.setattr(daily_history, "record_daily_health_snapshot", lambda today: {"health": "OK"})
    monkeypatch.setattr(daily_history, "compute_advisor_strategy", lambda **kw: calls.append(kw) or {})
    monkeypatch.setattr(daily_history, "_persist_strategy", lambda strategy: {"changed": False, "persisted": False})
    owner = {"id": 1, "account_id": "a", "workspace_id": harness.WORKSPACE, "role": "owner", "status": "active"}
    daily_history._record_workspace(owner, dt.date(2026, 10, 6))
    assert calls == [{}]  # the Owner's stored strategy history keeps the raw rate
    user = {**owner, "role": "user"}
    daily_history._record_workspace(user, dt.date(2026, 10, 6))
    assert calls == [{}]  # a VIP's daily history stores no strategy at all (health only)


# Health score ------------------------------------------------------------------------------------

@pytest.fixture
def health(monkeypatch):
    def install(rows):
        monkeypatch.setattr(strategic_engine, "get_monthly_financial_flow", lambda: dict(FLOW))
        monkeypatch.setattr(strategic_engine, "calculate_emergency_fund", lambda: {"current": 540_000, "monthly_base": 450_000})
        monkeypatch.setattr(strategic_engine, "_fetch_debts",
                            lambda rate_flag=False: [dict(row) if rate_flag else
                                                     {k: v for k, v in row.items() if k != "interest_rate_known"} for row in rows])
    return install


def test_a_known_rate_keeps_the_health_score(health):
    health([CARD, {**LOAN, "interest_rate": 12}])
    assert strategic_engine.calculate_financial_health_score(canonical_rates=True) == strategic_engine.calculate_financial_health_score()


def test_a_known_zero_percent_is_a_valid_debt_cost(health):
    health([{**CARD, "interest_rate": 0}, {**LOAN, "interest_rate_known": True}])
    score = strategic_engine.calculate_financial_health_score(canonical_rates=True)
    assert score["status"] == "OK" and score["components"]["debt_cost"] == 15.0 and score["score"] is not None


def test_an_unknown_rate_leaves_debt_cost_and_the_score_unknown_without_rescaling(health):
    health([CARD, LOAN])
    unknown = strategic_engine.calculate_financial_health_score(canonical_rates=True)
    assert unknown["components"]["debt_cost"] is None  # not 0 points, not 15
    assert unknown["score"] is None and unknown["level"] is None and unknown["status"] == "INCOMPLETE"
    assert unknown["missing"] == ["debt_interest_rates"] and "falta la tasa de interés" in unknown["explanation"].lower()
    assert unknown["inputs"]["highest_debt_apr"] is None
    known = strategic_engine.calculate_financial_health_score()  # the raw reading of the same rows
    # The known components keep their weights and values: nothing is rescaled to /100.
    assert {k: v for k, v in unknown["components"].items() if k != "debt_cost"} == \
           {k: v for k, v in known["components"].items() if k != "debt_cost"}


def test_a_paid_off_debt_without_a_rate_does_not_block_the_score(health):
    health([CARD, {**LOAN, "remaining_amount": 0}])
    assert strategic_engine.calculate_financial_health_score(canonical_rates=True)["score"] is not None


def test_the_owner_health_score_keeps_the_stored_rate(health):
    health([CARD, LOAN])
    owner = strategic_engine.calculate_financial_health_score()
    assert owner["status"] == "OK" and owner["score"] is not None and "missing" not in owner
    assert owner["inputs"]["highest_debt_apr"] == 30.0  # the unconfirmed 0 still reads as 0 for the Owner


def test_the_lifecycle_state_never_shows_an_incomplete_score_as_a_number(lifecycle):
    lifecycle([CARD, LOAN])
    current = state.build_financial_state()
    assert current["health"]["score"] is None and current["health"]["label"] is None
    assert current["health"]["missing"] == ["debt_interest_rates"]
    lifecycle([CARD, {**LOAN, "interest_rate_known": True}])
    complete = state.build_financial_state()
    assert isinstance(complete["health"]["score"], float) and "missing" not in complete["health"]


def _observed(score, missing=()):
    return {"health": {"score": score, **({"missing": list(missing)} if missing else {})},
            "strategy": {"next_action": {"type": "hold"}}}


def test_an_unknown_score_is_never_compared(lifecycle):
    from backend.financial_lifecycle.progress import compare_states
    for current, baseline in ((None, 70), (70, None)):
        metric = compare_states(_observed(current), _observed(baseline))["metrics"]["health_score"]
        assert metric["delta"] is None and metric["trend"] == "unknown"
    comparison = compare_states(_observed(60), _observed(70))
    assert comparison["metrics"]["health_score"]["trend"] == "declined"  # known scores still compare
    assert comparison["summary"]["declined"] == 1


def test_the_proactive_advisor_makes_no_score_drop_or_rise_from_an_unknown(lifecycle):
    from backend.financial_lifecycle.proactive import build_proactive_advisor
    today = dt.date(2026, 10, 6)
    went_unknown = build_proactive_advisor(current=_observed(None, ["debt_interest_rates"]), previous=_observed(70),
                                           baseline_date="2026-10-05", as_of=today)
    codes = {alert["code"]: alert for alert in went_unknown["alerts"]}
    assert "health_score_drop" not in codes  # 70 → unknown is not a drop
    assert codes["health_score_incomplete"]["action"]["route"] == "debts"
    assert "falta la tasa de interés" in codes["health_score_incomplete"]["title"].lower()
    back = build_proactive_advisor(current=_observed(55), previous=_observed(None, ["debt_interest_rates"]),
                                   baseline_date="2026-10-05", as_of=today)
    assert back["alerts"] == []  # unknown → 55 is neither a drop nor a rise
    known = build_proactive_advisor(current=_observed(60), previous=_observed(70), baseline_date="2026-10-05", as_of=today)
    assert [alert["code"] for alert in known["alerts"]] == ["health_score_drop"]  # known comparisons still alert


def test_the_monthly_review_explains_an_incomplete_score(lifecycle):
    from backend.financial_lifecycle.monthly_review import build_monthly_review
    observations = [{"snapshot_date": "2026-10-01", "state": _observed(70)}, {"snapshot_date": "2026-10-05", "state": _observed(70)}]
    review = build_monthly_review(period="2026-10", closing_state=_observed(None, ["debt_interest_rates"]), observations=observations)
    line = next(item for item in review["scorecard"] if item["key"] == "health_score")
    assert line["current"] is None and line["trend"] == "unknown" and "falta la tasa de interés" in line["explanation"].lower()
    assert all(item["key"] != "health_score" for item in review["wins"] + review["deviations"])
