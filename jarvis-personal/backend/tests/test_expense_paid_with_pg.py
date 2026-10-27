"""A manual expense's "paid with" account on a real PostgreSQL, through the real connection wrapper.

Two synthetic workspaces. An expense links only to the caller's own, active accounts; another
workspace's account is "not found"; a request that does not send the field leaves the link as it
is; before the migration (column absent) reads say "unavailable", expenses still save, and only a
request that links an account answers 503, never 500.
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
# The columns the public code reads (production's tables), without the new column.
TABLES = """
CREATE TABLE IF NOT EXISTS account_balances (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL DEFAULT 1,
    account_id UUID, workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    account_name TEXT NOT NULL, bank_name TEXT NOT NULL DEFAULT '', institution_code TEXT,
    account_type TEXT NOT NULL DEFAULT 'checking', account_last4 TEXT NOT NULL DEFAULT '',
    currency TEXT NOT NULL DEFAULT 'CRC', ownership_status TEXT NOT NULL DEFAULT 'own',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE(workspace_id, account_name, account_last4)
);
-- The test baseline already has a narrower `expenses`: give it production's other columns.
ALTER TABLE expenses ADD COLUMN IF NOT EXISTS expense_type TEXT,
    ADD COLUMN IF NOT EXISTS description TEXT, ADD COLUMN IF NOT EXISTS original_amount NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS original_currency TEXT, ADD COLUMN IF NOT EXISTS exchange_rate NUMERIC(12, 6);
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
# The migration's effect (20261026130000), applied by the tests that need it.
ADD_COLUMN = "ALTER TABLE expenses ADD COLUMN financial_account_id BIGINT REFERENCES account_balances(id) ON DELETE SET NULL"
ROWS = [  # name, workspace identity, type, ownership, active
    ("Tarjeta A", A, "credit_card", "own", True),
    ("Cuenta A", A, "checking", "own", True),
    ("Tarjeta pendiente A", A, "credit_card", "pending", True),
    ("Tarjeta inactiva A", A, "credit_card", "own", False),
    ("Tarjeta B", B, "credit_card", "own", True),
]


def _seed(cur) -> None:
    _seed_identities(cur)
    cur.execute(TABLES)
    for n, (name, who, kind, ownership, active) in enumerate(ROWS):
        cur.execute("INSERT INTO account_balances(account_id,workspace_id,account_name,account_type,account_last4,ownership_status,is_active)"
                    " VALUES(%s,%s,%s,%s,%s,%s,%s)", (who["account"], who["workspace"], name, kind, f"{1000 + n}", ownership, active))


@pytest.fixture
def db(admin_uri, monkeypatch):
    from backend.core import database
    from backend.user_product import expense_account, free_service, service

    uri, conn, drop = _create_database(admin_uri, _seed)
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    for module in (expense_account, free_service, service):  # the caller is workspace A
        monkeypatch.setattr(module, "get_current_account_id", lambda: A["account"])
        monkeypatch.setattr(module, "get_current_workspace_id", lambda: A["workspace"])
    monkeypatch.setattr(service, "_legacy_financial_user_id", lambda: 1)
    monkeypatch.setattr(free_service, "owner_account_context", lambda *_: False)
    try:
        yield conn
    finally:
        drop()


def _ids(conn) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute("SELECT account_name, id FROM account_balances")
        return dict(cur.fetchall())


def _query(conn, sql: str, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def _status(call) -> tuple[int, str]:
    with pytest.raises(HTTPException) as error:
        call()
    return error.value.status_code, error.value.detail["code"]


def _expense(**fields):
    from backend.user_product.models import ExpenseCreateRequest

    return ExpenseCreateRequest(amount=4500, description="Almuerzo", category="comida", entry_date=date(2026, 10, 20), **fields)


def _movement(**fields):
    from backend.user_product.models import MovementUpdateRequest

    return MovementUpdateRequest(transaction_date=date(2026, 10, 21), description="Almuerzo", amount=5000,
                                 transaction_type="expense", category="comida", **fields)


def test_before_the_migration_expenses_still_save_and_only_a_link_answers_503(db):
    from backend.user_product.expense_account import paid_with_options
    from backend.user_product.free_service import list_free_movements
    from backend.user_product.service import create_expense_entry, list_expenses

    assert paid_with_options() == {"status": "ok", "available": False, "items": []}
    create_expense_entry(_expense())  # older apps: no field
    create_expense_entry(_expense(financial_account_id=None))  # nothing to clear yet
    assert _status(lambda: create_expense_entry(_expense(financial_account_id=_ids(db)["Tarjeta A"]))) == (503, "paid_with_unavailable")
    assert _query(db, "SELECT count(*) FROM expenses") == [(2,)]  # the refused one was not saved half-way
    assert all(row["financial_account_id"] is None for row in list_expenses())
    assert all(row["financial_account_id"] is None for row in list_free_movements())


def test_an_expense_says_which_own_account_paid_it_and_keeps_it_unless_told(db):
    from backend.user_product.expense_account import paid_with_options
    from backend.user_product.free_service import list_free_movements, update_free_movement
    from backend.user_product.service import create_expense_entry, list_expenses, update_expense

    with db.cursor() as cur:
        cur.execute(ADD_COLUMN)
    ids = _ids(db)
    options = paid_with_options()
    assert options["available"] is True
    # Only the caller's own active accounts, cards first; never another workspace's.
    assert [item["account_name"] for item in options["items"]] == ["Tarjeta A", "Cuenta A"]

    created = create_expense_entry(_expense(financial_account_id=ids["Tarjeta A"]))
    assert created["financial_account_id"] == ids["Tarjeta A"]
    assert list_expenses()[0]["financial_account_id"] == ids["Tarjeta A"]
    movement = f"expense:{created['id']}"
    assert next(m for m in list_free_movements() if m["movement_id"] == movement)["financial_account_id"] == ids["Tarjeta A"]

    update_free_movement(movement, _movement())  # an older app's edit: the link stays
    assert _query(db, "SELECT amount, financial_account_id FROM expenses") == [(5000, ids["Tarjeta A"])]
    update_free_movement(movement, _movement(financial_account_id=ids["Cuenta A"]))
    assert _query(db, "SELECT financial_account_id FROM expenses") == [(ids["Cuenta A"],)]

    from backend.user_product.models import ExpenseUpdateRequest
    update_expense(created["id"], ExpenseUpdateRequest(amount=4500, category="comida"))  # not sent: kept
    assert _query(db, "SELECT financial_account_id FROM expenses") == [(ids["Cuenta A"],)]
    update_expense(created["id"], ExpenseUpdateRequest(amount=4500, category="comida", financial_account_id=None))  # cleared
    assert _query(db, "SELECT financial_account_id FROM expenses") == [(None,)]


def test_only_the_callers_own_active_accounts_can_pay_an_expense(db):
    from backend.user_product.free_service import update_free_movement
    from backend.user_product.service import create_expense_entry

    with db.cursor() as cur:
        cur.execute(ADD_COLUMN)
    ids = _ids(db)
    assert _status(lambda: create_expense_entry(_expense(financial_account_id=ids["Tarjeta B"]))) == (404, "paid_with_account_not_found")
    assert _status(lambda: create_expense_entry(_expense(financial_account_id=ids["Tarjeta inactiva A"]))) == (404, "paid_with_account_not_found")
    assert _status(lambda: create_expense_entry(_expense(financial_account_id=ids["Tarjeta pendiente A"]))) == (409, "paid_with_not_own")
    assert _query(db, "SELECT count(*) FROM expenses") == [(0,)]  # nothing was saved

    created = create_expense_entry(_expense())
    assert _status(lambda: update_free_movement(f"expense:{created['id']}", _movement(financial_account_id=ids["Tarjeta B"]))) \
        == (404, "paid_with_account_not_found")
    assert _query(db, "SELECT amount, financial_account_id FROM expenses") == [(4500, None)]  # the edit was not applied either


def test_only_an_expense_says_what_paid_it(db):
    from backend.user_product.free_service import update_free_movement

    with db.cursor() as cur:
        cur.execute(ADD_COLUMN)
        cur.execute("INSERT INTO salaries(workspace_id,amount,source) VALUES(%s,100000,'Salario') RETURNING id", (A["workspace"],))
        salary = cur.fetchone()[0]
    from backend.user_product.models import MovementUpdateRequest
    request = MovementUpdateRequest(transaction_date=date(2026, 10, 21), description="Salario", amount=100000,
                                    transaction_type="income", category="Salario", financial_account_id=_ids(db)["Cuenta A"])
    with pytest.raises(HTTPException) as error:
        update_free_movement(f"salary:{salary}", request)
    assert error.value.status_code == 422
