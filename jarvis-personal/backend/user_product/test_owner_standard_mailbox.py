"""DINCR Owner connects financial mailboxes through the standard per-account OAuth flow.

The Owner's legacy Gmail reader (server-held GMAIL_REFRESH_TOKEN) is retired. These
tests drive the real begin -> callback -> complete code with the stateful fakes of
test_mail_oauth, as the Owner, and check the legacy-import reconciliation.
"""
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend import main
from backend.email_monitor import routes as email_monitor_routes, service as email_monitor_service
from backend.user_product import gmail_service, legacy_owner_mail
from backend.user_product.candidate_resolution import resolve_candidate, semantic_fingerprint
from backend.user_product.test_mail_oauth import (  # noqa: F401  (env is a pytest fixture)
    A, B, GMAIL_CLIENT, FakeConnection, _as, callback, complete, connections_of, env, start,
)

BACKEND = Path(__file__).resolve().parents[1]
OWNER = {"id": 1, "account_id": "00000000-0000-0000-0000-0000000000ff", "workspace_id": "w0000000-0000-0000-0000-0000000000ff", "role": "owner"}


class MailboxConnection(FakeConnection):
    """Adds the per-mailbox disconnect queries to the OAuth fake."""

    def execute(self, query, params=()):
        q = " ".join(query.split())
        connections, vault = self.work["connections"], self.work["vault"]
        if q.startswith("SELECT id,refresh_token_secret_id,status,granted_scopes FROM finva_gmail_connections"):
            account, workspace, connection_id, _ = params
            return self._rows(c for c in connections.values()
                              if (c["account_id"], c["workspace_id"]) == (account, workspace) and c["status"] != "disabled"
                              and (connection_id is None or c["id"] == connection_id))
        if q.startswith("SELECT dincr_private.mail_secret_read"):
            return self._rows([{"decrypted_secret": vault[params[0]]}] if params[0] in vault else [])
        if q.startswith("UPDATE finva_gmail_connections SET status='disabled'"):
            connections[params[0]]["status"] = "disabled"
            return self._rows([])
        return super().execute(query, params)


@pytest.fixture
def owner_env(env, monkeypatch):  # noqa: F811
    env.db.vip.add(OWNER["account_id"])  # the Owner's own VIP subscription (access_source 'owner')
    env.db.connect = lambda: MailboxConnection(env.db)
    for module in (gmail_service, gmail_service.mail_oauth):
        monkeypatch.setattr(module, "get_connection", env.db.connect)
    env.revoked = []
    token_endpoint = gmail_service.requests.post

    def post(url, *args, **kwargs):
        if url == "https://oauth2.googleapis.com/revoke":
            env.revoked.append(kwargs["params"]["token"])
            return SimpleNamespace(status_code=200)
        return token_endpoint(url, *args, **kwargs)

    monkeypatch.setattr(gmail_service.requests, "post", post)
    return env


def connect(env, user, mailbox):
    _, params = callback("gmail", *env.provider.authorize(start("gmail", user), mailbox))
    return complete(user, params)


def secrets_by_mailbox(env, user):
    vault = env.db.state["vault"]
    return {c["google_email"]: vault.get(c["refresh_token_secret_id"])
            for c in env.db.state["connections"].values()
            if c["account_id"] == user["account_id"] and c["status"] == "active"}


def test_owner_uses_the_same_pkce_flow_and_callback_as_users(owner_env):
    owner_url, user_url = start("gmail", OWNER), start("gmail", A)
    for url in (owner_url, user_url):
        query = parse_qs(urlparse(url).query)
        assert query["code_challenge_method"] == ["S256"]
        assert query["redirect_uri"] == [GMAIL_CLIENT[2]]
        assert query["scope"] == [gmail_service.GMAIL_SCOPE]  # gmail.readonly only
    assert connect(owner_env, OWNER, "owner.one@example.com") == {"status": "connected", "provider": "gmail"}
    assert connections_of(owner_env, OWNER) == [("owner.one@example.com", OWNER["workspace_id"])]


def test_owner_connects_two_gmail_mailboxes_with_independent_tokens(owner_env):
    connect(owner_env, OWNER, "owner.one@example.com")
    connect(owner_env, OWNER, "owner.two@example.com")

    assert sorted(connections_of(owner_env, OWNER)) == [
        ("owner.one@example.com", OWNER["workspace_id"]), ("owner.two@example.com", OWNER["workspace_id"]),
    ]
    assert secrets_by_mailbox(owner_env, OWNER) == {
        "owner.one@example.com": "refresh-for-owner.one@example.com",
        "owner.two@example.com": "refresh-for-owner.two@example.com",
    }
    ids = [c["refresh_token_secret_id"] for c in owner_env.db.state["connections"].values()]
    assert len(set(ids)) == 2  # one Vault secret per mailbox
    assert owner_env.synced == [("gmail", 1), ("gmail", 2)]  # each mailbox syncs on its own


def test_reconnecting_one_owner_mailbox_leaves_the_other_untouched(owner_env):
    connect(owner_env, OWNER, "owner.one@example.com")
    connect(owner_env, OWNER, "owner.two@example.com")
    second = next(c for c in owner_env.db.state["connections"].values() if c["google_email"] == "owner.two@example.com")
    second_secret = second["refresh_token_secret_id"]

    connect(owner_env, OWNER, "owner.one@example.com")

    assert len(connections_of(owner_env, OWNER)) == 2
    assert owner_env.db.state["connections"][second["id"]]["refresh_token_secret_id"] == second_secret
    assert secrets_by_mailbox(owner_env, OWNER)["owner.two@example.com"] == "refresh-for-owner.two@example.com"


def test_disconnecting_one_owner_mailbox_keeps_the_other(owner_env):
    connect(owner_env, OWNER, "owner.one@example.com")
    connect(owner_env, OWNER, "owner.two@example.com")

    with pytest.raises(HTTPException) as ambiguous:
        _as(OWNER, gmail_service.disconnect_gmail)  # with two mailboxes the caller must choose
    assert ambiguous.value.status_code == 422

    assert _as(OWNER, gmail_service.disconnect_gmail, 1) == {"status": "disconnected"}

    assert secrets_by_mailbox(owner_env, OWNER) == {"owner.two@example.com": "refresh-for-owner.two@example.com"}
    assert owner_env.revoked == ["refresh-for-owner.one@example.com"]  # only mailbox A's grant is revoked


def test_owner_and_users_cannot_complete_each_others_flows(owner_env):
    _, owner_params = callback("gmail", *owner_env.provider.authorize(start("gmail", OWNER), "owner.one@example.com"))
    with pytest.raises(HTTPException) as refused:
        complete(B, owner_params)
    assert refused.value.status_code == 403

    _, user_params = callback("gmail", *owner_env.provider.authorize(start("gmail", A), "a@example.com"))
    with pytest.raises(HTTPException) as owner_refused:
        complete(OWNER, user_params)  # the Owner role grants no bypass over another account's flow
    assert owner_refused.value.status_code == 403
    assert connections_of(owner_env, OWNER) == [] and connections_of(owner_env, B) == [] and connections_of(owner_env, A) == []


def test_owner_role_is_not_a_bypass_for_the_mailbox_entitlement(owner_env):
    owner_env.db.vip.discard(OWNER["account_id"])
    code, state = owner_env.provider.authorize(start("gmail", OWNER), "owner.one@example.com")
    assert callback("gmail", code, state)[0] == "vip_required"
    assert connections_of(owner_env, OWNER) == [] and owner_env.db.state["vault"] == {}


def test_owner_mailbox_entitlement_comes_from_its_own_vip_subscription():
    migration = (BACKEND.parent / "database" / "migrations" / "20260831_unified_saas_foundation.sql").read_text(encoding="utf-8")
    assert "SELECT a.id,p.id,'active','owner',NOW(),NOW(),NOW()" in migration and "WHERE a.role='owner' AND p.code='vip'" in migration

    class Conn:
        def execute(self, query, params=()):
            self.query = " ".join(query.split())
            return SimpleNamespace(fetchone=lambda: {"allowed": 1})

    conn = Conn()
    assert gmail_service._has_active_vip_access(conn, OWNER["account_id"]) is True
    # Only courtesy grants need an expiry; the Owner's 'owner' access source never expires.
    assert "s.access_source<>'courtesy'" in conn.query and "p.code='vip'" in conn.query


def test_the_legacy_owner_gmail_reader_is_retired():
    for name in ("sync_gmail_for_owner", "cron_sync", "renew_gmail_watch", "process_gmail_push", "_gmail_service", "sync_ccss_payroll_orders"):
        assert not hasattr(email_monitor_service, name)
    assert not hasattr(email_monitor_routes, "sync_gmail_for_owner")
    for path in BACKEND.rglob("*.py"):
        if not path.name.startswith("test_"):
            assert "GMAIL_REFRESH_TOKEN" not in path.read_text(encoding="utf-8"), path

    client = TestClient(main.app, raise_server_exceptions=False)
    assert client.post("/email-monitor/cron", headers={"X-JARVIS-Cron-Secret": "x"}).status_code == 410
    assert client.post("/email-monitor/gmail-watch").status_code == 410
    push = client.post("/email-monitor/gmail-push?token=x", json={"message": {"data": "e30"}})
    assert push.status_code == 200 and push.json() == {"status": "retired"}  # acknowledged, nothing read


# --- Existing Owner data: reconnecting the mailbox the legacy reader used --------

class LegacyConn:
    def __init__(self, *, legacy_table=True, legacy_rows=()):
        self.legacy_table, self.legacy_rows, self.updates = legacy_table, list(legacy_rows), []

    def execute(self, query, params=()):
        q = " ".join(query.split())
        if q.startswith("SELECT to_regclass('public.email_transaction_candidates')"):
            return SimpleNamespace(fetchone=lambda: {"present": "email_transaction_candidates" if self.legacy_table else None})
        if q.startswith("SELECT t.id FROM email_ingested_messages m"):
            workspace, message_id = params
            rows = [{"id": row["transaction_id"]} for row in self.legacy_rows
                    if (row["workspace_id"], row["message_id"]) == (workspace, message_id)]
            return SimpleNamespace(fetchone=lambda: rows[0] if rows else None)
        if q.startswith("UPDATE finva_email_candidates SET status='duplicate',resolution_reason=%s"):
            self.updates.append(params)
            return SimpleNamespace(fetchone=lambda: None)
        raise AssertionError(q[:80])


LEGACY_ROW = {"workspace_id": OWNER["workspace_id"], "message_id": "18f0a1b2c3d4e5f6", "transaction_id": 501}


def test_a_message_the_legacy_reader_already_imported_is_not_offered_again(monkeypatch):
    conn = LegacyConn(legacy_rows=[LEGACY_ROW])
    monkeypatch.setattr(gmail_service, "discover_candidate_account", lambda *_a, **_k: None)
    monkeypatch.setattr(gmail_service, "link_received_payroll", lambda *_a, **_k: None)
    monkeypatch.setattr(gmail_service, "resolve_candidate", lambda _conn, _id: {"status": "pending"})
    inserted = {"id": 77}
    original_execute = conn.execute
    conn.execute = lambda q, p=(): SimpleNamespace(fetchone=lambda: inserted) if "INSERT INTO finva_email_candidates" in q else original_execute(q, p)
    candidate = {key: None for key in (
        "movement_index", "source_type", "source_provider", "source_record_key", "institution_country",
        "transaction_date", "transaction_time", "description", "amount", "currency", "original_amount",
        "original_currency", "transaction_type", "movement_direction", "movement_kind", "category", "bank",
        "source_account_label", "source_account_reference", "destination_account_reference", "counterparty",
        "external_reference", "parser_name", "parser_version", "extraction_method", "confidence",
        "uncertainty_reason", "dedupe_key", "is_internal_transfer")} | {"raw_payload": {}}
    connection = {"account_id": OWNER["account_id"], "workspace_id": OWNER["workspace_id"], "legacy_user_id": 1}

    result = gmail_service._insert_finva_candidate(
        conn, email_message_id=5, connection=connection, candidate=candidate, gmail_message_id="18f0a1b2c3d4e5f6",
    )

    assert result == {"status": "duplicate", "resolution_reason": "legacy_owner_import"}
    assert conn.updates == [("legacy_owner_import", 77)]  # only the new candidate; the transaction is untouched

    fresh = gmail_service._insert_finva_candidate(
        conn, email_message_id=6, connection=connection, candidate=candidate, gmail_message_id="18f0ffffffffffff",
    )
    assert fresh == {"status": "pending"} and len(conn.updates) == 1


def test_legacy_matching_is_scoped_to_the_workspace_and_optional():
    conn = LegacyConn(legacy_rows=[LEGACY_ROW])
    assert legacy_owner_mail.legacy_transaction_for_message(conn, workspace_id=OWNER["workspace_id"], provider_message_id="18f0a1b2c3d4e5f6") == 501
    assert legacy_owner_mail.legacy_transaction_for_message(conn, workspace_id=A["workspace_id"], provider_message_id="18f0a1b2c3d4e5f6") is None
    assert legacy_owner_mail.legacy_transaction_for_message(LegacyConn(legacy_table=False), workspace_id=OWNER["workspace_id"], provider_message_id="x") is None


@pytest.mark.parametrize("status", ["duplicate", "internal_transfer"])
def test_only_pending_candidates_are_resolved_as_legacy_imports(status):
    conn = LegacyConn()
    assert legacy_owner_mail.mark_legacy_duplicate(conn, candidate_id=9, resolution={"status": status}) == {"status": status}
    assert conn.updates == []


def test_same_movement_from_two_mailboxes_or_outlook_is_one_semantic_movement():
    base = {"account_id": OWNER["account_id"], "workspace_id": OWNER["workspace_id"], "transaction_date": "2026-09-21",
            "amount": 25000, "currency": "CRC", "bank": "bac", "external_reference": "REF-1"}
    fingerprints = {semantic_fingerprint({**base, "source_provider": provider, "source_type": "email"}) for provider in ("gmail", "microsoft")}
    assert len(fingerprints) == 1

    class Conn:
        def __init__(self):
            self.calls = []

        def execute(self, query, params=()):
            q = " ".join(query.split())
            self.calls.append((q, params))
            if q.startswith("SELECT * FROM finva_email_candidates"):
                row = {**base, "id": 12}
            elif q.startswith("SELECT id,status,related_candidate_id"):
                row = {"id": 11, "status": "pending", "related_candidate_id": None}
            else:
                row = {"id": 11}
            return SimpleNamespace(fetchone=lambda: row, fetchall=lambda: [])

    conn = Conn()
    assert resolve_candidate(conn, 12) == {"status": "duplicate", "related_candidate_id": 11}
    duplicate_query, params = next(call for call in conn.calls if "semantic_fingerprint=%s" in call[0])
    # Scoped to the account/workspace, not to one mailbox connection.
    assert "account_id=%s AND workspace_id=%s AND semantic_fingerprint=%s" in duplicate_query and "connection_id" not in duplicate_query
    assert params[:2] == (OWNER["account_id"], OWNER["workspace_id"])
