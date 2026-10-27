"""The "paid with" account migration for manual expenses (20261026130000) on a real PostgreSQL.

A schema-faithful local `expenses` and `account_balances` (database/schema.sql), synthetic rows.
Migration only: preflight, apply, postflight, no existing row linked, the FK (and its ON DELETE SET
NULL), idempotency, manual rollback (with its snapshot) and reapply.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.tests.test_financial_ownership_integrity_pg import (  # noqa: F401  (admin_uri is a fixture)
    IDENTITIES,
    _create_database,
    _seed_identities,
    admin_uri,
)

psycopg2 = pytest.importorskip("psycopg2")

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "database/migrations/20261026130000_expense_paid_with_account.sql"
ROLLBACK = ROOT / "database/rollback/20261026130000_expense_paid_with_account_rollback.sql"
A = IDENTITIES["A"]
PREFLIGHT = """
SELECT 'missing table: ' || t FROM unnest(ARRAY['public.expenses', 'public.account_balances']) AS t
WHERE to_regclass(t) IS NULL
UNION ALL
SELECT 'column already exists: ' || data_type FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'expenses' AND column_name = 'financial_account_id'
"""
# The postflight in the migration's header (run after COMMIT, as apply_migration's protocol says).
POSTFLIGHT = """
SELECT 'column missing or wrong type' AS problem
WHERE NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'expenses' AND column_name = 'financial_account_id'
      AND data_type = 'bigint' AND is_nullable = 'YES' AND column_default IS NULL
)
UNION ALL
SELECT 'foreign key missing or not validated'
WHERE NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'expenses_financial_account_id_fkey'
                  AND conrelid = 'public.expenses'::regclass AND contype = 'f' AND convalidated
                  AND confrelid = 'public.account_balances'::regclass AND confdeltype = 'n')
UNION ALL
SELECT 'index missing' WHERE to_regclass('public.idx_expenses_financial_account') IS NULL
UNION ALL
SELECT 'existing rows were linked: ' || count(*) FROM public.expenses WHERE financial_account_id IS NOT NULL
HAVING count(*) > 0
"""
# Production before the migration (database/schema.sql, without the new column).
TABLES = """
CREATE TABLE IF NOT EXISTS account_balances (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL DEFAULT 1,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    account_name TEXT NOT NULL, account_type TEXT NOT NULL DEFAULT 'checking',
    account_last4 TEXT NOT NULL DEFAULT '', currency TEXT NOT NULL DEFAULT 'CRC',
    UNIQUE(workspace_id, account_name, account_last4)
);
-- The test baseline already has a narrower `expenses`: give it production's other columns.
ALTER TABLE expenses ADD COLUMN IF NOT EXISTS expense_type TEXT,
    ADD COLUMN IF NOT EXISTS description TEXT, ADD COLUMN IF NOT EXISTS original_amount NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS original_currency TEXT, ADD COLUMN IF NOT EXISTS exchange_rate NUMERIC(12, 6),
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
"""
EXPENSES = [("comida", "variable", "Almuerzo", 4500, None, None), ("ocio", "variable", "Suscripción", 6000, 12, "USD")]


def _seed(cur) -> None:
    _seed_identities(cur)
    cur.execute(TABLES)
    cur.execute("INSERT INTO account_balances(workspace_id,account_name,account_type,account_last4) VALUES(%s,'Tarjeta','credit_card','1111')",
                (A["workspace"],))
    for category, kind, description, amount, original, currency in EXPENSES:
        cur.execute("INSERT INTO expenses(workspace_id,category,expense_type,description,amount,original_amount,original_currency)"
                    " VALUES(%s,%s,%s,%s,%s,%s,%s)", (A["workspace"], category, kind, description, amount, original, currency))


@pytest.fixture
def db(admin_uri):
    uri, conn, drop = _create_database(admin_uri, _seed)
    try:
        yield conn
    finally:
        drop()


def _run(conn, path: Path):
    with conn.cursor() as cur:
        cur.execute(path.read_text(encoding="utf-8"))
        return cur.fetchall() if cur.description else []


def _rows(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT category, description, amount, original_amount, original_currency, created_at FROM expenses ORDER BY id")
        return cur.fetchall()


def _query(conn, sql: str, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def test_preflight_passes_and_the_migration_links_no_existing_row(db):
    assert _query(db, PREFLIGHT) == []
    before = _rows(db)
    _run(db, MIGRATION)
    assert _query(db, POSTFLIGHT) == []  # nullable bigint, validated FK, index, no row linked
    assert _rows(db) == before  # no amount, currency or date rewritten


def test_the_link_must_be_a_real_account_and_is_cleared_when_it_goes(db):
    _run(db, MIGRATION)
    card = _query(db, "SELECT id FROM account_balances WHERE account_name='Tarjeta'")[0][0]
    with db.cursor() as cur:
        cur.execute("UPDATE expenses SET financial_account_id=%s WHERE description='Almuerzo'", (card,))
        with pytest.raises(psycopg2.errors.ForeignKeyViolation):  # autocommit: the row stays as it was
            cur.execute("UPDATE expenses SET financial_account_id=%s WHERE description='Suscripción'", (card + 999,))
        cur.execute("DELETE FROM account_balances WHERE id=%s", (card,))
    # The expense stays an expense; only its link is cleared.
    assert _query(db, "SELECT description, amount, financial_account_id FROM expenses ORDER BY id") == [
        ("Almuerzo", 4500, None), ("Suscripción", 6000, None)]


def test_it_is_one_transaction_the_apply_tool_accepts():
    from backend.scripts.apply_migration import check_single_transaction
    check_single_transaction(MIGRATION.read_text(encoding="utf-8"))  # BEGIN … COMMIT, nothing after


def test_it_is_idempotent(db):
    _run(db, MIGRATION)
    _run(db, MIGRATION)
    assert _query(db, POSTFLIGHT) == []


def test_rollback_keeps_the_declared_links_and_the_migration_reapplies(db):
    _run(db, MIGRATION)
    card = _query(db, "SELECT id FROM account_balances WHERE account_name='Tarjeta'")[0][0]
    with db.cursor() as cur:
        cur.execute("UPDATE expenses SET financial_account_id=%s WHERE description='Almuerzo' RETURNING id", (card,))
        expense_id = cur.fetchone()[0]
    before = _rows(db)
    _run(db, ROLLBACK)
    assert _query(db, "SELECT column_name FROM information_schema.columns WHERE table_name='expenses' "
                      "AND column_name='financial_account_id'") == []
    assert _query(db, "SELECT expense_id, financial_account_id FROM expense_paid_with_rollback_snapshot") == [(expense_id, card)]
    assert _rows(db) == before  # nothing else touched
    _run(db, ROLLBACK)  # a second run finds nothing left to drop
    _run(db, MIGRATION)
    assert _query(db, POSTFLIGHT) == []
