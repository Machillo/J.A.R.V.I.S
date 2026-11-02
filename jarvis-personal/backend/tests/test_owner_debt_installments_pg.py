"""The Owner's scheduled debt installments, restored, on a real PostgreSQL.

#307 made debt reads read-only and moved the installment schedule to an explicit command,
`apply_due_installments`, which nothing called. The daily financial-history job is its caller
now, for the verified Owner only, on the Costa Rica date. These tests pin: one installment on its
date, once (repeated and concurrent runs), the existing split and balance rules, an Owner payment
from the app and the schedule never charging the same installment twice, and no access for any
other account. The schema is the identity baseline plus the ownership fixture with the production
nullability and debt_payments columns (checked read-only on 2026-10-22); no migration. All
identities, names, dates and amounts are synthetic.
"""
from __future__ import annotations

import threading
from datetime import date
from decimal import Decimal

import pytest

from backend.tests.test_financial_ownership_integrity_pg import (  # noqa: F401  (admin_uri is a fixture)
    IDENTITIES,
    MIGRATION as OWNERSHIP_MIGRATION,
    _create_database,
    _seed_identities,
    admin_uri,
)

psycopg2 = pytest.importorskip("psycopg2")

OWNER, VIP = IDENTITIES["A"], IDENTITIES["B"]

# Production shape of what the installment engine reads and writes.
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
"""


def _seed(cur) -> None:
    _seed_identities(cur)
    cur.execute(PRODUCTION_SHAPE)
    cur.execute(OWNERSHIP_MIGRATION.read_text(encoding="utf-8"))


@pytest.fixture
def pg(admin_uri, monkeypatch):
    from backend.core import database

    uri, conn, drop = _create_database(admin_uri, _seed)
    try:
        monkeypatch.setattr(database, "DATABASE_URL", uri)
        monkeypatch.setattr(database, "APPLICATION_NAME", "dincr-backend")
        yield conn
    finally:
        drop()


def _context(ident: dict, role: str) -> dict:
    return {
        "id": ident["allowed"], "email": ident["email"], "role": role, "status": "active",
        "account_id": ident["account"], "account_role": role,
        "workspace_id": ident["workspace"], "workspace_role": "owner",
    }


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


def _debt(conn, ident=OWNER, *, remaining=1000, payment=110, rate=12, fee=5, first=date(2026, 10, 15), day=15) -> int:
    rows = _q(conn, """INSERT INTO debts(user_id,name,debt_type,total_amount,remaining_amount,monthly_payment,interest_rate,
                           term_months,payment_day,start_date,first_payment_date,next_payment_date,fixed_fee_amount,workspace_id)
                       VALUES(%s,'Préstamo sintético','loan',%s,%s,%s,%s,12,%s,%s,%s,%s,%s,%s) RETURNING id""",
              (ident["users"], remaining, remaining, payment, rate, day, first, first, first, fee, ident["workspace"]))
    return int(rows[0][0])


def _apply(today: date, *, dry_run: bool = False):
    from backend.finance.service import apply_due_installments

    return _owner(apply_due_installments, dry_run=dry_run, today=today)


def _state(conn, debt_id: int):
    return _q(conn, "SELECT remaining_amount, installments_paid, next_payment_date FROM debts WHERE id=%s", (debt_id,))[0]


def _ledger(conn, debt_id: int):
    return _q(conn, "SELECT installment_number, payment_date, source FROM debt_payments WHERE debt_id=%s ORDER BY id", (debt_id,))


# --- Once, on its date ---------------------------------------------------------------------

def test_an_installment_is_applied_on_its_date_not_before(pg):
    debt_id = _debt(pg)
    assert _apply(date(2026, 10, 14))["installments"] == []
    assert _ledger(pg, debt_id) == [] and _state(pg, debt_id)[0] == Decimal("1000.00")
    dry = _apply(date(2026, 10, 15), dry_run=True)
    assert [e["installment_number"] for e in dry["installments"]] == [1]
    assert _ledger(pg, debt_id) == []  # a dry run writes nothing
    [entry] = _apply(date(2026, 10, 15))["installments"]
    # The existing rules: principal + interest + fee = the installment; the balance moves by principal.
    assert round(entry["principal"] + entry["interest"] + entry["fee"], 2) == round(entry["amount"], 2)
    assert entry["fee"] == 5 and entry["interest"] > 0
    assert _ledger(pg, debt_id) == [(1, date(2026, 10, 15), "auto_schedule")]
    assert _state(pg, debt_id) == (Decimal(str(entry["new_remaining_amount"])).quantize(Decimal("0.01")), 1, date(2026, 11, 15))
    assert _q(pg, "SELECT count(*) FROM transactions WHERE source='auto_debt_schedule'") == [(1,)]


def test_repeated_runs_apply_the_installment_once(pg):
    debt_id = _debt(pg)
    for _ in range(3):
        _apply(date(2026, 10, 20))
    assert [row[0] for row in _ledger(pg, debt_id)] == [1]
    assert _q(pg, "SELECT count(*) FROM transactions WHERE source='auto_debt_schedule'") == [(1,)]


def test_a_run_waits_for_a_concurrent_one_and_never_duplicates_its_installment(pg):
    from backend.core import database

    debt_id = _debt(pg)
    other = psycopg2.connect(database.DATABASE_URL)  # another run (or a payment) holding the debt
    try:
        with other.cursor() as cur:
            cur.execute("SELECT id FROM debts WHERE id=%s FOR UPDATE", (debt_id,))
            cur.execute("""INSERT INTO debt_payments(workspace_id,debt_id,payment_type,amount,payment_date,installment_number,source)
                           VALUES(%s,%s,'monthly_payment',110,'2026-10-15',1,'auto_schedule')""", (OWNER["workspace"], debt_id))
            cur.execute("UPDATE debts SET installments_paid=1, next_payment_date='2026-11-15' WHERE id=%s", (debt_id,))
        errors: list[Exception] = []
        run = threading.Thread(target=lambda: _safe(errors, _apply, date(2026, 10, 20)))
        run.start()
        run.join(timeout=1.5)
        assert run.is_alive(), "the run must wait for the debt held by the other one"
        other.commit()
        run.join(timeout=10)
        assert not run.is_alive() and errors == []
    finally:
        other.close()
    assert [row[0] for row in _ledger(pg, debt_id)] == [1]  # the other run's, never a second one
    assert _state(pg, debt_id)[1] == 1


def _safe(errors: list, fn, *args):
    try:
        fn(*args)
    except Exception as exc:  # reported by the test
        errors.append(exc)


def test_nothing_is_backfilled_before_the_stored_history(pg):
    # A debt whose stored counter already covers the past: only the next due installment is applied.
    debt_id = _debt(pg, first=date(2026, 6, 15))
    _q(pg, "UPDATE debts SET installments_paid=4, next_payment_date='2026-10-15' WHERE id=%s", (debt_id,))
    _apply(date(2026, 10, 15))
    assert [row[0] for row in _ledger(pg, debt_id)] == [5]


def test_a_paused_debt_gets_no_installment(pg):
    debt_id = _debt(pg)
    _q(pg, "UPDATE debts SET auto_update_monthly=FALSE WHERE id=%s", (debt_id,))
    assert _apply(date(2026, 12, 20))["installments"] == []
    assert _ledger(pg, debt_id) == []


# --- Costa Rica's date -------------------------------------------------------------------

def test_the_command_uses_costa_ricas_day_when_none_is_given(pg, monkeypatch):
    from backend.finance import service

    debt_id = _debt(pg, first=date(2026, 11, 1), day=1)
    # 2026-11-01 03:30 UTC is still 2026-10-31 in Costa Rica: the installment is not due yet.
    monkeypatch.setattr(service, "costa_rica_today", lambda: date(2026, 10, 31))
    assert _owner(service.apply_due_installments, dry_run=False)["installments"] == []
    monkeypatch.setattr(service, "costa_rica_today", lambda: date(2026, 11, 1))
    assert len(_owner(service.apply_due_installments, dry_run=False)["installments"]) == 1
    assert [row[0] for row in _ledger(pg, debt_id)] == [1]


def test_costa_rica_today_is_the_calendar_day_in_costa_rica():
    from datetime import datetime, timezone

    from backend.core import time as dincr_time

    class Late(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 1, 3, 30, tzinfo=timezone.utc).astimezone(tz)

    original = dincr_time.datetime
    dincr_time.datetime = Late
    try:
        assert dincr_time.costa_rica_today() == date(2026, 10, 31)
    finally:
        dincr_time.datetime = original


# --- Manual payments ---------------------------------------------------------------------

def test_an_owner_payment_then_the_schedule_charge_the_installment_once(pg, monkeypatch):
    from backend.user_product import service

    monkeypatch.setattr(service, "costa_rica_today", lambda: date(2026, 10, 15))
    debt_id = _debt(pg)
    paid = _owner(service.pay_user_debt, debt_id, 110)
    assert paid["installment_number"] == 1
    _apply(date(2026, 10, 20))
    assert [(n, s != "auto_schedule") for n, _, s in _ledger(pg, debt_id)] == [(1, True)]
    _apply(date(2026, 11, 15))  # the next one is still applied, once
    assert [row[0] for row in _ledger(pg, debt_id)] == [1, 2]


def test_paying_an_installment_the_schedule_applied_charges_nothing_more(pg, monkeypatch):
    from backend.user_product import service

    debt_id = _debt(pg)
    _apply(date(2026, 10, 15))
    balance = _state(pg, debt_id)[0]
    monkeypatch.setattr(service, "costa_rica_today", lambda: date(2026, 10, 16))
    _owner(service.pay_user_debt, debt_id, 110)
    assert _state(pg, debt_id)[0] == balance
    assert len(_ledger(pg, debt_id)) == 1


def test_a_users_payment_keeps_its_existing_behaviour(pg):
    from backend.user_product import service

    debt_id = _debt(pg, VIP)
    result = _vip(service.pay_user_debt, debt_id, 20)
    assert result["new_remaining_amount"] == 980
    assert _ledger(pg, debt_id) == []  # no installment schedule for Users
    assert _q(pg, "SELECT source FROM transactions WHERE workspace_id=%s", (VIP["workspace"],)) == [("finva_debt_payment",)]


def _plan(conn, debt_id: int):
    return _q(conn, "SELECT monthly_payment, term_months - installments_paid FROM debts WHERE id=%s", (debt_id,))[0]


def test_an_extra_payment_keeps_term_and_installment_unless_the_owner_says_what_the_bank_did(pg, monkeypatch):
    """The Owner's report: an extra payment lowered the balance but neither the term nor the
    installment. What the bank did is the Owner's to say; without it nothing is guessed."""
    from backend.user_product import service

    monkeypatch.setattr(service, "costa_rica_today", lambda: date(2026, 10, 15))
    kept, shorter, lower = _debt(pg), _debt(pg), _debt(pg)
    _owner(service.pay_user_debt, kept, 500)
    assert _plan(pg, kept) == (110, 11), "no answer: the term and the installment stay"
    _owner(service.pay_user_debt, shorter, 500, remaining_installments=5)
    assert _plan(pg, shorter) == (110, 5), "the bank shortened the term: 5 installments left"
    _owner(service.pay_user_debt, lower, 500, new_monthly_payment=60)
    assert _plan(pg, lower) == (60, 11), "the bank lowered the installment"
    assert _q(pg, "SELECT new_monthly_payment FROM debt_payments WHERE debt_id=%s", (lower,)) == [(60,)]


def test_an_extra_payment_after_the_scheduled_installment_also_takes_what_the_bank_did(pg, monkeypatch):
    from backend.user_product import service

    debt_id = _debt(pg)
    _apply(date(2026, 10, 15))
    monkeypatch.setattr(service, "costa_rica_today", lambda: date(2026, 10, 16))
    _owner(service.pay_user_debt, debt_id, 410, remaining_installments=4)   # 300 above the installment
    assert _plan(pg, debt_id)[1] == 4


def test_a_users_extra_payment_takes_what_the_bank_did_too(pg):
    from backend.user_product import service

    debt_id = _debt(pg, VIP)
    _vip(service.pay_user_debt, debt_id, 300, new_monthly_payment=80)
    assert _plan(pg, debt_id)[0] == 80


def _preferences(conn):
    _q(conn, """CREATE TABLE IF NOT EXISTS user_preferences (id BIGSERIAL PRIMARY KEY, workspace_id UUID NOT NULL,
                  preference_key TEXT NOT NULL, preference_value JSONB NOT NULL, created_at TIMESTAMPTZ DEFAULT NOW(),
                  updated_at TIMESTAMPTZ DEFAULT NOW(), UNIQUE (workspace_id, preference_key))""")


def test_the_bank_says_it_later_the_debt_waits_and_the_answer_is_applied(pg, monkeypatch):
    """The Owner's case: the new installment is known only days later. "El banco me avisa después"
    keeps the payment, marks the debt pending with the day to be reminded, and the answer applies it."""
    from backend.finance import debt_after_extra
    from backend.user_product import service

    _preferences(pg)
    today = date(2026, 11, 1)
    monkeypatch.setattr(service, "costa_rica_today", lambda: today)
    monkeypatch.setattr(debt_after_extra, "costa_rica_today", lambda: today)
    debt_id = _debt(pg)
    _owner(service.pay_user_debt, debt_id, 500, remind_on="2026-11-05")
    waiting = _owner(debt_after_extra.list_pending)["items"]
    assert waiting[str(debt_id)]["remind_on"] == "2026-11-05" and _plan(pg, debt_id) == (110, 11)
    assert _vip(debt_after_extra.list_pending)["items"] == {}, "another workspace never sees it"

    _owner(debt_after_extra.answer, debt_id, {"remind_on": "2026-11-06"})
    assert _owner(debt_after_extra.list_pending)["items"][str(debt_id)]["remind_on"] == "2026-11-06"
    _owner(debt_after_extra.answer, debt_id, {"new_monthly_payment": 70})
    assert _plan(pg, debt_id)[0] == 70 and _owner(debt_after_extra.list_pending)["items"] == {}


@pytest.mark.parametrize("payload", [{}, {"unchanged": True, "remaining_installments": 3}, {"remind_on": "2026-10-01"},
                                     {"remaining_installments": 0}, {"new_monthly_payment": 0}])
def test_an_unclear_answer_changes_nothing(pg, monkeypatch, payload):
    from fastapi import HTTPException

    from backend.finance import debt_after_extra

    _preferences(pg)
    monkeypatch.setattr(debt_after_extra, "costa_rica_today", lambda: date(2026, 11, 1))
    debt_id = _debt(pg)
    with pytest.raises(HTTPException) as error:
        _owner(debt_after_extra.answer, debt_id, payload)
    assert error.value.status_code == 422 and _plan(pg, debt_id) == (110, 12)


def test_another_workspaces_debt_is_not_found(pg):
    from fastapi import HTTPException

    from backend.finance import debt_after_extra

    _preferences(pg)
    debt_id = _debt(pg, VIP)
    with pytest.raises(HTTPException) as error:
        _owner(debt_after_extra.answer, debt_id, {"unchanged": True})
    assert error.value.status_code == 404


# --- Owner only ---------------------------------------------------------------------------

def test_a_user_cannot_apply_installments(pg):
    from fastapi import HTTPException

    from backend.finance.service import apply_due_installments

    debt_id = _debt(pg, VIP)
    for dry_run in (True, False):
        with pytest.raises(HTTPException) as refused:
            _vip(apply_due_installments, VIP["workspace"], dry_run=dry_run, today=date(2026, 10, 20))
        assert refused.value.status_code == 403
    assert _ledger(pg, debt_id) == []
    _apply(date(2026, 10, 20))  # the Owner's run never reaches another workspace
    assert _ledger(pg, debt_id) == [] and _state(pg, debt_id)[0] == Decimal("1000.00")


def test_the_daily_job_applies_installments_for_the_owner_only(pg):
    from backend.finance.daily_history import _apply_owner_installments

    vip_debt, owner_debt = _debt(pg, VIP), _debt(pg)
    vip = _vip(_apply_owner_installments, {"role": "user", "workspace_id": VIP["workspace"]}, date(2026, 10, 20))
    assert vip == {"debt_installments": 0, "installments_failed": 0, "error": None}
    assert _ledger(pg, vip_debt) == []
    owner = _owner(_apply_owner_installments, {"role": "owner", "workspace_id": OWNER["workspace"]}, date(2026, 10, 20))
    assert owner == {"debt_installments": 1, "installments_failed": 0, "error": None}
    again = _owner(_apply_owner_installments, {"role": "owner", "workspace_id": OWNER["workspace"]}, date(2026, 10, 20))
    assert again == {"debt_installments": 0, "installments_failed": 0, "error": None}
    assert [row[0] for row in _ledger(pg, owner_debt)] == [1]


def test_the_daily_job_run_applies_the_owners_due_installments(pg, monkeypatch):
    from backend.finance import daily_history

    # Only the installment step is under test: health and strategy have their own tests.
    monkeypatch.setattr(daily_history, "record_daily_health_snapshot", lambda today: {"health": "stable"})
    monkeypatch.setattr(daily_history, "compute_advisor_strategy", lambda: {})
    monkeypatch.setattr(daily_history, "_persist_strategy", lambda strategy: {"changed": False, "persisted": False})
    monkeypatch.setattr(daily_history, "eligible_workspaces", lambda conn: [_context(OWNER, "owner"), _context(VIP, "user")])
    owner_debt, vip_debt = _debt(pg), _debt(pg, VIP)
    first = daily_history.run_daily_financial_history(date(2026, 10, 20))
    second = daily_history.run_daily_financial_history(date(2026, 10, 20))
    assert (first["debt_installments"], first["installments_failed"], first["failed"]) == (1, 0, 0)
    assert (second["debt_installments"], second["installments_failed"]) == (0, 0)
    assert [row[0] for row in _ledger(pg, owner_debt)] == [1]
    assert _ledger(pg, vip_debt) == []


def test_a_failed_installment_step_is_reported_never_blocks_the_day_and_is_safe_to_retry(pg, monkeypatch):
    from backend.finance import daily_history, service

    recorded = []
    monkeypatch.setattr(daily_history, "record_daily_health_snapshot", lambda today: recorded.append(today) or {"health": "stable"})
    monkeypatch.setattr(daily_history, "compute_advisor_strategy", lambda: {})
    monkeypatch.setattr(daily_history, "_persist_strategy", lambda strategy: {"changed": True, "persisted": True})
    monkeypatch.setattr(daily_history, "eligible_workspaces", lambda conn: [_context(OWNER, "owner"), _context(VIP, "user")])
    debt_id = _debt(pg)
    breakdown = service._scheduled_payment_breakdown

    def broken(*args):
        raise RuntimeError("synthetic failure 1000.00 Préstamo sintético")  # must never reach the result

    monkeypatch.setattr(service, "_scheduled_payment_breakdown", broken)
    failed = daily_history.run_daily_financial_history(date(2026, 10, 20))
    assert (failed["debt_installments"], failed["installments_failed"], failed["installments_errors"]) == (0, 1, ["RuntimeError"])
    assert (failed["recorded"], failed["failed"], failed["strategy_changed"]) == (2, 0, 1)  # the rest of the day ran
    assert len(recorded) == 2
    assert "1000" not in str(failed) and "sintético" not in str(failed)
    assert _ledger(pg, debt_id) == [] and _state(pg, debt_id)[1] == 0  # nothing half-applied

    monkeypatch.setattr(service, "_scheduled_payment_breakdown", breakdown)
    retried = daily_history.run_daily_financial_history(date(2026, 10, 20))
    again = daily_history.run_daily_financial_history(date(2026, 10, 20))
    assert (retried["debt_installments"], retried["installments_failed"], retried["installments_errors"]) == (1, 0, [])
    assert (again["debt_installments"], again["installments_failed"]) == (0, 0)
    assert [row[0] for row in _ledger(pg, debt_id)] == [1]


def test_the_cron_route_marks_an_installment_failure_in_the_job_heartbeat(monkeypatch):
    from fastapi.testclient import TestClient

    from backend import main
    from backend.core import observability
    from backend.finance import daily_history_routes

    monkeypatch.setenv("NOTIFICATION_CRON_SECRET", "synthetic-secret")
    result = {"status": "OK", "date": "2026-10-20", "eligible": 1, "recorded": 1, "strategy_changed": 0, "failed": 0,
              "debt_installments": 0, "installments_failed": 1, "installments_errors": ["RuntimeError"]}
    beats = []
    monkeypatch.setattr(daily_history_routes, "run_daily_financial_history", lambda: result)
    monkeypatch.setattr(observability, "heartbeat", lambda job, ok, **kw: beats.append((job, ok, kw.get("error_class"))))
    response = TestClient(main.app).post("/financial-history/cron", headers={"X-Cron-Secret": "synthetic-secret"})
    assert response.status_code == 200 and response.json()["installments_failed"] == 1
    assert beats == [("financial_history", False, "installment_failures")]
    beats.clear()
    monkeypatch.setattr(daily_history_routes, "run_daily_financial_history", lambda: {**result, "installments_failed": 0, "installments_errors": []})
    TestClient(main.app).post("/financial-history/cron", headers={"X-Cron-Secret": "synthetic-secret"})
    assert beats == [("financial_history", True, None)]


def test_the_daily_job_passes_its_costa_rica_day(monkeypatch):
    from backend.finance import daily_history

    seen = []
    monkeypatch.setattr(daily_history, "apply_due_installments",
                        lambda ws, dry_run, today: seen.append((ws, dry_run, today)) or {"installments": []})
    daily_history._apply_owner_installments({"role": "owner", "workspace_id": OWNER["workspace"]}, date(2026, 10, 31))
    assert seen == [(OWNER["workspace"], False, date(2026, 10, 31))]
