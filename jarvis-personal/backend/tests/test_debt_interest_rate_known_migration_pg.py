"""The debt interest-rate provenance migration (20261006120000) on a real PostgreSQL.

A schema-faithful local copy (the ownership fixture's `debts`, as in production), synthetic rows.
Migration only: preflight, apply, postflight, no historical row marked, a single transaction
apply_migration.py accepts, idempotency, manual rollback and reapply.
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
MIGRATION = ROOT / "database/migrations/20261006120000_debt_interest_rate_known.sql"
ROLLBACK = ROOT / "database/rollback/20261006120000_debt_interest_rate_known_rollback.sql"
A = IDENTITIES["A"]
PREFLIGHT = """
SELECT 'missing table' WHERE to_regclass('public.debts') IS NULL
UNION ALL
SELECT 'column already exists: ' || data_type FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'debts' AND column_name = 'interest_rate_known'
"""
# The postflight in the migration's header (run after COMMIT, as apply_migration's protocol says).
POSTFLIGHT = """
SELECT 'column missing or wrong type' AS problem
WHERE NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'debts' AND column_name = 'interest_rate_known'
      AND data_type = 'boolean' AND is_nullable = 'YES' AND column_default IS NULL
)
UNION ALL
SELECT 'existing rows were marked: ' || count(*) FROM public.debts WHERE interest_rate_known IS NOT NULL
HAVING count(*) > 0
"""
# Historical rows as create_user_debt wrote them (no rate given → 0) and real rates.
HISTORICAL = [("Sin tasa", "credit_card", 0), ("Tasa cero", "tasa_cero", 0), ("Con tasa", "loan", 24), ("Nula", "other", None)]


def _seed(cur) -> None:
    _seed_identities(cur)
    # The shared fixture mirrors production after this migration; model production before it.
    cur.execute("ALTER TABLE debts DROP COLUMN IF EXISTS interest_rate_known")
    for name, kind, rate in HISTORICAL:
        cur.execute("INSERT INTO debts(user_id,name,debt_type,total_amount,remaining_amount,monthly_payment,interest_rate,workspace_id)"
                    " VALUES(%s,%s,%s,1000,800,100,%s,%s)", (A["users"], name, kind, rate, A["workspace"]))


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
        cur.execute("SELECT name, debt_type, interest_rate, interest_rate_known FROM debts ORDER BY id")
        return cur.fetchall()


def test_preflight_passes_and_the_migration_marks_no_existing_row(db):
    with db.cursor() as cur:
        cur.execute(PREFLIGHT)
        assert cur.fetchall() == []
        cur.execute("SELECT name, debt_type, interest_rate FROM debts ORDER BY id")
        before = cur.fetchall()
    _run(db, MIGRATION)
    with db.cursor() as cur:
        cur.execute(POSTFLIGHT)
        assert cur.fetchall() == []  # the column exists as a nullable boolean and no row was marked
    after = _rows(db)
    assert [row[:3] for row in after] == before  # no rate rewritten
    assert all(row[3] is None for row in after)  # every historical row stays "not verified"
    with db.cursor() as cur:
        cur.execute("""SELECT data_type, is_nullable, column_default FROM information_schema.columns
                       WHERE table_name='debts' AND column_name='interest_rate_known'""")
        assert cur.fetchone() == ("boolean", "YES", None)


def test_it_is_one_transaction_the_apply_tool_accepts():
    from backend.scripts.apply_migration import check_single_transaction
    check_single_transaction(MIGRATION.read_text(encoding="utf-8"))  # BEGIN … COMMIT, nothing after


def test_it_is_idempotent(db):
    _run(db, MIGRATION)
    _run(db, MIGRATION)
    with db.cursor() as cur:
        cur.execute(POSTFLIGHT)
        assert cur.fetchall() == []


def test_manual_rollback_keeps_the_knowledge_and_reapply_works(db):
    _run(db, MIGRATION)
    with db.cursor() as cur:
        cur.execute("UPDATE debts SET interest_rate_known=TRUE WHERE name='Con tasa'")
    _run(db, ROLLBACK)
    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM information_schema.columns WHERE table_name='debts' AND column_name='interest_rate_known'")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT interest_rate, interest_rate_known FROM debt_interest_rate_known_rollback_snapshot")
        assert cur.fetchall() == [(24, True)]
    _run(db, ROLLBACK)  # idempotent
    _run(db, MIGRATION)
    with db.cursor() as cur:
        cur.execute(POSTFLIGHT)
        assert cur.fetchall() == []
