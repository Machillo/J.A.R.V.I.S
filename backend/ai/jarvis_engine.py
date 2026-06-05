from __future__ import annotations

import json

from backend.ai.action_flow import continue_pending_action, start_action
from backend.ai.gemini_client import ask_gemini
from backend.ai.intent_router import ACTION_TYPES, detect_intent
from backend.ai.response_formatter import format_jarvis_response
from backend.integrations.internet_search import internet_search
from backend.tasks.calendar_service import calendar_summary, create_calendar_event_from_text
from backend.sports.service import get_sports_calendar_summary

from backend.finance.service import (
    get_debts,
    get_financial_summary,
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

from backend.transactions.analyzer import get_transaction_analysis


def _safe_call(fn, fallback):
    try:
        return fn()
    except Exception as exc:
        return {"error": str(exc), "fallback": fallback}


def build_financial_context() -> dict:
    """Contexto real que Gemini puede usar sin inventar datos."""
    return {
        "financial_summary": _safe_call(get_financial_summary, {}),
        "net_worth": _safe_call(get_net_worth_report, {}),
        "debts": _safe_call(get_debts, []),
        "transactions": _safe_call(get_transaction_analysis, {}),
    }


def answer_with_context(user_message: str, intent_result: dict):
    context = build_financial_context()

    prompt = f"""
Eres J.A.R.V.I.S., asistente financiero privado.

Objetivo:
- Analiza la pregunta del usuario.
- Si la respuesta está en los datos reales del sistema, responde usando SOLO esos datos.
- Si no está en los datos, dilo claramente y sugiere qué dato falta registrar.
- No inventes montos, deudas, fechas, ingresos ni categorías.
- Responde en español, breve, claro y útil.
- No muestres JSON.
- No digas que eres Gemini.

Pregunta del usuario:
{user_message}

Intento detectado:
{json.dumps(intent_result, ensure_ascii=False)}

Datos reales disponibles en J.A.R.V.I.S.:
{json.dumps(context, ensure_ascii=False, indent=2)}
"""

    ai_response = ask_gemini(prompt, route="jarvis_context_answer")

    if ai_response["status"] != "OK":
        return {
            "message": "Señor, tengo los datos cargados, pero la IA no pudo generar la respuesta en este momento.",
            "intent": intent_result.get("intent", "context_answer"),
            "status": "AI_ERROR",
            "pending": False,
            "data": context,
        }

    return {
        "message": ai_response["text"].strip(),
        "intent": intent_result.get("intent", "context_answer"),
        "entity": intent_result.get("entity"),
        "confidence": intent_result.get("confidence", 0),
        "source": "gemini_with_jarvis_context",
        "pending": False,
        "status": "OK",
        "usage": ai_response.get("usage"),
        "data": context,
    }


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

    # Internet explícito: solo owner y nunca se mezcla con el motor financiero.
    if intent == "internet_search":
        search_result = internet_search(entity or user_message)
        if search_result.get("status") == "OK":
            results = search_result.get("results", [])
            if not results:
                message = "Señor, busqué en internet pero no encontré resultados claros."
            else:
                lines = ["Señor, encontré esto en internet:"]
                for index, item in enumerate(results[:4], start=1):
                    title = item.get("title") or "Resultado"
                    snippet = item.get("snippet") or ""
                    link = item.get("link") or ""
                    lines.append(f"{index}. {title}\n{snippet}\n{link}")
                message = "\n\n".join(lines)
        else:
            message = search_result.get("message", "Señor, no pude realizar la búsqueda en internet.")

        return {
            "message": message,
            "intent": "internet_search",
            "status": search_result.get("status", "OK"),
            "pending": False,
            "data": search_result,
        }

    # Calendario: se guarda en events y no debe caer en deuda/ahorro/gastos.
    if intent == "create_calendar_event":
        calendar_result = create_calendar_event_from_text(entity or user_message)
        return {
            "message": calendar_result.get("message"),
            "intent": "create_calendar_event",
            "status": calendar_result.get("status", "OK"),
            "pending": calendar_result.get("pending", False),
            "data": calendar_result,
        }

    if intent == "calendar_summary":
        result = calendar_summary()
        events = result.get("events", [])
        if events:
            event_lines = [f"- {event.get('event_date')}: {event.get('title')}" for event in events[:10]]
            message = result.get("message") + "\n" + "\n".join(event_lines)
        else:
            message = result.get("message")
        return {
            "message": message,
            "intent": "calendar_summary",
            "status": "OK",
            "pending": False,
            "data": result,
        }

    # Deportes: usa internet real con SERPER/TAVILY, pero solo cuando se pide o se actualiza radar deportivo.
    if intent == "sports_schedule":
        result = get_sports_calendar_summary(entity or "all")
        return {
            "message": result.get("message"),
            "intent": "sports_schedule",
            "status": result.get("status", "OK"),
            "pending": False,
            "data": result,
        }

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
        return answer_with_context(user_message, intent_result)

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
