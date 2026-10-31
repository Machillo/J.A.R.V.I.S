"""Patrimonio (VIP and the Owner) on a real PostgreSQL: what you have minus what you owe.

Accounts count at their declared balance plus later movements, in colones at the recorded rate;
the Salvavidas counts once (its linked account is not counted again); a negative balance is
owed; unknown values are named and leave net worth unknown, never 0. Another workspace never
counts, and reading never writes. Synthetic data only.

Uses DINCR_TEST_POSTGRES_URL or the embedded `pgserver`; CI sets DINCR_REQUIRE_PG_TESTS=1.
"""
from __future__ import annotations

import os
import uuid
from urllib.parse import urlsplit, urlunsplit

import pytest

psycopg2 = pytest.importorskip("psycopg2")

WS_A, WS_B = "00000000-0000-4000-8000-0000000000a2", "00000000-0000-4000-8000-0000000000b2"

SCHEMA = """
CREATE TABLE account_balances (id BIGSERIAL PRIMARY KEY, workspace_id UUID, account_name TEXT, account_type TEXT, currency TEXT,
    current_balance NUMERIC(14,2), balance_as_of TIMESTAMPTZ, is_active BOOLEAN DEFAULT TRUE, include_in_net_worth BOOLEAN DEFAULT TRUE);
CREATE TABLE transactions (id BIGSERIAL PRIMARY KEY, workspace_id UUID, financial_account_id BIGINT, transaction_date DATE,
    amount NUMERIC(14,2), transaction_type TEXT, created_at TIMESTAMPTZ DEFAULT NOW());
CREATE TABLE exchange_rates (id BIGSERIAL PRIMARY KEY, workspace_id UUID, currency TEXT, exchange_rate NUMERIC, rate_date DATE);
CREATE TABLE investments (id BIGSERIAL PRIMARY KEY, workspace_id UUID, name TEXT, amount NUMERIC(14,2));
CREATE TABLE debts (id BIGSERIAL PRIMARY KEY, workspace_id UUID, name TEXT, remaining_amount NUMERIC(14,2));
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


def q(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)


@pytest.fixture
def db(admin_uri, monkeypatch):
    from backend.core import database
    from backend.user_product import wealth

    name = f"wealth_{uuid.uuid4().hex[:12]}"
    admin = psycopg2.connect(admin_uri)
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{name}"')
    parts = urlsplit(admin_uri)
    conn = psycopg2.connect(urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment)))
    conn.autocommit = True
    q(conn, SCHEMA)
    for ws in (WS_A, WS_B):
        q(conn, "INSERT INTO account_balances (workspace_id, account_name, account_type, currency, current_balance, balance_as_of) VALUES (%s, 'Cuenta corriente', 'checking', 'CRC', 100000, '2026-10-01 12:00-06')", (ws,))
        q(conn, "INSERT INTO debts (workspace_id, name, remaining_amount) VALUES (%s, 'Préstamo sintético', 300000)", (ws,))
    monkeypatch.setattr(database, "DATABASE_URL", urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment)))
    monkeypatch.setattr(wealth, "get_salvavidas_state", lambda: {"current_amount": 50000})
    database.close_idle_connections()
    try:
        yield conn
    finally:
        database.close_idle_connections()
        conn.close()
        with admin.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.close()


def _wealth():
    from backend.auth.current_user import reset_current_user, set_current_user
    from backend.user_product import wealth

    token = set_current_user({"id": 7, "account_id": "account-a", "workspace_id": WS_A, "role": "user"})
    try:
        return wealth.get_wealth()
    finally:
        reset_current_user(token)


def _counts(conn):
    with conn.cursor() as cur:
        result = {}
        for table in ("account_balances", "transactions", "debts", "investments", "exchange_rates"):
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            result[table] = cur.fetchone()[0]
        return result


def test_net_worth_is_what_you_have_minus_what_you_owe(db):
    # A deposit after the declaration moves the balance; one before it was already in it.
    q(db, "INSERT INTO transactions (workspace_id, financial_account_id, transaction_date, amount, transaction_type) VALUES (%s, 1, '2026-10-05', 20000, 'income')", (WS_A,))
    q(db, "INSERT INTO transactions (workspace_id, financial_account_id, transaction_date, amount, transaction_type) VALUES (%s, 1, '2026-09-20', 99999, 'income')", (WS_A,))
    q(db, "INSERT INTO investments (workspace_id, name, amount) VALUES (%s, 'Fondo sintético', 75000)", (WS_A,))
    before = _counts(db)
    result = _wealth()
    assert _counts(db) == before, "reading never writes"
    assert [row["amount"] for row in result["assets"]["accounts"]] == [120000.0]
    assert result["assets"]["salvavidas"] == {"name": "Salvavidas", "amount": 50000.0}
    assert result["assets"]["investments"] == [{"name": "Fondo sintético", "amount": 75000.0}]
    assert result["assets"]["total"] == 245000.0 and result["liabilities"]["total"] == 300000.0
    assert result["net_worth"] == -55000.0 and result["complete"] is True and result["unknown"] == []


def test_the_salvavidas_account_counts_once_and_an_overdraft_is_owed(db):
    q(db, "INSERT INTO account_balances (workspace_id, account_name, account_type, currency, current_balance, balance_as_of) VALUES (%s, 'Salvavidas', 'emergency_fund', 'CRC', 40000, '2026-10-01 12:00-06')", (WS_A,))
    q(db, "INSERT INTO account_balances (workspace_id, account_name, account_type, currency, current_balance, balance_as_of) VALUES (%s, 'Sobregiro', 'checking', 'CRC', -8000, '2026-10-01 12:00-06')", (WS_A,))
    q(db, "INSERT INTO account_balances (workspace_id, account_name, account_type, currency, current_balance, balance_as_of, include_in_net_worth) VALUES (%s, 'Detectada', 'checking', 'CRC', 900000, '2026-10-01 12:00-06', FALSE)", (WS_A,))
    result = _wealth()
    assert [row["name"] for row in result["assets"]["accounts"]] == ["Cuenta corriente"], "not the Salvavidas account, not one left out"
    assert result["liabilities"]["accounts"][0]["amount"] == 8000.0
    assert result["net_worth"] == round(100000 + 50000 - 300000 - 8000, 2)


def test_another_currency_uses_the_recorded_rate_and_without_one_it_is_unknown(db):
    q(db, "INSERT INTO account_balances (workspace_id, account_name, account_type, currency, current_balance, balance_as_of) VALUES (%s, 'Cuenta en dólares', 'checking', 'USD', 100, '2026-10-01 12:00-06')", (WS_A,))
    unknown = _wealth()
    assert unknown["net_worth"] is None and unknown["complete"] is False and unknown["unknown"] == ["Cuenta en dólares"]
    assert unknown["assets"]["total"] == 150000.0, "the known parts are still added"
    q(db, "INSERT INTO exchange_rates (workspace_id, currency, exchange_rate, rate_date) VALUES (%s, 'USD', 500, '2026-10-01')", (WS_A,))
    q(db, "INSERT INTO exchange_rates (workspace_id, currency, exchange_rate, rate_date) VALUES (%s, 'USD', 999, '2026-10-02')", (WS_B,))
    known = _wealth()
    dollars = next(row for row in known["assets"]["accounts"] if row["currency"] == "USD")
    assert dollars == {**dollars, "original_amount": 100.0, "amount": 50000.0}
    assert known["complete"] is True


def test_an_unknown_salvavidas_or_debt_is_named_not_zero(db, monkeypatch):
    from backend.user_product import wealth

    monkeypatch.setattr(wealth, "get_salvavidas_state", lambda: {"current_amount": None})
    q(db, "INSERT INTO debts (workspace_id, name, remaining_amount) VALUES (%s, 'Deuda sin saldo', NULL)", (WS_A,))
    result = _wealth()
    assert result["assets"]["salvavidas"]["amount"] is None
    assert set(result["unknown"]) == {"Salvavidas", "Deuda sin saldo"} and result["net_worth"] is None
