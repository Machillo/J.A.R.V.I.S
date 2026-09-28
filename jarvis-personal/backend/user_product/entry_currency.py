"""Currency of manual income and expense entries.

`amount` is always stored in the account's base currency, so every total,
budget, report and strategy keeps adding one currency. An entry typed in the
other supported currency also keeps what the user typed and the exchange rate
the user entered. DINCR never invents or looks up a rate.

The rate is always expressed as CRC per 1 USD, whichever currency is the base.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException

SUPPORTED_CURRENCIES = ("CRC", "USD")
CENT = Decimal("0.01")
RATE_STEP = Decimal("0.000001")  # 6 decimals
# Limits of the columns written (salaries and expenses). original_amount NUMERIC(14,2) and
# exchange_rate NUMERIC(14,6) are 20260928110000's, verified in production. The type of
# `amount` itself is not verified (schema.sql says NUMERIC(14,2), and schema.sql proved
# wrong for transactions.amount, NUMERIC(12,2) in production), so the stricter one is used:
# a value is refused here, never discovered by PostgreSQL as SQLSTATE 22003 (a 500).
MAX_AMOUNT = Decimal("9999999999.99")  # amount, NUMERIC(12,2) at most
MAX_ORIGINAL = Decimal("999999999999.99")  # original_amount NUMERIC(14,2)
MAX_RATE = Decimal("99999999.999999")  # exchange_rate NUMERIC(14,6)
RATE_MESSAGE = "Indicá el tipo de cambio (colones por 1 dólar) para registrar un monto en otra moneda."


def _finite(value: Any) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number if number.is_finite() else None


def _within(value: Decimal, limit: Decimal) -> Decimal | None:
    """`value` rounded to cents if it fits `limit`; far beyond it, refused before rounding."""
    if value >= limit * 10:
        return None
    rounded = value.quantize(CENT, ROUND_HALF_UP)
    return rounded if rounded <= limit else None


def account_base_currency(conn, account_id: str) -> str:
    row = conn.execute("SELECT base_currency FROM accounts WHERE id=%s", (account_id,)).fetchone()
    return str((row or {}).get("base_currency") or "CRC").upper()


def entry_currencies(base_currency: str | None) -> list[str]:
    """Currencies this backend converts for an account, published with its identity.

    A client offers another currency only when its backend declares it here: an
    older backend ignores `currency`/`exchange_rate` and would store the typed
    figure as if it were in the base currency.
    """
    base = str(base_currency or "CRC").upper()
    return list(SUPPORTED_CURRENCIES) if base in SUPPORTED_CURRENCIES else [base]


def resolve_entry_amount(base_currency: str | None, amount: float, currency: str | None, exchange_rate: float | None) -> dict[str, Any]:
    """Return the stored columns for an amount typed in `currency`.

    No currency, or the base currency, stores the amount as typed. The other
    supported currency needs the user's rate. Accounts whose legacy base
    currency is not CRC or USD can only record entries in their base currency.
    """
    raw = _finite(amount)
    if raw is None:
        raise HTTPException(status_code=422, detail="El monto no es válido.")
    base = str(base_currency or "CRC").upper()
    code = str(currency).upper() if currency else base
    # In the base currency the typed figure is `amount`; otherwise it is `original_amount`.
    typed = _within(raw, MAX_AMOUNT if code == base else MAX_ORIGINAL)
    if typed is None:
        raise HTTPException(status_code=422, detail="El monto es demasiado grande.")
    if code == base:
        return {"amount": typed, "original_amount": None, "original_currency": None, "exchange_rate": None}
    if base not in SUPPORTED_CURRENCIES or code not in SUPPORTED_CURRENCIES:
        raise HTTPException(status_code=422, detail=f"Tu moneda principal es {base}: registrá el monto en {base}.")
    # Parsed, finite, rounded to its stored 6 decimals, then still positive and within its column.
    rate = None if exchange_rate is None else _finite(exchange_rate)
    if rate is not None and rate >= MAX_RATE * 10:
        raise HTTPException(status_code=422, detail="El tipo de cambio es demasiado grande.")
    rate = None if rate is None else rate.quantize(RATE_STEP, ROUND_HALF_UP)
    if rate is None or rate <= 0:  # below 0.0000005 it rounds to zero as stored
        raise HTTPException(status_code=422, detail=RATE_MESSAGE)
    if rate > MAX_RATE:
        raise HTTPException(status_code=422, detail="El tipo de cambio es demasiado grande.")
    # Computed with the rate exactly as it is stored.
    converted = typed * rate if code == "USD" else typed / rate
    converted = converted.quantize(CENT, ROUND_HALF_UP)
    if converted <= 0:
        raise HTTPException(status_code=422, detail="El monto convertido es demasiado pequeño para registrarse.")
    if converted > MAX_AMOUNT:
        raise HTTPException(status_code=422, detail="El monto convertido es demasiado grande.")
    return {"amount": converted, "original_amount": typed, "original_currency": code, "exchange_rate": rate}
