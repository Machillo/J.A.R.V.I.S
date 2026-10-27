"""Migration 20261023120000 (owner_distribution_confirmations) on PostgreSQL, run whole.

Built like production by a non-superuser migrator (the dincr_app environment of
test_dincr_app_role_pg): the ownership guards, the application role and the payroll receipts
migration first, then this one. Checked: its postflight returns no row, it can run twice, the
application role gets exactly SELECT/INSERT/UPDATE with RLS and no DELETE, the public API roles
get nothing, the delete guard keeps every table it protected and adds this one, and the rollback
refuses while confirmations exist. Synthetic data only.
"""
from __future__ import annotations

from pathlib import Path

import pytest

psycopg2 = pytest.importorskip("psycopg2")

from backend.tests.test_dincr_app_role_pg import WS_A, _postflight, env  # noqa: E402,F401  (fixture)

ROOT = Path(__file__).resolve().parents[2] / "database"
PAYROLL = ROOT / "migrations/20261002150000_payroll_receipts.sql"
MIGRATION = ROOT / "migrations/20261023120000_owner_distribution_confirmations.sql"
ROLLBACK = ROOT / "rollback/20261023120000_owner_distribution_confirmations_rollback.sql"


def _guarded(cur) -> set[str]:
    cur.execute("SELECT table_name FROM public.dincr_delete_guard_tables()")
    return {row[0] for row in cur.fetchall()}


@pytest.fixture
def migrated(env):  # noqa: F811
    cur = env["owner"]
    for table in ("salaries", "payroll_events", "bonuses"):
        cur.execute(f"CREATE TABLE IF NOT EXISTS public.{table} (id BIGSERIAL PRIMARY KEY, workspace_id UUID)")
    cur.execute(PAYROLL.read_text(encoding="utf-8"))
    before = _guarded(cur)
    cur.execute(MIGRATION.read_text(encoding="utf-8"))
    return {**env, "before": before}


def test_the_postflight_holds_and_the_migration_can_run_twice(migrated):
    cur = migrated["owner"]
    cur.execute(_postflight(MIGRATION))
    assert cur.fetchall() == []
    cur.execute(MIGRATION.read_text(encoding="utf-8"))
    cur.execute(_postflight(MIGRATION))
    assert cur.fetchall() == []


def test_the_delete_guard_keeps_every_table_and_adds_the_confirmations(migrated):
    assert _guarded(migrated["owner"]) == migrated["before"] | {"owner_distribution_confirmations"}


def test_the_application_role_records_and_reads_but_never_deletes(migrated):
    app = migrated["as_app"]()
    app.execute("""INSERT INTO owner_distribution_confirmations (workspace_id, confirmation_key, amount, items)
                   VALUES (%s, 'confirm-migration-1', 254698, '[]'::jsonb) RETURNING id""", (WS_A,))
    row_id = app.fetchone()[0]
    app.execute("UPDATE owner_distribution_confirmations SET applied='[]'::jsonb WHERE id=%s", (row_id,))
    app.execute("SELECT count(*) FROM owner_distribution_confirmations")
    assert app.fetchone()[0] == 1
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        app.execute("DELETE FROM owner_distribution_confirmations WHERE id=%s", (row_id,))
    with pytest.raises(psycopg2.errors.UniqueViolation):
        app.execute("""INSERT INTO owner_distribution_confirmations (workspace_id, confirmation_key, amount, items)
                       VALUES (%s, 'confirm-migration-1', 1, '[]'::jsonb)""", (WS_A,))
    for bad in ("short", "has spaces in it"):
        with pytest.raises(psycopg2.errors.CheckViolation):
            app.execute("""INSERT INTO owner_distribution_confirmations (workspace_id, confirmation_key, amount, items)
                           VALUES (%s, %s, 1, '[]'::jsonb)""", (WS_A, bad))
    with pytest.raises(psycopg2.errors.CheckViolation):
        app.execute("""INSERT INTO owner_distribution_confirmations (workspace_id, confirmation_key, amount, items)
                       VALUES (%s, 'confirm-migration-2', 0, '[]'::jsonb)""", (WS_A,))


def test_the_public_api_roles_get_nothing(migrated):
    cur = migrated["owner"]
    for role in ("anon", "authenticated"):
        cur.execute("SELECT has_table_privilege(%s, 'public.owner_distribution_confirmations', 'SELECT')", (role,))
        assert cur.fetchone()[0] is False


def test_the_rollback_refuses_while_confirmations_exist(migrated):
    cur = migrated["owner"]
    cur.execute("""INSERT INTO owner_distribution_confirmations (workspace_id, confirmation_key, amount, items)
                   VALUES (%s, 'confirm-migration-3', 1, '[]'::jsonb)""", (WS_A,))
    with pytest.raises(psycopg2.Error) as refused:
        cur.execute(ROLLBACK.read_text(encoding="utf-8"))
    assert refused.value.pgcode == "PR010"
    cur.execute("ROLLBACK")
    cur.execute("SELECT to_regclass('public.owner_distribution_confirmations') IS NOT NULL")
    assert cur.fetchone()[0] is True
