"""Uniqueness rules scoped by the legacy user_id get a workspace-scoped twin.

Runs migration 20260926131000 on PostgreSQL (embedded pgserver) against the
production shape of the four tables whose unique indexes include user_id. Once a
writer leaves user_id NULL, only the workspace twin still deduplicates. Synthetic data.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg2 = pytest.importorskip("psycopg2")

ROOT = Path(__file__).resolve().parents[2] / "database"
MIGRATION = ROOT / "migrations" / "20260926131000_workspace_unique_keys.sql"
ROLLBACK = ROOT / "rollback" / "20260926131000_workspace_unique_keys_rollback.sql"
WS = str(uuid.uuid4())
SCHEMA = """
CREATE TABLE credit_card_settings (id BIGSERIAL PRIMARY KEY, user_id BIGINT, workspace_id UUID NOT NULL,
    bank TEXT NOT NULL, card_last4 TEXT);
CREATE UNIQUE INDEX idx_credit_card_settings_user_bank_card ON credit_card_settings (user_id, bank, card_last4);
CREATE TABLE debt_payments (id BIGSERIAL PRIMARY KEY, user_id BIGINT, workspace_id UUID NOT NULL,
    debt_id BIGINT NOT NULL, payment_type TEXT NOT NULL, payment_date DATE);
CREATE UNIQUE INDEX idx_debt_payments_unique_monthly_due ON debt_payments (user_id, debt_id, payment_date)
    WHERE payment_type = 'monthly_payment' AND payment_date IS NOT NULL;
CREATE TABLE fixed_expense_matches (id BIGSERIAL PRIMARY KEY, user_id BIGINT, workspace_id UUID NOT NULL,
    fixed_expense_id BIGINT NOT NULL, period_month TEXT NOT NULL, UNIQUE (user_id, fixed_expense_id, period_month));
CREATE TABLE fixed_expenses (id BIGSERIAL PRIMARY KEY, user_id BIGINT, workspace_id UUID NOT NULL,
    name TEXT NOT NULL, UNIQUE (user_id, name));
CREATE TABLE ai_usage_daily (id BIGSERIAL PRIMARY KEY, user_id BIGINT, workspace_id UUID NOT NULL,
    usage_date DATE NOT NULL, UNIQUE (user_id, usage_date));
CREATE UNIQUE INDEX uq_ai_usage_daily_workspace_date ON ai_usage_daily (workspace_id, usage_date);
CREATE TABLE audit_backup_synthetic (user_id BIGINT, workspace_id UUID, UNIQUE (user_id));
"""


@pytest.fixture
def cur(tmp_path):
    server = pgserver.get_server(str(os.environ.get("DINCR_PGSERVER_DIR") or tmp_path / "pg"), cleanup_mode="stop")
    admin = psycopg2.connect(server.get_uri())
    admin.autocommit = True
    name = f"uniquekeys_{uuid.uuid4().hex[:12]}"
    with admin.cursor() as c:
        c.execute(f"CREATE DATABASE {name}")
    conn = psycopg2.connect(server.get_uri(name))
    conn.autocommit = True
    c = conn.cursor()
    c.execute(SCHEMA)
    try:
        yield c
    finally:
        conn.close()
        with admin.cursor() as a:
            a.execute(f"DROP DATABASE {name} WITH (FORCE)")
        admin.close()


def _postflight() -> str:
    tail = MIGRATION.read_text(encoding="utf-8").split("-- Postflight (read-only)")[-1]
    return "\n".join(line[3:] for line in tail.splitlines()[1:] if line.startswith("-- "))


def _twins(cur) -> set[str]:
    cur.execute("SELECT indexname FROM pg_indexes WHERE indexname LIKE 'uq\\_%\\_workspace\\_%'")
    return {row[0] for row in cur.fetchall()}


DUPLICATES = [
    "INSERT INTO fixed_expenses(workspace_id, name) VALUES (%(ws)s, 'Rent')",
    "INSERT INTO debt_payments(workspace_id, debt_id, payment_type, payment_date) VALUES (%(ws)s, 1, 'monthly_payment', '2026-09-01')",
    "INSERT INTO fixed_expense_matches(workspace_id, fixed_expense_id, period_month) VALUES (%(ws)s, 1, '2026-09')",
    "INSERT INTO credit_card_settings(workspace_id, bank, card_last4) VALUES (%(ws)s, 'Bank', '1234')",
]


@pytest.mark.parametrize("statement", DUPLICATES)
def test_without_user_id_only_the_workspace_twin_deduplicates(cur, statement):
    cur.execute(MIGRATION.read_text(encoding="utf-8"))
    cur.execute(MIGRATION.read_text(encoding="utf-8"))  # idempotent
    cur.execute(_postflight())
    assert cur.fetchall() == []
    cur.execute(statement, {"ws": WS})
    with pytest.raises(psycopg2.errors.UniqueViolation):
        cur.execute(statement, {"ws": WS})
    cur.execute(statement, {"ws": str(uuid.uuid4())})  # another workspace is independent


def test_rows_that_are_distinct_today_stay_valid(cur):
    # NULL card numbers and non-monthly payments were never unique; the twin keeps that.
    for _ in range(2):
        cur.execute("INSERT INTO credit_card_settings(user_id, workspace_id, bank) VALUES (1, %s, 'Bank')", (WS,))
        cur.execute("""INSERT INTO debt_payments(user_id, workspace_id, debt_id, payment_type, payment_date)
                       VALUES (1, %s, 1, 'manual', '2026-09-01')""", (WS,))
    cur.execute(MIGRATION.read_text(encoding="utf-8"))
    assert len(_twins(cur)) == 5  # four new twins and the one that already existed


def test_existing_workspace_duplicates_abort_and_change_nothing(cur):
    # Two legacy ids in one workspace (the two id spaces): distinct today, duplicates by workspace.
    cur.execute("INSERT INTO fixed_expenses(user_id, workspace_id, name) VALUES (1, %s, 'Rent'), (2, %s, 'Rent')", (WS, WS))
    with pytest.raises(psycopg2.Error) as refused:
        cur.execute(MIGRATION.read_text(encoding="utf-8"))
    assert refused.value.pgcode == "UK001"
    cur.execute("ROLLBACK")
    assert _twins(cur) == {"uq_ai_usage_daily_workspace_date"}
    cur.execute("SELECT count(*) FROM fixed_expenses")
    assert cur.fetchone() == (2,)


def test_a_user_id_rule_without_a_twin_is_refused(cur):
    cur.execute("CREATE TABLE settings_synthetic (user_id BIGINT, workspace_id UUID, k TEXT, UNIQUE (user_id, k))")
    with pytest.raises(psycopg2.Error) as refused:
        cur.execute(MIGRATION.read_text(encoding="utf-8"))
    assert refused.value.pgcode == "UK002" and "settings_synthetic" in str(refused.value)


def test_the_rollback_drops_only_the_twins_it_created(cur):
    cur.execute(MIGRATION.read_text(encoding="utf-8"))
    cur.execute(ROLLBACK.read_text(encoding="utf-8"))
    assert _twins(cur) == {"uq_ai_usage_daily_workspace_date"}
    cur.execute(_postflight())
    assert len(cur.fetchall()) == 4
