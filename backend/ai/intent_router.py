from __future__ import annotations

import json
import re
from typing import Any

from backend.ai.gemini_client import ask_gemini


ACTION_TYPES = [
    "create_debt",
    "create_saving",
    "create_investment",
    "create_expense",
    "create_income",
    "create_bonus",
    "create_transaction",
    "create_payroll_event",
    "create_employment_profile",
    "create_goal",
    "import_monthly_statement",
]

READ_INTENTS = [
    "highest_debt",
    "lowest_debt",
    "debt_summary",
    "net_worth",
    "user_status",
    "goal_status",
    "spending_habits",
    "advisor_summary",
    "unknown",
]

AVAILABLE_INTENTS = ACTION_TYPES + READ_INTENTS


START_PATTERNS = [
    ("create_debt", ["deuda", "prestamo", "préstamo", "tarjeta"]),
    ("create_saving", ["ahorro", "guardar ahorro"]),
    ("create_investment", ["inversion", "inversión", "inverti", "invertí"]),
    ("create_expense", ["gasto", "pago", "compra"]),
    ("create_income", ["ingreso", "salario", "sueldo"]),
    ("create_bonus", ["bono", "bonus"]),
    ("create_transaction", ["transaccion", "transacción", "movimiento"]),
    ("create_payroll_event", ["ot", "hora extra", "horas extra", "vgh", "vacaciones", "feriado"]),
    ("create_employment_profile", ["perfil laboral", "hora vale", "pago por hora", "tarifa por hora"]),
    ("create_goal", ["meta", "objetivo"]),
    ("import_monthly_statement", ["estado de cuenta", "estado financiero", "importar", "movimientos", "transacciones del mes"]),
]

CREATE_WORDS = [
    "agrega", "agregar", "añade", "anade", "registrar", "registra",
    "crear", "crea", "guardar", "guarda", "meter", "mete", "ingresar",
    "ingresa", "pon", "poner",
]


def _contains_any(text: str, words: list[str]) -> bool:
    return any(word in text for word in words)


def _fallback_detect(user_message: str) -> dict[str, Any]:
    text = user_message.lower().strip()

    import_words = [
        "estado de cuenta",
        "estado financiero",
        "voy a pasar",
        "te voy a pasar",
        "importar",
        "movimientos de",
        "transacciones de",
        "transacciones del mes",
    ]
    month_words = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "setiembre", "octubre",
        "noviembre", "diciembre",
    ]

    if _contains_any(text, import_words) and ("estado" in text or "movimiento" in text or "transaccion" in text or "transacción" in text or _contains_any(text, month_words)):
        return {
            "intent": "import_monthly_statement",
            "action_type": "import_monthly_statement",
            "entity": None,
            "confidence": 0.9,
            "source": "keyword_fallback",
        }

    wants_create = _contains_any(text, CREATE_WORDS)

    if wants_create:
        for action_type, keywords in START_PATTERNS:
            if _contains_any(text, keywords):
                return {
                    "intent": action_type,
                    "action_type": action_type,
                    "entity": None,
                    "confidence": 0.82,
                    "source": "keyword_fallback",
                }

    if re.search(r"deuda.+(pequeña|menor|baja|chiquita)|menor.+deuda|más pequeña", text):
        return {"intent": "lowest_debt", "entity": None, "confidence": 0.85, "source": "keyword_fallback"}

    if re.search(r"deuda.+(grande|mayor|alta)|mayor.+deuda|más grande", text):
        return {"intent": "highest_debt", "entity": None, "confidence": 0.85, "source": "keyword_fallback"}

    if "patrimonio" in text or "net worth" in text:
        return {"intent": "net_worth", "entity": None, "confidence": 0.8, "source": "keyword_fallback"}

    if "estado financiero" in text or "resumen financiero" in text or "cómo estoy" in text:
        return {"intent": "user_status", "entity": None, "confidence": 0.8, "source": "keyword_fallback"}

    if "gasto" in text or "hábitos" in text or "habitos" in text:
        return {"intent": "spending_habits", "entity": None, "confidence": 0.7, "source": "keyword_fallback"}

    if "recom" in text or "estrategia" in text:
        return {"intent": "advisor_summary", "entity": None, "confidence": 0.7, "source": "keyword_fallback"}

    return {"intent": "unknown", "entity": None, "confidence": 0, "source": "fallback"}


def detect_intent(user_message: str):
    fallback = _fallback_detect(user_message)
    if fallback["intent"] != "unknown":
        return fallback

    prompt = f"""
Eres el router de acciones de J.A.R.V.I.S.

Convierte el mensaje del usuario en JSON válido.

Acciones disponibles para CREAR datos:
{ACTION_TYPES}

Intenciones disponibles para CONSULTAR datos:
{READ_INTENTS}

Reglas:
- Responde SOLO JSON.
- No uses markdown.
- No expliques.
- Si el usuario quiere guardar, registrar, agregar, meter o crear datos, usa una acción create_*.
- Si el usuario quiere importar, pasar o cargar un estado de cuenta, movimientos o transacciones de un mes, usa import_monthly_statement.
- No inventes campos que el usuario no dijo.
- Si falta información, igual clasifica la acción y deja entity en null.
- Si pregunta por deuda más grande, usa highest_debt.
- Si pregunta por deuda más pequeña o menor, usa lowest_debt.
- Si pregunta por estado financiero general, usa user_status.
- Si pregunta por patrimonio, usa net_worth.
- Si pregunta por hábitos o gastos, usa spending_habits.

Formato:
{{
  "intent": "create_debt",
  "action_type": "create_debt",
  "entity": null,
  "confidence": 0.95
}}

Mensaje del usuario:
"{user_message}"
"""

    ai_response = ask_gemini(prompt)

    if ai_response["status"] != "OK":
        return fallback

    text = ai_response["text"].strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        parsed = json.loads(text)
        intent = parsed.get("intent", "unknown")
        if intent not in AVAILABLE_INTENTS:
            intent = "unknown"

        return {
            "intent": intent,
            "action_type": parsed.get("action_type") or (intent if intent in ACTION_TYPES else None),
            "entity": parsed.get("entity"),
            "confidence": parsed.get("confidence", 0),
            "source": "gemini",
        }

    except json.JSONDecodeError:
        return {
            "intent": "unknown",
            "action_type": None,
            "entity": None,
            "confidence": 0,
            "source": "gemini_parse_error",
            "raw": text,
        }
