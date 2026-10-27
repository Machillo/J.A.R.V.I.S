"""The pending-conversion migration for manual expenses (20261027120000) on a real PostgreSQL.

A schema-faithful local `expenses` (production's columns and its two-shape currency check),
synthetic rows. Migration only: preflight, apply, postflight, no existing row changed, the pending
shape accepted and every incomplete shape refused, idempotency, a rollback that refuses while an
expense is pending, and rollback + reapply when none is.
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
MIGRATION = ROOT / "database/migrations/20261027120000_expense_pending_conversion.sql"
ROLLBACK = ROOT / "database/rollback/20261027120000_expense_pending_conversion_rollback.sql"
A = IDENTITIES["A"]


def _header_query(path: Path, title: str) -> str:
    """The indented SQL under `-- <title>` in a migration header (what the operator runs)."""
    lines, inside = [], False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"-- {title}"):
            inside = True
            continue
        if inside and line.startswith("--   "):
            lines.append(line[5:])
        elif inside and lines:
            break
    assert lines, f"no {title} query in {path.name}"
    return "\n".join(lines)


PREFLIGHT = _header_query(MIGRATION, "Preflight")
POSTFLIGHT = _header_query(MIGRATION, "Postflight")
ROLLBACK_POSTFLIGHT = _header_query(ROLLBACK, "Postflight")

# Production before the migration: amount NOT NULL and the two-shape original currency check.
TABLES = """
ALTER TABLE expenses ADD COLUMN IF NOT EXISTS expense_type TEXT,
    ADD COLUMN IF NOT EXISTS description TEXT, ADD COLUMN IF NOT EXISTS original_amount NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS original_currency TEXT, ADD COLUMN IF NOT EXISTS exchange_rate NUMERIC(14, 6),
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE expenses ALTER COLUMN amount SET NOT NULL;
ALTER TABLE expenses DROP CONSTRAINT IF EXISTS expenses_original_currency_check;
ALTER TABLE expenses ADD CONSTRAINT expenses_original_currency_check CHECK (
    (original_currency IS NULL AND original_amount IS NULL AND exchange_rate IS NULL)
    OR (original_currency IS NOT NULL AND original_amount IS NOT NULL AND exchange_rate IS NOT NULL
        AND original_currency IN ('CRC', 'USD') AND original_amount > 0 AND exchange_rate > 0));
"""
EXPENSES = [("comida", "Almuerzo", 4500, None, None, None), ("ocio", "Suscripción", 6000, 12, "USD", 500)]
INSERT = ("INSERT INTO expenses(workspace_id,category,expense_type,description,amount,original_amount,original_currency,exchange_rate)"
          " VALUES(%s,%s,'variable',%s,%s,%s,%s,%s)")


def _seed(cur) -> None:
    _seed_identities(cur)
    cur.execute(TABLES)
    for category, description, amount, original, currency, rate in EXPENSES:
        cur.execute(INSERT, (A["workspace"], category, description, amount, original, currency, rate))


@pytest.fixture
def db(admin_uri):
    uri, conn, drop = _create_database(admin_uri, _seed)
    try:
        yield conn
    finally:
        drop()


def _run(conn, path: Path) -> None:
    with conn.cursor() as cur:
        cur.execute(path.read_text(encoding="utf-8"))


def _query(conn, sql: str, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params)  # no params: the header queries' LIKE '%…%' stays literal
        return cur.fetchall()


def _rows(conn):
    return _query(conn, "SELECT category, description, amount, original_amount, original_currency, exchange_rate, created_at "
                        "FROM expenses ORDER BY id")


def _pending(conn, description="Hotel", original=120, currency="USD"):
    with conn.cursor() as cur:
        cur.execute(INSERT, (A["workspace"], "viajes", description, None, original, currency, None))


def test_preflight_passes_and_the_migration_changes_no_existing_row(db):
    assert _query(db, PREFLIGHT) == []
    before = _rows(db)
    _run(db, MIGRATION)
    assert _query(db, POSTFLIGHT) == []  # nullable amount, both checks validated, index, nothing pending
    assert _rows(db) == before


def test_preflight_catches_a_table_that_is_not_production_shaped(db):
    with db.cursor() as cur:
        cur.execute("ALTER TABLE expenses ALTER COLUMN amount DROP NOT NULL")
    assert [row[0] for row in _query(db, PREFLIGHT)] == ["amount already nullable"]


def test_a_pending_expense_is_accepted_only_whole(db):
    with pytest.raises(psycopg2.errors.NotNullViolation):  # before the migration: no pending state
        _pending(db)
    _run(db, MIGRATION)
    _pending(db)
    assert _query(db, "SELECT amount, original_amount, original_currency, exchange_rate FROM expenses WHERE description='Hotel'") == [
        (None, 120, "USD", None)]
    refused = [
        (None, None, None, None),     # no amount at all
        (None, 120, None, None),      # no currency
        (None, 0, "USD", None),       # not a positive amount
        (None, 120, "EUR", None),     # unsupported currency
        (None, 120, "USD", 500),      # a rate but no converted amount
        (9000, 120, "USD", None),     # an amount but no rate: never a guessed conversion
    ]
    for amount, original, currency, rate in refused:
        with pytest.raises(psycopg2.errors.CheckViolation):
            with db.cursor() as cur:
                cur.execute(INSERT, (A["workspace"], "viajes", "Inválido", amount, original, currency, rate))
    assert _query(db, "SELECT count(*) FROM expenses WHERE description='Inválido'") == [(0,)]


def test_it_is_one_transaction_the_apply_tool_accepts():
    from backend.scripts.apply_migration import check_single_transaction
    check_single_transaction(MIGRATION.read_text(encoding="utf-8"))  # BEGIN … COMMIT, nothing after


def test_it_is_idempotent(db):
    _run(db, MIGRATION)
    _run(db, MIGRATION)
    assert _query(db, POSTFLIGHT) == []


def test_rollback_refuses_while_an_expense_is_pending_and_changes_nothing(db):
    _run(db, MIGRATION)
    _pending(db)
    before = _rows(db)
    with pytest.raises(psycopg2.errors.RaiseException):
        _run(db, ROLLBACK)
    with db.cursor() as cur:
        cur.execute("ROLLBACK")  # the failed file left its transaction open
    assert _rows(db) == before
    assert _query(db, "SELECT is_nullable FROM information_schema.columns WHERE table_name='expenses' "
                      "AND column_name='amount'") == [("YES",)]  # schema intact
    assert _query(db, "SELECT count(*) FROM pg_constraint WHERE conname='expenses_amount_known_or_pending_check'") == [(1,)]


def test_rollback_restores_the_original_shape_and_the_migration_reapplies(db):
    _run(db, MIGRATION)
    before = _rows(db)
    _run(db, ROLLBACK)
    assert _query(db, ROLLBACK_POSTFLIGHT) == []
    assert _rows(db) == before
    with pytest.raises(psycopg2.errors.NotNullViolation):
        _pending(db)
    _run(db, ROLLBACK)  # a second run finds the original state
    assert _query(db, PREFLIGHT) == []
    _run(db, MIGRATION)
    assert _query(db, POSTFLIGHT) == []
