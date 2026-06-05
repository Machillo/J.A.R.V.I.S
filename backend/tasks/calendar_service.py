from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Optional

from backend.core.events import add_event, get_events

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


def _parse_time(text: str) -> str:
    match = re.search(r"(?:a las|alas|@)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text, re.I)
    if not match:
        return "09:00"
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridian = (match.group(3) or "").lower()
    if meridian == "pm" and hour < 12:
        hour += 12
    if meridian == "am" and hour == 12:
        hour = 0
    return f"{hour:02d}:{minute:02d}"


def extract_event_date(text: str) -> Optional[str]:
    text_l = text.lower()
    today = date.today()

    if "pasado mañana" in text_l:
        event_day = today + timedelta(days=2)
        return f"{event_day.isoformat()} {_parse_time(text)}"
    if "mañana" in text_l:
        event_day = today + timedelta(days=1)
        return f"{event_day.isoformat()} {_parse_time(text)}"
    if "hoy" in text_l:
        return f"{today.isoformat()} {_parse_time(text)}"

    iso = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", text_l)
    if iso:
        y, m, d = map(int, iso.groups())
        return f"{date(y, m, d).isoformat()} {_parse_time(text)}"

    numeric = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](20\d{2}))?\b", text_l)
    if numeric:
        d, m, y = numeric.groups()
        y = int(y or today.year)
        event_day = date(y, int(m), int(d))
        if event_day < today and not numeric.group(3):
            event_day = date(today.year + 1, int(m), int(d))
        return f"{event_day.isoformat()} {_parse_time(text)}"

    month_names = "|".join(MONTHS.keys())
    named = re.search(rf"(?:el\s*)?(\d{{1,2}})\s+de\s+({month_names})(?:\s+del?\s+(20\d{{2}}))?", text_l)
    if named:
        d = int(named.group(1))
        m = MONTHS[named.group(2)]
        y = int(named.group(3) or today.year)
        event_day = date(y, m, d)
        if event_day < today and not named.group(3):
            event_day = date(today.year + 1, m, d)
        return f"{event_day.isoformat()} {_parse_time(text)}"

    return None


def extract_title(text: str) -> str:
    cleaned = re.sub(r"^\s*jarvis[,\s]*", "", text, flags=re.I)
    cleaned = re.sub(r"\b(recordame|recu[eé]rdame|agenda|agend[aá]|tengo|crear|crea|guardar|guarda|compromiso|evento|cita)\b", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\b(el\s*)?\d{1,2}\s+de\s+\w+(\s+del?\s+20\d{2})?\b", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\b\d{1,2}[/-]\d{1,2}([/-]20\d{2})?\b", "", cleaned)
    cleaned = re.sub(r"\ba las\s*\d{1,2}(:\d{2})?\s*(am|pm)?\b", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")
    return cleaned[:120] or "Compromiso"


def create_calendar_event_from_text(text: str) -> dict:
    event_date = extract_event_date(text)
    if not event_date:
        return {
            "status": "NEEDS_DATE",
            "message": "Señor, ¿para qué fecha y hora desea guardar ese compromiso?",
            "pending": False,
        }

    title = extract_title(text)
    event = add_event(
        title=title,
        event_date=event_date,
        event_type="personal",
        description=text,
    )
    return {
        "status": "OK",
        "message": f"Señor, listo. Guardé en calendario: {title} · {event_date}.",
        "event": event,
        "pending": False,
    }


def calendar_summary() -> dict:
    events = get_events()
    return {
        "status": "OK",
        "events": events[:10],
        "message": "Señor, estos son sus próximos compromisos." if events else "Señor, no tiene compromisos registrados todavía.",
    }
