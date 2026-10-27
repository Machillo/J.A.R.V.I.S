"""Manual expenses waiting for their conversion (migration 20261027120000).

The user keeps an expense typed in the other currency (dollars, for a colones account) in that
currency until the close: the card's statement cut, or the calendar month without a card. One rate
then converts it (a later change). Until then the expense is "pending": `original_amount` and
`original_currency` hold what the user typed, `amount` (base currency) and `exchange_rate` are NULL.

Unknown is not zero. A pending expense never counts as 0 colones and DINCR never invents a rate:
every base-currency read leaves pending expenses out (`KNOWN_AMOUNT`), and this module reads them
apart, with their totals per currency, so colones and dollars accumulate side by side.

A request asks for it explicitly (`convert_at_close`): an expense in the other currency sent without
a rate and without the flag is still refused, as before. Until the migration is applied the state
cannot exist: the listing says "unavailable" and only a request that asks for it answers 503.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import HTTPException

from backend.auth.current_user import get_current_workspace_id
from backend.core.database import get_connection
from backend.core.i18n import tx
from backend.user_product import expense_account
from backend.user_product.entry_currency import MAX_ORIGINAL, SUPPORTED_CURRENCIES, _finite, _within

FIELD = "convert_at_close"
CONSTRAINT = "expenses_amount_known_or_pending_check"
# Base-currency reads of `expenses` keep only the rows whose amount is known.
KNOWN_AMOUNT = "amount IS NOT NULL"


def pending_available(conn) -> bool:
    row = conn.execute(
        "SELECT 1 AS present FROM pg_catalog.pg_constraint WHERE conname = %s AND conrelid = to_regclass('public.expenses')",
        (CONSTRAINT,),
    ).fetchone()
    return bool(row)


def requested(payload) -> bool:
    return bool(getattr(payload, FIELD, False))


def pending_values(conn, base_currency: str | None, payload) -> dict[str, Any]:
    """The stored columns of an expense that waits for its conversion.

    Only for an amount typed in the other supported currency, without a rate: with a rate the
    expense is converted now, and in the base currency there is nothing to convert.
    """
    base = str(base_currency or "CRC").upper()
    code = str(getattr(payload, "currency", None) or base).upper()
    if code == base or base not in SUPPORTED_CURRENCIES or code not in SUPPORTED_CURRENCIES:
        raise HTTPException(status_code=422, detail=tx(
            "Solo un gasto en la otra moneda puede esperar al cierre para convertirse.",
            "Only an expense in the other currency can wait for the close to be converted."))
    if getattr(payload, "exchange_rate", None) is not None:
        raise HTTPException(status_code=422, detail=tx(
            "Con tipo de cambio el gasto se convierte ahora; sin él, espera al cierre.",
            "With a rate the expense is converted now; without one, it waits for the close."))
    raw = _finite(payload.amount)
    typed = None if raw is None or raw <= 0 else _within(raw, MAX_ORIGINAL)
    if typed is None or typed <= 0:
        raise HTTPException(status_code=422, detail=tx("El monto no es válido.", "The amount is not valid."))
    if not pending_available(conn):
        raise HTTPException(status_code=503, detail={
            "code": "pending_conversion_unavailable",
            "message": tx("Todavía no se puede dejar un gasto para convertir al cierre.",
                          "An expense can't wait for the close to be converted yet."),
        })
    return {"amount": None, "original_amount": typed, "original_currency": code, "exchange_rate": None}


def _amount(value) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01")))


def list_pending() -> dict[str, Any]:
    """The caller's expenses waiting for their conversion, and their totals per currency (read-only)."""
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        if not pending_available(conn):
            return {"status": "ok", "available": False, "items": [], "totals": []}
        rows = conn.execute(
            f"""SELECT id, created_at::date AS entry_date, COALESCE(description,'') AS description, category,
                       original_amount, original_currency, {expense_account.SELECT_SQL}
                FROM expenses WHERE workspace_id=%s AND amount IS NULL
                ORDER BY created_at DESC, id DESC""",
            (workspace_id,),
        ).fetchall()
    items, totals = [], {}
    for row in rows:
        currency = str(row["original_currency"])
        items.append({
            "movement_id": f"expense:{row['id']}", "id": row["id"], "entry_date": str(row["entry_date"])[:10],
            "description": row["description"], "category": row["category"],
            "original_amount": _amount(row["original_amount"]), "original_currency": currency,
            "financial_account_id": row["financial_account_id"],
        })
        total = totals.setdefault(currency, {"currency": currency, "amount": Decimal("0"), "count": 0})
        total["amount"] += Decimal(str(row["original_amount"]))
        total["count"] += 1
    return {
        "status": "ok", "available": True, "items": items,
        "totals": [{**total, "amount": _amount(total["amount"])} for _, total in sorted(totals.items())],
    }
