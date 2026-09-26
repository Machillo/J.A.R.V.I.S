"""Accepting a USD mail/statement candidate against a real PostgreSQL.

The real review_gmail_candidate runs on real connections (row locks, NUMERIC
columns, the financial_input_events contract). A USD movement is saved with the
user's rate, never the parser's matching-only amount; a missing rate leaves no
trace; two concurrent Accepts save one transaction. Synthetic data only.

Uses the embedded server of test_financial_ownership_integrity_pg.py
(DINCR_TEST_POSTGRES_URL or pgserver; CI sets DINCR_REQUIRE_PG_TESTS=1).
"""
from __future__ import annotations

import threading
import uuid

import pytest
from fastapi import HTTPException

from backend.tests.test_financial_ownership_integrity_pg import BASELINE, _admin_uri, _with_database

psycopg2 = pytest.importorskip("psycopg2")
from psycopg2.extras import RealDictCursor  # noqa: E402

from backend.auth.current_user import reset_current_user, set_current_user  # noqa: E402
from backend.core import database  # noqa: E402
from backend.user_product import gmail_service  # noqa: E402
from backend.user_product.models import GmailCandidateReviewRequest  # noqa: E402

A = {"allowed": 21, "users": 31, "account": "00000000-0000-4000-8000-0000000001a1",
     "workspace": "00000000-0000-4000-8000-0000000001a0", "base": "CRC"}
B = {"allowed": 22, "users": 32, "account": "00000000-0000-4000-8000-0000000001b1",
     "workspace": "00000000-0000-4000-8000-0000000001b0", "base": "USD"}

SCHEMA = """
ALTER TABLE accounts ADD COLUMN base_currency TEXT NOT NULL DEFAULT 'CRC';
CREATE TABLE transactions (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL, transaction_date TEXT NOT NULL,
    description TEXT NOT NULL, amount NUMERIC(14,2) NOT NULL, transaction_type TEXT NOT NULL,
    category TEXT NOT NULL, account TEXT, source TEXT, notes TEXT,
    original_amount NUMERIC(14,2), original_currency TEXT, exchange_rate NUMERIC(14,6),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), workspace_id UUID, financial_account_id BIGINT
);
CREATE TABLE finva_gmail_connections (
    id BIGSERIAL PRIMARY KEY, account_id UUID NOT NULL REFERENCES accounts(id),
    workspace_id UUID NOT NULL REFERENCES workspaces(id), legacy_user_id BIGINT NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'active'
);
CREATE TABLE finva_email_messages (
    id BIGSERIAL PRIMARY KEY, connection_id BIGINT NOT NULL REFERENCES finva_gmail_connections(id),
    account_id UUID NOT NULL REFERENCES accounts(id), workspace_id UUID NOT NULL REFERENCES workspaces(id),
    provider_message_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending'
);
CREATE TABLE finva_email_candidates (
    id BIGSERIAL PRIMARY KEY, email_message_id BIGINT NOT NULL REFERENCES finva_email_messages(id),
    account_id UUID NOT NULL REFERENCES accounts(id), workspace_id UUID NOT NULL REFERENCES workspaces(id),
    transaction_id BIGINT REFERENCES transactions(id), transaction_date DATE NOT NULL,
    description TEXT NOT NULL, amount NUMERIC(18,2) NOT NULL, currency TEXT NOT NULL DEFAULT 'CRC',
    original_amount NUMERIC(18,2), original_currency TEXT, transaction_type TEXT NOT NULL,
    category TEXT NOT NULL, bank TEXT NOT NULL, source_type TEXT NOT NULL DEFAULT 'email',
    source_provider TEXT NOT NULL DEFAULT 'gmail', financial_account_id BIGINT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'auto_saved', 'confirmed', 'rejected', 'duplicate')),
    is_internal_transfer BOOLEAN NOT NULL DEFAULT FALSE, related_candidate_id BIGINT, resolution_reason TEXT,
    reviewed_at TIMESTAMPTZ, corrected_fields TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE financial_input_events (
    id BIGSERIAL PRIMARY KEY, account_id UUID NOT NULL REFERENCES accounts(id),
    workspace_id UUID NOT NULL REFERENCES workspaces(id), user_id BIGINT NOT NULL REFERENCES allowed_users(id),
    event_name TEXT NOT NULL, contract_version TEXT NOT NULL,
    transaction_id BIGINT NOT NULL REFERENCES transactions(id), payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (event_name = 'transaction_confirmed' AND contract_version = 'financial-input-v1'),
    CHECK (NOT (payload ?| ARRAY['raw_payload','body','attachment_text','sender','subject']))
);
CREATE UNIQUE INDEX ON financial_input_events(transaction_id,event_name,contract_version);
CREATE TABLE notification_jobs (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES allowed_users(id), workspace_id UUID,
    title TEXT NOT NULL, body TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'general',
    scheduled_at TIMESTAMPTZ NOT NULL, status TEXT NOT NULL DEFAULT 'pending', reference_type TEXT,
    reference_id TEXT, dedupe_key TEXT, payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(workspace_id, dedupe_key)
);
"""

BAC_USD = {"amount": 10395, "currency": "CRC", "original_amount": 21, "original_currency": "USD"}  # parser @495
MULTIMONEY_USD = {"amount": 50, "currency": "CRC", "original_amount": 50, "original_currency": "USD"}  # unconverted


@pytest.fixture(scope="module")
def admin_uri(tmp_path_factory):
    return _admin_uri(tmp_path_factory.mktemp("pgserver-mail-currency"))


@pytest.fixture
def pg(admin_uri, monkeypatch):
    name = f"mail_currency_{uuid.uuid4().hex[:12]}"
    admin = psycopg2.connect(admin_uri)
    admin.autocommit = True
    with admin.cursor() as cur:
        for role in ("anon", "authenticated"):
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,))
            if not cur.fetchone():
                cur.execute(f'CREATE ROLE "{role}" NOLOGIN')
        cur.execute(f'CREATE DATABASE "{name}"')
    uri = _with_database(admin_uri, name)
    conn = psycopg2.connect(uri, cursor_factory=RealDictCursor)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(BASELINE.read_text(encoding="utf-8"))
        cur.execute(SCHEMA)
        for ident in (A, B):
            cur.execute("INSERT INTO allowed_users(id,email,role,status) VALUES(%s,%s,'user','active')",
                        (ident["allowed"], f"{ident['allowed']}@example.test"))
            cur.execute("INSERT INTO users(id,email,name,country,timezone) VALUES(%s,%s,'Synthetic','Nowhere','UTC')",
                        (ident["users"], f"{ident['users']}@example.test"))
            cur.execute("INSERT INTO accounts(id,legacy_allowed_user_id,primary_email,base_currency) VALUES(%s,%s,%s,%s)",
                        (ident["account"], ident["allowed"], f"{ident['allowed']}@example.test", ident["base"]))
            cur.execute("INSERT INTO workspaces(id,workspace_key,owner_account_id,name) VALUES(%s,%s,%s,'Personal')",
                        (ident["workspace"], f"personal:{ident['account']}", ident["account"]))
            cur.execute("INSERT INTO finva_gmail_connections(account_id,workspace_id,legacy_user_id) VALUES(%s,%s,%s) RETURNING id",
                        (ident["account"], ident["workspace"], ident["users"]))
            ident["connection"] = cur.fetchone()["id"]
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    try:
        yield conn
    finally:
        conn.close()
        with admin.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.close()


def _candidate(pg, ident, *, amount=18500, currency="CRC", original_amount=None, original_currency=None,
               provider="gmail", source_type="email") -> int:
    with pg.cursor() as cur:
        cur.execute(
            "INSERT INTO finva_email_messages(connection_id,account_id,workspace_id,provider_message_id) VALUES(%s,%s,%s,%s) RETURNING id",
            (ident["connection"], ident["account"], ident["workspace"], uuid.uuid4().hex),
        )
        message_id = cur.fetchone()["id"]
        cur.execute(
            """INSERT INTO finva_email_candidates(email_message_id,account_id,workspace_id,transaction_date,description,
                   amount,currency,original_amount,original_currency,transaction_type,category,bank,source_type,source_provider)
               VALUES(%s,%s,%s,'2026-09-20','HOSTING EJEMPLO',%s,%s,%s,%s,'expense','Servicios','bac',%s,%s) RETURNING id""",
            (message_id, ident["account"], ident["workspace"], amount, currency, original_amount, original_currency,
             source_type, provider),
        )
        return cur.fetchone()["id"]


def _as(ident, fn, *args):
    token = set_current_user({"id": ident["allowed"], "account_id": ident["account"],
                              "workspace_id": ident["workspace"], "role": "user"})
    try:
        return fn(*args)
    finally:
        reset_current_user(token)


def _corrections(amount, rate=None, **extra):
    return GmailCandidateReviewRequest(
        transaction_date="2026-09-20", description="HOSTING EJEMPLO", amount=amount,
        transaction_type="expense", category="Servicios", exchange_rate=rate, **extra,
    ).model_dump()


def _one(pg, query, params=()):
    with pg.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchone()


def _all(pg, query, params=()):
    with pg.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchall()


def _nothing_written(pg, candidate_id):
    assert _one(pg, "SELECT COUNT(*) AS n FROM transactions")["n"] == 0
    assert _one(pg, "SELECT COUNT(*) AS n FROM financial_input_events")["n"] == 0
    assert _one(pg, "SELECT COUNT(*) AS n FROM notification_jobs")["n"] == 0
    row = _one(pg, """SELECT c.status,c.transaction_id,c.reviewed_at,c.corrected_fields,c.amount,c.original_amount,
                             m.status AS message_status
                      FROM finva_email_candidates c JOIN finva_email_messages m ON m.id=c.email_message_id
                      WHERE c.id=%s""", (candidate_id,))
    assert row["status"] == "pending" and row["transaction_id"] is None and row["reviewed_at"] is None
    assert row["corrected_fields"] == [] and row["message_status"] == "pending"
    return row


# --------------------------------------------------------------------------- missing rate: atomic 422

@pytest.mark.parametrize("corrections", [None, "no-rate"])
def test_a_usd_candidate_without_a_rate_leaves_no_trace(pg, corrections):
    candidate_id = _candidate(pg, A, **BAC_USD)
    with pytest.raises(HTTPException) as error:
        _as(A, gmail_service.review_gmail_candidate, candidate_id, "accept",
            _corrections(21) if corrections else None)
    assert error.value.status_code == 422
    row = _nothing_written(pg, candidate_id)
    assert (float(row["amount"]), float(row["original_amount"])) == (10395.0, 21.0)


def test_a_legacy_base_currency_cannot_convert_and_leaves_no_trace(pg):
    with pg.cursor() as cur:
        cur.execute("UPDATE accounts SET base_currency='EUR' WHERE id=%s", (A["account"],))
    candidate_id = _candidate(pg, A)
    with pytest.raises(HTTPException) as error:
        _as(A, gmail_service.review_gmail_candidate, candidate_id, "accept", _corrections(18500, rate=505))
    assert error.value.status_code == 422 and "no puede convertirlo" in error.value.detail
    _nothing_written(pg, candidate_id)


# --------------------------------------------------------------------------- financial truth

@pytest.mark.parametrize("provider,source_type", [("gmail", "email"), ("microsoft", "email"), ("pdf", "statement")])
def test_a_bac_usd_candidate_is_saved_with_the_users_rate_everywhere(pg, provider, source_type):
    candidate_id = _candidate(pg, A, provider=provider, source_type=source_type, **BAC_USD)
    result = _as(A, gmail_service.review_gmail_candidate, candidate_id, "accept", _corrections(21, rate=505))
    assert result["status"] == "confirmed"
    tx = _one(pg, "SELECT * FROM transactions")
    assert (str(tx["amount"]), str(tx["original_amount"]), tx["original_currency"], str(tx["exchange_rate"])) == \
        ("10605.00", "21.00", "USD", "505.000000"), "21 USD at the user's 505, never the parser's 10,395"
    assert tx["workspace_id"] == A["workspace"] and tx["user_id"] == A["users"]
    event = _one(pg, "SELECT * FROM financial_input_events")
    assert (event["account_id"], event["workspace_id"], event["user_id"]) == (A["account"], A["workspace"], A["allowed"])
    payload = event["payload"]
    assert (payload["amount"], payload["currency"]) == (10605.0, "CRC")
    assert (payload["original_amount"], payload["original_currency"], payload["exchange_rate"]) == (21.0, "USD", 505.0)
    (notice,) = _all(pg, "SELECT body FROM notification_jobs")
    assert "10,605.00 CRC" in notice["body"] and "10,395" not in notice["body"]
    candidate = _one(pg, "SELECT * FROM finva_email_candidates WHERE id=%s", (candidate_id,))
    assert candidate["status"] == "confirmed" and candidate["transaction_id"] == tx["id"]
    # The matching-only representation keeps its meaning for cross-source dedupe.
    assert (str(candidate["amount"]), candidate["currency"], str(candidate["original_amount"]), candidate["original_currency"]) == \
        ("10395.00", "CRC", "21.00", "USD")
    assert candidate["corrected_fields"] == [], "the same values typed back are not a correction"
    # Nothing financial carries the matching value.
    assert "10395" not in str(payload) and str(tx["amount"]) != "10395.00"


def test_multimoney_usd_50_is_never_saved_as_50_colones(pg):
    candidate_id = _candidate(pg, A, **MULTIMONEY_USD)
    _as(A, gmail_service.review_gmail_candidate, candidate_id, "accept", _corrections(50, rate=500))
    tx = _one(pg, "SELECT amount,original_amount,original_currency,exchange_rate FROM transactions")
    assert (str(tx["amount"]), str(tx["original_amount"]), tx["original_currency"]) == ("25000.00", "50.00", "USD")


def test_a_correction_is_typed_in_the_native_currency(pg):
    candidate_id = _candidate(pg, A, **BAC_USD)
    _as(A, gmail_service.review_gmail_candidate, candidate_id, "accept", _corrections(20, rate=505))
    tx = _one(pg, "SELECT amount,original_amount FROM transactions")
    assert (str(tx["amount"]), str(tx["original_amount"])) == ("10100.00", "20.00")
    candidate = _one(pg, "SELECT amount,original_amount,corrected_fields FROM finva_email_candidates WHERE id=%s", (candidate_id,))
    assert (str(candidate["amount"]), str(candidate["original_amount"])) == ("10395.00", "20.00")
    assert candidate["corrected_fields"] == ["amount"]


def test_same_currency_needs_no_rate(pg):
    crc = _candidate(pg, A)
    _as(A, gmail_service.review_gmail_candidate, crc, "accept")
    usd = _candidate(pg, B, **BAC_USD)
    _as(B, gmail_service.review_gmail_candidate, usd, "accept")
    rows = _all(pg, "SELECT workspace_id::text AS ws,amount,original_amount,original_currency,exchange_rate FROM transactions ORDER BY id")
    assert [(r["ws"], str(r["amount"]), r["original_amount"], r["original_currency"], r["exchange_rate"]) for r in rows] == [
        (A["workspace"], "18500.00", None, None, None),
        (B["workspace"], "21.00", None, None, None),
    ]
    payloads = [r["payload"] for r in _all(pg, "SELECT payload FROM financial_input_events ORDER BY id")]
    assert [(p["amount"], p["currency"], "exchange_rate" in p) for p in payloads] == [(18500.0, "CRC", False), (21.0, "USD", False)]


def test_a_colon_movement_on_a_usd_account_uses_the_same_rate_definition(pg):
    candidate_id = _candidate(pg, B, amount=50500)
    with pytest.raises(HTTPException):
        _as(B, gmail_service.review_gmail_candidate, candidate_id, "accept")
    _as(B, gmail_service.review_gmail_candidate, candidate_id, "accept", _corrections(50500, rate=505))
    tx = _one(pg, "SELECT amount,original_amount,original_currency,exchange_rate FROM transactions")
    assert (str(tx["amount"]), str(tx["original_amount"]), tx["original_currency"], str(tx["exchange_rate"])) == \
        ("100.00", "50500.00", "CRC", "505.000000")


# --------------------------------------------------------------------------- canonical account

def test_the_base_currency_is_the_candidates_own_account_never_the_caller(pg):
    candidate_id = _candidate(pg, A, **BAC_USD)  # A is CRC-based, B is USD-based
    with pytest.raises(HTTPException) as error:
        _as(B, gmail_service.review_gmail_candidate, candidate_id, "accept", _corrections(21, rate=505))
    assert error.value.status_code == 404
    _nothing_written(pg, candidate_id)
    # A client cannot supply the base currency: the request model drops it.
    assert "base_currency" not in _corrections(21, rate=505, base_currency="USD")
    _as(A, gmail_service.review_gmail_candidate, candidate_id, "accept", _corrections(21, rate=505, base_currency="USD"))
    assert str(_one(pg, "SELECT amount FROM transactions")["amount"]) == "10605.00"


# --------------------------------------------------------------------------- concurrency

def test_two_concurrent_accepts_with_different_rates_save_one_transaction(pg):
    candidate_id = _candidate(pg, A, **BAC_USD)
    blocker = psycopg2.connect(database.DATABASE_URL)
    with blocker.cursor() as cur:  # hold the candidate row so both requests queue on the real lock
        cur.execute("SELECT id FROM finva_email_candidates WHERE id=%s FOR UPDATE", (candidate_id,))
    results, errors = {}, []
    start = threading.Barrier(3)

    def accept(rate):
        try:
            start.wait()
            results[rate] = _as(A, gmail_service.review_gmail_candidate, candidate_id, "accept", _corrections(21, rate=rate))
        except Exception as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=accept, args=(rate,)) for rate in (505, 510)]
    for thread in threads:
        thread.start()
    start.wait()
    # Both requests are now waiting on the row lock.
    for _ in range(100):
        waiting = _one(pg, "SELECT COUNT(*) AS n FROM pg_stat_activity WHERE wait_event_type='Lock' AND datname=current_database()")["n"]
        if waiting == 2:
            break
        threading.Event().wait(0.05)
    assert waiting == 2
    blocker.rollback()
    blocker.close()
    for thread in threads:
        thread.join(timeout=30)
    assert not errors
    (tx,) = _all(pg, "SELECT id,amount,exchange_rate FROM transactions")
    assert _one(pg, "SELECT COUNT(*) AS n FROM financial_input_events")["n"] == 1
    assert _one(pg, "SELECT COUNT(*) AS n FROM notification_jobs")["n"] == 1
    assert {result["transaction_id"] for result in results.values()} == {tx["id"]}
    assert {result["status"] for result in results.values()} == {"confirmed"}
    # The winner's rate, applied consistently: never a mix of both requests.
    assert (str(tx["exchange_rate"]), str(tx["amount"])) in {("505.000000", "10605.00"), ("510.000000", "10710.00")}
    candidate = _one(pg, "SELECT status,transaction_id FROM finva_email_candidates WHERE id=%s", (candidate_id,))
    assert (candidate["status"], candidate["transaction_id"]) == ("confirmed", tx["id"])
