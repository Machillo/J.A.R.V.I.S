"""The Owner category layer follows the stored Owner identity, proven on a real PostgreSQL (P0.1).

`owner_role.is_verified_owner_account` decides, without a session, whether the account and
workspace whose mail is processed (background Gmail sync, push) are the enabled Owner's. The
tables are created from `database/schema.sql`, so the query runs against the real columns.
Synthetic values only.
"""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg2 = pytest.importorskip("psycopg2")
from psycopg2.extras import RealDictCursor  # noqa: E402

from backend.auth.owner_role import is_verified_owner_account  # noqa: E402
from backend.finance.category_catalog import normalize_category, owner_account_context  # noqa: E402

SCHEMA = (Path(__file__).resolve().parents[2] / "database" / "schema.sql").read_text(encoding="utf-8")
OWNER_EMAIL = "owner@example.test"


def _table(name: str) -> str:
    match = re.search(rf"CREATE TABLE IF NOT EXISTS {name} \(.*?\n\);", SCHEMA, re.S)
    assert match, f"{name} moved in schema.sql"
    return match.group(0)


@pytest.fixture
def cur(tmp_path, monkeypatch):
    server = pgserver.get_server(str(os.environ.get("DINCR_PGSERVER_DIR") or tmp_path / "pg"), cleanup_mode="stop")
    admin = psycopg2.connect(server.get_uri())
    admin.autocommit = True
    name = f"ownercat_{os.getpid()}_{abs(hash(str(tmp_path))) % 10**8}"
    with admin.cursor() as c:
        c.execute(f"CREATE DATABASE {name}")
    conn = psycopg2.connect(server.get_uri(name), cursor_factory=RealDictCursor)
    conn.autocommit = True
    cursor = conn.cursor()
    for table in ("allowed_users", "accounts", "workspaces"):
        cursor.execute(_table(table))
    monkeypatch.setenv("OWNER_EMAILS", OWNER_EMAIL)
    yield cursor
    conn.close()
    with admin.cursor() as c:
        c.execute(f"DROP DATABASE {name} WITH (FORCE)")
    admin.close()


class _Conn:
    """The application's connection shape: execute(...) returns a cursor."""

    def __init__(self, cursor):
        self.cursor = cursor

    def execute(self, query, params=()):
        self.cursor.execute(query, params)
        return self.cursor


def _person(cur, email, *, allowed_role="user", account_role="user", status="active", account_status="active"):
    cur.execute("INSERT INTO allowed_users(email, role, status) VALUES (%s, %s, %s) RETURNING id", (email, allowed_role, status))
    legacy = cur.fetchone()["id"]
    account = str(uuid.uuid4())
    cur.execute("INSERT INTO accounts(id, legacy_allowed_user_id, primary_email, role, status) VALUES (%s, %s, %s, %s, %s)",
                (account, legacy, email, account_role, account_status))
    workspace = str(uuid.uuid4())
    cur.execute("INSERT INTO workspaces(id, workspace_key, owner_account_id, name) VALUES (%s, %s, %s, 'Personal')",
                (workspace, f"ws-{workspace}", account))
    return account, workspace


def test_the_enabled_owners_own_account_and_workspace_qualify(cur):
    account, workspace = _person(cur, OWNER_EMAIL, allowed_role="owner", account_role="owner")
    user_account, user_workspace = _person(cur, "persona@example.test")
    conn = _Conn(cur)
    assert is_verified_owner_account(conn, account, workspace) is True
    assert owner_account_context(conn, account, workspace) is True
    assert normalize_category("papá", "expense", owner=owner_account_context(conn, account, workspace)) == "Familiar"
    assert owner_account_context(conn, user_account, user_workspace) is False
    assert normalize_category("papá", "expense", owner=owner_account_context(conn, user_account, user_workspace)) == "Sin categoría"


def test_the_owner_account_with_another_accounts_workspace_does_not_qualify(cur):
    account, _ = _person(cur, OWNER_EMAIL, allowed_role="owner", account_role="owner")
    _, user_workspace = _person(cur, "persona@example.test")
    assert is_verified_owner_account(_Conn(cur), account, user_workspace) is False


@pytest.mark.parametrize("allowed_role, account_role, status", [
    ("user", "owner", "active"),      # one stored role alone is not enough
    ("owner", "user", "active"),
    ("owner", "owner", "pending"),    # an inactive Owner
])
def test_both_stored_roles_and_an_active_status_are_required(cur, allowed_role, account_role, status):
    account, workspace = _person(cur, OWNER_EMAIL, allowed_role=allowed_role, account_role=account_role, status=status)
    assert is_verified_owner_account(_Conn(cur), account, workspace) is False


def test_the_database_refuses_a_legacy_admin_role(cur):
    # P0.2d migration: an account or allowlist row can only be "user" or "owner".
    for allowed_role, account_role in (("owner", "admin"), ("admin", "user")):
        with pytest.raises(psycopg2.errors.CheckViolation):
            _person(cur, f"{allowed_role}-{account_role}@example.test", allowed_role=allowed_role, account_role=account_role)


def test_the_deployment_allowlist_is_required(cur, monkeypatch):
    account, workspace = _person(cur, OWNER_EMAIL, allowed_role="owner", account_role="owner")
    monkeypatch.setenv("OWNER_EMAILS", "someone-else@example.test")
    assert is_verified_owner_account(_Conn(cur), account, workspace) is False
    monkeypatch.setenv("OWNER_EMAILS", "")
    assert is_verified_owner_account(_Conn(cur), account, workspace) is False


def test_a_listed_user_is_not_the_owner(cur, monkeypatch):
    account, workspace = _person(cur, "persona@example.test")
    monkeypatch.setenv("OWNER_EMAILS", f"{OWNER_EMAIL},persona@example.test")
    assert is_verified_owner_account(_Conn(cur), account, workspace) is False


def test_two_enabled_owners_fail_closed(cur, monkeypatch):
    account, workspace = _person(cur, OWNER_EMAIL, allowed_role="owner", account_role="owner")
    _person(cur, "second@example.test", allowed_role="owner", account_role="owner")
    monkeypatch.setenv("OWNER_EMAILS", f"{OWNER_EMAIL},second@example.test")
    assert is_verified_owner_account(_Conn(cur), account, workspace) is False


@pytest.mark.parametrize("account, workspace", [(None, "w"), ("a", None), ("", ""), (None, None)])
def test_missing_identity_is_neutral_without_a_query(account, workspace):
    class _NoSql:
        def execute(self, *_a):
            raise AssertionError("no query without an identity")

    assert is_verified_owner_account(_NoSql(), account, workspace) is False


def test_a_blocked_owner_account_does_not_qualify(cur):
    account, workspace = _person(cur, OWNER_EMAIL, allowed_role="owner", account_role="owner", account_status="blocked")
    assert is_verified_owner_account(_Conn(cur), account, workspace) is False


def test_an_owner_role_account_with_another_email_does_not_qualify(cur):
    _person(cur, OWNER_EMAIL, allowed_role="owner", account_role="owner")
    other, other_workspace = _person(cur, "persona@example.test", account_role="owner")
    assert is_verified_owner_account(_Conn(cur), other, other_workspace) is False

