from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from datetime import date, datetime
from typing import Any

# ---------------------------------------------------------------------------
# JARVIS Email Parser Real
# ---------------------------------------------------------------------------
# Objetivo V1:
# - Leer solo correos financieros reales.
# - Extraer movimientos por plantilla exacta antes de usar IA.
# - Guardar candidatos pendientes, nunca transacciones automáticas.
# - Estados de cuenta quedan como documentos para conciliación, no como gasto.
# ---------------------------------------------------------------------------

BANK_SENDERS = {
    "bac": [
        "notificacion@notificacionesbaccr.com",
        "notificaciones@baccredomatic.cr",
        "alerta@baccredomatic.com",
        "estadosdecuenta@baccredomatic.cr",
        "estadodecuenta@baccredomatic.cr",
        "info@info.baccredomatic.net",
    ],
    "popular": [
        "bancopopular.fi.cr",
        "notificaciones@bancopopular",
        "banco popular informa",
    ],
    "multimoney": [
        "multimoneycr@multimoney.com",
        "financiera@multimoney.com",
        "@multimoney.com",
    ],
}

BANK_SUBJECT_HINTS = {
    "bac": ["bac - sinpe", "bac san jose", "bac san josé", "credomatic"],
    "popular": ["banco popular"],
    "multimoney": ["multimoney", "multi money"],
}

STATEMENT_KEYWORDS = [
    "estado de cuenta", "estados de cuenta", "estado de cuenta financiera",
    "estado de cuenta de cuenta", "estado de cuenta tarjeta", "cuentas bancarias",
    "correspondiente al mes", "detalle de los movimientos de tus cuentas",
    "movimientos de tus cuentas para el mes",
]

# Estos correos se ignoran SOLO si no coinciden primero con una plantilla bancaria.
REJECT_KEYWORDS = [
    "tu sesion se inicio", "tu sesión se inició", "sesion se inicio", "sesión se inició",
    "inicio de sesion", "inicio de sesión", "login", "cambio de clave", "codigo de seguridad",
    "código de seguridad", "promocion", "promoción", "participa por", "newsletter",
    "publicidad", "nuevos seguros", "seguro de vida", "e-scooter", "tasa cero",
    "preaprobado", "oferta", "cashback", "llevate", "llévate",
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
    r"\b(?P<month>jan(?:uary)?|ene(?:ro)?|feb(?:ruary|rero)?|mar(?:ch|zo)?|apr(?:il)?|abr(?:il)?|may(?:o)?|jun(?:e|io)?|jul(?:y|io)?|aug(?:ust)?|ago(?:sto)?|sep(?:t|tember|tiembre)?|setiembre|oct(?:ober|ubre)?|nov(?:ember|iembre)?|dec(?:ember)?|dic(?:iembre)?)\.?\s+"
    r"(?P<day>\d{1,2}),?\s+(?P<year>\d{4})(?:,?\s*(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s*(?P<ampm>a\.?m\.?|p\.?m\.?)?)?\b",
    re.I,
)
DATE_PATTERNS = [
    re.compile(r"\b(?P<day>\d{1,2})[/-](?P<month>\d{1,2})[/-](?P<year>\d{2,4})(?:\s+(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s*(?P<ampm>a\.?m\.?|p\.?m\.?)?)?\b", re.I),
    re.compile(r"\b(?P<year>\d{4})[/-](?P<month>\d{1,2})[/-](?P<day>\d{1,2})(?:\s+(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s*(?P<ampm>a\.?m\.?|p\.?m\.?)?)?\b", re.I),
]
SPANISH_MONTH_PERIOD_RE = re.compile(
    r"\b(?:mes\s+de|correspondiente\s+al\s+mes\s+de|para\s+el\s+mes\s+de|periodo\s+de|per[ií]odo\s+de|movimientos\s+de\s+tus\s+cuentas\s+para\s+el\s+mes\s+de?)\s*"
    r"(?P<month>enero|febrero|marzo|abril|mayo|junio|julio|agosto|setiembre|septiembre|octubre|noviembre|diciembre)\s+"
    r"(?P<year>20\d{2})\b",
    re.I,
)

FIELD_LABELS = {
    "comercio", "ciudad y pais", "fecha", "master", "visa", "autorizacion", "referencia",
    "tipo de transaccion", "monto", "concepto", "cuenta origen", "cuenta destino",
    "titular", "cuenta", "resumen de operacion",
}

# Known personal accounts. These are used only to prevent internal movements
# from becoming expenses/income. Display/masking uses the last 4 digits.
OWN_ACCOUNT_IBANS = {
    "CR74031001010093646126": "MultiMoney colones",
    "CR42010200009469042572": "BAC planilla",
    "CR50010200009625018137": "BAC cuenta",
}
OWN_ACCOUNT_LAST4 = {iban[-4:]: label for iban, label in OWN_ACCOUNT_IBANS.items()}
OWN_DEBIT_CARD_LAST4 = {"1655", "7514"}
OWN_ACCOUNT_ALIASES = {
    # IBAN/account/card endings that identify Kenneth's own money routes.
    # These must never become pending review candidates when both sides are own accounts
    # or when the template explicitly says the movement is an own investment/smart account.
    "6126": "MultiMoney colones",
    "2572": "BAC planilla",
    "8137": "BAC cuenta",
    "1655": "BAC débito",
    "7514": "BAC débito",
}
CARD_PAYMENT_KEYWORDS = [
    "pago tarjeta bac", "pago de tarjeta", "tarjeta de credito", "tarjeta de crédito",
    "monto del pago", "comprobante de pago de tarjeta",
]
REJECTED_MOVEMENT_KEYWORDS = [
    "rechazada", "rechazado", "no fue aplicada", "no aplicada", "fondosinsuficientes",
    "fondos insuficientes", "problemas de comunicacion", "problemas de comunicación",
    "transaccion rechazada", "transacción rechazada",
]
INTERNAL_CONCEPT_KEYWORDS = [
    "inversion vista smart", "inversión vista smart", "vista smart", "ahorro multimoney",
    "inversion propia", "inversión propia", "traslado entre cuentas", "movimiento entre cuentas",
]


def _compact_account(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def _own_account_label(value: str | None) -> str | None:
    compact = _compact_account(value)
    if not compact:
        return None
    for iban, label in OWN_ACCOUNT_IBANS.items():
        if iban in compact:
            return label
    if len(compact) >= 4:
        last4 = compact[-4:]
        if last4 in OWN_ACCOUNT_LAST4:
            return OWN_ACCOUNT_LAST4[last4]
        if last4 in OWN_ACCOUNT_ALIASES:
            return OWN_ACCOUNT_ALIASES[last4]
    return None


def _contains_own_account(value: str | None) -> bool:
    return _own_account_label(value) is not None


def _extract_ibans(text: str | None) -> list[str]:
    found: list[str] = []
    for match in re.finditer(r"CR\s*\d(?:[\s\-]*\d){19}", text or "", re.I):
        iban = _compact_account(match.group(0))
        if iban and iban not in found:
            found.append(iban)
    return found


def _extract_account_near(text: str | None, labels: list[str]) -> str:
    raw = clean_text(text or "")
    label_pattern = "|".join(re.escape(label) for label in labels)
    patterns = [
        rf"(?:{label_pattern})\s*[:\-]?\s*([A-Z]{{2}}\s*\d(?:[\s\-]*\d){{19}})",
        rf"(?:{label_pattern})\s*[:\-]?\s*(\*{{2,}}\d{{4}}|X{{2,}}\d{{4}}|\d{{4}})",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw, re.I)
        if match:
            return match.group(1).strip()
    return ""


def _has_rejected_movement(text: str | None) -> bool:
    clean = normalize(text or "")
    return any(token in clean for token in REJECTED_MOVEMENT_KEYWORDS)


def _is_card_payment(text: str | None) -> bool:
    clean = normalize(text or "")
    return any(token in clean for token in CARD_PAYMENT_KEYWORDS)


def _is_internal_concept(value: str | None) -> bool:
    clean_value = normalize(value or "")
    return any(token in clean_value for token in INTERNAL_CONCEPT_KEYWORDS)


def _own_account_labels_in_text(text: str | None) -> set[str]:
    labels: set[str] = set()
    compact = _compact_account(text or "")
    for iban, label in OWN_ACCOUNT_IBANS.items():
        if iban in compact:
            labels.add(label)
    for last4, label in OWN_ACCOUNT_ALIASES.items():
        # Match explicit masked/account endings without treating any random amount as an account.
        if re.search(rf"(?:IBAN|CUENTA|CTA|TARJETA|\*{{2,}}|X{{2,}}|CR\d{{16,}})[^\d]{{0,20}}{re.escape(last4)}\b", text or "", re.I):
            labels.add(label)
    return labels


def _is_internal_transfer(concept: str | None = None, origin: str | None = None, destination: str | None = None, body: str | None = None, direction: str = "unknown") -> bool:
    if _is_internal_concept(concept) or _is_internal_concept(body):
        return True

    origin_own = _contains_own_account(origin)
    destination_own = _contains_own_account(destination)

    # Two own endpoints means this is only a money move between pockets.
    if origin_own and destination_own:
        return True

    # If the known own account is the destination of an outgoing transfer, or the
    # origin of an incoming transfer, the other side is also ours in the bank template.
    if direction == "out" and destination_own:
        return True
    if direction == "in" and origin_own:
        return True

    labels = _own_account_labels_in_text(body)
    return len(labels) >= 2


def _internal_ignored(bank: str, subject: str, body: str, received_at: str | None, reason: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    result = _ignored(bank, subject, body, received_at, reason)
    result["transaction_type"] = "internal_transfer"
    result["category"] = "Movimiento interno"
    result["email_kind"] = "ignored"
    result["confidence"] = max(float(result.get("confidence") or 0), 0.98)
    if payload:
        result.update({k: v for k, v in payload.items() if k not in {"email_kind", "transaction_type", "category"}})
        result["email_kind"] = "ignored"
        result["transaction_type"] = "internal_transfer"
        result["category"] = "Movimiento interno"
        result["ignore_reason"] = reason
        result["notes"] = f"{payload.get('notes') or ''} | {reason}".strip(" |")
        result["confidence_reason"] = reason
    return result


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value or "")
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def normalize(value: str) -> str:
    clean = _strip_accents(html.unescape(value or "")).lower()
    clean = clean.replace("\u200c", " ").replace("\u200b", " ").replace("\ufeff", " ")
    clean = clean.replace("\xa0", " ")
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def clean_text(value: str) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"(?is)<(style|script|head|noscript)\b[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?i)<\s*(br|/tr|/td|/p|/div|/li|/h[1-6])\b[^>]*>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\u200c", " ").replace("\u200b", " ").replace("\ufeff", " ")
    text = text.replace("\xa0", " ")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _nonempty_lines(text: str) -> list[str]:
    return [line.strip() for line in clean_text(text).splitlines() if line.strip()]


def fingerprint_email(sender: str, subject: str, body: str, received_at: str | None = None) -> str:
    base = "|".join([normalize(sender), normalize(subject), normalize(received_at or ""), normalize(body)[:2500]])
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def fingerprint_candidate(user_id: int, transaction_date: str, amount: float, transaction_type: str, description: str, bank: str) -> str:
    base = f"{user_id}|{transaction_date}|{round(float(amount), 2)}|{transaction_type}|{normalize(description)}|{bank}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def detect_bank(sender: str, subject: str, body: str) -> str:
    """Detect bank with sender-first priority.

    The previous implementation searched the whole email and matched the generic
    word "bac" before checking MultiMoney, so MultiMoney messages that mentioned
    BAC accounts were classified as BAC. Financial email classification must be
    based first on the From address/domain, then on subject hints as a fallback.
    """
    sender_clean = normalize(sender or "")
    for bank, words in BANK_SENDERS.items():
        if any(normalize(word) in sender_clean for word in words):
            return bank

    subject_clean = normalize(subject or "")
    for bank, words in BANK_SUBJECT_HINTS.items():
        if any(normalize(word) in subject_clean for word in words):
            return bank

    body_head = normalize((body or "")[:800])
    if "multimoney" in body_head or "multi money" in body_head:
        return "multimoney"
    if "banco popular" in body_head:
        return "popular"
    if "bac" in body_head and ("sinpe" in body_head or "credomatic" in body_head):
        return "bac"
    return "unknown"


def _has_statement(text: str) -> bool:
    clean = normalize(text)
    return any(word in clean for word in STATEMENT_KEYWORDS)


def _has_reject(text: str) -> bool:
    clean = normalize(text)
    return any(word in clean for word in REJECT_KEYWORDS)


def _label_value(text: str, label: str, max_lookahead: int = 8) -> str | None:
    """Extract value after labels like BAC emails: Label line, blank, value line."""
    lines = _nonempty_lines(text)
    target = normalize(label).rstrip(":")
    for idx, line in enumerate(lines):
        clean = normalize(line).rstrip(":")
        if clean == target or clean.startswith(target + ":"):
            inline = re.sub(rf"(?i)^\s*{re.escape(label)}\s*[:\-]?\s*", "", line).strip()
            if inline and normalize(inline) != target:
                return inline[:260]
            for next_line in lines[idx + 1: idx + 1 + max_lookahead]:
                next_clean = normalize(next_line).rstrip(":")
                if not next_clean or next_clean in FIELD_LABELS:
                    continue
                if next_clean.startswith("banner promocional") or next_clean.startswith("icono "):
                    return None
                return next_line[:260]
    # Compact/flattened HTML fallback. Gmail sometimes returns the whole BAC or
    # MultiMoney template as one long line: "Comercio: X Ciudad y país: ...".
    # Capture until the next known field label instead of the end of the line.
    field_stops = [
        "Comercio", "Ciudad y país", "Ciudad y pais", "Fecha", "MASTER", "VISA",
        "Autorización", "Autorizacion", "Referencia", "Tipo de Transacción",
        "Tipo de Transaccion", "Monto", "Cuenta origen", "Cuenta destino",
        "Titular", "Cuenta", "Recordá", "Recorda", "Resumen de operación",
        "Resumen de operacion",
    ]
    stop = "|".join(re.escape(item) for item in field_stops if normalize(item) != target)
    pattern = re.compile(
        rf"{re.escape(label)}\s*[:\-]?\s*(.+?)(?=\s*(?:{stop})\s*[:\-]?|$)",
        re.I | re.S,
    )
    match = pattern.search(clean_text(text))
    if match:
        value = re.sub(r"\s+", " ", match.group(1)).strip(" .:-")
        if value:
            return value[:260]
    return None


def _parse_number(raw: str) -> float | None:
    value = (raw or "").strip()
    if not value:
        return None
    value = re.sub(r"[^\d.,]", "", value)
    digits_only = re.sub(r"\D", "", value)
    if not digits_only or len(digits_only) > 10:
        return None
    if "," in value and "." in value:
        if value.rfind(".") > value.rfind(","):
            value = value.replace(",", "")
        else:
            value = value.replace(".", "").replace(",", ".")
    elif "," in value:
        parts = value.split(",")
        value = value.replace(".", "").replace(",", ".") if len(parts[-1]) == 2 else value.replace(",", "")
    elif "." in value:
        parts = value.split(".")
        if len(parts) > 2:
            value = "".join(parts[:-1]) + "." + parts[-1] if len(parts[-1]) == 2 else "".join(parts)
    try:
        return float(value)
    except ValueError:
        return None


def _currency_code(value: str | None) -> str:
    raw = (value or "").upper()
    norm = normalize(raw)
    if "USD" in raw or "$" in raw or "DOLAR" in norm or "DOLARES" in norm:
        return "USD"
    return "CRC"


def _parse_labeled_amount_value(value: str | None) -> tuple[float | None, str]:
    if not value:
        return None, "CRC"
    match = re.search(
        r"(?P<currency>CRC|USD|₡|¢|\$|colones?|d[oó]lares?)?\s*"
        r"(?P<amount>\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})|\d+(?:[.,]\d{2}))\s*"
        r"(?P<currency2>CRC|USD|₡|¢|\$|colones?|d[oó]lares?)?",
        value,
        re.I,
    )
    if not match:
        return None, "CRC"
    amount = _parse_number(match.group("amount"))
    currency = _currency_code(match.group("currency") or match.group("currency2") or value)
    if amount is None or amount <= 0 or amount > 20_000_000:
        return None, currency
    return amount, currency


def _parse_context_amount(text: str) -> tuple[float | None, str]:
    patterns = [
        r"por\s+un\s+monto\s+de\s*(?P<amount>\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})|\d+(?:[.,]\d{2}))\s*(?P<currency>colones?|CRC|USD|₡|¢|\$)?",
        r"monto\s*[:\-]?\s*(?P<currency>CRC|USD|₡|¢|\$|colones?)?\s*(?P<amount>\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})|\d+(?:[.,]\d{2}))",
        r"(?P<currency>₡|¢|CRC|USD|\$)\s*(?P<amount>\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})|\d+(?:[.,]\d{2}))",
    ]
    for pattern in patterns:
        match = re.search(pattern, text or "", re.I)
        if match:
            amount = _parse_number(match.group("amount"))
            currency = _currency_code(match.groupdict().get("currency") or match.group(0))
            if amount is not None and 0 < amount < 20_000_000:
                return amount, currency
    return None, "CRC"


def _normalize_time(hour_min: str | None, ampm: str | None = None) -> str | None:
    if not hour_min:
        return None
    parts = [int(p) for p in hour_min.split(":")]
    hour = parts[0]
    minute = parts[1] if len(parts) > 1 else 0
    second = parts[2] if len(parts) > 2 else 0
    marker = normalize(ampm or "")
    if marker.startswith("p") and hour < 12:
        hour += 12
    if marker.startswith("a") and hour == 12:
        hour = 0
    return f"{hour:02d}:{minute:02d}:{second:02d}"


def parse_date(text: str, fallback: str | None = None) -> str:
    full = text or ""
    for pattern in DATE_PATTERNS:
        match = pattern.search(full)
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
    month_match = MONTH_NAME_RE.search(full)
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


def _parse_datetime_text(text: str, fallback: str | None = None) -> tuple[str, str | None]:
    raw = text or ""
    for pattern in DATE_PATTERNS:
        match = pattern.search(raw)
        if match:
            return parse_date(match.group(0), fallback), _normalize_time(match.groupdict().get("time"), match.groupdict().get("ampm"))
    match = MONTH_NAME_RE.search(raw)
    if match:
        return parse_date(match.group(0), fallback), _normalize_time(match.groupdict().get("time"), match.groupdict().get("ampm"))
    return parse_date(raw, fallback), None


def _parse_bac_subject_transaction(subject: str) -> tuple[str | None, str | None, str | None]:
    """Extract merchant/date/time from BAC transaction subjects.

    BAC often puts the most reliable metadata in the subject:
    "Notificación de transacción AM PM 05-06-2026 - 17:45".
    This fallback keeps valid purchases from being lost when Gmail HTML body
    extraction is imperfect.
    """
    raw = subject or ""
    match = re.search(
        r"notificaci[oó]n\s+de\s+transacci[oó]n\s+(.+?)\s+(\d{1,2}[-/]\d{1,2}[-/]\d{4})\s*-\s*(\d{1,2}:\d{2}(?::\d{2})?)",
        raw,
        re.I,
    )
    if not match:
        return None, None, None
    merchant = re.sub(r"\s+", " ", match.group(1)).strip(" -")
    tx_date, tx_time = _parse_datetime_text(f"{match.group(2)} {match.group(3)}")
    return merchant[:240], tx_date, tx_time


def _extract_reference(text: str) -> str | None:
    for pattern in [
        r"referencia\s*[:\-]?\s*(\d{5,})",
        r"autorizaci[oó]n\s*[:\-]?\s*(\d{4,})",
        r"n[uú]mero\s+de\s+referencia\s+(\d{5,})",
    ]:
        match = re.search(pattern, text or "", re.I)
        if match:
            return match.group(1)
    return None



def billing_cycle_for_date(transaction_date: str | date | None, cut_day: int = 21) -> tuple[str | None, str | None]:
    """Return BAC/card cycle window using configurable cut day.

    Kenneth's BAC card is reviewed by cut cycle, not calendar month. Default:
    21 -> 21. A transaction on June 5 belongs to 2026-05-21 / 2026-06-21.
    """
    if not transaction_date:
        return None, None
    try:
        if isinstance(transaction_date, date):
            d = transaction_date
        else:
            d = datetime.fromisoformat(str(transaction_date).replace("Z", "+00:00")).date()
    except Exception:
        return None, None

    cut_day = max(1, min(int(cut_day or 21), 28))
    if d.day >= cut_day:
        start = date(d.year, d.month, cut_day)
    else:
        if d.month == 1:
            start = date(d.year - 1, 12, cut_day)
        else:
            start = date(d.year, d.month - 1, cut_day)
    if start.month == 12:
        end = date(start.year + 1, 1, cut_day)
    else:
        end = date(start.year, start.month + 1, cut_day)
    return start.isoformat(), end.isoformat()


def parse_statement_month(text: str, received_at: str | None = None) -> str | None:
    match = SPANISH_MONTH_PERIOD_RE.search(text or "")
    if match:
        month = MONTHS.get(normalize(match.group("month")))
        if month:
            return f"{int(match.group('year')):04d}-{month:02d}"
    if received_at:
        try:
            received = datetime.fromisoformat(received_at.replace("Z", "+00:00")).date()
            month = received.month - 1
            year = received.year
            if month == 0:
                month = 12
                year -= 1
            return f"{year:04d}-{month:02d}"
        except Exception:
            pass
    return None


def infer_category(text: str, transaction_type: str, email_kind: str = "movement") -> str:
    clean = normalize(text)
    if email_kind == "statement":
        return "Estado de cuenta"
    if transaction_type == "income":
        return "Otros ingresos"
    if transaction_type == "debt_payment":
        return "Deudas"
    if transaction_type == "internal_transfer":
        return "Movimiento interno"
    if transaction_type == "transfer":
        if "terapia" in clean:
            return "Salud"
        if "papa" in clean or "papá" in clean:
            return "Familiar"
        return "Transferencias"

    rules = [
        # Reglas explícitas antes de IA. Usar solo categorías oficiales para evitar
        # que normalize_category caiga en alias raros como "Horas extra".
        ("Servicios", ["openai", "chatgpt", "render.com", "render ", "supabase", "railway", "vercel", "github", "domain", "hosting", "openai api"]),
        ("Deporte", ["gym", "gimnasio", "novo fit", "coffee bar novo fit", "uno sport", "uno sports", "box"]),
        ("Entretenimiento", ["playstation", "ps plus", "supercell", "fs *supercell", "gossip", "kingshot", "juego", "store.supercell", "roku"]),
        ("Suscripciones", ["apple.com/bill", "apple.com bill", "apple", "icloud", "crunchyroll", "google crunchyroll", "google one", "netflix", "resume.io", "spotify"]),
        ("Restaurante", ["taco bell", "pops", "mcdonald", "arcos dorados", "kfc", "restaurante", "sacc restaurante", "pizza", "burger", "uber eats"]),
        ("Comida", ["maxi pali", "maxipali", "pali", "palí", "walmart", "am pm", "automercado", "auto mercado", "supermercado", "jose m.zeledon", "zeledon"]),
        ("Gasolina", ["gasolinera", "estacion de servicio", "estación de servicio", "combustible", "servicentro"]),
        ("Transporte", ["uber rides", "uber", "parqueo", "taxi", "didi"]),
        ("Salud", ["farmacia", "farmavalue", "hospital", "clinica", "clínica", "nutricionista", "terapia", "medico", "médico"]),
        ("Compras", ["temu", "amazon", "tienda", "ecommerce", "ishop", "aliss", "city mall", "shein", "zara", "pull&bear", "bershka", "barber shop", "las vegas"]),
        ("Teléfono", ["liberty", "linea", "línea", "movil", "móvil", "kolbi", "claro"]),
        ("Vivienda", ["casa", "alquiler"]),
    ]
    for category, words in rules:
        if any(word in clean for word in words):
            return category
    return "Otros gastos"


def _card_holder_from_greeting(text: str) -> str | None:
    match = re.search(r"Hola\s*:??\s*([A-ZÁÉÍÓÚÑ ]{6,90})\s*:??", text or "", re.I)
    if not match:
        return None
    name = re.sub(r"\s+", " ", match.group(1)).strip(" :")
    norm = normalize(name)
    if norm.startswith("kenneth"):
        return "Kenneth"
    if norm.startswith("emily"):
        return "Emily"
    if norm.startswith("sidey"):
        return "Sidey"
    return name.title()


def _card_last4(text: str) -> str | None:
    raw = text or ""
    patterns = [
        r"\*{4,}(\d{4})",
        r"(?:tarjeta|master|visa|n[uú]mero)\D{0,40}(?:\d{4}[- ]?\d{2}\*{2}[- ]?\*{4}[- ]?|\*{4,}|x{4,})?(\d{4})",
        r"(?:\*|x){2,}[- ]?(?:\*|x){2,}[- ]?(\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw, re.I)
        if match:
            return match.group(1)
    return None


def _base_result(bank: str, kind: str, received_at: str | None) -> dict[str, Any]:
    return {
        "bank": bank,
        "email_kind": kind,
        "statement_month": None,
        "ignore_reason": None,
        "transaction_date": parse_date(received_at or "", received_at),
        "transaction_time": None,
        "description": "",
        "amount": 0.0,
        "transaction_type": "ignored",
        "category": "Ignorado",
        "account": bank.upper() if bank != "unknown" else "Correo",
        "source": "email_monitor",
        "notes": "",
        "original_amount": None,
        "original_currency": None,
        "exchange_rate": None,
        "card_last4": None,
        "card_owner": None,
        "billing_cycle_start": None,
        "billing_cycle_end": None,
        "dedupe_key": None,
        "confidence": 0.0,
        "confidence_reason": "",
    }


def _parse_bac_purchase(subject: str, sender: str, body: str, received_at: str | None, exchange_rate: float) -> dict[str, Any] | None:
    text = clean_text("\n".join([subject or "", body or ""]))
    clean = normalize(text)
    subject_merchant, subject_date, subject_time = _parse_bac_subject_transaction(subject or "")

    is_bac_card_email = (
        "notificacion de transaccion" in clean
        or "notificación de transacción" in (subject or "").lower()
        or subject_merchant is not None
    )
    if not is_bac_card_email:
        return None

    # Strong template extraction first. Subject fallback second.
    merchant = _label_value(text, "Comercio") or subject_merchant
    amount_raw = _label_value(text, "Monto")
    date_raw = _label_value(text, "Fecha")
    tipo_raw = _label_value(text, "Tipo de Transacción") or _label_value(text, "Tipo de Transaccion") or "COMPRA"

    if not merchant:
        return None

    amount, currency = _parse_labeled_amount_value(amount_raw)
    if amount is None:
        amount, currency = _parse_context_amount(text)
    if amount is None or amount <= 0:
        return None

    if date_raw:
        transaction_date, time_value = _parse_datetime_text(date_raw, received_at)
    elif subject_date:
        transaction_date, time_value = subject_date, subject_time
    else:
        transaction_date, time_value = _parse_datetime_text(text, received_at)

    card_last4 = _card_last4(text)
    holder = _card_holder_from_greeting(text)
    reference = _extract_reference(text)
    tipo_clean = normalize(tipo_raw)
    if any(word in tipo_clean for word in ["devolucion", "reversion", "reverso", "credito", "anulacion"]):
        transaction_type = "income"
    else:
        transaction_type = "expense"
    amount_crc = round(amount * exchange_rate, 2) if currency == "USD" else round(amount, 2)
    category = infer_category(merchant, transaction_type)
    notes = ["BAC compra por plantilla", f"tipo: {tipo_raw.strip()}"]
    if card_last4:
        notes.append(f"tarjeta ****{card_last4}")
    if holder:
        notes.append(f"titular correo: {holder}")
    if reference:
        notes.append(f"referencia {reference}")
    if time_value:
        notes.append(f"hora: {time_value}")
    if currency == "USD":
        notes.append(f"monto original USD {amount:.2f}; TC {exchange_rate}")
    cycle_start, cycle_end = billing_cycle_for_date(transaction_date)
    if cycle_start and cycle_end:
        notes.append(f"ciclo tarjeta: {cycle_start} a {cycle_end}")

    # Include time/reference in dedupe key so two real charges from the same
    # merchant on the same day do not collapse into one candidate.
    unique_part = reference or time_value or ""
    return {
        **_base_result("bac", "movement", received_at),
        "transaction_date": transaction_date,
        "transaction_time": time_value,
        "description": merchant[:240],
        "amount": amount_crc,
        "transaction_type": transaction_type,
        "category": category,
        "account": f"BAC ****{card_last4}" if card_last4 else "BAC Tarjeta",
        "notes": " | ".join(notes),
        "original_amount": amount if currency == "USD" else None,
        "original_currency": "USD" if currency == "USD" else None,
        "exchange_rate": exchange_rate if currency == "USD" else None,
        "card_last4": card_last4,
        "card_owner": holder,
        "billing_cycle_start": cycle_start,
        "billing_cycle_end": cycle_end,
        "dedupe_key": f"bac_card|{transaction_date}|{card_last4 or ''}|{round(amount_crc,2)}|{normalize(merchant)}|{unique_part}",
        "confidence": 0.99,
        "confidence_reason": "BAC compra: comercio, fecha, tipo, tarjeta, ciclo y monto extraídos por plantilla exacta.",
    }

def _parse_bac_sinpe(subject: str, sender: str, body: str, received_at: str | None) -> dict[str, Any] | None:
    text = clean_text("\n".join([subject or "", body or ""]))
    clean = normalize(text)
    if not ("sinpe" in clean and "transferencia" in clean and "monto" in clean):
        return None

    if _has_rejected_movement(text):
        return _ignored("bac", subject, body, received_at, "Transferencia SINPE rechazada/no aplicada; no afecta finanzas.")

    amount, _currency = _parse_context_amount(text)
    if amount is None or amount <= 0:
        return None

    date_match = re.search(r"d[ií]a\s+y\s+hora\s*:??\s*([^\.\n]+)", text, re.I)
    transaction_date, time_value = _parse_datetime_text(date_match.group(1) if date_match else text, received_at)

    is_out = "debitando su cuenta" in clean or "debito" in clean or "débito" in clean
    is_in = "se acredito" in clean or "se acredito en la cuenta" in clean or "se acreditó" in (body or "").lower() or "acreditando" in clean
    direction = "out" if is_out else "in" if is_in else "unknown"

    concept_match = re.search(r"por\s+concepto\s+de\s+(.+?)(?:\s+Monto\b|\.?D[ií]a\s+y\s+hora|\n|$)", text, re.I | re.S)
    concept = re.sub(r"[_\s]+", " ", concept_match.group(1)).strip(" .") if concept_match else ""
    reference_match = re.search(r"referencia\s+(\d{8,})", text, re.I)

    origin_account = _extract_account_near(text, ["cuenta origen", "cuenta debitada", "debitando su cuenta", "desde la cuenta", "de la cuenta"])
    destination_account = _extract_account_near(text, ["cuenta destino", "cuenta acreditada", "acreditando la cuenta", "a la cuenta", "hacia la cuenta", "al iban", "iban destino"])
    ibans = _extract_ibans(text)
    if not origin_account and direction == "out" and ibans:
        # BAC often mentions the debited own account first.
        origin_account = ibans[0]
    if not destination_account and direction == "in" and ibans:
        # Incoming notifications usually mention the credited own account.
        destination_account = ibans[-1]

    description_base = concept or ("SINPE enviado" if is_out else "SINPE recibido" if is_in else "Transferencia SINPE")
    notes = ["BAC SINPE por plantilla", "salida" if is_out else "entrada" if is_in else "dirección por revisar"]
    if reference_match:
        notes.append(f"referencia {reference_match.group(1)}")
    if origin_account:
        notes.append(f"origen: {origin_account}")
    if destination_account:
        notes.append(f"destino: {destination_account}")
    if ibans:
        notes.append("IBAN detectados: " + ", ".join(ibans))
    if time_value:
        notes.append(f"hora: {time_value}")

    if _is_internal_transfer(description_base, origin_account, destination_account, text, direction):
        payload = {
            **_base_result("bac", "movement", received_at),
            "transaction_date": transaction_date,
            "transaction_time": time_value,
            "description": description_base[:240],
            "amount": round(amount, 2),
            "account": "BAC SINPE",
            "notes": " | ".join(notes),
            "dedupe_key": f"sinpe_internal|{transaction_date}|{round(amount,2)}|{reference_match.group(1) if reference_match else normalize(description_base)}|{direction}",
            "confidence": 0.99,
            "movement_direction": direction,
            "origin_account": origin_account,
            "destination_account": destination_account,
        }
        return _internal_ignored(
            "bac",
            subject,
            body,
            received_at,
            "Movimiento interno entre cuentas propias detectado; no se genera candidato financiero.",
            payload,
        )

    transaction_type = "expense" if is_out else "income" if is_in else "transfer"
    category = infer_category(description_base, transaction_type)
    if transaction_type == "income":
        category = "Reembolsos"
    elif transaction_type == "expense" and not destination_account:
        notes.append("destino no visible en correo BAC; revisar categoría antes de confirmar")

    description = description_base
    if is_out and normalize(description) in {"sinpe enviado", "transferencia sinpe"}:
        description = "SINPE enviado a tercero"
    elif is_in and normalize(description) in {"sinpe recibido", "transferencia sinpe"}:
        description = "SINPE recibido de tercero"

    return {
        **_base_result("bac", "movement", received_at),
        "transaction_date": transaction_date,
        "transaction_time": time_value,
        "description": description[:240],
        "amount": round(amount, 2),
        "transaction_type": transaction_type,
        "category": category,
        "account": "BAC SINPE",
        "notes": " | ".join(notes),
        "dedupe_key": f"sinpe|{transaction_date}|{round(amount,2)}|{reference_match.group(1) if reference_match else normalize(description)}|{direction}",
        "confidence": 0.98,
        "confidence_reason": "BAC SINPE: dirección, monto, referencia, cuentas y fecha extraídos por plantilla exacta.",
        "movement_direction": direction,
        "origin_account": origin_account,
        "destination_account": destination_account,
    }

def _extract_multimoney_account_block(text: str, label: str) -> str:
    lines = _nonempty_lines(text)
    target = normalize(label).rstrip(":")
    for idx, line in enumerate(lines):
        if normalize(line).rstrip(":") != target:
            continue
        titular = ""
        cuenta = ""
        for next_line in lines[idx + 1: idx + 8]:
            clean = normalize(next_line).rstrip(":")
            if clean in {"cuenta origen", "cuenta destino", "recorda que", "recordá que"}:
                break
            if clean.startswith("titular"):
                titular = re.sub(r"(?i)^\s*titular\s*[:\-]?\s*", "", next_line).strip()
            elif clean.startswith("cuenta"):
                cuenta = re.sub(r"(?i)^\s*cuenta\s*[:\-]?\s*", "", next_line).strip()
        if titular or cuenta:
            return " / ".join(part for part in [titular, cuenta] if part)[:240]
    return ""


def _parse_multimoney_transfer(subject: str, sender: str, body: str, received_at: str | None) -> dict[str, Any] | None:
    text = clean_text("\n".join([sender or "", subject or "", body or ""]))
    clean = normalize(text)
    if not ("multimoney" in clean and "monto" in clean and "fecha" in clean):
        return None
    if _has_rejected_movement(text):
        return _ignored("multimoney", subject, body, received_at, "Movimiento MultiMoney rechazado/no aplicado; no afecta finanzas.")

    if not (
        "resumen de operacion" in clean
        or "operacion realizada" in clean
        or "se aplico un debito" in clean
        or "se aplicó un débito" in clean
        or "notificacion de transferencia" in clean
        or "recepcion de fondos" in clean
        or "recepción de fondos" in clean
        or "recibimos tu pago" in clean
        or "depositamos tu credito" in clean
        or "depositamos tu crédito" in clean
    ):
        return None

    concept = _label_value(text, "Concepto") or "Movimiento MultiMoney"
    amount, currency = _parse_labeled_amount_value(_label_value(text, "Monto"))
    if amount is None:
        amount, currency = _parse_context_amount(text)
    if amount is None or amount <= 0:
        return None

    date_raw = _label_value(text, "Fecha") or text
    transaction_date, time_value = _parse_datetime_text(date_raw, received_at)
    origin = _extract_multimoney_account_block(text, "Cuenta origen")
    destination = _extract_multimoney_account_block(text, "Cuenta destino")
    reference = _label_value(text, "Referencia") or ""

    is_debit = "se aplico un debito" in clean or "se aplicó un débito" in clean or "debito en tiempo real" in clean or "débito en tiempo real" in clean
    is_received = "recepcion de fondos" in clean or "recepción de fondos" in clean or "depositamos tu credito" in clean or "depositamos tu crédito" in clean
    is_payment_received = "recibimos tu pago" in clean
    direction = "out" if is_debit else "in" if is_received else "payment" if is_payment_received else "unknown"

    notes = ["MultiMoney transferencia por plantilla"]
    if origin:
        notes.append(f"origen: {origin}")
    if destination:
        notes.append(f"destino: {destination}")
    if reference:
        notes.append(f"referencia: {reference}")
    if time_value:
        notes.append(f"hora: {time_value}")

    if _is_internal_transfer(concept, origin, destination, text, direction):
        payload = {
            **_base_result("multimoney", "movement", received_at),
            "transaction_date": transaction_date,
            "transaction_time": time_value,
            "description": concept[:240],
            "amount": round(amount, 2),
            "account": "MultiMoney",
            "notes": " | ".join(notes),
            "original_amount": amount if currency == "USD" else None,
            "original_currency": "USD" if currency == "USD" else None,
            "dedupe_key": f"multimoney_internal|{transaction_date}|{round(amount,2)}|{reference or normalize(concept)}",
            "confidence": 0.99,
            "movement_direction": direction,
            "origin_account": origin,
            "destination_account": destination,
        }
        return _internal_ignored(
            "multimoney",
            subject,
            body,
            received_at,
            "Movimiento interno BAC/MultiMoney o inversión propia detectada; no se genera candidato financiero.",
            payload,
        )

    if is_payment_received:
        transaction_type = "debt_payment"
        category = "MultiMoney"
        description = "Pago recibido MultiMoney"
    elif is_received:
        transaction_type = "income"
        category = "Otros ingresos"
        description = concept or "Recepción de fondos MultiMoney"
    elif is_debit:
        transaction_type = "expense"
        category = infer_category(concept, "expense")
        description = concept or "Débito MultiMoney"
    else:
        transaction_type = "transfer"
        category = infer_category(concept, "transfer")
        description = concept

    return {
        **_base_result("multimoney", "movement", received_at),
        "transaction_date": transaction_date,
        "transaction_time": time_value,
        "description": description[:240],
        "amount": round(amount, 2),
        "transaction_type": transaction_type,
        "category": category,
        "account": "MultiMoney",
        "notes": " | ".join(notes),
        "original_amount": amount if currency == "USD" else None,
        "original_currency": "USD" if currency == "USD" else None,
        "dedupe_key": f"multimoney|{transaction_date}|{round(amount,2)}|{reference or normalize(description)}|{direction}",
        "confidence": 0.97,
        "confidence_reason": "MultiMoney: concepto, monto, fecha, dirección y cuentas extraídos por plantilla exacta.",
        "movement_direction": direction,
        "origin_account": origin,
        "destination_account": destination,
    }


def _extract_named_payment_target(text: str) -> str:
    clean_line = re.sub(r"\s+", " ", text or "").strip()
    patterns = [
        r"pago\s+de\s+servicio\s+de\s+(.+?)(?:\s+desde|\s+por|\s+monto|\.|$)",
        r"servicio\s+de\s+(.+?)(?:\s+desde|\s+por|\s+monto|\.|$)",
        r"dep[oó]sito\s+por\s+(?:CRC|USD|₡|¢|\$)?\s*[\d.,]+(?:\s+de)?\s*(.+?)(?:\.|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, clean_line, re.I)
        if match:
            value = re.sub(r"\s+", " ", match.group(1)).strip(" .:-")
            if value:
                return value[:120]
    return "Movimiento BAC"


def _parse_bac_alert_payment(subject: str, sender: str, body: str, received_at: str | None) -> dict[str, Any] | None:
    """Parse alerta@baccredomatic.com messages: service payments, card payments, deposits.

    These were previously ignored, but they contain important money movements.
    """
    text = clean_text("\n".join([subject or "", body or ""]))
    clean = normalize(text)
    sender_clean = normalize(sender)
    if "alerta@baccredomatic.com" not in sender_clean:
        return None

    is_payment = "notificacion de pago" in clean or "notificación de pago" in (subject or "").lower() or "comprobante de pago" in clean
    is_deposit = "deposito" in clean or "depósito" in (subject or "").lower() or "ha recibido un deposito" in clean or "ha recibido un depósito" in (body or "").lower()
    if not (is_payment or is_deposit):
        return None

    amount, currency = _parse_context_amount(text)
    if amount is None:
        for pattern in [
            r"monto\s+del\s+pago\s*[:\-]?\s*(?P<currency>CRC|USD|₡|¢|\$)?\s*(?P<amount>[\d.,]+)",
            r"monto\s*[:\-]?\s*(?P<currency>CRC|USD|₡|¢|\$)?\s*(?P<amount>[\d.,]+)",
            r"por\s+(?P<currency>CRC|USD|₡|¢|\$)\s*(?P<amount>[\d.,]+)",
        ]:
            match = re.search(pattern, text, re.I)
            if match:
                amount = _parse_number(match.group("amount"))
                currency = _currency_code(match.groupdict().get("currency") or match.group(0))
                break
    if amount is None or amount <= 0:
        return None

    amount_crc = round(amount, 2)
    card_last4 = _card_last4(text)
    transaction_date, time_value = _parse_datetime_text(text, received_at)

    if _has_rejected_movement(text):
        return _ignored("bac", subject, body, received_at, "Pago/depósito BAC rechazado/no aplicado; no afecta finanzas.")
    if _is_internal_transfer(subject, body=body, direction="unknown"):
        return _internal_ignored("bac", subject, body, received_at, "Movimiento entre cuentas propias detectado en alerta BAC; no se genera candidato financiero.")

    if is_deposit:
        transaction_type = "income"
        description = "Depósito BAC"
        category = "Otros ingresos"
        account = "BAC Depósito"
        reason = "BAC depósito: monto, fecha y remitente extraídos por plantilla alerta."
    elif _is_card_payment(text):
        return _ignored("bac", subject, body, received_at, "Pago de tarjeta BAC detectado; se ignora para evitar doble conteo porque las compras individuales ya son los gastos.")
    else:
        transaction_type = "expense"
        target = _extract_named_payment_target(text)
        description = target if target != "Movimiento BAC" else (subject or "Pago BAC")
        category = infer_category(description, "expense")
        account = f"BAC ****{card_last4}" if card_last4 else "BAC Pago"
        reason = "BAC pago de servicio: monto, fecha y servicio extraídos por plantilla alerta."

    notes = ["BAC alerta/pago por plantilla"]
    if card_last4:
        notes.append(f"tarjeta ****{card_last4}")
    if time_value:
        notes.append(f"hora: {time_value}")
    if currency == "USD":
        notes.append(f"monto original USD {amount:.2f}")
    cycle_start, cycle_end = billing_cycle_for_date(transaction_date)
    if card_last4 and cycle_start and cycle_end:
        notes.append(f"ciclo tarjeta: {cycle_start} a {cycle_end}")

    return {
        **_base_result("bac", "movement", received_at),
        "transaction_date": transaction_date,
        "transaction_time": time_value,
        "description": description[:240],
        "amount": amount_crc,
        "transaction_type": transaction_type,
        "category": category,
        "account": account,
        "notes": " | ".join(notes),
        "original_amount": amount if currency == "USD" else None,
        "original_currency": "USD" if currency == "USD" else None,
        "card_last4": card_last4,
        "billing_cycle_start": cycle_start if card_last4 else None,
        "billing_cycle_end": cycle_end if card_last4 else None,
        "dedupe_key": f"bac_alert|{transaction_date}|{card_last4 or ''}|{round(amount_crc,2)}|{normalize(description)}",
        "confidence": 0.97,
        "confidence_reason": reason,
    }


def _parse_statement(subject: str, sender: str, body: str, received_at: str | None) -> dict[str, Any] | None:
    text = clean_text("\n".join([sender or "", subject or "", body or ""]))
    if not _has_statement(text):
        return None
    bank = detect_bank(sender, subject, body)
    if bank == "unknown":
        bank = "popular" if "popular" in normalize(text) else "unknown"
    statement_month = parse_statement_month(text, received_at)
    received_date = parse_date(received_at or text, received_at)
    bank_label = "BAC" if bank == "bac" else "MultiMoney" if bank == "multimoney" else "Banco Popular" if bank == "popular" else "Banco"
    subject_clean = normalize(subject)
    statement_type = "tarjeta crédito" if "tarjeta" in subject_clean or "credito" in subject_clean else "cuenta bancaria" if "cuenta" in subject_clean else "estado de cuenta"
    description = f"Estado de cuenta {bank_label}"
    if statement_month:
        description += f" {statement_month}"
    return {
        **_base_result(bank, "statement", received_at),
        "statement_month": statement_month,
        "transaction_date": received_date,
        "description": description[:240],
        "amount": 0.0,
        "transaction_type": "statement",
        "category": "Estado de cuenta",
        "account": bank_label,
        "notes": f"Documento {statement_type}. No se guarda como gasto; queda pendiente de conciliación contra PDF y movimientos confirmados.",
        "confidence": 0.95,
        "confidence_reason": "Estado de cuenta detectado; pendiente de lectura/conciliación de PDF.",
    }


def _ignored(bank: str, subject: str, body: str, received_at: str | None, reason: str) -> dict[str, Any]:
    return {
        **_base_result(bank, "ignored", received_at),
        "ignore_reason": reason,
        "description": (subject or "Correo ignorado")[:240],
        "notes": reason,
        "confidence_reason": reason,
    }


def classify_email(subject: str, sender: str, body: str) -> tuple[str, str]:
    bank = detect_bank(sender, subject, body)
    text = "\n".join([sender or "", subject or "", body or ""])
    if bank == "unknown":
        return "ignored", "No es un correo de BAC, Banco Popular o MultiMoney."
    if _parse_statement(subject, sender, body, None):
        return "statement", "Estado de cuenta detectado; queda como documento pendiente."
    if bank == "bac":
        parsed = _parse_bac_purchase(subject, sender, body, None, 495.0) or _parse_bac_sinpe(subject, sender, body, None) or _parse_bac_alert_payment(subject, sender, body, None)
        if parsed:
            if parsed.get("email_kind") == "ignored":
                return "ignored", parsed.get("ignore_reason") or "Movimiento BAC descartado por reglas de seguridad financiera."
            return "movement", "Movimiento BAC estructurado detectado."
    if bank == "multimoney":
        parsed = _parse_multimoney_transfer(subject, sender, body, None)
        if parsed:
            if parsed.get("email_kind") == "ignored":
                return "ignored", parsed.get("ignore_reason") or "Movimiento MultiMoney descartado por reglas de seguridad financiera."
            return "movement", "Movimiento MultiMoney estructurado detectado."
    if _has_reject(text):
        return "ignored", "Correo promocional, login, seguridad o informativo."
    return "ignored", "No contiene estructura confiable de movimiento bancario."


def parse_financial_email(subject: str, sender: str, body: str, received_at: str | None = None, exchange_rate: float = 495.0) -> dict[str, Any]:
    text = "\n".join([sender or "", subject or "", body or ""])
    bank = detect_bank(sender, subject, body)

    if bank == "unknown":
        return _ignored(bank, subject, body, received_at, "No es un correo de BAC, Banco Popular o MultiMoney.")

    # Estados de cuenta tienen prioridad: son documentos, no movimientos.
    statement = _parse_statement(subject, sender, body, received_at)
    if statement:
        return statement

    # Plantillas exactas por banco. No buscar números genéricos fuera de estas plantillas.
    if bank == "bac":
        parsed = _parse_bac_purchase(subject, sender, body, received_at, exchange_rate)
        if parsed:
            return parsed
        parsed = _parse_bac_sinpe(subject, sender, body, received_at)
        if parsed:
            return parsed
        parsed = _parse_bac_alert_payment(subject, sender, body, received_at)
        if parsed:
            return parsed

    if bank == "multimoney":
        parsed = _parse_multimoney_transfer(subject, sender, body, received_at)
        if parsed:
            return parsed

    if bank == "bac" and "notificacion de transaccion" in normalize(text):
        amount, _currency = _parse_context_amount(text)
        if amount is not None and amount <= 0:
            return _ignored(bank, subject, body, received_at, "Autorización BAC con monto cero; no se genera candidato financiero.")

    if _has_reject(text):
        return _ignored(bank, subject, body, received_at, "Correo promocional/login/seguridad/informativo; no es movimiento de dinero.")

    # Banco Popular se acepta solo como estado de cuenta hasta tener ejemplos reales de movimientos.
    return _ignored(bank, subject, body, received_at, "Correo bancario sin plantilla confiable. No se genera candidato.")
