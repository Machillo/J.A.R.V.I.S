"""Migration 20261003120000: the database accepts only 'user' and the single 'owner' (P0.2d).

Real PostgreSQL. The tables start as production has them before the migration (accounts.role
CHECK with 'admin', allowed_users.role without a CHECK); the migration and its rollback are
the reviewed files. Synthetic values only.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg2 = pytest.importorskip("psycopg2")

from backend.scripts.apply_migration import check_single_transaction  # noqa: E402

ROOT = Path(__file__).resolve().parents[2] / "database"
MIGRATION = ROOT / "migrations" / "20261003120000_single_owner_account_roles.sql"
ROLLBACK = ROOT / "rollback" / "20261003120000_single_owner_account_roles_rollback.sql"
BEFORE = """
CREATE TABLE allowed_users (id BIGSERIAL PRIMARY KEY, email TEXT NOT NULL UNIQUE, role TEXT NOT NULL DEFAULT 'user',
                            status TEXT NOT NULL DEFAULT 'pending');
CREATE TABLE accounts (id UUID PRIMARY KEY, legacy_allowed_user_id BIGINT UNIQUE REFERENCES allowed_users(id),
                       primary_email TEXT NOT NULL,
                       role TEXT NOT NULL DEFAULT 'user' CONSTRAINT accounts_role_check CHECK (role IN ('user', 'admin', 'owner')),
                       status TEXT NOT NULL DEFAULT 'active');
"""


@pytest.fixture
def cur(tmp_path):
    server = pgserver.get_server(str(os.environ.get("DINCR_PGSERVER_DIR") or tmp_path / "pg"), cleanup_mode="stop")
    admin = psycopg2.connect(server.get_uri())
    admin.autocommit = True
    name = f"roles_{os.getpid()}_{abs(hash(str(tmp_path))) % 10**8}"
    with admin.cursor() as c:
        c.execute(f"CREATE DATABASE {name}")
    conn = psycopg2.connect(server.get_uri(name))
    conn.autocommit = True
    cursor = conn.cursor()
    cursor.execute(BEFORE)
    yield cursor
    conn.close()
    with admin.cursor() as c:
        c.execute(f"DROP DATABASE {name} WITH (FORCE)")
    admin.close()


def _person(cur, email, role):
    cur.execute("INSERT INTO allowed_users(email, role, status) VALUES (%s, %s, 'active') RETURNING id", (email, role))
    legacy = cur.fetchone()[0]
    cur.execute("INSERT INTO accounts(id, legacy_allowed_user_id, primary_email, role) VALUES (%s, %s, %s, %s)",
                (str(uuid.uuid4()), legacy, email, role))


def _rejected(cur, sql, params):
    with pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(sql, params)


def test_the_files_are_one_transaction_as_apply_migration_requires():
    check_single_transaction(MIGRATION.read_text(encoding="utf-8"))
    check_single_transaction(ROLLBACK.read_text(encoding="utf-8"))


def test_after_the_migration_only_user_and_owner_can_be_stored(cur):
    _person(cur, "user@example.test", "user")
    _person(cur, "owner@example.test", "owner")
    cur.execute(MIGRATION.read_text(encoding="utf-8"))
    for role in ("admin", "viewer", "Admin", "superuser"):
        _rejected(cur, "INSERT INTO allowed_users(email, role) VALUES (%s, %s)", (f"{role}@example.test", role))
        _rejected(cur, "INSERT INTO accounts(id, primary_email, role) VALUES (%s, %s, %s)", (str(uuid.uuid4()), f"{role}@example.test", role))
        _rejected(cur, "UPDATE accounts SET role = %s WHERE primary_email = %s", (role, "user@example.test"))
    _person(cur, "another-user@example.test", "user")
    cur.execute("SELECT role, count(*) FROM accounts GROUP BY role ORDER BY role")
    assert cur.fetchall() == [("owner", 1), ("user", 2)]   # no row rewritten


def test_the_migration_aborts_without_any_change_when_a_legacy_role_exists(cur):
    _person(cur, "user@example.test", "user")
    _person(cur, "legacy@example.test", "admin")
    with pytest.raises(psycopg2.errors.RaiseException) as error:
        cur.execute(MIGRATION.read_text(encoding="utf-8"))
    assert "never convert or promote" in str(error.value)
    cur.execute("ROLLBACK")
    cur.execute("SELECT role FROM accounts WHERE primary_email = 'legacy@example.test'")
    assert cur.fetchone() == ("admin",)                     # not converted, not promoted
    cur.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'accounts_role_check'")
    assert "admin" in cur.fetchone()[0]                     # the old constraint is untouched
    cur.execute("SELECT count(*) FROM pg_constraint WHERE conname = 'allowed_users_role_check'")
    assert cur.fetchone() == (0,)


def test_the_rollback_restores_the_previous_constraints(cur):
    cur.execute(MIGRATION.read_text(encoding="utf-8"))
    cur.execute(ROLLBACK.read_text(encoding="utf-8"))
    _person(cur, "legacy@example.test", "admin")            # accepted again by both tables
    cur.execute("SELECT count(*) FROM pg_constraint WHERE conname = 'allowed_users_role_check'")
    assert cur.fetchone() == (0,)


def test_the_migration_is_repeatable(cur):
    cur.execute(MIGRATION.read_text(encoding="utf-8"))
    cur.execute(MIGRATION.read_text(encoding="utf-8"))      # DROP ... IF EXISTS then ADD: same end state
    cur.execute("SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conname LIKE '%%role_check' ORDER BY 1")
    assert cur.fetchall() == [("accounts_role_check", "CHECK ((role = ANY (ARRAY['user'::text, 'owner'::text])))"),
                              ("allowed_users_role_check", "CHECK ((role = ANY (ARRAY['user'::text, 'owner'::text])))")]
