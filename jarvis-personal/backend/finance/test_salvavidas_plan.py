"""Salvavidas automatic contributions (VIP and Owner) and the Owner-only interest estimate.

Synthetic amounts only. The balance shown is the declared balance + the scheduled contributions
since it was declared (+ the Owner's estimated interest); reading never writes, and declaring a
new balance restarts the count so no contribution is added twice.
"""
from datetime import date

import pytest

from backend.finance import emergency_fund, salvavidas_plan as plan_math

WEEKLY = {"enabled": True, "amount": 2500, "frequency": "weekly", "start_date": "2026-11-05", "end_date": "2029-04-26"}


def plan(**changes):
    return plan_math.normalize_plan({**WEEKLY, **changes})


def test_weekly_contributions_count_every_scheduled_day_after_the_declaration():
    weekly = plan()
    assert plan_math.scheduled_dates(weekly, date(2026, 11, 4), date(2026, 11, 4)) == []
    assert plan_math.scheduled_dates(weekly, date(2026, 11, 4), date(2026, 11, 5)) == [date(2026, 11, 5)]
    # 5, 12, 19, 26 November: four Thursdays.
    progress = plan_math.progress(weekly, base_amount=0, base_date=date(2026, 11, 4), today=date(2026, 11, 30),
                                  annual_interest_rate=None)
    assert (progress["contributions_count"], progress["contributions_amount"], progress["total"]) == (4, 10000.0, 10000.0)
    assert progress["next_date"] == "2026-12-03"


def test_biweekly_and_monthly_schedules_and_the_end_date():
    assert len(plan_math.scheduled_dates(plan(frequency="biweekly"), date(2026, 11, 4), date(2026, 12, 31))) == 5
    monthly = plan(frequency="monthly", start_date="2027-01-31")
    assert plan_math.scheduled_dates(monthly, date(2027, 1, 1), date(2027, 4, 30)) == [
        date(2027, 1, 31), date(2027, 2, 28), date(2027, 3, 31), date(2027, 4, 30)]
    ended = plan(end_date="2026-11-12")
    assert len(plan_math.scheduled_dates(ended, date(2026, 11, 4), date(2027, 6, 1))) == 2


def test_a_new_declared_balance_restarts_the_count_so_nothing_is_added_twice():
    weekly = plan()
    before = plan_math.progress(weekly, base_amount=0, base_date=date(2026, 11, 4), today=date(2026, 11, 20),
                                annual_interest_rate=None)
    assert before["total"] == 7500.0  # 5, 12, 19
    # The user declares the real bank balance on the 20th: only later Thursdays add.
    after = plan_math.progress(weekly, base_amount=7600, base_date=date(2026, 11, 20), today=date(2026, 11, 27),
                               annual_interest_rate=None)
    assert (after["contributions_count"], after["total"]) == (1, 10100.0)


def test_the_interest_estimate_is_simple_daily_and_only_when_a_rate_is_given():
    weekly = plan()
    no_rate = plan_math.progress(weekly, base_amount=100000, base_date=date(2026, 11, 4), today=date(2027, 11, 4),
                                 annual_interest_rate=None)
    assert no_rate["estimated_interest"] == 0.0
    with_rate = plan_math.progress(plan(start_date="2028-01-01", end_date=None), base_amount=100000,
                                   base_date=date(2026, 11, 4), today=date(2027, 11, 4), annual_interest_rate=2.5)
    assert with_rate["estimated_interest"] == 2500.0  # 100,000 x 2.5 % for 365 days, no contributions


def test_a_disabled_or_incomplete_plan_adds_nothing():
    assert plan_math.progress(plan(enabled=False), base_amount=5, base_date=date(2026, 1, 1), today=date(2027, 1, 1),
                              annual_interest_rate=2.5) is None
    for broken in ({}, {"amount": 0}, {"frequency": "daily"}, {"start_date": "no"}):
        assert plan_math.normalize_plan({**WEEKLY, **broken}) is None if broken else plan_math.normalize_plan(broken) is None


@pytest.mark.parametrize("bad", [
    {**WEEKLY, "amount": 0}, {**WEEKLY, "amount": -1}, {**WEEKLY, "amount": "x"}, {**WEEKLY, "frequency": "daily"},
    {**WEEKLY, "start_date": None}, {**WEEKLY, "end_date": "2026-01-01"}, "weekly",
])
def test_an_invalid_plan_is_refused(bad):
    with pytest.raises(ValueError):
        plan_math.validated_plan(bad)


@pytest.mark.parametrize("rate", [-1, 50.01, "abc", None])
def test_an_invalid_interest_rate_is_refused(rate):
    with pytest.raises(ValueError):
        plan_math.validated_interest_rate(rate)


def _users_data(savings):
    return {"debts": [{"id": 1, "name": "Deuda", "monthly_payment": 10000, "remaining_amount": 50000}],
            "recurring": [], "liquid_savings": savings, "savings_source": "declared"}


def test_users_see_contributions_on_a_known_balance_and_never_interest(monkeypatch):
    monkeypatch.setattr(emergency_fund, "costa_rica_today", lambda: date(2026, 11, 30))
    config = {"auto_contribution": plan(), "base_date": "2026-11-04", "annual_interest_rate": 9.0}
    state = emergency_fund._users_salvavidas_from(_users_data(5000), 1, config)
    assert (state["declared_amount"], state["current_amount"]) == (5000, 15000.0)
    assert state["auto_contribution"]["estimated_interest"] == 0.0  # interest is Owner-only
    assert state["coverage_months"] == 1.5


def test_users_with_unknown_savings_stay_unknown_even_with_a_plan(monkeypatch):
    monkeypatch.setattr(emergency_fund, "costa_rica_today", lambda: date(2026, 11, 30))
    state = emergency_fund._users_salvavidas_from(_users_data(None), 1, {"auto_contribution": plan(), "base_date": "2026-11-04"})
    assert state["current_amount"] is None and state["auto_contribution"] is None


def _prefs(monkeypatch, stored):
    monkeypatch.setattr(emergency_fund, "get_preference", lambda _key, default=None: dict(stored))
    monkeypatch.setattr(emergency_fund, "set_preference", lambda _key, value: stored.update(value) or value)
    monkeypatch.setattr(emergency_fund, "get_salvavidas_state", lambda: {"saved": dict(stored)})
    monkeypatch.setattr(emergency_fund, "costa_rica_today", lambda: date(2026, 10, 29))
    monkeypatch.setattr(emergency_fund, "get_current_workspace_id", lambda: "workspace-a")
    monkeypatch.setattr(emergency_fund, "get_current_account_id", lambda: "account-a")


def test_a_user_cannot_set_the_interest_rate(monkeypatch):
    monkeypatch.setattr(emergency_fund, "_is_owner", lambda: False)
    with pytest.raises(ValueError):
        emergency_fund.update_salvavidas(annual_interest_rate=2.5)


def test_turning_the_plan_on_counts_from_today_and_needs_a_known_balance(monkeypatch):
    stored = {}
    _prefs(monkeypatch, stored)
    monkeypatch.setattr(emergency_fund, "_is_owner", lambda: False)
    monkeypatch.setattr(emergency_fund, "_load_users_obligations", lambda *_a: _users_data(None))
    with pytest.raises(ValueError):
        emergency_fund.update_salvavidas(auto_contribution=WEEKLY)
    monkeypatch.setattr(emergency_fund, "_load_users_obligations", lambda *_a: _users_data(0))
    emergency_fund.update_salvavidas(auto_contribution=WEEKLY)
    assert stored["auto_contribution"]["amount"] == 2500 and stored["base_date"] == "2026-10-29"


def test_the_owner_sets_the_rate_and_the_plan(monkeypatch):
    stored = {}
    _prefs(monkeypatch, stored)
    monkeypatch.setattr(emergency_fund, "_is_owner", lambda: True)
    rates = []
    monkeypatch.setattr(emergency_fund, "_set_owner_account_rate", rates.append)
    emergency_fund.update_salvavidas(auto_contribution=WEEKLY, annual_interest_rate=2.5)
    assert stored["annual_interest_rate"] == 2.5 and stored["auto_contribution"]["frequency"] == "weekly"
    assert rates == [2.5]


class _AccountConn:
    def __init__(self, row):
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def execute(self, query, params=()):
        assert "account_name)='salvavidas'" in " ".join(query.split()) and params == ("workspace-a",)
        return type("R", (), {"fetchone": lambda _self: self.row})()


def test_saving_the_owner_balance_keeps_the_accounts_bank_and_rate(monkeypatch):
    # Saving a balance used to rewrite the account as MultiMoney at 0 %, whatever the Owner set.
    monkeypatch.setattr(emergency_fund, "get_current_workspace_id", lambda: "workspace-a")
    monkeypatch.setattr(emergency_fund, "get_connection", lambda: _AccountConn({"bank_name": "BAC", "annual_interest_rate": 2.5}))
    assert emergency_fund._owner_account_terms({"annual_interest_rate": None}) == ("BAC", 2.5)
    assert emergency_fund._owner_account_terms({"annual_interest_rate": 3.0}) == ("BAC", 3.0)
    monkeypatch.setattr(emergency_fund, "get_connection", lambda: _AccountConn(None))
    assert emergency_fund._owner_account_terms({"annual_interest_rate": None}) == ("MultiMoney", 0.0)
