from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from backend.email_monitor import movement_taxonomy as mt
from backend.email_monitor.parser_identity import ParserIdentity, current_identity, use_identity

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
        # BAC moved its notices across senders; each one is observed in real mail.
        "notificacion@notificacionesbaccr.com",  # card alerts until 2026-07
        "notificacion@baccredomatic.cr",  # card alerts 2026-07/08
        "notificacionbac@baccredomatic.cr",  # card alerts since 2026-08
        "sinpe@notificacionesbaccr.com",  # SINPE until 2026-04
        "notificaciones@baccredomatic.cr",  # SINPE since 2026-04
        "alerta@baccredomatic.com",
        "estadosdecuenta@baccredomatic.cr",
        "estadodecuenta@baccredomatic.cr",
        "info@info.baccredomatic.net",
        "info@baccredomatic.com",  # credit disbursements (and promotions, which no template accepts)
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
    # BAC prints "Sep 30, 2026, 02:13", "Sep 23, 2026 , 13:32" and "Sep 21,2026 , 00:00".
    # Each whitespace run is matched once (no adjacent \s* pairs), so hostile spacing stays linear.
    r"(?P<day>\d{1,2})(?:\s*,\s*|\s+)(?P<year>\d{4})(?:\s*(?:,\s*)?(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s*(?P<ampm>a\.?m\.?|p\.?m\.?)?)?\b",
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

# The mailbox holder's own names and accounts come from the caller's parser
# identity (parser_identity.py), never from module-level Owner configuration.
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
    "transferencia entre cuentas", "transferencia entre cuentas bac",
    "debito aplicado por otra entidad financiera", "débito aplicado por otra entidad financiera",
]


def _compact_account(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def _own_account_label(value: str | None) -> str | None:
    compact = _compact_account(value)
    if not compact:
        return None
    identity = current_identity()
    for iban, label in identity.own_account_ibans.items():
        if iban in compact:
            return label
    if len(compact) >= 4:
        last4 = compact[-4:]
        if last4 in identity.own_account_last4:
            return identity.own_account_last4[last4]
        if last4 in identity.own_account_aliases:
            return identity.own_account_aliases[last4]
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
        rf"(?:{label_pattern})\s*[:\-]?\s*(?:IBAN|CUENTA|CTA|N[°ºO]?)?\s*([A-Z]{{2}}\s*\d(?:[\s\-]*\d){{19}})",
        rf"(?:{label_pattern})\s*[:\-]?\s*(?:IBAN|CUENTA|CTA|N[°ºO]?)?\s*(CR\s*\d{{0,8}}[X\*\s\-]{{2,}}\d{{4}})",
        rf"(?:{label_pattern})\s*[:\-]?\s*(?:IBAN|CUENTA|CTA|N[°ºO]?\s*)?(\*{{2,}}\d{{4}}|X{{2,}}\d{{4}}|\d{{4}})",
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


def _looks_like_account_reference(text: str | None, last4: str) -> bool:
    """Return True only when last4 appears as a bank/card/account reference.

    We intentionally avoid matching ordinary amounts. The real emails use both
    full IBANs and masked formats such as CR00****0001, CR0000XXXXXXXX0002,
    N°****0003 or Cuenta: ****0001.
    """
    raw = text or ""
    if not raw or not last4:
        return False

    # Full/unmasked or compact IBAN somewhere in the body.
    compact = _compact_account(raw)
    for iban in current_identity().own_account_ibans:
        if iban in compact and iban.endswith(last4):
            return True

    # Masked IBAN/account/card notations. Keep patterns close to account words
    # or CR prefixes so amounts like 10,000.00 never match as account endings.
    patterns = [
        rf"CR\s*\d{{0,8}}[X\*\s\-]{{2,}}{re.escape(last4)}\b",
        rf"(?:IBAN|CUENTA|CTA|N[°ºO]?|TARJETA|ACCOUNT)[^\n]{{0,80}}(?:X|\*){{2,}}[^\n]{{0,20}}{re.escape(last4)}\b",
        rf"(?:IBAN|CUENTA|CTA|N[°ºO]?|TARJETA|ACCOUNT)[^\n]{{0,80}}CR[^\n]{{0,40}}{re.escape(last4)}\b",
    ]
    return any(re.search(pattern, raw, re.I) for pattern in patterns)


def _own_account_labels_in_text(text: str | None) -> set[str]:
    labels: set[str] = set()
    identity = current_identity()
    for iban, label in identity.own_account_ibans.items():
        if iban in _compact_account(text or ""):
            labels.add(label)
    for last4, label in identity.own_account_aliases.items():
        if _looks_like_account_reference(text, last4):
            labels.add(label)
    return labels


def _is_internal_transfer(concept: str | None = None, origin: str | None = None, destination: str | None = None, body: str | None = None, direction: str = "unknown") -> bool:
    concept_internal = _is_internal_concept(concept)
    body_internal = _is_internal_concept(body)

    origin_own = _contains_own_account(origin)
    destination_own = _contains_own_account(destination)
    labels = _own_account_labels_in_text(body)

    # Explicit own-account concepts from BAC/MultiMoney are never expenses.
    # Examples: INVERSION VISTA SMART, transferencia entre cuentas, debit applied
    # by another financial entity when the account is one of the holder's own accounts.
    if concept_internal and (origin_own or destination_own or labels):
        return True
    if body_internal and len(labels) >= 1:
        return True

    # Two own endpoints means this is only a money move between pockets.
    if origin_own and destination_own:
        return True

    # If both own accounts appear anywhere in the email body, this is a mirror
    # notification from the same transfer path and should not be reviewed.
    if len(labels) >= 2:
        return True

    return False


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
    # Every horizontal whitespace run (em spaces too) becomes one space, so no
    # pattern downstream backtracks over a long hostile run.
    text = re.sub(r"[^\S\n]+", " ", text)
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


# Thousands-grouped amounts with optional decimals ("15.000", "1,234.56", "₡15.000,00")
# or plain digits with optional decimals ("25000", "12.50"). (?!\d) stops "15.000"
# from matching as "15.00".
AMOUNT_PATTERN = r"\d{1,3}(?:[.,  ]\d{3})+(?:[.,]\d{1,2})?(?!\d)|\d+(?:[.,]\d{1,2})?(?!\d)"
# Amounts that cannot be a count or an index: thousands-grouped or with cents.
# Free-text searches try these first so "$ 3 por comisión y ₡15.000,00" is 15.000.
STRICT_AMOUNT_PATTERN = r"\d{1,3}(?:[.,  ]\d{3})+(?:[.,]\d{1,2})?(?!\d)|\d+[.,]\d{2}(?!\d)"


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
        # A single separator followed by exactly 3 digits groups thousands ("1,234");
        # 1-2 trailing digits are decimals ("1,5" / "1,50").
        parts = value.split(",")
        value = value.replace(",", ".") if len(parts) == 2 and len(parts[-1]) in (1, 2) else value.replace(",", "")
    elif "." in value:
        parts = value.split(".")
        if len(parts) > 2:
            value = "".join(parts[:-1]) + "." + parts[-1] if len(parts[-1]) == 2 else "".join(parts)
        elif len(parts[-1]) == 3:
            value = "".join(parts)  # "15.000" is fifteen thousand colones, never 15.0
    try:
        return float(value)
    except ValueError:
        return None


def _currency_code(value: str | None) -> str:
    raw = (value or "").upper()
    norm = normalize(raw)
    # normalize() lowercases and strips accents: "DÓLARES" -> "dolares".
    if "USD" in raw or "$" in raw or "dolar" in norm:
        return "USD"
    return "CRC"


def _parse_labeled_amount_value(value: str | None) -> tuple[float | None, str]:
    if not value:
        return None, "CRC"
    match = re.search(
        r"(?P<currency>CRC|USD|₡|¢|\$|colones?|d[oó]lares?)?\s*"
        rf"(?P<amount>{AMOUNT_PATTERN})\s*"
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
    currency = r"(?P<currency>colones?|CRC|USD|₡|¢|\$|d[oó]lares?)"
    for amount in (STRICT_AMOUNT_PATTERN, AMOUNT_PATTERN):
        patterns = [
            rf"por\s+un\s+monto\s+de\s*(?P<amount>{amount})\s*{currency}?",
            rf"monto\s*[:\-]?\s*{currency}?\s*(?P<amount>{amount})",
            rf"(?P<currency>₡|¢|CRC|USD|\$)\s*(?P<amount>{amount})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text or "", re.I)
            if match:
                value = _parse_number(match.group("amount"))
                code = _currency_code(match.groupdict().get("currency") or match.group(0))
                if value is not None and 0 < value < 20_000_000:
                    return value, code
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


CR_TZ = ZoneInfo("America/Costa_Rica")


def _local_date(value: str | None) -> str | None:
    """Calendar date in Costa Rica for an ISO timestamp (a 19:30 purchase is not tomorrow in UTC)."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(CR_TZ)
    return parsed.date().isoformat()


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
    local = _local_date(fallback)
    if local:
        return local
    return datetime.now(CR_TZ).date().isoformat()


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


def _labeled_code(text: str, label: str) -> str | None:
    """A reference-like code printed after a label ("Referencia: BDPC1234").

    It must contain a digit, so an empty field never captures the next label word.
    """
    flat = re.sub(r"\s+", " ", text or "")
    match = re.search(rf"{label} ?[:\-]? ?((?=[A-Z]*\d)[A-Z0-9]{{4,30}})\b", flat, re.I)
    return match.group(1) if match else None


def _sinpe_reference(subject: str, text: str) -> str | None:
    """The 25-digit SINPE reference; both banks print the same one for one transfer."""
    match = re.search(r"referencia ?[:\-]? ?(\d{25})(?!\d)", re.sub(r"\s+", " ", text or ""), re.I) \
        or re.search(r"transferencia ?(\d{25})(?!\d)", re.sub(r"\s+", " ", subject or ""), re.I)
    return match.group(1) if match else None


def _masked_account(value: str | None) -> str:
    """Keep only the last four digits of an account, card or IBAN (never the full number)."""
    digits = re.sub(r"\D", "", value or "")
    return f"****{digits[-4:]}" if len(digits) >= 4 else ""



def billing_cycle_for_date(transaction_date: str | date | None, cut_day: int = 21) -> tuple[str | None, str | None]:
    """Return BAC/card cycle window using configurable cut day.

    A BAC card is reviewed by cut cycle, not calendar month. Default:
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
        # Neutral for every account: the Owner's own family rule lives in
        # backend.finance.owner_category_compat and applies only in his scan.
        return "Transferencias"

    rules = [
        # Reglas explícitas antes de IA. Usar solo categorías oficiales para evitar
        # que normalize_category caiga en alias raros como "Horas extra".
        ("Servicios", ["openai", "chatgpt", "render.com", "render ", "supabase", "railway", "vercel", "github", "domain", "hosting", "openai api",
                       "cloudflare", "figma"]),
        # Recurring app, streaming and cloud-storage plans.
        ("Suscripciones", ["crunchyroll", "netflix", "spotify", "google one", "icloud", "apple.com/bill", "apple.com bill"]),
        ("Seguros", ["seguro ", "poliza", "póliza"]),
        # Training and memberships; a store with "sport"/"box" in its name sells equipment (Compras).
        ("Deporte", ["gym", "gimnasio", "novo fit", "coffee bar novo fit", "boxeo", "muay thai", "artes marciales"]),
        ("Entretenimiento", ["playstation", "ps plus", "supercell", "fs *supercell", "gossip", "kingshot", "juego", "store.supercell", "roku"]),
        ("Servicios", ["apple", "resume.io"]),
        ("Restaurante", ["taco bell", "pops", "mcdonald", "arcos dorados", "kfc", "restaurante", "sacc restaurante", "pizza", "burger", "uber eats",
                         # Cafés and snack stands: the catalog's cafetería.
                         "cafe ", "café", "coffee", "cafeteria", "cafetería", "granizado"]),
        ("Comida", ["maxi pali", "maxipali", "pali", "palí", "walmart", "am pm", "automercado", "auto mercado", "supermercado", "jose m.zeledon", "zeledon",
                    "comida"]),
        # BAC truncates merchant names (~22 chars): "ESTACION DE SERV.LA ..." is still a fuel station.
        ("Gasolina", ["gasolinera", "estacion de servicio", "estación de servicio", "estacion de serv", "combustible", "servicentro"]),
        # Vehicle inspection (RTV) is a transport cost.
        ("Transporte", ["uber rides", "uber", "parqueo", "taxi", "didi", "dekra"]),
        ("Salud", ["farmacia", "farmavalue", "hospital", "clinica", "clínica", "nutricionista", "terapia", "medico", "médico"]),
        ("Compras", ["temu", "amazon", "tienda", "ecommerce", "ishop", "aliss", "city mall", "shein", "zara", "pull&bear", "bershka", "barber shop", "las vegas",
                     "ferreteria", "ferretería", "ropa", "zapatos", "camisa"]),
        ("Teléfono", ["liberty", "linea", "línea", "movil", "móvil", "kolbi", "claro"]),
        ("Vivienda", ["casa", "alquiler"]),
    ]
    for category, words in rules:
        if any(word in clean for word in words):
            return category
    return FALLBACK_EXPENSE_CATEGORY


# No rule matched: the merchant is unknown. Storage maps this label to the
# catalog's default expense category, so the parse must say it is a guess.
FALLBACK_EXPENSE_CATEGORY = "Otros gastos"
# Below the email auto-commit threshold: a guess is never saved without review.
GUESS_CONFIDENCE_CAP = 0.9


def _card_greeting_name(text: str) -> str | None:
    """The cardholder BAC greets; flattened mail continues with "A continuación ..."."""
    flat = re.sub(r"[^\S\n]+", " ", text or "")
    match = re.search(r"Hola:? ?([^\n:]{3,90}?) ?(?::|\n|\bA continuaci|$)", flat)
    name = match.group(1).strip(" :") if match else ""
    return name or None


def _card_holder_from_greeting(text: str) -> str | None:
    name = _card_greeting_name(text)
    return current_identity().person(name, prefix=True) if name else None


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
        "transaction_date": _local_date(received_at) or parse_date(received_at or "", received_at),
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
    # Referencia identifies the charge; Autorización is the fallback.
    reference = _labeled_code(text, "Referencia") or _labeled_code(text, r"Autorizaci[oó]n") or _extract_reference(text)
    tipo_clean = normalize(tipo_raw)
    # The card's own credits are never ordinary income nor spending: a refund
    # reduces spending and a PAGO (e.g. RED PUNTOS) redeems points/cashback.
    movement_kind, direction = "card_purchase", "out"
    if any(word in tipo_clean for word in ["devolucion", "reversion", "reverso", "credito", "anulacion"]):
        transaction_type, category, movement_kind, direction = "transfer", "Reembolso", mt.KIND_REFUND, "in"
        taxonomy = mt.movement(mt.CARD_REFUND, mt.REFUND)
    elif tipo_clean.startswith("pago"):
        points = "puntos" in normalize(merchant) or "redencion" in normalize(merchant)
        transaction_type, category, direction = "transfer", "Reembolso", "in"
        movement_kind = mt.KIND_REWARD if points else mt.KIND_CARD_CREDIT
        taxonomy = mt.movement(mt.CARD_POINTS_CREDIT if points else mt.CARD_CREDIT, mt.REWARD if points else mt.REVIEW)
    else:
        transaction_type = "expense"
        category = infer_category(merchant, transaction_type)
        automatic = "cargo automatico" in tipo_clean
        taxonomy = mt.movement(mt.CARD_AUTOMATIC_CHARGE if automatic else mt.CARD_PURCHASE, mt.EXPENSE)
    if reference and direction == "in":
        # A refund may print the purchase's reference: keep the credit a movement of its own.
        reference = f"{movement_kind}:{reference}"
    amount_crc = round(amount * exchange_rate, 2) if currency == "USD" else round(amount, 2)
    # An additional card of the same account greets its own cardholder: the
    # charge is still billed to this account, but the user must see it is not theirs.
    greeting = _card_greeting_name(text)
    cardholder_mismatch = current_identity().names_holder(greeting) is False if greeting else False
    reason = "BAC compra: comercio, fecha, tipo, tarjeta, ciclo y monto extraídos por plantilla exacta."
    if cardholder_mismatch:
        reason = "BAC tarjeta adicional: el correo saluda a otra persona; confirmá si el cargo es tuyo."
    notes = ["BAC compra por plantilla", f"tipo: {tipo_raw.strip()}"]
    if card_last4:
        notes.append(f"tarjeta ****{card_last4}")
    if holder:
        notes.append(f"titular correo: {holder}")
    if cardholder_mismatch:
        notes.append("tarjeta a nombre de otra persona (adicional); revisar antes de confirmar")
    if reference:
        notes.append(f"referencia {reference}")
    if time_value:
        notes.append(f"hora: {time_value}")
    if currency == "USD":
        notes.append(f"monto original USD {amount:.2f}; TC {exchange_rate} asumido, sin evidencia")
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
        # The notice prints no rate: the caller's default is an assumption. The real
        # rate is known only when the card's USD balance is paid (receipt or statement).
        "exchange_rate_source": "assumed_default" if currency == "USD" else None,
        "card_last4": card_last4,
        "card_owner": holder,
        "cardholder_mismatch": cardholder_mismatch,
        "billing_cycle_start": cycle_start,
        "billing_cycle_end": cycle_end,
        "reference": reference,
        "movement_direction": direction,
        **taxonomy,
        "movement_kind": movement_kind,
        "dedupe_key": f"bac_card|{transaction_date}|{card_last4 or ''}|{round(amount_crc,2)}|{normalize(merchant)}|{unique_part}",
        "confidence": 0.9 if cardholder_mismatch else 0.99,
        "confidence_reason": reason,
    }

def _normalize_person_name_from_text(value: str | None) -> str:
    return current_identity().person(value)


def _parse_bac_sinpe_movil(subject: str, sender: str, body: str, received_at: str | None) -> dict[str, Any] | None:
    """Parse BAC SINPE Móvil receipts (someone -> the mailbox holder).

    These emails do not always include an IBAN. They identify payer, recipient,
    phone, amount and detail. Incoming payments from the holder's configured
    receivable contacts are used later to reconcile cuentas por cobrar.
    """
    text = clean_text("\n".join([subject or "", body or ""]))
    clean = normalize(text)
    if "sinpe movil" not in clean and "sinpe móvil" not in (text or "").lower():
        return None
    if "transferencia" not in clean or "monto" not in clean:
        return None
    if _has_rejected_movement(text):
        return _rejected("bac", subject, body, received_at, "Transferencia SINPE Móvil rechazada/no aplicada; no afecta finanzas.")

    amount, _currency = _parse_context_amount(text)
    if amount is None or amount <= 0:
        return None
    transaction_date, time_value = _parse_datetime_text(text, received_at)

    payer_match = re.search(
        r"le\s+informamos\s+que\s+(.+?)\s+realiz[oó]\s+una\s+transferencia\s+por\s+medio\s+de\s+SINPE\s+M[oó]vil",
        text,
        re.I | re.S,
    )
    recipient_match = re.search(r"a\s+nombre\s+de\s+([A-ZÁÉÍÓÚÑ_\s\.]+?)(?:\.|\n|Referencia|Fecha|Hora|Monto|Detalle|$)", text, re.I | re.S)
    phone_match = re.search(r"tel[eé]fono\s+N?[°ºO]?\s*(\d{8})", text, re.I)
    reference_match = re.search(r"Referencia\s+(\d{8,})", text, re.I)
    detail_match = re.search(r"Detalle\s+([^\n]+)", text, re.I)

    payer = _normalize_person_name_from_text(payer_match.group(1) if payer_match else "")
    recipient = _normalize_person_name_from_text(recipient_match.group(1) if recipient_match else "")
    detail = re.sub(r"[_\s]+", " ", detail_match.group(1)).strip(" .") if detail_match else "SINPE Móvil recibido"

    if not recipient:
        # A named recipient is needed to classify this as an incoming alert.
        return None

    identity = current_identity()
    description = f"SINPE recibido de {payer}" if payer and not identity.is_holder(payer) else "SINPE Móvil recibido"
    notes = ["BAC SINPE Móvil", "entrada"]
    if payer:
        notes.append(f"payer: {payer}")
    if recipient:
        notes.append(f"recipient: {recipient}")
    if phone_match:
        notes.append(f"telefono destino: {phone_match.group(1)}")
    if detail:
        notes.append(f"detalle: {detail}")
    if reference_match:
        notes.append(f"referencia {reference_match.group(1)}")
    if time_value:
        notes.append(f"hora: {time_value}")

    category = "Reembolsos"
    if identity.is_receivable_contact(payer):
        category = "Cuentas por cobrar"

    # Some SINPE Móvil notices include the credited bank account as well as
    # the phone number. Only capture an explicitly labeled account here; a
    # phone number or payer name must never become an account identity.
    destination_account = _extract_account_near(text, ["cuenta destino", "cuenta acreditada", "a su cuenta"])

    return {
        **_base_result("bac", "movement", received_at),
        "transaction_date": transaction_date,
        "transaction_time": time_value,
        "description": description[:240],
        "amount": round(amount, 2),
        "transaction_type": "income",
        "category": category,
        "account": "BAC SINPE Móvil",
        "notes": " | ".join(notes),
        "dedupe_key": f"sinpe_movil_in|{transaction_date}|{round(amount,2)}|{reference_match.group(1) if reference_match else normalize(description)}",
        "confidence": 0.99,
        "confidence_reason": "BAC SINPE Móvil: ingreso, pagador, monto, fecha y referencia extraídos por plantilla exacta.",
        "movement_direction": "in",
        "destination_account": destination_account,
        "payer_name": payer,
        "recipient_name": recipient,
    }

def _parse_bac_sinpe(subject: str, sender: str, body: str, received_at: str | None) -> dict[str, Any] | None:
    text = clean_text("\n".join([subject or "", body or ""]))
    clean = normalize(text)
    is_transfer_notice = "transferencia" in clean and "monto" in clean
    is_sinpe_notice = "sinpe" in clean and is_transfer_notice
    is_local_transfer_notice = (
        is_transfer_notice
        and ("transferencia local" in clean or "transferencia electronica" in clean or "transferencia electrónica" in text.lower())
        and "notificacion de transaccion" not in clean
    )
    if not (is_sinpe_notice or is_local_transfer_notice):
        return None

    if _has_rejected_movement(text):
        return _rejected("bac", subject, body, received_at, "Transferencia SINPE rechazada/no aplicada; no afecta finanzas.")

    amount, _currency = _parse_context_amount(text)
    if amount is None or amount <= 0:
        return None

    # "Día y hora 12/09/2026 07:22:13 p.m." — keep the a.m./p.m. marker (it contains dots).
    date_match = re.search(
        r"d[ií]a\s+y\s+hora\s*:?\s*(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s*[ap]\.?\s?m\.?)?)",
        text, re.I,
    ) or re.search(r"d[ií]a\s+y\s+hora\s*:??\s*([^\.\n]+)", text, re.I)
    transaction_date, time_value = _parse_datetime_text(date_match.group(1) if date_match else text, received_at)

    is_out = "debitando su cuenta" in clean or "debito" in clean or "débito" in clean
    is_in = (
        "se acredito" in clean
        or "se acredito en la cuenta" in clean
        or "se acreditó" in (body or "").lower()
        or "se aplico en la cuenta" in clean
        or "recibio una transferencia" in clean
        or "acreditando" in clean
        or ("a su cuenta" in clean and not is_out)
    )
    # If both debit and credit appear in one notice, the posting direction is
    # ambiguous. Leave it for review instead of counting it as a debit.
    direction = "out" if is_out and not is_in else "in" if is_in and not is_out else "unknown"
    if direction == "unknown":
        is_out = is_in = False

    concept_match = re.search(r"por\s+concepto\s+de\s+(.+?)(?:\s+Monto\b|\.?D[ií]a\s+y\s+hora|\n|$)", text, re.I | re.S)
    concept = re.sub(r"[_\s]+", " ", concept_match.group(1)).strip(" .") if concept_match else ""
    reference_match = re.search(r"referencia\s+(\d{8,})", text, re.I)
    sinpe_reference = _sinpe_reference(subject, text)

    origin_account = _extract_account_near(text, ["cuenta origen", "cuenta debitada", "debitando su cuenta", "desde la cuenta", "de la cuenta"])
    destination_account = _extract_account_near(text, ["cuenta destino", "cuenta acreditada", "acreditando la cuenta", "a la cuenta", "a su cuenta", "hacia la cuenta", "al iban", "iban destino"])
    ibans = _extract_ibans(text)
    if not origin_account and direction == "out" and ibans:
        # BAC often mentions the debited own account first.
        origin_account = ibans[0]
    if not destination_account and direction == "in" and ibans:
        # Incoming notifications usually mention the credited own account.
        destination_account = ibans[-1]
    # Current notices mask the IBAN ("su cuenta IBAN CR0001XXXXXXXXXXXX1234"):
    # it is the holder's account on the side the notice describes.
    masked_iban = re.search(r"IBAN\s+(CR[\dX*]{8,30})", text, re.I)
    if masked_iban and direction == "out" and not origin_account:
        origin_account = _masked_account(masked_iban.group(1))
    if masked_iban and direction == "in" and not destination_account:
        destination_account = _masked_account(masked_iban.group(1))

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

    # A SINPE notice never names the other side: a credit may be income, a refund
    # or the holder's own money from another bank, and a debit may be spending or
    # a move to their own account. It stays a transfer with a known direction; the
    # user (or a correlation with the other bank's notice) decides the effect.
    transaction_type = "transfer"
    category = infer_category(description_base, transaction_type)
    if is_out and not destination_account:
        notes.append("destino no visible en correo BAC; confirmá si fue un gasto o un traslado propio")
    if is_in:
        notes.append("origen no visible en correo BAC; confirmá si fue un ingreso o un traslado propio")

    description = description_base
    if is_out and normalize(description) in {"sinpe enviado", "transferencia sinpe"}:
        description = "SINPE enviado"
    elif is_in and normalize(description) in {"sinpe recibido", "transferencia sinpe"}:
        description = "SINPE recibido"
    bank_movement = mt.SINPE_OUT if is_out else mt.SINPE_IN if is_in else mt.TRANSFER_UNKNOWN
    reference = sinpe_reference or (reference_match.group(1) if reference_match else None)

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
        "reference": reference,
        **mt.movement(bank_movement, mt.REVIEW, "transfer"),
        "dedupe_key": f"sinpe|{transaction_date}|{round(amount,2)}|{reference or normalize(description)}|{direction}",
        "confidence": 0.98,
        "confidence_reason": "BAC SINPE: dirección, monto, referencia, cuenta y fecha extraídos por plantilla exacta; el correo no identifica la otra parte.",
        "movement_direction": direction,
        "origin_account": origin_account,
        "destination_account": destination_account,
    }

MULTIMONEY_ENDPOINT_RE = (
    r"Cuenta\s+{side}\s*:?\s*Titular\s*:?\s*(?P<holder>.{{1,90}}?)\s+Cuenta\s*:?\s*"
    r"(?P<currency>CRC|USD)?\s*(?P<account>CR[0-9Xx*]{{4,30}})"
)


def _multimoney_endpoint(text: str, side: str) -> dict[str, str] | None:
    """One side of a MultiMoney transfer: printed holder, currency and account.

    Works on multi-line and on flattened mail ("Cuenta origen: Titular: X Cuenta: CRC CR00****1234").
    """
    flat = re.sub(r"\s+", " ", clean_text(text or ""))
    match = re.search(MULTIMONEY_ENDPOINT_RE.format(side=side), flat, re.I)
    if not match:
        return None
    return {
        "holder": match.group("holder").strip(" :"),
        "currency": (match.group("currency") or "").upper(),
        "raw": match.group("account"),
        "account": _masked_account(match.group("account")),
    }


def _multimoney_clock(transaction_date: str, time_value: str | None, received_at: str | None) -> tuple[str, str | None]:
    """MultiMoney prints Costa Rica time, but for months it printed UTC.

    Read the printed time as UTC only when it matches the email's own UTC
    timestamp (within minutes) and does not match its Costa Rica time.
    """
    if not time_value or not received_at:
        return transaction_date, time_value
    try:
        printed = datetime.fromisoformat(f"{transaction_date}T{time_value}")
        received = datetime.fromisoformat(received_at.strip().replace("Z", "+00:00"))
    except ValueError:
        return transaction_date, time_value
    if received.tzinfo is None:
        return transaction_date, time_value
    window = timedelta(minutes=15)
    local = received.astimezone(CR_TZ).replace(tzinfo=None)
    utc = received.astimezone(timezone.utc).replace(tzinfo=None)
    if abs(printed - local) <= window or abs(printed - utc) > window:
        return transaction_date, time_value
    converted = printed.replace(tzinfo=timezone.utc).astimezone(CR_TZ)
    return converted.date().isoformat(), converted.strftime("%H:%M:%S")


def _parse_bac_loan_disbursement(subject: str, sender: str, body: str, received_at: str | None) -> dict[str, Any] | None:
    """BAC credit drawn against a card ("extrafinanciamiento") paid into an account: debt, never income."""
    text = clean_text("\n".join([subject or "", body or ""]))
    clean = normalize(text)
    if not ("ha recibido su desembolso" in clean and "desembolsado a" in clean):
        return None
    match = re.search(r"desembolso\s*:?\s*(?P<currency>CRC|USD|₡|¢|\$)\s*(?P<amount>[\d.,]+)", text, re.I)
    amount = _parse_number(match.group("amount")) if match else None
    if amount is None or amount <= 0:
        return None
    currency = _currency_code(match.group("currency"))
    account = re.search(r"a\s+la\s+cuenta\s*:?\s*(\d{6,22})", text, re.I)
    card = re.search(r"tarjeta\s+de\s+cobro\s*:?\s*\d{4,6}X+(\d{4})", text, re.I)
    term = re.search(r"plazo\s*:?\s*(\d{1,3})\s*meses", text, re.I)
    installment = re.search(r"cuota\s+mensual\s*:?\s*(?:CRC|USD|₡|¢|\$)\s*([\d.,]+)", text, re.I)
    destination = _masked_account(account.group(1)) if account else ""
    notes = ["BAC desembolso de crédito sobre tarjeta", "deuda nueva, no es ingreso"]
    if term:
        notes.append(f"plazo {term.group(1)} meses")
    if installment:
        notes.append(f"cuota mensual {installment.group(1)}")
    if card:
        notes.append(f"tarjeta de cobro ****{card.group(1)}")
    transaction_date = _local_date(received_at) or parse_date(received_at or "", received_at)
    return {
        **_base_result("bac", "movement", received_at),
        "transaction_date": transaction_date,
        "description": "Desembolso de crédito BAC",
        "amount": round(amount, 2),
        "transaction_type": "transfer",
        "category": "Otros préstamos",
        "account": "BAC",
        "notes": " | ".join(notes),
        "original_amount": amount if currency == "USD" else None,
        "original_currency": "USD" if currency == "USD" else None,
        "card_last4": card.group(1) if card else None,
        **mt.movement(mt.LOAN_DISBURSEMENT, mt.LIABILITY, mt.KIND_LOAN_DISBURSEMENT),
        "dedupe_key": f"bac_loan_disbursement|{transaction_date}|{round(amount, 2)}|{destination}",
        "confidence": 0.97,
        "confidence_reason": "BAC: desembolso de crédito a tu cuenta; es deuda, no ingreso.",
        "movement_direction": "in",
        "destination_account": destination,
    }


def _parse_multimoney_disbursement(subject: str, sender: str, body: str, received_at: str | None) -> dict[str, Any] | None:
    """Loan / credit-line proceeds credited to the holder's account: debt, never income."""
    text = clean_text("\n".join([subject or "", body or ""]))
    clean = normalize(text)
    # Both observed notices name the credit ("de tu línea de crédito", "Depositamos tu crédito").
    if not (("te hemos acreditado" in clean or "depositamos tu credito" in clean) and "credito" in clean):
        return None
    match = re.search(r"acreditado\s*:?\s*(?P<currency>CRC|USD|₡|¢|\$)\s*(?P<amount>[\d.,]+)", text, re.I)
    amount = _parse_number(match.group("amount")) if match else None
    if amount is None or amount <= 0:
        return None
    currency = _currency_code(match.group("currency"))
    account = re.search(r"a\s+la\s+cuenta\s*:?\s*(CR[0-9Xx*]{4,30})", text, re.I)
    reference = re.search(r"referencia\s*:?\s*(\d{10,30})", text, re.I)
    when = re.search(r"Fecha\s+y\s+hora\s*:?\s*(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}(?::\d{2})?)", text, re.I)
    transaction_date, time_value = _parse_datetime_text(when.group(1) if when else "", received_at)
    destination = _masked_account(account.group(1)) if account else ""
    return {
        **_base_result("multimoney", "movement", received_at),
        "transaction_date": transaction_date,
        "transaction_time": time_value,
        "description": "Desembolso de crédito MultiMoney",
        "amount": round(amount, 2),
        "transaction_type": "transfer",
        "category": "Otros préstamos",
        "account": "MultiMoney",
        "notes": "MultiMoney desembolso de crédito | deuda nueva, no es ingreso",
        "original_amount": amount if currency == "USD" else None,
        "original_currency": "USD" if currency == "USD" else None,
        "reference": reference.group(1) if reference else None,
        **mt.movement(mt.LOAN_DISBURSEMENT, mt.LIABILITY, mt.KIND_LOAN_DISBURSEMENT),
        "dedupe_key": f"multimoney_disbursement|{transaction_date}|{round(amount, 2)}|{reference.group(1) if reference else ''}",
        "confidence": 0.97,
        "confidence_reason": "MultiMoney: desembolso de crédito a tu cuenta; es deuda, no ingreso.",
        "movement_direction": "in",
        "destination_account": destination,
    }


def _parse_multimoney_transfer(subject: str, sender: str, body: str, received_at: str | None) -> dict[str, Any] | None:
    text = clean_text("\n".join([sender or "", subject or "", body or ""]))
    clean = normalize(text)
    if not ("multimoney" in clean and "monto" in clean and "fecha" in clean):
        return None
    if _has_rejected_movement(text):
        return _rejected("multimoney", subject, body, received_at, "Movimiento MultiMoney rechazado/no aplicado; no afecta finanzas.")

    if not (
        "resumen de operacion" in clean
        or "operacion realizada" in clean
        or "se aplico un debito" in clean
        or "se aplicó un débito" in clean
        or "notificacion de transferencia" in clean
        or "recepcion de fondos" in clean
        or "recepción de fondos" in clean
        or "recibimos tu pago" in clean
        or "se aplico un credito" in clean
        or "credito en tiempo real" in clean
        or "acreditamos tu cuenta" in clean
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
    origin = _multimoney_endpoint(text, "origen")
    destination = _multimoney_endpoint(text, "destino")
    reference = _sinpe_reference(subject, text) or _labeled_code(text, "Referencia") or ""

    is_debit = "se aplico un debito" in clean or "debito en tiempo real" in clean or "debito aplicado por otra entidad" in clean
    is_received = (
        "recepcion de fondos" in clean
        or "se aplico un credito" in clean or "credito en tiempo real" in clean
        or "acreditamos tu cuenta" in clean
    )
    is_payment_received = "recibimos tu pago" in clean
    identity = current_identity()
    origin_is_holder = identity.names_holder(origin["holder"]) if origin else None
    destination_is_holder = identity.names_holder(destination["holder"]) if destination else None
    own_funding = "inversion vista smart" in normalize(concept)
    both_holder = origin_is_holder is True and destination_is_holder is True

    if is_payment_received:
        direction = "payment"  # parser vocabulary; canonical_direction maps a debt payment to "out"
    elif is_debit and is_received:
        direction = "unknown"
    elif is_debit:
        direction = "out"
    elif is_received or own_funding:
        direction = "in"
    elif both_holder:
        direction = "unknown"  # one notice describes both of the holder's accounts
    elif origin_is_holder is True and destination_is_holder is False:
        direction = "out"
    elif destination_is_holder is True and origin_is_holder is False:
        direction = "in"
    else:
        direction = "unknown"

    if not is_payment_received:
        # For some months MultiMoney printed UTC; payment receipts use another clock.
        transaction_date, time_value = _multimoney_clock(transaction_date, time_value, received_at)

    origin_account = origin["account"] if origin else ""
    destination_account = destination["account"] if destination else ""
    if is_debit and not origin_account:
        debited = re.search(r"Cuenta\s*:?\s*(CR[0-9Xx*]{4,30})", text, re.I)
        origin_account = _masked_account(debited.group(1)) if debited else ""

    notes = ["MultiMoney transferencia por plantilla"]
    if origin_account:
        notes.append(f"origen: {origin_account}")
    if destination_account:
        notes.append(f"destino: {destination_account}")
    if reference:
        notes.append(f"referencia: {reference}")
    if time_value:
        notes.append(f"hora: {time_value}")

    # Owner legacy identity only: configured own accounts mark an internal move.
    origin_text = f"{origin['holder']} / {origin['raw']}" if origin else ""
    destination_text = f"{destination['holder']} / {destination['raw']}" if destination else ""
    if _is_internal_transfer(concept, origin_text, destination_text, text, direction):
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
            "origin_account": origin_account,
            "destination_account": destination_account,
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
        # A loan payment receipt: the promissory note and time identify it.
        pagare = re.search(r"Pagar[eé]\s*:?\s*([A-Z]-?\d{3,})", text, re.I)
        reference = " ".join(part for part in [pagare.group(1) if pagare else "", transaction_date, time_value or ""] if part)
        transaction_type, category, description = "debt_payment", "MultiMoney", "Pago recibido MultiMoney"
        taxonomy = mt.movement(mt.LOAN_PAYMENT, mt.DEBT_PAYMENT)
    else:
        # Transfers never become income or spending here: the notice does not
        # prove the effect. Explicit own-account wording is recorded as a hint.
        transaction_type, category, description = "transfer", infer_category(concept, "transfer"), concept
        if is_debit:
            taxonomy = mt.movement(mt.REALTIME_DEBIT, mt.REVIEW, "transfer")
        elif own_funding:
            taxonomy = mt.movement(mt.OWN_ACCOUNT_FUNDING, mt.OWN_TRANSFER_LIKELY, "transfer")
        elif both_holder:
            fx = bool(origin and destination and origin["currency"] and destination["currency"]
                      and origin["currency"] != destination["currency"])
            taxonomy = mt.movement(mt.FX_CONVERSION if fx else mt.OWN_ACCOUNT_TRANSFER, mt.OWN_TRANSFER_LIKELY, "transfer")
        else:
            bank_movement = mt.TRANSFER_OUT if direction == "out" else mt.TRANSFER_IN if direction == "in" else mt.TRANSFER_UNKNOWN
            taxonomy = mt.movement(bank_movement, mt.REVIEW, "transfer")

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
        "reference": reference or None,
        **taxonomy,
        "dedupe_key": f"multimoney|{transaction_date}|{round(amount,2)}|{reference or normalize(description)}|{direction}",
        "confidence": 0.97,
        "confidence_reason": "MultiMoney: concepto, monto, fecha, referencia y cuentas extraídos por plantilla exacta.",
        "movement_direction": direction,
        "origin_account": origin_account,
        "destination_account": destination_account,
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


def _parse_bac_card_payment(subject: str, body: str, received_at: str | None) -> dict[str, Any] | None:
    """"Comprobante de Pago de Tarjeta": the holder's account pays the holder's credit card.

    Money leaves the account and the card debt goes down: a move between the
    holder's own products, never spending (the card purchases already are).
    """
    text = re.sub(r"\s+", " ", clean_text("\n".join([subject or "", body or ""])))
    paid = re.search(r"Monto\s+del\s+pago\s*:?\s*([\d.,]+)\s*(CRC|USD)", text, re.I)
    debited = re.search(r"Monto\s+del\s+d[eé]bito\s*:?\s*([\d.,]+)\s*(CRC|USD)", text, re.I)
    money = debited or paid
    amount = _parse_number(money.group(1)) if money else None
    if amount is None or amount <= 0:
        return None
    currency = money.group(2).upper()
    card = re.search(r"Tarjeta\s+de\s+Cr[eé]dito\s+N[uú]mero\s*:?\s*([\d*Xx\- ]{8,25}\d{4})", text, re.I)
    origin = re.search(r"Cuenta\s+Origen\s+N[uú]mero\s*:?\s*([\d*Xx]{4,24})", text, re.I)
    rate = re.search(r"Tipo\s+de\s+Cambio\s*:?\s*([\d.,]+)", text, re.I)
    reference = re.search(r"Referencia\s*:?\s*(\d{3,})", text, re.I)
    paid_on = re.search(r"Fecha\s+de\s+pago\s*:?\s*(\d{4}/\d{1,2}/\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)", text, re.I)
    transaction_date, time_value = _parse_datetime_text(paid_on.group(1) if paid_on else "", received_at)
    card_account = _masked_account(card.group(1)) if card else ""
    origin_account = _masked_account(origin.group(1)) if origin else ""
    # BAC reuses its 4-digit payment reference; with the payment time it is unique.
    unique_reference = " ".join(part for part in [reference.group(1) if reference else "", transaction_date, time_value or ""] if part)
    notes = ["BAC pago de tarjeta por plantilla", "traslado de cuenta propia a tarjeta propia"]
    if paid:
        notes.append(f"monto del pago {paid.group(1)} {paid.group(2).upper()}")
    exchange_rate = _parse_number(rate.group(1)) if rate else None
    if paid and debited and paid.group(2).upper() != debited.group(2).upper() and exchange_rate:
        notes.append(f"tipo de cambio {exchange_rate}")
    return {
        **_base_result("bac", "movement", received_at),
        "transaction_date": transaction_date,
        "transaction_time": time_value,
        "description": f"Pago de tarjeta {card_account}".strip(),
        "amount": round(amount, 2),
        "transaction_type": "transfer",
        "category": "Tarjeta BAC",
        "account": f"BAC {origin_account}".strip(),
        "notes": " | ".join(notes),
        "original_amount": amount if currency == "USD" else None,
        "original_currency": "USD" if currency == "USD" else None,
        "exchange_rate": exchange_rate if exchange_rate and exchange_rate != 1 else None,
        "exchange_rate_source": "email" if exchange_rate and exchange_rate != 1 else None,
        "reference": unique_reference or None,
        **mt.movement(mt.CARD_PAYMENT, mt.OWN_TRANSFER_LIKELY, mt.KIND_CARD_PAYMENT),
        "dedupe_key": f"bac_card_payment|{transaction_date}|{round(amount, 2)}|{unique_reference}",
        "confidence": 0.97,
        "confidence_reason": "BAC pago de tarjeta: cuenta origen, tarjeta, montos y tipo de cambio por plantilla exacta; no es gasto.",
        "movement_direction": "out",
        "origin_account": origin_account,
        "destination_account": card_account,
    }


_REDEMPTION_CARD = re.compile(r"tarjeta\s+(\d{4}-\d{2}\*\*-\*{4}-(\d{4}))", re.I)
_REDEMPTION_AMOUNT = re.compile(r"Puntos[\s*#|]*=[\s*#|]*([0-9][0-9.,]*)\s*(CRC|USD)", re.I)
_REDEMPTION_REFERENCE = re.compile(r"N[uú]mero\s+de\s+Referencia\s*:?[\s*#|]*([0-9][0-9-]{3,40}[0-9])", re.I)
_REDEMPTION_DESTINATION = re.compile(r"Producto\s+destino\s*:?[\s*#|]*(CR[0-9Xx*]{4,30}|[0-9Xx*]{4,30})", re.I)


def _parse_bac_reward_redemption(subject: str, sender: str, body: str, received_at: str | None) -> dict[str, Any] | None:
    """BAC points/cashback redemption receipt: points become money in a destination product.

    The receipt's footer refers to the statement ("verifique su estado de cuenta"), so it is
    recognized before statement detection. The credit is a reward: never spending and never
    ordinary income; the destination product is reported for ownership resolution.
    """
    text = clean_text("\n".join([sender or "", subject or "", body or ""]))
    clean = normalize(text)
    if not ("comprobante de redencion" in clean and "redencion de puntos" in clean):
        return None
    amount_match = _REDEMPTION_AMOUNT.search(text)
    if not amount_match:
        return None
    amount = _parse_number(amount_match.group(1))
    if amount is None or amount <= 0:
        return None
    currency = amount_match.group(2).upper()
    card = _REDEMPTION_CARD.search(text)
    card_last4 = card.group(2) if card else None
    destination = _REDEMPTION_DESTINATION.search(text)
    destination_account = _masked_account(destination.group(1)) if destination else ""
    reference_match = _REDEMPTION_REFERENCE.search(text)
    reference = reference_match.group(1) if reference_match else ""
    date_raw = _label_value(text, r"Fecha de redenci[oó]n") or text
    transaction_date, time_value = _parse_datetime_text(date_raw.replace(";", ""), received_at)
    notes = ["BAC redención de puntos por plantilla"]
    if card_last4:
        notes.append(f"tarjeta ****{card_last4}")
    if destination_account:
        notes.append(f"destino: {destination_account}")
    if reference:
        notes.append(f"referencia {reference}")
    return {
        **_base_result("bac", "movement", received_at),
        "transaction_date": transaction_date,
        "transaction_time": time_value,
        "description": "Redención de puntos BAC",
        "amount": round(amount, 2),
        "currency": currency,
        "transaction_type": "transfer",
        "category": "Reembolso",
        "account": f"BAC ****{card_last4}" if card_last4 else "BAC Tarjeta",
        "notes": " | ".join(notes),
        "card_last4": card_last4,
        "destination_account": destination_account,
        "reference": f"{mt.KIND_REWARD}:{reference}" if reference else "",
        "movement_direction": "in",
        **mt.movement(mt.CARD_POINTS_CREDIT, mt.REWARD),
        "movement_kind": mt.KIND_REWARD,
        "dedupe_key": f"bac_reward|{transaction_date}|{card_last4 or ''}|{round(amount, 2)}|{reference or time_value or ''}",
        "confidence": 0.95,
        "confidence_reason": "BAC comprobante de redención: puntos, monto, producto destino y referencia por plantilla exacta.",
    }


def _parse_bac_cardless_withdrawal(subject: str, sender: str, body: str, received_at: str | None) -> dict[str, Any] | None:
    """Cardless ATM withdrawal: creating the code moves nothing; the withdrawal is cash out."""
    if "retiro sin tarjeta" not in normalize(subject) or "alerta@baccredomatic.com" not in normalize(sender):
        return None
    text = re.sub(r"\s+", " ", clean_text(body or ""))
    clean = normalize(text)
    if "exitosamente" not in clean or "se retiro" not in clean or "no se retiro" in clean:
        return _ignored("bac", subject, body, received_at, "Código de retiro sin tarjeta creado; todavía no hay movimiento de dinero.")
    money = re.search(r"Monto\s*:?\s*([\d.,]+)\s*(CRC|USD)", text, re.I)
    amount = _parse_number(money.group(1)) if money else None
    if amount is None or amount <= 0:
        return None
    currency = money.group(2).upper()
    when = re.search(r"se\s+retir[oó]\s+el\s+dinero\s*:?\s*(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}(?::\d{2})?)", text, re.I)
    transaction_date, time_value = _parse_datetime_text(when.group(1) if when else "", received_at)
    return {
        **_base_result("bac", "movement", received_at),
        "transaction_date": transaction_date,
        "transaction_time": time_value,
        "description": "Retiro sin tarjeta",
        "amount": round(amount, 2),
        "transaction_type": "transfer",
        "category": "Retiro de efectivo",
        "account": "BAC",
        "notes": "BAC retiro sin tarjeta | efectivo retirado de tu cuenta; no es un gasto por sí mismo",
        "original_amount": amount if currency == "USD" else None,
        "original_currency": "USD" if currency == "USD" else None,
        **mt.movement(mt.CASH_WITHDRAWAL, mt.CASH, mt.KIND_CASH_WITHDRAWAL),
        "dedupe_key": f"bac_cardless|{transaction_date}|{time_value or ''}|{round(amount, 2)}",
        "confidence": 0.95,
        "confidence_reason": "BAC retiro sin tarjeta: monto, fecha y hora por plantilla exacta.",
        "movement_direction": "out",
    }


def _parse_bac_alert_payment(subject: str, sender: str, body: str, received_at: str | None) -> dict[str, Any] | None:
    """Parse alerta@baccredomatic.com messages: service payments, card payments, deposits.

    These were previously ignored, but they contain important money movements.
    """
    text = clean_text("\n".join([subject or "", body or ""]))
    clean = normalize(text)
    sender_clean = normalize(sender)
    if "alerta@baccredomatic.com" not in sender_clean:
        return None
    if "comprobante de pago de tarjeta" in clean and not _has_rejected_movement(text):
        card_payment = _parse_bac_card_payment(subject, body, received_at)
        if card_payment:
            return card_payment

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

    extras: dict[str, Any] = {}
    if is_deposit and re.search(r"\b(salario|planilla|nomina|pago salarial)\b", clean):
        # Income only on the notice's own words; payroll_income decides if it is salary.
        transaction_type = "income"
        description = "Depósito BAC"
        category = "Otros ingresos"
        account = "BAC Depósito"
        reason = "BAC depósito: monto y fecha por plantilla alerta; el aviso menciona salario/planilla."
    elif is_deposit:
        # A deposit notice names the receiving account, never the payer: like a SINPE
        # credit it may be income, a refund or the holder's own money. It stays an
        # inbound transfer and the user (or a correlation) decides its effect.
        transaction_type = "transfer"
        description = "Depósito BAC"
        category = infer_category(description, transaction_type)
        account = "BAC Depósito"
        reason = "BAC depósito: monto y fecha por plantilla alerta; el aviso no identifica quién depositó."
        extras = {**mt.movement(mt.TRANSFER_IN, mt.REVIEW, "transfer"), "movement_direction": "in",
                  "reference": _labeled_code(text, r"N[uú]mero\s+de\s+referencia")}
    elif _is_card_payment(text):
        return _ignored("bac", subject, body, received_at, "Pago de tarjeta BAC detectado; se ignora para evitar doble conteo porque las compras individuales ya son los gastos.")
    else:
        transaction_type = "expense"
        target = _extract_named_payment_target(text)
        description = target if target != "Movimiento BAC" else (subject or "Pago BAC")
        category = infer_category(description, "expense")
        account = f"BAC ****{card_last4}" if card_last4 else "BAC Pago"
        reason = "BAC pago de servicio: monto, fecha y servicio extraídos por plantilla alerta."
        # "Número de Autorización" identifies the payment (two same-day bills stay two).
        extras = {**mt.movement(mt.SERVICE_PAYMENT, mt.EXPENSE),
                  "reference": _labeled_code(text, r"N[uú]mero\s+de\s+Autorizaci[oó]n")}

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
        **extras,
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


def _rejected(bank: str, subject: str, body: str, received_at: str | None, reason: str) -> dict[str, Any]:
    """A rejected transfer moves no money. Its bank reference is kept because another
    institution may still have announced the same transfer (e.g. "débito aplicado"):
    that notice is cancelled by this reference, never counted."""
    text = clean_text("\n".join([subject or "", body or ""]))
    reference = re.search(r"referencia\s*:?\s*(\d{10,30})", text, re.I)
    return {**_ignored(bank, subject, body, received_at, reason), "rejected_reference": reference.group(1) if reference else None}


def cancelled_by_rejection(parsed: dict[str, Any], rejected_references: set[str]) -> bool:
    """True when a movement's reference was later reported rejected by the other bank."""
    reference = str(parsed.get("reference") or "")
    return bool(reference) and parsed.get("email_kind") == "movement" and reference in rejected_references


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
    if bank == "bac" and _parse_bac_reward_redemption(subject, sender, body, None):
        return "movement", "Redención de puntos BAC estructurada detectada."
    if _parse_statement(subject, sender, body, None):
        return "statement", "Estado de cuenta detectado; queda como documento pendiente."
    if bank == "bac":
        parsed = (
            _parse_bac_purchase(subject, sender, body, None, 495.0) or _parse_bac_loan_disbursement(subject, sender, body, None)
            or _parse_bac_sinpe_movil(subject, sender, body, None)
            or _parse_bac_sinpe(subject, sender, body, None) or _parse_bac_cardless_withdrawal(subject, sender, body, None)
            or _parse_bac_alert_payment(subject, sender, body, None)
        )
        if parsed:
            if parsed.get("email_kind") == "ignored":
                return "ignored", parsed.get("ignore_reason") or "Movimiento BAC descartado por reglas de seguridad financiera."
            return "movement", "Movimiento BAC estructurado detectado."
    if bank == "multimoney":
        parsed = _parse_multimoney_disbursement(subject, sender, body, None) or _parse_multimoney_transfer(subject, sender, body, None)
        if parsed:
            if parsed.get("email_kind") == "ignored":
                return "ignored", parsed.get("ignore_reason") or "Movimiento MultiMoney descartado por reglas de seguridad financiera."
            return "movement", "Movimiento MultiMoney estructurado detectado."
    if _has_reject(text):
        return "ignored", "Correo promocional, login, seguridad o informativo."
    return "ignored", "No contiene estructura confiable de movimiento bancario."


def parse_financial_email(
    subject: str, sender: str, body: str, received_at: str | None = None,
    exchange_rate: float = 495.0, identity: ParserIdentity | None = None,
) -> dict[str, Any]:
    """Parse one bank email for the mailbox holder described by ``identity``.

    Without an identity the parse is neutral: no holder name, contacts or own
    accounts, and never the Owner's.
    """
    with use_identity(identity):
        return _flag_guesses(_parse_financial_email(subject, sender, body, received_at, exchange_rate))


def _flag_guesses(parsed: dict[str, Any]) -> dict[str, Any]:
    """Mark what the parse assumed instead of read, and keep it below auto-commit.

    - A foreign-currency movement without a rate printed in the mail needs the real rate.
    - An expense whose merchant matched no category rule has a guessed category.
    """
    if parsed.get("email_kind") != "movement":
        return parsed
    foreign = str(parsed.get("original_currency") or "").upper() not in ("", "CRC")
    if foreign and parsed.get("exchange_rate_source") != "email":
        parsed["needs_exchange_rate"] = True
        parsed["confidence"] = min(float(parsed.get("confidence") or 0), GUESS_CONFIDENCE_CAP)
    if parsed.get("transaction_type") == "expense" and parsed.get("category") == FALLBACK_EXPENSE_CATEGORY:
        parsed["needs_category"] = True
        parsed["category_source"] = "fallback"
        parsed["confidence"] = min(float(parsed.get("confidence") or 0), GUESS_CONFIDENCE_CAP)
    return parsed


def _parse_financial_email(subject: str, sender: str, body: str, received_at: str | None, exchange_rate: float) -> dict[str, Any]:
    text = "\n".join([sender or "", subject or "", body or ""])
    bank = detect_bank(sender, subject, body)

    if bank == "unknown":
        return _ignored(bank, subject, body, received_at, "No es un correo de BAC, Banco Popular o MultiMoney.")

    # A redemption receipt mentions the statement in its footer: it is a movement.
    if bank == "bac":
        redemption = _parse_bac_reward_redemption(subject, sender, body, received_at)
        if redemption:
            return redemption

    # Estados de cuenta tienen prioridad: son documentos, no movimientos.
    statement = _parse_statement(subject, sender, body, received_at)
    if statement:
        return statement

    # Plantillas exactas por banco. No buscar números genéricos fuera de estas plantillas.
    if bank == "bac":
        parsed = _parse_bac_purchase(subject, sender, body, received_at, exchange_rate) or _parse_bac_loan_disbursement(subject, sender, body, received_at)
        if parsed:
            return parsed
        parsed = _parse_bac_sinpe_movil(subject, sender, body, received_at) or _parse_bac_sinpe(subject, sender, body, received_at)
        if parsed:
            return parsed
        parsed = _parse_bac_cardless_withdrawal(subject, sender, body, received_at) or _parse_bac_alert_payment(subject, sender, body, received_at)
        if parsed:
            return parsed

    if bank == "multimoney":
        parsed = _parse_multimoney_disbursement(subject, sender, body, received_at) or _parse_multimoney_transfer(subject, sender, body, received_at)
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
