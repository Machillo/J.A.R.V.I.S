"""Movements after a declared balance are decided by the economic date, on a real PostgreSQL.

A movement's ``transaction_date`` says when it happened; ``created_at`` says when DINCR
recorded it. Account balances, reconciliation, the month-end forecast and net worth all
add to a declared balance only the movements that happened after it. ``created_at`` only
breaks the tie for a movement dated the same local day as the declaration.

Uses DINCR_TEST_POSTGRES_URL or the embedded `pgserver`; CI sets DINCR_REQUIRE_PG_TESTS=1
so they fail instead of skipping. All data is synthetic.
"""
from __future__ import annotations

import os
import uuid
from datetime import date
from urllib.parse import urlsplit, urlunsplit

import pytest

psycopg2 = pytest.importorskip("psycopg2")

WS_A, WS_B = "00000000-0000-4000-8000-0000000000a1", "00000000-0000-4000-8000-0000000000b1"

SCHEMA = """
CREATE TABLE transactions (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT, workspace_id UUID NOT NULL, transaction_date DATE NOT NULL,
    description TEXT NOT NULL DEFAULT '', amount NUMERIC(14,2) NOT NULL, transaction_type TEXT NOT NULL, category TEXT,
    account TEXT, source TEXT, notes TEXT, original_amount NUMERIC(14,2), original_currency TEXT, exchange_rate NUMERIC(14,6),
    financial_account_id BIGINT, created_at TIMESTAMP NOT NULL DEFAULT NOW());
CREATE TABLE account_balances (
    id BIGSERIAL PRIMARY KEY, workspace_id UUID NOT NULL, account_name TEXT NOT NULL, bank_name TEXT DEFAULT '',
    account_type TEXT DEFAULT 'checking', account_last4 TEXT DEFAULT '', currency TEXT DEFAULT 'CRC',
    annual_interest_rate NUMERIC DEFAULT 0, last_reconciliation_difference NUMERIC DEFAULT 0,
    current_balance NUMERIC(14,2) NOT NULL DEFAULT 0, balance_as_of TIMESTAMPTZ NOT NULL DEFAULT NOW(), source TEXT DEFAULT 'manual',
    include_in_net_worth BOOLEAN DEFAULT TRUE, is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE account_balance_history (
    id BIGSERIAL PRIMARY KEY, workspace_id UUID, financial_account_id BIGINT, balance NUMERIC, currency TEXT, source TEXT, note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW());
CREATE TABLE exchange_rates (id BIGSERIAL PRIMARY KEY, workspace_id UUID, currency TEXT, exchange_rate NUMERIC, rate_date DATE);
CREATE TABLE savings (id BIGSERIAL PRIMARY KEY, name TEXT, amount NUMERIC, created_at TIMESTAMPTZ DEFAULT NOW(), user_id BIGINT, workspace_id UUID);
CREATE TABLE investments (id BIGSERIAL PRIMARY KEY, name TEXT, amount NUMERIC, created_at TIMESTAMPTZ DEFAULT NOW(), user_id BIGINT, workspace_id UUID);
CREATE TABLE investment_portfolio_snapshots (
    id BIGSERIAL PRIMARY KEY, workspace_id UUID, user_id BIGINT, market_value_crc NUMERIC, market_value NUMERIC, snapshot_at TIMESTAMPTZ,
    snapshot_date DATE, account_id_masked TEXT, currency TEXT, exchange_rate_crc NUMERIC, source TEXT, account_mode TEXT,
    included_in_net_worth BOOLEAN);
CREATE TABLE debts (
    id BIGSERIAL PRIMARY KEY, workspace_id UUID, user_id BIGINT, name TEXT, debt_type TEXT, total_amount NUMERIC, remaining_amount NUMERIC,
    monthly_payment NUMERIC, interest_rate NUMERIC, term_months INT, payment_day INT, interest_method TEXT, fixed_fee_amount NUMERIC,
    created_at TIMESTAMPTZ DEFAULT NOW());
"""
TABLES = ("transactions", "account_balances", "account_balance_history")

# A balance declared on 2026-09-30 at 07:54 in Costa Rica (13:54 UTC).
DECLARED = "2026-09-30 07:54:00-06"


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


@pytest.fixture
def db(admin_uri, monkeypatch):
    from backend.core import database
    from backend.auth.current_user import reset_current_user, set_current_user
    from backend.finance import service

    name = f"balances_{uuid.uuid4().hex[:12]}"
    admin = psycopg2.connect(admin_uri)
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{name}"')
    parts = urlsplit(admin_uri)
    uri = urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment))
    conn = psycopg2.connect(uri)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(SCHEMA)
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    # Net worth also stores a history snapshot (a separate, pre-existing write); not under test here.
    monkeypatch.setattr(service, "_save_net_worth_snapshot", lambda *args, **kwargs: [])
    database.close_idle_connections()
    token = set_current_user({"id": 7, "account_id": "account-a", "workspace_id": WS_A, "role": "owner"})
    try:
        yield conn
    finally:
        reset_current_user(token)
        database.close_idle_connections()
        conn.close()
        with admin.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.close()


def q(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall() if cur.description else None


def account(conn, balance=100000, declared=DECLARED, ws=WS_A, name="Cuenta"):
    return q(conn, "INSERT INTO account_balances (workspace_id, account_name, current_balance, balance_as_of) VALUES (%s, %s, %s, %s) RETURNING id",
             (ws, name, balance, declared))[0][0]


def movement(conn, acc, day, amount, kind="expense", created="2026-10-01 21:21:00-06", ws=WS_A):
    """A linked movement whose economic date is ``day`` and which DINCR recorded at ``created``."""
    # created_at is a timestamp without time zone holding the session's local time, like NOW().
    return q(conn, """INSERT INTO transactions (workspace_id, transaction_date, amount, transaction_type, financial_account_id, created_at)
                      VALUES (%s, %s, %s, %s, %s, (%s::timestamptz)::timestamp) RETURNING id""", (ws, day, amount, kind, acc, created))[0][0]


def balances():
    from backend.finance import intelligence
    return {item["id"]: item for item in intelligence.list_account_balances()["items"]}


def test_a_january_movement_imported_in_october_does_not_move_a_september_balance(db):
    """The core regression: history imported after a declaration was already in it."""
    acc = account(db)
    movement(db, acc, "2026-01-15", 18277.75, "expense", created="2026-10-01 21:21:00-06")
    item = balances()[acc]
    assert item["movements_since_balance"] == 0
    assert float(item["calculated_balance"]) == 100000.0


def test_the_economic_date_decides_and_created_at_keeps_its_meaning(db):
    acc = account(db)
    before = movement(db, acc, "2026-09-29", 1000, "expense", created="2026-10-02 09:00:00-06")   # recorded later, happened before
    after = movement(db, acc, "2026-10-01", 2500, "expense", created="2026-10-02 09:00:00-06")    # happened after
    item = balances()[acc]
    assert item["movements_since_balance"] == 1 and float(item["calculated_balance"]) == 97500.0
    # created_at still holds the real recording moment of both rows; nothing was rewritten.
    stored = dict(q(db, "SELECT id, (created_at::timestamptz AT TIME ZONE 'America/Costa_Rica')::text FROM transactions"))
    assert stored[before].startswith("2026-10-02 09:00") and stored[after].startswith("2026-10-02 09:00")


@pytest.mark.parametrize("created, counted", [("2026-09-30 07:00:00-06", False),   # recorded before the declaration that day
                                              ("2026-09-30 08:30:00-06", True)])   # recorded after it
def test_same_day_movements_use_created_at_only_as_the_tie_breaker(db, created, counted):
    acc = account(db)
    movement(db, acc, "2026-09-30", 4000, "expense", created=created)
    item = balances()[acc]
    assert item["movements_since_balance"] == (1 if counted else 0)
    assert float(item["calculated_balance"]) == (96000.0 if counted else 100000.0)


def test_the_declaration_day_is_the_costa_rica_day_not_the_utc_day(db):
    """Declared 2026-09-17 20:35 in Costa Rica = 2026-09-18 02:35 UTC: its day is the 17th."""
    acc = account(db, declared="2026-09-17 20:35:00-06")
    movement(db, acc, "2026-09-18", 700, "expense", created="2026-09-18 09:00:00-06")   # the next local day: after
    movement(db, acc, "2026-09-17", 300, "expense", created="2026-09-17 19:00:00-06")   # same local day, recorded before
    item = balances()[acc]
    assert item["movements_since_balance"] == 1 and float(item["calculated_balance"]) == 99300.0


@pytest.mark.parametrize("kind, effect", [("income", 1000), ("refund", 1000), ("reimbursement", 1000),
                                          ("receivable_payment", 1000), ("asset_sale", 1000),
                                          ("expense", -1000), ("debt_payment", -1000),
                                          ("receivable_offset", 0), ("internal_transfer", 0), ("transfer", 0)])
def test_cash_direction_of_each_movement_type(db, kind, effect):
    acc = account(db)
    movement(db, acc, "2026-10-05", 1000, kind, created="2026-10-05 10:00:00-06")
    assert float(balances()[acc]["calculated_balance"]) == 100000.0 + effect


def test_balances_reconciliation_forecast_and_net_worth_agree(db, monkeypatch):
    from backend.finance import intelligence, reconciliation, service, strategic_engine

    acc = account(db, balance=200000)
    movement(db, acc, "2026-01-10", 50000, "expense")                                     # history: ignored
    movement(db, acc, "2026-10-03", 30000, "income", created="2026-10-03 12:00:00-06")    # after: +30,000
    movement(db, acc, "2026-10-04", 5000, "expense", created="2026-10-04 12:00:00-06")    # after: -5,000
    expected = 225000.0
    assert float(balances()[acc]["calculated_balance"]) == expected
    [detail] = reconciliation.get_financial_reconciliation()["accounts"]
    assert detail["expected_balance"] == expected and detail["difference"] == 200000.0 - expected
    monkeypatch.setattr(strategic_engine, "_today", lambda: date(2026, 10, 6))
    assert strategic_engine.forecast_month_end_balance()["opening_available"] == expected
    assert service.get_net_worth_report()["assets"]["savings_total"] == expected
    # Declaring the real balance again records the difference against the same expectation.
    intelligence.upsert_account_balance("Cuenta", 224000)
    assert float(q(db, "SELECT last_reconciliation_difference FROM account_balances WHERE id = %s", (acc,))[0][0]) == -1000.0


def test_another_workspace_movement_never_moves_a_balance(db):
    acc = account(db)
    other = account(db, ws=WS_B, name="Otra")
    movement(db, acc, "2026-10-05", 999, "expense", ws=WS_B, created="2026-10-05 10:00:00-06")   # mislinked to A's account id
    movement(db, other, "2026-10-05", 111, "expense", ws=WS_B, created="2026-10-05 10:00:00-06")
    assert float(balances()[acc]["calculated_balance"]) == 100000.0
    assert other not in balances()


def test_reading_balances_writes_nothing(db):
    acc = account(db)
    movement(db, acc, "2026-10-05", 1000, "expense", created="2026-10-05 10:00:00-06")
    before = {t: q(db, f"SELECT * FROM {t} ORDER BY id") for t in TABLES}
    balances()
    assert {t: q(db, f"SELECT * FROM {t} ORDER BY id") for t in TABLES} == before
