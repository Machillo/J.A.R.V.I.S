"""Rehearse 20260925130000_request_path_schema.sql on a real PostgreSQL.

Skipped when the embedded server (pgserver) is not installed.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg2 = pytest.importorskip("psycopg2")

MIGRATION = Path(__file__).resolve().parents[2] / "database" / "migrations" / "20260925130000_request_path_schema.sql"
PREREQUISITES = """
GRANT ALL ON SCHEMA public TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO anon, authenticated;
CREATE TABLE accounts (id UUID PRIMARY KEY);
CREATE TABLE workspaces (id UUID PRIMARY KEY);
CREATE TABLE financial_goals (id BIGSERIAL PRIMARY KEY);
CREATE TABLE allowed_users (id BIGSERIAL PRIMARY KEY);
CREATE TABLE notification_jobs (id BIGSERIAL PRIMARY KEY, user_id BIGINT, scheduled_at TIMESTAMPTZ);
CREATE TABLE plans (id SERIAL PRIMARY KEY, code TEXT UNIQUE);
CREATE TABLE features (id SERIAL PRIMARY KEY, code TEXT UNIQUE, description TEXT);
CREATE TABLE plan_features (plan_id INT, feature_id INT, enabled BOOLEAN, PRIMARY KEY (plan_id, feature_id));
INSERT INTO plans(code) VALUES ('free'), ('basic'), ('vip');
-- An existing, deliberately disabled grant must survive the migration.
INSERT INTO features(code, description) VALUES ('guided_budget', 'kept description');
INSERT INTO plan_features SELECT p.id, f.id, FALSE FROM plans p, features f WHERE p.code = 'vip';
"""
NEW_TABLES = ("store_subscriptions", "store_subscription_events", "finva_budget_items", "finva_recurring_items", "finva_goal_contributions")


@pytest.fixture
def cur(tmp_path):
    server = pgserver.get_server(str(os.environ.get("DINCR_PGSERVER_DIR") or tmp_path / "pg"), cleanup_mode="stop")
    admin = psycopg2.connect(server.get_uri())
    admin.autocommit = True
    name = f"rps_{os.getpid()}_{abs(hash(str(tmp_path))) % 10**8}"
    with admin.cursor() as c:
        c.execute(f"CREATE DATABASE {name}")
    conn = psycopg2.connect(server.get_uri(name))
    conn.autocommit = True
    cursor = conn.cursor()
    # Roles are cluster-wide: create them once, tolerate other test databases.
    cursor.execute("DO $$ BEGIN CREATE ROLE anon NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
                   "DO $$ BEGIN CREATE ROLE authenticated NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;")
    cursor.execute(PREREQUISITES)
    yield cursor
    conn.close()
    with admin.cursor() as c:
        c.execute(f"DROP DATABASE {name} WITH (FORCE)")
    admin.close()


def _apply(cur):
    cur.execute(MIGRATION.read_text(encoding="utf-8"))


def test_migration_creates_closed_tables_and_is_idempotent(cur):
    _apply(cur)
    _apply(cur)

    for table in NEW_TABLES:
        cur.execute("SELECT relrowsecurity FROM pg_class WHERE oid = to_regclass(%s)", (f"public.{table}",))
        assert cur.fetchone() == (True,), table
        for role in ("anon", "authenticated"):
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                cur.execute("SELECT has_table_privilege(%s, %s, %s)", (role, f"public.{table}", privilege))
                assert cur.fetchone() == (False,), (role, table, privilege)
    for sequence in ("store_subscription_events_id_seq", "finva_budget_items_id_seq",
                     "finva_recurring_items_id_seq", "finva_goal_contributions_id_seq"):
        for role in ("anon", "authenticated"):
            cur.execute("SELECT has_sequence_privilege(%s, %s, 'USAGE')", (role, f"public.{sequence}"))
            assert cur.fetchone() == (False,), (role, sequence)
    cur.execute("SELECT count(*) FROM pg_indexes WHERE indexname IN "
                "('idx_notification_jobs_user','idx_finva_recurring_workspace','idx_finva_goal_contributions_workspace',"
                "'uq_store_event_provider_id','idx_store_subscription_status')")
    assert cur.fetchone() == (5,)


def test_migration_never_changes_existing_feature_configuration(cur):
    _apply(cur)

    cur.execute("SELECT description FROM features WHERE code = 'guided_budget'")
    assert cur.fetchone() == ("kept description",)
    cur.execute("""SELECT pf.enabled FROM plan_features pf JOIN plans p ON p.id = pf.plan_id
                   JOIN features f ON f.id = pf.feature_id WHERE p.code = 'vip' AND f.code = 'guided_budget'""")
    assert cur.fetchone() == (False,)
    cur.execute("""SELECT count(*) FROM plan_features pf JOIN plans p ON p.id = pf.plan_id
                   WHERE p.code = 'basic' AND pf.enabled""")
    assert cur.fetchone() == (5,)


def test_migration_keeps_existing_store_rows(cur):
    cur.execute("INSERT INTO accounts VALUES ('00000000-0000-0000-0000-00000000000a')")
    cur.execute("""CREATE TABLE store_subscriptions (account_id UUID PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
                   provider TEXT NOT NULL, plan_code TEXT NOT NULL, billing_period TEXT NOT NULL, product_id TEXT NOT NULL,
                   status TEXT NOT NULL, current_period_end TIMESTAMPTZ)""")
    cur.execute("INSERT INTO store_subscriptions VALUES ('00000000-0000-0000-0000-00000000000a','sandbox','basic','monthly','p','active',NULL)")
    _apply(cur)

    cur.execute("SELECT plan_code, pending_plan_code FROM store_subscriptions")
    assert cur.fetchall() == [("basic", None)]


def _postflight_sql() -> str:
    text = MIGRATION.read_text(encoding="utf-8")
    block = text[text.index("-- Postflight (read-only)"):].splitlines()[1:]
    return "\n".join(line[3:] for line in block if line.startswith("-- "))


def test_the_postflight_passes_after_the_migration_and_fails_before(cur):
    cur.execute(_postflight_sql())
    assert cur.fetchall(), "before the migration the postflight must report the missing tables"
    _apply(cur)
    cur.execute(_postflight_sql())
    assert cur.fetchall() == []


def test_free_never_gains_a_basic_feature(cur):
    _apply(cur)
    cur.execute("""SELECT count(*) FROM plan_features pf JOIN plans p ON p.id = pf.plan_id
                   JOIN features f ON f.id = pf.feature_id
                   WHERE p.code = 'free' AND f.code IN ('basic_dashboard','guided_budget','financial_calendar','recurring_items','basic_reports')""")
    assert cur.fetchone() == (0,)
