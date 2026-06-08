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
        "bac", "credomatic", "baccredomatic", "notificacionesbaccr",
        "notificacion@notificacionesbaccr.com", "notificaciones@baccredomatic.cr",
        "estadosdecuenta@baccredomatic.cr", "estadodecuenta@baccredomatic.cr",
        "bac - sinpe",
    ],
    "popular": [
        "banco popular", "bancopopular", "bancopopular.fi.cr",
        "notificaciones@bancopopular", "banco popular informa",
    ],
    "multimoney": [
        "multimoney", "multi money", "financiera multimoney", "multimoneycr",
        "financiera@multimoney.com",
    ],
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
    haystack = normalize(" ".join([sender or "", subject or "", (body or "")[:3500]]))
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
    # Compact fallback, only when value is in same line.
    pattern = re.compile(rf"(?im)^\s*{re.escape(label)}\s*[:\-]\s*(.+)$")
    match = pattern.search(clean_text(text))
    if match:
        return match.group(1).strip()[:260]
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
    if transaction_type == "transfer":
        if "inversion vista smart" in clean or "vista smart" in clean:
            return "Ahorro"
        if "terapia" in clean:
            return "Salud"
        if "papa" in clean or "papá" in clean:
            return "Familiar"
        return "Transferencias"

    rules = [
        ("Videojuegos", ["playstation", "ps plus", "supercell", "fs *supercell", "apple.com/bill", "gossip", "kingshot", "juego", "store.supercell"]),
        ("Restaurante", ["uber eats", "mcdonald", "arcos dorados", "kfc", "restaurante", "pizza", "burger"]),
        ("Comida", ["maxi pali", "maxipali", "pali", "am pm", "automercado", "auto mercado", "supermercado", "jose m.zeledon", "zeledon"]),
        ("Gasolina", ["gasolinera", "estacion de servicio", "combustible", "servicentro"]),
        ("Transporte", ["uber rides", "uber", "parqueo", "taxi"]),
        ("Salud", ["farmacia", "farmavalue", "hospital", "clinica", "clínica", "nutricionista", "terapia", "medico", "médico"]),
        ("Suscripciones", ["netflix", "crunchyroll", "google one", "icloud", "resume.io", "spotify", "liberty movil"]),
        ("Deporte", ["gym", "novo fit", "uno sport", "box"]),
        ("Ropa", ["shein", "zara", "pull&bear", "bershka"]),
        ("Compras", ["temu", "amazon", "tienda", "ecommerce", "ishop"]),
        ("Teléfono", ["liberty", "linea", "línea", "movil", "móvil"]),
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
    match = re.search(r"\*{4,}(\d{4})", text or "")
    return match.group(1) if match else None


def _base_result(bank: str, kind: str, received_at: str | None) -> dict[str, Any]:
    return {
        "bank": bank,
        "email_kind": kind,
        "statement_month": None,
        "ignore_reason": None,
        "transaction_date": parse_date(received_at or "", received_at),
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
        "confidence": 0.0,
        "confidence_reason": "",
    }


def _parse_bac_purchase(subject: str, sender: str, body: str, received_at: str | None, exchange_rate: float) -> dict[str, Any] | None:
    text = clean_text("\n".join([subject or "", body or ""]))
    clean = normalize(text)
    if not ("notificacion de transaccion" in clean and "comercio" in clean and "tipo de transaccion" in clean and "monto" in clean):
        return None

    merchant = _label_value(text, "Comercio")
    amount_raw = _label_value(text, "Monto")
    date_raw = _label_value(text, "Fecha")
    tipo_raw = _label_value(text, "Tipo de Transacción") or "COMPRA"
    if not merchant or not amount_raw or not date_raw:
        return None

    amount, currency = _parse_labeled_amount_value(amount_raw)
    if amount is None:
        return None
    transaction_date, time_value = _parse_datetime_text(date_raw, received_at)
    card_last4 = _card_last4(text)
    holder = _card_holder_from_greeting(text)
    tipo_clean = normalize(tipo_raw)
    if any(word in tipo_clean for word in ["devolucion", "reversion", "reverso", "credito"]):
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
    if time_value:
        notes.append(f"hora: {time_value}")
    if currency == "USD":
        notes.append(f"monto original USD {amount:.2f}; TC {exchange_rate}")

    return {
        **_base_result("bac", "movement", received_at),
        "transaction_date": transaction_date,
        "description": merchant[:240],
        "amount": amount_crc,
        "transaction_type": transaction_type,
        "category": category,
        "account": f"BAC ****{card_last4}" if card_last4 else "BAC Tarjeta",
        "notes": " | ".join(notes),
        "original_amount": amount if currency == "USD" else None,
        "original_currency": "USD" if currency == "USD" else None,
        "exchange_rate": exchange_rate if currency == "USD" else None,
        "confidence": 0.99,
        "confidence_reason": "BAC compra: comercio, fecha, tipo, tarjeta y monto extraídos por plantilla exacta.",
    }


def _parse_bac_sinpe(subject: str, sender: str, body: str, received_at: str | None) -> dict[str, Any] | None:
    text = clean_text("\n".join([subject or "", body or ""]))
    clean = normalize(text)
    if not ("sinpe" in clean and "transferencia" in clean and "monto" in clean):
        return None
    amount, _currency = _parse_context_amount(text)
    if amount is None:
        return None
    date_match = re.search(r"d[ií]a\s+y\s+hora\s*:??\s*([^\.\n]+)", text, re.I)
    transaction_date, time_value = _parse_datetime_text(date_match.group(1) if date_match else text, received_at)
    is_out = "debitando su cuenta" in clean
    is_in = "se acredito" in clean or "se acredito en la cuenta" in clean or "se acreditó" in (body or "").lower()
    concept_match = re.search(r"por\s+concepto\s+de\s+(.+?)(?:\.?D[ií]a\s+y\s+hora|\n|$)", text, re.I | re.S)
    concept = re.sub(r"[_\s]+", " ", concept_match.group(1)).strip(" .") if concept_match else ""
    reference_match = re.search(r"referencia\s+(\d{8,})", text, re.I)
    iban_match = re.search(r"IBAN\s+([A-Z]{2}\d{4}[A-Z0-9X*]+)", text, re.I)
    description = concept or ("SINPE enviado" if is_out else "SINPE recibido" if is_in else "Transferencia SINPE")
    notes = ["BAC SINPE por plantilla", "salida" if is_out else "entrada" if is_in else "dirección por revisar"]
    if reference_match:
        notes.append(f"referencia {reference_match.group(1)}")
    if iban_match:
        notes.append(f"IBAN {iban_match.group(1)}")
    if time_value:
        notes.append(f"hora: {time_value}")
    return {
        **_base_result("bac", "movement", received_at),
        "transaction_date": transaction_date,
        "description": description[:240],
        "amount": round(amount, 2),
        "transaction_type": "transfer",
        "category": infer_category(description, "transfer"),
        "account": "BAC SINPE",
        "notes": " | ".join(notes),
        "confidence": 0.98,
        "confidence_reason": "BAC SINPE: dirección, monto, referencia y fecha extraídos por plantilla exacta.",
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
    if not ("multimoney" in clean and "resumen de operacion" in clean and "monto" in clean and "fecha" in clean):
        return None
    concept = _label_value(text, "Concepto") or "Movimiento MultiMoney"
    amount, currency = _parse_labeled_amount_value(_label_value(text, "Monto"))
    if amount is None:
        amount, currency = _parse_context_amount(text)
    if amount is None:
        return None
    date_raw = _label_value(text, "Fecha") or text
    transaction_date, time_value = _parse_datetime_text(date_raw, received_at)
    origin = _extract_multimoney_account_block(text, "Cuenta origen")
    destination = _extract_multimoney_account_block(text, "Cuenta destino")
    reference = _label_value(text, "Referencia") or ""
    notes = ["MultiMoney transferencia por plantilla"]
    if origin:
        notes.append(f"origen: {origin}")
    if destination:
        notes.append(f"destino: {destination}")
    if reference:
        notes.append(f"referencia: {reference}")
    if time_value:
        notes.append(f"hora: {time_value}")
    return {
        **_base_result("multimoney", "movement", received_at),
        "transaction_date": transaction_date,
        "description": concept[:240],
        "amount": round(amount, 2),
        "transaction_type": "transfer",
        "category": infer_category(concept, "transfer"),
        "account": "MultiMoney",
        "notes": " | ".join(notes),
        "original_amount": amount if currency == "USD" else None,
        "original_currency": "USD" if currency == "USD" else None,
        "confidence": 0.97,
        "confidence_reason": "MultiMoney: concepto, monto, fecha y cuentas extraídos por plantilla exacta.",
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
    if bank == "bac" and (_parse_bac_purchase(subject, sender, body, None, 495.0) or _parse_bac_sinpe(subject, sender, body, None)):
        return "movement", "Movimiento BAC estructurado detectado."
    if bank == "multimoney" and _parse_multimoney_transfer(subject, sender, body, None):
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

    if bank == "multimoney":
        parsed = _parse_multimoney_transfer(subject, sender, body, received_at)
        if parsed:
            return parsed

    if _has_reject(text):
        return _ignored(bank, subject, body, received_at, "Correo promocional/login/seguridad/informativo; no es movimiento de dinero.")

    # Banco Popular se acepta solo como estado de cuenta hasta tener ejemplos reales de movimientos.
    return _ignored(bank, subject, body, received_at, "Correo bancario sin plantilla confiable. No se genera candidato.")
