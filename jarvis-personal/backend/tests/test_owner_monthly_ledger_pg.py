"""The Owner's single monthly ledger on a real PostgreSQL (Owner audit, Fase 1 §2).

The schema mirrors production: the record tables (salaries, expenses, payroll_events, bonuses)
keep ``created_at`` as ``timestamp without time zone`` written by ``NOW()`` in a UTC session,
and ``transactions.transaction_date`` is a ``date``. The Owner's month counts money received;
overtime, VGH and bonuses are gross payroll reported apart; record timestamps are read as Costa
Rica dates (UTC-6, no daylight saving). Another workspace's rows never count; a regular user
keeps today's totals. Only SELECTs run against the seeded data.

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
CREATE TABLE payroll_events (id BIGSERIAL PRIMARY KEY, workspace_id UUID, user_id BIGINT, event_type TEXT, hours NUMERIC(8,2),
    multiplier NUMERIC(8,4), amount NUMERIC(14,2), description TEXT, created_at TIMESTAMP NOT NULL DEFAULT NOW());
CREATE TABLE bonuses (id BIGSERIAL PRIMARY KEY, workspace_id UUID, user_id BIGINT, amount NUMERIC(14,2), description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW());
CREATE TABLE finva_email_candidates (id BIGSERIAL PRIMARY KEY, workspace_id UUID, transaction_date DATE, amount NUMERIC(14,2),
    transaction_type TEXT, status TEXT, is_internal_transfer BOOLEAN NOT NULL DEFAULT FALSE);
CREATE TABLE financial_goals (id BIGSERIAL PRIMARY KEY, workspace_id UUID, current_amount NUMERIC, target_amount NUMERIC);
CREATE TABLE financial_profiles (account_id TEXT, workspace_id UUID, liquid_savings NUMERIC);
CREATE TABLE accounts (id TEXT PRIMARY KEY, role TEXT, status TEXT, primary_email TEXT);
CREATE TABLE workspaces (id UUID PRIMARY KEY, owner_account_id TEXT);
CREATE TABLE allowed_users (email TEXT, role TEXT, status TEXT);
"""

SEPTEMBER, OCTOBER, NOVEMBER, DECEMBER = date(2026, 9, 1), date(2026, 10, 1), date(2026, 11, 1), date(2026, 12, 1)


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
    for ws in (WS_A, WS_B):  # the same months in another workspace: they must never count for WS_A
        for kind, amount in (("income", 1000), ("expense", 400), ("refund", 100), ("debt_payment", 300),
                             ("loan_received", 500), ("receivable_payment", 200), ("asset_sale", 50),
                             ("receivable_offset", 70), ("internal_transfer", 900), ("transfer", 60), ("reimbursement", 40)):
            q(conn, "INSERT INTO transactions (workspace_id, transaction_date, amount, transaction_type) VALUES (%s, '2026-10-15', %s, %s)",
              (ws, amount, kind))
        # The declared net salary, written by the app with its date at 12:00.
        q(conn, "INSERT INTO salaries (workspace_id, amount, created_at) VALUES (%s, 2000, '2026-10-30 12:00')", (ws,))
        q(conn, "INSERT INTO expenses (workspace_id, amount, category, created_at) VALUES (%s, 60, 'Comida', '2026-10-05 12:00')", (ws,))
        # Recorded at 22:00 on 30 Sep in Costa Rica (04:00 UTC on 1 Oct): a September expense.
        q(conn, "INSERT INTO expenses (workspace_id, amount, category, created_at) VALUES (%s, 25, 'Comida', '2026-10-01 04:00')", (ws,))
        # Gross payroll recorded through JARVIS at NOW() (UTC wall time):
        # overtime at 21:00 on 31 Oct in Costa Rica (03:00 UTC on 1 Nov) belongs to October;
        q(conn, "INSERT INTO payroll_events (workspace_id, amount, event_type, hours, multiplier, created_at) VALUES (%s, 80, 'ot', 2, 1.5, '2026-11-01 03:00')", (ws,))
        # a VGH (negative) in October; overtime at 01:00 on 1 Nov in Costa Rica (07:00 UTC) is November's.
        q(conn, "INSERT INTO payroll_events (workspace_id, amount, event_type, hours, multiplier, created_at) VALUES (%s, -15, 'vgh', 1, 1, '2026-10-12 15:00')", (ws,))
        q(conn, "INSERT INTO payroll_events (workspace_id, amount, event_type, hours, multiplier, created_at) VALUES (%s, 40, 'ot', 1, 1.5, '2026-11-01 07:00')", (ws,))
        q(conn, "INSERT INTO bonuses (workspace_id, amount, created_at) VALUES (%s, 250, '2026-10-20 18:00')", (ws,))
        # A refund in November only: never income, and November's spending does not go negative.
        q(conn, "INSERT INTO transactions (workspace_id, transaction_date, amount, transaction_type) VALUES (%s, '2026-11-03', 30, 'refund')", (ws,))
        q(conn, "INSERT INTO finva_email_candidates (workspace_id, transaction_date, amount, transaction_type, status) VALUES (%s, '2026-10-09', 99, 'income', 'pending')", (ws,))
        q(conn, "INSERT INTO finva_email_candidates (workspace_id, transaction_date, amount, transaction_type, status) VALUES (%s, '2026-10-10', 99, 'expense', 'confirmed')", (ws,))
        # A pending movement already proven to be between two own accounts is nothing to review.
        q(conn, "INSERT INTO finva_email_candidates (workspace_id, transaction_date, amount, transaction_type, status, is_internal_transfer) VALUES (%s, '2026-10-11', 99, 'internal_transfer', 'pending', TRUE)", (ws,))
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    # owner_account_context() checks the stored Owner identity; here the session role stands in for it.
    from backend.auth.current_user import get_current_user
    from backend.user_product import free_service
    monkeypatch.setattr(free_service, "owner_account_context",
                        lambda _conn, _account, _workspace: get_current_user().get("role") == "owner")
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


def _month(start, end):
    from backend.core.database import get_connection
    from backend.user_product.owner_ledger import owner_month_totals
    with get_connection() as conn:
        return owner_month_totals(conn, WS_A, start, end)


def test_the_owner_month_counts_money_received_and_reports_gross_payroll_apart(db):
    october = _month(OCTOBER, NOVEMBER)
    assert october == {
        "income": 1000 + 2000,                 # deposits + declared net salary: money received
        "expenses": 400 + 60 - 100,            # spending net of the refund (the 25 is September's)
        "gross_expenses": 460, "refunds": 100, "unmatched_refunds": 0,
        "debt_paid": 300,
        "other_inflows": 500 + 200 + 50,       # loan, collection, asset sale: money in, not income
        "loan_received": 500, "receivable_payments": 200, "asset_sale_proceeds": 50,
        "balance": 3000 - 360 - 300,           # gross payroll never enters the result
        "cash_flow": 2340 + 750,
        "unclassified_count": 2,               # the unclassified transfer and the undecided reimbursement
        "payroll_accrued": {"overtime_gross": 80, "vgh_gross": -15, "bonuses_gross": 250, "total_gross": 315},
        "pending_mail_count": 1,
        "complete": False,
        "incomplete_reasons": ["pending_mail_review", "unclassified_movements"],
    }


def test_record_timestamps_are_costa_rica_dates(db):
    september, november = _month(SEPTEMBER, OCTOBER), _month(NOVEMBER, DECEMBER)
    assert september["gross_expenses"] == 25, "22:00 on 30 Sep in Costa Rica is September"
    assert november["payroll_accrued"]["overtime_gross"] == 40, "01:00 on 1 Nov in Costa Rica is November"
    # November has gross payroll and no deposit: not a complete month.
    assert november["income"] == 0 and november["complete"] is False
    assert november["incomplete_reasons"] == ["payroll_without_deposit"]
    assert november["expenses"] == 0 and november["unmatched_refunds"] == 30


@pytest.mark.parametrize("role,expected", [
    ("owner", {"income": 3000, "expenses": 360, "debt_paid": 300, "balance": 2340}),
    # Regular users keep today's totals: gross spending, UTC dates, overtime counted as income.
    ("user", {"income": 3000, "expenses": 485, "debt_paid": 300, "balance": 2215}),
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
    payroll = [row for row in owner_rows if row["origin"] == "payroll"]
    assert payroll and all(row["counts_in"] == "payroll_accrued" for row in payroll)
    assert {row["transaction_type"] for row in owner_rows} <= {"income", "expense"}
    # Same rows, same order, same old fields; only the Owner gets the two new ones.
    strip = lambda rows: [{k: v for k, v in row.items() if k not in ("movement_kind", "counts_in")} for row in rows]
    assert strip(owner_rows) == user_rows
    assert all("movement_kind" not in row and "counts_in" not in row and "ledger_type" not in row for row in user_rows)


# The real Owner gate, not a simulated role: owner_account_context() reads the stored identity
# (accounts + workspaces + allowed_users + OWNER_EMAILS). A session that says "owner" is not enough.
OWNER_EMAIL = "owner@example.test"


def _identity(conn, stored_role):
    q(conn, "INSERT INTO accounts (id, role, status, primary_email) VALUES ('account-a', %s, 'active', %s)", (stored_role, OWNER_EMAIL))
    q(conn, "INSERT INTO workspaces (id, owner_account_id) VALUES (%s, 'account-a')", (WS_A,))
    q(conn, "INSERT INTO allowed_users (email, role, status) VALUES (%s, %s, 'active')", (OWNER_EMAIL, stored_role))


OWNER_OCTOBER = {"income": 3000, "expenses": 360, "debt_paid": 300, "balance": 2340}
LEGACY_OCTOBER = {"income": 3000, "expenses": 485, "debt_paid": 300, "balance": 2215}


@pytest.mark.parametrize("stored_role,allowlist,expected", [
    ("owner", OWNER_EMAIL, OWNER_OCTOBER),   # verified Owner: the single ledger
    ("user", OWNER_EMAIL, LEGACY_OCTOBER),   # the session claims "owner", the stored identity says user
    ("owner", "", LEGACY_OCTOBER),           # no Owner allowlisted in this deployment: fail safe
])
def test_only_the_verified_owner_identity_gets_the_ledger(db, monkeypatch, stored_role, allowlist, expected):
    from backend.auth.current_user import reset_current_user
    from backend.finance.category_catalog import owner_account_context
    from backend.user_product import free_service

    monkeypatch.setattr(free_service, "owner_account_context", owner_account_context)  # the real check
    monkeypatch.setenv("OWNER_EMAILS", allowlist)
    _identity(db, stored_role)
    token = _as("owner")
    try:
        summary = free_service.get_free_monthly_summary("2026-10")
        rows = free_service.list_free_movements()
    finally:
        reset_current_user(token)
    assert {key: summary[key] for key in expected} == expected
    assert all(("counts_in" in row) == (expected is OWNER_OCTOBER) for row in rows)


# Resumen (summary_breakdown): where the money came from adds up to the income each account's total
# counts, a year is a period of its own, and "lo que guardaste" is what was put aside, never income
# minus spending. Synthetic figures only.
@pytest.mark.parametrize("role,expected", [
    ("owner", {"Salario": 2000, "Sin categoría": 1000}),  # the Owner's ledger: no gross payroll
    ("user", {"Salario": 2000, "Sin categoría": 1000}),   # October's overtime is November in UTC for users
])
def test_income_categories_add_up_to_the_income_total(db, role, expected):
    from backend.auth.current_user import reset_current_user
    from backend.user_product import free_service

    token = _as(role)
    try:
        summary = free_service.get_free_monthly_summary("2026-10")
    finally:
        reset_current_user(token)
    assert {row["category"]: row["amount"] for row in summary["income_categories"]} == expected
    assert sum(row["amount"] for row in summary["income_categories"]) == summary["income"]
    assert summary["scope"] == "month" and summary["period"] == "2026-10"


def test_a_year_is_its_own_period_and_a_bad_period_is_refused(db):
    from fastapi import HTTPException
    from backend.auth.current_user import reset_current_user
    from backend.user_product import free_service

    token = _as("user")
    try:
        year = free_service.get_free_monthly_summary("2026")
        october = free_service.get_free_monthly_summary("2026-10")
        november = free_service.get_free_monthly_summary("2026-11")
        with pytest.raises(HTTPException) as refused:
            free_service.get_free_monthly_summary("26-1")
    finally:
        reset_current_user(token)
    assert refused.value.status_code == 422
    assert year["scope"] == "year" and year["period"] == "2026"
    assert year["income"] == october["income"] + november["income"]
    assert year["expenses"] == october["expenses"] + november["expenses"]


def test_saved_is_goals_and_salvavidas_contributions_never_income_minus_spending(db, monkeypatch):
    import json
    from datetime import date
    from backend.auth.current_user import reset_current_user
    from backend.user_product import free_service, summary_breakdown

    q(db, "CREATE TABLE finva_goal_contributions (id BIGSERIAL PRIMARY KEY, workspace_id UUID, goal_id BIGINT, amount NUMERIC(14,2), contribution_date DATE)")
    q(db, "CREATE TABLE user_preferences (workspace_id UUID, preference_key TEXT, preference_value JSONB)")
    for ws in (WS_A, WS_B):
        q(db, "INSERT INTO finva_goal_contributions (workspace_id, goal_id, amount, contribution_date) VALUES (%s, 1, 700, '2026-10-20')", (ws,))
    q(db, "INSERT INTO finva_goal_contributions (workspace_id, goal_id, amount, contribution_date) VALUES (%s, 1, 900, '2026-11-02')", (WS_A,))
    plan = {"auto_contribution": {"enabled": True, "amount": 2500, "frequency": "weekly", "start_date": "2026-10-01"}}
    q(db, "INSERT INTO user_preferences VALUES (%s, 'salvavidas', %s::jsonb)", (WS_A, json.dumps(plan)))
    monkeypatch.setattr(summary_breakdown, "costa_rica_today", lambda: date(2026, 10, 20))
    token = _as("user")
    try:
        october = free_service.get_free_monthly_summary("2026-10")
        november = free_service.get_free_monthly_summary("2026-11")
    finally:
        reset_current_user(token)
    # 1, 8 and 15 October; the 22nd is after today.
    assert october["saved"] == {"total": 8200.0, "goals": 700.0, "salvavidas": 7500.0}
    assert november["saved"] == {"total": 900.0, "goals": 900.0, "salvavidas": 0.0}, "nothing after today is counted"
