"""CONFIRMAR of the Owner's exact-amount distribution on a real PostgreSQL.

The strategy reads the real debts, Salvavidas, goals and investments of the database; only the
income side (salary projection, pay cycle, account cash) is answered in memory, because an exact
amount does not use it. The confirmations table is the migration's own DDL. Checked here:

- computing a distribution writes nothing;
- CONFIRMAR records the confirmation and the real money each destination got (extra debt payments
  in the strategy's debt order, the Salvavidas deposit, the goal contribution, the investment
  reserve), and the screens that read those records show it;
- a repeated confirmation (retry, double tap, two at once) is applied once;
- a failure in the middle leaves nothing applied;
- a distribution that changed since it was reviewed, or that cannot be recorded, is refused
  with nothing written;
- only the Owner can confirm, and another workspace's rows never change.

Uses DINCR_TEST_POSTGRES_URL or the embedded `pgserver`; CI sets DINCR_REQUIRE_PG_TESTS=1 so they
fail instead of skipping. All data is synthetic.
"""
from __future__ import annotations

import os
import re
import threading
import uuid
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest
from fastapi import HTTPException

psycopg2 = pytest.importorskip("psycopg2")
from psycopg2.extras import RealDictCursor  # noqa: E402

from backend.ai import owner_distribution as od  # noqa: E402
from backend.ai import strategy_dashboard as sd  # noqa: E402
from backend.auth.current_user import reset_current_user, set_current_user  # noqa: E402

WS, OTHER = "00000000-0000-4000-8000-0000000000a1", "00000000-0000-4000-8000-0000000000b1"
MIGRATION = Path(__file__).resolve().parents[2] / "database" / "migrations" / "20261023120000_owner_distribution_confirmations.sql"

SCHEMA = """
CREATE TABLE workspaces (id UUID PRIMARY KEY);
CREATE TABLE debts (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT, workspace_id UUID NOT NULL, name TEXT NOT NULL, debt_type TEXT NOT NULL DEFAULT 'other',
    total_amount NUMERIC(14,2) NOT NULL, remaining_amount NUMERIC(14,2) NOT NULL, monthly_payment NUMERIC(14,2) NOT NULL,
    interest_rate NUMERIC(8,4), interest_rate_known BOOLEAN, term_months INTEGER, payment_day INTEGER, start_date DATE,
    first_payment_date DATE, next_payment_date DATE, last_payment_date DATE, auto_update_monthly BOOLEAN NOT NULL DEFAULT TRUE,
    installments_paid INTEGER NOT NULL DEFAULT 0, interest_method TEXT NOT NULL DEFAULT 'monthly',
    fixed_fee_amount NUMERIC(14,2) NOT NULL DEFAULT 0, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE debt_payments (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT, workspace_id UUID NOT NULL, debt_id BIGINT NOT NULL REFERENCES debts(id),
    payment_type TEXT NOT NULL, amount NUMERIC(14,2) NOT NULL, previous_remaining_amount NUMERIC(14,2) NOT NULL,
    new_remaining_amount NUMERIC(14,2) NOT NULL, previous_monthly_payment NUMERIC(14,2) NOT NULL,
    new_monthly_payment NUMERIC(14,2) NOT NULL, principal_amount NUMERIC(14,2), interest_amount NUMERIC(14,2),
    fee_amount NUMERIC(14,2) NOT NULL DEFAULT 0, extra_principal_amount NUMERIC(14,2) NOT NULL DEFAULT 0, description TEXT,
    payment_date DATE, installment_number INTEGER, source TEXT NOT NULL DEFAULT 'manual', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE transactions (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT, workspace_id UUID NOT NULL, transaction_date DATE NOT NULL,
    description TEXT NOT NULL, amount NUMERIC(14,2) NOT NULL, transaction_type TEXT NOT NULL, category TEXT, account TEXT,
    source TEXT, notes TEXT, financial_account_id BIGINT, created_at TIMESTAMP NOT NULL DEFAULT NOW());
CREATE TABLE financial_goals (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT, workspace_id UUID NOT NULL, name TEXT NOT NULL, target_amount NUMERIC(14,2) NOT NULL,
    current_amount NUMERIC(14,2) NOT NULL DEFAULT 0, target_date TEXT, priority TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active',
    goal_type TEXT NOT NULL DEFAULT 'general', alternative_group TEXT, is_selected BOOLEAN NOT NULL DEFAULT TRUE,
    funding_order INTEGER NOT NULL DEFAULT 100, depends_on_group TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE user_preferences (
    id BIGSERIAL PRIMARY KEY, workspace_id UUID NOT NULL, preference_key TEXT NOT NULL, preference_value JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE (workspace_id, preference_key));
CREATE TABLE account_balances (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT, workspace_id UUID NOT NULL REFERENCES workspaces(id), account_name TEXT NOT NULL,
    bank_name TEXT NOT NULL DEFAULT '', account_type TEXT NOT NULL DEFAULT 'checking', account_last4 TEXT NOT NULL DEFAULT '',
    currency TEXT NOT NULL DEFAULT 'CRC', current_balance NUMERIC(18,2) NOT NULL DEFAULT 0,
    annual_interest_rate NUMERIC(8,4) NOT NULL DEFAULT 0, last_reconciliation_difference NUMERIC(18,2) NOT NULL DEFAULT 0,
    balance_as_of TIMESTAMPTZ NOT NULL DEFAULT NOW(), source TEXT NOT NULL DEFAULT 'manual',
    include_in_net_worth BOOLEAN NOT NULL DEFAULT TRUE, is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, account_name, account_last4));
CREATE TABLE account_balance_history (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT, workspace_id UUID NOT NULL REFERENCES workspaces(id),
    financial_account_id BIGINT NOT NULL REFERENCES account_balances(id), balance NUMERIC(18,2) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'CRC', balance_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), source TEXT NOT NULL DEFAULT 'manual',
    note TEXT NOT NULL DEFAULT '', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE investment_cashflows (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT, workspace_id UUID, flow_date DATE NOT NULL DEFAULT CURRENT_DATE,
    flow_type TEXT NOT NULL, amount NUMERIC(14,2) NOT NULL, currency TEXT NOT NULL DEFAULT 'USD',
    source TEXT NOT NULL DEFAULT 'manual', description TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE investments (id BIGSERIAL PRIMARY KEY, workspace_id UUID, name TEXT, amount NUMERIC(14,2), created_at TIMESTAMPTZ DEFAULT NOW());
CREATE TABLE investment_portfolio_snapshots (id BIGSERIAL PRIMARY KEY, workspace_id UUID, included_in_net_worth BOOLEAN,
    snapshot_at TIMESTAMPTZ, snapshot_date DATE, market_value NUMERIC);
CREATE TABLE fixed_expenses (
    id BIGSERIAL PRIMARY KEY, workspace_id UUID NOT NULL, name TEXT NOT NULL, category TEXT, expected_amount NUMERIC(14,2),
    currency TEXT DEFAULT 'CRC', frequency TEXT DEFAULT 'monthly', interval_months INTEGER DEFAULT 1, due_day INTEGER,
    is_active BOOLEAN DEFAULT TRUE, payment_method TEXT, aliases JSONB);
"""

# Every table CONFIRMAR may write, and the one it must never write.
WRITTEN = ("debts", "debt_payments", "transactions", "financial_goals", "user_preferences", "account_balances",
           "account_balance_history", "investment_cashflows", "owner_distribution_confirmations")


def _confirmations_ddl() -> str:
    match = re.search(r"CREATE TABLE IF NOT EXISTS public\.owner_distribution_confirmations \(.*?\n\);",
                      MIGRATION.read_text(encoding="utf-8"), re.S)
    assert match, "the confirmations table moved"
    return match.group(0)


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


def _seed(cur, ws):
    cur.execute("INSERT INTO workspaces (id) VALUES (%s)", (ws,))
    # Strategy debt order (Owner rules): the 40% card first (high rate, small balance), then the loan.
    cur.execute("""INSERT INTO debts (workspace_id, name, total_amount, remaining_amount, monthly_payment, interest_rate)
                   VALUES (%s, 'Préstamo sintético', 3000000, 2000000, 100000, 24),
                          (%s, 'Tarjeta sintética', 500000, 60000, 40000, 40)""", (ws, ws))
    cur.execute("""INSERT INTO account_balances (workspace_id, account_name, bank_name, account_type, current_balance, source,
                                                 last_reconciliation_difference, balance_as_of)
                   VALUES (%s, 'Salvavidas', 'Banco sintético', 'emergency_fund', 50000, 'salvavidas', 0, '2026-10-01 12:00+00')""", (ws,))
    cur.execute("""INSERT INTO user_preferences (workspace_id, preference_key, preference_value)
                   VALUES (%s, 'salvavidas', '{"current_amount": 50000, "target_months": 6, "protected_expense_ids": []}')""", (ws,))
    cur.execute("""INSERT INTO fixed_expenses (workspace_id, name, category, expected_amount) VALUES (%s, 'Alquiler sintético', 'vivienda', 400000)""", (ws,))


@pytest.fixture
def db(admin_uri, monkeypatch):
    from backend.core import database

    name = f"owner_distribution_{uuid.uuid4().hex[:12]}"
    admin = psycopg2.connect(admin_uri)
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{name}"')
    parts = urlsplit(admin_uri)
    uri = urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment))
    conn = psycopg2.connect(uri, cursor_factory=RealDictCursor)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(SCHEMA)
    cur.execute(_confirmations_ddl())
    for ws in (WS, OTHER):
        _seed(cur, ws)
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    # The income side of the Owner engine is not used by an exact amount: answered in memory.
    monkeypatch.setattr(sd, "get_financial_summary", lambda: {})
    monkeypatch.setattr(sd, "calculate_monthly_salary_projection", lambda: {"results": {"base_net": 900_000, "projected_net": 900_000}})
    monkeypatch.setattr(sd, "_safe_cycle_report", lambda: {"income": {"expected_total": 900_000, "received_from_transactions": 0},
                                                           "expenses": {"spending_only": 0}, "debts": {"payments_current_period": 0},
                                                           "cycle": {"start": "2026-10-05", "end_exclusive": "2026-11-05"}})
    monkeypatch.setattr(sd, "_get_strategy_living_expenses", lambda *_a: {"fixed_living_total": 400_000})
    monkeypatch.setattr(sd, "_fetch_post_cut_expenses", lambda *_a: {"total": 0})
    monkeypatch.setattr(sd, "_pending_mandatory_fixed_expenses", lambda *_a: {"total": 0})
    monkeypatch.setattr(sd, "_fetch_distributable_cash", lambda *_a: 0)
    yield cur
    conn.close()
    with admin.cursor() as c:
        c.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
    admin.close()


def _as(role, fn, *args, ws=WS, **kwargs):
    token = set_current_user({"id": 7, "account_id": "acc-synthetic", "workspace_id": ws, "role": role})
    try:
        return fn(*args, **kwargs)
    finally:
        reset_current_user(token)


def _preview(amount, role="owner"):
    return _as(role, sd.get_owner_exact_distribution, amount, "CRC")


def _confirm(amount, key, items, role="owner"):
    return _as(role, od.confirm_owner_distribution, amount, "CRC", key, items)


def _snapshot(cur, ws=None):
    state = {}
    for table in WRITTEN:
        where = " WHERE workspace_id = %s" if ws else ""
        cur.execute(f"SELECT to_jsonb(t) - 'updated_at' AS row FROM {table} t{where} ORDER BY id", (ws,) if ws else ())
        state[table] = [row["row"] for row in cur.fetchall()]
    return state


def _cents(value) -> int:
    return round(float(value) * 100)


def _items(preview):
    return [{"key": item["key"], "amount": item["amount"]} for item in preview["strategy"]["allocation_items"]]


# Calculation ------------------------------------------------------------------------------------

@pytest.mark.parametrize("amount", ["254698", "1", "0.01", "1234.56", "999999.99"])
def test_computing_a_distribution_writes_nothing_and_adds_up_exactly(db, amount):
    before = _snapshot(db)
    preview = _preview(amount)
    strategy = preview["strategy"]
    assert strategy["distribution_source"] == "manual_amount"
    assert sum(_cents(item["amount"]) for item in strategy["allocation_items"]) == _cents(amount)
    assert preview["confirmation_plan"]["confirmable"] is True
    assert _snapshot(db) == before


def test_254698_uses_the_owners_strategy_and_its_debt_order(db):
    preview = _preview("254698")
    strategy, plan = preview["strategy"], preview["confirmation_plan"]
    # Debt + an unfinished mini fund: the Director's DEBT + SAFETY split of the real records.
    assert strategy["mode"] == "debt_safety"
    assert strategy["emergency_fund"]["current"] == 50_000
    keys = {item["key"]: item["amount"] for item in strategy["allocation_items"]}
    assert set(keys) == {"ataque_de_deuda", "fondo_de_emergencia", "vida_controlada"}
    debt_step = next(step for step in plan["steps"] if step["key"] == "ataque_de_deuda")
    # The card (first in the strategy's order) gets what it owes, the rest goes to the loan.
    assert [target["name"] for target in debt_step["targets"]] == ["Tarjeta sintética", "Préstamo sintético"]
    assert debt_step["targets"][0]["amount"] == 60_000
    assert sum(_cents(t["amount"]) for t in debt_step["targets"]) == _cents(keys["ataque_de_deuda"])


# Confirmation and persistence -------------------------------------------------------------------

def test_confirm_records_every_destination_once_and_the_screens_show_it(db):
    other_before = _snapshot(db, OTHER)
    preview = _preview("254698")
    items = _items(preview)
    amounts = {item["key"]: item["amount"] for item in items}
    debt_targets = next(s for s in preview["confirmation_plan"]["steps"] if s["key"] == "ataque_de_deuda")["targets"]

    result = _confirm("254698", "confirm-0001", items)
    assert result["status"] == "applied"

    db.execute("SELECT name, remaining_amount FROM debts WHERE workspace_id=%s", (WS,))
    remaining = {row["name"]: float(row["remaining_amount"]) for row in db.fetchall()}
    assert remaining["Tarjeta sintética"] == 0
    assert remaining["Préstamo sintético"] == 2_000_000 - debt_targets[1]["amount"]
    db.execute("SELECT debt_id, amount, source, payment_type FROM debt_payments WHERE workspace_id=%s", (WS,))
    payments = db.fetchall()
    assert len(payments) == 2 and {p["source"] for p in payments} == {"owner_distribution"}
    assert {p["payment_type"] for p in payments} == {"extra_payment"}
    db.execute("SELECT amount, transaction_type, source FROM transactions WHERE workspace_id=%s", (WS,))
    movements = db.fetchall()
    assert {m["transaction_type"] for m in movements} == {"debt_payment"}
    assert sum(_cents(m["amount"]) for m in movements) == _cents(amounts["ataque_de_deuda"])

    db.execute("SELECT current_balance, last_reconciliation_difference, balance_as_of FROM account_balances WHERE workspace_id=%s", (WS,))
    salvavidas = db.fetchone()
    assert _cents(salvavidas["current_balance"]) == _cents(50_000 + amounts["fondo_de_emergencia"])
    assert float(salvavidas["last_reconciliation_difference"]) == 0  # a deposit, not an unexplained difference
    assert salvavidas["balance_as_of"].date() == date(2026, 10, 1)  # not re-declared
    db.execute("SELECT preference_value FROM user_preferences WHERE workspace_id=%s", (WS,))
    assert _cents(db.fetchone()["preference_value"]["current_amount"]) == _cents(salvavidas["current_balance"])
    db.execute("SELECT source FROM account_balance_history WHERE workspace_id=%s", (WS,))
    assert [row["source"] for row in db.fetchall()] == ["owner_distribution"]

    db.execute("SELECT amount, items, applied FROM owner_distribution_confirmations WHERE workspace_id=%s", (WS,))
    confirmation = db.fetchone()
    assert _cents(confirmation["amount"]) == 25_469_800
    assert sum(_cents(item["amount"]) for item in confirmation["items"]) == 25_469_800
    assert [step["action"] for step in confirmation["applied"]].count("debt_extra_payment") == 2
    assert any(step["action"] == "not_recorded" and step["key"] == "vida_controlada" for step in confirmation["applied"])

    # The screens read the records: Salvavidas, debts and the strategy itself.
    state = _as("owner", sd.get_salvavidas_state)
    assert _cents(state["current_amount"]) == _cents(salvavidas["current_balance"])
    debts = {d["name"]: float(d["remaining_amount"]) for d in _as("owner", sd.get_debts)}
    assert debts == remaining
    after = _preview("254698")["strategy"]
    assert _cents(after["emergency_fund"]["current"]) == _cents(salvavidas["current_balance"])

    assert _snapshot(db, OTHER) == other_before


def test_a_repeated_confirmation_is_applied_once(db):
    items = _items(_preview("254698"))
    assert _confirm("254698", "confirm-0002", items)["status"] == "applied"
    applied = _snapshot(db)
    again = _confirm("254698", "confirm-0002", items)
    assert again["status"] == "already_applied"
    assert _snapshot(db) == applied
    with pytest.raises(HTTPException) as refused:
        _confirm("100000", "confirm-0002", items)
    assert refused.value.status_code == 409
    assert _snapshot(db) == applied


def test_two_confirmations_at_once_apply_once(db):
    items = _items(_preview("254698"))
    results, errors = [], []

    def run():
        try:
            results.append(_confirm("254698", "confirm-race1", items)["status"])
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert not errors, errors
    assert sorted(results) == ["already_applied", "applied"]
    db.execute("SELECT COUNT(*) AS n FROM debt_payments WHERE workspace_id=%s", (WS,))
    assert db.fetchone()["n"] == 2
    db.execute("SELECT COUNT(*) AS n FROM owner_distribution_confirmations WHERE workspace_id=%s", (WS,))
    assert db.fetchone()["n"] == 1


def test_a_second_confirmation_of_a_stale_review_is_refused(db):
    items = _items(_preview("254698"))
    _confirm("254698", "confirm-0003", items)
    applied = _snapshot(db)
    # The same review, confirmed again under a new key: the records changed, so does the split.
    with pytest.raises(HTTPException) as refused:
        _confirm("254698", "confirm-0004", items)
    assert refused.value.status_code == 409
    assert _snapshot(db) == applied


def test_a_failure_in_the_middle_leaves_nothing_applied(db, monkeypatch):
    before = _snapshot(db)
    items = _items(_preview("254698"))

    def broken(*_a, **_k):
        raise RuntimeError("synthetic failure after the debt payments")

    monkeypatch.setattr(od, "deposit_to_owner_salvavidas", broken)
    with pytest.raises(RuntimeError):
        _confirm("254698", "confirm-0005", items)
    assert _snapshot(db) == before
    monkeypatch.undo()


def test_items_the_owner_did_not_review_are_refused(db):
    before = _snapshot(db)
    items = _items(_preview("254698"))
    tampered = [{**items[0], "amount": items[0]["amount"] + 1}, *items[1:]]
    for wrong in (tampered, items[:-1], [*items, {"key": "inversion", "amount": 5}]):
        with pytest.raises(HTTPException) as refused:
            _confirm("254698", "confirm-0006", wrong)
        assert refused.value.status_code == 409
    assert _snapshot(db) == before


def test_a_debt_share_larger_than_the_debts_cannot_be_confirmed(db):
    db.execute("UPDATE debts SET remaining_amount = 1000 WHERE workspace_id = %s", (WS,))
    before = _snapshot(db)
    preview = _preview("5000000")
    assert preview["confirmation_plan"]["confirmable"] is False
    with pytest.raises(HTTPException) as refused:
        _confirm("5000000", "confirm-0007", _items(preview))
    assert refused.value.status_code == 409
    assert _snapshot(db) == before


def test_the_goal_the_strategy_funds_receives_its_share(db):
    # The strategy funds goals only with a month of Salvavidas and no debt at 10% or more.
    db.execute("UPDATE debts SET interest_rate = 8 WHERE workspace_id = %s", (WS,))
    db.execute("UPDATE account_balances SET current_balance = 5000000 WHERE workspace_id = %s", (WS,))
    soon = (date.today() + timedelta(days=45)).isoformat()
    db.execute("""INSERT INTO financial_goals (workspace_id, name, target_amount, current_amount, target_date, priority)
                  VALUES (%s, 'Meta sintética', 300000, 0, %s, 'critical')""", (WS, soon))
    preview = _preview("254698")
    goal_share = next((item["amount"] for item in preview["strategy"]["allocation_items"] if item["key"] == "meta_prioritaria"), 0)
    assert goal_share > 0, "a critical goal with a close date is funded first"
    assert preview["strategy"]["mode"] == "goal_protection"
    _confirm("254698", "confirm-0008", _items(preview))
    db.execute("SELECT current_amount, status FROM financial_goals WHERE workspace_id=%s", (WS,))
    goal = db.fetchone()
    assert _cents(goal["current_amount"]) == _cents(goal_share) and goal["status"] == "active"


def test_one_colon_is_confirmed_exactly(db):
    preview = _preview("1")
    _confirm("1", "confirm-0009", _items(preview))
    db.execute("SELECT amount, items FROM owner_distribution_confirmations WHERE workspace_id=%s", (WS,))
    row = db.fetchone()
    assert _cents(row["amount"]) == 100 and sum(_cents(i["amount"]) for i in row["items"]) == 100


# Security ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("role", ["user", "admin"])
def test_only_the_owner_can_confirm(db, role, monkeypatch):
    before = _snapshot(db)
    items = _items(_preview("254698"))
    # Refused before any database work: not even the lock or the recomputation runs.
    monkeypatch.setattr(od, "get_connection", lambda: pytest.fail("a refused caller opens no connection"))
    with pytest.raises(HTTPException) as refused:
        _confirm("254698", "confirm-0010", items, role=role)
    assert refused.value.status_code == 403
    assert _snapshot(db) == before


def test_another_workspaces_debt_is_never_paid(db):
    """Even a debt id of another workspace in the plan is refused: payments are workspace-scoped."""
    db.execute("SELECT id FROM debts WHERE workspace_id=%s ORDER BY id LIMIT 1", (OTHER,))
    foreign = db.fetchone()["id"]
    from backend.core.database import get_connection
    from backend.finance.debt_extra_payment import record_extra_payment

    with get_connection() as conn:
        assert record_extra_payment(conn, WS, foreign, 1000, payment_date="2026-10-23") is None
    db.execute("SELECT COUNT(*) AS n FROM debt_payments")
    assert db.fetchone()["n"] == 0


# Through the whole app: the real routes, the real request models, the real database ----------------

def test_the_owner_calculates_and_confirms_over_http(db, monkeypatch):
    from fastapi.testclient import TestClient

    from backend import main

    role = {"value": "owner"}
    monkeypatch.setattr(main, "authenticate_access_token",
                        lambda _token: {"id": 7, "email": "owner@example.test", "role": role["value"], "status": "active",
                                        "account_id": "acc-synthetic", "workspace_id": WS, "plan": "vip"})
    monkeypatch.setattr(main, "disabled_feature_for_request", lambda *_a, **_k: None)
    client = TestClient(main.app)
    headers = {"Authorization": "Bearer synthetic"}
    path = "/jarvis/premium/strategy-dashboard/exact-distribution"

    before = _snapshot(db)
    preview = client.post(path, json={"amount": "254698", "currency": "CRC"}, headers=headers)
    assert preview.status_code == 200, preview.text
    assert _snapshot(db) == before, "calculating writes nothing"
    items = _items(preview.json())
    body = {"amount": "254698", "currency": "CRC", "confirmation_key": "confirm-http-0001", "expected_items": items}

    role["value"] = "user"
    assert client.post(path + "/confirm", json=body, headers=headers).status_code == 403
    assert _snapshot(db) == before

    role["value"] = "owner"
    first = client.post(path + "/confirm", json=body, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "applied"
    applied = _snapshot(db)
    assert applied != before
    again = client.post(path + "/confirm", json=body, headers=headers)
    assert again.status_code == 200 and again.json()["status"] == "already_applied"
    assert _snapshot(db) == applied

    # The Salvavidas the apps read (Plan → Salvavidas) shows the deposit.
    salvavidas = client.get("/user-product/vip/salvavidas", headers=headers)
    assert salvavidas.status_code == 200, salvavidas.text
    emergency = next(i["amount"] for i in items if i["key"] == "fondo_de_emergencia")
    assert _cents(salvavidas.json()["current_amount"]) == _cents(50_000 + emergency)
