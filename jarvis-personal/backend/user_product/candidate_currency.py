"""Currency of a mail or statement candidate when it becomes a transaction.

Parsers keep a USD movement's real amount in original_amount/original_currency,
but the `amount` they store next to it was converted with a default rate
(or, for some senders, not converted at all while labelled CRC). That number is
kept on the candidate only for cross-source matching and is never trusted as
money: a candidate is worth its native amount, in the currency it happened in.

Accepting it into an account whose base currency differs needs the exchange
rate the user enters (always CRC per 1 USD). DINCR never invents one. The
transaction then stores the base amount plus what happened (original_amount,
original_currency, exchange_rate), like manual entries.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import HTTPException

SUPPORTED_CURRENCIES = ("CRC", "USD")
CENT = Decimal("0.01")


def native_money(candidate: dict[str, Any]) -> tuple[str, Decimal]:
    """(currency, amount) the movement really happened in."""
    currency = str(candidate.get("currency") or "CRC").upper()
    original = str(candidate.get("original_currency") or "").upper()
    if original and original != currency and candidate.get("original_amount") is not None:
        return original, Decimal(str(candidate["original_amount"])).quantize(CENT, ROUND_HALF_UP)
    return currency, Decimal(str(candidate.get("amount") or 0)).quantize(CENT, ROUND_HALF_UP)


def transaction_amounts(currency: str, amount: Any, base_currency: str | None, exchange_rate: float | None) -> dict[str, Any]:
    """Columns for a transaction of `amount` in `currency` on a `base_currency` account."""
    code, base = str(currency).upper(), str(base_currency or "CRC").upper()
    typed = Decimal(str(amount)).quantize(CENT, ROUND_HALF_UP)
    if code == base:
        return {"amount": typed, "original_amount": None, "original_currency": None, "exchange_rate": None}
    if code not in SUPPORTED_CURRENCIES or base not in SUPPORTED_CURRENCIES:
        raise HTTPException(status_code=422, detail=f"Este movimiento está en {code} y tu moneda principal es {base}: DINCR no puede convertirlo.")
    if exchange_rate is None or exchange_rate <= 0:
        raise HTTPException(
            status_code=422,
            detail=f"Este movimiento está en {code}. Tocá Corregir e indicá el tipo de cambio (colones por 1 dólar) para guardarlo.",
        )
    rate = Decimal(str(exchange_rate))
    converted = (typed * rate if code == "USD" else typed / rate).quantize(CENT, ROUND_HALF_UP)
    if converted <= 0:
        raise HTTPException(status_code=422, detail="El monto convertido es demasiado pequeño para registrarse.")
    return {"amount": converted, "original_amount": typed, "original_currency": code, "exchange_rate": rate}
