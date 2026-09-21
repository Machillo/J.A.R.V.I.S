from datetime import date

from backend.user_product import gmail_service


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
        return next(self.results)

    def commit(self):
        self.committed = True


def _identity(monkeypatch):
    monkeypatch.setattr(gmail_service, "get_current_account_id", lambda: "account-a")
    monkeypatch.setattr(gmail_service, "get_current_workspace_id", lambda: "workspace-a")


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
    connection = _Connection([_Result(one=candidate), _Result(one={"id": 55}), _Result(), _Result()])
    monkeypatch.setattr(gmail_service, "get_connection", lambda: connection)

    result = gmail_service.review_gmail_candidate(4, "accept")

    first_query, first_params = connection.calls[0]
    assert "c.account_id=%s AND c.workspace_id=%s" in first_query
    assert first_params == (4, "account-a", "workspace-a")
    assert sum("INSERT INTO transactions" in query for query, _ in connection.calls) == 1
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
    connection = _Connection([_Result(one=candidate), _Result(one={"id": 55}), _Result(), _Result()])
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
    connection = _Connection([_Result(one=candidate), _Result(), _Result()])
    monkeypatch.setattr(gmail_service, "get_connection", lambda: connection)

    result = gmail_service.review_gmail_candidate(4, "reject")

    assert result["status"] == "rejected"
    assert all("INSERT INTO transactions" not in query for query, _ in connection.calls)
    assert connection.committed is True
