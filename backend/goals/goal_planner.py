from backend.goals.goal_analyzer import analyze_goal_by_id, analyze_goal
from backend.goals.service import get_financial_goal_by_name


def generate_goal_plan(goal_id: int):
    analysis = analyze_goal_by_id(goal_id)

    if analysis.get("status") == "ERROR":
        return analysis

    goal = analysis["goal"]

    available_cash = analysis["available_cash"]
    monthly_required = analysis["monthly_required"]
    monthly_gap = analysis["monthly_gap"]

    actions = []

    if monthly_gap >= 0:
        actions.append(
            f"Aportar ₡{monthly_required:,.2f} por mes."
        )

        if monthly_gap > 0:
            actions.append(
                f"Después de cubrir la meta quedarían ₡{monthly_gap:,.2f} libres cada mes."
            )

    else:
        deficit = abs(monthly_gap)

        actions.append(
            f"Aportar los ₡{available_cash:,.2f} disponibles cada mes."
        )

        actions.append(
            f"Generar aproximadamente ₡{deficit:,.2f} adicionales por mes."
        )

        if goal["priority"] == "critical":
            actions.append(
                "Priorizar esta meta sobre pagos extraordinarios de deuda."
            )

        actions.append(
            "Si la diferencia persiste cerca de la fecha objetivo, evaluar financiamiento."
        )

    probability_scores = {
        "completed": 100,
        "high": 85,
        "medium": 65,
        "low": 40,
        "very_low": 15
    }

    probability_percent = probability_scores.get(
        analysis["probability"],
        50
    )

    return {
        "goal_id": goal["id"],
        "goal_name": goal["name"],
        "target_amount": goal["target_amount"],
        "remaining_amount": goal["remaining_amount"],
        "target_date": goal["target_date"],
        "probability": analysis["probability"],
        "probability_percent": probability_percent,
        "risk_level": analysis["risk_level"],
        "recommended_actions": actions,
        "analysis": analysis
    }

def generate_goal_plan_by_name(name: str):
    goal = get_financial_goal_by_name(name)

    if goal.get("status") == "ERROR":
        return goal

    analysis = analyze_goal(goal)

    goal = analysis["goal"]

    available_cash = analysis["available_cash"]
    monthly_required = analysis["monthly_required"]
    monthly_gap = analysis["monthly_gap"]

    actions = []

    if monthly_gap >= 0:
        actions.append(
            f"Aportar ₡{monthly_required:,.2f} por mes."
        )

        if monthly_gap > 0:
            actions.append(
                f"Después de cubrir la meta quedarían ₡{monthly_gap:,.2f} libres cada mes."
            )
    else:
        deficit = abs(monthly_gap)

        actions.append(
            f"Aportar los ₡{available_cash:,.2f} disponibles cada mes."
        )

        actions.append(
            f"Generar aproximadamente ₡{deficit:,.2f} adicionales por mes."
        )

        if goal["priority"] == "critical":
            actions.append(
                "Priorizar esta meta sobre pagos extraordinarios de deuda."
            )

        actions.append(
            "Si la diferencia persiste cerca de la fecha objetivo, evaluar financiamiento."
        )

    probability_scores = {
        "completed": 100,
        "high": 85,
        "medium": 65,
        "low": 40,
        "very_low": 15
    }

    probability_percent = probability_scores.get(
        analysis["probability"],
        50
    )

    return {
        "goal_id": goal["id"],
        "goal_name": goal["name"],
        "target_amount": goal["target_amount"],
        "remaining_amount": goal["remaining_amount"],
        "target_date": goal["target_date"],
        "probability": analysis["probability"],
        "probability_percent": probability_percent,
        "risk_level": analysis["risk_level"],
        "recommended_actions": actions,
        "analysis": analysis
    }