"""Settling money owed is never earned income. Pure rules; synthetic names only."""
import pytest

from backend.finance import receivable_semantics as rs


@pytest.mark.parametrize("method", ["SINPE", "Transferencia", "Efectivo", "manual", "Otro", None])
def test_cash_methods_are_collections_not_income(method):
    how = rs.settlement(method)
    assert how["transaction_type"] == "receivable_payment" and how["is_cash"] is True
    assert how["account"] is None  # the method is a note, never an account


@pytest.mark.parametrize("method", ["non_cash_offset", "offset", "Compensación"])
def test_offset_moves_no_money(method):
    how = rs.settlement(method)
    assert how["transaction_type"] == "receivable_offset" and how["is_cash"] is False
    assert how["entry_source_type"] == "non_cash_offset"


def test_balance_comes_from_the_ledger_and_ignores_archived_entries():
    ledger = [
        {"entry_type": "charge", "amount": 200000, "is_archived": False},   # one instalment sale
        {"entry_type": "payment", "amount": 10000, "is_archived": False},   # cash collection
        {"entry_type": "payment", "amount": 18500, "is_archived": False},   # non-cash offset
        {"entry_type": "charge", "amount": 99999, "is_archived": True},
    ]
    assert rs.receivable_totals(ledger) == {"original_amount": 200000.0, "paid_amount": 28500.0, "pending_amount": 171500.0, "status": "partial"}


@pytest.mark.parametrize("kind, expected", [("installment_sale", "installment_sale"), ("LOAN", "loan"), ("purchase", "purchase"), ("raro", "other"), (None, "purchase")])
def test_charge_kinds(kind, expected):
    assert rs.charge_kind(kind) == expected


PEOPLE = ["Ana Prueba", "Luis Ejemplo"]


def test_payer_needs_payment_context_and_one_person():
    assert rs.payer_from_text("SINPE de Ana Prueba", PEOPLE) == "Ana Prueba"
    assert rs.payer_from_text("abono luis ejemplo", PEOPLE) == "Luis Ejemplo"
    assert rs.payer_from_text("Ana Prueba", PEOPLE) is None                       # no payment context
    assert rs.payer_from_text("SINPE de Ana Prueba y Luis Ejemplo", PEOPLE) is None  # ambiguous
    assert rs.payer_from_text("SINPE de Anabel", ["Ana"]) is None                 # never inside another word
    assert rs.payer_from_text("SINPE de alguien", []) is None                     # no people, no guess
