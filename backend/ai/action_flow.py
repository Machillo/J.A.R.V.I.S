from __future__ import annotations

import re
from datetime import date
from typing import Any

from backend.ai.chat_memory import (
    create_pending_action,
    finish_pending_action,
    get_pending_action,
    update_pending_action,
)
from backend.finance.service import (
    add_bonus,
    add_debt,
    add_expense,
    add_investment,
    add_payroll_event,
    add_salary,
    add_saving,
    set_employment_profile,
)
from backend.goals.service import add_financial_goal
from backend.transactions.service import create_transaction


YES_WORDS = {"si", "sí", "confirmo", "guardar", "guarda", "dale", "ok", "correcto", "acepto"}
NO_WORDS = {"no", "cancelar", "cancela", "olvida", "detener", "salir"}

ACTION_CONFIG = {
    "create_debt": {
        "label": "deuda",
        "required": ["name", "total_amount", "monthly_payment"],
        "optional_defaults": {
            "debt_type": "other",
            "remaining_amount": None,
            "interest_rate": 0,
            "term_months": None,
            "payment_day": None,
        },
        "questions": {
            "name": "¿Cómo se llama la deuda? Ejemplo: BAC, MultiMoney o préstamo Popular.",
            "total_amount": "¿Cuál es el monto total de la deuda?",
            "monthly_payment": "¿Cuál es la cuota mensual?",
        },
    },
    "create_saving": {
        "label": "ahorro",
        "required": ["name", "amount"],
        "optional_defaults": {},
        "questions": {
            "name": "¿Cómo se llama este ahorro?",
            "amount": "¿Cuánto dinero tiene ese ahorro?",
        },
    },
    "create_investment": {
        "label": "inversión",
        "required": ["name", "amount"],
        "optional_defaults": {},
        "questions": {
            "name": "¿Cómo se llama esta inversión?",
            "amount": "¿Cuál es el monto invertido?",
        },
    },
    "create_expense": {
        "label": "gasto",
        "required": ["category", "amount"],
        "optional_defaults": {"expense_type": "variable", "description": ""},
        "questions": {
            "category": "¿En qué categoría va este gasto? Ejemplo: comida, transporte, gimnasio.",
            "amount": "¿Cuál es el monto del gasto?",
        },
    },
    "create_income": {
        "label": "ingreso",
        "required": ["amount", "source"],
        "optional_defaults": {},
        "questions": {
            "amount": "¿Cuál es el monto del ingreso?",
            "source": "¿Cuál es la fuente del ingreso? Ejemplo: salario, OT, bono, freelance.",
        },
    },
    "create_bonus": {
        "label": "bono",
        "required": ["amount"],
        "optional_defaults": {"description": "Bono registrado por chat"},
        "questions": {
            "amount": "¿Cuál es el monto del bono?",
        },
    },
    "create_transaction": {
        "label": "transacción",
        "required": ["description", "amount", "transaction_type", "category"],
        "optional_defaults": {
            "transaction_date": None,
            "account": "",
            "source": "chat",
            "notes": "Registrado por JARVIS Chat",
            "original_amount": None,
            "original_currency": None,
            "exchange_rate": None,
        },
        "questions": {
            "description": "¿Cuál es la descripción de la transacción?",
            "amount": "¿Cuál es el monto?",
            "transaction_type": "¿Es ingreso o gasto? Responde: income o expense.",
            "category": "¿Qué categoría le pongo?",
        },
    },
    "create_payroll_event": {
        "label": "evento de planilla",
        "required": ["event_type", "hours"],
        "optional_defaults": {"description": "Registrado por chat"},
        "questions": {
            "event_type": "¿Qué tipo de evento es? Ejemplo: ot, vgh, holiday o regular.",
            "hours": "¿Cuántas horas son?",
        },
    },
    "create_employment_profile": {
        "label": "perfil laboral",
        "required": ["hourly_rate", "regular_hours_per_week"],
        "optional_defaults": {"overtime_multiplier": 1.5, "holiday_multiplier": 2},
        "questions": {
            "hourly_rate": "¿Cuánto vale tu hora?",
            "regular_hours_per_week": "¿Cuántas horas regulares trabajas por semana?",
        },
    },
    "create_goal": {
        "label": "meta financiera",
        "required": ["name", "target_amount"],
        "optional_defaults": {"current_amount": 0, "target_date": None, "priority": "medium"},
        "questions": {
            "name": "¿Cómo se llama la meta?",
            "target_amount": "¿Cuál es el monto objetivo de la meta?",
        },
    },
}

FIELD_LABELS = {
    "name": "nombre",
    "total_amount": "monto total",
    "remaining_amount": "saldo pendiente",
    "monthly_payment": "cuota mensual",
    "interest_rate": "interés",
    "term_months": "plazo en meses",
    "payment_day": "día de pago",
    "amount": "monto",
    "source": "fuente",
    "category": "categoría",
    "expense_type": "tipo de gasto",
    "description": "descripción",
    "transaction_date": "fecha",
    "transaction_type": "tipo",
    "account": "cuenta",
    "event_type": "tipo de evento",
    "hours": "horas",
    "hourly_rate": "valor por hora",
    "regular_hours_per_week": "horas regulares por semana",
    "target_amount": "monto objetivo",
    "current_amount": "monto actual",
    "target_date": "fecha objetivo",
    "priority": "prioridad",
}

NUMERIC_FIELDS = {
    "total_amount", "remaining_amount", "monthly_payment", "interest_rate",
    "amount", "hours", "hourly_rate", "regular_hours_per_week",
    "overtime_multiplier", "holiday_multiplier", "target_amount", "current_amount",
}
INTEGER_FIELDS = {"term_months", "payment_day"}
TYPE_ALIASES = {
    "ingreso": "income",
    "entrada": "income",
    "income": "income",
    "gasto": "expense",
    "salida": "expense",
    "expense": "expense",
    "egreso": "expense",
}


def _normalize_text(text: str) -> str:
    return text.strip().lower()


def _is_yes(text: str) -> bool:
    return _normalize_text(text).replace(".", "") in YES_WORDS


def _is_no(text: str) -> bool:
    return _normalize_text(text).replace(".", "") in NO_WORDS


def _extract_number(text: str) -> float | None:
    cleaned = text.lower()
    cleaned = cleaned.replace("₡", "").replace("$", "").replace("colones", "")
    cleaned = cleaned.replace("mil", "000") if re.fullmatch(r"\s*\d+\s*mil\s*", cleaned) else cleaned
    match = re.search(r"-?\d+(?:[.,]\d+)*", cleaned)
    if not match:
        return None
    number = match.group(0)
    if "," in number and "." in number:
        number = number.replace(",", "")
    elif "," in number:
        number = number.replace(",", "")
    return float(number)


def _coerce_field(field: str, text: str):
    value = text.strip()

    if field in NUMERIC_FIELDS:
        number = _extract_number(value)
        if number is None:
            raise ValueError(f"Necesito un número válido para {FIELD_LABELS.get(field, field)}.")
        return number

    if field in INTEGER_FIELDS:
        number = _extract_number(value)
        if number is None:
            raise ValueError(f"Necesito un número entero válido para {FIELD_LABELS.get(field, field)}.")
        return int(number)

    if field == "transaction_type":
        normalized = _normalize_text(value)
        return TYPE_ALIASES.get(normalized, normalized)

    if field == "event_type":
        normalized = _normalize_text(value)
        if "extra" in normalized:
            return "ot"
        if "vac" in normalized:
            return "vgh"
        if "feriado" in normalized:
            return "holiday"
        return normalized

    if field == "priority":
        normalized = _normalize_text(value)
        if normalized in {"critical", "high", "medium", "low"}:
            return normalized
        if "alta" in normalized:
            return "high"
        if "baja" in normalized:
            return "low"
        if "crit" in normalized:
            return "critical"
        return "medium"

    return value


def _initial_payload(action_type: str, user_message: str) -> dict[str, Any]:
    payload = {}
    text = user_message.strip()
    lower = text.lower()
    amount = _extract_number(text)

    if action_type == "create_debt":
        # Ejemplo: "agrega una deuda BAC de 500000"
        if amount is not None:
            payload["total_amount"] = amount
        cleaned = re.sub(r"\b(agrega|agregar|registrar|registra|crear|crea|deuda|prestamo|préstamo|de|por|₡|colones)\b", " ", lower)
        cleaned = re.sub(r"\d+(?:[.,]\d+)*", " ", cleaned).strip()
        if cleaned and len(cleaned) <= 50:
            payload["name"] = cleaned.upper()

    elif action_type in {"create_saving", "create_investment"}:
        if amount is not None:
            payload["amount"] = amount

    elif action_type == "create_expense":
        if amount is not None:
            payload["amount"] = amount
        if "fijo" in lower:
            payload["expense_type"] = "fixed"
        elif "único" in lower or "unico" in lower:
            payload["expense_type"] = "one_time"

    elif action_type in {"create_income", "create_bonus"}:
        if amount is not None:
            payload["amount"] = amount

    elif action_type == "create_payroll_event":
        if "vgh" in lower or "vac" in lower:
            payload["event_type"] = "vgh"
        elif "feriado" in lower:
            payload["event_type"] = "holiday"
        elif "ot" in lower or "extra" in lower:
            payload["event_type"] = "ot"
        if amount is not None:
            payload["hours"] = amount

    elif action_type == "create_employment_profile":
        if amount is not None:
            payload["hourly_rate"] = amount

    elif action_type == "create_goal":
        if amount is not None:
            payload["target_amount"] = amount

    return payload


def _missing_required(action_type: str, payload: dict[str, Any]) -> list[str]:
    config = ACTION_CONFIG[action_type]
    return [field for field in config["required"] if payload.get(field) in (None, "")]


def _next_question(action_type: str, missing_fields: list[str]) -> str:
    config = ACTION_CONFIG[action_type]
    if not missing_fields:
        return "¿Confirmo y guardo esta información? Responde sí o no."
    field = missing_fields[0]
    return config["questions"].get(field, f"¿Cuál es el valor de {FIELD_LABELS.get(field, field)}?")


def _format_payload(action_type: str, payload: dict[str, Any]) -> str:
    config = ACTION_CONFIG[action_type]
    lines = [f"Voy a guardar esta {config['label']}:"]
    ordered = config["required"] + list(config["optional_defaults"].keys())

    for field in ordered:
        value = payload.get(field)
        if value not in (None, ""):
            label = FIELD_LABELS.get(field, field)
            if isinstance(value, (int, float)) and field not in {"term_months", "payment_day", "hours", "regular_hours_per_week"}:
                lines.append(f"- {label}: ₡{value:,.2f}")
            else:
                lines.append(f"- {label}: {value}")

    lines.append("¿Confirmo y guardo? Responde sí o no.")
    return "\n".join(lines)


def _apply_defaults(action_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    config = ACTION_CONFIG[action_type]
    final = dict(config["optional_defaults"])
    final.update(payload)

    if action_type == "create_debt" and final.get("remaining_amount") is None:
        final["remaining_amount"] = final.get("total_amount", 0)

    if action_type == "create_transaction" and final.get("transaction_date") is None:
        final["transaction_date"] = date.today().isoformat()

    return final


def _save_action(action_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    final = _apply_defaults(action_type, payload)

    if action_type == "create_debt":
        return add_debt(
            name=final["name"],
            debt_type=final.get("debt_type", "other"),
            total_amount=final["total_amount"],
            remaining_amount=final["remaining_amount"],
            monthly_payment=final["monthly_payment"],
            interest_rate=final.get("interest_rate", 0),
            term_months=final.get("term_months"),
            payment_day=final.get("payment_day"),
        )

    if action_type == "create_saving":
        return add_saving(name=final["name"], amount=final["amount"])

    if action_type == "create_investment":
        return add_investment(name=final["name"], amount=final["amount"])

    if action_type == "create_expense":
        return add_expense(
            category=final["category"],
            amount=final["amount"],
            expense_type=final.get("expense_type", "variable"),
            description=final.get("description", ""),
        )

    if action_type == "create_income":
        return add_salary(amount=final["amount"], source=final["source"])

    if action_type == "create_bonus":
        return add_bonus(amount=final["amount"], description=final.get("description", ""))

    if action_type == "create_transaction":
        return create_transaction(
            transaction_date=final["transaction_date"],
            description=final["description"],
            amount=final["amount"],
            transaction_type=final["transaction_type"],
            category=final["category"],
            account=final.get("account", ""),
            source=final.get("source", "chat"),
            notes=final.get("notes", "Registrado por JARVIS Chat"),
            original_amount=final.get("original_amount"),
            original_currency=final.get("original_currency"),
            exchange_rate=final.get("exchange_rate"),
        )

    if action_type == "create_payroll_event":
        return add_payroll_event(
            event_type=final["event_type"],
            hours=final["hours"],
            description=final.get("description", ""),
        )

    if action_type == "create_employment_profile":
        return set_employment_profile(
            hourly_rate=final["hourly_rate"],
            regular_hours_per_week=final["regular_hours_per_week"],
            overtime_multiplier=final.get("overtime_multiplier", 1.5),
            holiday_multiplier=final.get("holiday_multiplier", 2),
        )

    if action_type == "create_goal":
        return add_financial_goal(
            name=final["name"],
            target_amount=final["target_amount"],
            current_amount=final.get("current_amount", 0),
            target_date=final.get("target_date"),
            priority=final.get("priority", "medium"),
        )

    raise ValueError(f"Acción no soportada: {action_type}")


def start_action(action_type: str, user_message: str) -> dict[str, Any]:
    if action_type not in ACTION_CONFIG:
        return {
            "message": "Señor, todavía no puedo guardar ese tipo de dato desde el chat.",
            "status": "ERROR",
            "pending": False,
            "action_type": action_type,
        }

    payload = _initial_payload(action_type, user_message)
    missing = _missing_required(action_type, payload)
    current_field = missing[0] if missing else "confirm"
    action = create_pending_action(action_type, payload, missing, current_field)

    if missing:
        message = _next_question(action_type, missing)
    else:
        message = _format_payload(action_type, _apply_defaults(action_type, payload))

    return {
        "message": message,
        "status": "PENDING",
        "pending": True,
        "action_type": action_type,
        "data": action,
    }


def continue_pending_action(user_message: str) -> dict[str, Any] | None:
    action = get_pending_action()
    if not action:
        return None

    action_type = action["action_type"]
    payload = action.get("payload", {}) or {}
    missing = action.get("missing_fields", []) or []
    current_field = action.get("current_field")

    if _is_no(user_message):
        finish_pending_action(action["id"], "cancelled")
        return {
            "message": "Listo, cancelé el registro. No guardé nada.",
            "status": "CANCELLED",
            "pending": False,
            "action_type": action_type,
        }

    if current_field == "confirm" or not missing:
        if _is_yes(user_message):
            result = _save_action(action_type, payload)
            finish_pending_action(action["id"], "completed")
            return {
                "message": "Listo, señor. Guardé la información correctamente en Supabase.",
                "status": "OK",
                "pending": False,
                "action_type": action_type,
                "data": result,
            }

        return {
            "message": "Necesito confirmación para guardar. Responde sí para guardar o no para cancelar.",
            "status": "PENDING",
            "pending": True,
            "action_type": action_type,
            "data": action,
        }

    field = missing[0]

    try:
        payload[field] = _coerce_field(field, user_message)
    except ValueError as error:
        return {
            "message": str(error),
            "status": "PENDING",
            "pending": True,
            "action_type": action_type,
            "data": action,
        }

    missing = _missing_required(action_type, payload)
    current_field = missing[0] if missing else "confirm"
    update_pending_action(action["id"], payload, missing, current_field)

    if missing:
        message = _next_question(action_type, missing)
    else:
        message = _format_payload(action_type, _apply_defaults(action_type, payload))

    return {
        "message": message,
        "status": "PENDING",
        "pending": True,
        "action_type": action_type,
        "data": {
            **action,
            "payload": payload,
            "missing_fields": missing,
            "current_field": current_field,
        },
    }
