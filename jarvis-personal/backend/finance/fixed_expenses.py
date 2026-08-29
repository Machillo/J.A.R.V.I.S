from __future__ import annotations

import json
import re
import unicodedata
from calendar import monthrange
from datetime import date, datetime
from typing import Any

from backend.auth.current_user import get_current_user_id
from backend.auth.workspace_context import get_current_workspace_id
from backend.core.database import get_connection


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _month_bounds(month: str | None = None) -> tuple[str, str, str]:
    if not month:
        today = date.today()
        year, month_number = today.year, today.month
    else:
        year_str, month_str = str(month).split("-", 1)
        year, month_number = int(year_str), int(month_str)
    last_day = monthrange(year, month_number)[1]
    month_key = f"{year:04d}-{month_number:02d}"
    return month_key, f"{month_key}-01", f"{month_key}-{last_day:02d}"


def _normalize(value: str | None) -> str:
    text = unicodedata.normalize("NFD", (value or "").lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _decode_aliases(raw_aliases: Any) -> list[str]:
    if raw_aliases is None:
        return []
    if isinstance(raw_aliases, list):
        return [str(item) for item in raw_aliases if str(item).strip()]
    if isinstance(raw_aliases, str):
        try:
            value = json.loads(raw_aliases)
            if isinstance(value, list):
                return [str(item) for item in value if str(item).strip()]
        except Exception:
            return [item.strip() for item in raw_aliases.split(",") if item.strip()]
    return []


def _encode_aliases(aliases: list[str] | None) -> str:
    return json.dumps([alias.strip() for alias in (aliases or []) if alias and alias.strip()])


def _keywords_for(expense: dict[str, Any]) -> list[str]:
    aliases = _decode_aliases(expense.get("aliases"))
    words = [expense.get("name"), expense.get("category"), expense.get("payment_method"), *aliases]
    normalized = []
    for item in words:
        clean = _normalize(str(item or ""))
        if clean and clean not in normalized:
            normalized.append(clean)
    return normalized


def _is_due_this_month(expense: dict[str, Any], month_key: str) -> bool:
    interval = int(expense.get("interval_months") or 1)
    if interval <= 1:
        return True

    start_month = expense.get("start_month")
    if not start_month:
        return True

    start_year, start_number = [int(part) for part in str(start_month).split("-", 1)]
    year, month_number = [int(part) for part in str(month_key).split("-", 1)]
    delta = (year - start_year) * 12 + (month_number - start_number)
    return delta >= 0 and delta % interval == 0


def _due_date_for(expense: dict[str, Any], month_key: str) -> str | None:
    due_day = expense.get("due_day")
    if not due_day:
        return None
    year, month_number = [int(part) for part in month_key.split("-", 1)]
    last_day = monthrange(year, month_number)[1]
    safe_day = min(max(int(due_day), 1), last_day)
    return f"{month_key}-{safe_day:02d}"


def _amount_score(expected: float | None, actual: float) -> tuple[float, str]:
    if not expected or expected <= 0:
        return 0.3, "Monto variable o pendiente de aprender."
    difference = abs(actual - expected)
    tolerance = max(expected * 0.15, 1500)
    if difference <= tolerance:
        return 0.45, "Monto dentro del rango esperado."
    if difference <= max(expected * 0.35, 5000):
        return 0.2, "Monto parecido, requiere revisión."
    return -0.15, "Monto muy distinto al esperado."


def _best_match(expense: dict[str, Any], transactions: list[dict[str, Any]]) -> dict[str, Any] | None:
    keywords = _keywords_for(expense)
    expected = expense.get("expected_amount")
    expected_float = _as_float(expected, None) if expected is not None else None
    best: dict[str, Any] | None = None

    for transaction in transactions:
        haystack = _normalize(" ".join([
            str(transaction.get("description") or ""),
            str(transaction.get("category") or ""),
            str(transaction.get("account") or ""),
            str(transaction.get("notes") or ""),
        ]))
        amount = abs(_as_float(transaction.get("amount")))
        score = 0.0
        reasons = []

        for keyword in keywords:
            if keyword and keyword in haystack:
                score += 0.35
                reasons.append(f"Coincide con '{keyword}'.")
                break

        category_clean = _normalize(expense.get("category"))
        if category_clean and category_clean == _normalize(transaction.get("category")):
            score += 0.15
            reasons.append("Categoría coincide.")

        amount_points, amount_reason = _amount_score(expected_float, amount)
        score += amount_points
        reasons.append(amount_reason)

        if transaction.get("transaction_type") in {"expense", "debt_payment"}:
            score += 0.05

        if score >= 0.45 and (best is None or score > best["confidence"]):
            best = {
                "transaction": transaction,
                "confidence": round(min(score, 1.0), 2),
                "reason": " ".join(reasons),
            }

    return best


def _status_for(expense: dict[str, Any], month_key: str, best: dict[str, Any] | None) -> tuple[str, str]:
    if not _is_due_this_month(expense, month_key):
        return "not_due", "No corresponde este mes por frecuencia."

    if best and best["confidence"] >= 0.68:
        return "paid", best.get("reason") or "Detectado automáticamente."
    if best:
        return "doubtful", best.get("reason") or "Hay una posible coincidencia."

    due_date = _due_date_for(expense, month_key)
    if not due_date:
        return "pending", "No tiene día exacto configurado."

    today = date.today().isoformat()
    if today > due_date:
        return "overdue", "Ya pasó la fecha esperada y no detecté pago."
    return "pending", "Pendiente para este mes."


def list_fixed_expenses(active_only: bool = True) -> list[dict[str, Any]]:
    workspace_id = get_current_workspace_id()
    sql = """
        SELECT *
        FROM fixed_expenses
        WHERE workspace_id = %s
    """
    params: list[Any] = [workspace_id]
    if active_only:
        sql += " AND is_active = TRUE"
    sql += " ORDER BY due_day NULLS LAST, name ASC"

    with get_connection() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()

    for row in rows:
        row["aliases"] = _decode_aliases(row.get("aliases"))
    return rows


def create_fixed_expense(
    name: str,
    category: str,
    expected_amount: float | None = None,
    frequency: str = "monthly",
    due_day: int | None = None,
    payment_method: str = "manual",
    auto_deducted: bool = False,
    aliases: list[str] | None = None,
    notes: str = "",
    interval_months: int = 1,
    start_month: str | None = None,
    currency: str = "CRC",
):
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM fixed_expenses WHERE workspace_id = %s AND name = %s",
            (workspace_id, name),
        ).fetchone()
        if existing:
            expense_id = existing["id"]
            conn.execute(
                """
                UPDATE fixed_expenses
                SET category = %s, expected_amount = %s, currency = %s, frequency = %s,
                    interval_months = %s, start_month = %s, due_day = %s, payment_method = %s,
                    auto_deducted = %s, aliases = %s::jsonb, notes = %s, is_active = TRUE, updated_at = NOW()
                WHERE id = %s AND workspace_id = %s
                """,
                (category, expected_amount, currency, frequency, interval_months, start_month, due_day,
                 payment_method, auto_deducted, _encode_aliases(aliases), notes, expense_id, workspace_id),
            )
        else:
            cursor = conn.execute(
                """
                INSERT INTO fixed_expenses (
                    user_id, workspace_id, name, category, expected_amount, currency, frequency,
                    interval_months, start_month, due_day, payment_method, auto_deducted, aliases,
                    notes, is_active, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, TRUE, NOW(), NOW())
                RETURNING id
                """,
                (user_id, workspace_id, name, category, expected_amount, currency, frequency,
                 interval_months, start_month, due_day, payment_method, auto_deducted,
                 _encode_aliases(aliases), notes),
            )
            expense_id = cursor.lastrowid
        conn.commit()

    return get_fixed_expense(expense_id)


def get_fixed_expense(expense_id: int) -> dict[str, Any] | None:
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM fixed_expenses
            WHERE id = %s AND workspace_id = %s
            """,
            (expense_id, workspace_id),
        ).fetchone()
    if row:
        row["aliases"] = _decode_aliases(row.get("aliases"))
    return row


def update_fixed_expense(expense_id: int, **updates):
    workspace_id = get_current_workspace_id()
    allowed = {
        "name", "category", "expected_amount", "currency", "frequency",
        "interval_months", "start_month", "due_day", "payment_method",
        "auto_deducted", "aliases", "notes", "is_active",
    }
    clean = {key: value for key, value in updates.items() if key in allowed and value is not None}
    if "aliases" in clean:
        clean["aliases"] = _encode_aliases(clean["aliases"])

    if not clean:
        return get_fixed_expense(expense_id)

    assignments = []
    params: list[Any] = []
    for key, value in clean.items():
        if key == "aliases":
            assignments.append(f"{key} = %s::jsonb")
        else:
            assignments.append(f"{key} = %s")
        params.append(value)
    params.extend([expense_id, workspace_id])

    with get_connection() as conn:
        conn.execute(
            f"""
            UPDATE fixed_expenses
            SET {', '.join(assignments)}, updated_at = NOW()
            WHERE id = %s AND workspace_id = %s
            """,
            tuple(params),
        )
        conn.commit()

    return get_fixed_expense(expense_id)


def delete_fixed_expense(expense_id: int):
    result = update_fixed_expense(expense_id, is_active=False)
    return {"status": "OK", "message": "Gasto fijo desactivado.", "item": result}


def get_fixed_expense_status(month: str | None = None) -> dict[str, Any]:
    workspace_id = get_current_workspace_id()
    month_key, start_date, end_date = _month_bounds(month)
    fixed_expenses = list_fixed_expenses(active_only=True)

    with get_connection() as conn:
        transactions = conn.execute(
            """
            SELECT id, transaction_date, description, amount, transaction_type, category, account, source, notes
            FROM transactions
            WHERE workspace_id = %s
            AND transaction_date::date BETWEEN %s::date AND %s::date
            AND transaction_type IN ('expense', 'debt_payment')
            ORDER BY transaction_date ASC, id ASC
            """,
            (workspace_id, start_date, end_date),
        ).fetchall()

    items = []
    totals = {"expected": 0.0, "paid": 0.0, "pending": 0.0, "overdue": 0.0, "doubtful": 0.0}
    alerts = []
    today = date.today()

    for expense in fixed_expenses:
        due_this_month = _is_due_this_month(expense, month_key)
        expected = _as_float(expense.get("expected_amount"), 0.0)
        best = _best_match(expense, transactions) if due_this_month else None
        status, reason = _status_for(expense, month_key, best)
        matched_transaction = best.get("transaction") if best else None
        matched_amount = _as_float(matched_transaction.get("amount"), 0.0) if matched_transaction else 0.0
        due_date = _due_date_for(expense, month_key)

        if due_this_month:
            totals["expected"] += expected
            if status == "paid":
                totals["paid"] += matched_amount or expected
            elif status in {"pending", "not_due"}:
                totals["pending"] += expected
            elif status == "overdue":
                totals["overdue"] += expected
            elif status == "doubtful":
                totals["doubtful"] += expected

        if status in {"pending", "overdue", "doubtful"} and due_date:
            due_dt = datetime.fromisoformat(due_date).date()
            days_until = (due_dt - today).days
            reminder_days = int(expense.get("reminder_days") or 3)
            if status == "overdue" or days_until <= reminder_days:
                alerts.append({
                    "level": "danger" if status == "overdue" else "warning",
                    "message": f"{expense['name']} está {status}. Fecha esperada: {due_date}.",
                    "fixed_expense_id": expense["id"],
                })

        items.append({
            "fixed_expense": expense,
            "month": month_key,
            "due_date": due_date,
            "due_this_month": due_this_month,
            "status": status,
            "reason": reason,
            "expected_amount": expected,
            "matched_amount": matched_amount,
            "matched_transaction": matched_transaction,
            "confidence": best.get("confidence") if best else 0,
        })

    return {
        "status": "OK",
        "month": month_key,
        "summary": {key: round(value, 2) for key, value in totals.items()},
        "items": items,
        "alerts": alerts,
    }


def seed_owner_fixed_expenses():
    defaults = [
        {"name": "Casa", "category": "Vivienda", "expected_amount": 100000, "due_day": 30, "aliases": ["casa y prestamo", "casa"], "notes": "Aporte mensual a casa."},
        {"name": "Préstamo papá", "category": "Familiar", "expected_amount": 30387.13, "due_day": 30, "aliases": ["prestamo papa", "préstamo papá", "casa y prestamo"], "notes": "Parte de Casa y Préstamo."},
        {"name": "Nutricionista", "category": "Salud", "expected_amount": 40000, "due_day": 14, "interval_months": 2, "start_month": "2026-02", "aliases": ["nutricionista"]},
        {"name": "Préstamo Popular", "category": "Banco Popular", "expected_amount": 65480.40, "auto_deducted": True, "payment_method": "planilla", "aliases": ["popular", "prestamo popular", "banco popular"], "notes": "Rebajo directo de planilla."},
        {"name": "Línea Liberty", "category": "Teléfono", "expected_amount": 33850.86, "due_day": 4, "aliases": ["liberty", "linea", "línea", "pago liberty"]},
        {"name": "Gimnasio", "category": "Salud", "expected_amount": 24950, "due_day": 4, "aliases": ["novo fit", "gimnasio", "gym"]},
        {"name": "Préstamo BAC", "category": "Tarjeta BAC", "expected_amount": 16950, "aliases": ["prestamo bac", "préstamo bac"]},
        {"name": "Reloj", "category": "Reloj", "expected_amount": 7793.30, "due_day": 22, "aliases": ["ishop", "reloj", "tasa cero"]},
        {"name": "Minicuota", "category": "Tarjeta BAC", "expected_amount": 8760, "due_day": 22, "aliases": ["minicuotas", "minicuota", "credomatic minic"]},
        {"name": "PS Plus", "category": "Videojuegos", "expected_amount": 7000, "due_day": 16, "aliases": ["playstation", "ps plus", "playstation network"]},
        {"name": "Seguro tarjeta", "category": "Seguros", "expected_amount": 2950, "due_day": 21, "aliases": ["seguro proteccion", "seguro protección", "bdpc5"]},
        {"name": "Crunchyroll", "category": "Suscripciones", "expected_amount": 3390, "due_day": 8, "aliases": ["crunchyroll"]},
        {"name": "Google One", "category": "Suscripciones", "expected_amount": 5537, "due_day": 22, "aliases": ["google one"]},
        {"name": "iCloud / Apple", "category": "Suscripciones", "expected_amount": None, "aliases": ["apple.com", "icloud", "apple"], "notes": "Monto variable; Jarvis debe aprenderlo con transacciones."},
    ]
    return [create_fixed_expense(**item) for item in defaults]


def _find_by_name(name: str) -> dict[str, Any] | None:
    needle = _normalize(name)
    for item in list_fixed_expenses(active_only=True):
        candidates = [_normalize(item.get("name")), *[_normalize(alias) for alias in item.get("aliases", [])]]
        if any(needle in candidate or candidate in needle for candidate in candidates if candidate):
            return item
    return None


def handle_fixed_expense_message(message: str) -> dict[str, Any]:
    text = _normalize(message)

    if any(word in text for word in ["lista", "estado", "status", "pendiente", "pagado", "recurrentes", "gastos fijos"]):
        status = get_fixed_expense_status()
        return {"status": "OK", "message": format_fixed_expense_status(status), "data": status}

    amount_match = re.search(r"(?:₡|crc|colones?)?\s*(\d{3,}(?:[.,]\d{2})?)", message, re.I)
    amount = float(amount_match.group(1).replace(",", "")) if amount_match else None
    day_match = re.search(r"(?:dia|día)\s*(\d{1,2})", text)
    due_day = int(day_match.group(1)) if day_match else None

    if any(word in text for word in ["cambia", "actualiza", "modifica", "subio", "subió", "bajo", "bajó"]):
        target = None
        for item in list_fixed_expenses(active_only=True):
            if _normalize(item.get("name")) in text or any(_normalize(alias) in text for alias in item.get("aliases", [])):
                target = item
                break
        if not target:
            return {"status": "NEEDS_CLARIFICATION", "message": "¿Cuál gasto fijo desea actualizar?", "data": {}}
        updated = update_fixed_expense(target["id"], expected_amount=amount, due_day=due_day)
        return {"status": "OK", "message": f"Listo. Actualicé {updated['name']}.", "data": updated}

    if any(word in text for word in ["agrega", "agregar", "crea", "crear", "nuevo"]):
        if amount is None:
            return {"status": "NEEDS_AMOUNT", "message": "¿Cuál es el monto esperado?", "data": {}}
        name = re.sub(r".*?(gasto fijo|pago fijo|recurrente)\s*(de)?", "", message, flags=re.I).strip(" .,")
        name = re.sub(r"(?:por|de)?\s*(₡|crc|colones?)?\s*\d{3,}(?:[.,]\d{2})?.*$", "", name, flags=re.I).strip(" .,;")
        if not name:
            return {"status": "NEEDS_NAME", "message": "¿Cómo se llama el gasto fijo?", "data": {}}
        item = create_fixed_expense(name=name, category="Gastos fijos", expected_amount=amount, due_day=due_day, aliases=[name])
        return {"status": "OK", "message": f"Listo. Guardé {name} como gasto fijo.", "data": item}

    status = get_fixed_expense_status()
    return {"status": "OK", "message": format_fixed_expense_status(status), "data": status}


def format_fixed_expense_status(status: dict[str, Any]) -> str:
    summary = status.get("summary", {})
    lines = [
        f"Señor, estos son los gastos fijos de {status.get('month')}:",
        f"- Esperado: ₡{summary.get('expected', 0):,.0f}",
        f"- Pagado/detectado: ₡{summary.get('paid', 0):,.0f}",
        f"- Pendiente: ₡{summary.get('pending', 0):,.0f}",
    ]
    important = [item for item in status.get("items", []) if item.get("status") in {"pending", "overdue", "doubtful"}]
    if important:
        lines.append("Pendientes o dudosos:")
        for item in important[:8]:
            expense = item.get("fixed_expense", {})
            lines.append(f"- {expense.get('name')}: {item.get('status')} · ₡{item.get('expected_amount', 0):,.0f}")
    return "\n".join(lines)
