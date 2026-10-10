"""The debt monthly-payment provenance migration (20261010120000) on a real PostgreSQL.

A schema-faithful local copy (the ownership fixture's `debts`, as in production), synthetic rows.
Migration only: preflight, apply, postflight, no historical row marked or rewritten, idempotency,
the SQL "unknown payment" rule matching the Python one, manual rollback and reapply.
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
from backend.user_product.debt_payments import UNKNOWN_PAYMENT_SQL, known_monthly_payment

psycopg2 = pytest.importorskip("psycopg2")

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "database/migrations/20261010120000_debt_monthly_payment_known.sql"
ROLLBACK = ROOT / "database/rollback/20261010120000_debt_monthly_payment_known_rollback.sql"
A = IDENTITIES["A"]
PREFLIGHT = """
SELECT 'missing table' WHERE to_regclass('public.debts') IS NULL
UNION ALL
SELECT 'column already exists: ' || data_type FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'debts' AND column_name = 'monthly_payment_known'
"""
# The postflight in the migration's header (run after COMMIT, as apply_migration's protocol says).
POSTFLIGHT = """
SELECT 'column missing or wrong type' AS problem
WHERE NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'debts' AND column_name = 'monthly_payment_known'
      AND data_type = 'boolean' AND is_nullable = 'YES' AND column_default IS NULL
)
UNION ALL
SELECT 'existing rows were marked: ' || count(*) FROM public.debts WHERE monthly_payment_known IS NOT NULL
HAVING count(*) > 0
"""
# Historical rows as create_user_debt wrote them (no payment given → 0) and real payments.
HISTORICAL = [("Sin cuota", 0), ("Con cuota", 45000)]


def _seed(cur) -> None:
    _seed_identities(cur)
    # The shared fixture mirrors production after this migration; model production before it.
    cur.execute("ALTER TABLE debts DROP COLUMN IF EXISTS monthly_payment_known")
    for name, payment in HISTORICAL:
        cur.execute("INSERT INTO debts(user_id,name,debt_type,total_amount,remaining_amount,monthly_payment,workspace_id)"
                    " VALUES(%s,%s,'loan',1000,800,%s,%s)", (A["users"], name, payment, A["workspace"]))


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
        cur.execute("SELECT name, monthly_payment, monthly_payment_known FROM debts ORDER BY id")
        return cur.fetchall()


def test_preflight_passes_and_the_migration_marks_or_rewrites_no_existing_row(db):
    with db.cursor() as cur:
        cur.execute(PREFLIGHT)
        assert cur.fetchall() == []
        cur.execute("SELECT name, monthly_payment FROM debts ORDER BY id")
        before = cur.fetchall()
    _run(db, MIGRATION)
    with db.cursor() as cur:
        cur.execute(POSTFLIGHT)
        assert cur.fetchall() == []  # the column exists as a nullable boolean and no row was marked
        cur.execute("""SELECT data_type, is_nullable, column_default FROM information_schema.columns
                       WHERE table_name='debts' AND column_name='monthly_payment_known'""")
        assert cur.fetchone() == ("boolean", "YES", None)
        cur.execute("""SELECT is_nullable FROM information_schema.columns WHERE table_name='debts' AND column_name='monthly_payment'""")
        assert cur.fetchone() == ("NO",), "monthly_payment stays NOT NULL: no engine ever reads a NULL"
    after = _rows(db)
    assert [row[:2] for row in after] == before  # no payment rewritten
    assert all(row[2] is None for row in after)  # every historical row stays "read as stored"


def test_it_is_one_transaction_the_apply_tool_accepts():
    from backend.scripts.apply_migration import check_single_transaction
    check_single_transaction(MIGRATION.read_text(encoding="utf-8"))  # BEGIN … COMMIT, nothing after


def test_it_is_idempotent(db):
    _run(db, MIGRATION)
    _run(db, MIGRATION)
    with db.cursor() as cur:
        cur.execute(POSTFLIGHT)
        assert cur.fetchall() == []


def test_the_sql_unknown_rule_matches_the_python_one(db):
    _run(db, MIGRATION)
    with db.cursor() as cur:
        cur.execute("INSERT INTO debts(user_id,name,debt_type,total_amount,remaining_amount,monthly_payment,monthly_payment_known,workspace_id)"
                    " VALUES(%s,'Nueva 0','loan',1000,800,0,TRUE,%s),(%s,'Nueva sin cuota','loan',1000,800,0,FALSE,%s)",
                    (A["users"], A["workspace"], A["users"], A["workspace"]))
        cur.execute(f"SELECT name, {UNKNOWN_PAYMENT_SQL} FROM debts ORDER BY id")
        sql_unknown = dict(cur.fetchall())
    for name, payment, known in _rows(db):
        python_unknown = known_monthly_payment({"monthly_payment": payment, "monthly_payment_known": known}) is None
        assert sql_unknown[name] is python_unknown, name
    # Historical rows are read as stored (a 0 stays 0 until a separate decision); only FALSE is unknown.
    assert sql_unknown == {"Sin cuota": False, "Con cuota": False, "Nueva 0": False, "Nueva sin cuota": True}


def test_manual_rollback_keeps_the_knowledge_and_reapply_works(db):
    _run(db, MIGRATION)
    with db.cursor() as cur:
        cur.execute("UPDATE debts SET monthly_payment_known=TRUE WHERE name='Con cuota'")
    _run(db, ROLLBACK)
    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM information_schema.columns WHERE table_name='debts' AND column_name='monthly_payment_known'")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT monthly_payment, monthly_payment_known FROM debt_monthly_payment_known_rollback_snapshot")
        assert cur.fetchall() == [(45000, True)]
    _run(db, ROLLBACK)  # idempotent
    _run(db, MIGRATION)
    with db.cursor() as cur:
        cur.execute(POSTFLIGHT)
        assert cur.fetchall() == []
