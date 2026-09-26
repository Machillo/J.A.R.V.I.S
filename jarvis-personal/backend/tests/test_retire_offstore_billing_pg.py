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
    cur.execute("""CREATE TABLE store_subscriptions (account_id UUID PRIMARY KEY, provider TEXT, plan_code TEXT, status TEXT,
                   trial_ends_at TIMESTAMPTZ, current_period_end TIMESTAMPTZ)""")
    cases = {
        ("active", None, "+1 day"): True,
        ("active", None, "-1 day"): False,
        ("trialing", "+1 day", "+30 days"): True,
        ("trialing", "-1 day", "+30 days"): False,   # the trial ended; its period end is not access
        ("grace_period", None, "+1 day"): True,
        ("grace_period", None, "-1 day"): False,
        ("canceled", None, "+1 day"): False,
        ("expired", None, "+1 day"): False,
        ("revoked", None, "+1 day"): False,
    }
    accounts = {}
    for (status, trial, period), _expected in cases.items():
        account = str(uuid.uuid4())
        accounts[(status, trial, period)] = account
        cur.execute("INSERT INTO store_subscriptions VALUES (%s, 'google', 'vip', %s, NOW() + %s::interval, NOW() + %s::interval)",
                    (account, status, trial, period))
    simulated = str(uuid.uuid4())  # the Owner-only QA simulator writes provider 'sandbox'
    cur.execute("INSERT INTO store_subscriptions VALUES (%s, 'sandbox', 'vip', 'active', NULL, NOW() + interval '30 days')",
                (simulated,))
    with database.get_connection() as conn:
        for key, expected in cases.items():
            assert has_store_entitlement(conn, accounts[key]) is expected, key
            assert has_store_entitlement(conn, accounts[key], "basic") is False, key  # other plan
        assert has_store_entitlement(conn, simulated) is False


def test_more_than_the_configuration_row_aborts(cur):
    cur.execute("INSERT INTO finva_beta_programs(code) VALUES ('beta-2026-02') ON CONFLICT DO NOTHING")
    cur.execute("SELECT count(*) FROM finva_beta_programs")
    assert cur.fetchone()[0] == 2
    with pytest.raises(psycopg2.Error) as refused:
        cur.execute(MIGRATION.read_text(encoding="utf-8"))
    assert refused.value.pgcode == "BL001"
    cur.execute("ROLLBACK")
    assert _present(cur) == 3


CALLER_SCHEMA = """
ALTER TABLE accounts ADD COLUMN role TEXT DEFAULT 'user', ADD COLUMN onboarding_level TEXT, ADD COLUMN plan_selected BOOLEAN,
    ADD COLUMN onboarding_completed BOOLEAN, ADD COLUMN updated_at TIMESTAMPTZ;
CREATE TABLE plans (id BIGSERIAL PRIMARY KEY, code TEXT UNIQUE, name TEXT, is_active BOOLEAN DEFAULT TRUE);
INSERT INTO plans(code, name) VALUES ('free', 'Gratis'), ('basic', 'Basic'), ('vip', 'VIP');
CREATE TABLE features (id BIGSERIAL PRIMARY KEY, code TEXT UNIQUE);
INSERT INTO features(code) VALUES ('strategy_vip');
CREATE TABLE plan_features (plan_id BIGINT, feature_id BIGINT, enabled BOOLEAN);
INSERT INTO plan_features SELECT p.id, f.id, TRUE FROM plans p, features f WHERE p.code = 'vip';
CREATE TABLE account_subscriptions (id BIGSERIAL PRIMARY KEY, account_id UUID UNIQUE, plan_id BIGINT, status TEXT,
    access_source TEXT, started_at TIMESTAMPTZ, expires_at TIMESTAMPTZ, last_payment_at TIMESTAMPTZ, courtesy_note TEXT,
    granted_by UUID, granted_at TIMESTAMPTZ, created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW());
CREATE TABLE store_subscriptions (account_id UUID PRIMARY KEY, provider TEXT, plan_code TEXT, status TEXT,
    trial_ends_at TIMESTAMPTZ, current_period_end TIMESTAMPTZ);
"""


@pytest.fixture
def caller(cur, monkeypatch):
    from backend.auth import saas
    from backend.core import database

    cur.execute(MIGRATION.read_text(encoding="utf-8"))  # the retired tables are gone, as after the deploy
    cur.execute(CALLER_SCHEMA)
    monkeypatch.setattr(database, "DATABASE_URL", cur.connection.dsn)
    state = {}
    monkeypatch.setattr(saas, "get_current_user", lambda: {"role": "user", "account_id": state["account"]})
    monkeypatch.setattr(saas, "get_current_account_id", lambda: state["account"])

    def account(plan, source, expires="NULL", store=None):
        state["account"] = str(uuid.uuid4())
        cur.execute("INSERT INTO accounts(id, onboarding_level, plan_selected) VALUES (%s, %s, TRUE)", (state["account"], plan))
        cur.execute(f"""INSERT INTO account_subscriptions(account_id, plan_id, status, access_source, expires_at, courtesy_note)
                        SELECT %s, id, 'active', %s, {expires}, 'launch-free-2026' FROM plans WHERE code = %s""",
                    (state["account"], source, plan))
        if store:
            cur.execute("INSERT INTO store_subscriptions VALUES (%s, %s, 'vip', 'active', NULL, NOW() + interval '20 days')",
                        (state["account"], store))
        return state["account"]
    return saas, account


@pytest.mark.parametrize(("store", "allowed"), [("google", True), ("apple", True), ("sandbox", False), (None, False)])
def test_a_self_service_paid_plan_needs_a_real_store_subscription(caller, store, allowed):
    saas, account = caller
    account("vip", "self_service", store=store)
    if allowed:
        assert saas.require_feature("strategy_vip") is True
    else:
        with pytest.raises(Exception) as refused:
            saas.require_feature("strategy_vip")
        assert getattr(refused.value, "status_code", None) == 402


@pytest.mark.parametrize(("store", "plan_after"), [("google", "vip"), ("sandbox", "free"), (None, "free")])
def test_the_end_of_the_promotion_keeps_only_a_real_store_plan(caller, cur, store, plan_after):
    saas, account = caller
    created = account("vip", "courtesy", expires="NOW() - interval '1 minute'", store=store)
    from backend.core import database
    with database.get_connection() as conn:
        subscription = saas._subscription(conn, created)
        conn.commit()
    assert subscription["plan"] == plan_after and subscription["access_notice"]["code"] == "promotion_ended"
