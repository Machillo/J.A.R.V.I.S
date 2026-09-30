from __future__ import annotations

import logging
import re

from backend.ai.action_flow import DIRECT_MARK, continue_pending_action, start_action
from backend.ai.chat_memory import finish_pending_action, get_pending_action
from backend.ai.intent_router import ACTION_TYPES, detect_intent, is_pending_interrupt
from backend.ai.memory_service import memory_content_from_message, search_memory_items
from backend.ai.response_formatter import format_jarvis_response
from backend.integrations.internet_search import internet_search
from backend.tasks.calendar_service import calendar_summary, parse_calendar_event
from backend.sports.service import get_sports_calendar_summary

from backend.finance.service import (
    get_debts,
    get_net_worth_report,
    get_user_status,
    preview_payroll_event,
)

from backend.goals.service import get_financial_goal_by_name
from backend.advisor.service import analyze_spending_habits, get_financial_advice
from backend.finance.strategic_engine import get_financial_engine_report, simulate_what_if
from backend.finance.intelligence import plan_long_term_goal, get_debt_advisory
from backend.finance.fixed_expenses import plan_fixed_expense_message
from backend.ai.strategy_dashboard import build_local_strategy_blueprint

logger = logging.getLogger(__name__)
from backend.ai.decision_engine import handle_decision_pending_action, handle_personal_decision_request


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
    """Fallback for messages without a deterministic handler.

    DINCR Owner no longer has a generative-AI assistant: no financial context
    is built and nothing is sent to an AI provider.
    """
    return {
        "message": "Señor, no tengo una respuesta calculada para eso. Consultá Finanzas o Estrategia.",
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


def _extract_simulation_payload(user_message: str) -> dict:
    import re
    text = user_message.lower()
    currency = "CRC"
    exchange_rate = 1.0

    usd_match = re.search(r"\$\s*([0-9]+(?:[.,][0-9]+)?)", user_message)
    crc_match = re.search(r"(?:₡|crc|colones?)\s*([0-9]+(?:[.,][0-9]+)?)", text, re.I)
    plain_match = re.search(r"\b([0-9]{4,}(?:[.,][0-9]+)?)\b", user_message)

    if usd_match:
        amount = float(usd_match.group(1).replace(",", "."))
        currency = "USD"
        exchange_rate = 495.0
    elif crc_match:
        amount = float(crc_match.group(1).replace(",", "."))
    elif plain_match:
        amount = float(plain_match.group(1).replace(",", "."))
    else:
        amount = 0.0

    months_match = re.search(r"(\d+)\s*(?:cuotas|meses|mes)", text)
    months = int(months_match.group(1)) if months_match else 1

    return {
        "amount": amount,
        "months": months,
        "description": user_message,
        "currency": currency,
        "exchange_rate": exchange_rate,
    }


def _format_financial_engine_message(report: dict) -> str:
    if report.get("status") != "OK":
        return "Señor, no pude calcular el motor financiero en este momento."

    health = report.get("health", {})
    forecast = report.get("forecast", {})
    emergency = report.get("emergency_fund", {})
    debts = report.get("debts", {})
    recs = report.get("recommendations", [])

    lines = [
        "Señor, este es el diagnóstico del motor financiero:",
        f"- Salud financiera: {health.get('score', 0)}% ({health.get('level', 'sin datos')}).",
        f"- Saldo estimado al cierre del mes: ₡{forecast.get('projected_end_balance', 0):,.0f}.",
        f"- Fondo de emergencia sugerido: ₡{emergency.get('recommended_3_months', 0):,.0f} a ₡{emergency.get('recommended_6_months', 0):,.0f}.",
    ]

    if debts.get("status") == "OK" and debts.get("avalanche"):
        lines.append(f"- Deuda prioritaria por avalancha: {debts['avalanche']['priority_debt']['name']}.")

    if recs:
        lines.append("Recomendaciones:")
        lines.extend([f"- {item}" for item in recs[:4]])

    return "\n".join(lines)


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


def process_message(user_message: str):
    # Decisiones personales claras (compras/viajes) se resuelven primero con su
    # flujo local, antes de clasificar la intención, para evitar respuestas genéricas.
    pending_action = get_pending_action()
    if pending_action and str(pending_action.get("action_type") or "").startswith("decision_"):
        pending_result = handle_decision_pending_action(pending_action, user_message)
        if pending_result:
            return pending_result

    if not pending_action:
        decision_result = handle_personal_decision_request(user_message)
        if decision_result:
            return decision_result

    strategy_request = bool(re.search(
        r"\b(estrategia|strategy|plan financiero|an[aá]lisis financiero)\b",
        (user_message or "").lower(),
    ))
    intent_result = (
        {"intent": "financial_strategy", "source": "deterministic", "confidence": 1.0}
        if strategy_request else detect_intent(user_message)
    )

    # Si hay una acción pendiente, primero verificamos si el usuario está cambiando de tema.
    # Esto evita que "busca Chimborazo" termine guardado como categoría o gasto.
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

    # Strategy requests always use the same live engine as both strategy screens.
    # The owner chat must not ask a model to generate or override the plan.
    if strategy_request:
        result = create_initial_financial_strategy()
        return {
            "message": result["message"],
            "intent": "financial_strategy",
            "status": "OK",
            "pending": False,
            "source": "live_database",
            "data": result["data"],
        }

    # Advisor Core owns every number and priority; the deterministic formatter
    # words its result, so the response can never become an empty
    # "Respuesta recibida" payload.
    if intent_result.get("intent") == "advisor_summary":
        advice = get_financial_advice()
        return {
            "message": format_jarvis_response(user_message, "advisor_summary", advice),
            "intent": "advisor_summary",
            "status": "OK",
            "pending": False,
            "source": "advisor_core_v2",
            "data": advice,
        }

    lower_message = (user_message or "").lower()
    if any(token in lower_message for token in ["quiero ir", "me gustaria ir", "me gustaría ir", "viajar", "viaje", "mónaco", "monaco", "f1", "formula 1", "fórmula 1"]):
        if any(goal_word in lower_message for goal_word in ["quiero", "gustaria", "gustaría", "viajar", "viaje", "ir a"]):
            plan = plan_long_term_goal(user_message)
            scenarios = plan.get("scenarios", [])
            scenario_lines = []
            for item in scenarios:
                if item.get("months"):
                    scenario_lines.append(f"{item['name']}: ₡{item['monthly_saving']:,.0f}/mes → {item['months']} meses, aprox. {item['target_year']}".replace(",", "."))
                else:
                    scenario_lines.append(f"{item['name']}: sin flujo disponible suficiente")
            message = plan.get("message", "Señor, generé una proyección de meta.")
            message += "\n" + "\n".join(scenario_lines[:3])
            return {
                "message": message,
                "intent": "goal_planning",
                "status": plan.get("status", "OK"),
                "pending": False,
                "source": "local_goal_planner",
                "data": plan,
            }

    if any(token in lower_message for token in ["abono", "abonar", "amortizar", "pagar deuda", "liquidar deuda", "ahorrar para pagar"]):
        advice = get_debt_advisory()
        return {
            "message": advice.get("message", "Señor, generé una estrategia de deuda."),
            "intent": "debt_advisory",
            "status": advice.get("status", "OK"),
            "pending": False,
            "source": "local_debt_advisory",
            "data": advice,
        }

    direct_payroll = _parse_direct_payroll_or_bonus(user_message)
    if direct_payroll:
        # Same interpretation as always (OT, VGH, holiday, bonus); the change is now shown with
        # its amount and saved only on "sí" (action_flow), with the historical reply.
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

    intent = intent_result.get("intent", "unknown")
    action_type = intent_result.get("action_type")
    entity = intent_result.get("entity")

    if intent == "internet_search":
        query = entity if isinstance(entity, str) and entity.strip() else user_message
        return _internet_answer(user_message, query)

    if intent == "create_calendar_event":
        parsed = parse_calendar_event(entity or user_message)
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

    if intent == "memory":
        text_lower = user_message.lower()
        if any(trigger in text_lower for trigger in ["recuerda que", "recorda que", "recordá que", "acuérdate", "acuerdate", "guarda en memoria", "agrega a memoria", "memoriza"]):
            payload = {"content": memory_content_from_message(user_message)}
            return _confirm_first("create_memory", user_message, payload, intent="memory")

        memories = search_memory_items(user_message, limit=8)
        if not memories:
            message = "Señor, no encontré recuerdos guardados sobre eso."
        else:
            lines = [f"- {item.get('content')}" for item in memories[:6]]
            message = "Señor, esto tengo en memoria:\n" + "\n".join(lines)
        return {"message": message, "intent": "memory", "status": "OK", "pending": False, "data": {"items": memories}}


    if intent == "financial_engine":
        lowered = (user_message or "").lower()
        if any(phrase in lowered for phrase in ["analiza mis finanzas", "primer analisis", "primer análisis", "estrategia completa", "plan completo"]):
            result = create_initial_financial_strategy()
            return {
                "message": result.get("message"),
                "intent": "financial_engine",
                "status": result.get("status", "OK"),
                "pending": False,
                "data": result,
                "budget": result.get("budget"),
            }
        report = get_financial_engine_report()
        return {
            "message": _format_financial_engine_message(report),
            "intent": "financial_engine",
            "status": report.get("status", "OK"),
            "pending": False,
            "data": report,
        }

    if intent == "financial_simulation":
        payload = _extract_simulation_payload(user_message)
        if payload["amount"] <= 0:
            return {
                "message": "Señor, necesito el monto para simular ese escenario.",
                "intent": "financial_simulation",
                "status": "MISSING_AMOUNT",
                "pending": False,
                "data": payload,
            }
        result = simulate_what_if(**payload)
        scenario = result.get("scenario", {})
        projection = result.get("projection", [])
        first_risk = next((item for item in projection if item.get("risk") == "high"), None)
        message = (
            f"Señor, si hace eso serían ₡{scenario.get('monthly_payment', 0):,.0f} al mes "
            f"durante {scenario.get('months')} mes(es). "
            f"Promedio de flujo mensual actual: ₡{result.get('baseline', {}).get('average_monthly_net_operational', 0):,.0f}. "
            f"{result.get('recommendation')}"
        )
        if first_risk:
            message += f" El primer mes con riesgo sería {first_risk.get('month')}."
        return {
            "message": message,
            "intent": "financial_simulation",
            "status": result.get("status", "OK"),
            "pending": False,
            "data": result,
        }

    if intent == "fixed_expense":
        result = plan_fixed_expense_message(user_message)
        if result["status"] == "READY":
            action = "create_fixed_expense" if result["operation"] == "create" else "update_fixed_expense"
            payload = {key: result.get(key) for key in ("fixed_expense_id", "name", "expected_amount", "due_day")}
            return _confirm_first(action, user_message, payload, intent="fixed_expense")
        return {
            "message": result.get("message"),
            "intent": "fixed_expense",
            "status": result.get("status", "OK"),
            "pending": False,
            "data": result.get("data"),
        }

    if intent == "email":
        return {
            "message": "Señor, detecté que esto corresponde a lectura de correos. Esa sección está identificada, pero la activaremos en su fase dedicada.",
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
