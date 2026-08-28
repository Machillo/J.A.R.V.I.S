from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from backend.transactions.service import create_transaction


MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

SECTION_ALIASES = {
    "ingresos": "income",
    "ingreso": "income",
    "gastos": "expense",
    "gasto": "expense",
    "deudas": "debt_payment",
    "deuda": "debt_payment",
    "pagos de deuda": "debt_payment",
    "pago de deuda": "debt_payment",
    "inversiones": "investment",
    "inversion": "investment",
    "inversión": "investment",
    "ahorros": "saving",
    "ahorro": "saving",
    "dolares": "expense",
    "dólares": "expense",
    "usd": "expense",
    "pendientes": "pending",
    "pendiente": "pending",
}

TRANSACTION_TYPE_LABELS = {
    "income": "ingresos",
    "expense": "gastos",
    "debt_payment": "pagos de deuda",
    "investment": "inversiones",
    "saving": "ahorros",
}

CATEGORY_MAP = {
    "salario": "Ingresos / Salario",
    "planilla": "Ingresos / Salario",
    "horas extra": "Ingresos / Horas extra",
    "ot": "Ingresos / Horas extra",
    "bono": "Ingresos / Bono",
    "reembolso": "Ingresos / Reembolso",
    "casa": "Gastos fijos / Vivienda",
    "vivienda": "Gastos fijos / Vivienda",
    "luz": "Gastos fijos / Servicios",
    "electricidad": "Gastos variables / Hogar",
    "arreglo electrico": "Gastos variables / Hogar",
    "arreglo eléctrico": "Gastos variables / Hogar",
    "internet": "Gastos fijos / Internet",
    "telefono": "Gastos fijos / Teléfono",
    "teléfono": "Gastos fijos / Teléfono",
    "seguro": "Gastos fijos / Seguros",
    "seguros": "Gastos fijos / Seguros",
    "comida": "Gastos variables / Comida",
    "restaurante": "Gastos variables / Restaurante",
    "uber eats": "Gastos variables / Restaurante",
    "granizados": "Gastos variables / Restaurante",
    "transporte": "Gastos variables / Transporte",
    "uber rides": "Gastos variables / Transporte",
    "uber": "Gastos variables / Transporte",
    "gasolina": "Gastos variables / Gasolina",
    "gasolinera": "Gastos variables / Gasolina",
    "videojuegos": "Gastos variables / Entretenimiento / Videojuegos",
    "gossip harbor": "Gastos variables / Entretenimiento / Videojuegos",
    "kingshot": "Gastos variables / Entretenimiento / Videojuegos",
    "8 ball pool": "Gastos variables / Entretenimiento / Videojuegos",
    "streaming": "Gastos variables / Entretenimiento / Streaming",
    "crunchyroll": "Gastos variables / Entretenimiento / Streaming",
    "suscripcion": "Gastos variables / Entretenimiento / Suscripciones",
    "suscripción": "Gastos variables / Entretenimiento / Suscripciones",
    "google one": "Gastos variables / Entretenimiento / Suscripciones",
    "yousician": "Gastos variables / Entretenimiento / Suscripciones",
    "playstation": "Gastos variables / Entretenimiento / Suscripciones",
    "budge": "Gastos variables / Entretenimiento / Videojuegos",
    "compras": "Gastos variables / Compras",
    "temu": "Gastos variables / Compras",
    "hogar": "Gastos variables / Hogar",
    "aliss": "Gastos variables / Hogar",
    "tecnologia": "Gastos variables / Tecnología",
    "tecnología": "Gastos variables / Tecnología",
    "reycomcell": "Gastos variables / Tecnología",
    "deporte": "Gastos variables / Deporte",
    "gym": "Gastos variables / Deporte",
    "gimnasio": "Gastos variables / Deporte",
    "novo fit": "Gastos variables / Deporte",
    "uno sport": "Gastos variables / Deporte",
    "box": "Gastos variables / Deporte",
    "boxeo": "Gastos variables / Deporte",
    "papá": "Deudas / Familiar",
    "papa": "Deudas / Familiar",
    "familiar": "Deudas / Familiar",
    "bac": "Deudas / Tarjeta BAC",
    "tarjeta bac": "Deudas / Tarjeta BAC",
    "multimoney": "Deudas / MultiMoney",
    "popular": "Deudas / Banco Popular",
    "ibkr": "Inversiones / IBKR",
    "cripto": "Inversiones / Cripto",
    "multimoney inversion": "Inversiones / MultiMoney Inversión",
    "multimoney inversión": "Inversiones / MultiMoney Inversión",
    "fondo emergencia": "Ahorro / Fondo emergencia",
    "viajes": "Ahorro / Viajes",
    "meta personal": "Ahorro / Meta personal",
}

@dataclass
class ParsedImportItem:
    transaction_date: str
    description: str
    amount: float
    transaction_type: str
    category: str
    account: str = ""
    source: str = "chat_monthly_import"
    notes: str = ""
    original_amount: float | None = None
    original_currency: str | None = None
    exchange_rate: float | None = None
    status: str = "ready"


def normalize_category(text: str, transaction_type: str = "expense") -> str:
    normalized = _normalize(text)

    # Primero respeta el tipo de transacción. Esto evita errores como:
    # "abono al préstamo" -> "bono" por contener la palabra "abono".
    if transaction_type == "income":
        income_keys = ["salario", "planilla", "horas extra", "ot", "bono", "reembolso"]
        for key in income_keys:
            if key in normalized:
                return CATEGORY_MAP[key]
        return "Ingresos / Otros ingresos"

    if transaction_type == "debt_payment":
        debt_keys = ["papá", "papa", "familiar", "bac", "tarjeta bac", "multimoney", "popular", "prestamo", "préstamo", "deuda"]
        for key in debt_keys:
            if key in normalized:
                if key in {"prestamo", "préstamo", "deuda"}:
                    return "Deudas / Otros préstamos"
                return CATEGORY_MAP[key]
        return "Deudas / Otros préstamos"

    if transaction_type == "investment":
        investment_keys = ["ibkr", "cripto", "multimoney inversion", "multimoney inversión"]
        for key in investment_keys:
            if key in normalized:
                return CATEGORY_MAP[key]
        return "Inversiones / Otros"

    if transaction_type == "saving":
        saving_keys = ["fondo emergencia", "viajes", "meta personal", "ahorro"]
        for key in saving_keys:
            if key in normalized and key in CATEGORY_MAP:
                return CATEGORY_MAP[key]
        return "Ahorro / Meta personal"

    for key, category in CATEGORY_MAP.items():
        if key in normalized:
            return category

    return "Gastos variables / Compras"


def extract_month_year(text: str) -> dict[str, int] | None:
    normalized = _normalize(text)
    found_month = None
    for name, number in MONTHS.items():
        if name in normalized:
            found_month = number
            break

    if not found_month:
        return None

    year_match = re.search(r"\b(20\d{2})\b", normalized)
    year = int(year_match.group(1)) if year_match else date.today().year

    return {"month": found_month, "year": year}


def parse_monthly_import(
    raw_text: str,
    month: int | None = None,
    year: int | None = None,
    exchange_rate: float | None = None
) -> dict[str, Any]:
    """
    Lee un bloque mensual línea por línea.

    Formatos aceptados:
    - 08/01/2026 | Salario | ₡72008.06 | Planilla
    - 08/01/2026 | Salario | Planilla | ₡72,008.06
    - 08/01 | Salario | ₡72008.06
    - INGRESOS:
      08/01/2026 | Salario | ₡72008.06

    Regla importante:
    - No toma números de la fecha como montos.
    - Si una línea tiene varios números, toma el monto desde el campo con ₡, $, CRC, USD o desde el último campo.
    """
    normalized_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in normalized_text.split("\n") if line.strip()]

    current_section = None
    items: list[ParsedImportItem] = []
    pending: list[dict[str, Any]] = []
    usd_without_rate = False

    for line in lines:
        section = _section_from_line(line)
        if section:
            current_section = section
            continue

        if _looks_like_metadata(line):
            month_data = extract_month_year(line)
            if month_data:
                month = month or month_data["month"]
                year = year or month_data["year"]
            continue

        parsed = _parse_line(line, current_section, month, year, exchange_rate)
        if not parsed:
            continue

        if parsed.status == "pending":
            pending.append(parsed.__dict__)
            continue

        if parsed.original_currency == "USD" and parsed.exchange_rate is None:
            usd_without_rate = True

        items.append(parsed)

    summary = summarize_items(items)

    return {
        "items": [item.__dict__ for item in items],
        "pending_items": pending,
        "summary": summary,
        "needs_exchange_rate": usd_without_rate,
    }


def apply_exchange_rate_to_items(items: list[dict[str, Any]], exchange_rate: float) -> list[dict[str, Any]]:
    updated = []
    for item in items:
        new_item = dict(item)
        if new_item.get("original_currency") == "USD" and new_item.get("original_amount") is not None:
            new_item["exchange_rate"] = exchange_rate
            new_item["amount"] = round(float(new_item["original_amount"]) * exchange_rate, 2)
            note = new_item.get("notes") or ""
            original = f"Monto original: ${float(new_item['original_amount']):,.2f}. Tipo cambio: ₡{exchange_rate:,.2f}."
            new_item["notes"] = f"{note} {original}".strip()
        updated.append(new_item)
    return updated


def summarize_items(items: list[dict[str, Any]] | list[ParsedImportItem]) -> dict[str, Any]:
    totals = {
        "income": 0.0,
        "expense": 0.0,
        "debt_payment": 0.0,
        "investment": 0.0,
        "saving": 0.0,
    }
    count = 0
    by_category: dict[str, float] = {}

    for item in items:
        data = item.__dict__ if isinstance(item, ParsedImportItem) else item
        if data.get("status", "ready") != "ready":
            continue

        transaction_type = data.get("transaction_type") or "expense"
        amount = float(data.get("amount") or 0)

        totals[transaction_type] = totals.get(transaction_type, 0.0) + amount

        category = data.get("category") or "Sin categoría"
        by_category[category] = by_category.get(category, 0.0) + amount
        count += 1

    return {
        "count": count,
        "totals": totals,
        "by_category": dict(sorted(by_category.items(), key=lambda pair: abs(pair[1]), reverse=True)),
    }


def save_monthly_import(items: list[dict[str, Any]]) -> dict[str, Any]:
    created = []

    for item in items:
        if item.get("status", "ready") != "ready":
            continue

        result = create_transaction(
            transaction_date=item["transaction_date"],
            description=item["description"],
            amount=float(item["amount"]),
            transaction_type=item["transaction_type"],
            category=item["category"],
            account=item.get("account", ""),
            source=item.get("source", "chat_monthly_import"),
            notes=item.get("notes", ""),
            original_amount=item.get("original_amount"),
            original_currency=item.get("original_currency"),
            exchange_rate=item.get("exchange_rate"),
        )
        created.append(result)

    return {
        "message": "Importación mensual guardada.",
        "total_created": len(created),
        "created": created,
    }


def format_import_preview(parsed: dict[str, Any]) -> str:
    summary = parsed.get("summary", {})
    totals = summary.get("totals", {})
    pending = parsed.get("pending_items", [])

    lines = ["Encontré:"]
    lines.append(f"- Ingresos: {_money(totals.get('income', 0))}")
    lines.append(f"- Gastos: {_money(totals.get('expense', 0))}")
    lines.append(f"- Pagos de deuda: {_money(totals.get('debt_payment', 0))}")
    lines.append(f"- Inversiones: {_money(totals.get('investment', 0))}")
    lines.append(f"- Ahorros: {_money(totals.get('saving', 0))}")
    lines.append(f"- Movimientos listos: {summary.get('count', 0)}")

    if pending:
        lines.append(f"- Pendientes: {len(pending)}")

    top_categories = list((summary.get("by_category") or {}).items())[:5]
    if top_categories:
        lines.append("")
        lines.append("Top categorías:")
        for category, total in top_categories:
            lines.append(f"- {category}: {_money(total)}")

    lines.append("")
    lines.append("¿Guardar?")
    return "\n".join(lines)


def _normalize(text: str) -> str:
    normalized = text.strip().lower()
    normalized = normalized.replace("á", "a").replace("é", "e").replace("í", "i")
    normalized = normalized.replace("ó", "o").replace("ú", "u")
    return normalized


def _money(value: float | int | None) -> str:
    return f"₡{float(value or 0):,.2f}"


def _section_from_line(line: str) -> str | None:
    normalized = _normalize(line)
    normalized = normalized.strip().strip(":").strip()
    normalized = re.sub(r"^[#\-*\s]+", "", normalized).strip()
    return SECTION_ALIASES.get(normalized)


def _looks_like_metadata(line: str) -> bool:
    normalized = _normalize(line)
    return normalized.startswith(("mes:", "periodo:", "tipo_cambio", "tipo cambio", "nota:", "reglas:"))


def _parse_line(
    line: str,
    current_section: str | None,
    month: int | None,
    year: int | None,
    exchange_rate: float | None
) -> ParsedImportItem | None:
    if not re.search(r"\d", line):
        return None

    transaction_date = _extract_date(line, month, year)
    if not transaction_date:
        return None

    transaction_type = current_section or _guess_transaction_type(line)

    amount_info = _extract_amount(line)
    if amount_info["amount"] is None and amount_info.get("original_amount") is None:
        return None

    if transaction_type == "pending":
        return ParsedImportItem(
            transaction_date=transaction_date,
            description=_clean_description(line),
            amount=float(amount_info.get("amount") or 0),
            transaction_type="pending",
            category="Pendiente",
            notes="Pendiente de confirmar",
            status="pending",
        )

    original_currency = amount_info.get("currency")
    original_amount = amount_info.get("original_amount")
    amount = amount_info["amount"]

    if original_currency == "USD":
        if exchange_rate:
            amount = round(float(original_amount or 0) * exchange_rate, 2)
        else:
            amount = 0.0

    description = _clean_description(line)
    category = normalize_category(line, transaction_type)

    notes = ""
    if original_currency == "USD" and exchange_rate:
        notes = f"Monto original: ${float(original_amount or 0):,.2f}. Tipo cambio: ₡{exchange_rate:,.2f}."

    return ParsedImportItem(
        transaction_date=transaction_date,
        description=description,
        amount=float(amount or 0),
        transaction_type=transaction_type,
        category=category,
        account="",
        source="chat_monthly_import",
        notes=notes,
        original_amount=original_amount,
        original_currency=original_currency,
        exchange_rate=exchange_rate if original_currency == "USD" else None,
    )


def _guess_transaction_type(line: str) -> str:
    normalized = _normalize(line)

    if any(word in normalized for word in ["salario", "planilla", "bono", "reembolso"]):
        return "income"

    if any(word in normalized for word in ["papa", "papá", "prestamo", "préstamo", "deuda", "tarjeta bac"]):
        return "debt_payment"

    if any(word in normalized for word in ["ibkr", "cripto", "inversion", "inversión", "capitalizacion", "capitalización"]):
        return "investment"

    if any(word in normalized for word in ["ahorro", "fondo emergencia"]):
        return "saving"

    return "expense"


def _extract_date(line: str, month: int | None, year: int | None) -> str | None:
    full = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b", line)
    if full:
        day = int(full.group(1))
        month_value = int(full.group(2))
        year_value = int(full.group(3))
        return date(year_value, month_value, day).isoformat()

    short = re.search(r"\b(\d{1,2})[/-](\d{1,2})\b", line)
    if short:
        day = int(short.group(1))
        month_value = int(short.group(2))
        year_value = year or date.today().year
        return date(year_value, month_value, day).isoformat()

    day_only = re.search(r"^\s*(\d{1,2})\s*[|,-]", line)
    if day_only and month and year:
        return date(year, month, int(day_only.group(1))).isoformat()

    return None


def _extract_amount(line: str) -> dict[str, Any]:
    """
    Extrae el monto real sin confundirlo con la fecha.

    Estrategia:
    1. Quita la fecha.
    2. Si hay separadores |, prioriza campos con ₡, $, CRC, USD.
    3. Si no hay símbolo, toma el último número del último campo útil.
    """
    text_without_date = re.sub(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]20\d{2})?\b", " ", line, count=1)
    parts = [part.strip() for part in re.split(r"\|", text_without_date) if part.strip()]
    search_parts = parts if parts else [text_without_date]

    # Primero: campos con moneda explícita.
    for part in reversed(search_parts):
        if re.search(r"(₡|CRC|colones?)", part, re.I):
            amount = _find_last_number(part)
            if amount is not None:
                return {"amount": amount, "currency": "CRC", "original_amount": None}

        if re.search(r"(\$|USD|dolares|dólares)", part, re.I):
            amount = _find_last_number(part)
            if amount is not None:
                return {"amount": 0.0, "currency": "USD", "original_amount": amount}

    # Segundo: último campo numérico. Evita tomar categorías/descripciones.
    for part in reversed(search_parts):
        amount = _find_last_number(part)
        if amount is not None:
            return {"amount": amount, "currency": "CRC", "original_amount": None}

    return {"amount": None, "currency": "CRC", "original_amount": None}


def _find_last_number(text: str) -> float | None:
    # Soporta:
    # 72008.06
    # 72,008.06
    # 72008
    # 72.008,06 (por si algún banco usa formato latino)
    pattern = r"-?\d+(?:[.,]\d{3})*(?:[.,]\d{1,2})?|-?\d+"
    matches = re.findall(pattern, text)
    if not matches:
        return None

    return _to_float(matches[-1])


def _to_float(value: str) -> float:
    clean = value.strip()
    clean = clean.replace("₡", "").replace("$", "").replace("CRC", "").replace("USD", "")
    clean = clean.replace("colones", "").replace("dolares", "").replace("dólares", "")
    clean = clean.replace(" ", "")

    if "," in clean and "." in clean:
        # 72,008.06 => 72008.06
        if clean.rfind(".") > clean.rfind(","):
            clean = clean.replace(",", "")
        # 72.008,06 => 72008.06
        else:
            clean = clean.replace(".", "").replace(",", ".")
    elif "," in clean:
        # 72008,06 => 72008.06
        if len(clean.split(",")[-1]) in (1, 2):
            clean = clean.replace(",", ".")
        # 72,008 => 72008
        else:
            clean = clean.replace(",", "")

    return float(clean)


def _clean_description(line: str) -> str:
    text = re.sub(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]20\d{2})?\b", "", line, count=1)

    # Si es formato con pipes, elimina el campo de monto y deja categoría/descripción.
    parts = [part.strip() for part in text.split("|") if part.strip()]
    if parts:
        cleaned_parts = []
        for part in parts:
            if re.search(r"(₡|\$|CRC|USD|colones?|dolares|dólares)", part, re.I):
                continue
            # Si el campo es solamente un número, se elimina.
            if _find_last_number(part) is not None and re.fullmatch(r"[\s₡$A-Za-z]*-?\d[\d.,\s]*(?:CRC|USD|colones?|dolares|dólares)?", part, re.I):
                continue
            cleaned_parts.append(part)
        text = " ".join(cleaned_parts)

    text = re.sub(r"(?:₡|\$|CRC|USD\s*)?-?\d+(?:[.,]\d{3})*(?:[.,]\d{1,2})?\s*(?:CRC|USD|colones?|dolares|dólares)?\s*$", "", text, flags=re.I)
    text = text.replace("|", " ").strip(" -—:")
    return re.sub(r"\s+", " ", text).strip() or "Movimiento importado"
