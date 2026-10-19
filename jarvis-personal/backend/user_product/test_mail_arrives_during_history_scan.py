"""New bank mail is read on every sync, even while the history scan of a connection is pending.

Production evidence (2026-10): no connection had finished its history scan, so every sync read
only the next page of older mail and never what had just arrived; and Gmail's watch (push)
expired after 7 days because nothing renewed it outside the maintenance cron. Now each sync,
whatever started it (push, maintenance, manual), reads the recent window as well, skips mail it
already recorded before downloading it, and renews the Gmail watch when it is due. The candidate
pipeline itself (confirmation for Users, the Owner's automation) is unchanged. Synthetic ids only.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.user_product import gmail_service
from backend.user_product import microsoft_mail as ms

BANK = "notificacion@notificacionesbaccr.com"


class _Db:
    def __init__(self, rows=()):
        self.calls, self.rows = [], list(rows)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        self.calls.append((" ".join(query.split()), params))
        return SimpleNamespace(fetchone=lambda: None, fetchall=lambda: self.rows)

    def commit(self):
        pass


def _gmail(monkeypatch, connection, *, history=(), recent=(), processed=(), watched=None):
    monkeypatch.setattr(gmail_service, "_connection_with_token", lambda _id: (connection, "token"))
    monkeypatch.setattr(gmail_service, "_list_message_page",
                        lambda *_args, **_kwargs: ([{"id": i} for i in history], "page-2"))
    queries = []

    def refs(_service, query, _limit):
        queries.append(query)
        return [] if query == gmail_service._aguinaldo_gmail_query() else [{"id": i} for i in recent]

    monkeypatch.setattr(gmail_service, "_list_message_refs", refs)
    monkeypatch.setattr(gmail_service, "already_processed", lambda _id, ids: {i for i in ids if i in processed})
    read = []
    monkeypatch.setattr(gmail_service, "_process_message", lambda _service, _connection, message_id: read.append(message_id) or "pending")
    monkeypatch.setattr(gmail_service, "_start_watch",
                        lambda connection_id, _service, suppress_errors=False: (watched if watched is not None else []).append(connection_id))
    monkeypatch.setattr(gmail_service, "get_connection", _Db)
    return read, queries


PENDING_SCAN = {"id": 5, "import_scope": "current_year", "import_since": None,
                "initial_scan_completed_at": None, "initial_scan_page_token": "page-1",
                "watch_expiration": datetime.now(timezone.utc) + timedelta(days=5)}


def test_gmail_reads_new_mail_while_the_history_scan_is_pending(monkeypatch):
    read, queries = _gmail(monkeypatch, dict(PENDING_SCAN), history=["old-1", "old-2"], recent=["new-1"])
    result = gmail_service._sync_connection(5, service=object(), trigger="push")
    assert "new-1" in read, "a message that just arrived is read on the push sync"
    assert {"old-1", "old-2"} <= set(read), "the history scan still advances"
    assert queries[0] == gmail_service._recent_query(PENDING_SCAN)
    assert result["pending"] == 3 and not result["initial_scan_complete"]


def test_gmail_skips_mail_it_already_recorded_before_downloading_it(monkeypatch):
    read, _ = _gmail(monkeypatch, dict(PENDING_SCAN, initial_scan_completed_at="2026-09-24T12:00:00Z"),
                     recent=["seen-1", "seen-2", "new-1"], processed={"seen-1", "seen-2"})
    result = gmail_service._sync_connection(5, service=object(), trigger="maintenance")
    assert read == ["new-1"]
    assert result["duplicates"] == 2 and result["pending"] == 1


def test_a_message_seen_in_both_windows_is_read_once(monkeypatch):
    read, _ = _gmail(monkeypatch, dict(PENDING_SCAN), history=["same"], recent=["same"])
    gmail_service._sync_connection(5, service=object())
    assert read == ["same"]


@pytest.mark.parametrize(("expiration", "renewed"), [
    (None, True),
    (datetime.now(timezone.utc) - timedelta(days=9), True),
    (datetime.now(timezone.utc) + timedelta(hours=3), True),
    ((datetime.now(timezone.utc) + timedelta(days=4)).isoformat(), False),
])
def test_every_gmail_sync_renews_a_watch_that_is_missing_or_ending(monkeypatch, expiration, renewed):
    watched = []
    _gmail(monkeypatch, dict(PENDING_SCAN, watch_expiration=expiration), watched=watched)
    gmail_service._sync_connection(5, service=object(), trigger="manual")
    assert watched == ([5] if renewed else [])


def test_maintenance_syncs_each_gmail_connection_once_and_the_sync_renews_its_watch(monkeypatch):
    monkeypatch.setenv("FINVA_GMAIL_CRON_SECRET", "cron-secret")
    monkeypatch.setattr(gmail_service.mail_oauth, "discard_stale_flows", lambda _conn: None)
    monkeypatch.setattr(gmail_service, "end_unentitled_mail_connections", lambda _conn: 0)
    monkeypatch.setattr(gmail_service, "get_connection", lambda: _Db([{"id": 5, "account_id": "a", "granted_scopes": [gmail_service.GMAIL_SCOPE]}]))
    monkeypatch.setattr(gmail_service, "_has_active_vip_access", lambda *_args: True)
    monkeypatch.setattr(gmail_service, "apply_gmail_retention", lambda: {})
    monkeypatch.setattr(gmail_service, "_start_watch", lambda *_args, **_kwargs: pytest.fail("the sync renews the watch, not maintenance"))
    synced = []
    monkeypatch.setattr(gmail_service, "_sync_connection", lambda connection_id, **kwargs: synced.append((connection_id, kwargs["trigger"])))
    assert gmail_service.gmail_maintenance("cron-secret")["completed"] == 1
    assert synced == [(5, "maintenance")]


def test_already_processed_rereads_failed_mail_and_unfinished_statements(monkeypatch):
    db = _Db([{"provider_message_id": "seen-1"}])
    monkeypatch.setattr(gmail_service, "get_connection", lambda: db)
    assert gmail_service.already_processed(5, ["seen-1", "new-1"]) == {"seen-1"}
    query, params = db.calls[0]
    assert "status NOT IN ('failed','statement')" in query
    assert params == (5, ["seen-1", "new-1"])
    assert gmail_service.already_processed(5, []) == set()
    assert len(db.calls) == 1, "no query without ids"


def _outlook(monkeypatch, connection, *, history, recent, processed=()):
    reads = iter([SimpleNamespace(fetchone=lambda: connection)])

    class Read(_Db):
        def execute(self, query, params=()):
            return next(reads)

    updates = _Db()
    connections = iter([Read(), updates])
    monkeypatch.setattr(ms, "get_connection", lambda: next(connections))
    monkeypatch.setattr(ms, "_has_active_vip_access", lambda *_args: True)
    monkeypatch.setattr(ms, "_vault_read", lambda *_args: "refresh")
    monkeypatch.setattr(ms, "_refresh", lambda *_args: "access")
    monkeypatch.setattr(ms, "already_processed", lambda _id, ids: {i for i in ids if i in processed})
    listed, fetched = [], []

    def graph(_token, path, params=None):
        if path.startswith("/me/messages/"):
            fetched.append(path.rsplit("/", 1)[-1])
            return {"subject": "Aviso", "body": {"content": "<p>Compra</p>"}, "receivedDateTime": "2026-10-18T10:00:00Z", "hasAttachments": False}
        listed.append(path)
        history_page = path.startswith("https://")
        page = {"value": [{"id": i, "from": {"emailAddress": {"address": BANK}}} for i in (history if history_page else recent)]}
        if history_page:
            page["@odata.nextLink"] = "https://graph.microsoft.com/v1.0/me/messages?$skiptoken=page-3"
        return page

    monkeypatch.setattr(ms, "_graph_get", graph)
    monkeypatch.setattr(ms, "_ingest_message", lambda _connection, message_id, **_kwargs: "pending")
    return listed, fetched, updates


OUTLOOK_PENDING = {"id": 7, "account_id": "account", "workspace_id": "workspace", "granted_scopes": ["Mail.Read"],
                   "refresh_token_secret_id": "secret", "initial_scan_completed_at": None,
                   "initial_scan_page_token": "https://graph.microsoft.com/v1.0/me/messages?$skiptoken=page-2",
                   "import_scope": "current_year", "import_since": None}


def test_outlook_reads_new_mail_while_the_history_scan_is_pending(monkeypatch):
    listed, fetched, updates = _outlook(monkeypatch, dict(OUTLOOK_PENDING), history=["old-1"], recent=["new-1"])
    result = ms.sync_connection(7, trigger="maintenance")
    assert "new-1" in fetched, "a message that just arrived is read"
    assert "old-1" in fetched, "the history scan still advances"
    assert listed[0] == OUTLOOK_PENDING["initial_scan_page_token"]
    # The cursor stored is the history page's next link, not the recent window's.
    assert "page-3" in str(updates.calls[-1][1]) and not result["initial_scan_complete"]


def test_outlook_skips_mail_it_already_recorded_before_downloading_it(monkeypatch):
    _listed, fetched, _updates = _outlook(monkeypatch, dict(OUTLOOK_PENDING, initial_scan_completed_at="2026-09-24T12:00:00Z"),
                                          history=[], recent=["seen-1", "new-1"], processed={"seen-1"})
    result = ms.sync_connection(7, trigger="maintenance")
    assert fetched == ["new-1"]
    assert result["duplicates"] == 1 and result["pending"] == 1
