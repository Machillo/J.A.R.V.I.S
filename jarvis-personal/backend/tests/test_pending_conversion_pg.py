"""Expenses waiting for their conversion (USD until the close) on a real PostgreSQL.

Two synthetic workspaces, through the real connection wrapper. An expense typed in dollars without a
rate, asked for explicitly, is stored pending: no colones amount and no rate, never 0. Base-currency
reads (movements, expense list, month totals, categories) leave it out; the pending listing shows it
with its dollar total, only to its own workspace. Before the migration the state cannot exist: the
listing says "unavailable" and only a request that asks for it answers 503.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException

from backend.tests.test_financial_ownership_integrity_pg import (  # noqa: F401  (admin_uri is a fixture)
    IDENTITIES,
    _create_database,
    _seed_identities,
    admin_uri,
)

psycopg2 = pytest.importorskip("psycopg2")

A, B = IDENTITIES["A"], IDENTITIES["B"]
TABLES = """
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS base_currency TEXT NOT NULL DEFAULT 'CRC';
CREATE TABLE IF NOT EXISTS account_balances (
    id BIGSERIAL PRIMARY KEY, workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    account_name TEXT NOT NULL, account_type TEXT NOT NULL DEFAULT 'checking', account_last4 TEXT NOT NULL DEFAULT ''
);
-- The test baseline has a narrower `expenses`: production's columns and its two-shape currency check.
ALTER TABLE expenses ADD COLUMN IF NOT EXISTS expense_type TEXT,
    ADD COLUMN IF NOT EXISTS description TEXT, ADD COLUMN IF NOT EXISTS original_amount NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS original_currency TEXT, ADD COLUMN IF NOT EXISTS exchange_rate NUMERIC(14, 6),
    ADD COLUMN IF NOT EXISTS financial_account_id BIGINT REFERENCES account_balances(id) ON DELETE SET NULL;
ALTER TABLE expenses ADD CONSTRAINT expenses_original_currency_check CHECK (
    (original_currency IS NULL AND original_amount IS NULL AND exchange_rate IS NULL)
    OR (original_currency IS NOT NULL AND original_amount IS NOT NULL AND exchange_rate IS NOT NULL
        AND original_currency IN ('CRC', 'USD') AND original_amount > 0 AND exchange_rate > 0));
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS original_amount NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS original_currency TEXT, ADD COLUMN IF NOT EXISTS exchange_rate NUMERIC(12, 6);
CREATE TABLE IF NOT EXISTS salaries (
    id BIGSERIAL PRIMARY KEY, workspace_id UUID, amount NUMERIC(14, 2) NOT NULL, source TEXT, category TEXT,
    original_amount NUMERIC(14, 2), original_currency TEXT, exchange_rate NUMERIC(12, 6),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS payroll_events (
    id BIGSERIAL PRIMARY KEY, workspace_id UUID, amount NUMERIC(14, 2), description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""
# The effect of migration 20261027120000, applied by the tests that need it.
MIGRATION = """
ALTER TABLE expenses ALTER COLUMN amount DROP NOT NULL;
ALTER TABLE expenses DROP CONSTRAINT expenses_original_currency_check;
ALTER TABLE expenses ADD CONSTRAINT expenses_original_currency_check CHECK (
    (original_currency IS NULL AND original_amount IS NULL AND exchange_rate IS NULL)
    OR (original_currency IS NOT NULL AND original_amount IS NOT NULL AND exchange_rate IS NOT NULL
        AND original_currency IN ('CRC', 'USD') AND original_amount > 0 AND exchange_rate > 0)
    OR (original_currency IS NOT NULL AND original_amount IS NOT NULL AND exchange_rate IS NULL AND amount IS NULL
        AND original_currency IN ('CRC', 'USD') AND original_amount > 0));
ALTER TABLE expenses ADD CONSTRAINT expenses_amount_known_or_pending_check
    CHECK (amount IS NOT NULL OR (original_amount IS NOT NULL AND exchange_rate IS NULL))
"""
OCTOBER = (date(2026, 10, 1), date(2026, 11, 1))


def _seed(cur) -> None:
    _seed_identities(cur)
    cur.execute(TABLES)
    for who in (A, B):  # each workspace: one colones expense in October
        cur.execute("INSERT INTO expenses(workspace_id,category,expense_type,description,amount,created_at)"
                    " VALUES(%s,'Alimentación','variable','Súper',20000,'2026-10-05 12:00')", (who["workspace"],))


@pytest.fixture
def db(admin_uri, monkeypatch):
    from backend.core import database
    from backend.user_product import expense_account, free_service, pending_conversion, service

    uri, conn, drop = _create_database(admin_uri, _seed)
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    for module in (expense_account, free_service, pending_conversion, service):  # the caller is workspace A
        if hasattr(module, "get_current_account_id"):
            monkeypatch.setattr(module, "get_current_account_id", lambda: A["account"])
        monkeypatch.setattr(module, "get_current_workspace_id", lambda: A["workspace"])
    monkeypatch.setattr(service, "_legacy_financial_user_id", lambda: 1)
    monkeypatch.setattr(free_service, "owner_account_context", lambda *_: False)
    try:
        yield conn
    finally:
        drop()


def _migrate(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(MIGRATION)


def _query(conn, sql: str, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def _expense(**fields):
    from backend.user_product.models import ExpenseCreateRequest

    values = {"amount": 120, "description": "Hotel", "category": "Viajes", "entry_date": date(2026, 10, 12),
              "currency": "USD", **fields}
    return ExpenseCreateRequest(**values)


def _movement(**fields):
    from backend.user_product.models import MovementUpdateRequest

    values = {"transaction_date": date(2026, 10, 13), "description": "Hotel", "amount": 150,
              "transaction_type": "expense", "category": "Viajes", "currency": "USD", **fields}
    return MovementUpdateRequest(**values)


def _refused(call) -> tuple[int, object]:
    with pytest.raises(HTTPException) as error:
        call()
    return error.value.status_code, error.value.detail


def _base_reads(conn) -> dict:
    """What the base-currency surfaces show for workspace A in October."""
    from backend.core.database import get_connection
    from backend.user_product import free_service, service

    with get_connection() as wrapped:
        totals = free_service._period_totals(wrapped, A["workspace"], *OCTOBER)
        categories = free_service._categories(wrapped, A["workspace"], *OCTOBER)
    return {
        "expenses": totals["expenses"], "categories": categories,
        "movements": sorted(row["description"] for row in free_service.list_free_movements()),
        "expense_list": sorted(row["description"] for row in service.list_expenses()),
    }


def test_before_the_migration_the_state_cannot_exist_and_nothing_else_changes(db):
    from backend.user_product import pending_conversion, service

    assert pending_conversion.list_pending() == {"status": "ok", "available": False, "items": [], "totals": [], "periods": []}
    status, detail = _refused(lambda: service.create_expense_entry(_expense(convert_at_close=True)))
    assert (status, detail["code"]) == (503, "pending_conversion_unavailable")
    # Without the flag a dollar expense still needs its rate, as before.
    assert _refused(lambda: service.create_expense_entry(_expense()))[0] == 422
    service.create_expense_entry(_expense(exchange_rate=500))  # converted now: 60,000 colones
    assert _query(db, "SELECT amount, original_amount, exchange_rate FROM expenses WHERE description='Hotel'") == [(60000, 120, 500)]


def test_a_pending_expense_is_stored_without_colones_and_listed_apart(db):
    from backend.user_product import pending_conversion, service

    _migrate(db)
    before = _base_reads(db)
    created = service.create_expense_entry(_expense(convert_at_close=True))
    assert created["amount"] is None and created["exchange_rate"] is None
    assert _query(db, "SELECT amount, original_amount, original_currency, exchange_rate FROM expenses WHERE description='Hotel'") == [
        (None, 120, "USD", None)]
    # Unknown is not zero: every base-currency read is exactly as before (no ₡0 row, no NULL category).
    assert _base_reads(db) == before
    listed = pending_conversion.list_pending()
    assert listed["available"] is True
    assert [(item["description"], item["original_amount"], item["original_currency"], item["entry_date"]) for item in listed["items"]] == [
        ("Hotel", 120.0, "USD", "2026-10-12")]
    assert listed["totals"] == [{"currency": "USD", "amount": 120.0, "count": 1}]
    service.create_expense_entry(_expense(amount=30.5, description="Taxi", convert_at_close=True))
    assert pending_conversion.list_pending()["totals"] == [{"currency": "USD", "amount": 150.5, "count": 2}]


def test_only_a_whole_dollar_expense_without_a_rate_can_wait(db):
    from backend.user_product import service

    _migrate(db)
    assert _refused(lambda: service.create_expense_entry(_expense(convert_at_close=True, exchange_rate=500)))[0] == 422
    assert _refused(lambda: service.create_expense_entry(_expense(convert_at_close=True, currency="CRC")))[0] == 422
    assert _refused(lambda: service.create_expense_entry(_expense(convert_at_close=True, currency=None)))[0] == 422
    assert _query(db, "SELECT count(*) FROM expenses WHERE description='Hotel'") == [(0,)]


def test_the_pending_listing_never_crosses_workspaces(db):
    from backend.user_product import pending_conversion, service

    _migrate(db)
    with db.cursor() as cur:  # workspace B's own pending expense
        cur.execute("INSERT INTO expenses(workspace_id,category,expense_type,description,amount,original_amount,original_currency)"
                    " VALUES(%s,'Viajes','variable','Vuelo B',NULL,300,'USD')", (B["workspace"],))
    assert pending_conversion.list_pending()["items"] == []
    service.create_expense_entry(_expense(convert_at_close=True))
    assert [item["description"] for item in pending_conversion.list_pending()["items"]] == ["Hotel"]


def test_an_edit_keeps_it_pending_or_converts_it_with_the_users_rate(db):
    from backend.user_product import free_service, pending_conversion, service

    _migrate(db)
    expense_id = service.create_expense_entry(_expense(convert_at_close=True))["id"]
    movement = f"expense:{expense_id}"
    free_service.update_free_movement(movement, _movement(convert_at_close=True))  # still pending, now 150 USD
    assert pending_conversion.list_pending()["totals"] == [{"currency": "USD", "amount": 150.0, "count": 1}]
    free_service.update_free_movement(movement, _movement(exchange_rate=510))  # the user converts it now
    assert _query(db, "SELECT amount, original_amount, exchange_rate FROM expenses WHERE id=%s", (expense_id,)) == [(76500, 150, 510)]
    assert pending_conversion.list_pending()["items"] == []
    assert "Hotel" in [row["description"] for row in free_service.list_free_movements()]


def test_income_and_ledger_rows_cannot_wait_for_the_close(db):
    from backend.user_product import free_service

    _migrate(db)
    with db.cursor() as cur:
        cur.execute("INSERT INTO salaries(workspace_id,amount,source,category) VALUES(%s,500000,'Planilla','Salario') RETURNING id",
                    (A["workspace"],))
        salary_id = cur.fetchone()[0]
    status, _ = _refused(lambda: free_service.update_free_movement(
        f"salary:{salary_id}", _movement(transaction_type="income", category="Salario", convert_at_close=True)))
    assert status == 422
    assert _query(db, "SELECT amount FROM salaries WHERE id=%s", (salary_id,)) == [(500000,)]
