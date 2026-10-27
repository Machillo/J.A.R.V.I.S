"""DEB-07a: a debt's payment history (real PostgreSQL, Users paths). Read-only.

Payments recorded with "Registrar pago" (`pay_user_debt`) are listed for their debt, newest first,
with the amount actually applied (a payment above the balance is capped). Another debt's payments are
not listed, another workspace's debt answers 404, and reading the history changes nothing.
Synthetic accounts and amounts.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.core import database
from backend.tests.test_financial_ownership_integrity_pg import (  # noqa: F401  (admin_uri is a fixture)
    IDENTITIES,
    _create_database,
    _seed_identities,
    admin_uri,
)
from backend.user_product import service

psycopg2 = pytest.importorskip("psycopg2")

A, B = IDENTITIES["A"], IDENTITIES["B"]


@pytest.fixture
def db(admin_uri, monkeypatch):
    uri, conn, drop = _create_database(admin_uri, _seed_identities)
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    state = {"identity": A}
    monkeypatch.setattr(service, "get_current_workspace_id", lambda: state["identity"]["workspace"])
    monkeypatch.setattr(service, "_legacy_financial_user_id", lambda: state["identity"]["users"])
    monkeypatch.setattr(service, "mark_applied", lambda _conn: None)
    try:
        yield {"conn": conn, "state": state}
    finally:
        drop()


def _debt(name: str, remaining: float = 100000) -> int:
    return service.create_user_debt(SimpleNamespace(
        name=name, debt_type="loan", total_amount=None, remaining_amount=remaining, monthly_payment=25000,
        interest_rate=None, payment_day=None, term_months=None, next_payment_date=None))["id"]


def _counts(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT (SELECT count(*) FROM transactions), (SELECT sum(remaining_amount) FROM debts)")
        return cur.fetchone()


def test_a_debts_payments_are_listed_newest_first_with_the_amount_applied(db):
    loan = _debt("Préstamo sintético", remaining=100000)
    other = _debt("Tarjeta sintética")
    service.pay_user_debt(loan, 30000)
    service.pay_user_debt(other, 5000)
    service.pay_user_debt(loan, 90000)  # above the balance left (70000): capped
    payments = service.list_user_debt_payments(loan)
    assert [payment["amount"] for payment in payments] == [70000.0, 30000.0], "newest first, the amount applied"
    assert all(payment["payment_date"] for payment in payments)
    assert [payment["amount"] for payment in service.list_user_debt_payments(other)] == [5000.0]


def test_a_debt_without_payments_has_an_empty_history(db):
    assert service.list_user_debt_payments(_debt("Sin pagos")) == []


def test_another_workspaces_debt_answers_404(db):
    loan = _debt("Préstamo de A")
    service.pay_user_debt(loan, 10000)
    db["state"]["identity"] = B
    with pytest.raises(HTTPException) as refused:
        service.list_user_debt_payments(loan)
    assert refused.value.status_code == 404


def test_reading_the_history_changes_nothing(db):
    loan = _debt("Préstamo sintético")
    service.pay_user_debt(loan, 10000)
    before = _counts(db["conn"])
    service.list_user_debt_payments(loan)
    service.list_user_debt_payments(loan)
    assert _counts(db["conn"]) == before
