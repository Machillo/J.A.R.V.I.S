from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
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
    "internet_search",
    "create_calendar_event",
    "calendar_summary",
    "sports_schedule",
    "memory",
    "email",
    "fixed_expense",
    "general",
    "unknown",
]

AVAILABLE_INTENTS = ACTION_TYPES + READ_INTENTS

CREATE_WORDS = {
    "agrega", "agregar", "añade", "anade", "registrar", "registra",
    "crear", "crea", "guardar", "guarda", "meter", "mete", "ingresar",
    "ingresa", "pon", "poner", "sumar", "suma", "cargar", "carga",
}

YES_NO_WORDS = {"si", "sí", "no", "ok", "dale", "confirmo", "cancelar", "cancela"}

MONTH_WORDS = {
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
    "septiembre", "setiembre", "octubre", "noviembre", "diciembre",
}

WEEKDAY_WORDS = {
    "lunes", "martes", "miercoles", "miércoles", "jueves", "viernes", "sabado", "sábado", "domingo",
}

FINANCE_READ_KEYWORDS = {
    "deuda", "deudas", "saldo", "net worth", "patrimonio", "ingreso", "ingresos",
    "gasto", "gastos", "ahorro", "ahorros", "inversion", "inversión", "meta", "metas",
    "financiero", "finanzas", "presupuesto", "categorias", "categorías", "bac", "multimoney",
    "popular", "prestamo", "préstamo", "tarjeta", "ibkr", "cripto",
}

SPORTS_F1 = {"f1", "formula 1", "fórmula 1", "gran premio", "gp", "sprint", "clasificacion", "clasificación", "carrera"}
SPORTS_UFC = {"ufc", "mma", "cartelera", "pelea", "peleas", "fight night", "main card"}
SPORTS_FOOTBALL = {
    "futbol", "fútbol", "partido", "partidos", "champions", "mundial", "liga", "lda",
    "alajuelense", "barcelona", "city", "manchester city", "arsenal", "milan", "inter", "psg",
    "bayern", "bayer", "bayer munich", "bayern munich", "borussia", "dortmund", "costa rica",
    "seleccion", "selección", "mundial de clubes",
}


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def normalize_message(message: str) -> str:
    text = _strip_accents((message or "").lower())
    text = re.sub(r"\b(k?jarvis|karvis|jervis|jarbis)\b[:,\s]*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _contains_any(text: str, words: set[str] | list[str]) -> bool:
    return any(word in text for word in words)


def _starts_with_any(text: str, words: set[str] | list[str]) -> bool:
    return any(text.startswith(word) for word in words)


def _has_date_signal(text: str) -> bool:
    if any(word in text for word in ["hoy", "manana", "mañana", "pasado manana", "pasado mañana"]):
        return True
    if _contains_any(text, MONTH_WORDS) or _contains_any(text, WEEKDAY_WORDS):
        return True
    if re.search(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b", text):
        return True
    if re.search(r"\b\d{1,2}\s+de\s+\w+\b", text):
        return True
    return False


def _is_question(text: str) -> bool:
    return bool(re.search(r"\b(que|qué|cual|cuál|cuando|cuándo|donde|dónde|quien|quién|como|cómo|cuanto|cuánto|por que|porque)\b", text))


def _extract_sports_scope(text: str) -> str:
    if _contains_any(text, SPORTS_F1):
        return "f1"
    if _contains_any(text, SPORTS_UFC):
        return "ufc"
    if _contains_any(text, SPORTS_FOOTBALL):
        return "football"
    return "all"


def _extract_sports_query_type(text: str) -> str:
    if any(word in text for word in ["proxima", "proximo", "siguiente", "cuando", "cuándo"]):
        return "next"
    if any(word in text for word in ["actualiza", "radar", "calendario", "agenda"]):
        return "radar"
    if any(word in text for word in ["recordame", "avisame", "notifica", "seguir"]):
        return "subscribe"
    return "next"


def _clean_search_query(user_message: str) -> str:
    query = re.sub(r"^\s*(jarvis|karvis|jervis|jarbis)[,\s]*", "", user_message.strip(), flags=re.I)
    query = re.sub(r"^\s*(busca|buscar|investiga|consulta|googlea)(\s+en\s+internet|\s+online|\s+en\s+la\s+web)?\s*", "", query, flags=re.I)
    return query.strip(" ¿?.,") or user_message.strip()


def _financial_read_intent(text: str) -> dict[str, Any] | None:
    if re.search(r"deuda.+(pequena|menor|baja|chiquita)|menor.+deuda|mas pequena", text):
        return {"intent": "lowest_debt", "entity": None, "confidence": 0.95, "source": "deterministic"}
    if re.search(r"deuda.+(grande|mayor|alta)|mayor.+deuda|mas grande", text):
        return {"intent": "highest_debt", "entity": None, "confidence": 0.95, "source": "deterministic"}
    if "patrimonio" in text or "net worth" in text:
        return {"intent": "net_worth", "entity": None, "confidence": 0.9, "source": "deterministic"}
    if any(phrase in text for phrase in ["estado financiero", "resumen financiero", "como estoy", "cómo estoy"]):
        return {"intent": "user_status", "entity": None, "confidence": 0.9, "source": "deterministic"}
    if any(word in text for word in ["habitos", "hábitos", "categorias", "categorías", "en que se va", "en que gasto"]):
        return {"intent": "spending_habits", "entity": None, "confidence": 0.85, "source": "deterministic"}
    if any(word in text for word in ["recom", "estrategia", "consejo", "asesor"]):
        return {"intent": "advisor_summary", "entity": None, "confidence": 0.8, "source": "deterministic"}
    if "deuda" in text or "deudas" in text:
        return {"intent": "debt_summary", "entity": None, "confidence": 0.75, "source": "deterministic"}
    return None


def _create_action_intent(text: str) -> dict[str, Any] | None:
    wants_create = _contains_any(text, CREATE_WORDS)
    if not wants_create:
        return None

    if any(phrase in text for phrase in ["estado de cuenta", "estado financiero", "movimientos", "transacciones del mes"]):
        return {"intent": "import_monthly_statement", "action_type": "import_monthly_statement", "entity": None, "confidence": 0.96, "source": "deterministic"}
    if any(word in text for word in ["deuda", "prestamo", "préstamo", "tarjeta"]):
        return {"intent": "create_debt", "action_type": "create_debt", "entity": None, "confidence": 0.9, "source": "deterministic"}
    if any(word in text for word in ["gasto", "compra", "pague", "pagué", "pago"]):
        return {"intent": "create_expense", "action_type": "create_expense", "entity": None, "confidence": 0.86, "source": "deterministic"}
    if any(word in text for word in ["ingreso", "salario", "sueldo"]):
        return {"intent": "create_income", "action_type": "create_income", "entity": None, "confidence": 0.86, "source": "deterministic"}
    if any(word in text for word in ["ahorro", "guardar ahorro"]):
        return {"intent": "create_saving", "action_type": "create_saving", "entity": None, "confidence": 0.86, "source": "deterministic"}
    if any(word in text for word in ["inversion", "inversión", "inverti", "invertí"]):
        return {"intent": "create_investment", "action_type": "create_investment", "entity": None, "confidence": 0.86, "source": "deterministic"}
    if any(word in text for word in ["meta", "objetivo"]):
        return {"intent": "create_goal", "action_type": "create_goal", "entity": None, "confidence": 0.86, "source": "deterministic"}
    if any(word in text for word in ["bono", "bonus"]):
        return {"intent": "create_bonus", "action_type": "create_bonus", "entity": None, "confidence": 0.86, "source": "deterministic"}
    if any(word in text for word in ["hora extra", "horas extra", "ot", "vacaciones", "feriado"]):
        return {"intent": "create_payroll_event", "action_type": "create_payroll_event", "entity": None, "confidence": 0.86, "source": "deterministic"}
    if any(word in text for word in ["perfil laboral", "hora vale", "tarifa por hora"]):
        return {"intent": "create_employment_profile", "action_type": "create_employment_profile", "entity": None, "confidence": 0.86, "source": "deterministic"}
    return None


def _fallback_detect(user_message: str) -> dict[str, Any]:
    text = normalize_message(user_message)

    if not text:
        return {"intent": "unknown", "entity": None, "confidence": 0, "source": "deterministic"}

    # 1. Internet explícito y consultas externas. Esto siempre va antes que finanzas.
    internet_prefixes = ["busca ", "buscar ", "investiga ", "consulta ", "googlea "]
    internet_phrases = ["en internet", "en la web", "online", "noticias", "precio actual", "resultado actual"]
    if _starts_with_any(text, internet_prefixes) or _contains_any(text, internet_phrases):
        return {
            "intent": "internet_search",
            "action_type": None,
            "entity": _clean_search_query(user_message),
            "confidence": 0.98,
            "source": "deterministic",
        }

    # 2. Deportes. Preguntas deportivas son externas y deben ser concisas.
    if _contains_any(text, SPORTS_F1 | SPORTS_UFC | SPORTS_FOOTBALL):
        sports_trigger = any(word in text for word in [
            "cuando", "cuándo", "proxima", "proximo", "siguiente", "hora", "calendario",
            "carrera", "clasificacion", "sprint", "partido", "cartelera", "pelea", "mundial",
            "champions", "actualiza", "recordame", "avisame", "notifica",
        ])
        if sports_trigger or _is_question(text):
            return {
                "intent": "sports_schedule",
                "action_type": None,
                "entity": {
                    "scope": _extract_sports_scope(text),
                    "query_type": _extract_sports_query_type(text),
                    "query": user_message.strip(),
                },
                "confidence": 0.96,
                "source": "deterministic",
            }

    # 3. Calendario / recordatorios. Se evalúa antes que crear pagos/gastos.
    calendar_words = {
        "calendario", "agenda", "agendar", "agendame", "agendá", "recordame", "recuerdame",
        "recuérdame", "recordatorio", "compromiso", "actividad", "evento", "cita", "reunion", "reunión",
        "tengo una", "tengo un", "tengo cita", "tengo actividad", "tengo compromiso",
    }
    calendar_query_words = {"que tengo", "qué tengo", "mis compromisos", "mi agenda", "proximos", "próximos"}
    if _contains_any(text, calendar_query_words):
        return {"intent": "calendar_summary", "entity": None, "confidence": 0.95, "source": "deterministic"}
    if _contains_any(text, calendar_words) or (_has_date_signal(text) and not _contains_any(text, FINANCE_READ_KEYWORDS)):
        return {
            "intent": "create_calendar_event",
            "action_type": None,
            "entity": user_message.strip(),
            "confidence": 0.94,
            "source": "deterministic",
        }

    # 4. Importador mensual antes de acciones sueltas.
    if any(phrase in text for phrase in ["estado de cuenta", "estado financiero", "transacciones del mes", "movimientos de"]):
        return {"intent": "import_monthly_statement", "action_type": "import_monthly_statement", "entity": None, "confidence": 0.9, "source": "deterministic"}

    # 5. Crear datos financieros.
    create_intent = _create_action_intent(text)
    if create_intent:
        return create_intent

    # 6. Consultas financieras.
    finance_read = _financial_read_intent(text)
    if finance_read:
        return finance_read

    # 7. Correos / memoria / gastos fijos.
    if any(word in text for word in ["correo", "correos", "gmail", "email", "mail"]):
        return {"intent": "email", "entity": None, "confidence": 0.75, "source": "deterministic"}
    if any(word in text for word in ["recuerda que", "recorda que", "memoria", "acordate", "acuérdate"]):
        return {"intent": "memory", "entity": user_message.strip(), "confidence": 0.8, "source": "deterministic"}
    if any(phrase in text for phrase in ["gasto fijo", "gastos fijos", "pago fijo", "recurrente"]):
        return {"intent": "fixed_expense", "entity": user_message.strip(), "confidence": 0.8, "source": "deterministic"}

    return {"intent": "general", "entity": user_message.strip(), "confidence": 0.4, "source": "deterministic"}


def _valid_intent_result(parsed: dict[str, Any]) -> dict[str, Any]:
    intent = parsed.get("intent", "unknown")
    if intent not in AVAILABLE_INTENTS:
        intent = "unknown"
    action_type = parsed.get("action_type") or (intent if intent in ACTION_TYPES else None)
    return {
        "intent": intent,
        "action_type": action_type,
        "entity": parsed.get("entity"),
        "confidence": float(parsed.get("confidence") or 0),
        "source": parsed.get("source") or "gemini",
    }


def detect_intent(user_message: str) -> dict[str, Any]:
    # Determinístico primero. Evita gastar tokens para casos claros.
    fallback = _fallback_detect(user_message)
    if fallback["intent"] not in {"general", "unknown"} and fallback.get("confidence", 0) >= 0.75:
        return fallback

    prompt = f"""
Eres el clasificador de intención de J.A.R.V.I.S. No respondes al usuario.

Devuelve SOLO JSON válido con esta forma:
{{"intent":"...","action_type":null,"entity":null,"confidence":0.0}}

Intenciones disponibles:
{AVAILABLE_INTENTS}

Reglas críticas:
1. Si el usuario pide buscar/investigar/consultar algo externo, usa internet_search.
2. Si menciona F1, UFC, fútbol, carreras, partidos, Champions o mundial, usa sports_schedule.
3. Si dice que tiene una cita, actividad, evento, compromiso, recordatorio o fecha personal, usa create_calendar_event.
4. Si pregunta por agenda/calendario, usa calendar_summary.
5. Solo usa create_expense/create_debt/create_income si claramente quiere guardar datos financieros.
6. Chimborazo, F1, UFC, fútbol, noticias o preguntas generales NO son gastos.
7. Responde breve JSON, sin markdown.

Mensaje:
{user_message!r}
"""

    ai_response = ask_gemini(prompt, route="intent_classifier")
    if ai_response.get("status") != "OK":
        return fallback

    text = (ai_response.get("text") or "").strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return _valid_intent_result(json.loads(text))
    except Exception:
        return fallback


def is_pending_interrupt(intent_result: dict[str, Any], user_message: str) -> bool:
    """True si un mensaje nuevo no debe alimentar una acción pendiente.

    Ejemplo: si quedó pendiente un gasto y el usuario dice "busca el Chimborazo",
    esa frase debe cancelar/interrumpir el flujo financiero, no guardarse como categoría.
    """
    text = normalize_message(user_message)
    if text in YES_NO_WORDS:
        return False
    intent = intent_result.get("intent")
    return intent in {
        "internet_search",
        "sports_schedule",
        "create_calendar_event",
        "calendar_summary",
        "email",
        "memory",
        "fixed_expense",
    }
