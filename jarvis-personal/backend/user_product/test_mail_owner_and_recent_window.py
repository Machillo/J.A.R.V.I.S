"""Both mail fixes together: every sync reads new mail (#366) and the Owner reads only its month (#367).

While a history scan is pending, a DINCR User's sync reads one history page and the 45-day recent
window; the Owner's sync reads no history and its recent window starts on the first day of the
current month, so September is never re-read for the Owner. Both skip mail already recorded, and
the Owner's stored cursor is never moved. Synthetic data only.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.user_product import gmail_service, owner_mail_automation
from backend.user_product import microsoft_mail as ms

OCT_1 = date(2026, 10, 1)
PENDING = {"id": 12, "account_id": "account-x", "workspace_id": "workspace-x", "import_scope": "current_year",
           "import_since": date(2026, 1, 1), "initial_scan_completed_at": None, "initial_scan_page_token": "page-4",
           "watch_expiration": datetime.now(timezone.utc) + timedelta(days=5)}


class _Db:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        self.calls.append((" ".join(query.split()), params))
        return SimpleNamespace(fetchone=lambda: None, fetchall=lambda: [])

    def commit(self):
        pass


def _gmail(monkeypatch, *, owner, processed=()):
    monkeypatch.setattr(gmail_service, "_connection_with_token", lambda _id: (dict(PENDING), "token"))
    monkeypatch.setattr(gmail_service, "owner_account_context", lambda *_a: owner)
    monkeypatch.setattr(owner_mail_automation, "window_since", lambda _connection, chosen: max(chosen, OCT_1))
    history, queries, read = [], [], []
    monkeypatch.setattr(gmail_service, "_list_message_page",
                        lambda _s, query, **_k: history.append(query) or ([{"id": "old-1"}], "page-5"))

    def refs(_service, query, _limit):
        queries.append(query)
        return [] if query == gmail_service._aguinaldo_gmail_query() else [{"id": "new-1"}, {"id": "seen-1"}]

    monkeypatch.setattr(gmail_service, "_list_message_refs", refs)
    monkeypatch.setattr(gmail_service, "already_processed", lambda _id, ids: {i for i in ids if i in processed})
    monkeypatch.setattr(gmail_service, "_process_message", lambda _s, _c, message_id: read.append(message_id) or "pending")
    monkeypatch.setattr(gmail_service, "_start_watch", lambda *_a, **_k: None)
    updates = _Db()
    monkeypatch.setattr(gmail_service, "get_connection", lambda: updates)
    result = gmail_service._sync_connection(12, service=object(), trigger="push")
    return result, history, queries, read, updates


def test_an_owner_push_reads_new_mail_of_the_current_month_only(monkeypatch):
    _result, history, queries, read, updates = _gmail(monkeypatch, owner=True, processed={"seen-1"})
    assert history == [], "the Owner never reads the history scan"
    assert f"after:{gmail_service._cr_midnight_epoch(OCT_1)}" in queries[0], "the recent window starts on the 1st"
    assert "newer_than" not in queries[0], "not the 45-day window (it would re-read September)"
    assert read == ["new-1"], "new mail is read; recorded mail is skipped"
    _query, params = updates.calls[-1]
    assert params[0] is False and "page-4" not in params and "page-5" not in params, "the stored cursor is kept"


def test_a_users_push_reads_new_mail_and_still_advances_its_history(monkeypatch):
    result, history, queries, read, _updates = _gmail(monkeypatch, owner=False, processed={"seen-1"})
    assert len(history) == 1, "one history page per sync"
    assert queries[0] == gmail_service._recent_query(PENDING), "the 45-day window, never before the chosen date"
    assert read == ["new-1", "old-1"]
    assert result["duplicates"] == 1 and not result["initial_scan_complete"]


def _outlook(monkeypatch, *, owner):
    connection = {"id": 7, "account_id": "account-x", "workspace_id": "workspace-x", "granted_scopes": ["Mail.Read"],
                  "refresh_token_secret_id": "secret",
                  "initial_scan_page_token": "https://graph.microsoft.com/v1.0/me/messages?$skiptoken=page-4",
                  **{k: PENDING[k] for k in ("import_scope", "import_since", "initial_scan_completed_at")}}
    reads = iter([SimpleNamespace(fetchone=lambda: connection)])

    class Read(_Db):
        def execute(self, query, params=()):
            return next(reads)

    updates = _Db()
    connections = iter([Read(), updates])
    monkeypatch.setattr(ms, "get_connection", lambda: next(connections))
    monkeypatch.setattr(ms, "_has_active_vip_access", lambda *_a: True)
    monkeypatch.setattr(ms, "_vault_read", lambda *_a: "refresh")
    monkeypatch.setattr(ms, "_refresh", lambda *_a: "access")
    monkeypatch.setattr(ms, "owner_account_context", lambda *_a: owner)
    monkeypatch.setattr(owner_mail_automation, "window_since", lambda _connection, chosen: max(chosen, OCT_1))
    monkeypatch.setattr(ms, "already_processed", lambda *_a: set())
    monkeypatch.setattr(ms, "_ingest_message", lambda *_a, **_k: "pending")
    listed = []

    def graph(_token, path, params=None):
        if path.startswith("/me/messages/"):
            return {"subject": "Aviso", "body": {"content": "x"}, "hasAttachments": False}
        listed.append((path, params))
        return {"value": []}

    monkeypatch.setattr(ms, "_graph_get", graph)
    ms.sync_connection(7, trigger="maintenance")
    return connection, listed, updates


def test_an_owner_outlook_sync_reads_the_current_month_and_keeps_its_cursor(monkeypatch):
    connection, listed, updates = _outlook(monkeypatch, owner=True)
    assert [path for path, _ in listed] == ["/me/messages"], "no history page link is followed"
    assert listed[0][1]["$filter"] == "receivedDateTime ge 2026-10-01T00:00:00-06:00"
    assert updates.calls[-1][1][1] == connection["initial_scan_page_token"]


def test_a_users_outlook_sync_reads_history_and_its_45_day_window(monkeypatch):
    _connection, listed, _updates = _outlook(monkeypatch, owner=False)
    paths = [path for path, _ in listed]
    assert paths[0].startswith("https://graph.microsoft.com/") and paths[1] == "/me/messages"
    recent_since = max(date(2026, 1, 1), date.today() - timedelta(days=45))
    assert listed[1][1]["$filter"] == f"receivedDateTime ge {recent_since:%Y-%m-%d}T00:00:00-06:00"


@pytest.mark.parametrize("owner", [True, False])
def test_maintenance_reaches_owner_and_user_connections_alike(monkeypatch, owner):
    """The scheduler (#366) syncs every entitled connection; the Owner/User difference lives in the sync."""
    monkeypatch.setenv("FINVA_GMAIL_CRON_SECRET", "cron-secret")
    monkeypatch.setattr(gmail_service.mail_oauth, "discard_stale_flows", lambda _conn: None)
    monkeypatch.setattr(gmail_service, "end_unentitled_mail_connections", lambda _conn: 0)
    db = _Db()
    db.execute = lambda query, params=(): SimpleNamespace(
        fetchall=lambda: [{"id": 12, "account_id": "account-x", "granted_scopes": [gmail_service.GMAIL_SCOPE]}],
        fetchone=lambda: None)
    monkeypatch.setattr(gmail_service, "get_connection", lambda: db)
    monkeypatch.setattr(gmail_service, "_has_active_vip_access", lambda *_a: True)
    monkeypatch.setattr(gmail_service, "apply_gmail_retention", lambda: {})
    synced = []
    monkeypatch.setattr(gmail_service, "_sync_connection", lambda connection_id, **kwargs: synced.append(kwargs["trigger"]))
    assert gmail_service.gmail_maintenance("cron-secret")["completed"] == 1
    assert synced == ["maintenance"]
