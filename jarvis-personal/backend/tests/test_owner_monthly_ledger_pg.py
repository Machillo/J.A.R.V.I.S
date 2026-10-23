"""The Owner's single monthly ledger on a real PostgreSQL (Owner audit, Fase 1 §2).

One month holds every movement type plus the other ledger tables. The Owner's Resumen del mes,
list and ledger must agree with the rules; another workspace's rows never count; a regular
user keeps the current totals. Only SELECTs run against the seeded data.

Uses DINCR_TEST_POSTGRES_URL or the embedded `pgserver`; CI sets DINCR_REQUIRE_PG_TESTS=1 so
they fail instead of skipping. All data is synthetic.
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
CREATE TABLE salaries (id BIGSERIAL PRIMARY KEY, workspace_id UUID, user_id BIGINT, amount NUMERIC(14,2), source TEXT, category TEXT,
    original_amount NUMERIC, original_currency TEXT, exchange_rate NUMERIC, created_at TIMESTAMP NOT NULL DEFAULT NOW());
CREATE TABLE expenses (id BIGSERIAL PRIMARY KEY, workspace_id UUID, user_id BIGINT, amount NUMERIC(14,2), category TEXT, expense_type TEXT,
    description TEXT, original_amount NUMERIC, original_currency TEXT, exchange_rate NUMERIC, created_at TIMESTAMP NOT NULL DEFAULT NOW());
CREATE TABLE payroll_events (id BIGSERIAL PRIMARY KEY, workspace_id UUID, user_id BIGINT, event_type TEXT, amount NUMERIC(14,2),
    description TEXT, event_date DATE, created_at TIMESTAMP NOT NULL DEFAULT NOW());
CREATE TABLE bonuses (id BIGSERIAL PRIMARY KEY, workspace_id UUID, user_id BIGINT, amount NUMERIC(14,2), description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW());
CREATE TABLE financial_goals (id BIGSERIAL PRIMARY KEY, workspace_id UUID, current_amount NUMERIC, target_amount NUMERIC);
CREATE TABLE financial_profiles (account_id TEXT, workspace_id UUID, liquid_savings NUMERIC);
"""

OCTOBER, NOVEMBER = date(2026, 10, 1), date(2026, 11, 1)


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

    name = f"owner_ledger_{uuid.uuid4().hex[:12]}"
    admin = psycopg2.connect(admin_uri)
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{name}"')
    parts = urlsplit(admin_uri)
    uri = urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment))
    conn = psycopg2.connect(uri)
    conn.autocommit = True
    q(conn, SCHEMA)
    for ws in (WS_A, WS_B):  # the same month in another workspace: it must never count for WS_A
        for kind, amount in (("income", 1000), ("expense", 400), ("refund", 100), ("debt_payment", 300),
                             ("loan_received", 500), ("receivable_payment", 200), ("asset_sale", 50),
                             ("receivable_offset", 70), ("internal_transfer", 900), ("transfer", 60), ("reimbursement", 40)):
            q(conn, "INSERT INTO transactions (workspace_id, transaction_date, amount, transaction_type) VALUES (%s, '2026-10-15', %s, %s)",
              (ws, amount, kind))
        q(conn, "INSERT INTO salaries (workspace_id, amount, created_at) VALUES (%s, 2000, '2026-10-30 10:00')", (ws,))
        q(conn, "INSERT INTO expenses (workspace_id, amount, category, created_at) VALUES (%s, 60, 'Comida', '2026-10-05 10:00')", (ws,))
        q(conn, "INSERT INTO bonuses (workspace_id, amount, created_at) VALUES (%s, 250, '2026-10-20 10:00')", (ws,))
        # Overtime that happened on 31 Oct but was recorded on 1 Nov: it belongs to October.
        q(conn, "INSERT INTO payroll_events (workspace_id, amount, event_type, event_date, created_at) VALUES (%s, 80, 'ot', '2026-10-31', '2026-11-01 09:00')", (ws,))
        # A refund in November only: never income, and November's spending does not go negative.
        q(conn, "INSERT INTO transactions (workspace_id, transaction_date, amount, transaction_type) VALUES (%s, '2026-11-03', 30, 'refund')", (ws,))
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    database.close_idle_connections()
    try:
        yield conn
    finally:
        database.close_idle_connections()
        conn.close()
        with admin.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.close()


def _as(role):
    from backend.auth.current_user import set_current_user
    return set_current_user({"id": 7, "account_id": "account-a", "workspace_id": WS_A, "role": role})


def test_the_owner_month_follows_the_rules_and_ignores_other_workspaces(db):
    from backend.core.database import get_connection
    from backend.user_product.owner_ledger import owner_month_totals

    with get_connection() as conn:
        october = owner_month_totals(conn, WS_A, OCTOBER, NOVEMBER)
        november = owner_month_totals(conn, WS_A, NOVEMBER, date(2026, 12, 1))
    assert october == {
        "income": 1000 + 2000 + 250 + 80,      # income + salaries + bonus + overtime by its event date
        "expenses": 400 + 60 - 100,            # spending net of the refund
        "gross_expenses": 460, "refunds": 100, "unmatched_refunds": 0,
        "debt_paid": 300,
        "other_inflows": 500 + 200 + 50,       # loan, collection, asset sale: money in, not income
        "balance": 3330 - 360 - 300,
        "cash_flow": 2670 + 750,
        "unclassified_count": 2,               # the unclassified transfer and the undecided reimbursement
    }
    assert november["income"] == 0 and november["expenses"] == 0 and november["unmatched_refunds"] == 30


@pytest.mark.parametrize("role,expected", [
    ("owner", {"income": 3330, "expenses": 360, "debt_paid": 300, "balance": 2670}),
    # Regular users keep today's totals: gross spending, overtime by its recording date, no bonuses.
    ("user", {"income": 3000, "expenses": 460, "debt_paid": 300, "balance": 2240}),
])
def test_resumen_del_mes_changes_only_for_the_owner(db, role, expected):
    from backend.auth.current_user import reset_current_user
    from backend.user_product import free_service

    token = _as(role)
    try:
        summary = free_service.get_free_monthly_summary("2026-10")
    finally:
        reset_current_user(token)
    assert {key: summary[key] for key in expected} == expected


def test_the_owner_list_says_what_each_row_is_and_keeps_the_old_type(db):
    from backend.auth.current_user import reset_current_user
    from backend.user_product import free_service

    token = _as("owner")
    try:
        owner_rows = free_service.list_free_movements()
    finally:
        reset_current_user(token)
    token = _as("user")
    try:
        user_rows = free_service.list_free_movements()
    finally:
        reset_current_user(token)
    kinds = {row["movement_kind"]: row["counts_in"] for row in owner_rows if row["origin"] == "transaction"}
    assert kinds["loan_received"] == "other_inflows" and kinds["refund"] == "refunds"
    assert kinds["debt_payment"] == "debt_payments" and kinds["transfer"] == "unclassified"
    assert kinds["reimbursement"] == "unclassified" and kinds["receivable_offset"] == "not_counted"
    assert "internal_transfer" not in kinds, "confirmed own transfers stay out of the list, as today"
    assert {row["transaction_type"] for row in owner_rows} <= {"income", "expense"}
    # Same rows, same order, same old fields; only the Owner gets the two new ones.
    strip = lambda rows: [{k: v for k, v in row.items() if k not in ("movement_kind", "counts_in")} for row in rows]
    assert strip(owner_rows) == user_rows
    assert all("movement_kind" not in row and "counts_in" not in row and "ledger_type" not in row for row in user_rows)
