"""Accept/Reject of a mail candidate against a real PostgreSQL.

The app (GmailAutomation) reports only the status the backend answers. That is
correct only if review_gmail_candidate locks the candidate (FOR UPDATE), acts
only on a pending row, commits the status change with its side effects in one
transaction and, for an already-reviewed row, answers the stored status. These
tests prove it on PostgreSQL row locks, including two devices racing.

Uses DINCR_TEST_POSTGRES_URL or the embedded `pgserver`; CI sets
DINCR_REQUIRE_PG_TESTS=1 so they fail instead of skipping. All data is synthetic.
The tables keep only the columns this flow touches, with the real names and
constraints of database/migrations.
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from urllib.parse import urlsplit, urlunsplit

import pytest
from fastapi import HTTPException

psycopg2 = pytest.importorskip("psycopg2")

ACC_A, WS_A = "00000000-0000-4000-8000-0000000000a1", "00000000-0000-4000-8000-00000000000a"
ACC_B, WS_B = "00000000-0000-4000-8000-0000000000b1", "00000000-0000-4000-8000-00000000000b"
USER_A = {"id": 11, "email": "a@example.test", "role": "user", "status": "active", "account_id": ACC_A,
          "account_role": "user", "workspace_id": WS_A, "workspace_role": "owner"}
USER_B = {**USER_A, "id": 12, "email": "b@example.test", "account_id": ACC_B, "workspace_id": WS_B}

SCHEMA = """
CREATE TABLE accounts (id UUID PRIMARY KEY);
CREATE TABLE workspaces (id UUID PRIMARY KEY);
CREATE TABLE allowed_users (id BIGINT PRIMARY KEY);
CREATE TABLE users (id BIGINT PRIMARY KEY);
CREATE TABLE transactions (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(id), transaction_date DATE NOT NULL,
    description TEXT NOT NULL, amount NUMERIC(14,2) NOT NULL, transaction_type TEXT NOT NULL, category TEXT,
    account TEXT, source TEXT, notes TEXT, workspace_id UUID REFERENCES workspaces(id), financial_account_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE financial_input_events (
    id BIGSERIAL PRIMARY KEY, account_id UUID NOT NULL REFERENCES accounts(id), workspace_id UUID NOT NULL REFERENCES workspaces(id),
    user_id BIGINT NOT NULL REFERENCES allowed_users(id), event_name TEXT NOT NULL, contract_version TEXT NOT NULL,
    transaction_id BIGINT NOT NULL REFERENCES transactions(id), payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE UNIQUE INDEX uq_financial_input_events_transaction_contract
    ON financial_input_events(transaction_id,event_name,contract_version);
CREATE TABLE notification_jobs (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT REFERENCES allowed_users(id), workspace_id UUID, title TEXT, body TEXT,
    category TEXT, scheduled_at TIMESTAMPTZ, reference_type TEXT, reference_id TEXT, dedupe_key TEXT UNIQUE, payload JSONB);
CREATE TABLE finva_gmail_connections (
    id BIGSERIAL PRIMARY KEY, account_id UUID NOT NULL REFERENCES accounts(id), workspace_id UUID NOT NULL REFERENCES workspaces(id),
    legacy_user_id BIGINT NOT NULL, granted_scopes TEXT[], status TEXT NOT NULL DEFAULT 'active');
CREATE TABLE finva_email_messages (
    id BIGSERIAL PRIMARY KEY, connection_id BIGINT NOT NULL REFERENCES finva_gmail_connections(id),
    account_id UUID NOT NULL REFERENCES accounts(id), workspace_id UUID NOT NULL REFERENCES workspaces(id),
    status TEXT NOT NULL DEFAULT 'processed');
CREATE TABLE finva_email_candidates (
    id BIGSERIAL PRIMARY KEY, email_message_id BIGINT NOT NULL UNIQUE REFERENCES finva_email_messages(id),
    account_id UUID NOT NULL REFERENCES accounts(id), workspace_id UUID NOT NULL REFERENCES workspaces(id),
    transaction_id BIGINT REFERENCES transactions(id), transaction_date DATE NOT NULL, description TEXT NOT NULL,
    amount NUMERIC(18,2) NOT NULL, currency TEXT NOT NULL DEFAULT 'CRC', transaction_type TEXT NOT NULL,
    category TEXT NOT NULL, bank TEXT NOT NULL, financial_account_id BIGINT, source_type TEXT NOT NULL DEFAULT 'gmail',
    source_provider TEXT NOT NULL DEFAULT 'gmail',
    is_internal_transfer BOOLEAN NOT NULL DEFAULT FALSE, related_candidate_id BIGINT, resolution_reason TEXT,
    corrected_fields TEXT[], reviewed_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','auto_saved','confirmed','rejected','duplicate')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
"""


@pytest.fixture(scope="module")
def admin_uri(tmp_path_factory):
    url = os.getenv("DINCR_TEST_POSTGRES_URL", "").strip()
    if url:
        return url
    try:
        import pgserver
    except ImportError:
        if os.getenv("DINCR_REQUIRE_PG_TESTS") == "1":
            pytest.fail("PostgreSQL tests are required but neither DINCR_TEST_POSTGRES_URL nor pgserver is available.")
        pytest.skip("No PostgreSQL available (set DINCR_TEST_POSTGRES_URL or install pgserver).")
    return pgserver.get_server(tmp_path_factory.mktemp("pgserver"), cleanup_mode="delete").get_uri()


@pytest.fixture
def db(admin_uri, monkeypatch):
    from backend.core import database

    name = f"mail_review_{uuid.uuid4().hex[:12]}"
    admin = psycopg2.connect(admin_uri)
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{name}"')
    parts = urlsplit(admin_uri)
    uri = urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment))
    conn = psycopg2.connect(uri)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(SCHEMA)
        for account, workspace, allowed, legacy, scope in ((ACC_A, WS_A, 11, 77, "gmail.readonly"), (ACC_B, WS_B, 12, 78, "Mail.Read")):
            cur.execute("INSERT INTO accounts VALUES(%s)", (account,))
            cur.execute("INSERT INTO workspaces VALUES(%s)", (workspace,))
            cur.execute("INSERT INTO allowed_users VALUES(%s)", (allowed,))
            cur.execute("INSERT INTO users VALUES(%s)", (legacy,))
            cur.execute(
                "INSERT INTO finva_gmail_connections(account_id,workspace_id,legacy_user_id,granted_scopes) VALUES(%s,%s,%s,%s)",
                (account, workspace, legacy, [scope]),
            )
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    try:
        yield conn
    finally:
        conn.close()
        with admin.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.close()


def _candidate(conn, status="pending", account=ACC_A, workspace=WS_A, provider="gmail") -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM finva_gmail_connections WHERE workspace_id=%s", (workspace,))
        connection_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO finva_email_messages(connection_id,account_id,workspace_id) VALUES(%s,%s,%s) RETURNING id",
            (connection_id, account, workspace),
        )
        message_id = cur.fetchone()[0]
        cur.execute(
            """INSERT INTO finva_email_candidates(email_message_id,account_id,workspace_id,transaction_date,description,
                   amount,transaction_type,category,bank,status,source_provider)
               VALUES(%s,%s,%s,'2026-09-20','Synthetic purchase',1850,'expense','Comida','bac',%s,%s) RETURNING id""",
            (message_id, account, workspace, status, provider),
        )
        return cur.fetchone()[0]


def _review(user, candidate_id, action):
    from backend.auth.current_user import reset_current_user, set_current_user
    from backend.user_product import gmail_service

    token = set_current_user(user)
    try:
        return gmail_service.review_gmail_candidate(candidate_id, action)
    finally:
        reset_current_user(token)


def _state(conn, candidate_id):
    with conn.cursor() as cur:
        cur.execute(
            """SELECT c.status, c.transaction_id, m.status FROM finva_email_candidates c
               JOIN finva_email_messages m ON m.id=c.email_message_id WHERE c.id=%s""",
            (candidate_id,),
        )
        status, transaction_id, message_status = cur.fetchone()
        cur.execute("SELECT COUNT(*) FROM transactions")
        transactions = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM financial_input_events")
        events = cur.fetchone()[0]
    return {"status": status, "transaction_id": transaction_id, "message": message_status,
            "transactions": transactions, "events": events}


@pytest.mark.parametrize(("stored", "action", "answered", "transactions"), [
    ("pending", "accept", "confirmed", 1),
    ("pending", "reject", "rejected", 0),
    ("confirmed", "accept", "confirmed", 0),
    ("rejected", "reject", "rejected", 0),
    ("rejected", "accept", "rejected", 0),   # stale Accept: the stored rejection wins
    ("confirmed", "reject", "confirmed", 0),  # stale Reject: the stored confirmation wins
])
def test_review_answers_the_stored_status(db, stored, action, answered, transactions):
    candidate_id = _candidate(db, stored)
    result = _review(USER_A, candidate_id, action)
    assert result["status"] == answered and result["candidate_id"] == candidate_id
    state = _state(db, candidate_id)
    assert state["status"] == answered
    assert state["transactions"] == transactions and state["events"] == transactions
    if stored == "pending":
        assert state["message"] == answered
        assert (state["transaction_id"] is not None) == (action == "accept")
        assert result["transaction_id"] == state["transaction_id"]


def test_another_workspace_cannot_review_the_candidate(db):
    candidate_id = _candidate(db)
    with pytest.raises(HTTPException) as denied:
        _review(USER_B, candidate_id, "reject")
    assert denied.value.status_code == 404
    assert _state(db, candidate_id)["status"] == "pending"


def _waiting_on_locks(conn) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock'"
        )
        return cur.fetchone()[0]


def _run_blocked(db, blocker, calls):
    """Start the reviews while `blocker` holds the candidate lock, then release it."""
    results, errors = [None] * len(calls), []

    def run(index, user, candidate_id, action):
        try:
            results[index] = _review(user, candidate_id, action)
        except Exception as exc:  # pragma: no cover - surfaced by the assertion below
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(index, *call)) for index, call in enumerate(calls)]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + 10
    while _waiting_on_locks(db) < len(calls) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert _waiting_on_locks(db) == len(calls), "every review waits on the candidate row lock"
    blocker()
    for thread in threads:
        thread.join(15)
    assert not errors and all(result is not None for result in results)
    return results


@pytest.mark.parametrize(("other_device", "stale_action"), [("rejected", "accept"), ("confirmed", "reject")])
def test_stale_device_waits_for_the_lock_and_gets_the_stored_status(db, admin_uri, other_device, stale_action):
    """Device A reviews while device B, still showing 'pending', taps the opposite action."""
    candidate_id = _candidate(db)
    from backend.core import database

    device_a = psycopg2.connect(database.DATABASE_URL)
    with device_a.cursor() as cur:
        cur.execute("SELECT id FROM finva_email_candidates WHERE id=%s FOR UPDATE", (candidate_id,))
        cur.execute("UPDATE finva_email_candidates SET status=%s WHERE id=%s", (other_device, candidate_id))

    [result] = _run_blocked(db, lambda: (device_a.commit(), device_a.close()), [(USER_A, candidate_id, stale_action)])
    assert result["status"] == other_device, "B learns what A stored; it never reports its own action"
    state = _state(db, candidate_id)
    assert state["status"] == other_device and state["transactions"] == 0


@pytest.mark.parametrize("actions", [("accept", "accept"), ("accept", "reject"), ("reject", "accept"), ("reject", "reject")])
def test_simultaneous_reviews_apply_once_and_both_answer_the_stored_status(db, actions):
    candidate_id = _candidate(db)
    from backend.core import database

    holder = psycopg2.connect(database.DATABASE_URL)
    with holder.cursor() as cur:
        cur.execute("SELECT id FROM finva_email_candidates WHERE id=%s FOR UPDATE", (candidate_id,))

    results = _run_blocked(db, lambda: (holder.rollback(), holder.close()),
                           [(USER_A, candidate_id, action) for action in actions])
    state = _state(db, candidate_id)
    assert state["status"] in {"confirmed", "rejected"}
    assert [result["status"] for result in results] == [state["status"]] * 2
    assert state["transactions"] == state["events"] == (1 if state["status"] == "confirmed" else 0)
    target = {"accept": "confirmed", "reject": "rejected"}
    # Exactly the winning action sees its own target; a losing opposite action sees a mismatch.
    assert sum(target[action] == state["status"] for action in actions) >= 1


def test_reviews_of_different_candidates_both_apply(db):
    """Two candidates of the same mailbox reviewed at the same time are both applied."""
    first, second = _candidate(db), _candidate(db)
    from backend.core import database

    holder = psycopg2.connect(database.DATABASE_URL)
    with holder.cursor() as cur:
        cur.execute("SELECT id FROM finva_email_candidates WHERE id IN (%s,%s) FOR UPDATE", (first, second))

    results = _run_blocked(db, lambda: (holder.rollback(), holder.close()),
                           [(USER_A, first, "accept"), (USER_A, second, "reject")])
    assert [result["status"] for result in results] == ["confirmed", "rejected"]
    assert _state(db, first)["status"] == "confirmed" and _state(db, second)["status"] == "rejected"
    assert _state(db, first)["transactions"] == 1


def test_outlook_candidates_use_the_same_review(db):
    """Microsoft mailboxes land in the same tables and go through the same endpoint."""
    candidate_id = _candidate(db, account=ACC_B, workspace=WS_B, provider="microsoft")
    assert _review(USER_B, candidate_id, "accept")["status"] == "confirmed"
    assert _review(USER_B, candidate_id, "reject")["status"] == "confirmed"
    assert _state(db, candidate_id)["transactions"] == 1
