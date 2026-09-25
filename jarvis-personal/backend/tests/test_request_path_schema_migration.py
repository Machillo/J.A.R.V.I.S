"""The request-path schema migration fits the reviewed-migration runner (no database needed)."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.scripts import apply_migration

DATABASE = Path(__file__).resolve().parents[2] / "database"
MIGRATION = DATABASE / "migrations" / "20260925130000_request_path_schema.sql"


def test_the_migration_is_one_transaction_the_runner_accepts():
    sql = MIGRATION.read_text(encoding="utf-8")
    apply_migration.check_single_transaction(sql)
    statements = apply_migration.statements(sql)
    assert statements[1:3] == ["SET LOCAL lock_timeout = '5s'", "SET LOCAL statement_timeout = '2min'"]
    assert "%" not in sql  # the runner executes the text without parameters


def test_the_migration_never_destroys_or_rewrites():
    for statement in apply_migration.statements(MIGRATION.read_text(encoding="utf-8")):
        upper = statement.upper()
        assert not upper.startswith(("DROP", "DELETE", "UPDATE", "TRUNCATE", "GRANT", "ALTER DEFAULT")), statement
        assert "SECURITY DEFINER" not in upper and "DO UPDATE" not in upper, statement


def test_the_store_lock_is_taken_last():
    statements = apply_migration.statements(MIGRATION.read_text(encoding="utf-8"))
    first_store = next(i for i, s in enumerate(statements) if "store_subscription" in s)
    assert all("store_subscription" in s for s in statements[first_store:-1])
    # Waiting for that lock while holding the Basic tables' locks on accounts etc.
    # blocks logins, so the wait is short.
    assert statements[first_store - 1] == "SET LOCAL lock_timeout = '1s'"


@pytest.mark.parametrize("name", ["20260909_finva_basic_01_07.sql", "20260909_finva_free_01_07.sql"])
def test_superseded_migrations_cannot_be_applied(tmp_path, name):
    superseded = DATABASE / "superseded" / name
    assert not (DATABASE / "migrations" / name).exists()
    assert superseded.read_text(encoding="utf-8").startswith("-- SUPERSEDED")
    with pytest.raises(SystemExit, match="only files in database/migrations"):
        apply_migration.main(["--file", str(superseded), "--backup-dir", str(tmp_path), "--confirm", name])


def test_no_migration_still_creates_a_gated_table_outside_this_one():
    # These tables are created only here, behind the replay precondition and closed
    # to the Data API; any other applicable file creating them bypasses both.
    gated = ("finva_budget_items", "finva_recurring_items", "finva_goal_contributions")
    for path in (DATABASE / "migrations").glob("*.sql"):
        if path == MIGRATION:
            continue
        for statement in apply_migration.statements(path.read_text(encoding="utf-8")):
            assert not any(f"CREATE TABLE IF NOT EXISTS {table}" in statement or f"CREATE TABLE {table}" in statement
                           for table in gated), path.name
