from __future__ import annotations

import json
from typing import Any

from backend.ai.openai_client import ask_openai_json, get_active_premium_guides
from backend.ai.memory_service import create_memory_item, get_relevant_memory_context
from backend.auth.current_user import get_current_user
from backend.finance.strategic_engine import get_financial_engine_report
from backend.finance.service import get_debts, get_financial_summary, get_net_worth_report
from backend.transactions.analyzer import get_transaction_analysis


def _safe(fn, fallback):
    try:
        return fn()
    except Exception as exc:
        return {"error": str(exc), "fallback": fallback}


def build_premium_context(user_message: str = "") -> dict[str, Any]:
    return {
        "financial_summary": _safe(get_financial_summary, {}),
        "net_worth": _safe(get_net_worth_report, {}),
        "debts": _safe(get_debts, []),
        "transactions_summary": _safe(get_transaction_analysis, {}),
        "strategic_engine": _safe(get_financial_engine_report, {}),
        "memory": _safe(lambda: get_relevant_memory_context(user_message or "finanzas estrategia preferencias", limit=8), []),
        "premium_guides": _safe(lambda: get_active_premium_guides(limit=4), []),
    }


def premium_route_command(user_message: str, local_intent: dict[str, Any] | None = None) -> dict[str, Any]:
    user = get_current_user()
    if user.get("role") not in {"owner", "admin"}:
        return {"status": "SKIPPED", "reason": "owner_only"}

    context = build_premium_context(user_message)
    system = """
Eres el cerebro premium de J.A.R.V.I.S. Tu trabajo NO es conversar todavía; debes interpretar intención y devolver JSON.
Reglas estrictas:
- No uses nombre/correo. Para respuestas futuras el prefijo permitido es solo "Señor,".
- Distingue consulta financiera de registro de gasto. "¿Puedo comprar X?" es capacidad_de_compra, NO create_expense.
- Si el usuario informa un cambio real ya ocurrido, clasifícalo como acción local si hay datos suficientes.
- Si falta un dato importante, pide solo ese dato.
- No inventes números. Usa el contexto solo como resumen.
- Para deportes/calendario/internet devuelve la intención correcta, no finanzas.

Devuelve JSON con esta forma:
{
  "status":"OK",
  "intent":"capacity_check|financial_strategy|salary_distribution|create_debt|create_saving|create_goal|create_expense|create_income|create_bonus|create_payroll_event|fixed_expense|sports_schedule|calendar|internet_search|email|memory|direct_finance_answer|general",
  "confidence":0.0,
  "should_use_local_action":true,
  "action_type":"create_payroll_event|null",
  "payload":{},
  "query":"",
  "needs_confirmation":true,
  "missing_field":"",
  "advisor_mode":"short|normal",
  "learning_note":"frase corta que Jarvis pueda guardar para aprender"
}
""".strip()

    prompt = f"""
Mensaje del usuario:
{user_message}

Intención local actual:
{json.dumps(local_intent or {}, ensure_ascii=False)}

Contexto resumido real de JARVIS:
{json.dumps(context, ensure_ascii=False, indent=2)}

Mapeo de acciones locales disponibles:
- create_debt: name,total_amount,remaining_amount,interest_rate,monthly_payment,payment_day
- create_saving: name,amount
- create_goal: name,target_amount,current_amount,target_date,priority
- create_expense: category,amount,description,expense_type
- create_income: amount,source
- create_bonus: amount,description
- create_payroll_event: event_type ('ot','vgh','holiday'), hours, description
- fixed_expense: cambios en gastos fijos recurrentes

Ejemplos:
"hoy hice 2.5 h de ot" => create_payroll_event payload {{"event_type":"ot","hours":2.5}}
"agarré 2 horas de vgh" => create_payroll_event payload {{"event_type":"vgh","hours":2}}
"me llegó 48000 de bono" => create_bonus payload {{"amount":48000}}
"puedo comprar una cerveza de 4000" => capacity_check, no action_type
"cuál es mi mayor deuda" => direct_finance_answer
"subió el gimnasio a 27000" => fixed_expense
"cuando es la próxima carrera" => sports_schedule
"busca Chimborazo" => internet_search
"tengo cita el 25 de julio" => calendar
"""

    routed = ask_openai_json(prompt, route="jarvis_premium_intent_router", system=system, max_tokens=650)
    if routed.get("status") != "OK":
        return routed
    data = routed.get("data") or {}
    if data.get("learning_note"):
        try:
            create_memory_item(
                content=str(data["learning_note"]),
                category="project",
                title="Aprendizaje de intención premium",
                importance=2,
                source="openai_router",
                metadata={"message": user_message, "intent": data.get("intent")},
            )
        except Exception:
            pass
    return {**routed, "route": data}


def get_current_strategy_summary() -> dict[str, Any]:
    context = build_premium_context("estrategia actual distribución dinero")
    guide_items = context.get("premium_guides") or []
    active_strategy = next((g for g in guide_items if g.get("guide_type") == "financial_strategy"), None)
    strategic = context.get("strategic_engine") or {}
    allocation = strategic.get("allocation") or strategic.get("smart_cash_allocation") or {}
    allocations = allocation.get("allocations") if isinstance(allocation, dict) else None

    # Fallback compact from recommendations/debts if allocation engine isn't present in report.
    if not allocations:
        debts = context.get("debts") or []
        highest_interest = None
        try:
            highest_interest = max(debts, key=lambda item: float(item.get("interest_rate") or 0)) if debts else None
        except Exception:
            highest_interest = None
        allocations = []
        if highest_interest:
            allocations.append({
                "target_type": "debt",
                "target_name": highest_interest.get("name") or "Deuda prioritaria",
                "percentage": 60,
                "amount": None,
                "reason": "Prioridad sugerida por tasa de interés y estrategia de deuda.",
            })
        allocations.append({
            "target_type": "cash_guard",
            "target_name": "Gastos fijos y margen",
            "percentage": 40,
            "amount": None,
            "reason": "Mantener pagos al día antes de abonar extras.",
        })

    title = active_strategy.get("title") if active_strategy else "Estrategia base"
    content = active_strategy.get("content") if active_strategy else "Señor, aún no hay una estrategia premium guardada. Ejecuta el primer análisis financiero premium."

    return {
        "status": "OK",
        "title": title,
        "summary": content[:1200],
        "allocations": allocations[:6],
        "health": (strategic.get("health") or {}),
        "forecast": (strategic.get("forecast") or {}),
        "source": "premium_guide" if active_strategy else "local_fallback",
    }
