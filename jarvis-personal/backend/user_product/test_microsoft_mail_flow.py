"""Outlook/Hotmail end-to-end contracts: OAuth, token handling, read-only Graph,
shared candidate pipeline, isolation, disconnection and Gmail non-regression."""
import logging
from datetime import date
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException

from backend import main
from backend.auth import saas
from backend.auth.current_user import reset_current_user, set_current_user
from backend.user_product import gmail_service
from backend.user_product import microsoft_mail as mail
from backend.user_product.candidate_resolution import semantic_fingerprint
from backend.user_product.financial_candidate import canonical_candidate
from backend.user_product.test_gmail_accept import FakeDatabase

CONFIG = ("client-id", "client-secret", "https://api.dincr.com/user-product/vip/mail/microsoft/callback")
SECRET_VALUES = ("client-secret", "refresh-secret", "access-secret", "rotated-secret")


class Rows:
    def __init__(self, one=None, rows=None):
        self.one, self.rows = one, rows or []

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.rows


class Db:
    def __init__(self, *results):
        self.results, self.calls, self.committed = list(results), [], False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        self.calls.append((" ".join(query.split()), params))
        return self.results.pop(0) if self.results else Rows()

    def commit(self):
        self.committed = True


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(mail, "_config", lambda: CONFIG)


# Configuration ------------------------------------------------------------

def test_render_variable_names_enable_outlook_and_legacy_names_still_work(monkeypatch):
    monkeypatch.undo()
    for names in mail.CONFIG_NAMES:
        for name in names:
            monkeypatch.delenv(name, raising=False)
    assert mail.microsoft_configured() is False
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "id")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "secret")
    assert mail.microsoft_configured() is False  # redirect URI still missing
    monkeypatch.setenv("FINVA_MICROSOFT_REDIRECT_URI", CONFIG[2])
    assert mail.microsoft_configured() is True
    assert mail._config() == ("id", "secret", CONFIG[2])


def test_callback_is_public_but_connect_requires_a_session():
    assert main._is_public_path("/user-product/vip/mail/microsoft/callback") is True
    assert main._is_public_path("/user-product/vip/mail/microsoft/connect") is False


def test_outlook_keeps_the_same_vip_entitlement_as_gmail():
    assert saas.BUILTIN_FEATURE_MIN_PLAN["gmail_automation"] == "vip"
    for plan in ("free", "basic"):
        assert saas.PLAN_RANK[plan] < saas.PLAN_RANK[saas.BUILTIN_FEATURE_MIN_PLAN["gmail_automation"]]


# OAuth --------------------------------------------------------------------

def test_authorization_url_uses_common_authority_and_read_only_scopes(monkeypatch):
    monkeypatch.setattr(mail, "require_gmail_consent", lambda: None)
    monkeypatch.setattr(mail.mail_oauth, "start_flow", lambda provider, *_scope: ("server-side-state", "pkce-challenge"))
    url = urlparse(mail.begin_connection()["authorization_url"])
    params = parse_qs(url.query)
    assert (url.scheme, url.hostname, url.path) == ("https", "login.microsoftonline.com", "/common/oauth2/v2.0/authorize")
    assert params["scope"] == ["offline_access User.Read Mail.Read"]
    assert params["redirect_uri"] == [CONFIG[2]]
    assert params["response_type"] == ["code"] and params["client_id"] == ["client-id"]
    assert params["state"] == ["server-side-state"]
    assert params["code_challenge"] == ["pkce-challenge"] and params["code_challenge_method"] == ["S256"]
    assert "client-secret" not in url.geturl()


def test_authorization_requires_the_mail_consent_first(monkeypatch):
    monkeypatch.setattr(mail, "require_gmail_consent", lambda: (_ for _ in ()).throw(HTTPException(status_code=409)))
    with pytest.raises(HTTPException):
        mail.begin_connection()


@pytest.mark.parametrize("scope", [
    "https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/User.Read",
    "https://graph.microsoft.com/mail.read https://graph.microsoft.com/user.read",
    "offline_access User.Read Mail.Read",
])
def test_granted_scope_formats_are_all_recognized(scope):
    assert mail.REQUIRED_SCOPE in mail._granted_scopes(scope)


def test_mail_read_write_is_never_mistaken_for_mail_read():
    assert mail.REQUIRED_SCOPE not in mail._granted_scopes("https://graph.microsoft.com/Mail.ReadWrite")


# Token renewal ------------------------------------------------------------

def test_refresh_rotates_the_vault_secret_and_returns_only_the_access_token(monkeypatch):
    monkeypatch.setattr(mail.requests, "post", lambda *_a, **_k: SimpleNamespace(
        status_code=200, raise_for_status=lambda: None,
        json=lambda: {"access_token": "access-secret", "refresh_token": "rotated-secret"}))
    db = Db(Rows(one={"refresh_token_secret_id": "old-vault", "status": "active"}))
    monkeypatch.setattr(mail, "get_connection", lambda: db)
    created, deleted = [], []
    monkeypatch.setattr(mail, "_vault_create", lambda _conn, token, *_a: created.append(token) or "new-vault")
    monkeypatch.setattr(mail, "_vault_delete", lambda _conn, secret_id: deleted.append(secret_id))

    token = mail._refresh({"id": 7, "account_id": "account-a", "refresh_token_secret_id": "old-vault"}, "refresh-secret")

    assert token == "access-secret"
    assert created == ["rotated-secret"] and deleted == ["old-vault"]
    assert db.committed and not any("rotated-secret" in str(params) for _, params in db.calls)


def test_revoked_refresh_token_requires_reauthorization_and_logs_no_token(monkeypatch, caplog):
    monkeypatch.setattr(mail.requests, "post", lambda *_a, **_k: SimpleNamespace(status_code=400, json=lambda: {"error": "invalid_grant"}))
    db = Db()
    monkeypatch.setattr(mail, "get_connection", lambda: db)
    with caplog.at_level(logging.WARNING), pytest.raises(HTTPException) as error:
        mail._refresh({"id": 7, "account_id": "account-a", "refresh_token_secret_id": "vault"}, "refresh-secret")
    assert error.value.status_code == 409
    assert any("reauthorization_required" in sql for sql, _ in db.calls)
    assert "invalid_grant" in caplog.text and "refresh-secret" not in caplog.text


# Graph is read-only ----------------------------------------------------------

def test_sync_only_issues_graph_gets_and_never_modifies_mail(monkeypatch):
    for method in ("post", "patch", "put", "delete"):
        monkeypatch.setattr(mail.requests, method, lambda *_a, _m=method, **_k: pytest.fail(f"Graph {_m} is not allowed"))
    requested = []

    def get(url, headers=None, params=None, **_kwargs):
        requested.append((url, params))
        assert headers == {"Authorization": "Bearer access-secret"}
        if url.endswith("/me/messages"):
            body = {"value": [{"id": "m1", "from": {"emailAddress": {"address": "notificacion@notificacionesbaccr.com"}}}]}
        else:
            body = {"subject": "Aviso", "body": {"content": "<p>Compra</p>"}, "receivedDateTime": "2026-09-23T10:00:00Z", "hasAttachments": False}
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None, json=lambda: body)

    monkeypatch.setattr(mail.requests, "get", get)
    connection = {"id": 7, "account_id": "account-a", "workspace_id": "workspace-a", "granted_scopes": ["Mail.Read"],
                  "refresh_token_secret_id": "vault", "initial_scan_completed_at": date(2026, 1, 1)}
    dbs = iter([Db(Rows(one=connection)), Db()])
    monkeypatch.setattr(mail, "get_connection", lambda: next(dbs))
    monkeypatch.setattr(mail, "_has_active_vip_access", lambda *_a: True)
    monkeypatch.setattr(mail, "_vault_read", lambda *_a: "refresh-secret")
    monkeypatch.setattr(mail, "_refresh", lambda *_a: "access-secret")
    ingested = []
    monkeypatch.setattr(mail, "_ingest_message", lambda conn, message_id, **kw: ingested.append((conn, message_id, kw)) or "pending")

    result = mail.sync_connection(7)

    assert result["pending"] == 1
    assert all(urlparse(url).hostname == "graph.microsoft.com" for url, _ in requested)
    assert requested[0][1]["$select"] == "id,from,receivedDateTime"  # no bodies for unrelated mail
    assert ingested[0][0]["granted_scopes"] == ["Mail.Read"] and ingested[0][2]["body"] == "Compra"


# Shared pipeline ------------------------------------------------------------

def test_outlook_candidates_are_labelled_microsoft_and_gmail_stays_gmail():
    parsed = {"bank": "bac", "transaction_date": "2026-09-20", "description": "Compra", "amount": 1250,
              "transaction_type": "expense", "category": "Comida", "reference": "ABC123"}
    outlook = canonical_candidate(parsed, provider_message_id="ms-1", subject="Compra", source_provider="microsoft")
    gmail = canonical_candidate(parsed, provider_message_id="g-1", subject="Compra")
    assert (outlook["source_provider"], outlook["source_record_key"]) == ("microsoft", "microsoft:ms-1:0")
    assert (gmail["source_provider"], gmail["source_record_key"]) == ("gmail", "gmail:g-1:0")
    assert gmail_service._mail_provider({"granted_scopes": ["Mail.Read"]}) == "microsoft"
    assert gmail_service._mail_provider({"granted_scopes": [gmail_service.GMAIL_SCOPE]}) == "gmail"
    # The same bank notice received in both mailboxes resolves to one movement.
    assert semantic_fingerprint(outlook) == semantic_fingerprint(gmail) is not None


def test_outlook_candidate_accept_reject_and_retry_use_the_shared_review(monkeypatch):
    db = FakeDatabase()
    for candidate in db.state["candidates"].values():
        candidate["source_provider"] = "microsoft"
    db.state["candidates"][84] = {**db.state["candidates"][81], "id": 84, "email_message_id": 984}
    monkeypatch.setattr(gmail_service, "get_connection", db.connect)
    token = set_current_user({"id": 12, "account_id": "account-a", "workspace_id": "workspace-a", "role": "user"})
    try:
        accepted = gmail_service.review_gmail_candidate(81, "accept")
        retried = gmail_service.review_gmail_candidate(81, "accept")
        rejected = gmail_service.review_gmail_candidate(84, "reject")
    finally:
        reset_current_user(token)
    assert accepted["status"] == retried["status"] == "confirmed"
    assert accepted["transaction_id"] == retried["transaction_id"]
    assert len(db.state["transactions"]) == 1 and len(db.state["events"]) == 1
    assert rejected["status"] == "rejected"


# Isolation and disconnection ------------------------------------------------

def test_manual_sync_only_reads_the_callers_connections_and_routes_by_provider(monkeypatch):
    db = Db(Rows(rows=[{"id": 1, "granted_scopes": [gmail_service.GMAIL_SCOPE]}, {"id": 2, "granted_scopes": ["Mail.Read"]}]), Rows())
    monkeypatch.setattr(gmail_service, "get_connection", lambda: db)
    monkeypatch.setattr(gmail_service, "get_current_account_id", lambda: "account-a")
    monkeypatch.setattr(gmail_service, "get_current_workspace_id", lambda: "workspace-a")
    monkeypatch.setattr(gmail_service, "reevaluate_workspace_candidates", lambda *_a, **_k: None)
    routed = []
    ok = {"scan_scope": "recent", "initial_scan_complete": True, "found": 0, "auto_saved": 0, "pending": 0,
          "payroll_reports": 0, "duplicates": 0}
    monkeypatch.setattr(gmail_service, "_sync_connection", lambda cid, **_k: routed.append(("gmail", cid)) or ok)
    monkeypatch.setattr(mail, "sync_connection", lambda cid, **_k: routed.append(("microsoft", cid)) or ok)

    gmail_service.sync_current_gmail()

    assert db.calls[0][1] == ("account-a", "workspace-a")
    assert "account_id=%s AND workspace_id=%s" in db.calls[0][0]
    assert routed == [("gmail", 1), ("microsoft", 2)]


def test_disconnecting_outlook_deletes_the_secret_without_calling_google(monkeypatch):
    db = Db(Rows(rows=[{"id": 2, "refresh_token_secret_id": "vault", "status": "active", "granted_scopes": ["Mail.Read"]}]))
    monkeypatch.setattr(gmail_service, "get_connection", lambda: db)
    monkeypatch.setattr(gmail_service, "get_current_account_id", lambda: "account-a")
    monkeypatch.setattr(gmail_service, "get_current_workspace_id", lambda: "workspace-a")
    monkeypatch.setattr(gmail_service.requests, "post", lambda *_a, **_k: pytest.fail("Google revoke must not run for Outlook"))

    assert gmail_service.disconnect_gmail(2) == {"status": "disconnected"}

    assert db.calls[0][1][:2] == ("account-a", "workspace-a")
    assert any("status='disabled'" in sql for sql, _ in db.calls)
    assert any(sql.startswith("DELETE FROM vault.secrets") and params == ("vault",) for sql, params in db.calls)
    assert db.committed
