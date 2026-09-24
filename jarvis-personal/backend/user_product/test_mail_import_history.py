"""History the user chooses before connecting a mailbox: stored server-side on the
OAuth flow, copied to the connection, and applied to the first Gmail/Outlook sync."""
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend import main
from backend.user_product import gmail_service, mail_oauth
from backend.user_product import microsoft_mail as ms
from backend.user_product import routes as user_product_routes
from backend.user_product.test_mail_oauth import A, BEGIN, PROVIDERS, _as, callback, complete, env  # noqa: F401

TODAY = date(2026, 9, 24)
MONTH_START, YEAR_START = date(2026, 9, 1), date(2026, 1, 1)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    original = mail_oauth.import_since
    monkeypatch.setattr(mail_oauth, "import_since", lambda scope, today=None: original(scope, today or TODAY))


def connect(env, provider, scope=None, mailbox="a@example.com"):
    begin = {"gmail": gmail_service.begin_gmail_connection, "microsoft": ms.begin_connection}[provider]
    url = _as(A, begin, *([scope] if scope else []))["authorization_url"]
    _status, params = callback(provider, *env.provider.authorize(url, mailbox))
    complete(A, params)
    return next(c for c in env.db.state["connections"].values() if c["google_email"] == mailbox)


def test_import_since_is_the_first_day_of_the_month_or_year():
    assert mail_oauth.import_since("current_month", date(2026, 9, 24)) == MONTH_START
    assert mail_oauth.import_since("current_year", date(2026, 9, 24)) == YEAR_START
    assert mail_oauth.import_since("current_month", date(2027, 1, 1)) == date(2027, 1, 1)


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize(("scope", "since"), [("current_month", MONTH_START), ("current_year", YEAR_START)])
def test_the_choice_travels_with_the_flow_to_the_connection(env, provider, scope, since):
    connection = connect(env, provider, scope)
    assert (connection["import_scope"], connection["import_since"]) == (scope, since)
    flow = next(iter(env.db.state["flows"].values()))
    assert flow["import_scope"] == scope


@pytest.mark.parametrize("provider", PROVIDERS)
def test_no_choice_keeps_the_previous_current_year_window(env, provider):
    connection = connect(env, provider)
    assert (connection["import_scope"], connection["import_since"]) == ("current_year", YEAR_START)


@pytest.mark.parametrize("provider", PROVIDERS)
def test_an_unknown_choice_is_rejected_before_any_flow_exists(env, provider):
    with pytest.raises(HTTPException) as error:
        _as(A, {"gmail": gmail_service.begin_gmail_connection, "microsoft": ms.begin_connection}[provider], "since_2010")
    assert error.value.status_code == 422
    assert env.db.state["flows"] == {}


@pytest.mark.parametrize("provider", PROVIDERS)
def test_reconnecting_with_a_longer_history_restarts_the_initial_scan(env, provider):
    connect(env, provider, "current_month")
    stored = next(iter(env.db.state["connections"].values()))
    stored.update(initial_scan_completed_at="2026-09-24T12:00:00Z", initial_scan_page_token=None)
    connection = connect(env, provider, "current_year")
    assert (connection["import_scope"], connection["import_since"]) == ("current_year", YEAR_START)
    assert connection["initial_scan_completed_at"] is None  # the earlier months are scanned now
    assert len(env.db.state["connections"]) == 1


@pytest.mark.parametrize("provider", PROVIDERS)
def test_reconnecting_with_a_shorter_history_keeps_what_was_imported(env, provider):
    connect(env, provider, "current_year")
    stored = next(iter(env.db.state["connections"].values()))
    stored.update(initial_scan_completed_at="2026-09-24T12:00:00Z", initial_scan_page_token="page-3")
    connection = connect(env, provider, "current_month")
    assert (connection["import_scope"], connection["import_since"]) == ("current_year", YEAR_START)
    assert connection["initial_scan_completed_at"] == "2026-09-24T12:00:00Z"
    assert connection["initial_scan_page_token"] == "page-3"


@pytest.mark.parametrize("provider", PROVIDERS)
def test_connections_from_before_the_choice_count_as_current_year(env, provider):
    connect(env, provider, "current_year")
    stored = next(iter(env.db.state["connections"].values()))
    stored.update(import_scope=None, import_since=None, initial_scan_completed_at="2026-03-01T00:00:00Z")
    connection = connect(env, provider, "current_month")
    assert (connection["import_scope"], connection["import_since"]) == ("current_year", YEAR_START)
    assert connection["initial_scan_completed_at"] == "2026-03-01T00:00:00Z"


def test_connect_routes_pass_the_choice_and_default_to_the_current_year(monkeypatch):
    user = {**A, "email": "persona@example.com"}
    monkeypatch.setattr(main, "authenticate_access_token", lambda _token, **_kwargs: user)
    monkeypatch.setattr(main, "disabled_feature_for_request", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(user_product_routes, "require_feature", lambda *_args, **_kwargs: None)
    received = []
    monkeypatch.setattr(user_product_routes, "begin_gmail_connection", lambda scope: received.append(("gmail", scope)) or {"authorization_url": "x"})
    monkeypatch.setattr(user_product_routes, "begin_microsoft_connection", lambda scope: received.append(("microsoft", scope)) or {"authorization_url": "x"})
    client, auth = TestClient(main.app), {"Authorization": "Bearer t"}
    assert client.post("/user-product/vip/gmail/connect", headers=auth).status_code == 200
    assert client.post("/user-product/vip/gmail/connect", headers=auth, json={"import_scope": "current_month"}).status_code == 200
    assert client.post("/user-product/vip/mail/microsoft/connect", headers=auth, json={"import_scope": "current_year"}).status_code == 200
    assert client.post("/user-product/vip/gmail/connect", headers=auth, json={"import_scope": "everything"}).status_code == 422
    assert received == [("gmail", "current_year"), ("gmail", "current_month"), ("microsoft", "current_year")]


class _Updates:
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


@pytest.mark.parametrize(("scope", "since", "scan_scope"), [
    ("current_month", MONTH_START, "current_month"), ("current_year", YEAR_START, "year_to_date"), (None, YEAR_START, "year_to_date"),
])
def test_first_gmail_sync_searches_from_the_chosen_date(monkeypatch, scope, since, scan_scope):
    connection = {"id": 5, "import_scope": scope, "import_since": since if scope else None,
                  "initial_scan_completed_at": None, "initial_scan_page_token": None}
    monkeypatch.setattr(gmail_service, "_connection_with_token", lambda _id: (connection, "token"))
    queries = []
    monkeypatch.setattr(gmail_service, "_list_message_page", lambda _service, query, **_kwargs: queries.append(query) or ([], None))
    monkeypatch.setattr(gmail_service, "_list_message_refs", lambda *_args: [])
    monkeypatch.setattr(gmail_service, "get_connection", _Updates)
    result = gmail_service._sync_connection(5, service=object())
    assert f"after:{gmail_service._cr_midnight_epoch(since)}" in queries[0] and "newer_than" not in queries[0]
    assert result["scan_scope"] == scan_scope and result["initial_scan_complete"]


original_recent = gmail_service._recent_query


def test_cr_midnight_is_six_hours_after_utc_midnight():
    assert gmail_service._cr_midnight_epoch(date(2026, 1, 1)) == 1767247200  # 2026-01-01T06:00:00Z


def test_recent_gmail_window_is_unchanged_when_the_choice_is_older():
    assert original_recent({"import_since": YEAR_START}, TODAY) == gmail_service.FINVA_QUERY
    assert original_recent({"import_since": None}, TODAY) == gmail_service.FINVA_QUERY


def test_later_gmail_syncs_keep_the_recent_window(monkeypatch):
    connection = {"id": 5, "import_scope": "current_month", "import_since": MONTH_START,
                  "initial_scan_completed_at": "2026-09-24T12:00:00Z"}
    monkeypatch.setattr(gmail_service, "_connection_with_token", lambda _id: (connection, "token"))
    monkeypatch.setattr(gmail_service, "_list_message_page", lambda *_args, **_kwargs: pytest.fail("initial scan is done"))
    queries = []
    monkeypatch.setattr(gmail_service, "_list_message_refs", lambda _service, query, _limit: queries.append(query) or [])
    monkeypatch.setattr(gmail_service, "get_connection", _Updates)
    monkeypatch.setattr(gmail_service, "_recent_query", lambda connection: original_recent(connection, TODAY))
    assert gmail_service._sync_connection(5, service=object())["scan_scope"] == "recent"
    # Chosen 1 Sept, 23 days ago: the 45-day window must not reach into August.
    assert queries[0] == f"{gmail_service.FINVA_QUERY} after:{gmail_service._cr_midnight_epoch(MONTH_START)}"


@pytest.mark.parametrize(("scope", "since"), [("current_month", MONTH_START), (None, YEAR_START)])
def test_first_outlook_sync_filters_from_the_chosen_date(monkeypatch, scope, since):
    connection = {"id": 7, "account_id": "account", "granted_scopes": ["Mail.Read"], "refresh_token_secret_id": "secret",
                  "initial_scan_completed_at": None, "initial_scan_page_token": None,
                  "import_scope": scope, "import_since": since if scope else None}
    reads = iter([SimpleNamespace(fetchone=lambda: connection)])
    class Read(_Updates):
        def execute(self, query, params=()):
            return next(reads)
    connections = iter([Read(), _Updates()])
    monkeypatch.setattr(ms, "get_connection", lambda: next(connections))
    monkeypatch.setattr(ms, "_has_active_vip_access", lambda *_args: True)
    monkeypatch.setattr(ms, "_vault_read", lambda *_args: "refresh")
    monkeypatch.setattr(ms, "_refresh", lambda *_args: "access")
    calls = []
    monkeypatch.setattr(ms, "_graph_get", lambda _token, path, params=None: calls.append(params) or {"value": []})
    result = ms.sync_connection(7)
    assert calls[0]["$filter"] == f"receivedDateTime ge {since:%Y-%m-%d}T00:00:00-06:00"
    assert result["scan_scope"] == ("current_month" if scope == "current_month" else "year_to_date")


def test_a_sync_only_advances_the_cursor_of_the_window_it_scanned(monkeypatch):
    connection = {"id": 5, "import_scope": "current_month", "import_since": MONTH_START,
                  "initial_scan_completed_at": None, "initial_scan_page_token": None}
    monkeypatch.setattr(gmail_service, "_connection_with_token", lambda _id: (connection, "token"))
    monkeypatch.setattr(gmail_service, "_list_message_page", lambda *_args, **_kwargs: ([], None))
    monkeypatch.setattr(gmail_service, "_list_message_refs", lambda *_args: [])
    updates = _Updates()
    monkeypatch.setattr(gmail_service, "get_connection", lambda: updates)
    gmail_service._sync_connection(5, service=object())
    query, params = updates.calls[-1]
    assert "initial_scan_page_token=CASE WHEN %s AND import_since IS NOT DISTINCT FROM %s::date" in query
    assert "initial_scan_completed_at=CASE WHEN %s AND %s IS NULL AND import_since IS NOT DISTINCT FROM %s::date" in query
    assert params.count(MONTH_START) == 2


def test_later_outlook_syncs_never_reach_before_the_chosen_date(monkeypatch):
    recent = {"id": 7, "account_id": "account", "granted_scopes": ["Mail.Read"], "refresh_token_secret_id": "secret",
              "initial_scan_completed_at": "2026-09-02T00:00:00Z", "initial_scan_page_token": None,
              "import_scope": "current_month", "import_since": date.today().replace(day=1)}
    reads = iter([SimpleNamespace(fetchone=lambda: recent)])
    class Read(_Updates):
        def execute(self, query, params=()):
            return next(reads)
    updates = _Updates()
    connections = iter([Read(), updates])
    monkeypatch.setattr(ms, "get_connection", lambda: next(connections))
    monkeypatch.setattr(ms, "_has_active_vip_access", lambda *_args: True)
    monkeypatch.setattr(ms, "_vault_read", lambda *_args: "refresh")
    monkeypatch.setattr(ms, "_refresh", lambda *_args: "access")
    calls = []
    monkeypatch.setattr(ms, "_graph_get", lambda _token, path, params=None: calls.append(params) or {"value": []})
    ms.sync_connection(7)
    assert calls[0]["$filter"] == f"receivedDateTime ge {date.today().replace(day=1):%Y-%m-%d}T00:00:00-06:00"
    assert "import_since IS NOT DISTINCT FROM %s::date" in updates.calls[-1][0]
