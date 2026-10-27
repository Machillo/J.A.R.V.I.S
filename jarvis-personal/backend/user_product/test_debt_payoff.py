"""When each debt is expected to be paid off (debt_payoff), as the debts list returns it.

Read-only and deterministic: the months are the strategy engine's, the date counts from the next
installment still to pay. No estimate (None, never a date) for an unknown rate, no payment or a
payment that does not cover the interest. Owner and Users read the same list. Synthetic data only.
"""
from datetime import date
from types import SimpleNamespace

from backend.user_product import service
from backend.user_product.debt_payoff import payoff_estimate

TODAY = date(2026, 10, 24)


def _debt(**fields):
    return {"remaining_amount": 100_000, "monthly_payment": 10_000, "interest_rate": 0, "interest_rate_known": True,
            "debt_type": "loan", "payment_day": 5, "next_payment_date": None, **fields}


def test_a_zero_rate_debt_ends_after_its_remaining_installments():
    # 10 installments from the next payment day (5 Nov): the last one is 5 Aug 2027.
    assert payoff_estimate(_debt(), TODAY) == {"estimated_payoff_months": 10, "estimated_payoff_date": "2027-08-05"}


def test_interest_makes_it_longer_and_the_months_are_the_strategy_engines():
    estimate = payoff_estimate(_debt(interest_rate=24), TODAY)
    # 2 % a month: 11.27 payments of 10 000, so 12 installments.
    assert estimate["estimated_payoff_months"] == 12
    assert estimate["estimated_payoff_date"] == "2027-10-05"


def test_the_stored_next_payment_date_starts_the_count_when_it_has_not_passed():
    assert payoff_estimate(_debt(next_payment_date="2026-10-30"), TODAY)["estimated_payoff_date"] == "2027-07-30"
    # A date already past is not trusted: the next payment day from today is.
    assert payoff_estimate(_debt(next_payment_date="2026-10-05"), TODAY)["estimated_payoff_date"] == "2027-08-05"


def test_a_payment_day_later_this_month_counts_this_month_and_short_months_are_clamped():
    assert payoff_estimate(_debt(payment_day=30, remaining_amount=40_000), TODAY)["estimated_payoff_date"] == "2027-01-30"
    # Day 31 in a 30-day month falls on its last day; February on the 28th.
    assert payoff_estimate(_debt(payment_day=31, remaining_amount=40_000), date(2026, 11, 1))["estimated_payoff_date"] == "2027-02-28"


def test_unknown_is_never_estimated():
    assert payoff_estimate(_debt(interest_rate=None, interest_rate_known=False), TODAY)["estimated_payoff_date"] is None
    # An unconfirmed historical 0 on a loan is unknown (debt_rates), not 0%.
    assert payoff_estimate(_debt(interest_rate=0, interest_rate_known=None), TODAY)["estimated_payoff_months"] is None
    assert payoff_estimate(_debt(monthly_payment=0), TODAY)["estimated_payoff_months"] is None
    # A payment that does not cover the interest never ends.
    assert payoff_estimate(_debt(interest_rate=240, monthly_payment=1_000), TODAY) == {
        "estimated_payoff_months": None, "estimated_payoff_date": None}


def test_a_historical_rate_above_zero_and_zero_rate_financing_are_known():
    assert payoff_estimate(_debt(interest_rate=15, interest_rate_known=None), TODAY)["estimated_payoff_months"] == 11
    assert payoff_estimate(_debt(interest_rate=0, interest_rate_known=None, debt_type="tasa_cero"), TODAY)["estimated_payoff_months"] == 10


def test_a_paid_debt_has_nothing_left():
    assert payoff_estimate(_debt(remaining_amount=0), TODAY) == {"estimated_payoff_months": 0, "estimated_payoff_date": None}


class _ReadOnlyDb:
    def __init__(self, rows):
        self.rows, self.queries = rows, []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        self.queries.append(" ".join(query.split()))
        return SimpleNamespace(fetchall=lambda: self.rows)

    def commit(self):
        raise AssertionError("the debts list never writes")


def test_the_debts_list_carries_the_estimate_and_stays_read_only(monkeypatch):
    rows = [_debt(id=1, name="Préstamo de ejemplo", total_amount=200_000), _debt(id=2, name="Tarjeta de ejemplo", interest_rate=None, interest_rate_known=False)]
    db = _ReadOnlyDb(rows)
    monkeypatch.setattr(service, "get_current_workspace_id", lambda: "workspace-x")
    monkeypatch.setattr(service, "get_connection", lambda: db)
    monkeypatch.setattr(service, "costa_rica_today", lambda: TODAY)
    debts = service.list_user_debts()
    assert [(d["id"], d["estimated_payoff_months"], d["estimated_payoff_date"]) for d in debts] == [(1, 10, "2027-08-05"), (2, None, None)]
    assert debts[1]["interest_rate_known"] is False
    assert all(q.startswith("SELECT") for q in db.queries)
