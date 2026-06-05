from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date, datetime
from typing import Any


BANK_SENDERS = {
    "bac": ["bac", "credomatic", "banco bac"],
    "popular": ["banco popular", "popular"],
    "multimoney": ["multimoney", "multi money", "financiera multimoney"],
}

AMOUNT_RE = re.compile(
    r"(?P<currency>₡|¢|CRC|colones|USD|\$)?\s*(?P<amount>[0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{2})|[0-9]+(?:[.,][0-9]{2})?)",
    re.I,
)

DATE_PATTERNS = [
    re.compile(r"\b(?P<day>\d{1,2})[/-](?P<month>\d{1,2})[/-](?P<year>\d{2,4})\b"),
    re.compile(r"\b(?P<year>\d{4})[/-](?P<month>\d{1,2})[/-](?P<day>\d{1,2})\b"),
]


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value or "")
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def normalize(value: str) -> str:
    clean = _strip_accents(value or "").lower()
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def fingerprint_email(sender: str, subject: str, body: str, received_at: str | None = None) -> str:
    base = "|".join([
        normalize(sender),
        normalize(subject),
        normalize(received_at or ""),
        normalize(body)[:2500],
    ])
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def fingerprint_candidate(user_id: int, transaction_date: str, amount: float, transaction_type: str, description: str, bank: str) -> str:
    base = f"{user_id}|{transaction_date}|{round(float(amount), 2)}|{transaction_type}|{normalize(description)}|{bank}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def detect_bank(sender: str, subject: str, body: str) -> str:
    haystack = normalize(" ".join([sender, subject, body[:1000]]))
    for bank, words in BANK_SENDERS.items():
        if any(word in haystack for word in words):
            return bank
    return "unknown"


def parse_date(text: str, fallback: str | None = None) -> str:
    for pattern in DATE_PATTERNS:
        match = pattern.search(text or "")
        if not match:
            continue
        day = int(match.group("day"))
        month = int(match.group("month"))
        year = int(match.group("year"))
        if year < 100:
            year += 2000
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            pass

    if fallback:
        try:
            return datetime.fromisoformat(fallback.replace("Z", "+00:00")).date().isoformat()
        except Exception:
            pass

    return date.today().isoformat()


def parse_amount(text: str) -> tuple[float | None, str]:
    matches = list(AMOUNT_RE.finditer(text or ""))
    candidates: list[tuple[float, str]] = []

    for match in matches:
        raw = match.group("amount")
        currency_raw = (match.group("currency") or "").upper()
        currency = "USD" if currency_raw in {"USD", "$"} else "CRC"

        value = raw.strip()
        if "," in value and "." in value:
            if value.rfind(",") > value.rfind("."):
                value = value.replace(".", "").replace(",", ".")
            else:
                value = value.replace(",", "")
        elif "," in value:
            parts = value.split(",")
            if len(parts[-1]) == 2:
                value = value.replace(".", "").replace(",", ".")
            else:
                value = value.replace(",", "")
        else:
            parts = value.split(".")
            if len(parts) > 2:
                value = "".join(parts[:-1]) + "." + parts[-1]

        try:
            amount = float(value)
        except ValueError:
            continue

        if amount > 0:
            candidates.append((amount, currency))

    if not candidates:
        return None, "CRC"

    # Escoge el monto más grande porque los correos suelen incluir saldos/límites y el movimiento principal destaca.
    return max(candidates, key=lambda item: item[0])


def infer_transaction_type(text: str) -> str:
    clean = normalize(text)
    if any(word in clean for word in ["deposito", "deposito recibido", "credito", "sinpe recibido", "planilla", "salario", "abono recibido", "transferencia recibida"]):
        return "income"
    if any(word in clean for word in ["pago recibido", "pago tarjeta", "pago de tarjeta", "pago unica moneda", "abono al prestamo", "prestamo", "cuota", "minicuota"]):
        return "debt_payment"
    return "expense"


def infer_category(text: str, transaction_type: str) -> str:
    clean = normalize(text)

    if transaction_type == "income":
        if "planilla" in clean or "salario" in clean:
            return "Salario"
        if "prestamo" in clean:
            return "Préstamo"
        return "Otros ingresos"

    if transaction_type == "debt_payment":
        if "bac" in clean or "tarjeta" in clean or "credomatic" in clean:
            return "Tarjeta BAC"
        if "popular" in clean:
            return "Banco Popular"
        if "multimoney" in clean or "multi money" in clean:
            return "MultiMoney"
        if "papa" in clean or "papá" in clean:
            return "Familiar"
        return "Deudas"

    category_rules = [
        ("Restaurante", ["uber eats", "mcdonald", "arcos dorados", "kfc", "restaurante", "comida rapida", "pizza"]),
        ("Comida", ["super", "maxi pali", "maxipali", "pali", "am pm", "automercado", "auto mercado", "pulperia"]),
        ("Gasolina", ["gasolinera", "estacion de servicio", "combustible"]),
        ("Transporte", ["uber rides", "uber", "parqueo", "taxi"]),
        ("Salud", ["farmacia", "farmavalue", "hospital", "clinica", "nutricionista", "terapia", "medico", "médico"]),
        ("Videojuegos", ["playstation", "apple.com/bill", "gossip", "kingshot", "8 ball", "juego"]),
        ("Suscripciones", ["netflix", "crunchyroll", "google one", "icloud", "resume.io", "spotify"]),
        ("Deporte", ["gym", "novo fit", "uno sport", "box"]),
        ("Compras", ["temu", "shein", "amazon", "tienda", "ecommerce"]),
        ("Teléfono", ["liberty", "linea", "línea", "movil"]),
        ("Vivienda", ["casa", "alquiler"]),
    ]

    for category, words in category_rules:
        if any(word in clean for word in words):
            return category

    return "Otros gastos"


def confidence_for(bank: str, amount: float | None, body: str) -> tuple[float, str]:
    if bank == "unknown":
        return 0.35, "Banco no identificado."
    if not amount:
        return 0.4, "No se detectó monto claro."

    clean = normalize(body)
    if any(word in clean for word in ["compra", "transaccion", "transacción", "pago", "sinpe", "deposito", "depósito", "tarjeta", "prestamo"]):
        return 0.86, "Banco, monto y tipo detectados."
    return 0.7, "Movimiento probable, requiere revisión."


def parse_financial_email(subject: str, sender: str, body: str, received_at: str | None = None, exchange_rate: float = 495.0) -> dict[str, Any]:
    bank = detect_bank(sender, subject, body)
    text = "\n".join(part for part in [subject, body] if part)
    amount, currency = parse_amount(text)
    transaction_date = parse_date(text, received_at)
    transaction_type = infer_transaction_type(text)
    category = infer_category(text, transaction_type)
    confidence, reason = confidence_for(bank, amount, text)

    if amount is None:
        amount_crc = 0.0
        original_amount = None
        original_currency = None
        used_exchange_rate = None
    elif currency == "USD":
        amount_crc = round(amount * exchange_rate, 2)
        original_amount = amount
        original_currency = "USD"
        used_exchange_rate = exchange_rate
    else:
        amount_crc = round(amount, 2)
        original_amount = None
        original_currency = None
        used_exchange_rate = None

    description = subject.strip() or "Movimiento detectado por correo"

    return {
        "bank": bank,
        "transaction_date": transaction_date,
        "description": description[:240],
        "amount": amount_crc,
        "transaction_type": transaction_type,
        "category": category,
        "account": bank.upper() if bank != "unknown" else "Correo",
        "source": "email_monitor",
        "notes": f"Detectado desde correo. {reason}".strip(),
        "original_amount": original_amount,
        "original_currency": original_currency,
        "exchange_rate": used_exchange_rate,
        "confidence": confidence,
        "confidence_reason": reason,
    }
