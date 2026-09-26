"""Migration 20260926125000 (the former Owner runtime DDL) on PostgreSQL.

Runs on the identity baseline plus the one earlier table it alters. Checks that it
is idempotent, that the advisor tables are locked down like every other table and
keep an optional legacy user_id (also where the superseded 20260908 migration ran),
and that advisor persistence works through the real connection wrapper, per workspace.
Synthetic data only.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg2 = pytest.importorskip("psycopg2")

from backend.advisor import core  # noqa: E402
from backend.core import database  # noqa: E402

ROOT = Path(__file__).resolve().parents[2] / "database"
BASELINE = ROOT / "baseline" / "v1_identity_ownership.sql"
MIGRATION = ROOT / "migrations" / "20260926125000_owner_legacy_schema.sql"
SUPERSEDED = ROOT / "migrations" / "20260908_advisor_core.sql"
WS_A, WS_B = str(uuid.uuid4()), str(uuid.uuid4())


@pytest.fixture
def db(tmp_path, monkeypatch):
    server = pgserver.get_server(str(os.environ.get("DINCR_PGSERVER_DIR") or tmp_path / "pg"), cleanup_mode="stop")
    admin = psycopg2.connect(server.get_uri())
    admin.autocommit = True
    name = f"ownerschema_{uuid.uuid4().hex[:12]}"
    with admin.cursor() as c:
        for role in ("anon", "authenticated"):
            c.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,))
            if not c.fetchone():
                c.execute(f'CREATE ROLE "{role}" NOLOGIN')
        c.execute(f"CREATE DATABASE {name}")
    uri = server.get_uri(name)
    conn = psycopg2.connect(uri)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(BASELINE.read_text(encoding="utf-8"))
    cur.execute("CREATE TABLE investment_portfolio_snapshots (id BIGSERIAL PRIMARY KEY, workspace_id UUID)")
    for n, workspace in enumerate((WS_A, WS_B), start=1):
        account = str(uuid.uuid4())
        cur.execute("INSERT INTO allowed_users(id,email,role,status) VALUES(%s,%s,'owner','active')", (n, f"{n}@example.test"))
        cur.execute("INSERT INTO accounts(id,legacy_allowed_user_id,primary_email) VALUES(%s,%s,%s)", (account, n, f"{n}@example.test"))
        cur.execute("""INSERT INTO workspaces(id,workspace_key,owner_account_id,name,workspace_type)
                       VALUES(%s,%s,%s,'Personal','personal')""", (workspace, f"personal:{account}", account))
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    try:
        yield cur
    finally:
        conn.close()
        with admin.cursor() as c:
            c.execute(f"DROP DATABASE {name} WITH (FORCE)")
        admin.close()


def _postflight() -> str:
    tail = MIGRATION.read_text(encoding="utf-8").split("-- Postflight (read-only)")[-1].split("-- Rollback")[0]
    return "\n".join(line[3:].lstrip() for line in tail.splitlines()[1:] if line.startswith("-- "))


def _schema(cur) -> list:
    cur.execute("""SELECT table_name, column_name, data_type, is_nullable FROM information_schema.columns
                   WHERE table_schema='public' ORDER BY 1, 2""")
    return cur.fetchall()


def test_the_migration_is_idempotent_and_locks_down_the_new_tables(db):
    db.execute(MIGRATION.read_text(encoding="utf-8"))
    first = _schema(db)
    db.execute(MIGRATION.read_text(encoding="utf-8"))
    assert _schema(db) == first
    db.execute(_postflight())
    assert db.fetchall() == []
    db.execute("""SELECT relname, relrowsecurity, has_table_privilege('anon', oid, 'SELECT')
                  FROM pg_class WHERE relname IN ('advisor_current_strategy', 'advisor_strategy_history') ORDER BY 1""")
    assert db.fetchall() == [("advisor_current_strategy", True, False), ("advisor_strategy_history", True, False)]


def test_a_required_user_id_from_the_superseded_migration_becomes_optional(db):
    db.execute(SUPERSEDED.read_text(encoding="utf-8"))
    db.execute(MIGRATION.read_text(encoding="utf-8"))
    db.execute(_postflight())
    assert db.fetchall() == []
    db.execute("SELECT to_regclass('public.idx_advisor_strategy_history_workspace_created') IS NOT NULL")
    assert db.fetchone() == (True,)


def test_advisor_persistence_is_per_workspace_through_the_real_wrapper(db, monkeypatch):
    db.execute(MIGRATION.read_text(encoding="utf-8"))
    monkeypatch.setattr(core, "get_current_user_id", lambda: 1)
    for workspace, strategy in ((WS_A, {"plan": "a"}), (WS_B, {"plan": "b"})):
        monkeypatch.setattr(core, "get_current_workspace_id", lambda workspace=workspace: workspace)
        first = core._persist_strategy(strategy)
        assert first["persisted"] is True and first["changed"] is True
        assert core._persist_strategy(strategy)["changed"] is False  # same strategy: no new history row
    monkeypatch.setattr(core, "get_current_workspace_id", lambda: WS_A)
    history = core.get_strategy_history()
    assert [row["strategy"] for row in history] == [{"plan": "a"}]
    db.execute("SELECT count(*) FROM advisor_current_strategy")
    assert db.fetchone() == (2,)
