"""Movimientos > Análisis > Análisis financiero (VIP and the Owner): the last twelve months of the
same figures Resumen del mes shows, so the app can explain them in plain words.

- ``months``: the twelve calendar months up to the current one (Costa Rica date), oldest first. Each
  carries the period's income, expenses and debt payments exactly as Resumen del mes counts them
  (the verified Owner's ledger for the Owner, ``owner_ledger``; everyone else's record tables), and
  what was saved (``summary_breakdown.saved``: goal and Salvavidas contributions, never income
  minus spending). The current month is ``partial``: it is not over.
- ``categories``: this month's spending by category beside the average of the last three complete
  months that recorded any spending (``average`` is null when there is none: unknown, not 0).

The app derives its sentences from these numbers (``FinancialReading`` in DincrCore / core-data);
nothing here judges or advises. Read-only: every statement only reads, scoped by the workspace.
"""
from __future__ import annotations

from backend.auth.current_user import get_current_account_id, get_current_workspace_id
from backend.core.database import get_connection
from backend.core.time import costa_rica_today
from backend.user_product import free_service, owner_ledger, summary_breakdown

MONTHS = 12
BASELINE_MONTHS = 3


def get_financial_analysis() -> dict:
    account_id, workspace_id = get_current_account_id(), get_current_workspace_id()
    current = costa_rica_today().replace(day=1)
    starts = [free_service._shift_month(current, offset) for offset in range(1 - MONTHS, 1)]
    with get_connection() as conn:
        # The same decision as Resumen del mes: the stored identity of this account and workspace.
        owner = free_service.owner_account_context(conn, account_id, workspace_id)
        months = []
        for start in starts:
            end = free_service._next_month(start)
            totals = (owner_ledger.owner_month_totals(conn, workspace_id, start, end) if owner
                      else free_service._period_totals(conn, workspace_id, start, end))
            months.append({
                "period": start.strftime("%Y-%m"),
                "income": free_service._money(totals["income"]),
                "expenses": free_service._money(totals["expenses"]),
                "debt_paid": free_service._money(totals["debt_paid"]),
                "saved": summary_breakdown.saved(conn, workspace_id, start, end)["total"],
                "partial": start == current,
            })
        baseline = [start for start, month in zip(starts[:-1], months[:-1]) if month["expenses"] > 0][-BASELINE_MONTHS:]
        now = free_service._categories(conn, workspace_id, current, free_service._next_month(current))
        before = [free_service._categories(conn, workspace_id, start, free_service._next_month(start)) for start in baseline]
    return {"months": months, "categories": _compare(now, before)}


def _compare(now: list[dict], before: list[list[dict]]) -> list[dict]:
    """This month's amount and the baseline average per category; this month's largest first."""
    current = {row["category"]: row["amount"] for row in now}
    totals: dict[str, float] = {}
    for month in before:
        for row in month:
            totals[row["category"]] = totals.get(row["category"], 0.0) + row["amount"]
    names = list(current) + sorted(name for name in totals if name not in current)
    return [{
        "category": name,
        "current": current.get(name, 0.0),
        "average": round(totals.get(name, 0.0) / len(before), 2) if before else None,
    } for name in names]
