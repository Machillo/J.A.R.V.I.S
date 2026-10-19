"""Owner-only automatic save of mail movements, against a real PostgreSQL.

Before 2026-09-24 the Owner's learned rules saved a movement on their own (a ``classify`` rule
with ``allow_auto_commit``, confidence >= AUTO_COMMIT_CONFIDENCE, colones). The standard mailbox
pipeline lost that; ``owner_mail_automation.auto_save`` restores it through the same
transaction and event writers as a manual confirmation, and leaves the candidate pending for
review whenever anything is uncertain. Tables keep the real names, columns and constraints of
database/migrations that this flow touches. All data is synthetic.
"""
from __future__ import annotations

import os
import uuid
from datetime import date
from urllib.parse import urlsplit, urlunsplit

import pytest

from backend.user_product import owner_mail_automation

psycopg2 = pytest.importorskip("psycopg2")
from psycopg2.extras import RealDictCursor  # noqa: E402

ACC, WS = "00000000-0000-4000-8000-0000000000f1", "00000000-0000-4000-8000-00000000000f"
ALLOWED, LEGACY = 21, 91
DAY = date(2026, 10, 14)

SCHEMA = """
CREATE TABLE accounts (id UUID PRIMARY KEY, base_currency TEXT NOT NULL DEFAULT 'CRC', legacy_allowed_user_id BIGINT);
CREATE TABLE workspaces (id UUID PRIMARY KEY);
CREATE TABLE allowed_users (id BIGINT PRIMARY KEY);
CREATE TABLE users (id BIGINT PRIMARY KEY);
CREATE TABLE transactions (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(id), transaction_date DATE NOT NULL,
    description TEXT NOT NULL, amount NUMERIC(14,2) NOT NULL, transaction_type TEXT NOT NULL, category TEXT,
    account TEXT, source TEXT, notes TEXT, workspace_id UUID REFERENCES workspaces(id), financial_account_id BIGINT,
    original_amount NUMERIC(14,2), original_currency TEXT, exchange_rate NUMERIC(14,6),
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
    id BIGSERIAL PRIMARY KEY, email_message_id BIGINT NOT NULL REFERENCES finva_email_messages(id),
    account_id UUID NOT NULL REFERENCES accounts(id), workspace_id UUID NOT NULL REFERENCES workspaces(id),
    transaction_id BIGINT REFERENCES transactions(id), transaction_date DATE NOT NULL, description TEXT NOT NULL,
    amount NUMERIC(18,2) NOT NULL, currency TEXT NOT NULL DEFAULT 'CRC',
    original_amount NUMERIC(18,2), original_currency TEXT, transaction_type TEXT NOT NULL,
    movement_direction TEXT, source_account_reference TEXT, destination_account_reference TEXT,
    confidence NUMERIC(5,4), category TEXT NOT NULL, bank TEXT NOT NULL, financial_account_id BIGINT,
    source_type TEXT NOT NULL DEFAULT 'gmail', source_provider TEXT NOT NULL DEFAULT 'gmail',
    is_internal_transfer BOOLEAN NOT NULL DEFAULT FALSE, related_candidate_id BIGINT, resolution_reason TEXT,
    corrected_fields TEXT[], reviewed_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','auto_saved','confirmed','rejected','duplicate')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE email_financial_accounts (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL, workspace_id UUID NOT NULL, account_key TEXT NOT NULL,
    institution TEXT NOT NULL, account_last4 TEXT NOT NULL CHECK (account_last4 ~ '^\\d{4}$'),
    ownership TEXT NOT NULL CHECK (ownership IN ('own', 'counterparty')), display_name TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE, UNIQUE (workspace_id, account_key));
CREATE TABLE email_classification_rules (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL, workspace_id UUID NOT NULL, name TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 100, concept_pattern TEXT NOT NULL DEFAULT '',
    match_mode TEXT NOT NULL DEFAULT 'contains' CHECK (match_mode IN ('exact', 'contains', 'regex')),
    direction TEXT CHECK (direction IN ('in', 'out', 'payment', 'unknown')), origin_account_key TEXT,
    destination_account_key TEXT, action TEXT NOT NULL CHECK (action IN ('classify', 'ignore', 'review')),
    output_description TEXT, transaction_type TEXT, category TEXT, allow_auto_commit BOOLEAN NOT NULL DEFAULT FALSE,
    review_reason TEXT, metadata JSONB NOT NULL DEFAULT '{}'::JSONB, active BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (workspace_id, name));
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


@pytest.fixture(autouse=True)
def verified_owner(monkeypatch):
    """The stored Owner identity (roles, allowlist, single Owner, own workspace) is proven on a real
    PostgreSQL in tests/test_owner_category_context_pg.py; here it answers for ACC/WS only."""
    from backend.auth import owner_role

    monkeypatch.setattr(owner_role, "is_verified_owner_account",
                        lambda conn, account_id, workspace_id: (str(account_id), str(workspace_id)) == (ACC, WS))


@pytest.fixture
def db(admin_uri):
    name = f"owner_auto_{uuid.uuid4().hex[:12]}"
    admin = psycopg2.connect(admin_uri)
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{name}"')
    parts = urlsplit(admin_uri)
    uri = urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment))
    conn = psycopg2.connect(uri, cursor_factory=RealDictCursor)
    with conn.cursor() as cur:
        cur.execute(SCHEMA)
        cur.execute("INSERT INTO accounts(id,legacy_allowed_user_id) VALUES(%s,%s)", (ACC, ALLOWED))
        cur.execute("INSERT INTO workspaces VALUES(%s)", (WS,))
        cur.execute("INSERT INTO allowed_users VALUES(%s)", (ALLOWED,))
        cur.execute("INSERT INTO users VALUES(%s)", (LEGACY,))
        cur.execute("INSERT INTO finva_gmail_connections(account_id,workspace_id,legacy_user_id,granted_scopes) VALUES(%s,%s,%s,%s)",
                    (ACC, WS, LEGACY, ["gmail.readonly"]))
    conn.commit()
    try:
        wrapped = _Conn(conn)
        wrapped.uri = uri
        yield wrapped
    finally:
        conn.close()
        with admin.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


class _Conn:
    """The application's connection interface (execute returns a cursor) over psycopg2."""

    def __init__(self, conn):
        self.raw = conn

    def execute(self, query, params=()):
        cur = self.raw.cursor()
        cur.execute(query, params)
        return cur

    def commit(self):
        self.raw.commit()

    def one(self, query, params=()):
        return self.execute(query, params).fetchone()


def _rule(db, *, pattern="supermercado sintetico", action="classify", allow=True, description="Supermercado",
          category="Comida", transaction_type="expense"):
    db.execute(
        """INSERT INTO email_classification_rules(user_id,workspace_id,name,concept_pattern,action,allow_auto_commit,
               output_description,category,transaction_type)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (LEGACY, WS, f"rule-{uuid.uuid4().hex[:6]}", pattern, action, allow, description, category, transaction_type),
    )
    db.commit()


def _candidate(db, *, description="COMPRA SUPERMERCADO SINTETICO", amount=12500, currency="CRC",
               original_currency=None, internal=False, source_type="gmail", status="pending", day=DAY,
               transaction_type="expense", resolution_reason=None):
    message = db.one("INSERT INTO finva_email_messages(connection_id,account_id,workspace_id) VALUES(1,%s,%s) RETURNING id", (ACC, WS))
    row = db.one(
        """INSERT INTO finva_email_candidates(email_message_id,account_id,workspace_id,transaction_date,description,amount,
               currency,original_amount,original_currency,transaction_type,movement_direction,confidence,category,bank,
               is_internal_transfer,source_type,status,resolution_reason)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'out',0.9,'Otros','BAC',%s,%s,%s,%s) RETURNING id""",
        (message["id"], ACC, WS, day, description, amount, currency,
         amount if original_currency else None, original_currency, transaction_type, internal, source_type, status,
         resolution_reason),
    )
    db.commit()
    return int(row["id"])


def _count(db, table):
    return int(db.one(f"SELECT count(*) AS n FROM {table}")["n"])


def test_a_learned_auto_commit_rule_saves_the_movement_like_a_confirmation(db):
    _rule(db)
    candidate_id = _candidate(db)
    assert owner_mail_automation.auto_save(db, candidate_id) == "auto_saved"
    db.commit()
    saved = db.one("SELECT * FROM finva_email_candidates WHERE id=%s", (candidate_id,))
    assert saved["status"] == "auto_saved" and saved["resolution_reason"] == "owner_learned_rule"
    tx = db.one("SELECT * FROM transactions WHERE id=%s", (saved["transaction_id"],))
    assert (tx["description"], tx["category"], tx["transaction_type"]) == ("Supermercado", "Comida", "expense")
    assert float(tx["amount"]) == 12500 and tx["transaction_date"] == DAY and tx["workspace_id"] is not None
    assert tx["notes"] == owner_mail_automation.AUTO_SAVED_NOTE and tx["user_id"] == LEGACY
    event = db.one("SELECT * FROM financial_input_events WHERE transaction_id=%s", (tx["id"],))
    assert event["user_id"] == ALLOWED and event["event_name"] == "transaction_confirmed"


@pytest.mark.parametrize("rule", [
    None,                                            # no learned rule matches
    {"allow": False},                                # the rule classifies but does not allow saving
    {"action": "review"},                            # the rule asks for review
    {"pattern": "otro comercio"},                    # a rule for another merchant
])
def test_without_an_auto_commit_rule_the_movement_waits_for_review(db, rule):
    if rule is not None:
        _rule(db, **rule)
    candidate_id = _candidate(db)
    assert owner_mail_automation.auto_save(db, candidate_id) is None
    db.commit()
    assert db.one("SELECT status FROM finva_email_candidates WHERE id=%s", (candidate_id,))["status"] == "pending"
    assert _count(db, "transactions") == 0


@pytest.mark.parametrize("days_apart", [0, 1, -1])
def test_a_recorded_transaction_of_the_same_amount_within_a_day_is_never_saved_twice(db, days_apart):
    """The reconstructed ledger (any description, any source) wins: the candidate waits for review."""
    _rule(db)
    db.execute(
        """INSERT INTO transactions(user_id,transaction_date,description,amount,transaction_type,workspace_id,source)
           VALUES(%s,%s::date + %s,'Compra reconstruida',12500,'expense',%s,'reconstruction')""",
        (LEGACY, DAY, days_apart, WS),
    )
    db.commit()
    candidate_id = _candidate(db)
    assert owner_mail_automation.auto_save(db, candidate_id) is None
    assert _count(db, "transactions") == 1


def test_a_transaction_two_days_away_or_of_another_amount_does_not_block_the_save(db):
    _rule(db)
    for offset, amount in ((2, 12500), (0, 9999)):
        db.execute(
            """INSERT INTO transactions(user_id,transaction_date,description,amount,transaction_type,workspace_id)
               VALUES(%s,%s::date + %s,'Otra compra',%s,'expense',%s)""",
            (LEGACY, DAY, offset, amount, WS),
        )
    db.commit()
    assert owner_mail_automation.auto_save(db, _candidate(db)) == "auto_saved"


@pytest.mark.parametrize("candidate", [
    {"currency": "USD", "original_currency": "USD"},  # a converted amount is never saved unreviewed
    {"internal": True},                               # own-account transfers follow their own review
    {"source_type": "statement"},                     # statement rows are reconciled, not auto-saved
    {"status": "confirmed"},                          # already reviewed
])
def test_uncertain_or_reviewed_candidates_are_left_as_they_are(db, candidate):
    _rule(db)
    candidate_id = _candidate(db, **candidate)
    before = db.one("SELECT status FROM finva_email_candidates WHERE id=%s", (candidate_id,))["status"]
    assert owner_mail_automation.auto_save(db, candidate_id) is None
    assert db.one("SELECT status FROM finva_email_candidates WHERE id=%s", (candidate_id,))["status"] == before
    assert _count(db, "transactions") == 0


def test_without_an_owner_identity_for_the_event_nothing_is_saved(db):
    _rule(db)
    db.execute("UPDATE accounts SET legacy_allowed_user_id=NULL")
    db.commit()
    assert owner_mail_automation.auto_save(db, _candidate(db)) is None
    assert _count(db, "transactions") == 0


def test_a_second_pass_never_saves_the_same_candidate_again(db):
    _rule(db)
    candidate_id = _candidate(db)
    assert owner_mail_automation.auto_save(db, candidate_id) == "auto_saved"
    db.commit()
    assert owner_mail_automation.auto_save(db, candidate_id) is None
    assert _count(db, "transactions") == 1 and _count(db, "financial_input_events") == 1


def test_the_owners_confidence_threshold_is_honoured(db, monkeypatch):
    """EMAIL_AUTO_COMMIT_CONFIDENCE (as the retired reader): above what the rule grants, nothing is saved."""
    from backend.email_monitor import service as email_monitor_service

    _rule(db)
    monkeypatch.setattr(email_monitor_service, "AUTO_COMMIT_CONFIDENCE", 1.01)
    assert owner_mail_automation.auto_save(db, _candidate(db)) is None
    assert _count(db, "transactions") == 0


def test_a_users_candidate_is_never_saved_even_with_a_matching_rule(db, monkeypatch):
    """The second barrier: auto_save itself refuses any account that is not the verified Owner."""
    from backend.auth import owner_role

    _rule(db)
    monkeypatch.setattr(owner_role, "is_verified_owner_account", lambda *_a: False)
    candidate_id = _candidate(db)
    assert owner_mail_automation.auto_save(db, candidate_id) is None
    assert db.one("SELECT status FROM finva_email_candidates WHERE id=%s", (candidate_id,))["status"] == "pending"
    assert _count(db, "transactions") == 0


@pytest.mark.parametrize("candidate", [
    {"resolution_reason": "possible_cross_source_match"},  # its statement copy or the other mailbox may hold it
    {"transaction_type": "transfer"},                      # one side of a transfer whose pair may still arrive
])
def test_a_movement_the_resolver_is_unsure_about_waits_for_review(db, candidate):
    _rule(db)
    candidate_id = _candidate(db, **candidate)
    assert owner_mail_automation.auto_save(db, candidate_id) is None
    assert _count(db, "transactions") == 0


def test_an_error_while_saving_leaves_the_candidate_pending_and_the_transaction_usable(db, monkeypatch):
    from backend.user_product import candidate_currency

    _rule(db)
    candidate_id = _candidate(db)
    monkeypatch.setattr(candidate_currency, "transaction_amounts", lambda *_a: (_ for _ in ()).throw(ValueError("refused")))
    assert owner_mail_automation.auto_save(db, candidate_id) is None
    db.commit()  # the caller's transaction (the message itself) still commits
    assert db.one("SELECT status FROM finva_email_candidates WHERE id=%s", (candidate_id,))["status"] == "pending"
    assert _count(db, "transactions") == 0 and _count(db, "financial_input_events") == 0


def test_two_mailboxes_saving_the_same_notice_at_once_save_it_once(db):
    """The same bank notice in two Owner mailboxes, synced in parallel: the second waits and sees the first."""
    import threading

    _rule(db)
    first, second = _candidate(db), _candidate(db)
    other = _Conn(psycopg2.connect(db.uri, cursor_factory=RealDictCursor))
    try:
        assert owner_mail_automation.auto_save(db, first) == "auto_saved"   # not committed yet: holds the lock
        result = {}
        worker = threading.Thread(target=lambda: result.update(status=owner_mail_automation.auto_save(other, second)))
        worker.start()
        worker.join(timeout=1.0)
        assert worker.is_alive(), "the second save waits for the first transaction"
        db.commit()
        worker.join(timeout=10)
        other.commit()
        assert result["status"] is None, "it found the first save's transaction"
        assert _count(db, "transactions") == 1
        assert db.one("SELECT status FROM finva_email_candidates WHERE id=%s", (second,))["status"] == "pending"
    finally:
        other.raw.close()
