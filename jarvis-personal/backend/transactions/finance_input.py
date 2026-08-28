from __future__ import annotations

import re
import tempfile
from datetime import date
from typing import Any

from pypdf import PdfReader

from backend.finance.category_catalog import normalize_category
from backend.transactions.service import bulk_create_transactions

MONEY_RE = re.compile(r"(?P<currency>₡|CRC|USD|\$)?\s*(?P<amount>-?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})|-?\d+(?:[.,]\d{2})?)", re.I)
ISO_DATE_RE = re.compile(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b")
LATAM_DATE_RE = re.compile(r"\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\b")

TYPE_KEYWORDS = {
    "income": ["salario", "planilla", "sueldo", "bono", "ingreso", "aguinaldo", "reembolso"],
    "loan_received": ["prestamo recibido", "préstamo recibido", "prestamo bac", "prestamo multimoney", "me prestaron"],
    "debt_payment": ["pago tarjeta", "pago bac", "deuda", "prestamo papa", "préstamo papá", "pago préstamo", "abono", "cuota"],
}

CATEGORY_HINTS = {
    "Salario": ["salario", "planilla", "sueldo"],
    "Horas extra": ["hora extra", "horas extra", "overtime", "ot"],
    "Bono": ["bono", "bonus"],
    "Vivienda": ["casa", "vivienda", "alquiler", "renta"],
    "Teléfono": ["linea", "línea", "telefono", "teléfono", "liberty", "kolbi"],
    "Comida": ["maxi pali", "maxipali", "pali", "am pm", "super", "supermercado", "comida", "pulperia", "pulpería"],
    "Restaurante": ["uber eats", "mcdonald", "kfc", "pizza", "restaurante", "subway", "cafe", "café"],
    "Transporte": ["uber", "taxi", "bus", "parqueo"],
    "Gasolina": ["gasolina", "estacion", "estación", "combustible"],
    "Salud": ["salud", "farmacia", "hospital", "doctor", "nutricionista", "terapia", "medicina", "minoxidil", "gym", "novo fit"],
    "Deporte": ["uno sport", "box", "deporte"],
    "Videojuegos": ["playstation", "gossip", "kingshot", "8 ball", "videojuego", "juego"],
    "Suscripciones": ["netflix", "crunchyroll", "google one", "apple", "spotify", "resume.io", "yousician"],
    "Compras": ["temu", "amazon", "compra", "tienda", "ecommerce"],
    "Ropa": ["shein", "ropa", "nails", "bellizzi"],
    "Automóvil": ["aceite", "carro", "marchamo", "auto", "vehiculo", "vehículo"],
    "Tarjeta BAC": ["tarjeta bac", "pago bac", "pago tarjeta"],
    "Familiar": ["papa", "papá", "mama", "mamá", "familiar"],
}

IGNORE_KEYWORDS = [
    "saldo anterior",
    "previous balance",
    "su pago recibido gracias",
    "reversion interes",
    "tasa mensual",
    "puntos",
    "informacion global",
    "límite global",
    "limite global",
    "disponible global",
    "saldo global",
]


def _clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", line.replace("\t", " ").strip())


def _parse_date(line: str, default_year_month: str | None = None) -> str:
    iso = ISO_DATE_RE.search(line)
    if iso:
        y, m, d = iso.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    latam = LATAM_DATE_RE.search(line)
    if latam:
        d, m, y = latam.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    if default_year_month and re.search(r"\b\d{1,2}\b", line):
        day = re.search(r"\b(\d{1,2})\b", line).group(1)
        return f"{default_year_month}-{int(day):02d}"

    return date.today().isoformat()


def _parse_amount(line: str, default_exchange_rate: float = 495.0) -> tuple[float | None, float | None, str | None, float | None]:
    matches = list(MONEY_RE.finditer(line))
    candidates = []
    for match in matches:
        raw_amount = match.group("amount")
        currency = (match.group("currency") or "CRC").upper()
        if raw_amount.count(",") == 1 and raw_amount.count(".") == 0:
            normalized = raw_amount.replace(",", ".")
        else:
            normalized = raw_amount.replace(",", "")
        try:
            value = float(normalized)
        except ValueError:
            continue
        if value == 0:
            continue
        # Avoid picking date fragments by favoring currency markers or larger numbers.
        candidates.append((currency, value, match.start()))

    if not candidates:
        return None, None, None, None

    currency, value, _ = candidates[-1]
    if currency in {"USD", "$"}:
        return round(value * default_exchange_rate, 2), value, "USD", default_exchange_rate
    return value, None, None, None


def _detect_type(text: str) -> str:
    low = text.lower()
    for transaction_type, keywords in TYPE_KEYWORDS.items():
        if any(keyword in low for keyword in keywords):
            return transaction_type
    return "expense"


def _detect_category(text: str, transaction_type: str) -> str:
    low = text.lower()
    for category, keywords in CATEGORY_HINTS.items():
        if any(keyword in low for keyword in keywords):
            return normalize_category(category, transaction_type)
    if transaction_type == "income":
        return "Otros ingresos"
    if transaction_type == "loan_received":
        return "Préstamo"
    if transaction_type == "debt_payment":
        return "Otros préstamos"
    return normalize_category("Compras", "expense")


def _description_from_line(line: str) -> str:
    text = ISO_DATE_RE.sub("", line)
    text = LATAM_DATE_RE.sub("", text)
    text = MONEY_RE.sub("", text)
    text = text.replace("|", " ").replace(";", " ").replace("-", " ")
    text = _clean_line(text)
    return text[:180] or "Movimiento financiero"


def parse_finance_text(text: str, default_year_month: str | None = None, default_exchange_rate: float = 495.0) -> dict[str, Any]:
    transactions: list[dict[str, Any]] = []
    needs_review: list[dict[str, Any]] = []

    for raw in text.splitlines():
        line = _clean_line(raw)
        if not line or len(line) < 4:
            continue
        low = line.lower()
        if any(keyword in low for keyword in IGNORE_KEYWORDS):
            continue

        amount, original_amount, original_currency, exchange_rate = _parse_amount(line, default_exchange_rate)
        if amount is None:
            needs_review.append({"line": line, "reason": "No detecté monto."})
            continue

        transaction_type = _detect_type(line)
        description = _description_from_line(line)
        category = _detect_category(line, transaction_type)
        transaction_date = _parse_date(line, default_year_month)

        transactions.append({
            "transaction_date": transaction_date,
            "description": description,
            "amount": amount,
            "transaction_type": transaction_type,
            "category": category,
            "account": "Manual",
            "source": "finance_input",
            "notes": "Previsualizado desde Añadir finanzas",
            "original_amount": original_amount,
            "original_currency": original_currency,
            "exchange_rate": exchange_rate,
        })

    return build_preview(transactions, needs_review)


def build_preview(transactions: list[dict[str, Any]], needs_review: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    summary = {
        "income": 0.0,
        "expenses": 0.0,
        "debt_payment": 0.0,
        "loan_received": 0.0,
        "count": len(transactions),
    }
    categories: dict[str, float] = {}

    for item in transactions:
        amount = float(item.get("amount") or 0)
        kind = item.get("transaction_type") or "expense"
        if kind in summary:
            summary[kind] += amount
        categories[item.get("category") or "Sin categoría"] = categories.get(item.get("category") or "Sin categoría", 0) + amount

    return {
        "status": "OK",
        "transactions": transactions,
        "needs_review": needs_review or [],
        "summary": summary,
        "categories": categories,
        "message": f"Detecté {len(transactions)} movimientos.",
    }


def commit_finance_preview(transactions: list[dict[str, Any]]) -> dict[str, Any]:
    cleaned = []
    for item in transactions:
        cleaned.append({
            "transaction_date": item["transaction_date"],
            "description": item["description"],
            "amount": float(item["amount"]),
            "transaction_type": item["transaction_type"],
            "category": item["category"],
            "account": item.get("account") or "Manual",
            "source": item.get("source") or "finance_input",
            "notes": item.get("notes") or "Guardado desde Añadir finanzas",
            "original_amount": item.get("original_amount"),
            "original_currency": item.get("original_currency"),
            "exchange_rate": item.get("exchange_rate"),
        })
    return bulk_create_transactions(cleaned)


def extract_pdf_upload_text(file) -> str:
    with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as temp:
        temp.write(file.file.read())
        temp.flush()
        reader = PdfReader(temp.name)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
