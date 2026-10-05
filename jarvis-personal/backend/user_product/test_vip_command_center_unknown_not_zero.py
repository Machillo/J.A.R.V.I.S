"""The VIP command center never states a financial fact from an unknown value (unknown ≠ 0).

Regression: with an income nobody knows (income policy source "none", returned as 0) the
command center said "Cierre mensual negativo" (critical); with undeclared savings, or with no
commitments at all (coverage fell back to 0), it said "Reserva menor a un mes" (high). Both
alerts now require the data behind them; a known zero keeps its meaning. Thresholds,
severities and copy are unchanged. All data is synthetic.
"""
import copy

import pytest

from backend.auth.current_user import reset_current_user, set_current_user
from backend.core.i18n import use_language
from backend.user_product import basic_service, service, vip_service
from backend.user_product.test_mail_preserves_financial_state import ACCOUNT, ALLOWED_USER_ID, WORKSPACE
from backend.user_product.test_vip_emergency_target import ProjectingConnection, ProjectingDB

NEGATIVE_CLOSE = "Cierre mensual negativo"
LOW_RESERVE = "Reserva menor a un mes"


class RecordingConnection(ProjectingConnection):
    """Also answers active recurring items and records every statement it runs."""

    def execute(self, query, params=()):
        statement = " ".join(query.split())
        self.db.statements.append(statement)
        if "FROM finva_recurring_items WHERE workspace_id=%s AND is_active=TRUE" in statement:
            return self._result([dict(row) for row in self.work.get("recurring", []) if row["workspace_id"] == params[0]])
        return super().execute(query, params)


class RecordingDB(ProjectingDB):
    def __init__(self):
        super().__init__()
        self.statements = []

    def connect(self):
        return RecordingConnection(self)


@pytest.fixture
def ledger(monkeypatch):
    database = RecordingDB()
    # Default synthetic profile: declared salary 1.000.000, essentials 400.000, savings 300.000,
    # one card with a 50.000 monthly payment → commitments 450.000, coverage 0.67 months.
    for module in (vip_service, service, basic_service):
        monkeypatch.setattr(module, "get_connection", database.connect, raising=False)
    return database


def _profile(ledger):
    return ledger.state["profiles"][ACCOUNT]


def _recurring_income(amount):
    return {"id": 61, "workspace_id": WORKSPACE, "name": "Ingreso recurrente sintético", "amount": amount,
            "category": "Salario", "item_type": "income", "frequency": "monthly", "due_day": 15, "is_active": True}


def _center(role="user"):
    token = set_current_user({"id": ALLOWED_USER_ID, "account_id": ACCOUNT, "workspace_id": WORKSPACE, "role": role})
    try:
        with use_language("es"):
            return vip_service.get_vip_command_center()
    finally:
        reset_current_user(token)


def _titles(center):
    return [alert["title"] for alert in center["alerts"]]


# Income ----------------------------------------------------------------------------------------

def test_unknown_income_never_says_the_month_closes_negative(ledger):
    _profile(ledger).update({"fixed_monthly_salary": None})  # nothing declared, nothing recorded
    center = _center()
    assert center["safe_to_spend"]["monthly_margin"] < 0      # the margin itself is unchanged here
    assert NEGATIVE_CLOSE not in _titles(center)


def test_a_known_zero_income_keeps_its_meaning(ledger):
    # The only income the user keeps is a recurring item of 0: a known zero, not an unknown.
    _profile(ledger).update({"fixed_monthly_salary": None})
    ledger.state["recurring"] = [_recurring_income(0)]
    assert NEGATIVE_CLOSE in _titles(_center())


def test_a_known_income_below_its_commitments_still_closes_negative(ledger):
    _profile(ledger).update({"fixed_monthly_salary": 300000})  # 300.000 < 450.000 of commitments
    center = _center()
    alert = next(alert for alert in center["alerts"] if alert["title"] == NEGATIVE_CLOSE)
    assert alert["severity"] == "critical"
    assert "₡150,000" in alert["context"]   # existing formatting, unchanged


def test_a_known_income_that_covers_its_commitments_has_no_negative_close(ledger):
    assert NEGATIVE_CLOSE not in _titles(_center())


# Reserve ---------------------------------------------------------------------------------------

def test_unknown_savings_never_say_the_reserve_is_below_one_month(ledger):
    _profile(ledger).update({"liquid_savings": None})
    assert LOW_RESERVE not in _titles(_center())


def test_unknown_commitments_give_no_reserve_alert(ledger):
    # Essentials never declared, no recurring expenses, no debts: nothing to divide by.
    _profile(ledger).update({"essential_monthly_expenses": None})
    ledger.state["debts"] = [debt for debt in ledger.state["debts"] if debt["workspace_id"] != WORKSPACE]
    assert LOW_RESERVE not in _titles(_center())


def test_no_commitments_is_not_a_zero_coverage(ledger):
    # Essentials declared as 0 and no debts: there is no coverage to state, not a coverage of 0.
    _profile(ledger).update({"essential_monthly_expenses": 0, "liquid_savings": 0})
    ledger.state["debts"] = [debt for debt in ledger.state["debts"] if debt["workspace_id"] != WORKSPACE]
    assert LOW_RESERVE not in _titles(_center())


def test_known_zero_savings_with_known_commitments_keep_the_reserve_alert(ledger):
    _profile(ledger).update({"liquid_savings": 0})
    alert = next(alert for alert in _center()["alerts"] if alert["title"] == LOW_RESERVE)
    assert alert["severity"] == "high"
    assert "0.0 meses" in alert["context"]


def test_known_savings_below_one_month_keep_the_reserve_alert(ledger):
    alert = next(alert for alert in _center()["alerts"] if alert["title"] == LOW_RESERVE)
    assert "0.7 meses" in alert["context"]   # 300.000 / 450.000, as before


def test_a_reserve_of_one_month_or_more_has_no_reserve_alert(ledger):
    _profile(ledger).update({"liquid_savings": 450000})   # exactly one month
    assert LOW_RESERVE not in _titles(_center())
    _profile(ledger).update({"liquid_savings": 900000})
    assert LOW_RESERVE not in _titles(_center())


# Contract and purity ---------------------------------------------------------------------------

def test_the_other_alerts_and_the_figures_are_unchanged(ledger):
    _profile(ledger).update({"fixed_monthly_salary": None, "liquid_savings": None})
    center = _center()
    # Pending imported transactions still raise their alert; margins and score keep their values.
    assert "Movimientos por revisar" in _titles(center)
    assert center["safe_to_spend"]["monthly_margin"] == -450000.0
    assert {"severity", "title", "context", "action"} == set(center["alerts"][0])


def test_reading_the_command_center_writes_nothing(ledger):
    before = copy.deepcopy(ledger.state)
    ledger.statements.clear()
    _center()
    assert ledger.state == before
    writes = [s for s in ledger.statements if s.split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}]
    assert writes == []
    assert not [s for s in ledger.statements if "notification" in s.lower()]


def test_vip_and_the_owner_read_the_same_contract(ledger):
    vip, owner = _center("user"), _center("owner")
    assert set(vip) == set(owner)
    assert _titles(vip) == _titles(owner)
