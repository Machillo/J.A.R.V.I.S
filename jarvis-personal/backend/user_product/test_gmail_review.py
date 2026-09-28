from datetime import date

from backend.user_product import gmail_service
from backend.user_product.financial_candidate import canonical_candidate


class _Result:
    def __init__(self, *, one=None, rows=None):
        self.one = one
        self.rows = rows or []

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query, params=()):
        self.calls.append((query, params))
        if query.startswith(("SAVEPOINT", "RELEASE SAVEPOINT", "ROLLBACK TO SAVEPOINT")):
            return _Result()
        return next(self.results)

    def commit(self):
        self.committed = True


ALLOWED_USER_ID = 12  # allowed_users.id of the authenticated person
LEGACY_USER_ID = 77   # users.id stored on the Gmail connection (legacy finance FK)


def _identity(monkeypatch):
    monkeypatch.setattr(gmail_service, "get_current_account_id", lambda: "account-a")
    monkeypatch.setattr(gmail_service, "get_current_workspace_id", lambda: "workspace-a")
    monkeypatch.setattr(gmail_service, "get_current_user_id", lambda: ALLOWED_USER_ID)


def test_email_inbox_is_scoped_to_account_and_workspace(monkeypatch):
    _identity(monkeypatch)
    connection = _Connection([_Result(rows=[{"email_id": 1, "review_status": "pending"}])])
    monkeypatch.setattr(gmail_service, "get_connection", lambda: connection)

    result = gmail_service.list_gmail_emails("pending")

    query, params = connection.calls[0]
    assert "m.account_id=%s AND m.workspace_id=%s" in query
    assert params == ("account-a", "workspace-a", "pending")
    assert result["items"][0]["email_id"] == 1


def test_accept_candidate_creates_one_transaction_and_confirms(monkeypatch):
    _identity(monkeypatch)
    candidate = {
        "id": 4, "email_message_id": 9, "account_id": "account-a", "workspace_id": "workspace-a",
        "transaction_id": None, "transaction_date": date(2026, 9, 20), "description": "Compra",
        "amount": 1250, "transaction_type": "expense", "category": "food", "bank": "bac",
        "status": "pending", "legacy_user_id": 77,
    }
    connection = _Connection([_Result(one=candidate), _Result(one={"id": 55}), _Result(), _Result(), _Result(), _Result()])
    monkeypatch.setattr(gmail_service, "get_connection", lambda: connection)

    result = gmail_service.review_gmail_candidate(4, "accept")

    first_query, first_params = connection.calls[0]
    assert "c.account_id=%s AND c.workspace_id=%s" in first_query
    assert "g.id=m.connection_id" in first_query
    assert first_params == (4, "account-a", "workspace-a")
    assert sum("INSERT INTO transactions" in query for query, _ in connection.calls) == 1
    assert sum("INSERT INTO financial_input_events" in query for query, _ in connection.calls) == 1
    assert sum("INSERT INTO notification_jobs" in query for query, _ in connection.calls) == 1
    assert result == {"status": "confirmed", "candidate_id": 4, "transaction_id": 55}
    assert connection.committed is True
    update_params = next(params for query, params in connection.calls if "corrected_fields" in query)
    assert update_params[-2] == []


def test_accept_records_fields_corrected_by_user(monkeypatch):
    _identity(monkeypatch)
    candidate = {
        "id": 4, "email_message_id": 9, "account_id": "account-a", "workspace_id": "workspace-a",
        "transaction_id": None, "transaction_date": date(2026, 9, 20), "description": "Compra",
        "amount": 1250, "transaction_type": "expense", "category": "food", "bank": "bac",
        "status": "pending", "legacy_user_id": 77,
    }
    connection = _Connection([_Result(one=candidate), _Result(one={"id": 55}), _Result(), _Result(), _Result(), _Result()])
    monkeypatch.setattr(gmail_service, "get_connection", lambda: connection)

    gmail_service.review_gmail_candidate(
        4,
        "accept",
        {
            "transaction_date": date(2026, 9, 20),
            "description": "Supermercado",
            "amount": 1250,
            "transaction_type": "expense",
            "category": "food",
        },
    )

    update_params = next(params for query, params in connection.calls if "corrected_fields" in query)
    assert update_params[-2] == ["description"]


def test_review_is_idempotent_after_candidate_was_confirmed(monkeypatch):
    _identity(monkeypatch)
    connection = _Connection([_Result(one={"id": 4, "status": "confirmed", "transaction_id": 55})])
    monkeypatch.setattr(gmail_service, "get_connection", lambda: connection)

    result = gmail_service.review_gmail_candidate(4, "accept")

    assert result["transaction_id"] == 55
    assert len(connection.calls) == 1
    assert connection.committed is False


def test_reject_candidate_does_not_create_transaction(monkeypatch):
    _identity(monkeypatch)
    candidate = {"id": 4, "email_message_id": 9, "status": "pending", "transaction_id": None}
    # select, reject candidate, reject message, release statement/notification copies (none)
    connection = _Connection([_Result(one=candidate), _Result(), _Result(), _Result()])
    monkeypatch.setattr(gmail_service, "get_connection", lambda: connection)

    result = gmail_service.review_gmail_candidate(4, "reject")

    assert result["status"] == "rejected"
    assert all("INSERT INTO transactions" not in query for query, _ in connection.calls)
    assert connection.committed is True


def test_accept_internal_transfer_confirms_without_creating_transaction(monkeypatch):
    _identity(monkeypatch)
    candidate = {
        "id": 4, "email_message_id": 9, "account_id": "account-a",
        "workspace_id": "workspace-a", "status": "pending", "transaction_id": None,
        "is_internal_transfer": True,
    }
    connection = _Connection([_Result(one=candidate), _Result(), _Result()])
    monkeypatch.setattr(gmail_service, "get_connection", lambda: connection)

    result = gmail_service.review_gmail_candidate(4, "accept")

    assert result["is_internal_transfer"] is True
    assert result["transaction_id"] is None
    assert all("INSERT INTO transactions" not in query for query, _ in connection.calls)
    assert connection.committed is True


def test_canonical_insert_keeps_statement_link_and_valid_parameter_shape(monkeypatch):
    candidate = canonical_candidate(
        {"bank": "bac", "transaction_date": "2026-09-20", "description": "Compra", "amount": 1250,
         "transaction_type": "expense", "category": "food", "dedupe_key": "one"},
        provider_message_id="gmail-1", subject="Compra",
    )
    candidate.update({"source_type": "statement", "source_provider": "pdf"})

    class _StrictConnection:
        def execute(self, query, params=()):
            assert query.count("%s") == len(params)
            assert params[3] == 88
            return _Result(one={"id": 44})

    monkeypatch.setattr(gmail_service, "discover_candidate_account", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gmail_service, "resolve_candidate", lambda *_args, **_kwargs: {"status": "pending"})
    result = gmail_service._insert_finva_candidate(
        _StrictConnection(), email_message_id=9,
        connection={"account_id": "account-a", "workspace_id": "workspace-a", "legacy_user_id": 7},
        candidate=candidate, statement_document_id=88,
    )
    assert result == {"status": "pending"}


def test_statement_confirmation_records_statement_source():
    connection = _Connection([_Result(one={"id": 55})])
    candidate = {
        "source_type": "statement", "bank": "bac", "legacy_user_id": 77,
        "workspace_id": "workspace-a", "financial_account_id": None,
    }
    gmail_service._create_candidate_transaction(
        connection, candidate,
        {"transaction_date": date(2026, 9, 20), "description": "Compra", "amount": 1250,
         "transaction_type": "expense", "category": "food"},
        {"amount": 1250, "original_amount": None, "original_currency": None, "exchange_rate": None},
    )
    _query, params = connection.calls[0]
    assert params[6] == "finva_statement"


def test_phase_1_contract_excludes_raw_email_and_is_idempotent():
    connection = _Connection([_Result(), _Result()])
    candidate = {
        "account_id": "account-a", "workspace_id": "workspace-a", "legacy_user_id": 77,
        "currency": "CRC", "source_type": "gmail", "financial_account_id": None,
        "raw_payload": {"body": "must never leave ingestion"},
    }
    values = {
        "transaction_date": date(2026, 9, 22), "description": "Supermercado",
        "amount": 4200, "transaction_type": "expense", "category": "food",
    }

    gmail_service._publish_confirmed_financial_input(
        connection, candidate, values, 55, ALLOWED_USER_ID, {"amount": 4200, "original_amount": None, "original_currency": None, "exchange_rate": None},
    )

    event_query, event_params = connection.calls[0]
    notification_query, notification_params = next(
        call for call in connection.calls if "INSERT INTO notification_jobs" in call[0]
    )
    assert "financial-input-v1" in event_query
    assert "ON CONFLICT(transaction_id,event_name,contract_version) DO NOTHING" in event_query
    assert "raw_payload" not in event_params[-1]
    assert "must never leave ingestion" not in event_params[-1]
    assert "ON CONFLICT DO NOTHING" in notification_query
    assert notification_params[-2] == "financial-input-v1:55"


def test_first_sync_query_covers_current_calendar_year(monkeypatch):
    monkeypatch.setattr(gmail_service, "FINVA_QUERY", "(from:bank@example.com) newer_than:45d -in:spam")
    query = gmail_service._year_to_date_query(date(2026, 9, 21))
    assert "newer_than" not in query
    assert "after:1767247200" in query  # 2026-01-01 00:00 Costa Rica
    assert "from:bank@example.com" in query


def test_finva_query_includes_all_verified_popular_domains():
    assert "from:bancopopular.fi.cr" in gmail_service.FINVA_QUERY
    assert "from:bancopopularinforma.fi.cr" in gmail_service.FINVA_QUERY
    assert "from:bpdc.fi.cr" in gmail_service.FINVA_QUERY


def test_message_listing_paginates_but_respects_hard_limit():
    calls = []
    pages = [
        {"messages": [{"id": "1"}, {"id": "2"}], "nextPageToken": "next"},
        {"messages": [{"id": "3"}, {"id": "4"}]},
    ]

    class _ListCall:
        def __init__(self, response): self.response = response
        def execute(self): return self.response

    class _Messages:
        def list(self, **kwargs):
            calls.append(kwargs)
            return _ListCall(pages.pop(0))

    class _Users:
        def messages(self): return _Messages()

    class _Service:
        def users(self): return _Users()

    items = gmail_service._list_message_refs(_Service(), "from:bank", 3)
    assert [item["id"] for item in items] == ["1", "2", "3"]
    assert calls[1]["pageToken"] == "next"


def test_initial_scan_page_returns_resume_cursor():
    class _Call:
        def execute(self): return {"messages": [{"id": "1"}], "nextPageToken": "resume"}
    class _Messages:
        def list(self, **kwargs):
            assert kwargs["maxResults"] == 50
            assert "pageToken" not in kwargs
            return _Call()
    class _Users:
        def messages(self): return _Messages()
    class _Service:
        def users(self): return _Users()

    items, cursor = gmail_service._list_message_page(_Service(), "after:2026/01/01", page_token=None)
    assert items == [{"id": "1"}]
    assert cursor == "resume"


def test_disconnect_revokes_access_without_deleting_financial_history(monkeypatch):
    _identity(monkeypatch)
    connection = _Connection([
        _Result(rows=[{"id": 12, "refresh_token_secret_id": "secret-a"}]), _Result(),
    ])
    monkeypatch.setattr(gmail_service, "get_connection", lambda: connection)
    monkeypatch.setattr(gmail_service, "_vault_read", lambda *_args: "token")
    monkeypatch.setattr(gmail_service, "_vault_delete", lambda *_args: None)
    monkeypatch.setattr(gmail_service.requests, "post", lambda *_args, **_kwargs: None)

    assert gmail_service.disconnect_gmail() == {"status": "disconnected"}
    queries = [query for query, _params in connection.calls]
    assert any("SET status='disabled'" in query for query in queries)
    assert all("DELETE FROM finva_gmail_connections" not in query for query in queries)


def test_gmail_status_lists_independent_connections(monkeypatch):
    _identity(monkeypatch)
    connection = _Connection([
        _Result(rows=[
            {"id": 3, "google_email": "first@gmail.com", "status": "active", "watch_expiration": "tomorrow"},
            {"id": 4, "google_email": "second@gmail.com", "status": "reauthorization_required", "watch_expiration": None},
        ]),
        _Result(one={"total": 2}),
    ])
    monkeypatch.setattr(gmail_service, "get_connection", lambda: connection)
    monkeypatch.setattr(gmail_service, "gmail_consent_status", lambda: {"required": False})
    status = gmail_service.gmail_status()
    assert status["connected"] is True
    assert status["needs_reauthorization"] is True
    assert status["pending"] == 2
    assert [row["google_email"] for row in status["connections"]] == ["first@gmail.com", "second@gmail.com"]
    assert "refresh_token_secret_id" not in str(status)


def test_disconnect_requires_id_when_multiple_emails_exist(monkeypatch):
    from fastapi import HTTPException
    import pytest
    _identity(monkeypatch)
    connection = _Connection([_Result(rows=[{"id": 3}, {"id": 4}])])
    monkeypatch.setattr(gmail_service, "get_connection", lambda: connection)
    with pytest.raises(HTTPException) as exc:
        gmail_service.disconnect_gmail()
    assert exc.value.status_code == 422
    assert connection.committed is False


def test_sync_all_gmail_connections_keeps_success_when_one_fails(monkeypatch):
    _identity(monkeypatch)
    connection = _Connection([_Result(rows=[{"id": 3}, {"id": 4}]), _Result()])
    monkeypatch.setattr(gmail_service, "get_connection", lambda: connection)
    monkeypatch.setattr(gmail_service, "reevaluate_workspace_candidates", lambda *_args, **_kwargs: 0)
    def sync(id):
        if id == 4:
            raise RuntimeError("expired")
        return {"scan_scope": "recent", "initial_scan_complete": True, "found": 4, "pending": 1}
    monkeypatch.setattr(gmail_service, "_sync_connection", sync)
    result = gmail_service.sync_current_gmail()
    assert result["status"] == "partial"
    assert result["failed_connections"] == [4]
    assert result["found"] == 4


def test_accept_paired_own_transfer_confirms_both_notices_without_transactions(monkeypatch):
    _identity(monkeypatch)
    connection = _Connection([
        _Result(one={"id": 9, "status": "pending", "email_message_id": 15,
                     "is_internal_transfer": True, "resolution_reason": "paired_owned_transfer",
                     "related_candidate_id": 10}),
        _Result(), _Result(), _Result(), _Result(),
    ])
    monkeypatch.setattr(gmail_service, "get_connection", lambda: connection)
    result = gmail_service.review_gmail_candidate(9, "accept")
    assert result["is_internal_transfer"] is True
    assert connection.committed is True
    queries = [query for query, _ in connection.calls]
    assert not any("INSERT INTO transactions" in query for query in queries)
    assert any("id=%s AND account_id=%s AND workspace_id=%s" in query and "status='confirmed'" in query for query in queries[3:])


def test_concurrent_sync_of_the_same_message_is_a_duplicate_not_a_crash(monkeypatch):
    # Push and manual sync can both reach a new message; the second INSERT hits
    # UNIQUE(connection_id, provider_message_id) and must not abort the sync.
    connection = _Connection([_Result(one=None), _Result(one=None)])
    monkeypatch.setattr(gmail_service, "get_connection", lambda: connection)
    body = (
        "Comercio:\nSUPERMERCADO EJEMPLO\nFecha:\nSep 22, 2026, 10:15\nVISA\n************1234\n"
        "Autorización:\n123456\nReferencia:\n000011112222\nTipo de Transacción:\nCOMPRA\nMonto:\nCRC 15.000"
    )
    result = gmail_service._ingest_message(
        {"id": 3, "account_id": "account-a", "workspace_id": "workspace-a", "legacy_user_id": LEGACY_USER_ID, "display_name": ""},
        "gmail-9", subject="Notificación de transacción", sender="BAC <notificacion@notificacionesbaccr.com>",
        body=body, received_at="2026-09-22T16:15:00Z",
    )
    assert result == "duplicate"
    assert "ON CONFLICT(connection_id,provider_message_id) DO NOTHING" in connection.calls[1][0]
    assert connection.committed is False
