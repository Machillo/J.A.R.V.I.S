"""One live connection per mailbox, enforced by PostgreSQL, and the stale takeover on real rows.

Skipped when the embedded server (pgserver) is not installed.
"""
from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException

pgserver = pytest.importorskip("pgserver")
psycopg2 = pytest.importorskip("psycopg2")

from backend.core import database  # noqa: E402
from backend.user_product import mail_oauth  # noqa: E402

ROOT = Path(__file__).resolve().parents[2] / "database"
MIGRATION = ROOT / "migrations" / "20260926110000_mailbox_single_owner.sql"
ROLLBACK = ROOT / "rollback" / "20260926110000_mailbox_single_owner_rollback.sql"
SCHEMA = """
DO $$ BEGIN CREATE ROLE anon NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE ROLE authenticated NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
CREATE SCHEMA vault;
CREATE TABLE vault.secrets (id UUID PRIMARY KEY);
CREATE TABLE accounts (id UUID PRIMARY KEY);
CREATE TABLE mail_oauth_flows (id UUID PRIMARY KEY, mailbox_address TEXT);
CREATE TABLE finva_gmail_connections (
    id BIGSERIAL PRIMARY KEY, account_id UUID NOT NULL, workspace_id UUID NOT NULL,
    google_email TEXT NOT NULL, refresh_token_secret_id UUID,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'reauthorization_required', 'disabled')),
    history_id TEXT, watch_expiration TIMESTAMPTZ, initial_scan_page_token TEXT, last_error TEXT,
    updated_at TIMESTAMPTZ,
    UNIQUE (workspace_id, google_email));
CREATE UNIQUE INDEX finva_gmail_connections_account_email_key ON finva_gmail_connections(account_id, lower(google_email));
"""
SAMPLES = ["A.B+x@GMAIL.com", " ab.c@googlemail.com ", "First.Last@Outlook.com", "x+y@example.com", "plain"]


@pytest.fixture
def db(tmp_path, monkeypatch):
    server = pgserver.get_server(str(os.environ.get("DINCR_PGSERVER_DIR") or tmp_path / "pg"), cleanup_mode="stop")
    admin = psycopg2.connect(server.get_uri())
    admin.autocommit = True
    name = f"mailbox_{os.getpid()}_{abs(hash(str(tmp_path))) % 10**8}"
    with admin.cursor() as c:
        c.execute(f"CREATE DATABASE {name}")
    uri = server.get_uri(name)
    conn = psycopg2.connect(uri)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(SCHEMA)
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    yield {"cur": cur, "uri": uri}
    conn.close()
    with admin.cursor() as c:
        c.execute(f"DROP DATABASE {name} WITH (FORCE)")
    admin.close()


def _legacy_insert(cur, email, status="active"):
    """A row as written by the code before this migration (no identity columns)."""
    cur.execute("INSERT INTO finva_gmail_connections(account_id, workspace_id, google_email, status) VALUES (%s, %s, %s, %s)",
                (str(uuid.uuid4()), str(uuid.uuid4()), email, status))


def _insert(cur, email, status="active", key=None, secret=None):
    """A row as written by the new code."""
    account = str(uuid.uuid4())
    cur.execute("INSERT INTO accounts VALUES (%s)", (account,))
    cur.execute("""INSERT INTO finva_gmail_connections(account_id, workspace_id, google_email, mailbox_email, mailbox_key,
                   refresh_token_secret_id, status) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (account, str(uuid.uuid4()), email, mail_oauth.canonical_mailbox(email),
                 key or mail_oauth.mailbox_key("gmail", email), secret, status))
    return account, cur.fetchone()[0]


def _postflight():
    return "\n".join(line[3:] for line in MIGRATION.read_text(encoding="utf-8").split("-- Postflight (read-only)")[-1].splitlines()[1:]
                     if line.startswith("-- "))


def test_the_backfill_matches_the_application_rule(db):
    cur = db["cur"]
    for sample in SAMPLES:
        _legacy_insert(cur, sample, status="disabled")
    cur.execute(MIGRATION.read_text(encoding="utf-8"))
    cur.execute("SELECT google_email, mailbox_email, mailbox_key FROM finva_gmail_connections ORDER BY id")
    for google_email, mailbox_email, key in cur.fetchall():
        assert mailbox_email == mail_oauth.canonical_mailbox(google_email)
        assert key == mail_oauth.mailbox_key("gmail", google_email) == f"email:{mailbox_email}"
    cur.execute(_postflight())
    assert cur.fetchall() == []


@pytest.mark.parametrize(("first", "second"), [("shared@example.com", " Shared@Example.com"),
                                               ("first.last@gmail.com", "FirstLast+bank@googlemail.com")])
def test_the_migration_refuses_existing_duplicates_and_changes_nothing(db, first, second):
    cur = db["cur"]
    _legacy_insert(cur, first)
    _legacy_insert(cur, second)
    with pytest.raises(psycopg2.Error) as refused:
        cur.execute(MIGRATION.read_text(encoding="utf-8"))
    assert refused.value.pgcode == "MB001"
    cur.execute("ROLLBACK")
    cur.execute("SELECT to_regclass('public.uq_finva_mail_connections_live_mailbox'), "
                "count(*) FILTER (WHERE attname = 'mailbox_email') FROM pg_attribute "
                "WHERE attrelid = 'public.finva_gmail_connections'::regclass AND NOT attisdropped")
    assert cur.fetchone() == (None, 0)


def test_one_live_connection_per_mailbox_and_identity(db):
    cur = db["cur"]
    _legacy_insert(cur, "old@example.com", status="disabled")
    _legacy_insert(cur, "old@example.com", status="disabled")  # disconnected duplicates are allowed
    cur.execute(MIGRATION.read_text(encoding="utf-8"))
    cur.execute(MIGRATION.read_text(encoding="utf-8"))  # idempotent
    _insert(cur, "old@example.com", key="google:1")  # a disconnected mailbox is free again
    for status in ("active", "reauthorization_required"):
        with pytest.raises(psycopg2.errors.UniqueViolation):
            _insert(cur, "OLD@example.com", status, key="google:2")  # same address
        with pytest.raises(psycopg2.errors.UniqueViolation):
            _insert(cur, "renamed@example.com", status, key="google:1")  # same provider account
    _insert(cur, "old@example.com", "disabled", key="google:1")


def test_concurrent_completions_for_one_mailbox_leave_exactly_one(db):
    db["cur"].execute(MIGRATION.read_text(encoding="utf-8"))
    barrier, outcomes = threading.Barrier(8), []

    def attach():
        conn = psycopg2.connect(db["uri"])
        try:
            barrier.wait()
            with conn.cursor() as cur:
                _insert(cur, "race@example.com")
            conn.commit()
            outcomes.append("attached")
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            outcomes.append("refused")
        finally:
            conn.close()

    threads = [threading.Thread(target=attach) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["attached"] + ["refused"] * 7


def test_a_stale_mailbox_is_taken_over_once_even_by_concurrent_claims(db):
    """Two accounts complete a real consent for a stale mailbox at once: exactly one takes it over."""
    cur = db["cur"]
    cur.execute(MIGRATION.read_text(encoding="utf-8"))
    secret = str(uuid.uuid4())
    cur.execute("INSERT INTO vault.secrets VALUES (%s)", (secret,))
    stale_account, stale_id = _insert(cur, "shared@example.com", "reauthorization_required", secret=secret)
    claimants = [(str(uuid.uuid4()), str(uuid.uuid4())) for _ in range(2)]
    for claimant, _workspace in claimants:
        cur.execute("INSERT INTO accounts VALUES (%s)", (claimant,))
    barrier, outcomes = threading.Barrier(2), []

    def claim(claimant, workspace):
        barrier.wait()
        try:
            with database.get_connection() as conn:
                mail_oauth.claim_mailbox(conn, provider="gmail", account_id=claimant, workspace_id=workspace,
                                         key="email:shared@example.com", email="shared@example.com",
                                         is_entitled=lambda _conn, _account: True)
                conn.execute("""INSERT INTO finva_gmail_connections(account_id, workspace_id, google_email, mailbox_email,
                                mailbox_key, status) VALUES (%s, %s, 'shared@example.com', 'shared@example.com',
                                'email:shared@example.com', 'active') RETURNING id""", (claimant, workspace))
                conn.commit()
            outcomes.append("connected")
        except (HTTPException, psycopg2.errors.UniqueViolation):
            outcomes.append("refused")

    threads = [threading.Thread(target=claim, args=pair) for pair in claimants]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["connected", "refused"]
    cur.execute("SELECT status, last_error, account_id::text FROM finva_gmail_connections WHERE id = %s", (stale_id,))
    assert cur.fetchone() == ("disabled", mail_oauth.MAILBOX_TAKEN_OVER, stale_account)
    cur.execute("SELECT count(*) FROM vault.secrets")
    assert cur.fetchone() == (0,)  # the stale token is deleted, never handed over
    cur.execute("SELECT previous_connection_id, previous_account_id::text, reason FROM mail_connection_takeovers")
    assert cur.fetchall() == [(stale_id, stale_account, "access_lost")]


def test_the_rollback_restores_the_previous_schema(db):
    cur = db["cur"]
    cur.execute(MIGRATION.read_text(encoding="utf-8"))
    cur.execute(ROLLBACK.read_text(encoding="utf-8"))
    cur.execute("""SELECT to_regclass('public.mail_connection_takeovers'), to_regclass('public.uq_finva_mail_connections_live_mailbox'),
                          to_regclass('public.finva_gmail_connections_account_email_key') IS NOT NULL""")
    assert cur.fetchone() == (None, None, True)
