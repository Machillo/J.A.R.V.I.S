from __future__ import annotations

import re
import unicodedata


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value or "")
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _clean_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _norm_key(value: str) -> str:
    value = _strip_accents(value or "").upper()
    value = value.replace("&AMP;", "&")
    value = re.sub(r"[\u200b\u200c\ufeff\xa0]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


# Exact/contains aliases for stable merchants. Add new rules here first before
# writing broad regexes; this keeps the normalizer deterministic and auditable.
MERCHANT_ALIASES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bAPPLE\s*\.\s*COM\s*[\\/ ]?\s*BILL\b|\bAPPLE\s*\.\s*COM\s*/\s*BILL\b", re.I), "APPLE"),
    (re.compile(r"\bOPENAI\b|\bOPENAI\s*\*\s*CHATGPT\b|\bCHATGPT\b", re.I), "OPENAI"),
    (re.compile(r"\bCRUNCHYROLL\b|\bGOOGLE\s*\*\s*CRUNCHYROLL\b", re.I), "CRUNCHYROLL"),
    (re.compile(r"\bSUPERCELL\b|\bFS\s*\*\s*SUPERCELL\b|\bSTORE\s*\.\s*SUPERCELL\b", re.I), "SUPERCELL"),
    (re.compile(r"\bUBER\s*\*?\s*(TRIP|RIDES)?\b|\bUBER\s+RIDES\b", re.I), "UBER"),
    (re.compile(r"\bAM\s*PM\b|\bAMPM\b", re.I), "AM PM"),
    (re.compile(r"\bTACO\s+BELL\b", re.I), "TACO BELL"),
    (re.compile(r"\bSHEIN\b", re.I), "SHEIN"),
    (re.compile(r"\bTEMU\b", re.I), "TEMU"),
]

# Ordered transformers. These remove payment-processor noise but keep the real
# merchant when there is no exact alias.
PREFIX_TRANSFORMERS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^(?:PF|PP|POS|PAG|COMPRA|PAYPAL|SQ|TST|SP)\s*[\*\-:\.]\s*", re.I), ""),
    (re.compile(r"^(?:GOOGLE|APPLE|FACEBK|META)\s*[\*\-:\.]\s*", re.I), ""),
]

GENERIC_SUFFIXES: list[re.Pattern[str]] = [
    re.compile(r"\b(CR|CRI|CRC|COL|COSTA\s+RICA|SAN\s+JOSE|ALAJUELA|HEREDIA|CARTAGO)\b$", re.I),
    re.compile(r"\b(S\.A\.|SA|SRL|LTDA|SOCIEDAD\s+ANONIMA)\b$", re.I),
]

GENERIC_DESCRIPTIONS = {
    "MOVIMIENTO MULTIMONEY",
    "DEBITO APLICADO POR OTRA ENTIDAD FINANCIERA",
    "DÉBITO APLICADO POR OTRA ENTIDAD FINANCIERA",
    "INVERSION VISTA SMART COL",
    "INVERSIÓN VISTA SMART COL",
}


def normalizeDescription(rawDescription: str) -> str:
    """Normalize noisy bank merchant descriptions into a stable merchant label.

    Safe default: if no rule matches, return an uppercase, whitespace-normalized
    version of the original text instead of guessing or returning NULL.
    """
    raw = _clean_spaces(rawDescription or "")
    if not raw:
        return "SIN DESCRIPCION"

    value = _norm_key(raw)
    value = value.replace("/", " / ")
    value = re.sub(r"\s+", " ", value).strip()

    for pattern, canonical in MERCHANT_ALIASES:
        if pattern.search(value):
            return canonical

    for pattern, replacement in PREFIX_TRANSFORMERS:
        value = pattern.sub(replacement, value).strip()

    # Real case: PF*JYCOB S BARBER SHOP -> BARBER SHOP. Keep this as a semantic
    # rule because the proper noun changes, but the useful spend label is stable.
    if re.search(r"\bBARBER\s+SHOP\b", value, re.I):
        return "BARBER SHOP"

    # Remove authorization/reference fragments and location/legal suffixes.
    value = re.sub(r"\b(AUT|AUTH|REF|REFERENCIA|AUTORIZACION|AUTORIZACIÓN)\s*#?\s*\d+\b", " ", value, flags=re.I)
    value = re.sub(r"\b\d{5,}\b", " ", value)
    value = re.sub(r"[\*_]+", " ", value)
    value = re.sub(r"[^A-Z0-9ÁÉÍÓÚÑ& .\-]", " ", value)
    value = _clean_spaces(value)

    changed = True
    while changed and value:
        changed = False
        for pattern in GENERIC_SUFFIXES:
            new_value = _clean_spaces(pattern.sub("", value))
            if new_value != value:
                value = new_value
                changed = True

    return value or "SIN DESCRIPCION"


def normalize_description(raw_description: str) -> str:
    """Pythonic alias used internally by the email monitor."""
    return normalizeDescription(raw_description)


def is_generic_mirror_description(description: str) -> bool:
    clean = _norm_key(description)
    return clean in {_norm_key(item) for item in GENERIC_DESCRIPTIONS} or any(
        token in clean
        for token in [
            "INVERSION VISTA SMART",
            "DEBITO APLICADO POR OTRA ENTIDAD",
            "MOVIMIENTO MULTIMONEY",
        ]
    )
