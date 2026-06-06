from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date, datetime
from typing import Any


BANK_SENDERS = {
    "bac": ["bac", "credomatic", "banco bac", "notificacionesbaccr", "notificaciones@bac", "estadosdecuenta@bac"],
    "popular": ["banco popular", "popular", "bancopopular.fi.cr"],
    "multimoney": ["multimoney", "multi money", "financiera multimoney", "multimoneycr"],
}

MOVEMENT_KEYWORDS = [
    "compra",
    "pago",
    "transferencia",
    "sinpe",
    "deposito",
    "depósito",
    "retiro",
    "abono",
    "debito",
    "débito",
    "credito",
    "crédito",
    "transaccion realizada",
    "transacción realizada",
    "movimiento entre cuentas",
    "notificacion de transaccion",
    "notificación de transacción",
    "notificacion de transferencia",
    "notificación de transferencia",
    "confirmacion de transferencia",
    "confirmación de transferencia",
]

STATEMENT_KEYWORDS = [
    "estado de cuenta",
    "estados de cuenta",
    "estado de cuenta financiera",
    "cuenta bancaria",
    "cuentas bancarias",
]

REJECT_KEYWORDS = [
    "tu sesion se inicio",
    "tu sesión se inició",
    "sesion se inicio",
    "sesión se inició",
    "inicio de sesion",
    "inicio de sesión",
    "login",
    "darse de baja",
    "promocion",
    "promoción",
    "participa por",
    "newsletter",
    "publicidad",
    "nuevos seguros",
    "seguro de vida",
    "conoce mas",
    "conocé más",
    "aviso legal",
    "actualizar tus preferencias",
]

# Correos tipo tabla/línea: Monto: CRC 2,750.00 | Monto: USD 3.49 | por un monto de 104,396.54 Colones
LABELED_AMOUNT_PATTERNS = [
    re.compile(r"\bmonto\s*[:\-]?\s*(?P<currency>CRC|USD|₡|¢|\$|colones?)\s*(?P<amount>\d[\d.,]*)(?!\d)", re.I),
    re.compile(r"\bmonto\s*[:\-]?\s*(?P<amount>\d[\d.,]*)\s*(?P<currency>CRC|USD|₡|¢|\$|colones?)\b", re.I),
    re.compile(r"\bpor\s+un\s+monto\s+de\s*(?P<currency>CRC|USD|₡|¢|\$|colones?)?\s*(?P<amount>\d[\d.,]*)\s*(?P<currency2>CRC|USD|₡|¢|\$|colones?)?\b", re.I),
    re.compile(r"\btotal\s*[:\-]?\s*(?P<currency>CRC|USD|₡|¢|\$|colones?)\s*(?P<amount>\d[\d.,]*)(?!\d)", re.I),
]

# Fallback estricto: solo números con símbolo/moneda explícita, evita IPs, referencias y teléfonos.
EXPLICIT_AMOUNT_RE = re.compile(
    r"(?P<currency>₡|¢|CRC|USD|\$)\s*(?P<amount>\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})|\d+(?:[.,]\d{2}))\b",
    re.I,
)

DATE_PATTERNS = [
    re.compile(r"\b(?P<day>\d{1,2})[/-](?P<month>\d{1,2})[/-](?P<year>\d{2,4})\b"),
    re.compile(r"\b(?P<year>\d{4})[/-](?P<month>\d{1,2})[/-](?P<day>\d{1,2})\b"),
]

MONTHS = {
    "jan": 1, "january": 1, "ene": 1, "enero": 1,
    "feb": 2, "february": 2, "febrero": 2,
    "mar": 3, "march": 3, "marzo": 3,
    "apr": 4, "april": 4, "abr": 4, "abril": 4,
    "may": 5, "mayo": 5,
    "jun": 6, "june": 6, "junio": 6,
    "jul": 7, "july": 7, "julio": 7,
    "aug": 8, "august": 8, "ago": 8, "agosto": 8,
    "sep": 9, "sept": 9, "september": 9, "setiembre": 9, "septiembre": 9,
    "oct": 10, "october": 10, "octubre": 10,
    "nov": 11, "november": 11, "noviembre": 11,
    "dec": 12, "december": 12, "dic": 12, "diciembre": 12,
}
MONTH_NAME_RE = re.compile(
    r"\b(?P<month>jan(?:uary)?|ene(?:ro)?|feb(?:ruary|rero)?|mar(?:ch|zo)?|apr(?:il)?|abr(?:il)?|may(?:o)?|jun(?:e|io)?|jul(?:y|io)?|aug(?:ust)?|ago(?:sto)?|sep(?:t|tember|tiembre)?|setiembre|oct(?:ober|ubre)?|nov(?:ember|iembre)?|dec(?:ember)?|dic(?:iembre)?)\.?\s+(?P<day>\d{1,2}),?\s+(?P<year>\d{4})\b",
    re.I,
)


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
    haystack = normalize(" ".join([sender, subject, body[:1500]]))
    for bank, words in BANK_SENDERS.items():
        if any(word in haystack for word in words):
            return bank
    return "unknown"


def classify_email(subject: str, sender: str, body: str) -> tuple[str, str]:
    """Return movement | statement | ignored and a human reason."""
    clean = normalize(" ".join([sender, subject, body[:2500]]))
    bank = detect_bank(sender, subject, body)

    if bank == "unknown":
        return "ignored", "No es un correo de BAC, Banco Popular o MultiMoney."

    if any(word in clean for word in REJECT_KEYWORDS) and not any(word in clean for word in MOVEMENT_KEYWORDS):
        return "ignored", "Correo informativo/promocional, no es movimiento de dinero."

    if any(word in clean for word in STATEMENT_KEYWORDS):
        return "statement", "Estado de cuenta detectado. Requiere lectura de adjunto/PDF para IVA y detalle."

    if any(word in clean for word in MOVEMENT_KEYWORDS):
        return "movement", "Movimiento de dinero detectado."

    return "ignored", "No contiene palabras clave de compra, pago, transferencia, SINPE, depósito, retiro, abono, crédito/débito o estado de cuenta."


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

    month_match = MONTH_NAME_RE.search(text or "")
    if month_match:
        month_key = normalize(month_match.group("month")).replace(".", "")
        month = MONTHS.get(month_key[:3], MONTHS.get(month_key))
        if month:
            try:
                return date(int(month_match.group("year")), month, int(month_match.group("day"))).isoformat()
            except ValueError:
                pass

    if fallback:
        try:
            return datetime.fromisoformat(fallback.replace("Z", "+00:00")).date().isoformat()
        except Exception:
            pass

    return date.today().isoformat()


def _currency_code(raw: str | None) -> str:
    value = (raw or "").strip().upper()
    if value in {"USD", "$"}:
        return "USD"
    return "CRC"


def _parse_number(raw: str) -> float | None:
    value = (raw or "").strip()
    if not value:
        return None

    # Rechaza identificadores demasiado largos sin separadores útiles.
    digits_only = re.sub(r"\D", "", value)
    if len(digits_only) > 12:
        return None

    if "," in value and "." in value:
        # El separador decimal es el último que aparece.
        if value.rfind(".") > value.rfind(","):
            value = value.replace(",", "")
        else:
            value = value.replace(".", "").replace(",", ".")
    elif "," in value:
        parts = value.split(",")
        if len(parts[-1]) == 2:
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    elif "." in value:
        parts = value.split(".")
        # 2.750.00 no debería pasar, pero si hay muchos puntos, los previos son miles.
        if len(parts) > 2:
            value = "".join(parts[:-1]) + "." + parts[-1]

    try:
        return float(value)
    except ValueError:
        return None


def parse_amount(text: str) -> tuple[float | None, str]:
    content = text or ""

    for pattern in LABELED_AMOUNT_PATTERNS:
        for match in pattern.finditer(content):
            raw_currency = match.groupdict().get("currency") or match.groupdict().get("currency2")
            amount = _parse_number(match.group("amount"))
            if amount and 0 < amount < 50_000_000:
                return amount, _currency_code(raw_currency)

    for match in EXPLICIT_AMOUNT_RE.finditer(content):
        amount = _parse_number(match.group("amount"))
        if amount and 0 < amount < 50_000_000:
            return amount, _currency_code(match.group("currency"))

    return None, "CRC"


def infer_transaction_type(text: str) -> str:
    clean = normalize(text)
    incoming_terms = [
        "sinpe recibido", "transferencia recibida", "deposito recibido", "deposito", "depósito",
        "credito a su cuenta", "crédito a su cuenta", "abono recibido", "salario", "planilla",
    ]
    debt_terms = [
        "pago tarjeta", "pago de tarjeta", "pago unica moneda", "abono al prestamo",
        "cuota", "minicuota", "pago prestamo", "pago préstamo",
    ]
    transfer_terms = ["transferencia sinpe", "notificacion de transferencia", "notificación de transferencia", "confirmacion de transferencia", "confirmación de transferencia"]

    if any(word in clean for word in incoming_terms):
        return "income"
    if any(word in clean for word in debt_terms):
        return "debt_payment"
    if any(word in clean for word in transfer_terms):
        # BAC no dice siempre si salió o entró. Lo dejamos pendiente como gasto/transferencia saliente por seguridad.
        return "expense"
    return "expense"


def infer_category(text: str, transaction_type: str, email_kind: str = "movement") -> str:
    clean = normalize(text)

    if email_kind == "statement":
        return "Estado de cuenta"

    if transaction_type == "income":
        if "planilla" in clean or "salario" in clean:
            return "Salario"
        if "prestamo" in clean or "préstamo" in clean:
            return "Préstamo"
        if "sinpe" in clean or "transferencia" in clean:
            return "Transferencia recibida"
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
        ("Videojuegos", ["playstation", "supercell", "fs *supercell", "apple.com/bill", "gossip", "kingshot", "8 ball", "juego"]),
        ("Restaurante", ["uber eats", "mcdonald", "arcos dorados", "kfc", "restaurante", "comida rapida", "pizza"]),
        ("Comida", ["maxi pali", "maxipali", "pali", "am pm", "automercado", "auto mercado", "pulperia", "supermercado"]),
        ("Gasolina", ["gasolinera", "estacion de servicio", "combustible"]),
        ("Transporte", ["uber rides", "uber", "parqueo", "taxi"]),
        ("Salud", ["farmacia", "farmavalue", "hospital", "clinica", "nutricionista", "terapia", "medico", "médico"]),
        ("Suscripciones", ["netflix", "crunchyroll", "google one", "icloud", "resume.io", "spotify"]),
        ("Deporte", ["gym", "novo fit", "uno sport", "box"]),
        ("Compras", ["temu", "shein", "amazon", "tienda", "ecommerce"]),
        ("Teléfono", ["liberty", "linea", "línea", "movil"]),
        ("Vivienda", ["casa", "alquiler"]),
        ("Transferencias", ["sinpe", "transferencia", "movimiento entre cuentas"]),
    ]

    for category, words in category_rules:
        if any(word in clean for word in words):
            return category

    return "Otros gastos"


def confidence_for(bank: str, amount: float | None, text: str, email_kind: str) -> tuple[float, str]:
    if email_kind == "ignored":
        return 0.0, "Correo ignorado: no es movimiento financiero útil."
    if email_kind == "statement":
        return 0.75, "Estado de cuenta detectado; requiere revisión/lectura de adjunto."
    if bank == "unknown":
        return 0.35, "Banco no identificado."
    if not amount:
        return 0.45, "Movimiento probable, pero no se detectó monto claro."

    clean = normalize(text)
    if any(word in clean for word in ["monto", "compra", "transaccion", "transacción", "pago", "sinpe", "deposito", "depósito", "transferencia"]):
        return 0.92, "Banco, monto y tipo detectados."
    return 0.72, "Movimiento probable, requiere revisión."


def extract_description(subject: str, body: str, bank: str) -> str:
    subject_clean = (subject or "").strip()
    if subject_clean:
        return subject_clean[:240]

    body_clean = re.sub(r"\s+", " ", body or "").strip()
    return (body_clean[:180] or f"Movimiento {bank}")[:240]


def parse_financial_email(subject: str, sender: str, body: str, received_at: str | None = None, exchange_rate: float = 495.0) -> dict[str, Any]:
    bank = detect_bank(sender, subject, body)
    email_kind, kind_reason = classify_email(subject, sender, body)
    text = "\n".join(part for part in [subject, body] if part)

    if email_kind == "ignored":
        return {
            "bank": bank,
            "email_kind": "ignored",
            "ignore_reason": kind_reason,
            "transaction_date": parse_date(text, received_at),
            "description": extract_description(subject, body, bank),
            "amount": 0.0,
            "transaction_type": "ignored",
            "category": "Ignorado",
            "account": bank.upper() if bank != "unknown" else "Correo",
            "source": "email_monitor",
            "notes": kind_reason,
            "original_amount": None,
            "original_currency": None,
            "exchange_rate": None,
            "confidence": 0.0,
            "confidence_reason": kind_reason,
        }

    amount, currency = parse_amount(text)
    transaction_date = parse_date(text, received_at)

    if email_kind == "statement":
        transaction_type = "statement"
        category = infer_category(text, "statement", email_kind)
        amount_crc = 0.0
        original_amount = None
        original_currency = None
        used_exchange_rate = None
    else:
        transaction_type = infer_transaction_type(text)
        category = infer_category(text, transaction_type, email_kind)
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

    confidence, reason = confidence_for(bank, amount, text, email_kind)
    if email_kind == "statement":
        reason = kind_reason

    return {
        "bank": bank,
        "email_kind": email_kind,
        "ignore_reason": None,
        "transaction_date": transaction_date,
        "description": extract_description(subject, body, bank),
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
