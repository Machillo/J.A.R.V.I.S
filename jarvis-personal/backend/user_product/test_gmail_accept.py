"""Accept flow for Gmail candidates against a fake DB that enforces the real FKs.

Regression for the HTTP 500 on POST /user-product/vip/gmail/candidates/{id}/accept:
financial_input_events.user_id and notification_jobs.user_id reference
allowed_users(id), while finva_gmail_connections.legacy_user_id is a users.id.
"""
import copy
import logging
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend import main
from backend.auth.current_user import reset_current_user, set_current_user
from backend.user_product import gmail_service
from backend.user_product import routes as user_product_routes

ALLOWED_USER_ID = 12   # allowed_users.id of the person using the app
LEGACY_USER_ID = 77    # users.id kept on the Gmail connection for legacy finance rows
ACCOUNT, WORKSPACE = "account-a", "workspace-a"


class FakeDatabaseError(Exception):
    def __init__(self, message, *, pgcode, table, constraint):
        super().__init__(message)
        self.pgcode = pgcode
        self.diag = SimpleNamespace(table_name=table, constraint_name=constraint, column_name=None)


class FakeDatabase:
    """Committed state plus a per-connection working copy (commit/rollback/savepoints)."""

    def __init__(self):
        self.allowed_users = {ALLOWED_USER_ID}
        self.users = {LEGACY_USER_ID}
        self.state = {
            "candidates": {
                81: self._candidate(81, ACCOUNT, WORKSPACE),
                82: self._candidate(82, "account-b", "workspace-b"),
                83: {**self._candidate(83, ACCOUNT, WORKSPACE), "status": "rejected"},
            },
            "transactions": [], "events": [], "notifications": [],
        }
        self.fail_on = set()

    @staticmethod
    def _candidate(candidate_id, account, workspace):
        return {
            "id": candidate_id, "email_message_id": 900 + candidate_id, "account_id": account,
            "workspace_id": workspace, "transaction_id": None, "transaction_date": date(2026, 9, 20),
            "description": "Compra supermercado", "amount": 18500, "currency": "CRC",
            "transaction_type": "expense", "category": "Comida", "bank": "bac", "status": "pending",
            "source_type": "gmail", "financial_account_id": None, "is_internal_transfer": False,
            "legacy_user_id": LEGACY_USER_ID,
        }

    def connect(self):
        return FakeConnection(self)


class FakeConnection:
    def __init__(self, db):
        self.db = db
        self.work = copy.deepcopy(db.state)
        self.savepoints = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_args):
        return False  # uncommitted work is discarded, like PostgresConnection.rollback()

    def commit(self):
        self.db.state = copy.deepcopy(self.work)

    def _fk(self, value, table, constraint):
        if value not in self.db.allowed_users:
            raise FakeDatabaseError(
                f'insert or update on table "{table}" violates foreign key constraint; Key (user_id)=({value}) not present',
                pgcode="23503", table=table, constraint=constraint,
            )

    def execute(self, query, params=()):
        q = " ".join(query.split())
        if q.startswith("SAVEPOINT "):
            self.savepoints[q.split()[1]] = copy.deepcopy(self.work)
        elif q.startswith("ROLLBACK TO SAVEPOINT "):
            self.work = copy.deepcopy(self.savepoints[q.split()[-1]])
        elif q.startswith("RELEASE SAVEPOINT "):
            self.savepoints.pop(q.split()[-1], None)
        elif q.startswith("SELECT c.*,g.legacy_user_id"):
            candidate_id, account, workspace = params
            row = self.work["candidates"].get(candidate_id)
            if row and row["account_id"] == account and row["workspace_id"] == workspace:
                return SimpleNamespace(fetchone=lambda: dict(row))
            return SimpleNamespace(fetchone=lambda: None)
        elif q.startswith("INSERT INTO transactions"):
            if "transactions" in self.db.fail_on:
                raise FakeDatabaseError("boom", pgcode="23514", table="transactions", constraint="transactions_check")
            transaction_id = 5000 + len(self.work["transactions"])
            self.work["transactions"].append({"id": transaction_id, "user_id": params[8], "workspace_id": params[9]})
            return SimpleNamespace(fetchone=lambda: {"id": transaction_id})
        elif q.startswith("INSERT INTO financial_input_events"):
            self._fk(params[2], "financial_input_events", "financial_input_events_user_id_fkey")
            if all(event["transaction_id"] != params[3] for event in self.work["events"]):
                self.work["events"].append({"user_id": params[2], "transaction_id": params[3]})
        elif q.startswith("INSERT INTO notification_jobs"):
            if "notification_jobs" in self.db.fail_on:
                raise FakeDatabaseError("boom", pgcode="42P01", table="notification_jobs", constraint=None)
            self._fk(params[0], "notification_jobs", "notification_jobs_user_id_fkey")
            self.work["notifications"].append({"user_id": params[0], "dedupe_key": params[5]})
        elif q.startswith("UPDATE finva_email_candidates"):
            row = self.work["candidates"][params[-1]]
            row.update({"transaction_id": params[0], "status": "confirmed"})
        elif q.startswith("UPDATE finva_email_messages"):
            pass
        elif q.startswith("SELECT id FROM finva_email_candidates WHERE account_id=%s AND workspace_id=%s AND related_candidate_id=%s"):
            account, workspace, related, *reasons = params
            return SimpleNamespace(fetchall=lambda: [
                {"id": c["id"]} for c in self.work["candidates"].values()
                if (c["account_id"], c["workspace_id"], c.get("related_candidate_id")) == (account, workspace, related)
                and c["status"] == "duplicate" and c.get("resolution_reason") in reasons
            ], fetchone=lambda: None)
        else:
            raise AssertionError(f"Unexpected query: {q[:80]}")
        return SimpleNamespace(fetchone=lambda: None, fetchall=lambda: [])


@pytest.fixture
def db(monkeypatch):
    database = FakeDatabase()
    monkeypatch.setattr(gmail_service, "get_connection", database.connect)
    return database


@pytest.fixture
def signed_in():
    token = set_current_user({"id": ALLOWED_USER_ID, "account_id": ACCOUNT, "workspace_id": WORKSPACE, "role": "user"})
    yield
    reset_current_user(token)


def test_accept_creates_transaction_and_attributes_events_to_authenticated_user(db, signed_in):
    result = gmail_service.review_gmail_candidate(81, "accept")

    assert result == {"status": "confirmed", "candidate_id": 81, "transaction_id": 5000}
    assert db.state["transactions"] == [{"id": 5000, "user_id": LEGACY_USER_ID, "workspace_id": WORKSPACE}]
    assert db.state["events"] == [{"user_id": ALLOWED_USER_ID, "transaction_id": 5000}]
    assert db.state["notifications"] == [{"user_id": ALLOWED_USER_ID, "dedupe_key": "financial-input-v1:5000"}]
    assert db.state["candidates"][81]["status"] == "confirmed"


def test_second_accept_is_controlled_and_does_not_duplicate(db, signed_in):
    first = gmail_service.review_gmail_candidate(81, "accept")
    second = gmail_service.review_gmail_candidate(81, "accept")

    assert second == {"status": "confirmed", "candidate_id": 81, "transaction_id": first["transaction_id"]}
    assert len(db.state["transactions"]) == 1
    assert len(db.state["events"]) == 1


def test_missing_candidate_returns_404(db, signed_in):
    with pytest.raises(HTTPException) as error:
        gmail_service.review_gmail_candidate(999, "accept")
    assert error.value.status_code == 404


def test_candidate_from_another_account_is_not_visible(db, signed_in):
    with pytest.raises(HTTPException) as error:
        gmail_service.review_gmail_candidate(82, "accept")
    assert error.value.status_code == 404
    assert db.state["candidates"][82]["status"] == "pending"
    assert db.state["transactions"] == []


def test_rejected_candidate_cannot_become_a_transaction(db, signed_in):
    result = gmail_service.review_gmail_candidate(83, "accept")

    assert result == {"status": "rejected", "candidate_id": 83, "transaction_id": None}
    assert db.state["transactions"] == []


def test_failed_transaction_insert_rolls_back_and_candidate_stays_pending(db, signed_in):
    db.fail_on.add("transactions")
    with pytest.raises(FakeDatabaseError):
        gmail_service.review_gmail_candidate(81, "accept")

    assert db.state["candidates"][81]["status"] == "pending"
    assert db.state["transactions"] == [] and db.state["events"] == []

    db.fail_on.clear()
    assert gmail_service.review_gmail_candidate(81, "accept")["status"] == "confirmed"


def test_notification_failure_cannot_turn_a_valid_accept_into_an_error(db, signed_in, caplog):
    db.fail_on.add("notification_jobs")
    with caplog.at_level(logging.WARNING):
        result = gmail_service.review_gmail_candidate(81, "accept")

    assert result["status"] == "confirmed"
    assert len(db.state["transactions"]) == 1 and len(db.state["events"]) == 1
    assert db.state["notifications"] == []
    assert "notification skipped" in caplog.text and "Compra" not in caplog.text


def test_legacy_users_id_is_rejected_by_allowed_users_foreign_key(db):
    """Documents the production failure: the old code passed legacy_user_id (77)."""
    connection = db.connect()
    candidate = db.state["candidates"][81]
    values = {key: candidate[key] for key in ("transaction_date", "description", "amount", "transaction_type", "category")}
    with pytest.raises(FakeDatabaseError) as error:
        gmail_service._publish_confirmed_financial_input(
            connection, candidate, values, 5000, LEGACY_USER_ID, {"amount": values["amount"], "original_amount": None, "original_currency": None, "exchange_rate": None},
        )
    assert error.value.pgcode == "23503"


# HTTP layer ---------------------------------------------------------------

@pytest.fixture
def client(db, monkeypatch):
    user = {"id": ALLOWED_USER_ID, "account_id": ACCOUNT, "workspace_id": WORKSPACE, "role": "user", "email": "person@example.com"}
    monkeypatch.setattr(main, "authenticate_access_token", lambda _token: user)
    monkeypatch.setattr(main, "disabled_feature_for_request", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(user_product_routes, "require_feature", lambda *_args, **_kwargs: None)
    return TestClient(main.app, raise_server_exceptions=False)


AUTH = {"Authorization": "Bearer test-token"}


def test_http_accept_returns_200_with_transaction(client, db):
    response = client.post("/user-product/vip/gmail/candidates/81/accept", headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {"status": "confirmed", "candidate_id": 81, "transaction_id": 5000}


def test_http_accept_unknown_candidate_returns_404(client):
    response = client.post("/user-product/vip/gmail/candidates/999/accept", headers=AUTH)
    assert response.status_code == 404


def test_http_unexpected_error_is_safe_for_client_and_diagnosable_in_logs(client, db, monkeypatch, caplog):
    def failing_publish(*_args, **_kwargs):
        raise FakeDatabaseError(
            "Key (email)=(person@example.com) already exists; amount 18500",
            pgcode="23505", table="financial_input_events", constraint="uq_example",
        )
    monkeypatch.setattr(gmail_service, "_publish_confirmed_financial_input", failing_publish)

    with caplog.at_level(logging.ERROR, logger="jarvis.api"):
        response = client.post("/user-product/vip/gmail/candidates/81/accept", headers=AUTH)

    body = response.json()
    assert response.status_code == 500
    assert body["detail"] == "Ocurrió un error interno. Intentá nuevamente."
    assert body["error_id"] == body["request_id"]
    log = caplog.text
    assert body["error_id"] in log
    assert "FakeDatabaseError pgcode=23505 table=financial_input_events constraint=uq_example" in log
    assert "gmail_service.py" in log and "review_gmail_candidate" in log
    assert "person@example.com" not in log and "18500" not in log
    assert db.state["candidates"][81]["status"] == "pending"
