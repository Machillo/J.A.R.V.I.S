from __future__ import annotations

import math
import re
import unicodedata
from datetime import date, datetime
from typing import Any

from backend.ai.chat_memory import create_pending_action, finish_pending_action, update_pending_action
from backend.auth.current_user import get_current_user_id
from backend.core.database import get_connection
from backend.finance.service import get_debts, get_financial_cycle_report
from backend.goals.service import add_financial_goal

YES_WORDS = {"si", "sí", "ok", "dale", "confirmo", "agregala", "agrégala", "agregar", "guardala", "guárdala", "acepto"}
NO_WORDS = {"no", "cancelar", "cancela", "despues", "después", "aun no", "todavia no", "todavía no"}
IMPORTANCE_LEVELS = {
    "critical": {"label": "crítica", "weight": 1.0},
    "high": {"label": "alta", "weight": 0.75},
    "medium": {"label": "media", "weight": 0.45},
    "low": {"label": "baja", "weight": 0.2},
}


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value or "")
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", _strip_accents(value or "").lower()).strip()


def _money(value: Any) -> str:
    try:
        return f"₡{float(value or 0):,.0f}".replace(",", ".")
    except Exception:
        return "₡0"


def _parse_number(raw: str | None) -> float | None:
    if not raw:
        return None
    text = _norm(raw).replace("₡", "").replace("crc", "").replace("colones", "").strip()
    is_mil = bool(re.search(r"\bmil\b", text))
    text = re.sub(r"\bmil\b", "", text).strip()
    text = re.sub(r"[^0-9,.]", "", text)
    if not text:
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
    elif "," in text:
        tail = text.split(",")[-1]
        text = text.replace(",", ".") if len(tail) in {1, 2} else text.replace(",", "")
    elif "." in text:
        parts = text.split(".")
        if len(parts) > 2 or (len(parts[-1]) == 3 and len(parts[0]) <= 3):
            text = text.replace(".", "")
    try:
        value = float(text)
    except ValueError:
        return None
    return value * 1000 if is_mil else value


def extract_amount(message: str) -> float | None:
    text = message or ""
    patterns = [
        r"(?:₡|crc|colones?)\s*([0-9][0-9.,]*(?:\s*mil)?)",
        r"([0-9][0-9.,]*\s*mil)\b",
        r"\b([0-9]{4,}[0-9.,]*)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            amount = _parse_number(match.group(1))
            if amount and amount > 0:
                return amount
    return None


def extract_months(message: str) -> int | None:
    text = _norm(message)
    match = re.search(r"(\d{1,2})\s*(?:meses|cuotas|mes)", text)
    if match:
        value = int(match.group(1))
        if 1 <= value <= 72:
            return value
    return None


def extract_importance(message: str) -> str | None:
    text = _norm(message)
    if any(word in text for word in ["critica", "critico", "urgente", "obligatoria", "obligatorio", "vital"]):
        return "critical"
    if any(word in text for word in ["alta", "alto", "importante", "prioridad"]):
        return "high"
    if any(word in text for word in ["media", "medio", "normal", "util", "útil"]):
        return "medium"
    if any(word in text for word in ["baja", "bajo", "leve", "capricho", "gusto", "antojo", "no es importante"]):
        return "low"
    return None


def extract_payment_method(message: str) -> str:
    text = _norm(message)
    if "tasa cero" in text or "taza cero" in text or "sin interes" in text or "sin intereses" in text:
        return "tasa_cero"
    if "minicuota" in text or "mini cuota" in text or "mini-cuota" in text:
        return "minicuotas"
    return "contado"


def _parse_year_from_text(text: str) -> int | None:
    match = re.search(r"\b(20\d{2})\b", text)
    if match:
        return int(match.group(1))
    norm = _norm(text)
    today = date.today()
    if "otro ano" in norm or "otro año" in (text or "").lower() or "proximo ano" in norm or "proximo año" in (text or "").lower():
        return today.year + 1
    if "este ano" in norm or "este año" in (text or "").lower():
        return today.year
    return None


def extract_target_date(message: str) -> str | None:
    text = _norm(message)
    months = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
        "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
        "noviembre": 11, "diciembre": 12,
    }
    year = _parse_year_from_text(message)
    for name, month in months.items():
        if name in text:
            return date(year or date.today().year, month, 15).isoformat()
    explicit = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", message or "")
    if explicit:
        day = int(explicit.group(1))
        month = int(explicit.group(2))
        raw_year = explicit.group(3)
        parsed_year = int(raw_year) if raw_year else (year or date.today().year)
        if parsed_year < 100:
            parsed_year += 2000
        try:
            return date(parsed_year, month, day).isoformat()
        except ValueError:
            return None
    return None


def extract_destination(message: str) -> str | None:
    text = message or ""
    patterns = [
        r"(?:quiero|me gustaria|me gustaría|puedo|podria|podría)\s+(?:ir|viajar)\s+a\s+([^,?.!]+)",
        r"(?:viaje|viajar)\s+a\s+([^,?.!]+)",
        r"\ba\s+(monaco|mónaco|japon|japón|ecuador|mexico|méxico|colombia|italia|espana|españa|francia)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            raw = match.group(1).strip()
            raw = re.sub(r"\b(en|para|por|con|el|la|los|las|este|otro|proximo|próximo)\b.*$", "", raw, flags=re.I).strip()
            return raw.title() if raw else None
    known = {
        "monaco": "Mónaco", "mónaco": "Mónaco", "japon": "Japón", "japón": "Japón",
        "ecuador": "Ecuador", "mexico": "México", "méxico": "México", "colombia": "Colombia",
    }
    norm = _norm(text)
    for key, label in known.items():
        if _norm(key) in norm:
            return label
    return None


def _get_cycle_financial_context() -> dict[str, Any]:
    try:
        cycle = get_financial_cycle_report() or {}
    except Exception:
        cycle = {}
    income = float((cycle.get("income") or {}).get("expected_total") or 0)
    expenses = float((cycle.get("expenses") or {}).get("current_period") or 0)
    debt_payments = float((cycle.get("debts") or {}).get("payments_current_period") or 0)
    goals_reserved = float((cycle.get("goals") or {}).get("reserved_current_period") or 0)
    real_balance = float((cycle.get("cashflow") or {}).get("real_balance") or 0)
    strategic_surplus_before_goals = income - expenses - debt_payments
    return {
        "cycle": cycle,
        "income": income,
        "expenses": expenses,
        "debt_payments": debt_payments,
        "goals_reserved": goals_reserved,
        "real_balance": real_balance,
        "strategic_surplus_before_goals": strategic_surplus_before_goals,
        "free_after_critical_goals": strategic_surplus_before_goals - goals_reserved,
    }


def _fetch_active_goals() -> list[dict[str, Any]]:
    user_id = get_current_user_id()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, target_amount, current_amount, target_date, priority, status
            FROM financial_goals
            WHERE user_id = %s
              AND COALESCE(status, 'active') = 'active'
            ORDER BY target_date ASC NULLS LAST, id ASC
            """,
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _critical_goals_summary() -> tuple[list[dict[str, Any]], float]:
    items = []
    monthly_required = 0.0
    today = date.today()
    for goal in _fetch_active_goals():
        priority = str(goal.get("priority") or "medium").lower()
        if priority not in {"critical", "critica", "crítica"}:
            continue
        target = float(goal.get("target_amount") or 0)
        current = float(goal.get("current_amount") or 0)
        remaining = max(target - current, 0)
        target_date = goal.get("target_date")
        months = 12
        if target_date:
            try:
                d = datetime.fromisoformat(str(target_date)[:10]).date()
                months = max(1, (d.year - today.year) * 12 + d.month - today.month + (1 if d.day > today.day else 0))
            except Exception:
                months = 12
        required = remaining / months if months else remaining
        monthly_required += required
        items.append({**goal, "remaining_amount": remaining, "months_left": months, "monthly_required": required})
    return items, monthly_required


def _estimate_travel_cost(destination: str | None, message: str = "") -> dict[str, Any]:
    dest = _norm(destination or message)
    if "monaco" in dest or "mónaco" in (destination or "").lower():
        total = 3_000_000
        breakdown = {"vuelos": 950_000, "hospedaje": 850_000, "entradas/evento": 750_000, "alimentacion": 250_000, "transporte/extras": 200_000}
    elif "japon" in dest or "japón" in (destination or "").lower():
        total = 1_800_000
        breakdown = {"vuelos": 900_000, "hospedaje": 450_000, "alimentacion": 250_000, "transporte/extras": 200_000}
    elif "ecuador" in dest:
        total = 600_000
        breakdown = {"vuelos": 280_000, "hospedaje": 150_000, "alimentacion": 100_000, "transporte/extras": 70_000}
    elif "mexico" in dest or "méxico" in (destination or "").lower():
        total = 700_000
        breakdown = {"vuelos": 320_000, "hospedaje": 180_000, "alimentacion": 120_000, "transporte/extras": 80_000}
    elif "colombia" in dest:
        total = 500_000
        breakdown = {"vuelos": 220_000, "hospedaje": 130_000, "alimentacion": 90_000, "transporte/extras": 60_000}
    else:
        total = 1_000_000
        breakdown = {"vuelos": 450_000, "hospedaje": 250_000, "alimentacion": 180_000, "transporte/extras": 120_000}
    return {"estimated_total": total, "breakdown": breakdown, "source": "heuristic_v1"}


def _months_to_date(target_date: str | None) -> int | None:
    if not target_date:
        return None
    try:
        target = datetime.fromisoformat(str(target_date)[:10]).date()
    except Exception:
        return None
    today = date.today()
    months = (target.year - today.year) * 12 + (target.month - today.month)
    if target.day > today.day:
        months += 1
    return max(months, 1)


def _target_year_from_months(months: int) -> int:
    today = date.today()
    year = today.year + ((today.month - 1 + months) // 12)
    return year


def is_personal_decision_request(message: str) -> bool:
    text = _norm(message)
    purchase_signals = ["puedo comprar", "deberia comprar", "debería comprar", "vale la pena comprar", "me compro", "comprar", "minicuotas", "mini cuotas", "tasa cero", "taza cero"]
    travel_signals = ["quiero ir", "quiero viajar", "viajar a", "viaje a", "me gustaria ir", "me gustaría ir", "monaco", "mónaco", "japon", "japón"]
    return any(s in text for s in purchase_signals) or any(s in text for s in travel_signals)


def classify_decision_request(message: str) -> str | None:
    text = _norm(message)
    if any(s in text for s in ["quiero ir", "quiero viajar", "viajar a", "viaje a", "me gustaria ir", "monaco", "mónaco", "japon", "japón"]):
        return "travel"
    if any(s in text for s in ["puedo comprar", "deberia comprar", "vale la pena comprar", "comprar", "minicuotas", "mini cuotas", "tasa cero", "taza cero"]):
        return "purchase"
    return None


def _ask_importance(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    create_pending_action(f"decision_collect_{kind}", payload, ["importance"], "importance")
    label = "viaje" if kind == "travel" else "compra"
    return {
        "message": f"Señor, ¿qué importancia tiene este {label}: crítica, alta, media o baja?",
        "intent": f"{kind}_decision",
        "status": "PENDING_IMPORTANCE",
        "pending": True,
        "data": payload,
    }


def _ask_amount(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    create_pending_action(f"decision_collect_{kind}", payload, ["amount"], "amount")
    label = payload.get("destination") or payload.get("item") or ("viaje" if kind == "travel" else "compra")
    return {
        "message": f"Señor, ¿cuánto cuesta aproximadamente {label}?",
        "intent": f"{kind}_decision",
        "status": "PENDING_AMOUNT",
        "pending": True,
        "data": payload,
    }


def _purchase_item_from_message(message: str) -> str:
    text = re.sub(r"[¿?]", "", message or "", flags=re.I).strip()
    text = re.sub(r".*?(?:comprar|compro|comprarme)\s+", "", text, flags=re.I)
    text = re.sub(r"\s+(?:de|por|en)\s+(?:₡|crc|colones?)?.*$", "", text, flags=re.I).strip()
    return text[:80] or "compra"


def _evaluate_purchase(payload: dict[str, Any]) -> dict[str, Any]:
    amount = float(payload.get("amount") or 0)
    importance = payload.get("importance") or "medium"
    method = payload.get("payment_method") or "contado"
    months = int(payload.get("months") or 1)
    item = payload.get("item") or "compra"
    ctx = _get_cycle_financial_context()
    goals, critical_required = _critical_goals_summary()
    surplus_before_goals = ctx["strategic_surplus_before_goals"]
    free_after_goals = surplus_before_goals - critical_required
    monthly_impact = amount
    estimated_interest = 0.0
    if method == "tasa_cero":
        months = max(months, 1)
        monthly_impact = amount / months
    elif method == "minicuotas":
        months = max(months, 3)
        annual_rate = 0.22
        estimated_interest = amount * annual_rate * (months / 12)
        monthly_impact = (amount + estimated_interest) / months

    approved = False
    warning = ""
    if importance == "critical":
        approved = monthly_impact <= max(surplus_before_goals, 0)
        warning = "compite contra pagos del ciclo" if not approved else "prioridad crítica cubierta"
    elif importance == "high":
        approved = monthly_impact <= max(free_after_goals * 0.8, 0)
        warning = "solo si no compromete la meta crítica" if not approved else "viable con control"
    elif importance == "medium":
        approved = monthly_impact <= max(free_after_goals * 0.45, 0)
        warning = "puede esperar si Ecuador sigue crítico" if not approved else "viable, pero controlado"
    else:
        approved = monthly_impact <= max(free_after_goals * 0.15, 0) and free_after_goals > 0
        warning = "no es prioridad frente a Ecuador/deuda" if not approved else "viable porque el impacto es pequeño"

    method_note = ""
    if method == "tasa_cero":
        method_note = f"Tasa cero: {_money(monthly_impact)} por {months} meses, sin interés."
    elif method == "minicuotas":
        method_note = f"Minicuotas: cuota estimada {_money(monthly_impact)} por {months} meses; costo extra aprox. {_money(estimated_interest)}."
    else:
        method_note = f"Contado: impacto inmediato {_money(amount)}."

    status = "APROBADA" if approved else "NO RECOMENDADA"
    message = (
        f"Señor, decisión sobre {item}: {status}.\n"
        f"Monto: {_money(amount)}. Importancia: {IMPORTANCE_LEVELS.get(importance, {}).get('label', importance)}.\n"
        f"Excedente antes de metas críticas: {_money(surplus_before_goals)}. Meta crítica mensual requerida: {_money(critical_required)}.\n"
        f"{method_note}\n"
        f"Criterio: {warning}."
    )
    if not approved and method == "contado" and importance in {"medium", "high"}:
        message += " Si es necesario, revise tasa cero corta antes que minicuotas."
    return {"message": message, "status": "OK", "pending": False, "intent": "purchase_decision", "data": {"payload": payload, "financial_context": ctx, "critical_goals": goals}}


def _evaluate_travel(payload: dict[str, Any], *, create_goal_prompt: bool = True) -> dict[str, Any]:
    destination = payload.get("destination") or "viaje"
    importance = payload.get("importance") or "medium"
    target_date = payload.get("target_date")
    estimate = _estimate_travel_cost(destination, payload.get("original_message", ""))
    total = float(payload.get("amount") or estimate["estimated_total"])
    ctx = _get_cycle_financial_context()
    _, critical_required = _critical_goals_summary()
    free_after_current_critical = max(ctx["strategic_surplus_before_goals"] - critical_required, 0)
    priority_multiplier = {"critical": 1.0, "high": 0.7, "medium": 0.4, "low": 0.2}.get(importance, 0.4)
    monthly_capacity = max(free_after_current_critical * priority_multiplier, 0)
    if monthly_capacity <= 0:
        monthly_capacity = 0

    desired_months = _months_to_date(target_date)
    required_for_desired = total / desired_months if desired_months else None
    scenarios = []
    for name, factor in [("Conservador", 0.5), ("Realista", 1.0), ("Agresivo", 1.6)]:
        monthly = monthly_capacity * factor
        if monthly <= 0:
            months = 120
            monthly_needed = math.ceil(total / months)
            scenarios.append({"name": name, "monthly_saving": monthly_needed, "months": months, "target_year": _target_year_from_months(months), "needs_new_cashflow": True})
        else:
            months = max(1, math.ceil(total / monthly))
            scenarios.append({"name": name, "monthly_saving": monthly, "months": months, "target_year": _target_year_from_months(months), "needs_new_cashflow": False})

    breakdown_lines = ", ".join(f"{k}: {_money(v)}" for k, v in estimate["breakdown"].items())
    importance_label = IMPORTANCE_LEVELS.get(importance, {}).get("label", importance)
    message_lines = [
        f"Señor, proyección para {destination}.",
        f"Costo estimado: {_money(total)} ({breakdown_lines}).",
        f"Importancia: {importance_label}. Excedente libre después de metas críticas actuales: {_money(free_after_current_critical)}.",
    ]
    if target_date and required_for_desired is not None:
        viable = monthly_capacity >= required_for_desired
        message_lines.append(f"Fecha deseada: {target_date}. Requiere {_money(required_for_desired)}/mes. {'Viable' if viable else 'No viable con el flujo actual; hay que mover fecha o liberar dinero' }.")
    else:
        message_lines.append("No indicó fecha objetivo; uso ventanas conservadora, realista y agresiva.")
    message_lines.append("Escenarios:")
    for item in scenarios:
        suffix = "requiere liberar flujo" if item.get("needs_new_cashflow") else ""
        message_lines.append(f"- {item['name']}: {_money(item['monthly_saving'])}/mes → {item['months']} meses, aprox. {item['target_year']} {suffix}".strip())
    message_lines.append("¿Desea que agregue esta meta de viaje en Metas?")

    if create_goal_prompt:
        create_pending_action(
            "decision_confirm_travel_goal",
            {
                "name": f"Viaje a {destination}",
                "target_amount": total,
                "current_amount": 0,
                "target_date": target_date,
                "priority": importance,
                "source": "travel_decision_engine",
            },
            [],
            "confirm",
        )
    return {"message": "\n".join(message_lines), "status": "OK", "pending": bool(create_goal_prompt), "intent": "travel_decision", "data": {"payload": payload, "estimate": estimate, "scenarios": scenarios, "financial_context": ctx}}


def handle_decision_pending_action(action: dict[str, Any], user_message: str) -> dict[str, Any] | None:
    action_type = action.get("action_type")
    if not str(action_type or "").startswith("decision_"):
        return None
    payload = action.get("payload") or {}
    current = action.get("current_field")
    lower = _norm(user_message)

    if action_type == "decision_confirm_travel_goal":
        if lower in NO_WORDS or lower.startswith("no "):
            finish_pending_action(action["id"], "cancelled")
            return {"message": "Listo, Señor. No guardé la meta.", "intent": action_type, "status": "CANCELLED", "pending": False, "data": payload}
        if lower in YES_WORDS or lower.startswith("si ") or lower.startswith("sí ") or any(word in lower for word in {"agregala", "agrégala", "guardala", "guárdala"}):
            result = add_financial_goal(
                name=payload.get("name") or "Viaje",
                target_amount=float(payload.get("target_amount") or 0),
                current_amount=float(payload.get("current_amount") or 0),
                target_date=payload.get("target_date"),
                priority=payload.get("priority") or "medium",
            )
            finish_pending_action(action["id"], "completed")
            return {"message": f"Listo, Señor. Agregué la meta: {result.get('name')} por {_money(result.get('target_amount'))}.", "intent": "create_goal", "status": "OK", "pending": False, "data": result}
        return {"message": "Señor, responda sí para agregar la meta o no para descartarla.", "intent": action_type, "status": "PENDING", "pending": True, "data": payload}

    if lower in {"cancelar", "cancela", "olvida", "salir"}:
        finish_pending_action(action["id"], "cancelled")
        return {"message": "Listo, Señor. Cancelé la evaluación.", "intent": action_type, "status": "CANCELLED", "pending": False, "data": payload}

    if current == "amount":
        amount = extract_amount(user_message)
        if not amount:
            return {"message": "Señor, necesito el monto aproximado.", "intent": action_type, "status": "PENDING_AMOUNT", "pending": True, "data": payload}
        payload["amount"] = amount
    elif current == "importance":
        importance = extract_importance(user_message)
        if not importance:
            return {"message": "Señor, indique la importancia: crítica, alta, media o baja.", "intent": action_type, "status": "PENDING_IMPORTANCE", "pending": True, "data": payload}
        payload["importance"] = importance
    else:
        # Intento flexible: si el usuario respondió con todo en una frase.
        payload["amount"] = payload.get("amount") or extract_amount(user_message)
        payload["importance"] = payload.get("importance") or extract_importance(user_message)

    kind = "travel" if action_type.endswith("travel") else "purchase"
    missing = []
    if kind == "purchase" and not payload.get("amount"):
        missing.append("amount")
    if not payload.get("importance"):
        missing.append("importance")
    if missing:
        update_pending_action(action["id"], payload, missing, missing[0])
        return _ask_amount(kind, payload) if missing[0] == "amount" else _ask_importance(kind, payload)

    finish_pending_action(action["id"], "completed")
    if kind == "travel":
        return _evaluate_travel(payload, create_goal_prompt=True)
    return _evaluate_purchase(payload)


def handle_personal_decision_request(message: str) -> dict[str, Any] | None:
    kind = classify_decision_request(message)
    if not kind:
        return None

    if kind == "purchase":
        payload = {
            "kind": "purchase",
            "item": _purchase_item_from_message(message),
            "amount": extract_amount(message),
            "importance": extract_importance(message),
            "payment_method": extract_payment_method(message),
            "months": extract_months(message) or (3 if extract_payment_method(message) == "tasa_cero" else 1),
            "original_message": message,
        }
        if not payload.get("amount"):
            return _ask_amount("purchase", payload)
        if not payload.get("importance"):
            return _ask_importance("purchase", payload)
        return _evaluate_purchase(payload)

    if kind == "travel":
        payload = {
            "kind": "travel",
            "destination": extract_destination(message) or "viaje",
            "target_date": extract_target_date(message),
            "importance": extract_importance(message),
            "amount": extract_amount(message),
            "original_message": message,
        }
        if not payload.get("importance"):
            return _ask_importance("travel", payload)
        return _evaluate_travel(payload, create_goal_prompt=True)

    return None
