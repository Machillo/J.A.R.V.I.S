"""Deterministic, read-only cash liquidity timeline."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any

from backend.finance.cashflow import get_pay_schedule
from backend.finance.fixed_expenses import list_fixed_expenses
from backend.finance.intelligence import list_account_balances
from backend.finance.service import calculate_monthly_salary_projection, get_debts
from backend.goals.service import get_financial_goals


def _money(value: Any) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _date(value: Any) -> date | None:
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except (TypeError, ValueError):
        return None


def _safe_day(year: int, month: int, day: int) -> date:
    return date(year, month, min(max(int(day), 1), monthrange(year, month)[1]))


def _next_monthly(day_of_month: int, start: date, interval: int = 1):
    cursor = date(start.year, start.month, 1)
    for _ in range(3):
        due = _safe_day(cursor.year, cursor.month, day_of_month)
        if due >= start:
            yield due
        month = cursor.month - 1 + interval
        cursor = date(cursor.year + month // 12, month % 12 + 1, 1)


def _events_for_pay_schedule(schedule: dict[str, Any] | None, start: date, end: date, amount: float):
    if not schedule or amount <= 0:
        return []
    frequency = str(schedule.get("pay_frequency") or "").lower()
    first = _date(schedule.get("first_pay_date"))
    events: list[date] = []
    if first:
        step = 7 if frequency == "weekly" else 14 if frequency in {"biweekly", "quincenal"} else 0
        if step:
            cursor = first
            while cursor < start:
                cursor += timedelta(days=step)
            while cursor <= end:
                events.append(cursor)
                cursor += timedelta(days=step)
    if not events and frequency in {"monthly", "monthly_fixed"}:
        day_value = schedule.get("pay_day") or 15
        events = list(_next_monthly(int(day_value), start))
    return events


def get_financial_timeline(days: int = 45) -> dict[str, Any]:
    """Project available CRC liquidity after each known event, without mutating data."""
    start = date.today()
    end = start + timedelta(days=min(max(int(days or 45), 7), 90))
    accounts = list_account_balances().get("items", [])
    available = round(sum(_money(item.get("balance_crc")) for item in accounts
                          if item.get("include_in_net_worth") and item.get("account_type") != "investment"), 2)
    events: list[dict[str, Any]] = []

    salary = calculate_monthly_salary_projection()
    salary_amount = _money((salary.get("results") or {}).get("projected_net")) if isinstance(salary, dict) else 0
    schedule = get_pay_schedule()
    pay_dates = _events_for_pay_schedule(schedule, start, end, salary_amount)
    for when in pay_dates:
        events.append({"date": when.isoformat(), "name": "Ingreso de salario", "kind": "income", "amount": salary_amount, "impact": salary_amount, "source": "pay_schedule"})

    for expense in list_fixed_expenses(active_only=True):
        if not expense.get("due_day") or str(expense.get("frequency") or "monthly").lower() not in {"monthly", "bimonthly", "quarterly"}:
            continue
        interval = int(expense.get("interval_months") or 1)
        for when in _next_monthly(int(expense["due_day"]), start, interval):
            if when > end:
                continue
            amount = _money(expense.get("expected_amount"))
            events.append({"date": when.isoformat(), "name": expense.get("name") or "Gasto recurrente", "kind": "recurring_expense", "amount": amount, "impact": -amount, "source": "fixed_expense"})

    for debt in get_debts() or []:
        if not debt.get("payment_day") or _money(debt.get("monthly_payment")) <= 0:
            continue
        for when in _next_monthly(int(debt["payment_day"]), start):
            if when > end or _money(debt.get("remaining_amount")) <= 0:
                continue
            amount = min(_money(debt.get("monthly_payment")), _money(debt.get("remaining_amount")))
            events.append({"date": when.isoformat(), "name": f"Cuota · {debt.get('name') or 'Deuda'}", "kind": "debt_payment", "amount": amount, "impact": -amount, "source": "debt"})

    for goal in get_financial_goals() or []:
        target = _date(goal.get("target_date"))
        if target and start <= target <= end and str(goal.get("status") or "active").lower() == "active":
            events.append({"date": target.isoformat(), "name": f"Meta · {goal.get('name') or 'Meta financiera'}", "kind": "goal", "amount": _money(goal.get("target_amount")), "impact": 0, "source": "financial_goal", "note": "Recordatorio; no descuenta saldo sin una aportación programada."})

    events.sort(key=lambda item: (item["date"], 0 if item["impact"] >= 0 else 1, item["name"]))
    projected = available
    for event in events:
        projected = round(projected + _money(event["impact"]), 2)
        event["projected_balance"] = projected
    return {"status": "OK", "start_date": start.isoformat(), "end_date": end.isoformat(), "opening_available": available, "events": events, "ending_available": projected, "event_count": len(events), "assumptions": ["Solo se proyectan ingresos con calendario configurado y obligaciones activas con fecha y monto.", "Metas se muestran como recordatorio y no descuentan saldo automáticamente.", "IBKR/inversiones quedan fuera de liquidez disponible; se reflejan en Patrimonio." ]}
