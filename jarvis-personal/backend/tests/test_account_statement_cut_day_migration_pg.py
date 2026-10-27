"""The card statement cut-day migration (20261026120000) on a real PostgreSQL.

A schema-faithful local `account_balances` (database/schema.sql), synthetic rows. Migration only:
preflight, apply, postflight, no existing row set, the 1–31 CHECK, idempotency, manual rollback
(with its snapshot) and reapply.
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
MIGRATION = ROOT / "database/migrations/20261026120000_account_statement_cut_day.sql"
ROLLBACK = ROOT / "database/rollback/20261026120000_account_statement_cut_day_rollback.sql"
A = IDENTITIES["A"]
PREFLIGHT = """
SELECT 'missing table' WHERE to_regclass('public.account_balances') IS NULL
UNION ALL
SELECT 'column already exists: ' || data_type FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'account_balances' AND column_name = 'statement_cut_day'
"""
# The postflight in the migration's header (run after COMMIT, as apply_migration's protocol says).
POSTFLIGHT = """
SELECT 'column missing or wrong type' AS problem
WHERE NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'account_balances' AND column_name = 'statement_cut_day'
      AND data_type = 'smallint' AND is_nullable = 'YES' AND column_default IS NULL
)
UNION ALL
SELECT 'constraint missing or not validated'
WHERE NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'account_balances_statement_cut_day_check'
                  AND conrelid = 'public.account_balances'::regclass AND convalidated)
UNION ALL
SELECT 'existing rows were set: ' || count(*) FROM public.account_balances WHERE statement_cut_day IS NOT NULL
HAVING count(*) > 0
"""
# Production before the migration (database/schema.sql's account_balances, without the new column).
ACCOUNT_BALANCES = """
CREATE TABLE IF NOT EXISTS account_balances (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL DEFAULT 1,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    account_name TEXT NOT NULL, bank_name TEXT NOT NULL DEFAULT '',
    account_type TEXT NOT NULL DEFAULT 'checking', account_last4 TEXT NOT NULL DEFAULT '',
    currency TEXT NOT NULL DEFAULT 'CRC', current_balance NUMERIC(18,2) NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE(workspace_id, account_name, account_last4)
)
"""
CARDS = [("Tarjeta", "credit_card", "1111", "CRC", 150_000), ("Cuenta", "checking", "2222", "USD", 900)]


def _seed(cur) -> None:
    _seed_identities(cur)
    cur.execute(ACCOUNT_BALANCES)
    for name, kind, last4, currency, balance in CARDS:
        cur.execute("INSERT INTO account_balances(workspace_id,account_name,account_type,account_last4,currency,current_balance)"
                    " VALUES(%s,%s,%s,%s,%s,%s)", (A["workspace"], name, kind, last4, currency, balance))


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
        cur.execute("SELECT account_name, account_type, currency, current_balance FROM account_balances ORDER BY id")
        return cur.fetchall()


def _query(conn, sql: str, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def test_preflight_passes_and_the_migration_sets_no_existing_row(db):
    assert _query(db, PREFLIGHT) == []
    before = _rows(db)
    _run(db, MIGRATION)
    assert _query(db, POSTFLIGHT) == []  # nullable smallint, validated CHECK, no row set
    assert _rows(db) == before  # no balance, type or currency rewritten


def test_the_cut_day_is_one_to_thirty_one_or_unknown(db):
    _run(db, MIGRATION)
    with db.cursor() as cur:
        cur.execute("UPDATE account_balances SET statement_cut_day=21 WHERE account_name='Tarjeta'")
        cur.execute("UPDATE account_balances SET statement_cut_day=NULL WHERE account_name='Tarjeta'")
        for bad in (0, 32, -1):  # autocommit: each refused UPDATE leaves the row as it was
            with pytest.raises(psycopg2.errors.CheckViolation):
                cur.execute("UPDATE account_balances SET statement_cut_day=%s WHERE account_name='Tarjeta'", (bad,))
    assert _query(db, "SELECT statement_cut_day FROM account_balances WHERE account_name='Tarjeta'") == [(None,)]


def test_it_is_one_transaction_the_apply_tool_accepts():
    from backend.scripts.apply_migration import check_single_transaction
    check_single_transaction(MIGRATION.read_text(encoding="utf-8"))  # BEGIN … COMMIT, nothing after


def test_it_is_idempotent(db):
    _run(db, MIGRATION)
    _run(db, MIGRATION)
    assert _query(db, POSTFLIGHT) == []


def test_rollback_keeps_the_declared_days_and_the_migration_reapplies(db):
    _run(db, MIGRATION)
    with db.cursor() as cur:
        cur.execute("UPDATE account_balances SET statement_cut_day=21 WHERE account_name='Tarjeta' RETURNING id")
        card_id = cur.fetchone()[0]
    before = _rows(db)
    _run(db, ROLLBACK)
    assert _query(db, "SELECT column_name FROM information_schema.columns WHERE table_name='account_balances' "
                      "AND column_name='statement_cut_day'") == []
    assert _query(db, "SELECT account_balance_id, statement_cut_day FROM account_statement_cut_day_rollback_snapshot") == [(card_id, 21)]
    assert _rows(db) == before  # nothing else touched
    _run(db, ROLLBACK)  # a second run finds nothing left to drop
    _run(db, MIGRATION)
    assert _query(db, POSTFLIGHT) == []
