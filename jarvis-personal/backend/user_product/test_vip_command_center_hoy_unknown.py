"""What Hoy states from the VIP command center is never made from an unknown (UX-6, UNKNOWN ≠ 0).

Safe to spend, the monthly margin, the 45-day minimum, the director's priority and the roadmap
need known inputs. When one is missing the figure is null, `missing` names the inputs with stable
codes, the director is `incomplete` and the roadmap is empty — never ₡0, never a false deficit,
never a reserve gap or an "invest" from data DINCR doesn't have. Fully known inputs keep their
results. Score, projections and net worth are out of scope. All data is synthetic.

Default synthetic profile (test_mail_preserves_financial_state): declared salary 1.000.000,
essentials 400.000, savings 300.000, reserve target 0, one card with balance 500.000 and a
50.000 monthly payment due in 10 days → commitments 450.000, margin 550.000.
"""
import copy

import pytest

from backend.user_product.test_mail_preserves_financial_state import WORKSPACE
from backend.user_product.test_vip_command_center_unknown_not_zero import RecordingDB, _center
from backend.user_product import basic_service, service, vip_service

DEFICIT_HEADLINE = "Cerrar el déficit mensual"


@pytest.fixture
def ledger(monkeypatch):
    database = RecordingDB()
    for module in (vip_service, service, basic_service):
        monkeypatch.setattr(module, "get_connection", database.connect, raising=False)
    return database


def _profile(ledger):
    from backend.user_product.test_mail_preserves_financial_state import ACCOUNT
    return ledger.state["profiles"][ACCOUNT]


def _own_debts(ledger):
    return [debt for debt in ledger.state["debts"] if debt["workspace_id"] == WORKSPACE]


def _titles(center):
    return [step["title"] for step in center["roadmap"]]


# Fully known ------------------------------------------------------------------------------------

def test_fully_known_inputs_keep_their_results(ledger):
    center = _center()
    assert center["safe_to_spend"] == {"amount": 250000.0, "monthly_margin": 550000.0, "next_45_days_minimum": 250000.0, "missing": []}
    assert center["director"]["priority"] == "debt"
    assert center["director"]["missing"] == []
    assert _titles(center) == ["Abonar a Tarjeta Sintética", "Invertir"]


def test_a_known_monthly_payment_still_counts_normally(ledger):
    _own_debts(ledger)[0]["monthly_payment"] = 100000
    center = _center()
    assert center["safe_to_spend"]["monthly_margin"] == 500000.0
    assert center["safe_to_spend"]["amount"] == 200000.0  # 300.000 − 100.000 in 10 days


# Income -----------------------------------------------------------------------------------------

def test_unknown_income_is_null_never_a_safe_to_spend_of_zero(ledger):
    _profile(ledger).update({"fixed_monthly_salary": None})
    spend = _center()["safe_to_spend"]
    assert spend["amount"] is None and spend["monthly_margin"] is None
    assert spend["missing"] == ["income"]
    assert spend["next_45_days_minimum"] == 250000.0  # the cash timeline doesn't need the income


def test_unknown_income_is_no_deficit_and_no_close_the_deficit_priority(ledger):
    _profile(ledger).update({"fixed_monthly_salary": None})
    center = _center()
    assert center["director"]["priority"] == "incomplete"
    assert center["director"]["headline"] != DEFICIT_HEADLINE
    assert center["director"]["missing"] == ["income"]
    assert "₡" not in center["director"]["next_action"]  # no amount to assign
    assert center["roadmap"] == []  # no "Eliminar déficit", no step from an unknown margin


# Essential expenses -----------------------------------------------------------------------------

def test_unknown_essential_expenses_make_the_figures_unknown(ledger):
    _profile(ledger).update({"essential_monthly_expenses": None})
    center = _center()
    assert center["safe_to_spend"]["amount"] is None and center["safe_to_spend"]["monthly_margin"] is None
    assert center["safe_to_spend"]["missing"] == ["essential_expenses"]
    assert center["director"]["priority"] == "incomplete" and center["roadmap"] == []


def test_declared_zero_essential_expenses_are_a_known_zero(ledger):
    _profile(ledger).update({"essential_monthly_expenses": 0})
    spend = _center()["safe_to_spend"]
    assert spend["missing"] == [] and spend["monthly_margin"] == 950000.0


# Debt payments ----------------------------------------------------------------------------------

def test_an_active_debt_without_a_known_payment_is_not_a_payment_of_zero(ledger):
    _own_debts(ledger)[0]["monthly_payment"] = 0  # how create_user_debt stores an unknown payment
    center = _center()
    spend = center["safe_to_spend"]
    assert spend["amount"] is None and spend["monthly_margin"] is None and spend["next_45_days_minimum"] is None
    assert spend["missing"] == ["debt_payments"]
    assert center["director"]["priority"] == "incomplete" and center["roadmap"] == []


# Reserve / savings ------------------------------------------------------------------------------

def test_unknown_savings_with_a_target_never_state_the_gap(ledger):
    _profile(ledger).update({"liquid_savings": None, "emergency_fund_target": 600000})
    center = _center()
    assert center["director"]["priority"] == "incomplete"
    assert center["director"]["missing"] == ["savings"]
    assert center["director"]["headline"] != "Completar el fondo de emergencia"
    assert center["roadmap"] == []
    # No fictitious coverage of 0: no reserve alert, and no cash figure from undeclared savings.
    assert "Tu fondo de emergencia cubre menos de un mes" not in [alert["title"] for alert in center["alerts"]]
    assert center["safe_to_spend"]["amount"] is None and center["safe_to_spend"]["next_45_days_minimum"] is None
    assert center["safe_to_spend"]["missing"] == ["savings"]


def test_unknown_reserve_never_recommends_investing(ledger):
    # No debts, no goals, target never declared: the only remaining priority would be "invest".
    _profile(ledger).update({"emergency_fund_target": None})
    ledger.state["debts"] = [debt for debt in ledger.state["debts"] if debt["workspace_id"] != WORKSPACE]
    center = _center()
    assert center["director"]["priority"] == "incomplete"
    assert center["director"]["missing"] == ["emergency_fund_target"]
    assert center["director"]["headline"] != "Preparar inversión"
    assert "Invertir" not in _titles(center) and center["roadmap"] == []
    assert center["safe_to_spend"]["missing"] == []  # spending doesn't need the reserve


def test_an_unknown_target_doesnt_block_the_debt_priority(ledger):
    # Optional data missing is not a global block: the debt priority doesn't depend on the reserve.
    _profile(ledger).update({"emergency_fund_target": None})
    center = _center()
    assert center["director"]["priority"] == "debt" and center["director"]["missing"] == []
    assert _titles(center) == ["Abonar a Tarjeta Sintética", "Esperar para invertir"]  # never "Invertir"


def test_a_known_deficit_stays_a_deficit_even_with_unknown_reserve_data(ledger):
    # Known income below known commitments is a real deficit: the reserve doesn't change that, and
    # no reserve step is invented from undeclared savings.
    _profile(ledger).update({"fixed_monthly_salary": 300000, "liquid_savings": None, "emergency_fund_target": 600000})
    center = _center()
    assert center["director"]["priority"] == "stabilize"
    assert center["safe_to_spend"]["monthly_margin"] == -150000.0
    assert _titles(center) == ["Eliminar déficit", "Esperar para invertir"]


def test_declared_zero_savings_are_a_known_zero(ledger):
    _profile(ledger).update({"liquid_savings": 0, "emergency_fund_target": 600000})
    center = _center()
    assert center["director"]["priority"] == "emergency"
    assert "Completar reserva" in _titles(center)


def test_confirmed_balances_make_cash_known_without_declared_savings(ledger):
    _profile(ledger).update({"liquid_savings": None})
    ledger.state["accounts"] = [{"workspace_id": WORKSPACE, "is_active": True, "account_name": "Cuenta sintética",
                                 "bank_name": "Banco sintético", "currency": "CRC", "current_balance": 400000,
                                 "account_type": "checking", "include_in_net_worth": True}]
    spend = _center()["safe_to_spend"]
    assert spend["missing"] == [] and spend["amount"] == 350000.0  # 400.000 − 50.000 in 10 days


# Contract, Owner, purity ------------------------------------------------------------------------

def test_missing_names_every_unknown_input_with_stable_codes(ledger):
    _profile(ledger).update({"fixed_monthly_salary": None, "essential_monthly_expenses": None, "liquid_savings": None})
    _own_debts(ledger)[0]["monthly_payment"] = 0
    center = _center()
    assert center["safe_to_spend"]["missing"] == ["income", "essential_expenses", "debt_payments", "savings"]
    assert center["director"]["missing"] == ["income", "essential_expenses", "debt_payments"]


def test_vip_and_the_owner_read_the_same_contract(ledger):
    _profile(ledger).update({"fixed_monthly_salary": None})
    vip, owner = _center("user"), _center("owner")
    assert vip["safe_to_spend"] == owner["safe_to_spend"]
    assert vip["director"] == owner["director"]


def test_reading_the_command_center_still_writes_nothing(ledger):
    _profile(ledger).update({"fixed_monthly_salary": None, "liquid_savings": None})
    before = copy.deepcopy(ledger.state)
    ledger.statements.clear()
    _center()
    assert ledger.state == before
    assert not [s for s in ledger.statements if s.split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}]
    assert not [s for s in ledger.statements if "notification" in s.lower()]
