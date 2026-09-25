"""One live connection per mailbox, enforced by PostgreSQL (the application check's backstop).

Skipped when the embedded server (pgserver) is not installed.
"""
from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg2 = pytest.importorskip("psycopg2")

MIGRATION = Path(__file__).resolve().parents[2] / "database" / "migrations" / "20260926110000_mailbox_single_owner.sql"
SCHEMA = """
CREATE TABLE finva_gmail_connections (
    id BIGSERIAL PRIMARY KEY, account_id UUID NOT NULL, workspace_id UUID NOT NULL,
    google_email TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'reauthorization_required', 'disabled')),
    UNIQUE (workspace_id, google_email));
CREATE UNIQUE INDEX finva_gmail_connections_account_email_key ON finva_gmail_connections(account_id, lower(google_email));
"""


@pytest.fixture
def db(tmp_path):
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
    yield {"cur": cur, "uri": uri}
    conn.close()
    with admin.cursor() as c:
        c.execute(f"DROP DATABASE {name} WITH (FORCE)")
    admin.close()


def _insert(cur, email, status="active"):
    cur.execute("INSERT INTO finva_gmail_connections(account_id, workspace_id, google_email, status) VALUES (%s, %s, %s, %s)",
                (str(uuid.uuid4()), str(uuid.uuid4()), email, status))


def test_the_migration_refuses_existing_duplicates_and_changes_nothing(db):
    cur = db["cur"]
    _insert(cur, "shared@example.com")
    _insert(cur, " Shared@Example.com")
    with pytest.raises(psycopg2.Error) as refused:
        cur.execute(MIGRATION.read_text(encoding="utf-8"))
    assert refused.value.pgcode == "MB001"
    cur.execute("ROLLBACK")
    cur.execute("SELECT to_regclass('public.uq_finva_mail_connections_live_mailbox')")
    assert cur.fetchone() == (None,)


def test_one_live_connection_per_mailbox_and_disconnected_ones_do_not_count(db):
    cur = db["cur"]
    _insert(cur, "old@example.com", status="disabled")
    _insert(cur, "old@example.com", status="disabled")
    cur.execute(MIGRATION.read_text(encoding="utf-8"))
    cur.execute(MIGRATION.read_text(encoding="utf-8"))  # idempotent
    _insert(cur, "old@example.com")  # a disconnected mailbox is free again
    for variant in ("old@example.com", "OLD@example.com", " old@example.com "):
        for status in ("active", "reauthorization_required"):
            with pytest.raises(psycopg2.errors.UniqueViolation):
                _insert(cur, variant, status)
    postflight = "\n".join(line[3:] for line in MIGRATION.read_text(encoding="utf-8").split("-- Postflight (read-only)")[-1].splitlines()[1:]
                           if line.startswith("-- "))
    cur.execute(postflight)
    assert cur.fetchall() == []


def test_a_mailbox_disconnected_in_one_workspace_can_be_connected_in_another_of_the_same_account(db):
    cur = db["cur"]
    cur.execute(MIGRATION.read_text(encoding="utf-8"))
    account = str(uuid.uuid4())
    cur.execute("INSERT INTO finva_gmail_connections(account_id, workspace_id, google_email, status) VALUES (%s, %s, 'x@example.com', 'disabled')",
                (account, str(uuid.uuid4())))
    cur.execute("INSERT INTO finva_gmail_connections(account_id, workspace_id, google_email, status) VALUES (%s, %s, 'x@example.com', 'active')",
                (account, str(uuid.uuid4())))
    cur.execute("SELECT to_regclass('public.finva_gmail_connections_account_email_key')")
    assert cur.fetchone() == (None,)


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
    db["cur"].execute("SELECT count(*) FROM finva_gmail_connections WHERE lower(btrim(google_email)) = 'race@example.com'")
    assert db["cur"].fetchone() == (1,)
