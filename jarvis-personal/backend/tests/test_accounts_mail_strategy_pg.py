"""Correos and Cuentas are two surfaces of ONE review system, on a real PostgreSQL.

Email Monitor lists the whole review inbox; Cuentas lists the same candidates for one
bank or one detected account (`bank` / `financial_account_id` filters of the same
endpoint). Reviewing from either surface changes the one candidate both read; a
candidate accepted twice creates one transaction. An accepted movement reaches the
ledger that Strategy and the charts read; a rejected one never does. Another
workspace sees none of it. Synthetic data only.

Uses the embedded server of test_financial_ownership_integrity_pg.py
(DINCR_TEST_POSTGRES_URL or pgserver; CI sets DINCR_REQUIRE_PG_TESTS=1).
"""
from __future__ import annotations

import json
import uuid
from datetime import date

import pytest

from backend.tests.test_financial_ownership_integrity_pg import BASELINE, _with_database
from backend.tests.test_mail_candidate_currency_pg import SCHEMA, A, B, admin_uri  # noqa: F401  (module fixture)

psycopg2 = pytest.importorskip("psycopg2")
from psycopg2.extras import RealDictCursor  # noqa: E402

from backend.ai import strategy_dashboard  # noqa: E402
from backend.auth.current_user import reset_current_user, set_current_user  # noqa: E402
from backend.core import database  # noqa: E402
from backend.user_product import gmail_service  # noqa: E402

# What the review list and the Users ledger read on top of the review schema.
EXTRA_SCHEMA = """
ALTER TABLE finva_email_messages ADD COLUMN sender TEXT, ADD COLUMN subject TEXT, ADD COLUMN received_at TIMESTAMPTZ,
    ADD COLUMN bank TEXT, ADD COLUMN parse_reason TEXT, ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE finva_email_candidates ADD COLUMN movement_direction TEXT, ADD COLUMN movement_kind TEXT,
    ADD COLUMN source_account_label TEXT, ADD COLUMN source_account_reference TEXT,
    ADD COLUMN destination_account_reference TEXT, ADD COLUMN counterparty TEXT, ADD COLUMN parser_name TEXT,
    ADD COLUMN parser_version TEXT, ADD COLUMN extraction_method TEXT, ADD COLUMN confidence NUMERIC,
    ADD COLUMN uncertainty_reason TEXT, ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN statement_document_id BIGINT, ADD COLUMN raw_payload JSONB;
CREATE TABLE salaries (id BIGSERIAL PRIMARY KEY, workspace_id UUID, amount NUMERIC(12,2), created_at TIMESTAMPTZ DEFAULT NOW());
CREATE TABLE payroll_events (id BIGSERIAL PRIMARY KEY, workspace_id UUID, amount NUMERIC(12,2), created_at TIMESTAMPTZ DEFAULT NOW());
CREATE TABLE expenses (id BIGSERIAL PRIMARY KEY, workspace_id UUID, amount NUMERIC(12,2), created_at TIMESTAMPTZ DEFAULT NOW());
CREATE TABLE financial_profiles (
    account_id UUID PRIMARY KEY, workspace_id UUID NOT NULL, income_type TEXT, fixed_monthly_salary NUMERIC(14,2),
    hourly_rate NUMERIC(14,2), work_days_per_week INTEGER, hours_per_day NUMERIC(6,2), pay_frequency TEXT,
    payday_note TEXT, essential_monthly_expenses NUMERIC(14,2), liquid_savings NUMERIC(14,2), emergency_fund_target NUMERIC(14,2)
);
CREATE TABLE finva_recurring_items (
    id BIGSERIAL PRIMARY KEY, account_id UUID, workspace_id UUID NOT NULL, name TEXT NOT NULL, amount NUMERIC(14,2) NOT NULL,
    category TEXT, item_type TEXT NOT NULL, frequency TEXT NOT NULL DEFAULT 'monthly', due_day INTEGER,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);
"""

TODAY = date.today()


@pytest.fixture
def pg(admin_uri, monkeypatch):  # noqa: F811
    name = f"accounts_mail_{uuid.uuid4().hex[:12]}"
    admin = psycopg2.connect(admin_uri)
    admin.autocommit = True
    with admin.cursor() as cur:
        for role in ("anon", "authenticated"):
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,))
            if not cur.fetchone():
                cur.execute(f'CREATE ROLE "{role}" NOLOGIN')
        cur.execute(f'CREATE DATABASE "{name}"')
    uri = _with_database(admin_uri, name)
    conn = psycopg2.connect(uri, cursor_factory=RealDictCursor)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(BASELINE.read_text(encoding="utf-8"))
        cur.execute(SCHEMA)
        cur.execute(EXTRA_SCHEMA)
        for ident in (A, B):
            cur.execute("INSERT INTO allowed_users(id,email,role,status) VALUES(%s,%s,'user','active')",
                        (ident["allowed"], f"{ident['allowed']}@example.test"))
            cur.execute("INSERT INTO users(id,email,name,country,timezone) VALUES(%s,%s,'Synthetic','Nowhere','UTC')",
                        (ident["users"], f"{ident['users']}@example.test"))
            cur.execute("INSERT INTO accounts(id,legacy_allowed_user_id,primary_email,base_currency) VALUES(%s,%s,%s,'CRC')",
                        (ident["account"], ident["allowed"], f"{ident['allowed']}@example.test"))
            cur.execute("INSERT INTO workspaces(id,workspace_key,owner_account_id,name) VALUES(%s,%s,%s,'Personal')",
                        (ident["workspace"], f"personal:{ident['account']}", ident["account"]))
            cur.execute("INSERT INTO finva_gmail_connections(account_id,workspace_id,legacy_user_id) VALUES(%s,%s,%s) RETURNING id",
                        (ident["account"], ident["workspace"], ident["users"]))
            ident["connection"] = cur.fetchone()["id"]
            cur.execute("""INSERT INTO financial_profiles(account_id,workspace_id,income_type,fixed_monthly_salary,
                               work_days_per_week,pay_frequency) VALUES(%s,%s,'fixed',900000,5,'monthly')""",
                        (ident["account"], ident["workspace"]))
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    try:
        yield conn
    finally:
        conn.close()
        with admin.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.close()


def _candidate(pg, ident, *, amount, bank, account_id, description, movement="card_purchase"):
    with pg.cursor() as cur:
        cur.execute(
            """INSERT INTO finva_email_messages(connection_id,account_id,workspace_id,provider_message_id,sender,subject,
                   received_at,bank) VALUES(%s,%s,%s,%s,'avisos@banco.example','Notificación de transacción',NOW(),%s) RETURNING id""",
            (ident["connection"], ident["account"], ident["workspace"], uuid.uuid4().hex, bank),
        )
        message_id = cur.fetchone()["id"]
        cur.execute(
            """INSERT INTO finva_email_candidates(email_message_id,account_id,workspace_id,transaction_date,description,
                   amount,currency,transaction_type,category,bank,financial_account_id,raw_payload)
               VALUES(%s,%s,%s,%s,%s,%s,'CRC','expense','Compras',%s,%s,%s) RETURNING id""",
            (message_id, ident["account"], ident["workspace"], TODAY, description, amount, bank, account_id,
             json.dumps({"bank_movement": movement, "financial_effect": "expense"})),
        )
        return cur.fetchone()["id"]


def _as(ident, fn, *args, **kwargs):
    token = set_current_user({"id": ident["allowed"], "account_id": ident["account"],
                              "workspace_id": ident["workspace"], "role": "user"})
    try:
        return fn(*args, **kwargs)
    finally:
        reset_current_user(token)


def _states(ident, **filters):
    return {item["candidate_id"]: item["review_status"]
            for item in _as(ident, gmail_service.list_gmail_emails, None, **filters)["items"]}


def _month(ident):
    """What the Users strategy reads for this month: the same ledger as Home and the charts."""
    inputs = _as(ident, strategy_dashboard._load_users_strategy_inputs, ident["workspace"], ident["account"], TODAY)
    return inputs["month"]["expenses"], inputs["income_policy"]["monthly_income"]


def _surplus(ident):
    """The Users strategy built on this month's real inputs (no debts or goals here)."""
    inputs = _as(ident, strategy_dashboard._load_users_strategy_inputs, ident["workspace"], ident["account"], TODAY)
    blueprint = strategy_dashboard._users_blueprint_from_inputs(
        all_debts=[], inputs=inputs, salvavidas={}, goals=[], investment_portfolio={}, today=TODAY)
    return blueprint["distribution_formula"]["surplus"]


def _transactions(pg):
    with pg.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n, COALESCE(SUM(amount),0) AS total FROM transactions")
        row = cur.fetchone()
    return row["n"], float(row["total"])


def test_correos_and_cuentas_review_the_same_candidates(pg):
    card = _candidate(pg, A, amount=25000, bank="bac", account_id=7, description="SUPERMERCADO EJEMPLO")
    other_card = _candidate(pg, A, amount=9000, bank="bac", account_id=8, description="FARMACIA EJEMPLO")
    elsewhere = _candidate(pg, A, amount=4000, bank="promerica", account_id=None, description="CAFE EJEMPLO")

    # Correos (whole inbox) and Cuentas (one bank / one account) read the same rows.
    assert set(_states(A)) == {card, other_card, elsewhere}
    assert set(_states(A, bank="BAC")) == {card, other_card}
    assert set(_states(A, financial_account_id=7)) == {card}
    row = _as(A, gmail_service.list_gmail_emails, None, financial_account_id=7)["items"][0]
    assert (row["financial_account_id"], row["bank_movement"], row["financial_effect"]) == (7, "card_purchase", "expense")
    assert _month(A) == (0, 900000) and _surplus(A) == 900000

    # Accept from Cuentas -> Correos shows it confirmed; the ledger (Strategy, charts) gets it.
    _as(A, gmail_service.review_gmail_candidate, card, "accept")
    assert _states(A)[card] == "confirmed" and _states(A, financial_account_id=7)[card] == "confirmed"
    assert _transactions(pg) == (1, 25000.0)
    assert _month(A) == (25000, 900000)  # spending moved; the declared income did not
    assert _surplus(A) == 875000  # the strategy's distribution reacts to the accepted movement

    # Reject from Correos -> Cuentas shows it rejected; nothing reaches the ledger.
    _as(A, gmail_service.review_gmail_candidate, other_card, "reject")
    assert _states(A, bank="bac")[other_card] == "rejected" and _states(A, financial_account_id=8)[other_card] == "rejected"
    assert _transactions(pg) == (1, 25000.0)
    assert _month(A) == (25000, 900000) and _surplus(A) == 875000  # a rejected movement changes nothing

    # Reviewing again from the other surface never creates a second movement.
    again = _as(A, gmail_service.review_gmail_candidate, card, "accept")
    assert again.get("already_reviewed") is True
    assert _transactions(pg) == (1, 25000.0)
    assert _states(A)[elsewhere] == "pending"


def test_another_workspace_sees_and_moves_nothing(pg):
    card = _candidate(pg, A, amount=25000, bank="bac", account_id=7, description="SUPERMERCADO EJEMPLO")
    assert _states(B) == {} and _states(B, bank="bac") == {} and _states(B, financial_account_id=7) == {}
    _as(A, gmail_service.review_gmail_candidate, card, "accept")
    assert _month(B) == (0, 900000)
    assert _states(B) == {}
