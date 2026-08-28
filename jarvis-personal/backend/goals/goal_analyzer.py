from backend.finance.service import get_financial_summary
from backend.finance.evaluators import evaluate_loan
from backend.goals.service import get_financial_goals, get_financial_goal


def build_goal_solution_options(goal: dict, available_cash: float, monthly_required: float):
    remaining_amount = goal["remaining_amount"]
    monthly_gap = available_cash - monthly_required

    options = []

    if monthly_gap < 0:
        deficit = abs(monthly_gap)

        options.append({
            "option": "increase_income",
            "name": "Generar ingreso extra",
            "monthly_needed": deficit,
            "description": f"Necesitas generar aproximadamente ₡{deficit:,.2f} extra por mes para llegar a tiempo."
        })

        affordable_target = available_cash * (goal["days_remaining"] / 30)

        options.append({
            "option": "reduce_goal",
            "name": "Reducir presupuesto de la meta",
            "affordable_target": affordable_target,
            "description": f"Con tu flujo actual, podrías cubrir aproximadamente ₡{affordable_target:,.2f} antes de la fecha."
        })

        options.append({
            "option": "financing",
            "name": "Financiar diferencia",
            "amount_to_finance": remaining_amount,
            "description": "Podrías evaluar préstamo o minicuotas, pero solo si la cuota mensual sigue siendo viable."
        })

        options.append({
            "option": "extend_deadline",
            "name": "Mover fecha objetivo",
            "description": "Si la fecha no es obligatoria, extenderla reduce la presión mensual."
        })

    else:
        options.append({
            "option": "stay_on_plan",
            "name": "Mantener estrategia actual",
            "monthly_surplus_after_goal": monthly_gap,
            "description": f"La meta es viable. Después de cubrirla quedarían ₡{monthly_gap:,.2f} al mes."
        })

    return options


def analyze_goal(goal: dict):
    summary = get_financial_summary()

    available_cash = summary["results"]["available_cash"]

    remaining_amount = goal["remaining_amount"]
    monthly_required = goal["monthly_required"] or 0

    monthly_gap = available_cash - monthly_required

    if goal["status"] == "completed":
        probability = "completed"
        risk_level = "none"
        recommendation = "Meta completada."
    elif available_cash <= 0:
        probability = "very_low"
        risk_level = "critical"
        recommendation = "No hay dinero disponible para avanzar esta meta."
    elif monthly_required <= 0:
        probability = "unknown"
        risk_level = "unknown"
        recommendation = "No hay fecha objetivo suficiente para calcular probabilidad."
    elif monthly_gap >= 0:
        probability = "high"
        risk_level = "low"
        recommendation = "La meta es alcanzable si mantienes este ritmo."
    elif available_cash >= monthly_required * 0.75:
        probability = "medium"
        risk_level = "medium"
        recommendation = "La meta es posible, pero necesitas reducir gastos o generar ingresos extra."
    elif available_cash >= monthly_required * 0.5:
        probability = "low"
        risk_level = "high"
        recommendation = "La meta está en riesgo. Necesitas una estrategia adicional."
    else:
        probability = "very_low"
        risk_level = "critical"
        recommendation = "Con el flujo actual, la meta no es alcanzable sin cambios fuertes."

    return {
        "goal": goal,
        "available_cash": available_cash,
        "remaining_amount": remaining_amount,
        "monthly_required": monthly_required,
        "monthly_gap": monthly_gap,
        "probability": probability,
        "risk_level": risk_level,
        "recommendation": recommendation,
        "solution_options": build_goal_solution_options(
            goal=goal,
            available_cash=available_cash,
            monthly_required=monthly_required
        )
    }


def analyze_goal_by_id(goal_id: int):
    goal = get_financial_goal(goal_id)

    if goal.get("status") == "ERROR":
        return goal

    return analyze_goal(goal)


def analyze_all_goals():
    goals = get_financial_goals()

    return [
        analyze_goal(goal)
        for goal in goals
    ]