from backend.ai.intent_router import detect_intent
from backend.ai.response_formatter import format_jarvis_response

from backend.finance.service import (
    get_net_worth_report,
    get_user_status,
    get_debts,
)

from backend.goals.service import (
    get_financial_goal_by_name,
)

from backend.advisor.service import (
    get_financial_advice,
    analyze_spending_habits,
)


def process_message(user_message: str):
    intent_result = detect_intent(user_message)

    intent = intent_result.get("intent", "unknown")
    entity = intent_result.get("entity")

    data = {}

    if intent == "highest_debt":
        debts = get_debts()
        highest_debt = None

        if debts:
            highest_debt = max(
                debts,
                key=lambda debt: debt["remaining_amount"]
            )

        data = {
            "debt": highest_debt,
            "debts_count": len(debts)
        }

    elif intent == "debt_summary":
        debts = get_debts()

        total_debt = sum(
            debt["remaining_amount"]
            for debt in debts
        )

        monthly_payments = sum(
            debt["monthly_payment"]
            for debt in debts
        )

        data = {
            "debts": debts,
            "total_debt": total_debt,
            "monthly_payments": monthly_payments
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
                "message": "No se indicó una meta específica."
            }

        data = {
            "goal": goal
        }

    elif intent == "spending_habits":
        data = analyze_spending_habits()

    elif intent == "advisor_summary":
        data = get_financial_advice()

    else:
        return {
            "message": (
                "Señor, todavía no tengo una acción clara para esa solicitud. "
                "Puedo ayudarle con deudas, metas, patrimonio, estado financiero y hábitos de gasto."
            ),
            "intent": intent,
            "entity": entity,
            "confidence": intent_result.get("confidence", 0),
            "source": intent_result.get("source")
        }

    message = format_jarvis_response(
        user_message=user_message,
        intent=intent,
        data=data
    )

    return {
        "message": message,
        "intent": intent,
        "entity": entity,
        "confidence": intent_result.get("confidence", 0),
        "source": intent_result.get("source"),
        "data": data
    }