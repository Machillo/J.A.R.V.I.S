"""Currency of manual income and expense entries.

`amount` is always stored in the account's base currency, so every total,
budget, report and strategy keeps adding one currency. An entry typed in the
other supported currency also keeps what the user typed and the exchange rate
the user entered. DINCR never invents or looks up a rate.

The rate is always expressed as CRC per 1 USD, whichever currency is the base.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import HTTPException

SUPPORTED_CURRENCIES = ("CRC", "USD")
CENT = Decimal("0.01")


def account_base_currency(conn, account_id: str) -> str:
    row = conn.execute("SELECT base_currency FROM accounts WHERE id=%s", (account_id,)).fetchone()
    return str((row or {}).get("base_currency") or "CRC").upper()


def resolve_entry_amount(base_currency: str | None, amount: float, currency: str | None, exchange_rate: float | None) -> dict[str, Any]:
    """Return the stored columns for an amount typed in `currency`.

    No currency, or the base currency, stores the amount as typed. The other
    supported currency needs the user's rate. Accounts whose legacy base
    currency is not CRC or USD can only record entries in their base currency.
    """
    typed = Decimal(str(amount)).quantize(CENT, ROUND_HALF_UP)
    if not currency:
        return {"amount": typed, "original_amount": None, "original_currency": None, "exchange_rate": None}
    base = str(base_currency or "CRC").upper()
    code = str(currency).upper()
    if code == base:
        return {"amount": typed, "original_amount": None, "original_currency": None, "exchange_rate": None}
    if base not in SUPPORTED_CURRENCIES or code not in SUPPORTED_CURRENCIES:
        raise HTTPException(status_code=422, detail=f"Tu moneda principal es {base}: registrá el monto en {base}.")
    if exchange_rate is None or exchange_rate <= 0:
        raise HTTPException(status_code=422, detail="Indicá el tipo de cambio (colones por 1 dólar) para registrar un monto en otra moneda.")
    rate = Decimal(str(exchange_rate))
    converted = typed * rate if code == "USD" else typed / rate
    converted = converted.quantize(CENT, ROUND_HALF_UP)
    if converted <= 0:
        raise HTTPException(status_code=422, detail="El monto convertido es demasiado pequeño para registrarse.")
    return {"amount": converted, "original_amount": typed, "original_currency": code, "exchange_rate": rate}
