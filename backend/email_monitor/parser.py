from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date, datetime
from typing import Any

BANK_SENDERS = {
    "bac": [
        "bac", "credomatic", "baccredomatic", "notificacionesbaccr", "notificaciones@bac",
        "notificacion@notificacionesbaccr.com", "estadosdecuenta@baccredomatic.cr", "bac - sinpe",
    ],
    "popular": ["banco popular", "bancopopular.fi.cr", "notificaciones@bancopopular"],
    "multimoney": ["multimoney", "multi money", "financiera multimoney", "multimoneycr"],
}

# Lo que sí queremos procesar como dinero real.
MONEY_KEYWORDS = [
    "compra", "pago", "transferencia", "sinpe", "deposito", "depósito", "retiro",
    "abono", "debito", "débito", "credito", "crédito", "transaccion realizada",
    "transacción realizada", "movimiento entre cuentas", "notificacion de transaccion",
    "notificación de transacción", "notificacion de transferencia", "notificación de transferencia",
    "confirmacion de transferencia", "confirmación de transferencia",
]

STATEMENT_KEYWORDS = [
    "estado de cuenta", "estados de cuenta", "estado de cuenta financiera",
    "cuenta bancaria", "cuentas bancarias",
]

# Si aparece esto, casi siempre NO es movimiento real. Estados de cuenta se manejan aparte.
REJECT_KEYWORDS = [
    "tu sesion se inicio", "tu sesión se inició", "sesion se inicio", "sesión se inició",
    "inicio de sesion", "inicio de sesión", "login", "darse de baja", "dar de baja",
    "promocion", "promoción", "participa por", "podés darte ese gusto", "llevá tu",
    "tasa cero", "e-scooter", "newsletter", "publicidad", "nuevos seguros", "seguro de vida",
    "conoce mas", "conocé más", "aviso legal", "actualizar tus preferencias",
    "politicas de privacidad", "términos y condiciones", "terminos y condiciones",
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

DATE_PATTERNS = [
    re.compile(r"\b(?P<day>\d{1,2})[/-](?P<month>\d{1,2})[/-](?P<year>\d{2,4})\b"),
    re.compile(r"\b(?P<year>\d{4})[/-](?P<month>\d{1,2})[/-](?P<day>\d{1,2})\b"),
]
MONTH_NAME_RE = re.compile(
    r"\b(?P<month>jan(?:uary)?|ene(?:ro)?|feb(?:ruary|rero)?|mar(?:ch|zo)?|apr(?:il)?|abr(?:il)?|may(?:o)?|jun(?:e|io)?|jul(?:y|io)?|aug(?:ust)?|ago(?:sto)?|sep(?:t|tember|tiembre)?|setiembre|oct(?:ober|ubre)?|nov(?:ember|iembre)?|dec(?:ember)?|dic(?:iembre)?)\.?\s+(?P<day>\d{1,2}),?\s+(?P<year>\d{4})\b",
    re.I,
)

# Montos permitidos SOLO en contexto claro de dinero.
LABELED_AMOUNT_PATTERNS = [
    re.compile(r"\bmonto\s*[:\-]?\s*(?P<currency>CRC|USD|₡|¢|\$|colones?)\s*(?P<amount>\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})|\d+(?:[.,]\d{2}))\b", re.I),
    re.compile(r"\bmonto\s*[:\-]?\s*(?P<amount>\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})|\d+(?:[.,]\d{2}))\s*(?P<currency>CRC|USD|₡|¢|\$|colones?)\b", re.I),
    re.compile(r"\bpor\s+un\s+monto\s+de\s*(?P<currency>CRC|USD|₡|¢|\$|colones?)?\s*(?P<amount>\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})|\d+(?:[.,]\d{2}))\s*(?P<currency2>CRC|USD|₡|¢|\$|colones?)?\b", re.I),
    re.compile(r"\btotal\s+(?:pagado|debitado|acreditado)?\s*[:\-]?\s*(?P<currency>CRC|USD|₡|¢|\$|colones?)\s*(?P<amount>\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})|\d+(?:[.,]\d{2}))\b", re.I),
]

EXPLICIT_AMOUNT_RE = re.compile(
    r"(?P<currency>₡|¢|CRC|USD|\$)\s*(?P<amount>\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})|\d+(?:[.,]\d{2}))\b",
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
    base = "|".join([normalize(sender), normalize(subject), normalize(received_at or ""), normalize(body)[:2500]])
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def fingerprint_candidate(user_id: int, transaction_date: str, amount: float, transaction_type: str, description: str, bank: str) -> str:
    base = f"{user_id}|{transaction_date}|{round(float(amount), 2)}|{transaction_type}|{normalize(description)}|{bank}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def detect_bank(sender: str, subject: str, body: str) -> str:
    haystack = normalize(" ".join([sender, subject, body[:1500]]))
    for bank, words in BANK_SENDERS.items():
        if any(normalize(word) in haystack for word in words):
            return bank
    return "unknown"


def _has_statement(text: str) -> bool:
    clean = normalize(text)
    return any(word in clean for word in STATEMENT_KEYWORDS)


def _has_reject(text: str) -> bool:
    clean = normalize(text)
    return any(word in clean for word in REJECT_KEYWORDS)


def _is_structured_bac_purchase(text: str) -> bool:
    clean = normalize(text)
    return (
        "notificacion de transaccion" in clean
        and "comercio" in clean
        and "tipo de transaccion" in clean
        and "monto" in clean
    )


def _is_bac_sinpe(text: str) -> bool:
    clean = normalize(text)
    return "sinpe" in clean and "monto" in clean and ("transferencia" in clean or "notificacion de transferencia" in clean)


def _is_multimoney_transfer(text: str) -> bool:
    clean = normalize(text)
    return "multimoney" in clean and ("transaccion realizada" in clean or "confirmacion de transferencia" in clean or "confirmación de transferencia" in clean) and "monto" in clean


def classify_email(subject: str, sender: str, body: str) -> tuple[str, str]:
    text = "\n".join([sender or "", subject or "", body or ""])
    clean = normalize(text)
    bank = detect_bank(sender, subject, body)

    if bank == "unknown":
        return "ignored", "No es un correo de BAC, Banco Popular o MultiMoney."

    # Estado de cuenta se conserva, pero NO se guarda como gasto. Luego se leerá PDF/adjunto.
    if _has_statement(text):
        return "statement", "Estado de cuenta detectado; queda pendiente para leer PDF/adjunto."

    # Promos/logins/seguros deben rechazarse aunque digan BAC o tarjeta.
    if _has_reject(text):
        return "ignored", "Correo promocional/informativo/login/seguro; no es movimiento de dinero."

    if bank == "bac" and (_is_structured_bac_purchase(text) or _is_bac_sinpe(text)):
        return "movement", "Movimiento BAC estructurado detectado."

    if bank == "multimoney" and _is_multimoney_transfer(text):
        return "movement", "Movimiento MultiMoney estructurado detectado."

    # Banco Popular normalmente llega como estado de cuenta/adjunto. Si no trae monto claro, no guardar.
    if bank == "popular" and "monto" in clean and any(word in clean for word in MONEY_KEYWORDS):
        return "movement", "Movimiento Banco Popular probable detectado."

    if any(word in clean for word in MONEY_KEYWORDS) and "monto" in clean:
        return "movement", "Movimiento probable con palabra clave y monto."

    return "ignored", "No contiene estructura confiable de movimiento bancario."


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
        month = MONTHS.get(month_key, MONTHS.get(month_key[:3]))
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
    digits_only = re.sub(r"\D", "", value)
    if len(digits_only) > 11:
        return None

    if "," in value and "." in value:
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
        if len(parts) > 2:
            if len(parts[-1]) == 2:
                value = "".join(parts[:-1]) + "." + parts[-1]
            else:
                return None
    try:
        return float(value)
    except ValueError:
        return None


def _money_context_ok(text: str, start: int, end: int) -> bool:
    window = normalize(text[max(0, start - 90): min(len(text), end + 90)])
    allowed = ["monto", "total", "compra", "pago", "transferencia", "sinpe", "deposito", "depósito", "retiro", "abono", "debitado", "acreditado"]
    rejected = ["referencia", "autorizacion", "autorización", "telefono", "teléfono", "cuenta iban", "iban", "tarjeta", "master", "hora", "fecha"]
    return any(word in window for word in allowed) and not any(word in window for word in rejected if "monto" not in window)


def parse_amount(text: str) -> tuple[float | None, str]:
    content = text or ""
    for pattern in LABELED_AMOUNT_PATTERNS:
        for match in pattern.finditer(content):
            raw_currency = match.groupdict().get("currency") or match.groupdict().get("currency2")
            amount = _parse_number(match.group("amount"))
            if amount and 0 < amount < 20_000_000:
                return amount, _currency_code(raw_currency)

    for match in EXPLICIT_AMOUNT_RE.finditer(content):
        if not _money_context_ok(content, match.start(), match.end()):
            continue
        amount = _parse_number(match.group("amount"))
        if amount and 0 < amount < 20_000_000:
            return amount, _currency_code(match.group("currency"))
    return None, "CRC"


def infer_transaction_type(text: str) -> str:
    clean = normalize(text)
    if any(word in clean for word in ["salario", "planilla", "deposito recibido", "depósito recibido", "credito a su cuenta", "crédito a su cuenta", "abono recibido"]):
        return "income"
    if any(word in clean for word in ["pago de tarjeta", "pago tarjeta", "pago prestamo", "pago préstamo", "cuota", "minicuota"]):
        return "debt_payment"
    return "expense"


def infer_category(text: str, transaction_type: str, email_kind: str = "movement") -> str:
    clean = normalize(text)
    if email_kind == "statement":
        return "Estado de cuenta"
    if transaction_type == "income":
        if "planilla" in clean or "salario" in clean:
            return "Salario"
        if "sinpe" in clean or "transferencia" in clean:
            return "Transferencia recibida"
        return "Otros ingresos"
    if transaction_type == "debt_payment":
        if "bac" in clean or "tarjeta" in clean:
            return "Tarjeta BAC"
        if "popular" in clean:
            return "Banco Popular"
        if "multimoney" in clean:
            return "MultiMoney"
        return "Deudas"

    rules = [
        ("Videojuegos", ["playstation", "supercell", "fs *supercell", "apple.com/bill", "gossip", "kingshot", "8 ball", "juego"]),
        ("Restaurante", ["uber eats", "mcdonald", "arcos dorados", "kfc", "restaurante", "pizza"]),
        ("Comida", ["maxi pali", "maxipali", "pali", "am pm", "automercado", "auto mercado", "supermercado", "jose m.zeledon"]),
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
    for category, words in rules:
        if any(word in clean for word in words):
            return category
    return "Otros gastos"


def confidence_for(bank: str, amount: float | None, text: str, email_kind: str) -> tuple[float, str]:
    if email_kind == "ignored":
        return 0.0, "Correo ignorado: no es movimiento financiero útil."
    if email_kind == "statement":
        return 0.80, "Estado de cuenta detectado; queda pendiente para leer PDF/adjunto."
    if bank == "unknown":
        return 0.0, "Banco no identificado."
    if not amount:
        return 0.40, "Movimiento probable, pero no se detectó monto confiable."
    clean = normalize(text)
    if "monto" in clean and any(w in clean for w in ["comercio", "tipo de transaccion", "tipo de transacción", "sinpe", "transferencia"]):
        return 0.94, "Banco, monto y estructura detectados."
    return 0.70, "Movimiento probable, requiere revisión."


def _extract_after_label(text: str, label: str) -> str | None:
    pattern = re.compile(rf"{re.escape(label)}\s*[:\-]?\s*(.+?)(?:\n|\r|$)", re.I)
    match = pattern.search(text or "")
    if match:
        value = re.sub(r"\s+", " ", match.group(1)).strip()
        return value[:120]
    return None


def extract_description(subject: str, body: str, bank: str) -> str:
    commerce = _extract_after_label(body, "Comercio")
    if commerce:
        return commerce[:240]
    concept = _extract_after_label(body, "Concepto")
    if concept:
        return concept[:240]
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

    transaction_date = parse_date(text, received_at)

    if email_kind == "statement":
        amount_crc = 0.0
        original_amount = None
        original_currency = None
        used_exchange_rate = None
        transaction_type = "statement"
        category = "Estado de cuenta"
        amount_for_confidence = None
    else:
        amount, currency = parse_amount(text)
        amount_for_confidence = amount
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

    confidence, reason = confidence_for(bank, amount_for_confidence, text, email_kind)
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
