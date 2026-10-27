"""Manual expenses waiting for their conversion (migration 20261027120000).

The user keeps an expense typed in the other currency (dollars, for a colones account) in that
currency until the close: the card's statement cut, or the calendar month without a card. One rate
then converts it (`close_period`). Until then the expense is "pending": `original_amount` and
`original_currency` hold what the user typed, `amount` (base currency) and `exchange_rate` are NULL.

Unknown is not zero. A pending expense never counts as 0 colones and DINCR never invents a rate:
every base-currency read leaves pending expenses out (`KNOWN_AMOUNT`), and this module reads them
apart, with their totals per currency, so colones and dollars accumulate side by side.

A request asks for it explicitly (`convert_at_close`): an expense in the other currency sent without
a rate and without the flag is still refused, as before. Until the migration is applied the state
cannot exist: the listing says "unavailable" and only a request that asks for it answers 503.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import HTTPException

from backend.auth.current_user import get_current_account_id, get_current_workspace_id
from backend.core.database import get_connection
from backend.core.i18n import tx
from backend.core.idempotency import mark_applied
from backend.core.time import costa_rica_today
from backend.user_product import conversion_periods, expense_account
from backend.user_product.entry_currency import (
    MAX_ORIGINAL, SUPPORTED_CURRENCIES, _finite, _within, account_base_currency, resolve_entry_amount,
)

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


def _pending_rows(conn, workspace_id: str, *, lock: bool = False) -> list[dict]:
    """The workspace's pending expenses with what decides their close: the card that paid them and
    its declared cut day (only the caller's own account rows, same workspace)."""
    return conn.execute(
        f"""SELECT expenses.id, expenses.created_at::date AS entry_date, COALESCE(expenses.description,'') AS description,
                   expenses.category, expenses.original_amount, expenses.original_currency, {expense_account.SELECT_SQL},
                   card.account_type, card.account_name, card.account_last4,
                   (to_jsonb(card)->>'statement_cut_day')::int AS statement_cut_day
            FROM expenses
            LEFT JOIN account_balances card
              ON card.id = (to_jsonb(expenses)->>'financial_account_id')::bigint AND card.workspace_id = expenses.workspace_id
            WHERE expenses.workspace_id=%s AND expenses.amount IS NULL
            ORDER BY expenses.created_at DESC, expenses.id DESC{" FOR UPDATE OF expenses" if lock else ""}""",
        (workspace_id,),
    ).fetchall()


def _period(row) -> conversion_periods.Period:
    return conversion_periods.period_for(date.fromisoformat(str(row["entry_date"])[:10]), account_id=row["financial_account_id"],
                                         account_type=row["account_type"], cut_day=row["statement_cut_day"])


def _totals(rows) -> list[dict[str, Any]]:
    totals: dict[str, dict[str, Any]] = {}
    for row in rows:
        currency = str(row["original_currency"])
        total = totals.setdefault(currency, {"currency": currency, "amount": Decimal("0"), "count": 0})
        total["amount"] += Decimal(str(row["original_amount"]))
        total["count"] += 1
    return [{**total, "amount": _amount(total["amount"])} for _, total in sorted(totals.items())]


def list_pending() -> dict[str, Any]:
    """The caller's expenses waiting for their conversion, grouped by close, with their totals (read-only)."""
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        if not pending_available(conn):
            return {"status": "ok", "available": False, "items": [], "totals": [], "periods": []}
        rows = _pending_rows(conn, workspace_id)
    today = costa_rica_today()
    items, groups = [], {}
    for row in rows:
        period = _period(row)
        items.append({
            "movement_id": f"expense:{row['id']}", "id": row["id"], "entry_date": str(row["entry_date"])[:10],
            "description": row["description"], "category": row["category"],
            "original_amount": _amount(row["original_amount"]), "original_currency": str(row["original_currency"]),
            "financial_account_id": row["financial_account_id"], "period_key": period.key,
        })
        group = groups.setdefault(period.key, {"period": period, "rows": [], "card": row if period.kind == "card" else None})
        group["rows"].append(row)
    periods = []
    for key, group in sorted(groups.items(), key=lambda entry: entry[1]["period"].end):
        period, card = group["period"], group["card"]
        periods.append({
            "key": key, "kind": period.kind, "start": period.start.isoformat(), "end": period.end.isoformat(),
            "closable": period.closable(today), "cut_day_missing": period.cut_day_missing or any(
                _period(row).cut_day_missing for row in group["rows"]),
            "account_id": period.account_id,
            "account_name": card["account_name"] if card else None, "account_last4": card["account_last4"] if card else None,
            "totals": _totals(group["rows"]), "count": len(group["rows"]),
        })
    return {"status": "ok", "available": True, "items": items, "totals": _totals(rows), "periods": periods}


def close_period(period_key: str, exchange_rate: float) -> dict[str, Any]:
    """The close: converts every expense still waiting in `period_key` with the user's one rate.

    A command, never a read: the user asks for it. The period is recomputed here (the client only
    names it) and must have ended. Only rows still pending in the caller's workspace are converted,
    locked first, so a second close of the same period converts nothing.
    """
    account_id, workspace_id = get_current_account_id(), get_current_workspace_id()
    with get_connection() as conn:
        if not pending_available(conn):
            raise HTTPException(status_code=503, detail={"code": "pending_conversion_unavailable",
                                                         "message": tx("Todavía no se pueden cerrar gastos en dólares.",
                                                                       "Dollar expenses can't be closed yet.")})
        base = account_base_currency(conn, account_id)
        rows = [row for row in _pending_rows(conn, workspace_id, lock=True) if _period(row).key == period_key]
        if not rows:
            raise HTTPException(status_code=404, detail={"code": "period_not_found",
                                                         "message": tx("No hay gastos por convertir en ese cierre.",
                                                                       "There are no expenses to convert in that close.")})
        period = _period(rows[0])
        if not period.closable(costa_rica_today()):
            raise HTTPException(status_code=409, detail={"code": "period_open", "message": tx(
                f"Este cierre termina el {period.end.isoformat()}: se convierte desde ese día.",
                f"This close ends on {period.end.isoformat()}: it converts from that day.")})
        converted, total = 0, Decimal("0")
        for row in rows:
            # The same conversion as an expense typed with a rate (entry_currency): one rate for the whole close.
            values = resolve_entry_amount(base, row["original_amount"], row["original_currency"], exchange_rate)
            done = conn.execute(
                "UPDATE expenses SET amount=%s, exchange_rate=%s WHERE id=%s AND workspace_id=%s AND amount IS NULL RETURNING id",
                (values["amount"], values["exchange_rate"], row["id"], workspace_id),
            ).fetchone()
            if done:
                converted += 1
                total += values["amount"]
        mark_applied(conn)
        conn.commit()
    return {"status": "ok", "period_key": period_key, "converted": converted, "amount": _amount(total), "currency": base,
            "exchange_rate": float(values["exchange_rate"])}
