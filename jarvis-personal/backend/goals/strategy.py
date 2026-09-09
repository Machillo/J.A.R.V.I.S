"""Deterministic portfolio rules for financial goals.

Goals in the same ``alternative_group`` compete with each other: only the
explicitly selected option receives money.  A later goal can depend on a group
being completed, which lets JARVIS keep a car behind the active trip without
mixing either reserve with the Salvavidas.
"""
from __future__ import annotations

from typing import Any


def _n(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def build_goal_portfolio(
    goals: list[dict[str, Any]],
    *,
    available: float,
    one_month_protected: bool,
    highest_debt_apr: float,
    immediate_risk: bool = False,
) -> dict[str, Any]:
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
        blocked_by = None
        if group and not goal.get("is_selected"):
            blocked_by = "alternativa no seleccionada"
        elif dependency and dependency not in completed_groups:
            blocked_by = f"primero debe completarse {dependency}"
        elif immediate_risk:
            blocked_by = "riesgo de liquidez en los próximos 45 días"
        elif not one_month_protected:
            blocked_by = "Salvavidas menor a un mes"
        elif highest_debt_apr >= 10:
            blocked_by = "deuda prioritaria con tasa anual de 10% o más"

        remaining = max(_n(goal.get("remaining_amount", _n(goal.get("target_amount")) - _n(goal.get("current_amount")))), 0)
        required = min(max(_n(goal.get("monthly_required")), 0), remaining)
        candidates.append({**goal, "remaining_amount": round(remaining, 2), "monthly_required": round(required, 2), "blocked_by": blocked_by})

    candidates.sort(key=lambda goal: (int(_n(goal.get("funding_order")) or 100), str(goal.get("target_date") or "9999-12-31"), int(_n(goal.get("id")))))
    active = next((goal for goal in candidates if not goal.get("blocked_by") and _n(goal.get("remaining_amount")) > 0), None)
    allocation = min(max(_n(available), 0), _n(active.get("monthly_required"))) if active else 0.0
    return {
        "active_goal": {**active, "fundable_now": round(allocation, 2)} if active else None,
        "goal_allocation": round(allocation, 2),
        "items": candidates,
        "selected_alternatives": selected_by_group,
        "rule": "Una alternativa por grupo; metas solo después de liquidez, un mes de Salvavidas y deuda cara.",
    }
