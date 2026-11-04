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

A mail or statement expense confirmed without a rate waits the same way (`candidate_waits`): it
becomes a pending expense, with no transaction until there is a rate to give it a base amount.

Dollars in a colones account also get, with the Banco Central's published selling rate
(`integrations/bccr_rates.py`):
- an estimate while they wait, read-only and labeled as such, at the purchase day's rate;
- their conversion when the close arrives (`close_due_periods`, a scheduled command), at the rate of
  the close's last day, as a card does. The user asked for that by keeping the expense in dollars
  until the close, and can still correct it or close it by hand first.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from fastapi import HTTPException

from backend.auth.current_user import get_current_account_id, get_current_workspace_id
from backend.core.database import get_connection
from backend.core.i18n import tx
from backend.core.idempotency import mark_applied
from backend.core.time import costa_rica_today
from backend.integrations import bccr_rates
from backend.finance.category_catalog import expense_type_for_category, manual_expense_category, normalize_category
from backend.user_product import conversion_periods, expense_account
from backend.user_product.entry_currency import (
    MAX_ORIGINAL, SUPPORTED_CURRENCIES, _finite, _within, account_base_currency, resolve_entry_amount,
)

logger = logging.getLogger(__name__)

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


def candidate_waits(conn, candidate: dict[str, Any], currency: str, transaction_type: str, exchange_rate: float | None) -> bool:
    """A mail or statement expense in the other currency, confirmed without a rate, waits for the close.

    Income and transfers have no pending state: they still need the rate. Before the migration the
    state cannot exist, so the confirmation keeps asking for it.
    """
    base = str(candidate.get("account_base_currency") or "CRC").upper()
    return (exchange_rate is None and transaction_type == "expense" and currency != base
            and base in SUPPORTED_CURRENCIES and currency in SUPPORTED_CURRENCIES and pending_available(conn))


def save_candidate_expense(conn, candidate: dict[str, Any], values: dict[str, Any], currency: str, *, owner: bool = False) -> int:
    """The pending expense of a confirmed candidate, in the caller's transaction.

    It is dated on the day of the purchase, not of the review, so it falls in the close the purchase
    belongs to, and it stays linked to the card the notice named: that card's cut decides the close.
    """
    money = pending_values(conn, candidate.get("account_base_currency"),
                           SimpleNamespace(currency=currency, amount=values["amount"], exchange_rate=None))
    category = manual_expense_category(normalize_category(values["category"], "expense", owner=owner))
    row = conn.execute(
        """INSERT INTO expenses(category,expense_type,description,amount,original_amount,original_currency,exchange_rate,
                                workspace_id,created_at)
           VALUES(%s,%s,%s,NULL,%s,%s,NULL,%s,%s::date+TIME '12:00') RETURNING id""",
        (category, expense_type_for_category(category, owner=owner), values["description"].strip(),
         money["original_amount"], money["original_currency"], candidate["workspace_id"], str(values["transaction_date"])[:10]),
    ).fetchone()
    if candidate.get("financial_account_id") is not None and expense_account.paid_with_available(conn):
        expense_account.write_link(conn, row["id"], candidate["financial_account_id"], workspace_id=candidate["workspace_id"])
    return int(row["id"])


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


def _totals(rows, estimates: dict[int, Decimal] | None = None) -> list[dict[str, Any]]:
    estimates = estimates or {}
    totals: dict[str, dict[str, Any]] = {}
    for row in rows:
        currency = str(row["original_currency"])
        total = totals.setdefault(currency, {"currency": currency, "amount": Decimal("0"), "count": 0, "estimated_amount": Decimal("0")})
        total["amount"] += Decimal(str(row["original_amount"]))
        total["count"] += 1
        estimate = estimates.get(row["id"])
        # One expense without an estimate leaves the total unknown: it would otherwise read as complete.
        total["estimated_amount"] = None if estimate is None or total["estimated_amount"] is None else total["estimated_amount"] + estimate
    listed = []
    for _, total in sorted(totals.items()):
        estimate = total.pop("estimated_amount")
        # Left out when unknown: a reader never finds a number that isn't there.
        listed.append({**total, "amount": _amount(total["amount"]), **({} if estimate is None else {"estimated_amount": _amount(estimate)})})
    return listed


def _estimates(conn, rows, base: str) -> dict[int, Decimal]:
    """Each waiting dollar expense in colones, at its purchase day's rate. No rate for that day: no estimate."""
    dollars = [row for row in rows if base == "CRC" and str(row["original_currency"]) == bccr_rates.CURRENCY]
    if not dollars:
        return {}
    days = [date.fromisoformat(str(row["entry_date"])[:10]) for row in dollars]
    rates = bccr_rates.rates_between(conn, min(days), max(days))
    estimates = {}
    for row, day in zip(dollars, days):
        rate = bccr_rates.rate_on_or_before(rates, day)
        if rate is not None:
            estimates[row["id"]] = Decimal(str(row["original_amount"])) * rate
    return estimates


def list_pending() -> dict[str, Any]:
    """The caller's expenses waiting for their conversion, grouped by close, with their totals (read-only)."""
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        if not pending_available(conn):
            return {"status": "ok", "available": False, "items": [], "totals": [], "periods": []}
        rows = _pending_rows(conn, workspace_id)
        base = account_base_currency(conn, get_current_account_id())
        estimates = _estimates(conn, rows, base) if rows else {}
        auto_close = base == "CRC" and bccr_rates.auto_close_active(conn)
    today = costa_rica_today()
    items, groups = [], {}
    for row in rows:
        period = _period(row)
        items.append({
            "movement_id": f"expense:{row['id']}", "id": row["id"], "entry_date": str(row["entry_date"])[:10],
            "description": row["description"], "category": row["category"],
            "original_amount": _amount(row["original_amount"]), "original_currency": str(row["original_currency"]),
            "financial_account_id": row["financial_account_id"], "period_key": period.key,
            "estimated_amount": _amount(estimates[row["id"]]) if row["id"] in estimates else None,
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
            "totals": _totals(group["rows"], estimates), "count": len(group["rows"]),
        })
    return {"status": "ok", "available": True, "items": items, "totals": _totals(rows, estimates), "periods": periods,
            "auto_close": auto_close}


def _convert(conn, rows, base: str, exchange_rate: float, workspace_id: str) -> tuple[int, Decimal, dict[str, Any]]:
    """One rate for the whole close. Only a row still waiting converts, so no close applies twice."""
    converted, total, values = 0, Decimal("0"), {}
    for row in rows:
        # The same conversion as an expense typed with a rate (entry_currency).
        values = resolve_entry_amount(base, row["original_amount"], row["original_currency"], exchange_rate)
        done = conn.execute(
            "UPDATE expenses SET amount=%s, exchange_rate=%s WHERE id=%s AND workspace_id=%s AND amount IS NULL RETURNING id",
            (values["amount"], values["exchange_rate"], row["id"], workspace_id),
        ).fetchone()
        if done:
            converted += 1
            total += values["amount"]
    return converted, total, values


def _close_due_in_workspace(conn, workspace_id: str, base: str, today: date) -> dict[str, int]:
    """Converts this workspace's dollars whose close has arrived, each close with the rate of its last day."""
    due: dict[str, list[dict]] = {}
    periods = {}
    for row in _pending_rows(conn, workspace_id, lock=True):
        period = _period(row)
        if period.closable(today) and str(row["original_currency"]) == bccr_rates.CURRENCY:
            due.setdefault(period.key, []).append(row)
            periods[period.key] = period
    result = {"closed_periods": 0, "converted": 0, "waiting_for_rate": 0}
    if not due:
        return result
    ends = [period.end for period in periods.values()]
    rates = bccr_rates.rates_between(conn, min(ends), max(ends))
    for key, rows in due.items():
        rate = bccr_rates.closing_rate(rates, periods[key].end, today)
        if rate is None:
            result["waiting_for_rate"] += 1
            continue
        converted, _, _ = _convert(conn, rows, base, float(rate), workspace_id)
        result["closed_periods"] += 1
        result["converted"] += converted
    return result


def close_due_periods(today: date) -> dict[str, int]:
    """The scheduled close, for every workspace, each one isolated in its own transaction: one that
    fails stays waiting and never touches another. A close without its rate waits for a later run.
    Only a colones account's dollars: no other pair has a published rate here."""
    totals = {"closed_periods": 0, "converted": 0, "waiting_for_rate": 0, "failed_workspaces": 0}
    with get_connection() as conn:
        if not pending_available(conn) or not bccr_rates.available(conn):
            return totals
        owners = conn.execute(
            """SELECT DISTINCT workspaces.id AS workspace_id, workspaces.owner_account_id AS account_id
               FROM expenses JOIN workspaces ON workspaces.id = expenses.workspace_id
               WHERE expenses.amount IS NULL AND expenses.original_currency = %s""",
            (bccr_rates.CURRENCY,),
        ).fetchall()
    for owner in owners:
        try:
            with get_connection() as conn:
                base = account_base_currency(conn, owner["account_id"])
                if base != "CRC":
                    continue
                result = _close_due_in_workspace(conn, owner["workspace_id"], base, today)
                conn.commit()
        except Exception as exc:  # noqa: BLE001 - one workspace never stops the others; no ids or amounts logged
            logger.error("Scheduled dollar close failed type=%s", type(exc).__name__)
            totals["failed_workspaces"] += 1
            continue
        for key, value in result.items():
            totals[key] += value
    return totals


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
        converted, total, values = _convert(conn, rows, base, exchange_rate, workspace_id)
        mark_applied(conn)
        conn.commit()
    return {"status": "ok", "period_key": period_key, "converted": converted, "amount": _amount(total), "currency": base,
            "exchange_rate": float(values["exchange_rate"])}
