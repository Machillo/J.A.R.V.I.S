"""What the Owner's plan sets aside before it distributes anything (Tu plan del mes, distribución).

The plan only splits money that is really free, so every commitment the app knows about comes out
first (the "universe": everything recorded feeds the plan):

- every active fixed expense due in the cycle and not yet paid (not only house and phone), except
  the ones that are a debt already counted in ``debts`` (``debt_duplicate``);
- the expenses recorded by hand (the ``expenses`` table) in the cycle, besides the bank movements
  the plan already reads;
- the Salvavidas automatic contributions still to come in the cycle: that money goes to the
  Salvavidas by itself, so the distribution tells the Owner only what to move on top of it. It
  comes out of the Salvavidas share first, then out of free spending, investment and the extra
  for debt; an urgent goal keeps its share;
- the exact amount (what the Owner has left, distributed on the 1st with the month before's leftover)
  is distributed whole: the Salvavidas already got that month's automatic contributions (4 or 5
  paydays), so they come out of the Salvavidas share only and go to the debt attack
  (``last_month_automatic_savings``, ``move_share``), never out of the amount;
- the locked savings blocks' contributions still to come in the cycle (``owner_debt_block_store``):
  that money is the debt attack, paid into the debt when the block matures, so it comes out of the
  extra for debt first, then out of the other shares; an urgent goal keeps its share.

Read-only: every statement only reads, scoped by the workspace. Owner only (``strategy_dashboard``
calls it from the Owner blueprint).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from backend.ai import owner_debt_block_store
from backend.core.database import get_connection
from backend.finance import salvavidas_plan

# The order the automatic contributions are taken from (the urgent goal keeps its share).
ABSORB_ORDER = ("fondo_de_emergencia", "vida_controlada", "inversion", "metas_o_inversion", "ataque_de_deuda")
BLOCK_ABSORB_ORDER = ("ataque_de_deuda", "vida_controlada", "inversion", "metas_o_inversion", "fondo_de_emergencia")


def _f(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def fixed_expense_ids(living: dict[str, Any]) -> set[int]:
    """Every active fixed expense that is not a debt counted in ``debts``."""
    rows = list(living.get("included_fixed") or []) + list(living.get("excluded_from_strategy") or [])
    return {int(row["id"]) for row in rows if row.get("id") is not None and row.get("reason") != "debt_duplicate"}


def manual_expenses(workspace_id: str, cycle_report: dict[str, Any], today: date) -> dict[str, Any]:
    """Expenses recorded by hand from the cycle's expense window start (Costa Rica date) to today."""
    start = _day((cycle_report.get("expense_cycle") or {}).get("start")) or _day((cycle_report.get("cycle") or {}).get("start"))
    if not start or start > today:
        return {"total": 0.0, "count": 0}
    with get_connection() as conn:
        if not conn.execute("SELECT to_regclass('public.expenses') AS name").fetchone()["name"]:
            return {"total": 0.0, "count": 0}
        row = conn.execute(
            """SELECT COALESCE(SUM(amount),0) AS total, COUNT(*) AS count FROM expenses
               WHERE workspace_id=%s AND amount IS NOT NULL
                 AND (created_at - interval '6 hours')::date >= %s AND (created_at - interval '6 hours')::date <= %s""",
            (workspace_id, start, today),
        ).fetchone()
    return {"total": round(_f(row.get("total") if row else 0), 2), "count": int(_f(row.get("count") if row else 0))}


def automatic_savings(salvavidas: dict[str, Any], cycle_report: dict[str, Any], today: date) -> dict[str, Any]:
    """The Salvavidas automatic contributions from today to the end of the cycle."""
    plan = salvavidas_plan.normalize_plan(salvavidas.get("auto_contribution"))
    end = _day((cycle_report.get("cycle") or {}).get("end"))
    if not plan or not plan["enabled"] or not end or end < today:
        return {"amount": 0.0, "count": 0, "per_contribution": 0.0, "frequency": None}
    dates = salvavidas_plan.scheduled_dates(plan, today - timedelta(days=1), end)
    return {"amount": round(len(dates) * plan["amount"], 2), "count": len(dates),
            "per_contribution": plan["amount"], "frequency": plan["frequency"]}


def last_month_automatic_savings(salvavidas: dict[str, Any], today: date) -> dict[str, Any]:
    """The Salvavidas automatic contributions made in the calendar month before ``today``'s: the month
    whose leftover the Owner distributes on the 1st (4 or 5 paydays)."""
    plan = salvavidas_plan.normalize_plan(salvavidas.get("auto_contribution"))
    first = today.replace(day=1)
    last_day = first - timedelta(days=1)
    month_start = last_day.replace(day=1)
    if not plan or not plan["enabled"]:
        return {"amount": 0.0, "count": 0, "per_contribution": 0.0, "frequency": None, "month": month_start.strftime("%Y-%m")}
    dates = salvavidas_plan.scheduled_dates(plan, month_start - timedelta(days=1), last_day)
    return {"amount": round(len(dates) * plan["amount"], 2), "count": len(dates), "per_contribution": plan["amount"],
            "frequency": plan["frequency"], "month": month_start.strftime("%Y-%m")}


def move_share(amounts: dict[str, float], amount: float, source: str, target: str) -> tuple[dict[str, float], float]:
    """Moves up to ``amount`` from one share to another; the total stays the same."""
    result = dict(amounts)
    moved = round(min(max(_f(amount), 0.0), max(_f(result.get(source)), 0.0)), 2)
    result[source] = round(_f(result.get(source)) - moved, 2)
    result[target] = round(_f(result.get(target)) + moved, 2)
    return result, moved


def block_savings(blocks: list[dict[str, Any]], cycle_report: dict[str, Any], today: date) -> dict[str, Any]:
    """The locked savings blocks' contributions from today to the end of the cycle."""
    end = _day((cycle_report.get("cycle") or {}).get("end"))
    if not end or end < today:
        return {"amount": 0.0, "count": 0, "blocks": []}
    rows = []
    for block in blocks:
        dates = owner_debt_block_store.contributions(block, today - timedelta(days=1), end)
        if dates:
            rows.append({"debt_name": block.get("debt_name"), "count": len(dates),
                         "amount": round(len(dates) * block["weekly_amount"], 2)})
    return {"amount": round(sum(row["amount"] for row in rows), 2), "count": sum(row["count"] for row in rows), "blocks": rows}


def absorb(amounts: dict[str, float], automatic: float, order: tuple[str, ...] = ABSORB_ORDER) -> tuple[dict[str, float], float]:
    """The shares after the automatic contributions are taken out, and how much they took."""
    left = max(_f(automatic), 0.0)
    result = dict(amounts)
    for key in order:
        take = min(max(_f(result.get(key)), 0.0), left)
        result[key] = round(_f(result.get(key)) - take, 2)
        left = round(left - take, 2)
    return result, round(max(_f(automatic), 0.0) - left, 2)


def colones(amount: float) -> str:
    """"₡10.800": whole colones with dot thousands, as the app shows them."""
    return "₡" + f"{round(_f(amount)):,}".replace(",", ".")
