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
    "uber": "Gastos variables / Transporte",
    "uber rides": "Gastos variables / Transporte",
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

    for key, category in CATEGORY_MAP.items():
        if key in normalized:
            return category

    if transaction_type == "income":
        return "Ingresos / Otros ingresos"
    if transaction_type == "debt_payment":
        return "Deudas / Otros préstamos"
    if transaction_type == "investment":
        return "Inversiones / Otros"
    if transaction_type == "saving":
        return "Ahorro / Meta personal"

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


def parse_monthly_import(raw_text: str, month: int | None = None, year: int | None = None, exchange_rate: float | None = None) -> dict[str, Any]:
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

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
            continue

        parsed = _parse_line(line, current_section, month, year, exchange_rate)
        if not parsed:
            continue

        if parsed.status == "pending":
            pending.append(parsed.__dict__)
        elif parsed.original_currency == "USD" and parsed.exchange_rate is None:
            usd_without_rate = True
            items.append(parsed)
        else:
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
    return text.strip().lower().replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")


def _money(value: float | int | None) -> str:
    return f"₡{float(value or 0):,.2f}"


def _section_from_line(line: str) -> str | None:
    normalized = _normalize(line).strip(":")
    normalized = re.sub(r"^[#\-*\s]+", "", normalized).strip()
    return SECTION_ALIASES.get(normalized)


def _looks_like_metadata(line: str) -> bool:
    normalized = _normalize(line)
    return normalized.startswith(("mes:", "periodo:", "tipo_cambio", "tipo cambio", "nota:", "reglas:"))


def _parse_line(line: str, current_section: str | None, month: int | None, year: int | None, exchange_rate: float | None) -> ParsedImportItem | None:
    if not re.search(r"\d", line):
        return None

    transaction_type = current_section or _guess_transaction_type(line)
    if transaction_type == "pending":
        amount = _extract_amount(line)
        return ParsedImportItem(
            transaction_date=_extract_date(line, month, year) or date.today().isoformat(),
            description=_clean_description(line),
            amount=amount.get("amount", 0),
            transaction_type="pending",
            category="Pendiente",
            notes="Pendiente de confirmar",
            status="pending",
        )

    amount_info = _extract_amount(line)
    if amount_info["amount"] is None:
        return None

    transaction_date = _extract_date(line, month, year)
    if not transaction_date:
        return None

    original_currency = amount_info.get("currency")
    original_amount = amount_info.get("original_amount")
    amount = amount_info["amount"]

    if original_currency == "USD":
        if exchange_rate:
            amount = round(original_amount * exchange_rate, 2)
        else:
            amount = 0.0

    description = _clean_description(line)
    category = normalize_category(line, transaction_type)

    notes = ""
    if original_currency == "USD" and exchange_rate:
        notes = f"Monto original: ${original_amount:,.2f}. Tipo cambio: ₡{exchange_rate:,.2f}."

    return ParsedImportItem(
        transaction_date=transaction_date,
        description=description,
        amount=amount,
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
    if any(word in normalized for word in ["ibkr", "cripto", "inversion", "inversión"]):
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
    currency = "USD" if "$" in line or re.search(r"\bUSD\b", line, re.I) else "CRC"

    if currency == "USD":
        usd_match = re.search(r"(?:\$|USD\s*)(-?\d+(?:[.,]\d+)*)", line, re.I)
        if not usd_match:
            usd_match = re.search(r"(-?\d+(?:[.,]\d+)*)\s*(?:USD|dolares|dólares)", line, re.I)
        if usd_match:
            original = _to_float(usd_match.group(1))
            return {"amount": 0.0, "currency": "USD", "original_amount": original}

    amounts = re.findall(r"-?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?|-?\d+", line)
    if not amounts:
        return {"amount": None, "currency": currency, "original_amount": None}

    # Evita tomar la fecha como monto; normalmente el monto viene al final de la línea.
    selected = amounts[-1]
    return {"amount": _to_float(selected), "currency": "CRC", "original_amount": None}


def _to_float(value: str) -> float:
    clean = value.strip().replace("₡", "").replace("$", "").replace(" ", "")
    if "," in clean and "." in clean:
        clean = clean.replace(",", "")
    elif "," in clean:
        clean = clean.replace(",", "")
    return float(clean)


def _clean_description(line: str) -> str:
    text = re.sub(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]20\d{2})?\b", "", line)
    text = re.sub(r"^\s*\d{1,2}\s*[|,-]", "", text)
    text = re.sub(r"(?:₡|\$|USD\s*)?-?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\s*(?:USD|dolares|dólares)?\s*$", "", text, flags=re.I)
    text = text.replace("|", " ").strip(" -—:")
    return re.sub(r"\s+", " ", text).strip() or "Movimiento importado"
