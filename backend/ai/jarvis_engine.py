from __future__ import annotations

import json

from backend.ai.action_flow import continue_pending_action, start_action
from backend.ai.chat_memory import finish_pending_action, get_pending_action
from backend.ai.gemini_client import ask_gemini
from backend.ai.intent_router import ACTION_TYPES, detect_intent, is_pending_interrupt
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

from backend.goals.service import get_financial_goal_by_name
from backend.advisor.service import analyze_spending_habits, get_financial_advice
from backend.transactions.analyzer import get_transaction_analysis


def _safe_call(fn, fallback):
    try:
        return fn()
    except Exception as exc:
        return {"error": str(exc), "fallback": fallback}


def build_financial_context() -> dict:
    return {
        "financial_summary": _safe_call(get_financial_summary, {}),
        "net_worth": _safe_call(get_net_worth_report, {}),
        "debts": _safe_call(get_debts, []),
        "transactions": _safe_call(get_transaction_analysis, {}),
    }


def _internet_answer(user_message: str, query: str) -> dict:
    search_result = internet_search(query)
    if search_result.get("status") != "OK":
        return {
            "message": search_result.get("message", "Señor, no pude realizar la búsqueda en internet."),
            "intent": "internet_search",
            "status": search_result.get("status", "ERROR"),
            "pending": False,
            "data": search_result,
        }

    results = search_result.get("results", [])[:5]
    if not results:
        message = "Señor, busqué en internet pero no encontré resultados claros."
    else:
        prompt = f"""
Eres J.A.R.V.I.S. Responde SOLO lo que el usuario pidió, breve y útil.
No hagas resumen gigante. Usa los resultados de internet, sin inventar.
Si no hay certeza, dilo.

Pregunta del usuario: {user_message}
Consulta usada: {query}
Resultados:
{json.dumps(results, ensure_ascii=False, indent=2)}

Formato recomendado: 1 a 3 frases y, si aplica, una fuente corta.
"""
        ai = ask_gemini(prompt, route="internet_answer")
        if ai.get("status") == "OK" and (ai.get("text") or "").strip():
            message = ai["text"].strip()
        else:
            first = results[0]
            title = first.get("title") or "Resultado"
            snippet = first.get("snippet") or ""
            link = first.get("link") or ""
            message = f"Señor, encontré esto: {title}. {snippet}\n{link}".strip()

    return {
        "message": message,
        "intent": "internet_search",
        "status": "OK",
        "pending": False,
        "data": search_result,
    }


def answer_with_context(user_message: str, intent_result: dict):
    context = build_financial_context()
    prompt = f"""
Eres J.A.R.V.I.S., asistente financiero privado.

Responde en español, breve, claro y útil.
Usa SOLO los datos reales si la pregunta es financiera.
Si no hay datos suficientes, dilo y pide el dato que falta.
No inventes montos, fechas, deudas ni categorías.

Pregunta: {user_message}
Intento detectado: {json.dumps(intent_result, ensure_ascii=False)}
Datos reales: {json.dumps(context, ensure_ascii=False, indent=2)}
"""
    ai_response = ask_gemini(prompt, route="jarvis_context_answer")
    if ai_response.get("status") != "OK":
        return {
            "message": "Señor, tengo el contexto cargado, pero la IA no pudo generar respuesta en este momento.",
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
    intent_result = detect_intent(user_message)

    # Si hay una acción pendiente, primero verificamos si el usuario está cambiando de tema.
    # Esto evita que "busca Chimborazo" termine guardado como categoría o gasto.
    pending_action = get_pending_action()
    if pending_action and is_pending_interrupt(intent_result, user_message):
        finish_pending_action(pending_action["id"], "cancelled")
    elif pending_action:
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

    intent = intent_result.get("intent", "unknown")
    action_type = intent_result.get("action_type")
    entity = intent_result.get("entity")

    if intent == "internet_search":
        query = entity if isinstance(entity, str) and entity.strip() else user_message
        return _internet_answer(user_message, query)

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
        return {"message": message, "intent": "calendar_summary", "status": "OK", "pending": False, "data": result}

    if intent == "sports_schedule":
        result = get_sports_calendar_summary(entity or {"scope": "all", "query_type": "next", "query": user_message})
        return {
            "message": result.get("message"),
            "intent": "sports_schedule",
            "status": result.get("status", "OK"),
            "pending": False,
            "data": result,
        }

    if intent in {"email", "memory", "fixed_expense"}:
        labels = {
            "email": "lectura de correos",
            "memory": "memoria",
            "fixed_expense": "gastos fijos",
        }
        return {
            "message": f"Señor, detecté que esto corresponde a {labels[intent]}. Esa sección ya está identificada para la siguiente fase, pero todavía no está activa al 100%.",
            "intent": intent,
            "status": "NOT_READY",
            "pending": False,
            "data": {"intent_result": intent_result},
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
        data = {"debts": debts, "total_debt": total_debt, "monthly_payments": monthly_payments}
    elif intent == "net_worth":
        data = get_net_worth_report()
    elif intent == "user_status":
        data = get_user_status()
    elif intent == "goal_status":
        goal = get_financial_goal_by_name(entity) if entity else {"status": "ERROR", "message": "No se indicó una meta específica."}
        data = {"goal": goal}
    elif intent == "spending_habits":
        data = analyze_spending_habits()
    elif intent == "advisor_summary":
        data = get_financial_advice()
    else:
        return answer_with_context(user_message, intent_result)

    message = format_jarvis_response(user_message=user_message, intent=intent, data=data)
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
