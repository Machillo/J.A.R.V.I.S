"""The close of waiting dollar expenses (3d) on a real PostgreSQL.

Two synthetic workspaces. Pending expenses are grouped by their close: the card's statement cut, or
the calendar month without a card (a card without a declared cut day is never given one). A close
converts every expense still waiting in that period with one rate, only once the period has ended,
only in the caller's workspace, and only once.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException

from backend.tests.test_pending_conversion_pg import A, B, MIGRATION, _migrate, _query, _seed  # noqa: F401
from backend.tests.test_financial_ownership_integrity_pg import _create_database, admin_uri  # noqa: F401

psycopg2 = pytest.importorskip("psycopg2")

CARDS = """
ALTER TABLE account_balances ADD COLUMN IF NOT EXISTS account_type TEXT NOT NULL DEFAULT 'checking',
    ADD COLUMN IF NOT EXISTS account_last4 TEXT NOT NULL DEFAULT '', ADD COLUMN IF NOT EXISTS statement_cut_day SMALLINT
"""
INSERT = ("INSERT INTO expenses(workspace_id,category,expense_type,description,amount,original_amount,original_currency,created_at,"
          "financial_account_id) VALUES(%s,'Viajes','variable',%s,NULL,%s,'USD',%s,%s) RETURNING id")


@pytest.fixture
def db(admin_uri, monkeypatch):
    from backend.core import database
    from backend.user_product import pending_conversion

    uri, conn, drop = _create_database(admin_uri, _seed)
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    monkeypatch.setattr(pending_conversion, "get_current_account_id", lambda: A["account"])
    monkeypatch.setattr(pending_conversion, "get_current_workspace_id", lambda: A["workspace"])
    _migrate(conn)
    with conn.cursor() as cur:
        cur.execute(CARDS)
    try:
        yield conn
    finally:
        drop()


def _today(monkeypatch, day: date) -> None:
    from backend.user_product import pending_conversion

    monkeypatch.setattr(pending_conversion, "costa_rica_today", lambda: day)


def _account(conn, who, name, kind, cut=None) -> int:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO account_balances(workspace_id,account_name,account_type,account_last4,statement_cut_day)"
                    " VALUES(%s,%s,%s,'5678',%s) RETURNING id", (who["workspace"], name, kind, cut))
        return cur.fetchone()[0]


def _pending(conn, who, description, amount, day, account=None) -> int:
    with conn.cursor() as cur:
        cur.execute(INSERT, (who["workspace"], description, amount, f"{day} 12:00", account))
        return cur.fetchone()[0]


def _refused(call) -> tuple[int, str]:
    with pytest.raises(HTTPException) as error:
        call()
    detail = error.value.detail
    return error.value.status_code, detail["code"] if isinstance(detail, dict) else detail


@pytest.fixture
def october(db):
    """Workspace A: a card cutting on the 21st, a card without a cut day, and a cash expense."""
    card = _account(db, A, "Tarjeta", "credit_card", 21)
    undeclared = _account(db, A, "Tarjeta sin corte", "credit_card")
    ids = {
        "hotel": _pending(db, A, "Hotel", 120, "2026-10-12", card),
        "taxi": _pending(db, A, "Taxi", 30, "2026-10-25", card),
        "libro": _pending(db, A, "Libro", 15, "2026-10-08", undeclared),
        "efectivo": _pending(db, A, "Propina", 5, "2026-10-03"),
    }
    return {"card": card, "undeclared": undeclared, **ids}


def test_pending_expenses_are_grouped_by_their_close(db, october, monkeypatch):
    from backend.user_product import pending_conversion

    _today(monkeypatch, date(2026, 10, 22))
    listed = pending_conversion.list_pending()
    periods = {period["key"]: period for period in listed["periods"]}
    card = october["card"]
    assert set(periods) == {f"card:{card}:2026-10-21", f"card:{card}:2026-11-21", "month:2026-10"}
    october_cut = periods[f"card:{card}:2026-10-21"]
    assert (october_cut["start"], october_cut["end"], october_cut["closable"]) == ("2026-09-22", "2026-10-21", True)
    assert october_cut["totals"] == [{"currency": "USD", "amount": 120.0, "count": 1}]
    assert october_cut["account_name"] == "Tarjeta" and october_cut["account_last4"] == "5678"
    assert periods[f"card:{card}:2026-11-21"]["closable"] is False
    month = periods["month:2026-10"]  # cash plus the card without a cut day: never given one
    assert month["cut_day_missing"] is True and month["closable"] is False
    assert month["totals"] == [{"currency": "USD", "amount": 20.0, "count": 2}]
    assert {item["description"]: item["period_key"] for item in listed["items"]}["Hotel"] == f"card:{card}:2026-10-21"


def test_a_close_converts_its_period_with_one_rate_and_nothing_else(db, october, monkeypatch):
    from backend.user_product import pending_conversion

    _today(monkeypatch, date(2026, 10, 22))
    key = f"card:{october['card']}:2026-10-21"
    closed = pending_conversion.close_period(key, 510)
    assert (closed["converted"], closed["amount"], closed["currency"], closed["exchange_rate"]) == (1, 61200.0, "CRC", 510.0)
    assert _query(db, "SELECT amount, original_amount, exchange_rate FROM expenses WHERE id=%s", (october["hotel"],)) == [(61200, 120, 510)]
    still = sorted(row[0] for row in _query(db, "SELECT description FROM expenses WHERE amount IS NULL"))
    assert still == ["Libro", "Propina", "Taxi"]
    # Closed once: a second close of the same period finds nothing to convert.
    assert _refused(lambda: pending_conversion.close_period(key, 600)) == (404, "period_not_found")
    assert _query(db, "SELECT exchange_rate FROM expenses WHERE id=%s", (october["hotel"],)) == [(510,)]


def test_a_period_converts_only_once_it_has_ended(db, october, monkeypatch):
    from backend.user_product import pending_conversion

    _today(monkeypatch, date(2026, 10, 20))
    assert _refused(lambda: pending_conversion.close_period(f"card:{october['card']}:2026-10-21", 510)) == (409, "period_open")
    _today(monkeypatch, date(2026, 10, 31))  # the calendar month closes on its last day
    assert pending_conversion.close_period("month:2026-10", 505)["converted"] == 2
    assert _query(db, "SELECT amount FROM expenses WHERE id IN (%s,%s) ORDER BY id", (october["libro"], october["efectivo"])) == [
        (7575,), (2525,)]


def test_a_close_never_reaches_another_workspace(db, october, monkeypatch):
    from backend.user_product import pending_conversion

    other = _pending(db, B, "Vuelo B", 300, "2026-10-05")  # B's own October, same month key
    _today(monkeypatch, date(2026, 11, 1))
    listed = pending_conversion.list_pending()
    assert "Vuelo B" not in [item["description"] for item in listed["items"]]
    assert {period["key"]: period["count"] for period in listed["periods"]}["month:2026-10"] == 2
    assert pending_conversion.close_period("month:2026-10", 505)["converted"] == 2
    assert _query(db, "SELECT amount FROM expenses WHERE id=%s", (other,)) == [(None,)]
    # Another workspace's card id names no period of A.
    foreign = _account(db, B, "Tarjeta B", "credit_card", 21)
    assert _refused(lambda: pending_conversion.close_period(f"card:{foreign}:2026-10-21", 505)) == (404, "period_not_found")


def test_an_invalid_rate_converts_nothing(db, october, monkeypatch):
    from backend.user_product import pending_conversion

    _today(monkeypatch, date(2026, 10, 22))
    status, _ = _refused(lambda: pending_conversion.close_period(f"card:{october['card']}:2026-10-21", 0))
    assert status == 422
    assert _query(db, "SELECT amount FROM expenses WHERE id=%s", (october["hotel"],)) == [(None,)]
