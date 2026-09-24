"""Remove personal data from a bank email sample while keeping its layout."""
from __future__ import annotations

import re

EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")
URL_RE = re.compile(r"https?://\S+", re.I)
# Text right after these labels is a person's name ("Hola MARIA PEREZ:", "a nombre de ...").
NAME_LABEL_RE = re.compile(
    r"(?P<label>\b(?:hola|estimad[oa]s?|se[ñn]or(?:a)?|titular|cliente|a\s+nombre\s+de|nombre|beneficiario|ordenante)\b\s*[:,]?\s*)"
    r"(?P<name>[A-ZÁÉÍÓÚÑa-záéíóúñ][A-ZÁÉÍÓÚÑa-záéíóúñ.'\- ]{1,80}?)(?=\s*(?:[:,.\n]|$|\b(?:realiz|le\s+inform|por\s+medio)))",
    re.I,
)


def _mask_digits(match: re.Match) -> str:
    return re.sub(r"\d", "9", match.group(0))


def sanitize_sample(text: str) -> str:
    """Emails, URLs and names are replaced; every digit becomes 9.

    Digit masking keeps the *shape* of amounts, dates, cards and references
    ("₡15.000,00" -> "₡99.999,99", "22/09/2026" -> "99/99/9999"), which is what
    a parser needs, without any real value.
    """
    clean = URL_RE.sub("<url>", text or "")
    clean = EMAIL_RE.sub("<email>", clean)
    clean = NAME_LABEL_RE.sub(lambda m: f"{m.group('label')}<nombre>", clean)
    clean = re.sub(r"\d+", _mask_digits, clean)
    return clean


def residual_risks(text: str) -> list[str]:
    """Cheap checks a human must clear before a sanitized sample may be sent."""
    risks = []
    if re.search(r"[0-8]", text):
        risks.append("unmasked digits")
    if EMAIL_RE.search(text):
        risks.append("email address")
    if re.search(r"\b[A-ZÁÉÍÓÚÑ]{3,}\s+[A-ZÁÉÍÓÚÑ]{3,}\s+[A-ZÁÉÍÓÚÑ]{3,}\b", text):
        risks.append("possible full name in capitals (review manually)")
    return risks
