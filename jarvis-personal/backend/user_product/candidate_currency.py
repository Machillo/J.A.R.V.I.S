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

The conversion contract (rate precision, rounding, limits, errors) is the same
as manual entries'; test_currency_conversion_contract.py pins it with shared
golden vectors so the two can never drift apart silently.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException

SUPPORTED_CURRENCIES = ("CRC", "USD")
CENT = Decimal("0.01")
# The production columns this writes (verified read-only, gate Q0 of 2026-09-28):
# transactions.amount and .original_amount NUMERIC(12, 2), .exchange_rate NUMERIC(12, 6).
# Anything outside them is refused here, never discovered by PostgreSQL (SQLSTATE 22003).
RATE_STEP = Decimal("0.000001")  # 6 decimals
MAX_AMOUNT = Decimal("9999999999.99")  # NUMERIC(12, 2)
MAX_RATE = Decimal("999999.999999")  # NUMERIC(12, 6)
# Below these, quantizing can never fail and the value may still round into range.
_AMOUNT_CEILING, _RATE_CEILING = MAX_AMOUNT * 10, MAX_RATE * 10


def _finite(value: Any) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number if number.is_finite() else None


def native_money(candidate: dict[str, Any]) -> tuple[str, Decimal]:
    """(currency, amount) the movement really happened in."""
    currency = str(candidate.get("currency") or "CRC").upper()
    original = str(candidate.get("original_currency") or "").upper()
    if original and original != currency and candidate.get("original_amount") is not None:
        return original, Decimal(str(candidate["original_amount"])).quantize(CENT, ROUND_HALF_UP)
    return currency, Decimal(str(candidate["amount"])).quantize(CENT, ROUND_HALF_UP)  # NOT NULL column


def transaction_amounts(currency: str, amount: Any, base_currency: str | None, exchange_rate: float | None) -> dict[str, Any]:
    """Columns for a transaction of `amount` in `currency` on a `base_currency` account."""
    code, base = str(currency).upper(), str(base_currency or "CRC").upper()
    typed = _finite(amount)
    if typed is None:
        raise HTTPException(status_code=422, detail="El monto no es válido.")
    if typed >= _AMOUNT_CEILING or typed.quantize(CENT, ROUND_HALF_UP) > MAX_AMOUNT:
        raise HTTPException(status_code=422, detail="El monto es demasiado grande.")
    typed = typed.quantize(CENT, ROUND_HALF_UP)
    if code == base:
        return {"amount": typed, "original_amount": None, "original_currency": None, "exchange_rate": None}
    if code not in SUPPORTED_CURRENCIES or base not in SUPPORTED_CURRENCIES:
        raise HTTPException(status_code=422, detail=f"Este movimiento está en {code} y tu moneda principal es {base}: DINCR no puede convertirlo.")
    # Computed with the rate exactly as the transaction stores it.
    rate = None if exchange_rate is None else _finite(exchange_rate)
    if rate is not None and rate >= _RATE_CEILING:
        raise HTTPException(status_code=422, detail="El tipo de cambio es demasiado grande.")
    rate = None if rate is None else rate.quantize(RATE_STEP, ROUND_HALF_UP)
    # After quantizing: a rate that rounds to 0 at 6 decimals is no rate at all.
    if rate is None or rate <= 0:
        raise HTTPException(
            status_code=422,
            detail=f"Este movimiento está en {code}. Tocá Corregir e indicá el tipo de cambio (colones por 1 dólar) para guardarlo.",
        )
    if rate > MAX_RATE:
        raise HTTPException(status_code=422, detail="El tipo de cambio es demasiado grande.")
    converted = (typed * rate if code == "USD" else typed / rate).quantize(CENT, ROUND_HALF_UP)
    if converted <= 0:
        raise HTTPException(status_code=422, detail="El monto convertido es demasiado pequeño para registrarse.")
    if converted > MAX_AMOUNT:
        raise HTTPException(status_code=422, detail="El monto convertido es demasiado grande.")
    return {"amount": converted, "original_amount": typed, "original_currency": code, "exchange_rate": rate}
