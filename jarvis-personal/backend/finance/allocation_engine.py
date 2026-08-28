from backend.finance.service import get_financial_summary
from backend.finance.strategy_rules import select_recommended_strategy
from backend.goals.service import get_financial_goals


PRIORITY_WEIGHTS = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1
}


def calculate_goal_pressure(goal):
    monthly_required = goal.get("monthly_required") or 0
    remaining_amount = goal.get("remaining_amount") or 0
    priority = goal.get("priority", "medium")

    priority_weight = PRIORITY_WEIGHTS.get(priority, 2)

    return {
        "goal_id": goal["id"],
        "name": goal["name"],
        "priority": priority,
        "remaining_amount": remaining_amount,
        "monthly_required": monthly_required,
        "days_remaining": goal.get("days_remaining"),
        "priority_weight": priority_weight,
        "pressure_score": monthly_required * priority_weight
    }


def get_active_goals():
    goals = get_financial_goals()

    return [
        goal for goal in goals
        if goal["status"] == "active" and goal["remaining_amount"] > 0
    ]


def has_urgent_critical_goal(goals, available_cash):
    for goal in goals:
        if (
            goal.get("priority") == "critical"
            and goal.get("monthly_required")
            and goal["monthly_required"] > available_cash
        ):
            return True

    return False


def calculate_allocation_plan():
    summary = get_financial_summary()
    recommended_strategy = select_recommended_strategy()
    goals = get_active_goals()

    available_cash = summary["results"]["available_cash"]
    debt_total = summary["debts"]["debt_total"]

    if available_cash <= 0:
        return {
            "status": "NO_AVAILABLE_CASH",
            "message": "No hay dinero disponible para repartir. Primero hay que estabilizar el flujo mensual.",
            "summary": summary,
            "recommended_strategy": recommended_strategy,
            "allocations": []
        }

    goal_pressures = [calculate_goal_pressure(goal) for goal in goals]
    total_goal_pressure = sum(goal["pressure_score"] for goal in goal_pressures)

    allocations = []

    urgent_critical_goal = has_urgent_critical_goal(goals, available_cash)

    if urgent_critical_goal:
        debt_percentage = 0
        goals_percentage = 1
        allocation_reason = (
            "Existe una meta crítica que requiere más dinero mensual del disponible. "
            "Se recomienda priorizar temporalmente esa meta y no hacer pagos extra a deudas."
        )
    elif debt_total > 0 and goals:
        debt_percentage = 0.5
        goals_percentage = 0.5
        allocation_reason = "Hay deuda activa y metas activas. Se recomienda repartir el disponible."
    elif debt_total > 0:
        debt_percentage = 1
        goals_percentage = 0
        allocation_reason = "Hay deuda activa y no hay metas activas. Se recomienda usar el disponible para deuda."
    elif goals:
        debt_percentage = 0
        goals_percentage = 1
        allocation_reason = "Hay metas activas y no hay deuda. Se recomienda usar el disponible para metas."
    else:
        debt_percentage = 0
        goals_percentage = 0
        allocation_reason = "No hay metas ni deudas activas para asignar dinero."

    debt_amount = available_cash * debt_percentage
    goals_amount = available_cash * goals_percentage

    if debt_amount > 0:
        allocations.append({
            "target_type": "debt",
            "target_name": "Pago adicional a deudas",
            "amount": debt_amount,
            "percentage": debt_percentage * 100,
            "reason": "Tienes deuda activa. Conviene destinar parte del dinero libre a reducir obligaciones."
        })

    if goals and goals_amount > 0:
        if total_goal_pressure <= 0:
            amount_per_goal = goals_amount / len(goals)

            for goal in goals:
                allocations.append({
                    "target_type": "goal",
                    "target_id": goal["id"],
                    "target_name": goal["name"],
                    "amount": amount_per_goal,
                    "percentage": (amount_per_goal / available_cash) * 100,
                    "reason": "Meta activa sin presión mensual calculada."
                })
        else:
            for goal in goal_pressures:
                goal_share = goal["pressure_score"] / total_goal_pressure
                goal_amount = goals_amount * goal_share

                allocations.append({
                    "target_type": "goal",
                    "target_id": goal["goal_id"],
                    "target_name": goal["name"],
                    "amount": goal_amount,
                    "percentage": (goal_amount / available_cash) * 100,
                    "reason": (
                        f"Meta con prioridad {goal['priority']} y requerimiento mensual "
                        f"de ₡{goal['monthly_required']:,.2f}."
                    )
                })

    unallocated_amount = available_cash - sum(item["amount"] for item in allocations)

    if unallocated_amount > 1:
        allocations.append({
            "target_type": "free",
            "target_name": "Libre no asignado",
            "amount": unallocated_amount,
            "percentage": (unallocated_amount / available_cash) * 100,
            "reason": "Monto no asignado por reglas actuales."
        })

    monthly_required_for_goals = sum(goal.get("monthly_required") or 0 for goal in goals)

    feasibility = "OK"

    if monthly_required_for_goals > available_cash:
        feasibility = "INSUFFICIENT_CASH_FOR_GOALS"

    return {
        "status": "OK",
        "available_cash": available_cash,
        "debt_total": debt_total,
        "goals": goals,
        "monthly_required_for_goals": monthly_required_for_goals,
        "feasibility": feasibility,
        "allocation_reason": allocation_reason,
        "urgent_critical_goal": urgent_critical_goal,
        "recommended_strategy": recommended_strategy,
        "allocations": allocations
    }