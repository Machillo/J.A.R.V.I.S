from datetime import date
from urllib.parse import parse_qs, urlparse

import pytest

from backend.user_product import microsoft_mail as mail


class Result:
    def __init__(self, one=None, rows=None):
        self.one, self.rows = one, rows or []

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.rows


class Connection:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query, params=()):
        self.calls.append((query, params))
        return next(self.responses)

    def commit(self):
        self.committed = True


def test_oauth_begin_requires_consent_and_exact_read_scopes(monkeypatch):
    monkeypatch.setattr(mail, "require_gmail_consent", lambda: None)
    monkeypatch.setattr(mail, "_config", lambda: ("client", "secret", "https://api.example/callback"))
    monkeypatch.setattr(mail.mail_oauth, "start_flow", lambda provider: (f"opaque-{provider}-state", "challenge"))
    uri = mail.begin_connection()["authorization_url"]
    params = parse_qs(urlparse(uri).query)
    assert urlparse(uri).hostname == "login.microsoftonline.com"
    assert urlparse(uri).path.startswith("/common/")
    assert params["scope"] == ["offline_access User.Read Mail.Read"]
    assert params["state"] == ["opaque-microsoft-state"]
    assert params["code_challenge"] == ["challenge"] and params["code_challenge_method"] == ["S256"]
    assert "Mail.Send" not in uri and "Mail.ReadWrite" not in uri and "secret" not in uri

def test_graph_pagination_rejects_third_party_url_before_request(monkeypatch):
    monkeypatch.setattr(mail.requests, "get", lambda *_args, **_kwargs: pytest.fail("token leaked"))
    with pytest.raises(ValueError):
        mail._graph_get("private-token", "https://evil.example/v1.0/me/messages")
    with pytest.raises(ValueError):
        mail._graph_get("private-token", "https://graph.microsoft.com.evil.example/v1.0/me/messages")
    with pytest.raises(ValueError):
        mail._graph_get("private-token", "https://graph.microsoft.com/v1.0/users/other/messages")


def test_sender_restriction_checks_actual_address_not_display_name():
    assert mail._sender_allowed('notificacion@notificacionesbaccr.com')
    assert mail._sender_allowed("info@bpdc.fi.cr")
    assert not mail._sender_allowed('notificacion@notificacionesbaccr.com <attacker@evil.example>')
    assert not mail._sender_allowed("attacker@notificacionesbaccr.com.evil.example")


def test_sync_reuses_candidate_pipeline_and_preserves_next_page(monkeypatch):
    connection = {
        "id": 7, "account_id": "account", "workspace_id": "workspace",
        "granted_scopes": ["Mail.Read"], "refresh_token_secret_id": "secret", "initial_scan_completed_at": None,
        "initial_scan_page_token": None,
    }
    original = Connection([Result(one=connection), Result(one={"decrypted_secret": "refresh"})])
    updated = Connection([Result()])
    connections = iter([original, updated])
    monkeypatch.setattr(mail, "get_connection", lambda: next(connections))
    monkeypatch.setattr(mail, "_has_active_vip_access", lambda *_args: True)
    monkeypatch.setattr(mail, "_refresh", lambda *_args: "access")
    monkeypatch.setattr(mail, "_vault_read", lambda *_args: "refresh")
    graph_calls = []
    def graph(_token, url, params=None):
        graph_calls.append((url, params))
        if url.startswith("/me/messages/"):
            return {"subject": "Aviso", "body": {"content": "<p>Transferencia</p>"},
                    "receivedDateTime": "2026-09-23T10:00:00Z", "hasAttachments": False}
        return {"value": [
            {"id": "bank-1", "from": {"emailAddress": {"address": "notificacion@notificacionesbaccr.com"}},
             "subject": "Aviso", "body": {"content": "<p>Transferencia</p>"}, "receivedDateTime": "2026-09-23T10:00:00Z"},
            {"id": "other", "from": {"emailAddress": {"address": "someone@example.com"}}},
        ], "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/messages?$skiptoken=next"}
    monkeypatch.setattr(mail, "_graph_get", graph)
    ingested = []
    monkeypatch.setattr(mail, "_ingest_message", lambda *_args, **kwargs: ingested.append(kwargs) or "pending")
    result = mail.sync_connection(7)
    assert result["found"] == result["pending"] == 1
    assert ingested[0]["body"] == "Transferencia"
    assert graph_calls[0][1]["$filter"] == f"receivedDateTime ge {date.today().year}-01-01T00:00:00Z"
    assert "body" not in graph_calls[0][1]["$select"]
    assert len(graph_calls) == 2  # Read the selected bank message, never the unrelated message.
    assert updated.calls[0][1][0].startswith("https://graph.microsoft.com/")
    assert not result["initial_scan_complete"]
    assert updated.committed


def test_failed_message_does_not_advance_initial_cursor(monkeypatch):
    connection = {"id": 7, "account_id": "account", "workspace_id": "workspace",
                  "granted_scopes": ["Mail.Read"], "refresh_token_secret_id": "secret",
                  "initial_scan_completed_at": None, "initial_scan_page_token": None}
    db = Connection([Result(one=connection)])
    monkeypatch.setattr(mail, "get_connection", lambda: db)
    monkeypatch.setattr(mail, "_has_active_vip_access", lambda *_args: True)
    monkeypatch.setattr(mail, "_vault_read", lambda *_args: "refresh")
    monkeypatch.setattr(mail, "_refresh", lambda *_args: "access")
    monkeypatch.setattr(mail, "_graph_get", lambda *_args, **_kwargs: {"value": [{
        "id": "bank-1", "from": {"emailAddress": {"address": "notificacion@notificacionesbaccr.com"}},
    }], "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/messages?$skiptoken=next"})
    monkeypatch.setattr(mail, "_ingest_message", lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("temporary")))
    with pytest.raises(ValueError):
        mail.sync_connection(7)
    assert not db.committed
    assert not any("UPDATE finva_gmail_connections" in sql for sql, _ in db.calls)

# OAuth callback and completion are covered in test_mail_oauth.py.
