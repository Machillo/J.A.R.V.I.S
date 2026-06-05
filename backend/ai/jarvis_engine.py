from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from backend.ai.action_flow import continue_pending_action, start_action
from backend.ai.gemini_client import ask_gemini
from backend.ai.intent_router import ACTION_TYPES, detect_intent
from backend.ai.response_formatter import format_jarvis_response
from backend.ai.web_access import internet_search, should_use_internet
from backend.ai.preferences import update_sports_preferences, get_sports_preferences
from backend.core.events import add_event

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



def _extract_simple_date(message: str) -> str | None:
    text = message.lower()
    today = datetime.now().date()

    if "mañana" in text or "manana" in text:
        return (today + timedelta(days=1)).isoformat()

    iso = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", text)
    if iso:
        year, month, day = map(int, iso.groups())
        return datetime(year, month, day).date().isoformat()

    slash = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](20\d{2}))?\b", text)
    if slash:
        day, month, year = slash.groups()
        year = int(year or today.year)
        return datetime(year, int(month), int(day)).date().isoformat()

    months = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
        "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
        "noviembre": 11, "diciembre": 12,
    }
    for name, month in months.items():
        match = re.search(rf"\b(\d{{1,2}}) de {name}(?: de (20\d{{2}}))?", text)
        if match:
            day = int(match.group(1))
            year = int(match.group(2) or today.year)
            return datetime(year, month, day).date().isoformat()

    return None


def _looks_like_calendar_request(message: str) -> bool:
    text = message.lower()
    return any(phrase in text for phrase in [
        "tengo un compromiso", "tengo una cita", "recordame", "recuérdame", "agend",
        "calendario", "notificame", "notifícame", "evento", "reunion", "reunión",
    ])


def _create_calendar_event_from_message(message: str) -> dict:
    event_date = _extract_simple_date(message)
    if not event_date:
        return {
            "message": "Señor, ¿para qué fecha lo agendo? Puedes decírmelo como 2026-06-15 o 15/06/2026.",
            "intent": "create_calendar_event",
            "status": "NEEDS_DATE",
            "pending": False,
        }

    clean_title = message.strip()
    clean_title = re.sub(r"(?i)jarvis|recu[eé]rdame|recordame|agend(a|e|ame)|tengo un compromiso|tengo una cita|notificame|notifícame", "", clean_title).strip(" ,.-")
    title = clean_title[:90] or "Compromiso"
    event = add_event(title=title, event_date=event_date, event_type="personal", description=message)
    return {
        "message": f"Señor, compromiso guardado para el {event_date}: {title}.",
        "intent": "create_calendar_event",
        "status": "OK",
        "pending": False,
        "data": event,
    }


def _looks_like_sports_preferences(message: str) -> bool:
    text = message.lower()
    return any(word in text for word in ["equipo favorito", "equipos favoritos", "f1", "formula 1", "fórmula 1", "ufc", "champions", "mundial de clubes"] )


def _handle_sports_preferences(message: str) -> dict | None:
    text = message.lower()
    if "equipo" not in text and "f1" not in text and "ufc" not in text and "champions" not in text:
        return None

    prefs = get_sports_preferences()
    teams = prefs.get("football", {}).get("teams", [])
    possible_team = re.search(r"(?:mi equipo favorito es|mis equipos favoritos son|sigo a|equipo:|equipos:)(.+)", message, re.I)
    if possible_team:
        raw = possible_team.group(1)
        new_teams = [item.strip(" .") for item in re.split(r",| y ", raw) if item.strip()]
        teams = sorted(set(teams + new_teams))
        update_sports_preferences({"football": {"teams": teams}})
        return {
            "message": f"Señor, guardé tus equipos favoritos: {', '.join(teams)}.",
            "intent": "sports_preferences",
            "status": "OK",
            "pending": False,
            "data": {"teams": teams},
        }

    if "f1" in text or "formula" in text or "fórmula" in text:
        update_sports_preferences({"f1": True})
        return {"message": "Señor, dejaré Fórmula 1 activa para recordarte prácticas importantes, clasificación, sprint y carrera cuando conectemos calendarios deportivos.", "intent": "sports_preferences", "status": "OK", "pending": False}

    if "ufc" in text:
        update_sports_preferences({"ufc": True})
        return {"message": "Señor, dejaré UFC activo para recordarte carteleras y peleas importantes cuando conectemos el calendario deportivo.", "intent": "sports_preferences", "status": "OK", "pending": False}

    return None

def process_message(user_message: str):
    if should_use_internet(user_message):
        return internet_search(user_message)

    if _looks_like_calendar_request(user_message):
        return _create_calendar_event_from_message(user_message)

    sports_result = _handle_sports_preferences(user_message)
    if sports_result:
        return sports_result

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
