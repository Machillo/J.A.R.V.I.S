from backend.ai.action_flow import continue_pending_action, start_action
from backend.ai.intent_router import ACTION_TYPES, detect_intent
from backend.ai.response_formatter import format_jarvis_response

from backend.finance.service import (
    get_debts,
    get_net_worth_report,
    get_user_status,
)

from backend.goals.service import (
    get_financial_goal_by_name,
)

from backend.advisor.service import (
    analyze_spending_habits,
    get_financial_advice,
)


def process_message(user_message: str):
    pending_result = continue_pending_action(user_message)
    if pending_result:
        return {
            "message": pending_result["message"],
            "intent": "pending_action",
            "action_type": pending_result.get("action_type"),
            "status": pending_result.get("status", "OK"),
            "pending": pending_result.get("pending", False),
            "data": pending_result.get("data"),
        }

    intent_result = detect_intent(user_message)

    intent = intent_result.get("intent", "unknown")
    action_type = intent_result.get("action_type")
    entity = intent_result.get("entity")

    if action_type in ACTION_TYPES or intent in ACTION_TYPES:
        selected_action = action_type or intent
        action_result = start_action(selected_action, user_message)
        return {
            "message": action_result["message"],
            "intent": selected_action,
            "action_type": selected_action,
            "status": action_result.get("status", "PENDING"),
            "pending": action_result.get("pending", True),
            "confidence": intent_result.get("confidence", 0),
            "source": intent_result.get("source"),
            "data": action_result.get("data"),
        }

    data = {}

    if intent == "highest_debt":
        debts = get_debts()
        highest_debt = max(debts, key=lambda debt: debt["remaining_amount"]) if debts else None
        data = {"debt": highest_debt, "debts_count": len(debts)}

    elif intent == "lowest_debt":
        debts = get_debts()
        lowest_debt = min(debts, key=lambda debt: debt["remaining_amount"]) if debts else None
        data = {"debt": lowest_debt, "debts_count": len(debts)}

    elif intent == "debt_summary":
        debts = get_debts()
        total_debt = sum(debt["remaining_amount"] for debt in debts)
        monthly_payments = sum(debt["monthly_payment"] for debt in debts)
        data = {
            "debts": debts,
            "total_debt": total_debt,
            "monthly_payments": monthly_payments,
        }

    elif intent == "net_worth":
        data = get_net_worth_report()

    elif intent == "user_status":
        data = get_user_status()

    elif intent == "goal_status":
        if entity:
            goal = get_financial_goal_by_name(entity)
        else:
            goal = {
                "status": "ERROR",
                "message": "No se indicó una meta específica.",
            }
        data = {"goal": goal}

    elif intent == "spending_habits":
        data = analyze_spending_habits()

    elif intent == "advisor_summary":
        data = get_financial_advice()

    else:
        return {
            "message": (
                "Señor, todavía no tengo una acción clara para esa solicitud. "
                "Puedo consultar deudas, metas, patrimonio y también registrar datos como deudas, gastos, ingresos, ahorros, inversiones y metas."
            ),
            "intent": intent,
            "entity": entity,
            "confidence": intent_result.get("confidence", 0),
            "source": intent_result.get("source"),
            "pending": False,
            "status": "UNKNOWN",
        }

    message = format_jarvis_response(
        user_message=user_message,
        intent=intent,
        data=data,
    )

    return {
        "message": message,
        "intent": intent,
        "entity": entity,
        "confidence": intent_result.get("confidence", 0),
        "source": intent_result.get("source"),
        "pending": False,
        "status": "OK",
        "data": data,
    }
