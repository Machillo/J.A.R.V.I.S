"""Owner recurring automation (20261022150000) on a real PostgreSQL.

Fixed recurring incomes recorded once on their Costa Rica due date, scheduled debt installments
recorded once with their principal/interest/fee split, both run by the daily job for the verified
Owner only. The schema is the identity baseline plus the ownership fixture, brought to the
production shape of the columns this code reads (checked read-only on 2026-10-22), then the
ownership, payroll and this migration. All identities, names, dates and amounts are synthetic.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backend.tests.test_financial_ownership_integrity_pg import (  # noqa: F401  (admin_uri is a fixture)
    IDENTITIES,
    MIGRATION as OWNERSHIP_MIGRATION,
    _create_database,
    _seed_identities,
    admin_uri,
)

psycopg2 = pytest.importorskip("psycopg2")

ROOT = Path(__file__).resolve().parents[2]
PAYROLL = ROOT / "database/migrations/20261002150000_payroll_receipts.sql"
MIGRATION = ROOT / "database/migrations/20261022150000_owner_recurring_automation.sql"
ROLLBACK = ROOT / "database/rollback/20261022150000_owner_recurring_automation_rollback.sql"

OWNER, VIP = IDENTITIES["A"], IDENTITIES["B"]
TODAY = date(2026, 10, 22)

# Production columns the code reads that the shared fixture does not carry.
PRODUCTION_SHAPE = """
ALTER TABLE transactions ALTER COLUMN user_id DROP NOT NULL, ALTER COLUMN user_id DROP DEFAULT;
ALTER TABLE debt_payments ALTER COLUMN user_id DROP NOT NULL, ALTER COLUMN user_id DROP DEFAULT;
ALTER TABLE debts ALTER COLUMN user_id DROP NOT NULL, ALTER COLUMN user_id DROP DEFAULT;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS financial_account_id BIGINT;
ALTER TABLE debt_payments
    ADD COLUMN IF NOT EXISTS previous_remaining_amount NUMERIC, ADD COLUMN IF NOT EXISTS new_remaining_amount NUMERIC,
    ADD COLUMN IF NOT EXISTS previous_monthly_payment NUMERIC, ADD COLUMN IF NOT EXISTS new_monthly_payment NUMERIC,
    ADD COLUMN IF NOT EXISTS description TEXT, ADD COLUMN IF NOT EXISTS principal_amount NUMERIC,
    ADD COLUMN IF NOT EXISTS interest_amount NUMERIC, ADD COLUMN IF NOT EXISTS payment_date DATE,
    ADD COLUMN IF NOT EXISTS installment_number INTEGER, ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual',
    ADD COLUMN IF NOT EXISTS fee_amount NUMERIC NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS extra_principal_amount NUMERIC NOT NULL DEFAULT 0;
ALTER TABLE finva_recurring_items
    ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT 'general',
    ADD COLUMN IF NOT EXISTS item_type TEXT NOT NULL DEFAULT 'expense',
    ADD COLUMN IF NOT EXISTS frequency TEXT NOT NULL DEFAULT 'monthly',
    ADD COLUMN IF NOT EXISTS due_day INTEGER, ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
CREATE TABLE IF NOT EXISTS account_balances (
    id BIGSERIAL PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    account_name TEXT NOT NULL,
    current_balance NUMERIC NOT NULL DEFAULT 0
);
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dincr_app') THEN CREATE ROLE dincr_app NOLOGIN; END IF;
END $$;
"""


def _seed(cur) -> None:
    _seed_identities(cur)
    cur.execute(PRODUCTION_SHAPE)
    cur.execute(OWNERSHIP_MIGRATION.read_text(encoding="utf-8"))
    cur.execute(PAYROLL.read_text(encoding="utf-8"))


def _context(ident: dict, role: str) -> dict:
    return {
        "id": ident["allowed"], "email": ident["email"], "role": role, "status": "active",
        "account_id": ident["account"], "account_role": role,
        "workspace_id": ident["workspace"], "workspace_role": "owner",
    }


@pytest.fixture
def pg(admin_uri, monkeypatch):
    from backend.core import database
    from backend.finance import recurring_automation

    uri, conn, drop = _create_database(admin_uri, _seed)
    try:
        with conn.cursor() as cur:
            cur.execute(MIGRATION.read_text(encoding="utf-8"))
        monkeypatch.setattr(database, "DATABASE_URL", uri)
        monkeypatch.setattr(database, "APPLICATION_NAME", "dincr-backend")
        # The server's "today" in Costa Rica, fixed for the tests.
        monkeypatch.setattr(recurring_automation, "costa_rica_today", lambda: TODAY)
        yield conn
    finally:
        drop()


def _as(ident: dict, role: str, fn, *args, **kwargs):
    from backend.auth.current_user import reset_current_user, set_current_user

    token = set_current_user(_context(ident, role))
    try:
        return fn(*args, **kwargs)
    finally:
        reset_current_user(token)


def _owner(fn, *args, **kwargs):
    return _as(OWNER, "owner", fn, *args, **kwargs)


def _vip(fn, *args, **kwargs):
    return _as(VIP, "user", fn, *args, **kwargs)


def _q(conn, sql: str, params=()) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall() if cur.description else []


def _request(**fields):
    from backend.user_product.models import RecurringItemRequest

    return RecurringItemRequest(**{"name": "Alquiler cobrado", "amount": 150000, "category": "alquiler",
                                   "item_type": "income", "frequency": "monthly", **fields})


def _income(next_due: date, **fields) -> int:
    from backend.user_product import basic_service

    row = _owner(basic_service.create_recurring_item,
                 _request(next_due_date=next_due, start_date=next_due, auto_record=True, **fields))
    return int(row["id"])


def _materialize(today: date, *, dry_run: bool = False):
    from backend.finance.recurring_automation import materialize_recurring_incomes

    return _owner(materialize_recurring_incomes, dry_run=dry_run, today=today)


def _incomes(conn) -> list[tuple]:
    return _q(conn, "SELECT transaction_date, amount, source, notes FROM transactions "
                    "WHERE transaction_type='income' ORDER BY transaction_date, id")


def _debt(conn, *, remaining=1000, payment=110, rate=12, fee=5, first=date(2026, 10, 15), day=15) -> int:
    rows = _q(conn, """INSERT INTO debts(user_id,name,debt_type,total_amount,remaining_amount,monthly_payment,interest_rate,
                           term_months,payment_day,start_date,first_payment_date,next_payment_date,fixed_fee_amount,workspace_id)
                       VALUES(%s,'Préstamo sintético','loan',%s,%s,%s,%s,12,%s,%s,%s,%s,%s,%s) RETURNING id""",
              (OWNER["users"], remaining, remaining, payment, rate, day, first, first, first, fee, OWNER["workspace"]))
    return int(rows[0][0])


def _apply_installments(today: date, *, dry_run: bool = False):
    from backend.finance.service import apply_due_installments

    return _owner(apply_due_installments, dry_run=dry_run, today=today)


# --- 1. Create and edit -------------------------------------------------------------------

def test_owner_creates_and_edits_a_recurring_income(pg):
    from backend.user_product import basic_service

    item_id = _income(date(2026, 10, 25), due_day=25)
    listed = _owner(basic_service.list_recurring_items)["items"]
    assert [(i["id"], i["auto_record"], i["next_due_date"], i["is_active"]) for i in listed] == [
        (item_id, True, "2026-10-25", True)]
    row = _owner(basic_service.update_recurring_item, item_id,
                 _request(amount=160000, due_day=25, next_due_date=date(2026, 11, 25), auto_record=True))
    assert (float(row["amount"]), row["next_due_date"], row["auto_record"]) == (160000, "2026-11-25", True)


def test_an_account_of_another_workspace_is_refused(pg):
    from fastapi import HTTPException

    other = _q(pg, "INSERT INTO account_balances(workspace_id,account_name) VALUES(%s,'Ajena') RETURNING id",
               (VIP["workspace"],))[0][0]
    mine = _q(pg, "INSERT INTO account_balances(workspace_id,account_name) VALUES(%s,'Propia') RETURNING id",
              (OWNER["workspace"],))[0][0]
    with pytest.raises(HTTPException) as refused:
        _income(date(2026, 10, 25), financial_account_id=other)
    assert refused.value.status_code == 404
    item_id = _income(date(2026, 10, 25), financial_account_id=mine)
    _materialize(date(2026, 10, 25))
    assert _q(pg, "SELECT financial_account_id FROM transactions WHERE notes=%s",
              (f"recurring_item:{item_id};due:2026-10-25",)) == [(mine,)]


@pytest.mark.parametrize("fields, status", [
    ({"next_due_date": None}, 422),                       # no date: nothing to schedule
    ({"next_due_date": date(2026, 10, 21)}, 422),         # yesterday: no backfill
    ({"category": "Salario"}, 422),                       # salary comes from payroll
    ({"item_type": "expense"}, 422),                      # expenses stay projections
])
def test_invalid_automatic_incomes_are_refused(pg, fields, status):
    from fastapi import HTTPException

    from backend.user_product import basic_service

    payload = {"next_due_date": date(2026, 10, 25), "auto_record": True, **fields}
    with pytest.raises(HTTPException) as refused:
        _owner(basic_service.create_recurring_item, _request(**payload))
    assert refused.value.status_code == status
    assert _q(pg, "SELECT count(*) FROM finva_recurring_items") == [(0,)]


# --- 2. Recorded on its date --------------------------------------------------------------

def test_the_income_is_recorded_on_its_due_date_and_not_before(pg):
    item_id = _income(date(2026, 10, 25), due_day=25)
    assert _materialize(date(2026, 10, 24))["occurrences"] == []
    assert _incomes(pg) == []
    dry = _materialize(date(2026, 10, 25), dry_run=True)
    assert [o["status"] for o in dry["occurrences"]] == ["would_record"]
    assert _incomes(pg) == []  # a dry run writes nothing
    _materialize(date(2026, 10, 25))
    assert _incomes(pg) == [(date(2026, 10, 25), Decimal("150000.00"), "recurring_income",
                             f"recurring_item:{item_id};due:2026-10-25")]
    assert _q(pg, "SELECT next_due_date FROM finva_recurring_items WHERE id=%s", (item_id,)) == [(date(2026, 11, 25),)]


# --- 3. Installment and balance -----------------------------------------------------------

def test_a_due_installment_is_recorded_once_with_its_split_and_moves_the_balance(pg):
    debt_id = _debt(pg)
    assert _apply_installments(date(2026, 10, 14))["installments"] == []
    result = _apply_installments(date(2026, 10, 15))
    [entry] = result["installments"]
    assert entry["installment_number"] == 1 and entry["due_date"] == "2026-10-15"
    assert round(entry["principal"] + entry["interest"] + entry["fee"], 2) == round(entry["amount"], 2)
    assert entry["fee"] == 5 and entry["interest"] > 0
    rows = _q(pg, "SELECT amount, principal_amount, interest_amount, fee_amount, source FROM debt_payments WHERE debt_id=%s",
              (debt_id,))
    assert len(rows) == 1 and rows[0][4] == "auto_schedule"
    assert _q(pg, "SELECT remaining_amount, installments_paid, next_payment_date FROM debts WHERE id=%s", (debt_id,)) == [
        (Decimal(str(entry["new_remaining_amount"])).quantize(Decimal("0.01")), 1, date(2026, 11, 15))]
    assert _q(pg, "SELECT count(*) FROM transactions WHERE source='auto_debt_schedule'") == [(1,)]


# --- 4. No duplicates ---------------------------------------------------------------------

def test_repeated_runs_record_nothing_twice(pg):
    _income(date(2026, 10, 25))
    debt_id = _debt(pg)
    for _ in range(3):
        _materialize(date(2026, 10, 26))
        _apply_installments(date(2026, 10, 26))
    assert len(_incomes(pg)) == 1
    assert _q(pg, "SELECT count(*) FROM debt_payments WHERE debt_id=%s", (debt_id,)) == [(1,)]
    assert _q(pg, "SELECT count(*) FROM transactions WHERE source='auto_debt_schedule'") == [(1,)]


def test_an_occurrence_already_claimed_is_never_recorded_again(pg):
    item_id = _income(date(2026, 10, 25))
    _materialize(date(2026, 10, 25))
    # A second run that read the item before the first one advanced it (the unique key decides).
    _q(pg, "UPDATE finva_recurring_items SET next_due_date='2026-10-25' WHERE id=%s", (item_id,))
    again = _materialize(date(2026, 10, 25))
    assert [o["status"] for o in again["occurrences"]] == ["skipped_already_processed"]
    assert len(_incomes(pg)) == 1


def test_the_database_refuses_a_second_transaction_for_one_installment(pg):
    _debt(pg)
    _apply_installments(date(2026, 10, 15))
    with pytest.raises(psycopg2.errors.UniqueViolation):
        _q(pg, """INSERT INTO transactions(user_id,transaction_date,description,amount,transaction_type,source,notes,workspace_id)
                  SELECT user_id,transaction_date,description,amount,transaction_type,source,notes,workspace_id
                  FROM transactions WHERE source='auto_debt_schedule'""")


# --- 5. Pause, reactivate, cancel ---------------------------------------------------------

def test_pause_reactivate_and_delete_never_backfill_nor_alter_history(pg, monkeypatch):
    from backend.finance import recurring_automation
    from backend.user_product import basic_service

    item_id = _income(date(2026, 10, 25), due_day=25)
    _materialize(date(2026, 10, 25))
    _owner(basic_service.update_recurring_item, item_id, _request(due_day=25, is_active=False))
    _materialize(date(2027, 1, 30))  # three due dates pass while paused
    assert len(_incomes(pg)) == 1
    # Reactivated on 2027-01-30 with the stored (past) date: it rolls forward, no backfill.
    monkeypatch.setattr(recurring_automation, "costa_rica_today", lambda: date(2027, 1, 30))
    row = _owner(basic_service.update_recurring_item, item_id, _request(amount=170000, due_day=25, is_active=True))
    assert row["next_due_date"] == "2027-02-25"
    _materialize(date(2027, 2, 25))
    assert [(d, a) for d, a, *_ in _incomes(pg)] == [(date(2026, 10, 25), Decimal("150000.00")),
                                                     (date(2027, 2, 25), Decimal("170000.00"))]
    _owner(basic_service.delete_recurring_item, item_id)
    assert len(_incomes(pg)) == 2  # the recorded incomes stay
    assert _q(pg, "SELECT item_id, item_name, due_date FROM recurring_item_occurrences ORDER BY due_date") == [
        (None, "Alquiler cobrado", date(2026, 10, 25)), (None, "Alquiler cobrado", date(2027, 2, 25))]


def test_a_paused_debt_records_no_installment(pg):
    debt_id = _debt(pg)
    _q(pg, "UPDATE debts SET auto_update_monthly=FALSE WHERE id=%s", (debt_id,))
    assert _apply_installments(date(2026, 12, 20))["installments"] == []
    assert _q(pg, "SELECT count(*) FROM debt_payments") == [(0,)]


# --- 6. Costa Rica dates ------------------------------------------------------------------

def test_costa_rica_today_is_the_calendar_day_in_costa_rica():
    from datetime import datetime, timezone

    from backend.core import time as dincr_time

    class Late(datetime):  # 2026-11-01 03:30 UTC is still 2026-10-31 21:30 in Costa Rica
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 1, 3, 30, tzinfo=timezone.utc).astimezone(tz)

    original = dincr_time.datetime
    dincr_time.datetime = Late
    try:
        assert dincr_time.costa_rica_today() == date(2026, 10, 31)
    finally:
        dincr_time.datetime = original


def test_the_daily_job_passes_costa_ricas_day_to_both_commands(pg, monkeypatch):
    from backend.finance import daily_history

    seen = []
    monkeypatch.setattr(daily_history, "materialize_recurring_incomes",
                        lambda ws, dry_run, today: seen.append(("incomes", ws, dry_run, today)) or {"occurrences": []})
    monkeypatch.setattr(daily_history, "apply_due_installments",
                        lambda ws, dry_run, today: seen.append(("debts", ws, dry_run, today)) or {"installments": []})
    daily_history._run_owner_automation({"role": "owner", "workspace_id": OWNER["workspace"]}, date(2026, 10, 31))
    assert seen == [("incomes", OWNER["workspace"], False, date(2026, 10, 31)),
                    ("debts", OWNER["workspace"], False, date(2026, 10, 31))]


@pytest.mark.parametrize("frequency, start, anchor, expected", [
    ("monthly", date(2026, 10, 31), 31, [date(2026, 11, 30), date(2026, 12, 31), date(2027, 1, 31), date(2027, 2, 28)]),
    ("biweekly", date(2026, 10, 30), None, [date(2026, 11, 13), date(2026, 11, 27), date(2026, 12, 11)]),
    ("weekly", date(2026, 10, 31), None, [date(2026, 11, 7), date(2026, 11, 14)]),
    ("quarterly", date(2026, 11, 30), 30, [date(2027, 2, 28), date(2027, 5, 30)]),
    ("annual", date(2028, 2, 29), 29, [date(2029, 2, 28), date(2030, 2, 28)]),
])
def test_series_keep_their_day_and_clamp_short_months(frequency, start, anchor, expected):
    from backend.finance.recurring_automation import next_occurrence

    due, series = start, []
    for _ in expected:
        due = next_occurrence(due, frequency, anchor)
        series.append(due)
    assert series == expected


def test_a_weekend_date_is_recorded_on_that_calendar_date(pg):
    # Current rule (as for debt installments): the scheduled calendar date, never moved.
    _income(date(2026, 10, 31), due_day=31)  # a Saturday
    _materialize(date(2026, 11, 2))
    assert [row[0] for row in _incomes(pg)] == [date(2026, 10, 31)]


# --- 7. Dashboard and cash flow -----------------------------------------------------------

def test_upcoming_shows_recorded_and_expected_separately(pg):
    from backend.finance.recurring_automation import upcoming_schedule

    _income(date(2026, 10, 25), due_day=25)
    _debt(pg, first=date(2026, 10, 15), day=15)
    _materialize(date(2026, 10, 25))
    _apply_installments(date(2026, 10, 25))
    view = _owner(upcoming_schedule, 45, today=date(2026, 10, 26))
    assert [(i["due_date"], i["status"]) for i in view["incomes"]] == [("2026-10-25", "recorded"), ("2026-11-25", "expected")]
    assert [(i["due_date"], i["status"]) for i in view["installments"]] == [("2026-10-15", "paid"), ("2026-11-15", "expected"),
                                                                           ("2026-12-15", "expected")][:len(view["installments"])]
    assert view["totals"]["incomes_expected"] == 150000
    # A read: nothing written.
    assert len(_incomes(pg)) == 1


def test_the_owner_strategy_counts_recurring_incomes_once(pg):
    from backend.ai.strategy_dashboard import _owner_recurring_income

    _income(date(2026, 10, 25), due_day=25)
    _materialize(date(2026, 10, 25))
    cycle = {"cycle": {"start": "2026-10-05", "end_exclusive": "2026-11-05"}}
    window = _owner(_owner_recurring_income, OWNER["workspace"], cycle)
    assert window["available"] is True
    assert (window["recorded_total"], window["expected_pending_total"], window["total"], window["monthly"]) == (
        150000, 0, 150000, 150000)
    unavailable = _owner(_owner_recurring_income, OWNER["workspace"], {})
    assert unavailable["available"] is False  # unknown is said, never counted


# --- 8. No double counting ----------------------------------------------------------------

def test_an_income_that_already_arrived_is_linked_not_repeated(pg):
    # The deposit was imported from mail two days early.
    deposit = _q(pg, """INSERT INTO transactions(user_id,transaction_date,description,amount,transaction_type,category,source,workspace_id)
                        VALUES(%s,'2026-10-23','Depósito',150000,'income','alquiler','owner_mail',%s) RETURNING id""",
                 (OWNER["users"], OWNER["workspace"]))[0][0]
    _income(date(2026, 10, 25))
    result = _materialize(date(2026, 10, 25))
    assert [(o["status"], o["transaction_id"]) for o in result["occurrences"]] == [("already_recorded", deposit)]
    assert len(_incomes(pg)) == 1


def test_salary_is_never_recorded_by_the_recurring_automation(pg):
    # A legacy row (saved before the rule) with a salary category: skipped by the run as well.
    _q(pg, """INSERT INTO finva_recurring_items(account_id,workspace_id,name,amount,category,item_type,frequency,next_due_date,auto_record)
              VALUES(%s,%s,'Salario',900000,'salario','income','monthly','2026-10-20',TRUE)""",
       (OWNER["account"], OWNER["workspace"]))
    assert _materialize(date(2026, 10, 22))["occurrences"] == []
    assert _incomes(pg) == []


def test_a_manual_owner_payment_and_the_schedule_charge_the_installment_once(pg, monkeypatch):
    from backend.user_product import service

    monkeypatch.setattr(service, "costa_rica_today", lambda: date(2026, 10, 15))
    debt_id = _debt(pg)
    paid = _owner(service.pay_user_debt, debt_id, 110)
    assert paid["installment_number"] == 1
    _apply_installments(date(2026, 10, 20))
    rows = _q(pg, "SELECT installment_number, source FROM debt_payments WHERE debt_id=%s ORDER BY id", (debt_id,))
    assert [row[0] for row in rows] == [1] and rows[0][1] != "auto_schedule"
    # The schedule then records the next installment once, on its date.
    _apply_installments(date(2026, 11, 15))
    assert [row[0] for row in _q(pg, "SELECT installment_number FROM debt_payments WHERE debt_id=%s ORDER BY id",
                                 (debt_id,))] == [1, 2]


def test_paying_the_already_applied_installment_charges_nothing_more(pg, monkeypatch):
    from backend.user_product import service

    debt_id = _debt(pg)
    _apply_installments(date(2026, 10, 15))
    balance = _q(pg, "SELECT remaining_amount FROM debts WHERE id=%s", (debt_id,))
    monkeypatch.setattr(service, "costa_rica_today", lambda: date(2026, 10, 16))
    _owner(service.pay_user_debt, debt_id, 110)
    assert _q(pg, "SELECT remaining_amount FROM debts WHERE id=%s", (debt_id,)) == balance
    assert _q(pg, "SELECT count(*) FROM debt_payments WHERE debt_id=%s", (debt_id,)) == [(1,)]


# --- 9. Not for Users ---------------------------------------------------------------------

def test_a_user_cannot_turn_on_or_run_the_automation(pg):
    from fastapi import HTTPException

    from backend.finance.recurring_automation import materialize_recurring_incomes, upcoming_schedule  # noqa: F401
    from backend.finance.service import apply_due_installments
    from backend.user_product import basic_service

    with pytest.raises(HTTPException) as refused:
        _vip(basic_service.create_recurring_item, _request(next_due_date=date(2026, 10, 25), auto_record=True))
    assert refused.value.status_code == 403
    for command in (materialize_recurring_incomes, apply_due_installments):
        with pytest.raises(HTTPException) as refused:
            _vip(command, VIP["workspace"], dry_run=False, today=date(2026, 10, 25))
        assert refused.value.status_code == 403
    # Their recurring items keep working as projections.
    row = _vip(basic_service.create_recurring_item, _request(next_due_date=date(2026, 10, 25)))
    assert row["auto_record"] is False
    _q(pg, "UPDATE finva_recurring_items SET next_due_date='2026-10-01' WHERE id=%s", (row["id"],))
    _materialize(date(2026, 10, 25))  # the Owner's run never reaches another workspace
    assert _incomes(pg) == []


def test_the_daily_job_runs_the_automation_for_the_owner_only(pg):
    from backend.finance.daily_history import _run_owner_automation

    _q(pg, """INSERT INTO finva_recurring_items(account_id,workspace_id,name,amount,category,item_type,frequency,next_due_date,auto_record)
              VALUES(%s,%s,'Sintético',1000,'otros','income','monthly','2026-10-20',TRUE)""",
       (VIP["account"], VIP["workspace"]))  # a row no User can create: still never recorded
    vip = _vip(_run_owner_automation, {"role": "user", "workspace_id": VIP["workspace"]}, date(2026, 10, 22))
    assert vip == {"recurring_incomes": 0, "debt_installments": 0, "automation_failed": 0}
    assert _incomes(pg) == []
    _income(date(2026, 10, 22))
    _debt(pg)
    owner = _owner(_run_owner_automation, {"role": "owner", "workspace_id": OWNER["workspace"]}, date(2026, 10, 22))
    assert owner == {"recurring_incomes": 1, "debt_installments": 1, "automation_failed": 0}


# --- 10. Compatibility --------------------------------------------------------------------

def test_an_older_app_keeps_the_stored_automation_untouched(pg):
    from backend.user_product import basic_service
    from backend.user_product.models import RecurringItemRequest

    item_id = _income(date(2026, 10, 25), due_day=25)
    # The older app sends only the fields it knows.
    legacy = RecurringItemRequest(name="Alquiler cobrado", amount=155000, category="alquiler", item_type="income",
                                  frequency="monthly", due_day=25)
    row = _owner(basic_service.update_recurring_item, item_id, legacy)
    assert (row["auto_record"], row["next_due_date"], float(row["amount"])) == (True, "2026-10-25", 155000)
    plain = _owner(basic_service.create_recurring_item, RecurringItemRequest(name="Internet", amount=25000))
    assert (plain["auto_record"], plain["next_due_date"], plain["item_type"]) == (False, None, "expense")


def test_rollback_keeps_transactions_and_the_migration_reapplies(pg):
    _income(date(2026, 10, 25))
    _materialize(date(2026, 10, 25))
    with pg.cursor() as cur:
        cur.execute(ROLLBACK.read_text(encoding="utf-8"))
        cur.execute(ROLLBACK.read_text(encoding="utf-8"))  # idempotent
    assert len(_incomes(pg)) == 1
    assert _q(pg, "SELECT count(*) FROM recurring_item_occurrences_rollback_snapshot") == [(1,)]
    assert _q(pg, "SELECT to_regclass('public.recurring_item_occurrences')") == [(None,)]
    with pg.cursor() as cur:
        cur.execute(MIGRATION.read_text(encoding="utf-8"))
        cur.execute(MIGRATION.read_text(encoding="utf-8"))  # idempotent
    assert _q(pg, "SELECT count(*) FROM finva_recurring_items WHERE auto_record") == [(0,)]
