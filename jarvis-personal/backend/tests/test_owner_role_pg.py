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
                   CREATE TABLE accounts (id UUID PRIMARY KEY, legacy_allowed_user_id BIGINT, role TEXT, updated_at TIMESTAMPTZ,
                                          supabase_user_id UUID, primary_email TEXT);
                   CREATE TABLE plans (id BIGSERIAL PRIMARY KEY, code TEXT UNIQUE);
                   INSERT INTO plans(code) VALUES ('free'), ('vip');
                   CREATE TABLE account_subscriptions (id BIGSERIAL PRIMARY KEY, account_id UUID UNIQUE, plan_id BIGINT, status TEXT,
                       access_source TEXT, expires_at TIMESTAMPTZ, courtesy_note TEXT, granted_by UUID, granted_at TIMESTAMPTZ,
                       updated_at TIMESTAMPTZ)""")
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    yield cur
    conn.close()
    with admin.cursor() as c:
        c.execute(f"DROP DATABASE {name} WITH (FORCE)")
    admin.close()


def _person(cur, email=EMAIL, role="user", status="active", plan="free", source="self_service"):
    auth_id = str(uuid.uuid4())
    cur.execute("INSERT INTO allowed_users(email, role, status, supabase_user_id) VALUES (%s, %s, %s, %s) RETURNING id",
                (email, role, status, auth_id))
    legacy = cur.fetchone()[0]
    account = str(uuid.uuid4())
    cur.execute("INSERT INTO accounts VALUES (%s, %s, %s, NOW(), %s, %s)", (account, legacy, role, auth_id, email))
    cur.execute("""INSERT INTO account_subscriptions(account_id, plan_id, status, access_source)
                   SELECT %s, id, 'active', %s FROM plans WHERE code = %s""", (account, source, plan))
    return legacy, auth_id


def _plan(cur, legacy):
    cur.execute("""SELECT p.code, s.access_source FROM account_subscriptions s JOIN plans p ON p.id = s.plan_id
                   JOIN accounts a ON a.id = s.account_id WHERE a.legacy_allowed_user_id = %s""", (legacy,))
    return cur.fetchone()


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
    assert _roles(db, legacy) == ("owner", "owner") and _plan(db, legacy) == ("vip", "owner")
    _run(monkeypatch, "--revoke", "--apply")
    assert _roles(db, legacy) == ("user", "user") and _plan(db, legacy) == ("free", "self_service")  # no eternal VIP


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
    db.execute("SELECT role FROM allowed_users WHERE supabase_user_id = %s", (auth_id,))
    assert db.fetchone() == ("owner",)  # never demoted


def test_a_revoke_works_for_a_blocked_owner_and_a_grant_needs_a_bound_identity(db, monkeypatch):
    legacy, _ = _person(db, role="owner", status="blocked", plan="vip", source="owner")
    monkeypatch.setenv("OWNER_EMAILS", "")
    _run(monkeypatch, "--revoke", "--apply")
    assert _roles(db, legacy) == ("user", "user") and _plan(db, legacy) == ("free", "self_service")
    unbound, _ = _person(db, email="other@example.test")
    db.execute("UPDATE accounts SET supabase_user_id = NULL WHERE legacy_allowed_user_id = %s", (unbound,))
    monkeypatch.setenv("OWNER_EMAILS", "other@example.test")
    monkeypatch.setenv("TARGET_EMAIL", "other@example.test")
    with pytest.raises(SystemExit):
        set_owner_role.main(["--email-from-env", "TARGET_EMAIL", "--grant", "--apply"])
    assert _roles(db, unbound) == ("user", "user")


@pytest.mark.parametrize(("listed", "expected"), [
    ("owner@example.test", "owner@example.test"),       # the stored Owner, listed
    ("user@example.test,owner@example.test", "owner@example.test"),  # a listed User never qualifies
    ("user@example.test", None),                        # only a User listed: fail closed
    ("", None),
])
def test_background_owner_integrations_need_both_keys(db, monkeypatch, listed, expected):
    from backend.auth.owner_role import enabled_owner_email

    _person(db, role="owner", plan="vip", source="owner")
    _person(db, email="user@example.test")
    monkeypatch.setenv("OWNER_EMAILS", listed)
    with database.get_connection() as conn:
        if expected:
            assert enabled_owner_email(conn) == expected
        else:
            with pytest.raises(RuntimeError):
                enabled_owner_email(conn)
