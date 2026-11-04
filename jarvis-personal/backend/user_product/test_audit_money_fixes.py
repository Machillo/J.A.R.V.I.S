"""Money and date defects found in the Users audit; each test failed before its fix.

- The calendar day is Costa Rica's: at 18:00 on the last day of a month the server's UTC day is
  already next month, so a payment landed in the wrong month and the dashboards flipped early.
- An unknown interest rate gives no payoff estimate, not an interest-free one.
- Salvavidas with a debt whose payment is unknown can't state a base, target or coverage.
- A movement that is a debt payment can't be deleted by id: the debt stays reduced otherwise.
- A paid-off debt is no longer a monthly commitment.
"""
import re
from pathlib import Path

import pytest

from backend.finance.emergency_fund import _users_salvavidas_from
from backend.user_product import service
from backend.user_product.debt_payments import ACTIVE_MONTHLY_PAYMENT_SQL
from backend.user_product.strategy_engine import build_basic_strategy

HERE = Path(__file__).parent
USERS_MODULES = ["service.py", "free_service.py", "basic_service.py", "vip_service.py", "summary_breakdown.py"]


@pytest.mark.parametrize("module", USERS_MODULES)
def test_users_money_code_reads_the_costa_rica_day_not_the_servers(module):
    source = (HERE / module).read_text(encoding="utf-8")
    assert not re.search(r"\bdate\.today\(\)", source), f"{module}: use costa_rica_today()"
    assert "CURRENT_DATE" not in source, f"{module}: pass the Costa Rica day instead of the database's"


def _snapshot(rate):
    return {
        "monthly_income_estimate": 500000, "essential_monthly_expenses": 100000, "liquid_savings": 500000, "emergency_fund_target": 300000,
        "debts": [{"id": 1, "name": "Tarjeta", "remaining_amount": 300000, "monthly_payment": 30000,
                   "interest_rate": rate, "debt_type": "credit_card"}],
        "goals": [],
    }


def test_an_unknown_rate_gives_no_payoff_estimate():
    projection = build_basic_strategy(_snapshot(None))["projection"]
    assert projection["months"] is None and projection["baseline_months"] is None


def test_a_known_rate_still_gives_one():
    for rate in (0, 24):
        projection = build_basic_strategy(_snapshot(rate))["projection"]
        assert projection["months"] and projection["baseline_months"] >= projection["months"]


def _salvavidas(debts):
    return _users_salvavidas_from({"debts": debts, "recurring": [], "liquid_savings": 100000.0}, 3)


def test_salvavidas_states_nothing_it_cannot_know():
    result = _salvavidas([{"id": 1, "name": "A", "monthly_payment": 50000, "remaining_amount": 100, "monthly_payment_known": True},
                          {"id": 2, "name": "B", "monthly_payment": 0, "remaining_amount": 100, "monthly_payment_known": False}])
    assert result["unknown_debt_payments"] == 1
    for field in ("monthly_base", "target_amount", "missing_amount", "coverage_months", "progress_percent"):
        assert result[field] is None, field
    assert result["debts"][1]["monthly_payment"] is None
    assert all(m["target"] is None and m["reached"] is False for m in result["milestones"])
    assert result["status"] == "OK", "it has obligations: they are just not all known"


def test_salvavidas_with_every_payment_known_is_unchanged():
    result = _salvavidas([{"id": 1, "name": "A", "monthly_payment": 50000, "remaining_amount": 100, "monthly_payment_known": True}])
    assert result["unknown_debt_payments"] == 0
    assert result["monthly_base"] == 50000 and result["target_amount"] == 150000 and result["coverage_months"] == 2


def test_a_debt_payment_movement_cannot_be_deleted_by_id(monkeypatch):
    seen = []

    class Result:
        def fetchone(self):
            return {"id": 5}

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def commit(self):
            pass

        def execute(self, query, params=()):
            seen.append(query)
            return Result()

    monkeypatch.setattr(service, "get_connection", Conn)
    monkeypatch.setattr(service, "get_current_workspace_id", lambda: "00000000-0000-4000-8000-00000000000b")
    service.delete_user_transaction(5)
    assert "source IN ('finva','manual','manual_expense')" in seen[0]


def test_a_paid_off_debt_is_not_a_monthly_commitment():
    assert "remaining_amount>0" in ACTIVE_MONTHLY_PAYMENT_SQL.replace(" ", "")
    assert "ACTIVE_MONTHLY_PAYMENT_SQL" in (HERE / "basic_service.py").read_text(encoding="utf-8")
    assert "SUM(monthly_payment) FROM debts WHERE workspace_id=%s)" not in (HERE / "service.py").read_text(encoding="utf-8")
