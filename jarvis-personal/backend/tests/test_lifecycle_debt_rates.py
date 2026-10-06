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
        monkeypatch.setattr(core, "calculate_financial_health_score", lambda: {
            "score": 70, "level": "stable", "inputs": {"debt_service_ratio": 0.1, "highest_debt_apr": 30}})

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
