"""Every connected mailbox is read, not only the first: Gmail and Outlook, several per account.

The scheduled maintenance syncs every active, entitled connection; an account's own sync (opening
the app) syncs all of its connections, each with its provider; one failing mailbox never stops
the others. Synthetic data only.
"""
from __future__ import annotations

from types import SimpleNamespace

from backend.user_product import gmail_service
from backend.user_product import microsoft_mail as ms

GMAIL = [gmail_service.GMAIL_SCOPE]
OUTLOOK = ["Mail.Read"]


class _Db:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        return SimpleNamespace(fetchall=lambda: self.rows, fetchone=lambda: None)

    def commit(self):
        pass


def _providers(monkeypatch, failing=()):
    synced = []

    def gmail(connection_id, **kwargs):
        if connection_id in failing:
            raise RuntimeError("provider down")
        synced.append(("gmail", connection_id, kwargs.get("trigger", "manual")))
        return {"scan_scope": "recent", "initial_scan_complete": True, "found": 1, "pending": 1}

    def outlook(connection_id, **kwargs):
        synced.append(("outlook", connection_id, kwargs.get("trigger", "manual")))
        return {"scan_scope": "recent", "initial_scan_complete": True, "found": 1, "pending": 1}

    monkeypatch.setattr(gmail_service, "_sync_connection", gmail)
    monkeypatch.setattr(ms, "sync_connection", outlook)
    return synced


def test_maintenance_reads_every_mailbox_of_every_account(monkeypatch):
    rows = [{"id": 1, "account_id": "a", "granted_scopes": GMAIL}, {"id": 2, "account_id": "a", "granted_scopes": GMAIL},
            {"id": 3, "account_id": "a", "granted_scopes": OUTLOOK}, {"id": 4, "account_id": "b", "granted_scopes": GMAIL}]
    monkeypatch.setenv("FINVA_GMAIL_CRON_SECRET", "cron-secret")
    monkeypatch.setattr(gmail_service.mail_oauth, "discard_stale_flows", lambda _conn: None)
    monkeypatch.setattr(gmail_service, "end_unentitled_mail_connections", lambda _conn: 0)
    monkeypatch.setattr(gmail_service, "get_connection", lambda: _Db(rows))
    monkeypatch.setattr(gmail_service, "_has_active_vip_access", lambda *_a: True)
    monkeypatch.setattr(gmail_service, "apply_gmail_retention", lambda: {})
    synced = _providers(monkeypatch, failing={2})
    result = gmail_service.gmail_maintenance("cron-secret")
    assert synced == [("gmail", 1, "maintenance"), ("outlook", 3, "maintenance"), ("gmail", 4, "maintenance")]
    assert result["connections"] == 4 and result["completed"] == 3, "one failing mailbox never stops the others"


def test_an_accounts_own_sync_reads_all_of_its_mailboxes(monkeypatch):
    rows = [{"id": 1, "granted_scopes": GMAIL}, {"id": 2, "granted_scopes": GMAIL}, {"id": 3, "granted_scopes": OUTLOOK}]
    monkeypatch.setattr(gmail_service, "get_current_account_id", lambda: "a")
    monkeypatch.setattr(gmail_service, "get_current_workspace_id", lambda: "w")
    monkeypatch.setattr(gmail_service, "get_connection", lambda: _Db(rows))
    monkeypatch.setattr(gmail_service, "reevaluate_workspace_candidates", lambda *_a, **_k: None)
    synced = _providers(monkeypatch)
    result = gmail_service.sync_current_gmail()
    assert [(provider, connection_id) for provider, connection_id, _ in synced] == [("gmail", 1), ("gmail", 2), ("outlook", 3)]
    assert result["connections"] == 3 and result["found"] == 3
