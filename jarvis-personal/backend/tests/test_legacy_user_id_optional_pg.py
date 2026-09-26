"""Legacy identity retirement, phase E1, against a real PostgreSQL.

The migration makes the legacy user_id optional (no DEFAULT 1, no NOT NULL) and
gives the tables that only cascaded through user_id a workspace cascade. Runs on
the identity baseline, the ownership fixture and the ownership guard (#245), so
the guard's treatment of a NULL user_id is exercised for real. Synthetic data only.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

psycopg2 = pytest.importorskip("psycopg2")

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "database/baseline/v1_identity_ownership.sql"
FIXTURE = Path(__file__).resolve().parent / "fixtures/ownership_financial_tables.sql"
OWNERSHIP = ROOT / "database/migrations/20260925140000_financial_ownership_integrity.sql"
MIGRATION = ROOT / "database/migrations/20260926130000_legacy_user_id_optional.sql"
ROLLBACK = ROOT / "database/rollback/20260926130000_legacy_user_id_optional_rollback.sql"

WS = "00000000-0000-4000-8000-00000000000a"
OTHER_WS = "00000000-0000-4000-8000-00000000000b"
ACC = "00000000-0000-4000-8000-0000000000a1"
OTHER_ACC = "00000000-0000-4000-8000-0000000000b1"

# Tables that, in production, only reached account deletion through user_id.
LEGACY_CASCADE_ONLY = """
CREATE TABLE notification_jobs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1 REFERENCES allowed_users(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL,
    title TEXT NOT NULL);
CREATE TABLE audit_backup_synthetic (user_id BIGINT, workspace_id UUID NOT NULL);
-- A user_id that was optional before the migration: the rollback must leave it optional.
CREATE TABLE settings_synthetic (
    user_id BIGINT, workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE);
"""

# Financial tables that already cascade from workspaces in production (checked on a
# restored backup); the migration refuses to run (LI003) if one does not.
PRODUCTION_WORKSPACE_CASCADES = ("debt_payments", "debts", "exchange_rates", "expenses", "receivable_payments",
                                 "receivables", "transactions")


def _admin_uri(data_dir: Path) -> str:
    url = os.getenv("DINCR_TEST_POSTGRES_URL", "").strip()
    if url:
        return url
    try:
        import pgserver
    except ImportError:
        if os.getenv("DINCR_REQUIRE_PG_TESTS") == "1":
            pytest.fail("PostgreSQL tests are required but neither DINCR_TEST_POSTGRES_URL nor pgserver is available.")
        pytest.skip("No PostgreSQL available (set DINCR_TEST_POSTGRES_URL or install pgserver).")
    return pgserver.get_server(data_dir, cleanup_mode="delete").get_uri()


@pytest.fixture(scope="module")
def admin_uri(tmp_path_factory):
    return _admin_uri(tmp_path_factory.mktemp("pgserver"))


@pytest.fixture
def cur(admin_uri):
    from urllib.parse import urlsplit, urlunsplit

    name = f"legacy_{uuid.uuid4().hex[:12]}"
    admin = psycopg2.connect(admin_uri)
    admin.autocommit = True
    with admin.cursor() as c:
        for role in ("anon", "authenticated"):
            c.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,))
            if not c.fetchone():
                c.execute(f'CREATE ROLE "{role}" NOLOGIN')
        c.execute(f'CREATE DATABASE "{name}"')
    parts = urlsplit(admin_uri)
    conn = psycopg2.connect(urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment)),
                            application_name="Supavisor")
    conn.autocommit = True
    c = conn.cursor()
    c.execute(BASELINE.read_text(encoding="utf-8"))
    c.execute(FIXTURE.read_text(encoding="utf-8"))
    c.execute(LEGACY_CASCADE_ONLY)
    for table in PRODUCTION_WORKSPACE_CASCADES:  # present in production, absent from the shared fixture
        c.execute(f"ALTER TABLE {table} ADD FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE")
    c.execute(OWNERSHIP.read_text(encoding="utf-8"))
    for allowed, account, workspace in ((11, ACC, WS), (12, OTHER_ACC, OTHER_WS)):
        c.execute("INSERT INTO allowed_users(id,email,role,status) VALUES(%s,%s,'user','active')",
                  (allowed, f"{allowed}@example.test"))
        c.execute("INSERT INTO accounts(id,legacy_allowed_user_id,primary_email) VALUES(%s,%s,%s)",
                  (account, allowed, f"{allowed}@example.test"))
        c.execute("""INSERT INTO workspaces(id,workspace_key,owner_account_id,name,workspace_type)
                     VALUES(%s,%s,%s,'Personal','personal')""", (workspace, f"personal:{account}", account))
        c.execute("""INSERT INTO workspace_members(workspace_id,account_id,member_role,status)
                     VALUES(%s,%s,'owner','active')""", (workspace, account))
    try:
        yield c
    finally:
        conn.close()
        with admin.cursor() as a:
            a.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.close()


def _postflight() -> str:
    tail = MIGRATION.read_text(encoding="utf-8").split("-- Postflight (read-only)")[-1]
    return "\n".join(line[3:] for line in tail.splitlines()[1:] if line.startswith("-- "))


def _required(cur) -> set[str]:
    cur.execute("""SELECT table_name FROM information_schema.columns
                   WHERE table_schema='public' AND column_name='user_id' AND is_nullable='NO'""")
    return {row[0] for row in cur.fetchall()}


def _debt(cur, workspace, user_id=None):
    cur.execute("""INSERT INTO debts(user_id,name,debt_type,total_amount,remaining_amount,monthly_payment,workspace_id)
                   VALUES(%s,'Synthetic','other',1000,800,100,%s) RETURNING user_id""", (user_id, workspace))
    return cur.fetchone()[0]


def test_a_row_without_an_existing_workspace_aborts_and_changes_nothing(cur):
    cur.execute("ALTER TABLE notification_jobs DISABLE TRIGGER USER")
    cur.execute("INSERT INTO notification_jobs(user_id,workspace_id,title) VALUES(11,%s,'orphan')", (str(uuid.uuid4()),))
    cur.execute("ALTER TABLE notification_jobs ENABLE TRIGGER USER")
    before = _required(cur)
    with pytest.raises(psycopg2.Error) as refused:
        cur.execute(MIGRATION.read_text(encoding="utf-8"))
    assert refused.value.pgcode == "LI001"
    cur.execute("ROLLBACK")
    assert _required(cur) == before and "debts" in before
    cur.execute("SELECT count(*) FROM pg_constraint WHERE conname='notification_jobs_workspace_fk'")
    assert cur.fetchone() == (0,)
    cur.execute("SELECT count(*) FROM notification_jobs")
    assert cur.fetchone() == (1,)  # never deleted by the migration


def test_a_table_without_a_workspace_cascade_aborts_and_changes_nothing(cur):
    cur.execute("CREATE TABLE uncovered_synthetic (user_id BIGINT NOT NULL, workspace_id UUID NOT NULL)")
    before = _required(cur)
    with pytest.raises(psycopg2.Error) as refused:
        cur.execute(MIGRATION.read_text(encoding="utf-8"))
    assert refused.value.pgcode == "LI003" and "uncovered_synthetic" in str(refused.value)
    cur.execute("ROLLBACK")
    assert _required(cur) == before


def test_user_id_becomes_optional_and_the_guard_still_holds(cur):
    cur.execute(MIGRATION.read_text(encoding="utf-8"))
    cur.execute(MIGRATION.read_text(encoding="utf-8"))  # idempotent
    cur.execute(_postflight())
    assert cur.fetchall() == []
    assert _required(cur) == set()
    cur.execute("SELECT to_regclass('public.notification_jobs_workspace_id_idx') IS NOT NULL")
    assert cur.fetchone() == (True,)
    # An omitted user_id is no longer attributed to legacy id 1.
    assert _debt(cur, WS) is None
    # A wrong legacy id is still refused by the ownership guard.
    with pytest.raises(psycopg2.Error, match="ownership"):
        _debt(cur, WS, user_id=12)
    assert _debt(cur, WS, user_id=11) == 11


def test_a_row_without_user_id_is_deleted_with_its_workspace(cur):
    cur.execute(MIGRATION.read_text(encoding="utf-8"))
    cur.execute("INSERT INTO notification_jobs(workspace_id,title) VALUES(%s,'mine'),(%s,'theirs')", (WS, OTHER_WS))
    cur.execute("DELETE FROM workspaces WHERE id=%s", (WS,))
    cur.execute("SELECT title FROM notification_jobs")
    assert cur.fetchall() == [("theirs",)]


def test_the_rollback_restores_not_null_only_while_no_row_needs_a_decision(cur):
    cur.execute(MIGRATION.read_text(encoding="utf-8"))
    cur.execute(ROLLBACK.read_text(encoding="utf-8"))
    assert "debts" in _required(cur)
    assert not {"audit_backup_synthetic", "settings_synthetic"} & _required(cur)  # never NOT NULL before
    cur.execute("SELECT count(*) FROM pg_constraint WHERE conname='notification_jobs_workspace_fk'")
    assert cur.fetchone() == (0,)
    cur.execute("SELECT to_regclass('public.notification_jobs_workspace_id_idx')")
    assert cur.fetchone() == (None,)
    cur.execute("SELECT column_default FROM information_schema.columns WHERE table_name='debts' AND column_name='user_id'")
    assert cur.fetchone() == (None,)  # DEFAULT 1 is not restored

    cur.execute(MIGRATION.read_text(encoding="utf-8"))
    _debt(cur, WS)
    with pytest.raises(psycopg2.Error) as refused:
        cur.execute(ROLLBACK.read_text(encoding="utf-8"))
    assert refused.value.pgcode == "LI002"
    cur.execute("ROLLBACK")
    assert _required(cur) == set()
