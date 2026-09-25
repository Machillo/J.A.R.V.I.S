"""Retiring the off-store billing schema drops only empty tables (real PostgreSQL)."""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg2 = pytest.importorskip("psycopg2")

ROOT = Path(__file__).resolve().parents[2] / "database"
MIGRATION = ROOT / "migrations" / "20260926120000_retire_offstore_billing.sql"
ROLLBACK = ROOT / "rollback" / "20260926120000_retire_offstore_billing_rollback.sql"
CREATE_ORIGINAL = ROOT / "migrations" / "20260910_finva_beta_product_ops.sql"


@pytest.fixture
def cur(tmp_path):
    server = pgserver.get_server(str(os.environ.get("DINCR_PGSERVER_DIR") or tmp_path / "pg"), cleanup_mode="stop")
    admin = psycopg2.connect(server.get_uri())
    admin.autocommit = True
    name = f"billing_{os.getpid()}_{abs(hash(str(tmp_path))) % 10**8}"
    with admin.cursor() as c:
        c.execute(f"CREATE DATABASE {name}")
    conn = psycopg2.connect(server.get_uri(name))
    conn.autocommit = True
    cursor = conn.cursor()
    cursor.execute("DO $$ BEGIN CREATE ROLE anon NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
                   "DO $$ BEGIN CREATE ROLE authenticated NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
                   "CREATE TABLE accounts (id UUID PRIMARY KEY)")
    cursor.execute(CREATE_ORIGINAL.read_text(encoding="utf-8"))
    yield cursor
    conn.close()
    with admin.cursor() as c:
        c.execute(f"DROP DATABASE {name} WITH (FORCE)")
    admin.close()


def _present(cur):
    cur.execute("SELECT count(*) FROM unnest(ARRAY['billing_orders','billing_subscriptions','finva_beta_programs']) t "
                "WHERE to_regclass('public.' || t) IS NOT NULL")
    return cur.fetchone()[0]


def test_empty_off_store_billing_is_retired_and_the_rollback_recreates_it(cur):
    cur.execute(MIGRATION.read_text(encoding="utf-8"))
    assert _present(cur) == 0
    cur.execute(ROLLBACK.read_text(encoding="utf-8"))
    assert _present(cur) == 3
    cur.execute(MIGRATION.read_text(encoding="utf-8"))  # and it can be retired again
    assert _present(cur) == 0


@pytest.mark.parametrize("table", ["billing_orders", "billing_subscriptions"])
def test_any_billing_row_aborts_and_drops_nothing(cur, table):
    account = str(uuid.uuid4())
    cur.execute("INSERT INTO accounts VALUES (%s)", (account,))
    if table == "billing_orders":
        cur.execute("INSERT INTO billing_orders(account_id, plan_code, amount, consent_version, consent_at) "
                    "VALUES (%s, 'vip', 4990, 'v1', NOW())", (account,))
    else:
        cur.execute("INSERT INTO billing_subscriptions(account_id, plan_code, status) VALUES (%s, 'vip', 'active')", (account,))
    with pytest.raises(psycopg2.Error) as refused:
        cur.execute(MIGRATION.read_text(encoding="utf-8"))
    assert refused.value.pgcode == "BL001"
    cur.execute("ROLLBACK")
    assert _present(cur) == 3


def test_only_a_live_store_subscription_grants_a_paid_plan(cur, monkeypatch):
    """A paid plan comes only from the store; trial and grace count until they end, nothing else does."""
    from backend.core import database
    from backend.product_ops.service import has_store_entitlement

    uri = cur.connection.dsn
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    with database.get_connection() as conn:
        assert has_store_entitlement(conn, str(uuid.uuid4())) is False  # no store table yet: nothing is paid
    cur.execute("""CREATE TABLE store_subscriptions (account_id UUID PRIMARY KEY, plan_code TEXT, status TEXT,
                   trial_ends_at TIMESTAMPTZ, current_period_end TIMESTAMPTZ)""")
    cases = {
        ("active", None, "+1 day"): True,
        ("active", None, "-1 day"): False,
        ("trialing", "+1 day", "+30 days"): True,
        ("trialing", "-1 day", "+30 days"): False,   # the trial ended; its period end is not access
        ("grace_period", None, "+1 day"): True,
        ("canceled", None, "+1 day"): False,
        ("expired", None, "+1 day"): False,
        ("revoked", None, "+1 day"): False,
    }
    accounts = {}
    for (status, trial, period), _expected in cases.items():
        account = str(uuid.uuid4())
        accounts[(status, trial, period)] = account
        cur.execute("INSERT INTO store_subscriptions VALUES (%s, 'vip', %s, NOW() + %s::interval, NOW() + %s::interval)",
                    (account, status, trial, period))
    with database.get_connection() as conn:
        for key, expected in cases.items():
            assert has_store_entitlement(conn, accounts[key]) is expected, key
            assert has_store_entitlement(conn, accounts[key], "basic") is False, key  # other plan
