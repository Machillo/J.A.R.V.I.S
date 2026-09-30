from __future__ import annotations

import logging
import re

from backend.ai.action_flow import (
    CLARIFY_ANSWER,
    CLARIFY_FIELD,
    CLARIFY_OTHER,
    DIRECT_MARK,
    continue_pending_action,
    hold_for_clarification,
    pending_prompt,
    release_clarification,
    start_action,
)
from backend.ai.chat_memory import PendingActionKept, finish_pending_action, get_pending_action, keep_pending_action
from backend.ai.intent_router import YES_NO_WORDS, detect_intent, is_explicit_calendar_command, normalize_message
from backend.tasks.calendar_service import calendar_summary, parse_calendar_event
from backend.finance.service import preview_payroll_event
from backend.ai.strategy_dashboard import build_local_strategy_blueprint

logger = logging.getLogger(__name__)

# JARVIS Chat's scope (Owner decision, J2): quick payroll records (OT, VGH, holidays and bonuses,
# the historical parsing and amounts) and the agenda (create an event, "¿qué tengo?"). Every change
# is shown first and saved only on "sí" (J1). The travel, purchase, goal, debt, strategy, finance,
# sports, memory, search and other engines stay in the backend for their own modules and endpoints;
# the chat no longer answers with them.
CHAT_PAYROLL_ACTIONS = {"create_payroll_event", "create_bonus"}
CHAT_ACTIONS = CHAT_PAYROLL_ACTIONS | {"create_calendar_event"}
OUT_OF_SCOPE_MESSAGE = (
    "Señor, eso no está disponible en JARVIS Chat. Aquí registro horas extra, VGH, feriados y bonos, "
    "y manejo su agenda: agendar eventos y ver qué tiene próximo."
)
DROPPED_PENDING_MESSAGE = "Señor, cancelé un registro pendiente que JARVIS Chat ya no maneja. No guardé nada."


def answer_with_context(user_message: str, intent_result: dict):
    """The answer to anything outside JARVIS Chat's scope (payroll records and the agenda).

    DINCR Owner has no generative-AI assistant: no financial context is built, no other engine
    runs and nothing is sent to an AI provider.
    """
    return {
        "message": OUT_OF_SCOPE_MESSAGE,
        "intent": intent_result.get("intent", "context_answer"),
        "status": "UNSUPPORTED",
        "pending": False,
        "source": "deterministic",
    }


def _money(value) -> str:
    try:
        return f"₡{float(value or 0):,.0f}".replace(",", ".")
    except Exception:
        return "₡0"



def _parse_direct_payroll_or_bonus(user_message: str) -> dict | None:
    """Ruta local segura para OT, VGH, feriados y bonos.

    No depende de GPT. Si el usuario informa algo ya ocurrido y viene claro,
    Jarvis lo guarda directo para que la estrategia se recalculue con datos reales.
    """
    text = user_message.lower()

    def parse_number(raw: str) -> float | None:
        raw = raw.strip().lower()
        is_mil = raw.endswith("mil")
        raw = raw.replace("mil", "").strip()
        if "," in raw and "." in raw:
            raw = raw.replace(",", "") if raw.rfind(".") > raw.rfind(",") else raw.replace(".", "").replace(",", ".")
        elif "," in raw:
            after = raw.split(",")[-1]
            raw = raw.replace(",", ".") if len(after) in {1, 2} else raw.replace(",", "")
        elif "." in raw:
            parts = raw.split(".")
            if len(parts) > 2 or (len(parts[-1]) == 3 and len(parts[0]) <= 3):
                raw = raw.replace(".", "")
        try:
            val = float(raw)
        except ValueError:
            return None
        return val * 1000 if is_mil else val

    bonus_match = re.search(r"(?:bono|bonus).*?(\d+(?:[.,]\d+)*\s*(?:mil)?)|(?:(\d+(?:[.,]\d+)*\s*(?:mil)?)\s*(?:de\s*)?(?:bono|bonus))", text)
    if bonus_match:
        amount_text = next((g for g in bonus_match.groups() if g), "")
        amount = parse_number(amount_text)
        if amount and amount > 0:
            return {
                "action_type": "create_bonus",
                "payload": {"amount": amount, "description": "Bono registrado por chat"},
            }

    event_type = None
    if re.search(r"\b(vgh|horas?\s+libres?|no\s+pagad[ao]s?)\b", text):
        event_type = "vgh"
    elif "feriado" in text:
        event_type = "holiday"
    elif re.search(r"\b(ot|extra|extras|tiempo\s+extra|horas?\s+extra)\b", text):
        event_type = "ot"

    if event_type:
        hmatch = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:h|hr|hrs|hora|horas)\b", text)
        if not hmatch:
            hmatch = re.search(r"\b(\d+(?:[.,]\d+)?)\b", text)
        if hmatch:
            hours = parse_number(hmatch.group(1))
            if hours and 0 < hours <= 24:
                return {
                    "action_type": "create_payroll_event",
                    "payload": {"event_type": event_type, "hours": hours, "description": "Evento de planilla registrado por chat"},
                }
    return None

def _director_strategy_message(blueprint: dict) -> str:
    allocation = blueprint.get("allocation") or {}
    timeline = blueprint.get("timeline") or []
    first = timeline[0] if timeline else {}
    months = blueprint.get("estimated_total_months") or 0
    base_months = blueprint.get("base_estimated_total_months") or months
    saved = blueprint.get("months_saved_by_current_extras") or 0
    income = blueprint.get("monthly_income") or 0
    recurring_income = blueprint.get("recurring_monthly_income") or income
    one_time = blueprint.get("current_month_one_time_debt_boost") or 0
    debt = blueprint.get("total_debt") or 0
    lines = [
        "Señor, estrategia financiera calculada con los datos actuales.",
        f"Estrategia: {blueprint.get('title') or 'Plan financiero'}.",
        f"Ingreso base recurrente: {_money(recurring_income)}. Ingreso de este mes: {_money(income)}. Deuda actual: {_money(debt)}.",
    ]
    if first:
        lines.append(f"Primera deuda a atacar: {first.get('name')} con pago objetivo de este mes de {_money(first.get('recommended_payment'))}.")
    if base_months:
        if one_time > 0 and months and months != base_months:
            lines.append(f"Escenario base sin extras futuros: {base_months} meses. Con extras únicos de este mes: {months} meses. Ahorro estimado: {saved} meses.")
        else:
            lines.append(f"Tiempo estimado para quedar libre de deudas: {base_months} meses, recalculable cada mes.")
    if allocation:
        labels = {
            "ataque_de_deuda": "Ataque de deuda",
            "vida_controlada": "Vida controlada",
            "fondo_de_emergencia": "Salvavidas",
            "metas_o_inversion": "Metas o inversión",
        }
        amounts = blueprint.get("allocation_amounts") or {}
        dist = ", ".join(
            f"{labels.get(k, k)} {v}% ({_money(amounts.get(k, 0))})"
            for k, v in allocation.items()
        )
        lines.append(f"Distribución del sobrante real de este ciclo: {dist}.")
    lines.append("Regla: OT, bono y feriados solo aceleran el mes actual; no se asumen como ingresos permanentes.")
    if recurring_income <= 0:
        lines.append("Pendiente crítico: configurar salario base mensual para aumentar precisión.")
    return "\n".join(lines)


def create_initial_financial_strategy():
    """Return the live deterministic strategy without AI or saved guide overrides."""
    blueprint = build_local_strategy_blueprint()
    return {
        "status": "OK",
        "message": _director_strategy_message(blueprint),
        "data": {"strategy": blueprint},
        "source": "live_database",
    }


def _confirm_first(action_type: str, user_message: str, payload: dict, *, intent: str, source: str | None = None) -> dict:
    """A change the chat understood: show what will be saved and wait for "sí" (action_flow)."""
    action_result = start_action(action_type, user_message, prefill_payload=payload)
    response = {
        "message": action_result["message"],
        "intent": intent,
        "action_type": action_type,
        "status": action_result.get("status", "PENDING"),
        "pending": action_result.get("pending", True),
        "data": action_result.get("data"),
    }
    if source:
        response["source"] = source
    return response


def _pending_response(result: dict) -> dict:
    return {
        "message": result["message"],
        "intent": "pending_action",
        "action_type": result.get("action_type"),
        "status": result.get("status", "OK"),
        "pending": result.get("pending", False),
        "data": result.get("data"),
    }


def _is_ambiguous(intent_result: dict, user_message: str) -> bool:
    """A message waiting to fill a pending field that the router also reads as its own request
    ("Fondo de emergencia", "septiembre", "estrategia"): JARVIS cannot know which one was meant."""
    if normalize_message(user_message) in YES_NO_WORDS:
        return False
    return intent_result.get("intent") not in {"general", "unknown"}


def _resolve_clarification(action: dict, user_message: str) -> dict:
    """The Owner said whether the held message answers the pending action or is another request."""
    held, restored = release_clarification(action)
    choice = normalize_message(user_message)
    if choice == CLARIFY_ANSWER:
        # The held text, exactly as written, answers the field; the historical flow continues.
        result = continue_pending_action(held)
        return _pending_response(result) if result else _process(held, None)
    if choice == CLARIFY_OTHER:
        # Answered as a normal request; the pending action stays exactly where it was.
        with keep_pending_action():
            try:
                response = dict(_process(held, None))
            except PendingActionKept:
                response = {
                    "message": "Señor, primero terminemos o cancelemos lo pendiente antes de registrar algo nuevo.",
                    "intent": "pending_action",
                    "status": "BLOCKED",
                    "pending": False,
                    "data": None,
                }
        response["message"] = f"{response.get('message') or ''}\n\n{pending_prompt(restored)} Podés responderla o decir «cancelar»."
        response["pending"] = True
        response["pending_action"] = {"action_type": restored.get("action_type"), "current_field": restored.get("current_field")}
        return response
    # Anything else: the question is set aside and the message goes against the pending action as usual.
    return _process(user_message, restored)


def process_message(user_message: str):
    pending_action = get_pending_action()
    if pending_action and pending_action.get("action_type") not in CHAT_ACTIONS:
        # Left from before the chat's scope was reduced (a goal, a debt, a travel decision…):
        # it is never continued or saved from the chat.
        finish_pending_action(pending_action["id"], "cancelled")
        response = dict(_process(user_message, None))
        response["message"] = f"{DROPPED_PENDING_MESSAGE}\n\n{response.get('message') or ''}"
        return response
    if pending_action and pending_action.get("current_field") == CLARIFY_FIELD:
        return _resolve_clarification(pending_action, user_message)
    return _process(user_message, pending_action)


def _calendar_event(user_message: str, text: str) -> dict:
    parsed = parse_calendar_event(text)
    if parsed["status"] != "READY":
        return {
            "message": parsed.get("message"),
            "intent": "create_calendar_event",
            "status": parsed.get("status", "OK"),
            "pending": parsed.get("pending", False),
            "data": parsed,
        }
    payload = {"title": parsed["title"], "event_date": parsed["event_date"], "description": parsed["description"]}
    return _confirm_first("create_calendar_event", user_message, payload, intent="create_calendar_event")


def _calendar_summary_answer() -> dict:
    result = calendar_summary()
    events = result.get("events", [])
    if events:
        event_lines = [f"- {event.get('event_date')}: {event.get('title')}" for event in events[:10]]
        message = result.get("message") + "\n" + "\n".join(event_lines)
    else:
        message = result.get("message")
    return {"message": message, "intent": "calendar_summary", "status": "OK", "pending": False, "data": result}


def _direct_payroll_answer(user_message: str, direct_payroll: dict) -> dict:
    # Same interpretation as always (OT, VGH, holiday, bonus); the change is shown with its amount
    # and saved only on "sí" (action_flow), with the historical reply.
    action_type = direct_payroll["action_type"]
    payload = {**direct_payroll["payload"], DIRECT_MARK: True}
    if action_type == "create_payroll_event":
        preview = preview_payroll_event(payload["event_type"], payload["hours"])
        if preview.get("status") != "OK":
            return {
                "message": f"Señor, no puedo registrar ese evento: {preview.get('message', 'no pude calcularlo')}",
                "intent": action_type,
                "action_type": action_type,
                "status": "ERROR",
                "pending": False,
                "source": "local_direct_payroll_guard",
                "data": preview,
            }
    return _confirm_first(action_type, user_message, payload, intent=action_type, source="local_direct_payroll_guard")


def _process(user_message: str, pending_action: dict | None):
    intent_result = detect_intent(user_message)

    # With a pending action, a message that the router also reads as its own request is neither
    # saved as the answer nor cancels the action: JARVIS asks which one it is (J1).
    if pending_action and _is_ambiguous(intent_result, user_message):
        return _pending_response(hold_for_clarification(pending_action, user_message))
    if pending_action:
        pending_result = continue_pending_action(user_message)
        if pending_result:
            return _pending_response(pending_result)

    # 1. An explicit agenda order ("Agendá el viaje a Ecuador el 11 de octubre") is an event,
    #    whatever it is about: a trip, a purchase, a card, a race.
    if is_explicit_calendar_command(user_message):
        return _calendar_event(user_message, user_message)

    # 2. Quick payroll records: OT, VGH, holidays and bonuses in plain words.
    direct_payroll = _parse_direct_payroll_or_bonus(user_message)
    if direct_payroll:
        return _direct_payroll_answer(user_message, direct_payroll)

    # 3. The router's agenda and payroll intents; anything else is outside the chat.
    intent = intent_result.get("intent", "unknown")
    if intent == "create_calendar_event":
        return _calendar_event(user_message, intent_result.get("entity") or user_message)
    if intent == "calendar_summary":
        return _calendar_summary_answer()
    selected_action = intent_result.get("action_type") or intent
    if selected_action in CHAT_PAYROLL_ACTIONS:
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
    return answer_with_context(user_message, intent_result)
