"""Dollars with the Banco Central's rate on a real PostgreSQL, two synthetic workspaces: the estimate
reads the purchase day's rate and writes nothing; the scheduled close converts at the rate of the
close's last day, only what is due, each workspace apart, once."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backend.tests.test_pending_close_pg import A, B, CARDS, _account, _pending, _query, _today, db  # noqa: F401
from backend.tests.test_financial_ownership_integrity_pg import admin_uri  # noqa: F401

psycopg2 = pytest.importorskip("psycopg2")

ROOT = Path(__file__).resolve().parents[2]
RATE_MIGRATION = (ROOT / "database/migrations/20261104120000_market_exchange_rates.sql").read_text(encoding="utf-8")
RATE_ROLLBACK = (ROOT / "database/rollback/20261104120000_market_exchange_rates_rollback.sql").read_text(encoding="utf-8")


def _roles(conn):
    with conn.cursor() as cur:
        for role in ("anon", "authenticated", "dincr_app"):
            cur.execute(f"DO $$ BEGIN CREATE ROLE {role}; EXCEPTION WHEN duplicate_object THEN NULL; END $$")


def _rates(conn, **by_day):
    with conn.cursor() as cur:
        for day, rate in by_day.items():
            cur.execute("INSERT INTO market_exchange_rates(rate_date,currency,rate_type,rate,source) VALUES(%s,'USD','sell',%s,'test')",
                        (day.replace("d", "").replace("_", "-"), rate))


@pytest.fixture
def rated(db):  # noqa: F811
    _roles(db)
    with db.cursor() as cur:
        cur.execute(RATE_MIGRATION)
    return db


def _row(conn, expense_id):
    return _query(conn, "SELECT amount, exchange_rate FROM expenses WHERE id=%s", (expense_id,))[0]


def test_each_expense_is_estimated_at_its_purchase_days_rate(rated, monkeypatch):
    from backend.user_product import pending_conversion as pc

    _today(monkeypatch, date(2026, 11, 20))
    _rates(rated, d2026_11_02=500, d2026_11_10=520)
    first = _pending(rated, A, "Compra", 10, "2026-11-02")
    second = _pending(rated, A, "Otra", 20, "2026-11-12")
    before = _query(rated, "SELECT count(*) FROM expenses WHERE amount IS NULL")[0]
    read = pc.list_pending()
    items = {item["id"]: item for item in read["items"]}
    assert items[first]["estimated_amount"] == 5000
    assert items[second]["estimated_amount"] == 10400, "two days later: the closest earlier rate"
    assert read["totals"][0]["estimated_amount"] == 15400
    assert read["totals"][0]["amount"] == 30
    assert _query(rated, "SELECT count(*) FROM expenses WHERE amount IS NULL")[0] == before, "a read writes nothing"


def test_without_a_rate_the_estimate_is_unknown_not_zero(rated, monkeypatch):
    from backend.user_product import pending_conversion as pc

    _today(monkeypatch, date(2026, 11, 20))
    _rates(rated, d2026_11_10=520)
    known = _pending(rated, A, "Con tasa", 10, "2026-11-11")
    unknown = _pending(rated, A, "Sin tasa", 20, "2026-11-01")
    read = pc.list_pending()
    items = {item["id"]: item for item in read["items"]}
    assert items[known]["estimated_amount"] == 5200
    assert items[unknown]["estimated_amount"] is None
    assert "estimated_amount" not in read["totals"][0], "a partial sum would read as complete"


def test_the_listing_works_before_the_migration(db, monkeypatch):  # noqa: F811
    from backend.user_product import pending_conversion as pc

    _today(monkeypatch, date(2026, 11, 20))
    expense = _pending(db, A, "Compra", 10, "2026-11-02")
    item = pc.list_pending()["items"][0]
    assert item["id"] == expense and item["estimated_amount"] is None


def test_the_app_is_told_the_close_is_automatic_only_when_it_can_run(rated, monkeypatch):
    from backend.integrations import bccr_rates
    from backend.user_product import pending_conversion as pc

    _today(monkeypatch, date(2026, 11, 20))
    monkeypatch.delenv(bccr_rates.TOKEN_ENV, raising=False)
    assert pc.list_pending()["auto_close"] is False
    monkeypatch.setenv(bccr_rates.TOKEN_ENV, "synthetic")
    assert pc.list_pending()["auto_close"] is True
    with rated.cursor() as cur:
        cur.execute("UPDATE accounts SET base_currency='USD' WHERE id=%s", (A["account"],))
    assert pc.list_pending()["auto_close"] is False


def test_the_scheduled_close_uses_the_rate_of_the_cut_not_of_the_purchase(rated):
    from backend.user_product import pending_conversion as pc

    card = _account(rated, A, "Tarjeta", "credit_card", 21)
    expense = _pending(rated, A, "Compra", 10, "2026-10-05", card)
    _rates(rated, d2026_10_05=500, d2026_10_21=530)
    result = pc.close_due_periods(date(2026, 10, 22))
    assert result == {"closed_periods": 1, "converted": 1, "waiting_for_rate": 0, "failed_workspaces": 0}
    amount, rate = _row(rated, expense)
    assert Decimal(str(amount)) == Decimal("5300.00") and Decimal(str(rate)) == Decimal("530")


def test_a_close_that_has_not_arrived_keeps_waiting(rated):
    from backend.user_product import pending_conversion as pc

    card = _account(rated, A, "Tarjeta", "credit_card", 21)
    expense = _pending(rated, A, "Compra", 10, "2026-10-05", card)
    _rates(rated, d2026_10_20=530)
    assert pc.close_due_periods(date(2026, 10, 20))["converted"] == 0
    assert _row(rated, expense)[0] is None


def test_on_the_cut_day_without_its_rate_it_waits_and_the_next_run_closes_it(rated):
    from backend.user_product import pending_conversion as pc

    card = _account(rated, A, "Tarjeta", "credit_card", 21)
    expense = _pending(rated, A, "Compra", 10, "2026-10-05", card)
    _rates(rated, d2026_10_20=500)
    assert pc.close_due_periods(date(2026, 10, 21))["waiting_for_rate"] == 1
    assert _row(rated, expense)[0] is None
    _rates(rated, d2026_10_21=530)
    assert pc.close_due_periods(date(2026, 10, 21))["converted"] == 1
    assert Decimal(str(_row(rated, expense)[1])) == Decimal("530")


def test_no_rate_at_all_never_converts(rated):
    from backend.user_product import pending_conversion as pc

    expense = _pending(rated, A, "Compra", 10, "2026-10-05")
    assert pc.close_due_periods(date(2026, 11, 3))["waiting_for_rate"] == 1
    assert _row(rated, expense)[0] is None


def test_a_second_run_converts_nothing_and_keeps_a_corrected_amount(rated):
    from backend.user_product import pending_conversion as pc

    expense = _pending(rated, A, "Compra", 10, "2026-10-05")
    _rates(rated, d2026_10_31=530)
    assert pc.close_due_periods(date(2026, 11, 1))["converted"] == 1
    with rated.cursor() as cur:
        cur.execute("UPDATE expenses SET amount=5555, exchange_rate=555.5 WHERE id=%s", (expense,))
    assert pc.close_due_periods(date(2026, 11, 2))["converted"] == 0
    assert Decimal(str(_row(rated, expense)[0])) == Decimal("5555")


def test_each_workspace_closes_with_its_own_periods(rated):
    from backend.user_product import pending_conversion as pc

    card = _account(rated, A, "Tarjeta", "credit_card", 21)
    a_due = _pending(rated, A, "De A", 10, "2026-10-05", card)
    b_open = _pending(rated, B, "De B", 10, "2026-10-25")
    _rates(rated, d2026_10_21=530, d2026_10_22=540)
    assert pc.close_due_periods(date(2026, 10, 22))["converted"] == 1
    assert _row(rated, a_due)[0] is not None
    assert _row(rated, b_open)[0] is None, "another workspace's open month is untouched"


def test_a_workspace_that_fails_does_not_stop_the_others(rated, monkeypatch):
    from backend.user_product import pending_conversion as pc

    a_due, b_due = _pending(rated, A, "De A", 10, "2026-10-05"), _pending(rated, B, "De B", 10, "2026-10-05")
    _rates(rated, d2026_10_31=530)
    real = pc._close_due_in_workspace

    def fails_for_a(conn, workspace_id, base, today):
        if workspace_id == A["workspace"]:
            raise RuntimeError("synthetic failure")
        return real(conn, workspace_id, base, today)

    monkeypatch.setattr(pc, "_close_due_in_workspace", fails_for_a)
    result = pc.close_due_periods(date(2026, 11, 1))
    assert result["failed_workspaces"] == 1 and result["converted"] == 1
    assert _row(rated, a_due)[0] is None and _row(rated, b_due)[0] is not None


def test_a_dollar_account_is_left_alone(rated):
    from backend.user_product import pending_conversion as pc

    expense = _pending(rated, A, "Compra", 10, "2026-10-05")
    _rates(rated, d2026_10_31=530)
    with rated.cursor() as cur:
        cur.execute("UPDATE accounts SET base_currency='USD' WHERE id=%s", (A["account"],))
    assert pc.close_due_periods(date(2026, 11, 1))["converted"] == 0
    assert _row(rated, expense)[0] is None


def test_before_the_migration_the_scheduled_close_does_nothing(db):  # noqa: F811
    from backend.user_product import pending_conversion as pc

    expense = _pending(db, A, "Compra", 10, "2026-10-05")
    assert pc.close_due_periods(date(2026, 11, 1)) == {"closed_periods": 0, "converted": 0, "waiting_for_rate": 0, "failed_workspaces": 0}
    assert _row(db, expense)[0] is None


def test_the_migration_is_idempotent_and_rolls_back(rated):
    with rated.cursor() as cur:
        cur.execute(RATE_MIGRATION)
        cur.execute("SELECT relrowsecurity FROM pg_class WHERE oid=to_regclass('public.market_exchange_rates')")
        assert cur.fetchone()[0] is True
        cur.execute(RATE_ROLLBACK)
        cur.execute("SELECT to_regclass('public.market_exchange_rates')")
        assert cur.fetchone()[0] is None
        cur.execute(RATE_MIGRATION)
