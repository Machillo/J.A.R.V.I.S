"""Deterministic readers of bank SMS sent by the iOS Shortcuts "Mensaje" automation.

SINPE Móvil in Costa Rica notifies only by SMS. Each supported format is one small function
written from real, anonymized samples and pinned by tests with synthetic data in that exact
shape. No generative AI reads an SMS, and no format is ever guessed: a message no parser
recognizes is discarded (only an aggregate "not recognized" count per bank is kept).

SMS formats live here, separate to the mail parsers (email_monitor/parser.py): the two never
share a parser. Amounts are read with Decimal, never float.

Formats are recognized by their text, never by the sender number (a bank may send from several
numbers, and the Shortcuts automation filters by text). Supported (from real, anonymized samples):
- SINPE Móvil received, BAC (2026-10-29): "Ha recibido 36,455.00 Colones de NOMBRE por SINPE
  Movil, DESCRIPCION. Referencia NNN." The bank writes spaces in names as "_" or "§". The same
  SMS may arrive twice from two numbers: the reference makes them one movement (semantic dedupe).
Pending real samples: SINPE Móvil sent, card purchases, other currencies, other banks.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Callable

MAX_TEXT = 1000
# Movement kinds a bank SMS may describe, and what each one is for the user.
KINDS = {
    "sinpe_in": ("income", "transfer", "in"),       # SINPE Móvil received: income
    "sinpe_out": ("expense", "transfer", "out"),    # SINPE Móvil sent: spending
    "card_purchase": ("expense", "card_purchase", "out"),
}
# Banks named in the aggregate "not recognized" counter (never the text). Detection only looks
# for the institution's own name; anything else is "unknown".
BANK_NAMES = {
    "bac": ("bac", "credomatic"),
    "bcr": ("bcr", "banco de costa rica"),
    "bn": ("banco nacional", "bncr"),
    "popular": ("banco popular",),
    "promerica": ("promerica",),
    "davivienda": ("davivienda",),
    "lafise": ("lafise",),
    "mucap": ("mucap",),
    "multimoney": ("multimoney",),
}


@dataclass(frozen=True)
class SmsMovement:
    bank: str
    kind: str  # a key of KINDS
    amount: Decimal
    currency: str  # CRC or USD
    description: str  # merchant or counterparty as the bank wrote it
    reference: str | None = None
    card_last4: str | None = None


Parser = Callable[[str], "SmsMovement | None"]

_SINPE_RECEIVED = re.compile(
    r"^Ha recibido (?P<amount>[\d,]+\.\d{2}) Colones de (?P<name>.+?) por SINPE Movil, "
    r"(?P<detail>.*?)\. Referencia (?P<reference>\d{6,30})\.?$",
    re.DOTALL,
)
_NO_DETAIL = {"sin descripcion", "sin descripción", ""}


def _person(raw: str) -> str:
    """The sender's name as printed (the bank writes spaces as "_" or "§"), with single spaces."""
    return re.sub(r"\s+", " ", re.sub(r"[_§]+", " ", raw)).strip()


def sinpe_received_bac(text: str) -> "SmsMovement | None":
    """BAC SINPE Móvil received, in colones (format of real samples, 2026-10-29)."""
    match = _SINPE_RECEIVED.match(re.sub(r"\s+", " ", text).strip())
    if not match:
        return None
    amount = amount_from(match.group("amount"), decimal_separator=".")
    name = _person(match.group("name"))
    if amount is None or not name:
        return None
    detail = re.sub(r"\s+", " ", match.group("detail")).strip()
    description = f"SINPE de {name}" + (f" · {detail}" if plain(detail) not in _NO_DETAIL else "")
    return SmsMovement(bank="bac", kind="sinpe_in", amount=amount, currency="CRC",
                       description=description[:200], reference=match.group("reference"))


# Real bank formats only (see module docstring); fixed order. Tests may register synthetic ones.
PARSERS: list[Parser] = [sinpe_received_bac]


def plain(text: str) -> str:
    """Lowercase without accents and with single spaces (for matching, never stored)."""
    folded = unicodedata.normalize("NFKD", text)
    folded = "".join(char for char in folded if not unicodedata.combining(char)).lower()
    return re.sub(r"\s+", " ", folded).strip()


def valid_text(text: object) -> str | None:
    """The SMS text if it is plausible: 1..MAX_TEXT characters, no control or binary characters."""
    if not isinstance(text, str):
        return None
    clean = text.strip()
    if not clean or len(clean) > MAX_TEXT:
        return None
    if any(unicodedata.category(char) in {"Cc", "Cs", "Co", "Cn"} and char not in "\n\r\t" for char in clean):
        return None
    return clean


def amount_from(raw: str, *, decimal_separator: str) -> Decimal | None:
    """A bank-printed amount ("12.500,00" with ',' or "12,500.00" with '.') as Decimal > 0."""
    grouping = "." if decimal_separator == "," else ","
    normalized = raw.strip().replace(grouping, "").replace(decimal_separator, ".")
    if not re.fullmatch(r"\d{1,10}(\.\d{1,2})?", normalized):
        return None
    try:
        value = Decimal(normalized)
    except InvalidOperation:
        return None
    return value if value > 0 else None


def detect_bank(text: str) -> str:
    folded = plain(text)
    for bank, names in BANK_NAMES.items():
        if any(re.search(rf"(?<![a-z]){re.escape(name)}(?![a-z])", folded) for name in names):
            return bank
    return "unknown"


def parse(text: str, parsers: list[Parser] | None = None) -> SmsMovement | None:
    """The movement the first matching parser reads, or None. Deterministic: parser order is fixed."""
    for parser in PARSERS if parsers is None else parsers:
        movement = parser(text)
        if movement is not None and movement.kind in KINDS and movement.amount > 0 and movement.currency in {"CRC", "USD"}:
            return movement
    return None
