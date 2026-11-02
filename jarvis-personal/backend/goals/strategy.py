"""Deterministic portfolio rules for financial goals.

Goals in the same ``alternative_group`` compete with each other: only the
explicitly selected option receives money.  A later goal can depend on a group
being completed, which lets JARVIS keep a car behind the active trip without
mixing either reserve with the Salvavidas.

A goal's importance (its ``priority``) decides how much debt it can wait behind:
an essential goal due within a year is funded once one month of Salvavidas is
protected, even with expensive debt; an important one waits for no debt at 20% or
more; a nice-to-have waits for no debt at 10% or more (building wealth).
"""
from __future__ import annotations

from datetime import date
from typing import Any
from backend.core.i18n import tx

EXPENSIVE_DEBT_APR = 20.0
PRIORITY_DEBT_APR = 10.0
NEAR_GOAL_MONTHS = 12
IMPORTANCE_RANK = {"essential": 0, "important": 1, "nice": 2}


def _n(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def goal_importance(priority: Any) -> str:
    """essential (high/critical), important (medium, or unset) or nice (low)."""
    value = str(priority or "").lower().strip()
    if value in {"critical", "critica", "crítica", "high", "alta"}:
        return "essential"
    if value in {"low", "baja"}:
        return "nice"
    return "important"


def _months_until(target_date: Any, today: date) -> int | None:
    try:
        target = date.fromisoformat(str(target_date)[:10])
    except (TypeError, ValueError):
        return None
    return (target.year - today.year) * 12 + target.month - today.month


def build_goal_portfolio(
    goals: list[dict[str, Any]],
    *,
    available: float,
    one_month_protected: bool,
    highest_debt_apr: float | None,
    immediate_risk: bool = False,
    today: date | None = None,
) -> dict[str, Any]:
    today = today or date.today()
    completed_groups = {
        str(goal.get("alternative_group"))
        for goal in goals
        if goal.get("alternative_group") and goal.get("status") == "completed"
    }
    selected_by_group = {
        str(goal.get("alternative_group")): goal.get("id")
        for goal in goals
        if goal.get("alternative_group") and goal.get("is_selected")
    }
    candidates = []
    for goal in goals:
        if str(goal.get("status") or "active") not in {"active", "candidate"}:
            continue
        group = str(goal.get("alternative_group") or "")
        dependency = str(goal.get("depends_on_group") or "")
        importance = goal_importance(goal.get("priority"))
        months_left = _months_until(goal.get("target_date"), today)
        near = months_left is not None and months_left <= NEAR_GOAL_MONTHS
        blocked_by = None
        if group and not goal.get("is_selected"):
            blocked_by = tx("alternativa no seleccionada", "alternative not selected")
        elif dependency and dependency not in completed_groups:
            blocked_by = tx(f"primero debe completarse {dependency}", f"{dependency} must be completed first")
        elif immediate_risk:
            blocked_by = tx("riesgo de liquidez en los próximos 45 días", "liquidity risk in the next 45 days")
        elif not one_month_protected:
            blocked_by = tx("Salvavidas menor a un mes", "emergency fund below one month")
        elif importance == "essential" and near:
            # An essential goal with a date within a year can't wait for the debts to end.
            blocked_by = None
        elif highest_debt_apr is None:
            # A debt's rate is unknown: whether it is expensive debt can't be told (never 0%).
            blocked_by = tx("falta la tasa de interés de una deuda", "a debt's interest rate is missing")
        elif importance == "nice" and highest_debt_apr >= PRIORITY_DEBT_APR:
            blocked_by = tx("deuda prioritaria con tasa anual de 10% o más", "priority debt with an annual rate of 10% or more")
        elif highest_debt_apr >= EXPENSIVE_DEBT_APR:
            blocked_by = tx("deuda cara con tasa anual de 20% o más", "expensive debt with an annual rate of 20% or more")

        remaining = max(_n(goal.get("remaining_amount", _n(goal.get("target_amount")) - _n(goal.get("current_amount")))), 0)
        required = min(max(_n(goal.get("monthly_required")), 0), remaining)
        candidates.append({**goal, "remaining_amount": round(remaining, 2), "monthly_required": round(required, 2), "importance": importance, "blocked_by": blocked_by})

    candidates.sort(key=lambda goal: (int(_n(goal.get("funding_order")) or 100), IMPORTANCE_RANK[goal["importance"]], str(goal.get("target_date") or "9999-12-31"), int(_n(goal.get("id")))))
    active = next((goal for goal in candidates if not goal.get("blocked_by") and _n(goal.get("remaining_amount")) > 0), None)
    allocation = min(max(_n(available), 0), _n(active.get("monthly_required"))) if active else 0.0
    return {
        "active_goal": {**active, "fundable_now": round(allocation, 2)} if active else None,
        "goal_allocation": round(allocation, 2),
        "items": candidates,
        "selected_alternatives": selected_by_group,
        "rule": tx(
            "Una alternativa por grupo; metas después de liquidez y un mes de Salvavidas. Imprescindible con fecha en 12 meses: aunque haya deuda cara; importante: sin deudas de 20% o más; un gusto: sin deudas de 10% o más.",
            "One alternative per group; goals after liquidity and one month of emergency fund. Essential and due within 12 months: even with expensive debt; important: no debt at 20% or more; nice to have: no debt at 10% or more.",
        ),
    }
