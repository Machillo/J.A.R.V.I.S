"""DEB-03: an unknown debt monthly payment is never a 0 payment (real PostgreSQL, Users paths).

Through the real service functions on a production-shaped `debts` table (after migration
20261010120000), synthetic rows:
- creating a debt without a payment stores it as unknown, and the debts list returns null;
- a given payment, 0 included, is known;
- editing: clearing a known payment makes it unknown; an unknown one sent back empty, or as an older
  client's 0, stays unknown; a typed payment becomes known;
- the Basic strategy reads an unknown payment as missing (it says so instead of counting it as 0);
- the Basic calendar shows the event without an amount and no month total from it;
- historical rows (written before the column, or by the Owner's finance paths) read as before.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.core import database
from backend.tests.test_financial_ownership_integrity_pg import (  # noqa: F401  (admin_uri is a fixture)
    IDENTITIES,
    _create_database,
    _seed_identities,
    admin_uri,
)
from backend.user_product import basic_service, service, strategy_engine

psycopg2 = pytest.importorskip("psycopg2")

A = IDENTITIES["A"]


def _seed(cur) -> None:
    _seed_identities(cur)
    cur.execute("CREATE TABLE IF NOT EXISTS financial_goals (id BIGSERIAL PRIMARY KEY, workspace_id UUID, name TEXT,"
                " target_amount NUMERIC(14,2), current_amount NUMERIC(14,2), target_date DATE, status TEXT, priority TEXT)")
    # The fixture's profile table is a minimal copy: add the columns the strategy reads (left empty).
    for column, kind in [("income_type", "TEXT"), ("fixed_monthly_salary", "NUMERIC"), ("hourly_rate", "NUMERIC"),
                         ("work_days_per_week", "NUMERIC"), ("hours_per_day", "NUMERIC"), ("essential_monthly_expenses", "NUMERIC"),
                         ("liquid_savings", "NUMERIC"), ("emergency_fund_target", "NUMERIC"), ("strategy_preference", "TEXT"),
                         ("discretionary_monthly_minimum", "NUMERIC"), ("pay_frequency", "TEXT"), ("payday_note", "TEXT")]:
        cur.execute(f"ALTER TABLE financial_profiles ADD COLUMN IF NOT EXISTS {column} {kind}")
    cur.execute("DROP TABLE IF EXISTS finva_recurring_items CASCADE")  # the calendar degrades without it (_basic_tables_ready)
    # A historical row: written before the column existed (NULL), a 0 the old writer stored.
    cur.execute("INSERT INTO debts(user_id,name,debt_type,total_amount,remaining_amount,monthly_payment,workspace_id,payment_day)"
                " VALUES(%s,'Histórica','loan',1000,800,0,%s,10)", (A["users"], A["workspace"]))


@pytest.fixture
def db(admin_uri, monkeypatch):
    uri, conn, drop = _create_database(admin_uri, _seed)
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    for module in (service, basic_service):
        monkeypatch.setattr(module, "get_current_workspace_id", lambda: A["workspace"])
        monkeypatch.setattr(module, "get_current_account_id", lambda: A["account"], raising=False)
    monkeypatch.setattr(service, "_legacy_financial_user_id", lambda: A["users"])
    monkeypatch.setattr(service, "mark_applied", lambda _conn: None)
    monkeypatch.setattr(basic_service, "_profile", lambda *_args: {})
    try:
        yield conn
    finally:
        drop()


def _payload(**kw):
    base = dict(name="Tarjeta sintética", debt_type="credit_card", total_amount=None, remaining_amount=100000,
                monthly_payment=None, interest_rate=None, payment_day=15, term_months=None, next_payment_date=None,
                interest_rate_confirmed=None)
    return SimpleNamespace(**{**base, **kw})


def _stored(conn, debt_id):
    with conn.cursor() as cur:
        cur.execute("SELECT monthly_payment, monthly_payment_known FROM debts WHERE id=%s", (debt_id,))
        return cur.fetchone()


def _listed(debt_id):
    return next(row for row in service.list_user_debts() if row["id"] == debt_id)


def test_a_debt_without_a_payment_is_stored_and_listed_as_unknown(db):
    created = service.create_user_debt(_payload())
    assert created["monthly_payment"] is None and created["monthly_payment_known"] is False
    assert _stored(db, created["id"]) == (0, False), "the NOT NULL column holds a placeholder, never a payment"
    listed = _listed(created["id"])
    assert listed["monthly_payment"] is None and listed["monthly_payment_known"] is False


@pytest.mark.parametrize("given", [0, 25000])
def test_a_given_payment_zero_included_is_known(db, given):
    created = service.create_user_debt(_payload(monthly_payment=given))
    assert _stored(db, created["id"]) == (given, True)
    assert _listed(created["id"])["monthly_payment"] == float(given)


def test_editing_never_turns_an_unknown_payment_into_zero(db):
    debt = service.create_user_debt(_payload())["id"]
    service.update_user_debt(debt, _payload(name="Otro nombre"))  # sent back empty
    assert _stored(db, debt) == (0, False)
    service.update_user_debt(debt, _payload(monthly_payment=0))  # an older client's 0 for an empty field
    assert _stored(db, debt) == (0, False)
    service.update_user_debt(debt, _payload(monthly_payment=30000))  # typed
    assert _stored(db, debt) == (30000, True)
    service.update_user_debt(debt, _payload(monthly_payment=None))  # cleared
    assert _stored(db, debt) == (0, False)


def test_a_historical_row_reads_as_before(db):
    historical = next(row for row in service.list_user_debts() if row["name"] == "Histórica")
    assert historical["monthly_payment"] == 0.0 and historical["monthly_payment_known"] is True


def test_the_basic_strategy_says_a_payment_is_missing_instead_of_counting_it_as_zero(db):
    service.create_user_debt(_payload(name="Sin cuota"))
    snapshot = service._strategy_snapshot()
    debts = {row["name"]: row for row in snapshot["debts"]}
    assert debts["Sin cuota"]["monthly_payment"] is None, "unknown reaches the engine as unknown"
    assert debts["Histórica"]["monthly_payment"] == 0.0  # read as before
    # A synthetic income, so the engine reaches its debt checks (an account with no income stops before them).
    strategy = strategy_engine.build_basic_strategy({**snapshot, "monthly_income_estimate": 800000})
    # The engine's existing contract for a missing payment (no new formula): it says so.
    assert any("Falta la cuota mensual de 1 deuda" in warning for warning in strategy["warnings"]), strategy["warnings"]


def test_the_basic_calendar_shows_an_unknown_payment_without_an_amount(db):
    service.create_user_debt(_payload(name="Sin cuota", payment_day=15))
    calendar = basic_service.get_financial_calendar()
    event = next(e for e in calendar["events"] if e["name"] == "Sin cuota")
    assert event["amount"] is None, "never a ₡0 payment"
    assert calendar["summary"]["payments"] is None, "no month total from an unknown payment"
    historical = next(e for e in calendar["events"] if e["name"] == "Histórica")
    assert historical["amount"] == 0.0  # read as before
