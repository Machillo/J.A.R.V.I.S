"""Mailbox reading is limited to the verified Owner during the launch, on a real PostgreSQL.

Launch decision (2026-10-22): while DINCR's Google OAuth app stays in testing, only the verified
Owner connects and reads a mailbox. Everyone else keeps what was already imported, can review it
and can always disconnect (revoke + delete the token). Pausing reading never revokes,
disconnects or deletes anything by itself: only a lapsed plan ends a stored authorization.

Accounts, workspaces and allowed_users come from database/schema.sql; mail tokens go through
the real account-bound Vault boundary (20260926149000). Synthetic values only.
"""
from __future__ import annotations

import base64
import json
import os
import re
import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException

pgserver = pytest.importorskip("pgserver")
psycopg2 = pytest.importorskip("psycopg2")

from backend.auth.current_user import reset_current_user, set_current_user  # noqa: E402
from backend.core import feature_flags  # noqa: E402
from backend.core.database import get_connection  # noqa: E402
from backend.user_product import gmail_service, routes  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = (ROOT / "database" / "schema.sql").read_text(encoding="utf-8")
VAULT_STUB = Path(__file__).resolve().parent / "fixtures/vault_stub.sql"
MAIL_SECRET_BOUNDARY = ROOT / "database/migrations/20260926149000_mail_secret_boundary.sql"
OWNER_EMAIL = "owner@example.test"
CRON_SECRET = "cron-secret-sintetico"
PUSH_TOKEN = "push-token-sintetico"


def _table(name: str) -> str:
    match = re.search(rf"CREATE TABLE IF NOT EXISTS {name} \(.*?\n\);", SCHEMA, re.S)
    assert match, f"{name} moved in schema.sql"
    return match.group(0)


@pytest.fixture
def pg(tmp_path, monkeypatch):
    from backend.core import database

    server = pgserver.get_server(str(os.environ.get("DINCR_PGSERVER_DIR") or tmp_path / "pg"), cleanup_mode="stop")
    admin = psycopg2.connect(server.get_uri())
    admin.autocommit = True
    name = f"mailowner_{os.getpid()}_{abs(hash(str(tmp_path))) % 10**8}"
    with admin.cursor() as c:
        c.execute(f"CREATE DATABASE {name}")
    uri = server.get_uri(name)
    conn = psycopg2.connect(uri)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(VAULT_STUB.read_text(encoding="utf-8"))
    for table in ("allowed_users", "accounts", "workspaces"):
        cur.execute(_table(table))
    cur.execute(MAIL_SECRET_BOUNDARY.read_text(encoding="utf-8"))
    cur.execute("""CREATE TABLE plans (id BIGSERIAL PRIMARY KEY, code TEXT UNIQUE);
                   INSERT INTO plans(code) VALUES ('free'), ('basic'), ('vip');
                   CREATE TABLE account_subscriptions (account_id UUID PRIMARY KEY, plan_id BIGINT, status TEXT,
                       access_source TEXT, expires_at TIMESTAMPTZ);
                   CREATE TABLE finva_gmail_connections (id BIGSERIAL PRIMARY KEY, account_id UUID, workspace_id UUID,
                       google_email TEXT, status TEXT, refresh_token_secret_id UUID, granted_scopes TEXT[],
                       history_id TEXT, watch_expiration TIMESTAMPTZ, initial_scan_page_token TEXT,
                       last_error TEXT, updated_at TIMESTAMPTZ)""")
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    monkeypatch.setenv("OWNER_EMAILS", OWNER_EMAIL)
    monkeypatch.setenv("FINVA_GMAIL_CRON_SECRET", CRON_SECRET)
    monkeypatch.setenv("FINVA_GMAIL_PUBSUB_VERIFICATION_TOKEN", PUSH_TOKEN)
    feature_flags.clear_feature_flag_cache()
    yield cur
    feature_flags.clear_feature_flag_cache()
    conn.close()
    with admin.cursor() as c:
        c.execute(f"DROP DATABASE {name} WITH (FORCE)")
    admin.close()


def person(cur, email, *, role="user", status="active", plan="vip", source="courtesy",
           expires="NOW() + interval '30 days'", mailbox=True):
    """One account with its workspace, subscription and (optionally) an active Gmail connection."""
    cur.execute("INSERT INTO allowed_users(email, role, status) VALUES (%s, %s, %s) RETURNING id", (email, role, status))
    legacy = cur.fetchone()[0]
    account, workspace = str(uuid.uuid4()), str(uuid.uuid4())
    cur.execute("INSERT INTO accounts(id, legacy_allowed_user_id, primary_email, role, status) VALUES (%s,%s,%s,%s,%s)",
                (account, legacy, email, role, status))
    cur.execute("INSERT INTO workspaces(id, workspace_key, owner_account_id, name) VALUES (%s,%s,%s,'Personal')",
                (workspace, f"ws-{workspace}", account))
    cur.execute(f"INSERT INTO account_subscriptions SELECT %s, id, 'active', %s, {expires} FROM plans WHERE code=%s",
                (account, source, plan))
    connection = secret = None
    if mailbox:
        secret = str(uuid.uuid4())
        cur.execute("INSERT INTO vault.secrets(id, secret, description) VALUES (%s, %s, %s)",
                    (secret, f"token-{email}", f"DINCR Gmail refresh token for account {account}"))
        cur.execute("""INSERT INTO finva_gmail_connections(account_id, workspace_id, google_email, status,
                           refresh_token_secret_id, granted_scopes)
                       VALUES (%s,%s,%s,'active',%s,%s) RETURNING id""",
                    (account, workspace, email, secret, [gmail_service.GMAIL_SCOPE]))
        connection = cur.fetchone()[0]
    return {"account": account, "workspace": workspace, "email": email, "role": role,
            "connection": connection, "secret": secret}


def allowed(who) -> bool:
    with get_connection() as conn:
        return gmail_service.mail_reading_allowed(conn, who["account"], who["workspace"])


def session(who, role=None):
    return set_current_user({"id": 1, "account_id": who["account"], "workspace_id": who["workspace"],
                             "role": role or ("owner" if who["role"] == "owner" else "user")})


def row(cur, connection_id):
    cur.execute("SELECT status, last_error FROM finva_gmail_connections WHERE id=%s", (connection_id,))
    return cur.fetchone()


def secrets_left(cur):
    cur.execute("SELECT id::text FROM vault.secrets ORDER BY id")
    return {r[0] for r in cur.fetchall()}


# --- who may read a mailbox ------------------------------------------------------------------------

def test_only_the_verified_owner_may_read_a_mailbox(pg):
    owner = person(pg, OWNER_EMAIL, role="owner", source="owner", expires="NULL")
    vip = person(pg, "vip@example.test")
    free = person(pg, "free@example.test", plan="free", source="self_service", expires="NULL")
    assert allowed(owner) is True
    assert allowed(vip) is False  # a VIP (launch promotion) no longer reads mail
    assert allowed(free) is False


def test_an_owner_outside_the_deployment_allowlist_is_not_authorized(pg, monkeypatch):
    owner = person(pg, OWNER_EMAIL, role="owner", source="owner", expires="NULL")
    monkeypatch.setenv("OWNER_EMAILS", "otra-persona@example.test")
    assert allowed(owner) is False
    monkeypatch.delenv("OWNER_EMAILS")
    assert allowed(owner) is False  # no allowlist: nobody qualifies


def test_an_inactive_owner_account_is_not_authorized(pg):
    owner = person(pg, OWNER_EMAIL, role="owner", source="owner", expires="NULL", status="blocked")
    assert allowed(owner) is False


def test_the_owner_with_another_accounts_workspace_is_not_authorized(pg):
    owner = person(pg, OWNER_EMAIL, role="owner", source="owner", expires="NULL")
    vip = person(pg, "vip@example.test")
    assert allowed({**owner, "workspace": vip["workspace"]}) is False


# --- direct calls to the backend --------------------------------------------------------------------

OWNER_ONLY_ROUTES = [
    ("vip_gmail_connect", lambda: routes.vip_gmail_connect(None, None), "begin_gmail_connection"),
    ("vip_gmail_consent", lambda: routes.vip_gmail_consent(type("R", (), {"accepted": True, "version": "v"})()),
     "accept_gmail_consent"),
    ("vip_mail_oauth_complete",
     lambda: routes.vip_mail_oauth_complete(type("R", (), {"flow": "f", "completion": "c"})(), None),
     "complete_mail_connection"),
    ("vip_microsoft_connect", lambda: routes.vip_microsoft_connect(None), "begin_microsoft_connection"),
    ("vip_gmail_sync", lambda: routes.vip_gmail_sync(), "sync_current_gmail"),
]


@pytest.mark.parametrize(("name", "call", "service"), OWNER_ONLY_ROUTES, ids=[r[0] for r in OWNER_ONLY_ROUTES])
def test_a_regular_user_calling_a_reading_route_directly_gets_403_and_nothing_runs(pg, monkeypatch, name, call, service):
    vip = person(pg, "vip@example.test")
    monkeypatch.setattr(routes, "require_feature", lambda *_a: True)  # the VIP plan check passes
    monkeypatch.setattr(routes, service, lambda *_a, **_k: pytest.fail(f"{service} must not run for a regular user"))
    token = session(vip)
    try:
        with pytest.raises(HTTPException) as error:
            call()
    finally:
        reset_current_user(token)
    assert error.value.status_code == 403
    assert error.value.detail == gmail_service.MAIL_READING_PAUSED


def test_a_session_claiming_owner_without_the_stored_identity_gets_403(pg, monkeypatch):
    vip = person(pg, "vip@example.test")
    monkeypatch.setattr(routes, "require_feature", lambda *_a: True)
    monkeypatch.setattr(routes, "begin_gmail_connection", lambda *_a, **_k: pytest.fail("must not connect"))
    token = session(vip, role="owner")  # the decision reads stored records, never the session role
    try:
        with pytest.raises(HTTPException) as error:
            routes.vip_gmail_connect(None, None)
    finally:
        reset_current_user(token)
    assert error.value.status_code == 403


def test_the_verified_owner_keeps_connecting(pg, monkeypatch):
    owner = person(pg, OWNER_EMAIL, role="owner", source="owner", expires="NULL")
    monkeypatch.setattr(routes, "require_feature", lambda *_a: True)
    monkeypatch.setattr(routes, "begin_gmail_connection", lambda *_a, **_k: {"authorization_url": "https://accounts.google.com/x"})
    token = session(owner)
    try:
        assert routes.vip_gmail_connect(None, None)["authorization_url"].startswith("https://")
    finally:
        reset_current_user(token)


def test_cuentas_and_the_aguinaldo_no_longer_share_the_mail_key():
    import inspect

    assert 'require_feature("financial_accounts")' in inspect.getsource(routes.vip_financial_identity)
    assert 'require_feature("financial_accounts")' in inspect.getsource(routes.vip_financial_identity_declare)
    assert 'require_feature("financial_accounts")' in inspect.getsource(routes.vip_financial_identity_confirm)
    assert 'require_feature("aguinaldo")' in inspect.getsource(routes.vip_aguinaldo)
    for function in (routes.vip_financial_identity, routes.vip_aguinaldo, routes.vip_gmail_emails,
                     routes.vip_gmail_candidate_accept, routes.vip_gmail_candidate_reject, routes.vip_gmail_status):
        assert "require_mail_reading" not in inspect.getsource(function)  # reviewing imported data stays VIP


# --- background paths --------------------------------------------------------------------------------

def _maintenance(monkeypatch):
    synced, revoked = [], []
    monkeypatch.setattr(gmail_service, "_sync_connection", lambda connection_id, **_k: synced.append(connection_id))
    monkeypatch.setattr(gmail_service.requests, "post", lambda url, data=None, **_k: revoked.append((data or {}).get("token")))
    monkeypatch.setattr(gmail_service, "apply_gmail_retention", lambda: {"ran": True})
    monkeypatch.setattr(gmail_service.mail_oauth, "discard_stale_flows", lambda conn: 0)
    result = gmail_service.gmail_maintenance(CRON_SECRET)
    return result, synced, revoked


def test_maintenance_reads_only_the_owner_and_never_ends_a_paused_connection(pg, monkeypatch):
    owner = person(pg, OWNER_EMAIL, role="owner", source="owner", expires="NULL")
    vip = person(pg, "vip@example.test")
    result, synced, revoked = _maintenance(monkeypatch)
    assert synced == [owner["connection"]]
    assert revoked == [] and result["ended_without_plan"] == 0
    assert row(pg, vip["connection"]) == ("active", None)  # paused, not disconnected
    assert secrets_left(pg) == {owner["secret"], vip["secret"]}  # no token deleted
    assert result["retention"] == {"ran": True}  # retention still runs


def test_a_lapsed_plan_still_ends_its_stored_authorization(pg, monkeypatch):
    owner = person(pg, OWNER_EMAIL, role="owner", source="owner", expires="NULL")
    lapsed = person(pg, "lapsed@example.test", expires="NOW() - interval '1 minute'")
    result, synced, revoked = _maintenance(monkeypatch)
    assert result["ended_without_plan"] == 1 and revoked == [f"token-{lapsed['email']}"]
    assert row(pg, lapsed["connection"])[0] == "disabled"
    assert secrets_left(pg) == {owner["secret"]}
    assert synced == [owner["connection"]]


def _push(email):
    data = base64.urlsafe_b64encode(json.dumps({"emailAddress": email, "historyId": "1"}).encode()).decode()
    return gmail_service.process_gmail_push({"message": {"data": data}}, PUSH_TOKEN)


def test_a_push_for_a_regular_users_mailbox_is_ignored_and_the_owners_is_read(pg, monkeypatch):
    owner = person(pg, OWNER_EMAIL, role="owner", source="owner", expires="NULL")
    vip = person(pg, "vip@example.test")
    synced = []
    monkeypatch.setattr(gmail_service, "_sync_connection", lambda connection_id, **_k: synced.append(connection_id))
    assert _push(vip["email"]) == {"status": "ignored"}
    assert _push(owner["email"])["status"] == "ok"
    assert synced == [owner["connection"]]


def test_reading_a_regular_users_connection_is_refused_even_when_called_directly(pg):
    vip = person(pg, "vip@example.test")
    with pytest.raises(HTTPException) as error:
        gmail_service._connection_with_token(vip["connection"])
    assert error.value.status_code == 403


# --- withdrawing authorization and deleting data -----------------------------------------------------

def test_a_regular_user_can_always_disconnect_and_the_token_is_revoked_and_deleted(pg, monkeypatch):
    owner = person(pg, OWNER_EMAIL, role="owner", source="owner", expires="NULL")
    vip = person(pg, "vip@example.test")
    revoked = []
    monkeypatch.setattr(gmail_service.requests, "post", lambda url, params=None, **_k: revoked.append((params or {}).get("token")))
    token = session(vip)
    try:
        assert routes.vip_gmail_disconnect(vip["connection"]) == {"status": "disconnected"}
    finally:
        reset_current_user(token)
    assert revoked == [f"token-{vip['email']}"]
    assert row(pg, vip["connection"])[0] == "disabled"
    assert secrets_left(pg) == {owner["secret"]}


@pytest.mark.parametrize(("method", "path"), [("DELETE", "/user-product/vip/gmail"),
                                              ("POST", "/user-product/vip/gmail/maintenance")])
def test_disconnecting_and_maintenance_never_pause_with_the_mail_switch(method, path):
    assert "gmail_automation" not in feature_flags._request_flags(method, path)


def test_the_mail_switch_off_stops_vip_reading_but_not_the_owner(pg, monkeypatch):
    owner = person(pg, OWNER_EMAIL, role="owner", source="owner", expires="NULL")
    vip = person(pg, "vip@example.test")
    monkeypatch.setattr(gmail_service, "MAIL_READING_OWNER_ONLY", False)  # the VIP path, once reopened
    state = {"enabled": True}
    monkeypatch.setattr(gmail_service, "load_feature_flags", lambda: {"gmail_automation": dict(state)})
    assert allowed(vip) is True and allowed(owner) is True
    state["enabled"] = False
    assert allowed(vip) is False and allowed(owner) is True
