"""Fixed recurring incomes recorded on their due date, for the verified Owner only.

The Owner configures a recurring income in Recurrentes (finva_recurring_items) with a next due
date and `auto_record`. On each due date (America/Costa_Rica) this records it once as an
`income` transaction:

- **Once.** recurring_item_occurrences has UNIQUE (workspace_id, item_id, due_date): the
  occurrence row is inserted first, inside the same transaction as the income, so a second or
  concurrent run records nothing (ON CONFLICT DO NOTHING).
- **Never twice with what already arrived.** When the workspace already has an income of the
  same amount within ±3 days of the due date that no other occurrence claimed (e.g. the deposit
  imported from mail), that transaction is linked as `already_recorded` and nothing is added.
- **Never salary.** Salary keeps its own treatment (employment profile, payroll events and the
  deposit; finance/payroll_receipts.py): `auto_record` is refused for salary categories.
- **Pausing never backfills.** Only an active item is recorded; reactivating an item whose next
  date passed moves the date forward to today or later (recurring_items.py), so the paused
  period is never recorded afterwards. Editing an item never touches recorded history.

It is a command run by the daily job (finance/daily_history.py) inside the Owner's identity,
never from a read. DINCR Users' recurring items stay projections: the same Owner boundary as
the debt installments (finance/debt_automation.py).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from fastapi import HTTPException

from backend.auth.current_user import get_current_workspace_id
from backend.core.database import get_connection
from backend.core.time import costa_rica_today
from backend.finance.debt_automation import schedule_automation_enabled
from backend.finance.payroll_receipts import SALARY_CATEGORIES

SOURCE = "recurring_income"
MATCH_DAYS = 3
MAX_OCCURRENCES_PER_RUN = 60  # a guard against a misconfigured date, never reached by a daily run
_MONTHS = {"monthly": 1, "quarterly": 3, "annual": 12}


def is_salary_category(category: Any) -> bool:
    return str(category or "").strip().lower() in SALARY_CATEGORIES


def next_occurrence(due: date, frequency: str, anchor_day: int | None = None) -> date:
    """The date after `due` for this frequency. Months keep the anchor day, clamped to the
    month's last day (31 → 30 Apr → 28/29 Feb → 31 Mar)."""
    if frequency == "weekly":
        return due + timedelta(days=7)
    if frequency == "biweekly":
        return due + timedelta(days=14)
    months = _MONTHS.get(frequency)
    if not months:
        raise ValueError(f"unsupported frequency: {frequency}")
    from backend.finance.service import _add_months

    return _add_months(due, months, anchor_day or due.day)


def first_on_or_after(due: date, today: date, frequency: str, anchor_day: int | None = None) -> date:
    """Move a past due date forward along its series to the first date on or after `today`."""
    steps = 0
    while due < today and steps < 10_000:
        due = next_occurrence(due, frequency, anchor_day)
        steps += 1
    return due


def _as_date(value: Any) -> date | None:
    """The database layer returns dates as ISO text; compare them as dates."""
    return date.fromisoformat(str(value)[:10]) if value else None


def _anchor(item: dict[str, Any]) -> int | None:
    return int(item["due_day"]) if item.get("due_day") else None


def materialize_recurring_incomes(workspace_id: str | None = None, *, today: date | None = None,
                                  dry_run: bool = True) -> dict[str, Any]:
    """Record each recurring income already due, once. ``dry_run`` (the default) writes nothing."""
    if not schedule_automation_enabled():
        raise HTTPException(status_code=403, detail="Solo el Owner registra ingresos recurrentes automáticamente.")
    workspace_id = workspace_id or get_current_workspace_id()
    today = today or costa_rica_today()
    plan: list[dict[str, Any]] = []
    with get_connection() as conn:
        items = conn.execute(
            """SELECT id,account_id,name,amount,category,frequency,due_day,next_due_date,financial_account_id
               FROM finva_recurring_items
               WHERE workspace_id=%s AND is_active=TRUE AND auto_record=TRUE AND item_type='income'
                 AND next_due_date IS NOT NULL AND next_due_date <= %s
               ORDER BY id FOR UPDATE""",
            (workspace_id, today),
        ).fetchall() or []
        for item in items:
            item = dict(item)
            if is_salary_category(item.get("category")):
                continue  # refused on save; a legacy row never records salary
            due = _as_date(item["next_due_date"])
            amount = Decimal(str(item["amount"])).quantize(Decimal("0.01"))
            count = 0
            while due <= today and count < MAX_OCCURRENCES_PER_RUN:
                count += 1
                entry = {"item_id": item["id"], "name": item["name"], "due_date": due.isoformat(), "amount": float(amount)}
                if dry_run:
                    entry["status"] = "would_record"
                    plan.append(entry)
                else:
                    plan.append({**entry, **_record_once(conn, workspace_id, item, due, amount)})
                due = next_occurrence(due, item["frequency"], _anchor(item))
            if not dry_run:
                conn.execute("UPDATE finva_recurring_items SET next_due_date=%s,updated_at=NOW() WHERE id=%s AND workspace_id=%s",
                             (due, item["id"], workspace_id))
        if not dry_run:
            conn.commit()
    return {"dry_run": dry_run, "date": today.isoformat(), "occurrences": plan}


def _record_once(conn, workspace_id: str, item: dict[str, Any], due: date, amount: Decimal) -> dict[str, Any]:
    claimed = conn.execute(
        """INSERT INTO recurring_item_occurrences(workspace_id,item_id,item_name,due_date,amount,status)
           VALUES(%s,%s,%s,%s,%s,'recorded') ON CONFLICT (workspace_id,item_id,due_date) DO NOTHING RETURNING id""",
        (workspace_id, item["id"], item["name"], due, amount),
    ).fetchone()
    if not claimed:
        return {"status": "skipped_already_processed"}
    existing = conn.execute(
        """SELECT t.id FROM transactions t
           WHERE t.workspace_id=%s AND t.transaction_type='income' AND ABS(t.amount - %s) < 0.01
             AND t.transaction_date::date BETWEEN %s AND %s
             AND NOT EXISTS (SELECT 1 FROM recurring_item_occurrences o
                             WHERE o.workspace_id=t.workspace_id AND o.transaction_id=t.id)
           ORDER BY ABS(t.transaction_date::date - %s::date), t.id LIMIT 1""",
        (workspace_id, amount, due - timedelta(days=MATCH_DAYS), due + timedelta(days=MATCH_DAYS), due),
    ).fetchone()
    if existing:
        conn.execute("UPDATE recurring_item_occurrences SET status='already_recorded',transaction_id=%s WHERE id=%s",
                     (existing["id"], claimed["id"]))
        return {"status": "already_recorded", "transaction_id": int(existing["id"])}
    transaction = conn.execute(
        """INSERT INTO transactions(workspace_id,transaction_date,description,amount,transaction_type,category,account,
                                    source,notes,financial_account_id,created_at)
           VALUES(%s,%s,%s,%s,'income',%s,NULL,%s,%s,%s,NOW()) RETURNING id""",
        (workspace_id, due, item["name"], amount, item.get("category") or "general", SOURCE,
         f"recurring_item:{item['id']};due:{due.isoformat()}", item.get("financial_account_id")),
    ).fetchone()
    conn.execute("UPDATE recurring_item_occurrences SET transaction_id=%s WHERE id=%s", (transaction["id"], claimed["id"]))
    return {"status": "recorded", "transaction_id": int(transaction["id"])}


def recurring_incomes_in_window(conn, workspace_id: str, start: date, end_exclusive: date) -> dict[str, Any]:
    """Read-only: the Owner's automatic recurring incomes due in [start, end): recorded (already in
    transactions, so already counted as received) and still expected."""
    recorded = conn.execute(
        """SELECT item_id,item_name,due_date,amount,status FROM recurring_item_occurrences
           WHERE workspace_id=%s AND due_date >= %s AND due_date < %s ORDER BY due_date,id""",
        (workspace_id, start, end_exclusive),
    ).fetchall() or []
    items = conn.execute(
        """SELECT id,name,amount,frequency,due_day,next_due_date FROM finva_recurring_items
           WHERE workspace_id=%s AND is_active=TRUE AND auto_record=TRUE AND item_type='income'
             AND next_due_date IS NOT NULL AND next_due_date < %s""",
        (workspace_id, end_exclusive),
    ).fetchall() or []
    done = {(row["item_id"], _as_date(row["due_date"])) for row in recorded}
    expected: list[dict[str, Any]] = []
    for item in items:
        due = _as_date(item["next_due_date"])
        steps = 0
        while due < end_exclusive and steps < MAX_OCCURRENCES_PER_RUN:
            if due >= start and (item["id"], due) not in done:
                expected.append({"item_id": item["id"], "name": item["name"], "due_date": due.isoformat(),
                                 "amount": float(item["amount"]), "status": "expected"})
            due = next_occurrence(due, item["frequency"], _anchor(item))
            steps += 1
    recorded_items = [{"item_id": row["item_id"], "name": row["item_name"], "due_date": _as_date(row["due_date"]).isoformat(),
                       "amount": float(row["amount"]), "status": row["status"]} for row in recorded]
    recorded_total = round(sum(item["amount"] for item in recorded_items), 2)
    expected_total = round(sum(item["amount"] for item in expected), 2)
    return {"recorded_total": recorded_total, "expected_pending_total": expected_total,
            "total": round(recorded_total + expected_total, 2), "items": recorded_items + expected}


def monthly_recurring_income(conn, workspace_id: str) -> float:
    """Read-only: the monthly equivalent of the Owner's active automatic recurring incomes."""
    factors = {"weekly": 52 / 12, "biweekly": 26 / 12, "monthly": 1, "quarterly": 1 / 3, "annual": 1 / 12}
    rows = conn.execute(
        """SELECT amount,frequency FROM finva_recurring_items
           WHERE workspace_id=%s AND is_active=TRUE AND auto_record=TRUE AND item_type='income'""",
        (workspace_id,),
    ).fetchall() or []
    return round(sum(float(row["amount"]) * factors.get(row["frequency"], 0) for row in rows), 2)


AUTOMATION_FIELDS = ("start_date", "next_due_date", "financial_account_id", "auto_record")


def automation_values(conn, workspace_id: str, payload, current: dict[str, Any] | None = None) -> dict[str, Any]:
    """The automation fields to store for a recurring item, validated on the server.

    Only the fields the request actually sent change (an older app that never sends them keeps
    what the item has). `auto_record` is the verified Owner's alone, only for an income, never for
    salary, and needs a next date that is not in the past (no backfill). Reactivating an item whose
    next date passed moves it forward to today or later, so a paused period is never recorded.
    """
    sent = getattr(payload, "model_fields_set", set())
    current = current or {}
    values = {field: current.get(field) for field in AUTOMATION_FIELDS}
    values["auto_record"] = bool(values.get("auto_record"))
    for field in AUTOMATION_FIELDS:
        if field in sent:
            values[field] = getattr(payload, field)
    values["auto_record"] = bool(values["auto_record"])
    for field in ("start_date", "next_due_date"):
        values[field] = _as_date(values[field])
    today = costa_rica_today()
    if values["auto_record"]:
        if not schedule_automation_enabled():
            raise HTTPException(status_code=403, detail="Solo el Owner registra ingresos recurrentes automáticamente.")
        if payload.item_type != "income":
            raise HTTPException(status_code=422, detail="Solo un ingreso se registra automáticamente; los gastos fijos siguen como previstos.")
        if is_salary_category(payload.category):
            raise HTTPException(status_code=422, detail="El salario ya se registra con tu nómina y el depósito: no se repite como recurrente.")
        if not values["next_due_date"]:
            raise HTTPException(status_code=422, detail="Indicá la próxima fecha de este ingreso.")
        changed_date = "next_due_date" in sent and values["next_due_date"] != _as_date(current.get("next_due_date"))
        reactivated = payload.is_active and current and not current.get("is_active")
        if values["next_due_date"] < today:
            if reactivated and not changed_date:
                values["next_due_date"] = first_on_or_after(values["next_due_date"], today, payload.frequency, payload.due_day)
            elif changed_date or not current:
                raise HTTPException(status_code=422, detail="La próxima fecha no puede ser anterior a hoy: DINCR no registra ingresos pasados.")
    if values.get("financial_account_id"):
        owned = conn.execute("SELECT 1 FROM account_balances WHERE id=%s AND workspace_id=%s",
                             (values["financial_account_id"], workspace_id)).fetchone()
        if not owned:
            raise HTTPException(status_code=404, detail="Cuenta no encontrada.")
    return values


def upcoming_schedule(days: int = 45, *, today: date | None = None) -> dict[str, Any]:
    """Read-only: the Owner's next recurring incomes and debt installments, with their dates.

    Recorded entries of the last two weeks are listed as `recorded`/`paid`; future ones as
    `expected`: a projection, never shown as money that already moved.
    """
    from backend.finance.service import _add_months, _parse_date

    workspace_id = get_current_workspace_id()
    today = today or costa_rica_today()
    start, end = today - timedelta(days=14), today + timedelta(days=max(1, min(days, 120)) + 1)
    with get_connection() as conn:
        incomes = recurring_incomes_in_window(conn, workspace_id, start, end)
        debts = conn.execute(
            """SELECT id,name,monthly_payment,remaining_amount,payment_day,next_payment_date,auto_update_monthly
               FROM debts WHERE workspace_id=%s AND remaining_amount > 0 ORDER BY id""",
            (workspace_id,),
        ).fetchall() or []
        paid = conn.execute(
            """SELECT p.debt_id,d.name,p.payment_date,p.amount,p.source FROM debt_payments p JOIN debts d ON d.id=p.debt_id
               WHERE p.workspace_id=%s AND d.workspace_id=p.workspace_id AND p.payment_type='monthly_payment'
                 AND p.payment_date >= %s AND p.payment_date < %s ORDER BY p.payment_date""",
            (workspace_id, start, end),
        ).fetchall() or []
    installments = [{"debt_id": row["debt_id"], "name": row["name"], "due_date": str(row["payment_date"])[:10],
                     "amount": float(row["amount"]), "status": "paid",
                     "automatic": row["source"] == "auto_schedule"} for row in paid]
    for debt in debts:
        due = _parse_date(debt.get("next_payment_date"))
        amount = float(debt.get("monthly_payment") or 0)
        if not due or amount <= 0:
            continue
        day = int(debt.get("payment_day") or due.day)
        steps = 0
        while due < end and steps < 12:
            if due >= today:
                installments.append({"debt_id": debt["id"], "name": debt["name"], "due_date": due.isoformat(),
                                     "amount": round(min(amount, float(debt["remaining_amount"])), 2), "status": "expected",
                                     "automatic": bool(debt.get("auto_update_monthly", True))})
            due = _add_months(due, 1, day)
            steps += 1
    installments.sort(key=lambda entry: entry["due_date"])
    incomes["items"].sort(key=lambda entry: entry["due_date"])
    return {"date": today.isoformat(), "window": {"start": start.isoformat(), "end_exclusive": end.isoformat()},
            "incomes": incomes["items"], "installments": installments,
            "totals": {"incomes_expected": incomes["expected_pending_total"],
                       "installments_expected": round(sum(e["amount"] for e in installments if e["status"] == "expected"), 2)}}
