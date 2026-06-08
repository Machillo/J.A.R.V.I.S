from __future__ import annotations

import json

from backend.ai.action_flow import continue_pending_action, start_action, _missing_required, _save_action
from backend.ai.chat_memory import finish_pending_action, get_pending_action
from backend.ai.gemini_client import ask_gemini
from backend.ai.openai_client import ask_openai, get_active_premium_guides, save_premium_guide
from backend.ai.intent_router import ACTION_TYPES, detect_intent, is_pending_interrupt
from backend.ai.memory_service import get_relevant_memory_context, remember_from_message, search_memory_items
from backend.ai.response_formatter import format_jarvis_response
from backend.ai.premium_orchestrator import premium_route_command, get_current_strategy_summary
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
from backend.finance.strategic_engine import get_financial_engine_report, simulate_what_if
from backend.finance.fixed_expenses import handle_fixed_expense_message
from backend.ai.strategy_dashboard import build_local_strategy_blueprint


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
        "strategic_engine": _safe_call(get_financial_engine_report, {}),
    }


def _internet_answer(user_message: str, query: str) -> dict:
    memory_context = get_relevant_memory_context(user_message, limit=5)
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
Memoria relevante del usuario:
{json.dumps(memory_context, ensure_ascii=False, indent=2)}
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
    memory_context = get_relevant_memory_context(user_message, limit=8)
    premium_guides = get_active_premium_guides(limit=3)

    system = """
Eres J.A.R.V.I.S., asesor financiero personal.
Responde en español con tono de asesor: directo, corto y accionable.
No uses nombre ni correo en saludos. Si saludas, usa solo: "Señor, ...".
No conviertas preguntas de capacidad de compra en registro de gastos.
Si el usuario dice "¿puedo comprar...?", evalúa capacidad, deudas, gastos fijos y estrategia.
Usa SOLO los datos reales recibidos. No inventes montos, fechas, deudas ni categorías.
No muestres todo el historial: da conclusión, razón y siguiente acción.
""".strip()

    prompt = f"""
Pregunta/comando del usuario:
{user_message}

Intento detectado:
{json.dumps(intent_result, ensure_ascii=False)}

Memoria relevante:
{json.dumps(memory_context, ensure_ascii=False, indent=2)}

Guías financieras activas creadas anteriormente:
{json.dumps(premium_guides, ensure_ascii=False, indent=2)}

Resumen real del backend financiero:
{json.dumps(context, ensure_ascii=False, indent=2)}

Instrucción final:
Responde máximo en 5 líneas. Si hay un riesgo claro, dilo primero. Si falta un dato, pide solo ese dato.
"""

    ai_response = ask_openai(prompt, route="jarvis_premium_finance_answer", system=system, max_tokens=650)
    source = "openai_premium_with_jarvis_context"

    if ai_response.get("status") != "OK":
        fallback_prompt = f"""
Eres J.A.R.V.I.S., asistente financiero privado.
Responde en español, breve, claro y útil.
Usa SOLO los datos reales si la pregunta es financiera.
No inventes montos, fechas, deudas ni categorías.

Pregunta: {user_message}
Intento detectado: {json.dumps(intent_result, ensure_ascii=False)}
Memoria del usuario:
{json.dumps(memory_context, ensure_ascii=False, indent=2)}
Datos reales:
{json.dumps(context, ensure_ascii=False, indent=2)}
"""
        ai_response = ask_gemini(fallback_prompt, route="jarvis_context_answer")
        source = "gemini_fallback_with_jarvis_context"

    if ai_response.get("status") != "OK":
        return {
            "message": "Señor, tengo el contexto cargado, pero la IA no pudo generar respuesta en este momento.",
            "intent": intent_result.get("intent", "context_answer"),
            "status": "AI_ERROR",
            "pending": False,
            "data": context,
            "ai_error": ai_response,
        }

    return {
        "message": ai_response["text"].strip(),
        "intent": intent_result.get("intent", "context_answer"),
        "entity": intent_result.get("entity"),
        "confidence": intent_result.get("confidence", 0),
        "source": source,
        "pending": False,
        "status": "OK",
        "usage": ai_response.get("usage"),
        "budget": ai_response.get("budget"),
        "data": context,
    }


def create_initial_financial_strategy():
    """Crea una estrategia premium en modo Director: decide, guarda y muestra ruta.

    No pregunta si debe comenzar; si el usuario pidió estrategia, Jarvis ejecuta.
    """
    context = build_financial_context()
    memory_context = get_relevant_memory_context("estrategia financiera principal", limit=10)
    blueprint = build_local_strategy_blueprint()

    system = """
Eres J.A.R.V.I.S., Director Financiero Personal.
No eres consultor: cuando el usuario pide estrategia, decides y ejecutas una estrategia base con los datos existentes.
No preguntes "¿desea que...?" si ya hay deudas, ingresos o gastos suficientes.
No saludes con nombre/correo. Usa solo "Señor,".
Sé firme, corto y accionable. Debes actuar como director estricto: deuda primero, liquidez controlada, compras no esenciales restringidas.
No inventes datos; si algo falta, lo marcas como pendiente, pero igual creas una estrategia provisional.
""".strip()

    prompt = f"""
Crea y activa una estrategia financiera premium para el usuario.

Blueprint calculado por el backend, úsalo como fuente dura:
{json.dumps(blueprint, ensure_ascii=False, indent=2)}

Memoria relevante:
{json.dumps(memory_context, ensure_ascii=False, indent=2)}

Datos reales del backend:
{json.dumps(context, ensure_ascii=False, indent=2)}

Entrega obligatoria:
1. Nombre de estrategia activa.
2. Diagnóstico brutal en máximo 4 bullets.
3. Deuda prioritaria y por qué.
4. Distribución del salario en porcentajes.
5. Regla para OT, bonos y sobrantes.
6. Tiempo estimado para pagar deudas según datos actuales.
7. Qué debe hacer este mes.
8. Qué datos faltan para mejorar precisión.

Tono: firme, tipo director. No pidas permiso para comenzar.
"""
    ai_response = ask_openai(prompt, route="jarvis_premium_initial_strategy", system=system, max_tokens=1400)
    if ai_response.get("status") != "OK":
        fallback = (
            "Señor, estrategia activada en modo local. Prioridad absoluta: atacar deuda de mayor impacto, "
            "mantener pagos mínimos al día y mandar OT/bonos/sobrantes a la deuda prioritaria."
        )
        saved = save_premium_guide(
            guide_type="financial_strategy",
            title=blueprint.get("title", "Estrategia financiera principal"),
            content=fallback,
            data={"strategy_blueprint": blueprint, "context_snapshot": context, "created_by": "local_fallback"},
        )
        return {"status": "OK", "message": fallback, "guide": saved.get("guide"), "data": {"strategy": blueprint}, "budget": ai_response.get("budget")}

    content = ai_response["text"].strip()
    saved = save_premium_guide(
        guide_type="financial_strategy",
        title=blueprint.get("title", "Estrategia financiera principal"),
        content=content,
        data={"strategy_blueprint": blueprint, "context_snapshot": context, "created_by": "openai_director"},
    )
    return {
        "status": "OK",
        "message": content,
        "guide": saved.get("guide"),
        "data": {"strategy": blueprint},
        "usage": ai_response.get("usage"),
        "budget": ai_response.get("budget"),
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

    premium_route = premium_route_command(user_message, intent_result)
    if premium_route.get("status") == "OK":
        route = premium_route.get("route") or {}
        premium_intent = route.get("intent")
        premium_action = route.get("action_type") if route.get("action_type") not in {None, "", "null"} else None
        premium_payload = route.get("payload") if isinstance(route.get("payload"), dict) else {}

        if premium_action in ACTION_TYPES:
            # Eventos diarios seguros: registrar directo y recalcular contexto. El Director no pregunta por OT/bonos si el monto/horas ya vino claro.
            if premium_action in {"create_payroll_event", "create_bonus"} and not _missing_required(premium_action, premium_payload):
                saved_action = _save_action(premium_action, premium_payload)
                followup = answer_with_context(
                    f"Registré este evento: {json.dumps(premium_payload, ensure_ascii=False)}. Recalcula impacto y dime adónde debe ir el extra según la estrategia.",
                    {"intent": "salary_distribution", "premium_route": route},
                )
                return {
                    "message": followup.get("message") or "Señor, registrado. El extra debe ir según la estrategia activa.",
                    "intent": premium_intent or premium_action,
                    "action_type": premium_action,
                    "status": "OK",
                    "pending": False,
                    "confidence": route.get("confidence", 0),
                    "source": "openai_premium_director_autosave",
                    "usage": premium_route.get("usage"),
                    "budget": premium_route.get("budget"),
                    "data": {"router": route, "action": saved_action, "followup": followup.get("data")},
                }

            action_result = start_action(premium_action, user_message, prefill_payload=premium_payload)
            return {
                "message": action_result["message"],
                "intent": premium_intent or premium_action,
                "action_type": premium_action,
                "status": action_result.get("status", "PENDING"),
                "pending": action_result.get("pending", True),
                "confidence": route.get("confidence", 0),
                "source": "openai_premium_router",
                "usage": premium_route.get("usage"),
                "budget": premium_route.get("budget"),
                "data": {"router": route, "action": action_result.get("data")},
            }

        if premium_intent == "financial_strategy":
            result = create_initial_financial_strategy()
            return {
                "message": result.get("message"),
                "intent": "financial_strategy",
                "status": result.get("status", "OK"),
                "pending": False,
                "source": "openai_premium_director",
                "usage": result.get("usage"),
                "budget": result.get("budget"),
                "data": result,
            }

        if premium_intent == "internet_search":
            query = route.get("query") or user_message
            return _internet_answer(user_message, query)

        if premium_intent == "calendar":
            calendar_result = create_calendar_event_from_text(route.get("query") or user_message)
            return {
                "message": calendar_result.get("message"),
                "intent": "create_calendar_event",
                "status": calendar_result.get("status", "OK"),
                "pending": calendar_result.get("pending", False),
                "source": "openai_premium_router",
                "data": calendar_result,
            }

        if premium_intent == "sports_schedule":
            result = get_sports_calendar_summary({"scope": "all", "query_type": "next", "query": route.get("query") or user_message})
            return {
                "message": result.get("message"),
                "intent": "sports_schedule",
                "status": result.get("status", "OK"),
                "pending": False,
                "source": "openai_premium_router",
                "data": result,
            }

        if premium_intent == "fixed_expense":
            result = handle_fixed_expense_message(user_message)
            if result.get("status") == "OK":
                return {
                    "message": result.get("message"),
                    "intent": "fixed_expense",
                    "status": result.get("status", "OK"),
                    "pending": False,
                    "source": "openai_premium_router",
                    "data": result.get("data"),
                }

        if premium_intent in {
            "capacity_check", "financial_strategy", "salary_distribution",
            "direct_finance_answer", "general"
        } or float(route.get("confidence") or 0) >= 0.72:
            enhanced_intent = dict(intent_result)
            enhanced_intent.update({"premium_route": route, "intent": premium_intent or intent_result.get("intent")})
            return answer_with_context(user_message, enhanced_intent)

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

    if intent == "memory":
        text_lower = user_message.lower()
        if any(trigger in text_lower for trigger in ["recuerda que", "recorda que", "recordá que", "acuérdate", "acuerdate", "guarda en memoria", "agrega a memoria", "memoriza"]):
            result = remember_from_message(user_message)
            return {
                "message": "Listo, lo recordaré.",
                "intent": "memory",
                "status": result.get("status", "OK"),
                "pending": False,
                "data": result,
            }

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
        result = handle_fixed_expense_message(user_message)
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
