"""Movimientos > Análisis > Resumen: the period (a month or a year), the sources of the money, and
what was saved.

- ``period``: ``YYYY-MM`` is a month, ``YYYY`` a whole year; anything else is refused (422).
- income by category: the same rows each account's income total counts. Everyone: ``salaries``
  (their category, else "Salario"), ``payroll_events`` (overtime, "Horas extra") and ``income``
  movements. The verified Owner's income follows his ledger (``owner_ledger``): his salary by its
  rule (``owner_salary``: projected for the month in course and for a closed month without a
  deposit) and the other ``income`` movements; gross payroll is not income there.
- saved ("lo que guardaste"): money the user put aside in the period, never income minus spending:
  contributions to their goals (``finva_goal_contributions``) and the Salvavidas automatic
  contributions their active plan schedules in the period up to today (``salvavidas_plan``, the
  same dates the Salvavidas screen counts). Unknown parts are 0 only when there is nothing to
  count (no table, no plan), never guessed.

Read-only: every statement only reads, scoped by the workspace.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import HTTPException

from backend.core.time import costa_rica_today
from backend.finance import salvavidas_plan
from backend.user_product import owner_ledger


def period_range(value: str | None) -> tuple[date, date, str, str]:
    """``(start, end, label, scope)`` for ``YYYY-MM`` (a month) or ``YYYY`` (a year); the current month by default."""
    text = (value or "").strip()
    try:
        if not text:
            start = date.today().replace(day=1)
        elif len(text) == 4 and text.isdigit():
            start = date(int(text), 1, 1)
            return start, date(start.year + 1, 1, 1), text, "year"
        else:
            start = date.fromisoformat(f"{text}-01")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="El periodo debe tener formato YYYY-MM o YYYY.") from exc
    end = date(start.year + (start.month == 12), 1 if start.month == 12 else start.month + 1, 1)
    return start, end, start.strftime("%Y-%m"), "month"


def _table_exists(conn, name: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (f"public.{name}",)).fetchone()
    return bool(row and row.get("table_name"))


def income_categories(conn, workspace_id: str, start: date, end: date, *, transaction_date: str, owner: Any = False) -> list[dict]:
    """Income in ``[start, end)`` by category, largest first."""
    if owner:
        # The Owner's ledger: the salary by its rule (owner_ledger.owner_salary, "Salario (estimado)"
        # when any month of it is projected) and the other income movements.
        rows = conn.execute(
            f"""SELECT COALESCE(NULLIF(BTRIM(category),''),'Sin categoría') AS category, ROUND(SUM(amount),2) AS amount FROM transactions
                WHERE workspace_id=%s AND LOWER(BTRIM(COALESCE(transaction_type,'')))='income'
                  AND LOWER(BTRIM(COALESCE(category,'')))<>'salario'
                  AND {transaction_date} >= %s AND {transaction_date} < %s
                GROUP BY 1 HAVING SUM(amount) <> 0""",
            (workspace_id, start, end),
        ).fetchall()
        salary = owner_ledger.owner_salary(conn, workspace_id, start, end)
        items = [{"category": row["category"], "amount": round(float(row["amount"] or 0), 2)} for row in rows]
        if salary["salary"]:
            label = "Salario (estimado)" if salary["estimated"] else owner_ledger.SALARY_CATEGORY
            items.append({"category": label, "amount": round(float(salary["salary"]), 2)})
        return sorted(items, key=lambda item: item["amount"], reverse=True)
    else:
        sql = f"""SELECT category, ROUND(SUM(amount),2) AS amount FROM (
                    SELECT COALESCE(NULLIF(BTRIM(category),''),'Salario') AS category, amount FROM salaries
                      WHERE workspace_id=%s AND created_at::date >= %s AND created_at::date < %s
                    UNION ALL
                    SELECT 'Horas extra', amount FROM payroll_events
                      WHERE workspace_id=%s AND amount>0 AND created_at::date >= %s AND created_at::date < %s
                    UNION ALL
                    SELECT COALESCE(NULLIF(BTRIM(category),''),'Sin categoría'), amount FROM transactions
                      WHERE workspace_id=%s AND transaction_type='income' AND {transaction_date} >= %s AND {transaction_date} < %s
                  ) q GROUP BY 1 HAVING SUM(amount) <> 0 ORDER BY amount DESC"""
        params = (workspace_id, start, end, workspace_id, start, end, workspace_id, start, end)
    return [{"category": row["category"], "amount": round(float(row["amount"] or 0), 2)} for row in conn.execute(sql, params).fetchall()]


def saved(conn, workspace_id: str, start: date, end: date) -> dict[str, Any]:
    """What was put aside in ``[start, end)``: goal contributions and Salvavidas automatic contributions."""
    goals = 0.0
    if _table_exists(conn, "finva_goal_contributions"):
        goals = float(conn.execute(
            """SELECT COALESCE(SUM(amount),0) AS total FROM finva_goal_contributions
               WHERE workspace_id=%s AND contribution_date >= %s AND contribution_date < %s""",
            (workspace_id, start, end),
        ).fetchone()["total"] or 0)
    salvavidas = 0.0
    row = conn.execute(
        "SELECT preference_value FROM user_preferences WHERE workspace_id=%s AND preference_key='salvavidas'",
        (workspace_id,),
    ).fetchone() if _table_exists(conn, "user_preferences") else None
    config = (row or {}).get("preference_value")
    plan = salvavidas_plan.normalize_plan(config.get("auto_contribution")) if isinstance(config, dict) else None
    until = min(end - timedelta(days=1), costa_rica_today())
    if plan and plan["enabled"] and until >= start:
        dates = salvavidas_plan.scheduled_dates(plan, start - timedelta(days=1), until)
        salvavidas = len(dates) * plan["amount"]
    return {"total": round(goals + salvavidas, 2), "goals": round(goals, 2), "salvavidas": round(salvavidas, 2)}
