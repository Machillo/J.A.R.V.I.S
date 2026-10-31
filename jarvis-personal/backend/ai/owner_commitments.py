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
  for debt; an urgent goal keeps its share.

Read-only: every statement only reads, scoped by the workspace. Owner only (``strategy_dashboard``
calls it from the Owner blueprint).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from backend.core.database import get_connection
from backend.finance import salvavidas_plan

# The order the automatic contributions are taken from (the urgent goal keeps its share).
ABSORB_ORDER = ("fondo_de_emergencia", "vida_controlada", "inversion", "metas_o_inversion", "ataque_de_deuda")


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


def absorb(amounts: dict[str, float], automatic: float) -> tuple[dict[str, float], float]:
    """The shares after the automatic contributions are taken out, and how much they took."""
    left = max(_f(automatic), 0.0)
    result = dict(amounts)
    for key in ABSORB_ORDER:
        take = min(max(_f(result.get(key)), 0.0), left)
        result[key] = round(_f(result.get(key)) - take, 2)
        left = round(left - take, 2)
    return result, round(max(_f(automatic), 0.0) - left, 2)


def colones(amount: float) -> str:
    """"₡10.800": whole colones with dot thousands, as the app shows them."""
    return "₡" + f"{round(_f(amount)):,}".replace(",", ".")
