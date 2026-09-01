from __future__ import annotations

from typing import Any

from backend.ai.preferences import get_preference, set_preference
from backend.auth.current_user import get_current_workspace_id
from backend.core.database import get_connection

PREFERENCE_KEY = "salvavidas"
TARGET_MONTHS = 6


def _f(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _monthly_amount(expected_amount: Any, frequency: str | None, interval_months: Any) -> float:
    amount = max(_f(expected_amount), 0.0)
    interval = max(int(_f(interval_months) or 1), 1)
    frequency = (frequency or "monthly").lower().strip()

    if frequency in {"annual", "yearly", "anual"}:
        return amount / 12.0
    if frequency in {"weekly", "semanal"}:
        return amount * 52.0 / 12.0
    if frequency in {"biweekly", "quincenal"}:
        return amount * 24.0 / 12.0
    return amount / interval


def _load_config() -> dict[str, Any]:
    raw = get_preference(PREFERENCE_KEY, {}) or {}
    if not isinstance(raw, dict):
        raw = {}
    protected = raw.get("protected_expense_ids") or []
    return {
        "current_amount": max(_f(raw.get("current_amount")), 0.0),
        "protected_expense_ids": [int(item) for item in protected if str(item).isdigit()],
        "target_months": TARGET_MONTHS,
    }


def _fetch_active_debts(workspace_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, remaining_amount, monthly_payment, payment_day
            FROM debts
            WHERE workspace_id = %s
              AND COALESCE(remaining_amount, 0) > 0
            ORDER BY monthly_payment DESC, name ASC
            """,
            (workspace_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _fetch_fixed_expenses(workspace_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, category, expected_amount, currency, frequency,
                   interval_months, due_day, is_active
            FROM fixed_expenses
            WHERE workspace_id = %s
              AND is_active = TRUE
            ORDER BY due_day NULLS LAST, name ASC
            """,
            (workspace_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_salvavidas_state() -> dict[str, Any]:
    workspace_id = get_current_workspace_id()
    config = _load_config()
    debts = _fetch_active_debts(workspace_id)
    fixed_expenses = _fetch_fixed_expenses(workspace_id)

    valid_expense_ids = {int(row["id"]) for row in fixed_expenses}
    selected_ids = [item for item in config["protected_expense_ids"] if item in valid_expense_ids]
    selected_set = set(selected_ids)

    debt_items = []
    debt_monthly = 0.0
    for debt in debts:
        monthly = max(_f(debt.get("monthly_payment")), 0.0)
        debt_monthly += monthly
        debt_items.append({
            "id": debt.get("id"),
            "name": debt.get("name") or "Deuda",
            "monthly_payment": round(monthly, 2),
            "remaining_amount": round(max(_f(debt.get("remaining_amount")), 0.0), 2),
            "payment_day": debt.get("payment_day"),
        })

    expense_items = []
    protected_monthly = 0.0
    for expense in fixed_expenses:
        monthly = _monthly_amount(
            expense.get("expected_amount"),
            expense.get("frequency"),
            expense.get("interval_months"),
        )
        selected = int(expense["id"]) in selected_set
        if selected:
            protected_monthly += monthly
        expense_items.append({
            "id": expense.get("id"),
            "name": expense.get("name") or "Gasto",
            "category": expense.get("category") or "Gastos fijos",
            "expected_amount": round(max(_f(expense.get("expected_amount")), 0.0), 2),
            "monthly_amount": round(monthly, 2),
            "currency": expense.get("currency") or "CRC",
            "frequency": expense.get("frequency") or "monthly",
            "interval_months": int(_f(expense.get("interval_months")) or 1),
            "due_day": expense.get("due_day"),
            "selected": selected,
        })

    monthly_base = debt_monthly + protected_monthly
    target = monthly_base * TARGET_MONTHS
    current = max(_f(config.get("current_amount")), 0.0)
    missing = max(target - current, 0.0)
    coverage = current / monthly_base if monthly_base > 0 else 0.0
    progress = min((current / target) * 100.0, 100.0) if target > 0 else 0.0

    milestones = []
    for months in (1, 3, 6):
        milestone_target = monthly_base * months
        milestones.append({
            "months": months,
            "target": round(milestone_target, 2),
            "reached": current >= milestone_target if milestone_target > 0 else False,
        })

    return {
        "status": "OK",
        "current_amount": round(current, 2),
        "monthly_base": round(monthly_base, 2),
        "target_months": TARGET_MONTHS,
        "target_amount": round(target, 2),
        "missing_amount": round(missing, 2),
        "coverage_months": round(coverage, 2),
        "progress_percent": round(progress, 2),
        "protected_expense_ids": selected_ids,
        "components": {
            "debt_monthly_payments": round(debt_monthly, 2),
            "protected_expenses": round(protected_monthly, 2),
        },
        "debts": debt_items,
        "available_expenses": expense_items,
        "milestones": milestones,
        "verification": {
            "mode": "manual",
            "account_linked": False,
            "message": "El saldo se registra manualmente. La conciliación automática se activará cuando JARVIS tenga movimientos y una cuenta real asignada al Salvavidas.",
        },
    }


def update_salvavidas(*, current_amount: float | None = None, protected_expense_ids: list[int] | None = None) -> dict[str, Any]:
    config = _load_config()
    if current_amount is not None:
        config["current_amount"] = max(float(current_amount), 0.0)
    if protected_expense_ids is not None:
        clean_ids = []
        for item in protected_expense_ids:
            value = int(item)
            if value > 0 and value not in clean_ids:
                clean_ids.append(value)
        config["protected_expense_ids"] = clean_ids

    config["target_months"] = TARGET_MONTHS
    set_preference(PREFERENCE_KEY, config)
    return get_salvavidas_state()
