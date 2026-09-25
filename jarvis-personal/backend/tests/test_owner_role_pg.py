"""The Owner role is explicit: set only by the reviewed command, gated by OWNER_EMAILS (real PostgreSQL)."""
from __future__ import annotations

import os
import uuid

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg2 = pytest.importorskip("psycopg2")

from backend.auth import owner_bridge  # noqa: E402
from backend.core import database  # noqa: E402
from backend.scripts import set_owner_role  # noqa: E402

EMAIL = "owner@example.test"


@pytest.fixture
def db(tmp_path, monkeypatch):
    server = pgserver.get_server(str(os.environ.get("DINCR_PGSERVER_DIR") or tmp_path / "pg"), cleanup_mode="stop")
    admin = psycopg2.connect(server.get_uri())
    admin.autocommit = True
    name = f"owner_{os.getpid()}_{abs(hash(str(tmp_path))) % 10**8}"
    with admin.cursor() as c:
        c.execute(f"CREATE DATABASE {name}")
    uri = server.get_uri(name)
    conn = psycopg2.connect(uri)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("""CREATE TABLE allowed_users (id BIGSERIAL PRIMARY KEY, email TEXT, role TEXT, status TEXT, supabase_user_id TEXT);
                   CREATE TABLE accounts (id UUID PRIMARY KEY, legacy_allowed_user_id BIGINT, role TEXT, updated_at TIMESTAMPTZ)""")
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    yield cur
    conn.close()
    with admin.cursor() as c:
        c.execute(f"DROP DATABASE {name} WITH (FORCE)")
    admin.close()


def _person(cur, email=EMAIL, role="user", status="active"):
    auth_id = str(uuid.uuid4())
    cur.execute("INSERT INTO allowed_users(email, role, status, supabase_user_id) VALUES (%s, %s, %s, %s) RETURNING id",
                (email, role, status, auth_id))
    legacy = cur.fetchone()[0]
    cur.execute("INSERT INTO accounts VALUES (%s, %s, %s, NOW())", (str(uuid.uuid4()), legacy, role))
    return legacy, auth_id


def _roles(cur, legacy):
    cur.execute("SELECT a.role, c.role FROM allowed_users a JOIN accounts c ON c.legacy_allowed_user_id = a.id WHERE a.id = %s",
                (legacy,))
    return cur.fetchone()


def _run(monkeypatch, *args):
    monkeypatch.setenv("TARGET_EMAIL", EMAIL)
    return set_owner_role.main(["--email-from-env", "TARGET_EMAIL", *args])


def test_a_grant_needs_the_allowlist_and_changes_both_tables_only_with_apply(db, monkeypatch):
    legacy, _ = _person(db)
    monkeypatch.setenv("OWNER_EMAILS", "")
    with pytest.raises(SystemExit):
        _run(monkeypatch, "--grant", "--apply")
    monkeypatch.setenv("OWNER_EMAILS", EMAIL)
    _run(monkeypatch, "--grant")  # dry run
    assert _roles(db, legacy) == ("user", "user")
    _run(monkeypatch, "--grant", "--apply")
    assert _roles(db, legacy) == ("owner", "owner")
    _run(monkeypatch, "--revoke", "--apply")
    assert _roles(db, legacy) == ("user", "user")


def test_disagreeing_tables_change_nothing(db, monkeypatch):
    legacy, _ = _person(db)
    db.execute("UPDATE accounts SET role = 'owner' WHERE legacy_allowed_user_id = %s", (legacy,))
    monkeypatch.setenv("OWNER_EMAILS", EMAIL)
    with pytest.raises(SystemExit):
        _run(monkeypatch, "--grant", "--apply")
    assert _roles(db, legacy) == ("user", "owner")


@pytest.mark.parametrize(("configured", "allowed"), [(EMAIL, True), ("", False), ("other@example.test", False)])
def test_the_owner_bridge_honors_the_allowlist(db, monkeypatch, configured, allowed):
    _, auth_id = _person(db, role="owner")
    monkeypatch.setenv("OWNER_EMAILS", configured)
    if allowed:
        assert owner_bridge.verify_personal_owner(auth_id)["role"] == "owner"
    else:
        with pytest.raises(Exception) as refused:
            owner_bridge.verify_personal_owner(auth_id)
        assert getattr(refused.value, "status_code", None) == 403
    assert _roles(db, 1)[0] == "owner"  # never demoted
