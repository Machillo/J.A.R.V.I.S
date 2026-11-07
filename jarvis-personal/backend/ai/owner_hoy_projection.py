"""Owner only: Hoy's statement projected whole from its first day.

The Owner's Hoy shows his card statement (``owner_ledger.owner_cycle_window``). He never types his
installments, his fixed expenses or his automatic savings: they go by themselves. So the statement
counts them from its first day, and what he records adds on top:

- Ingresos: the ledger's income (the salary rule with OT, bonuses and VGH, plus other incomes).
- Gastos: what the ledger already holds (spending and posted debt payments), plus the installments
  and fixed expenses due in the statement that are not paid yet, plus the statement's automatic
  savings, plus the dollar expenses still waiting for their close (estimated in colones).
- Resultado: Ingresos − Gastos.

A commitment already paid is in the ledger and is not added again. Derived on read, nothing is
written. Users' Hoy never calls this module (``vip_service`` calls it only for the verified Owner).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from math import ceil
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

# Debt payments made with money counted elsewhere: a locked block's abono (its weekly savings were
# already this or an earlier statement's automatic savings) and a confirmed distribution's abonos
# (the leftover of the statement before). Spending them again here would count them twice.
FUNDED_ELSEWHERE = ("debt_savings_block", "owner_distribution")
_PAID = "paid"


def _d(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _day(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def pending_installments(debts: list[dict[str, Any]], paid_debt_ids: set[int], end_exclusive: date) -> dict[str, Any]:
    """Each debt's installment of the statement not paid yet: one per debt (a statement is one month).

    Every debt counts, card installment plans (tasa cero, minicuotas) too: the daily debt schedule
    posts their installment as a debt payment like any other, and the card statements imported so
    far carry no installment charges. Left out: debts whose installment was paid in the statement
    (``paid_debt_ids``, already in the ledger), debts whose next installment falls after it, and
    unknown payments (counted in ``unknown``, never as 0)."""
    total, unknown = Decimal("0"), 0
    for debt in debts:
        if int(debt["id"]) in paid_debt_ids:
            continue
        next_due = _day(debt.get("next_payment_date"))
        if next_due is not None and next_due >= end_exclusive:
            continue
        if debt.get("monthly_payment") is None:
            unknown += 1
            continue
        total += _d(debt["monthly_payment"])
    return {"total": total, "unknown": unknown}


def pending_fixed(items: list[dict[str, Any]], start: date, end_exclusive: date, is_debt: Any) -> Decimal:
    """The fixed expenses due in the statement not matched as paid (``get_fixed_expense_status`` items).
    A fixed expense that is a debt is already an installment above (``is_debt``)."""
    total = Decimal("0")
    for item in items:
        due = _day(item.get("due_date"))
        if not item.get("due_this_month") or due is None or not start <= due < end_exclusive:
            continue
        if item.get("status") == _PAID or is_debt(item.get("fixed_expense") or {}):
            continue
        total += _d(item.get("expected_amount"))
    return total


def projected(cycle: dict[str, Any], *, installments: Decimal, fixed: Decimal, savings_total: Any, dollars: Decimal | None,
              funded_elsewhere: Decimal = Decimal("0")) -> dict[str, Any]:
    """The statement's three figures; the parts of Gastos are kept for whoever needs to explain it."""
    income = _d(cycle.get("income"))
    parts = {
        "recorded": _d(cycle.get("expenses")),
        "debt_paid": max(_d(cycle.get("debt_paid")) - funded_elsewhere, Decimal("0")),
        "installments_pending": installments,
        "fixed_pending": fixed,
        "automatic_savings": _d(savings_total),
        "dollars_estimated": dollars or Decimal("0"),
    }
    expenses = sum(parts.values(), Decimal("0"))
    money = lambda value: float(value.quantize(Decimal("0.01")))  # noqa: E731
    return {"income": money(income), "expenses": money(expenses), "result": money(income - expenses),
            "parts": {key: money(value) for key, value in parts.items()}, "dollars_unknown": dollars is None}


def ot_hour_net(profile: dict[str, Any] | None, deductions: list[dict[str, Any]]) -> Decimal | None:
    """What one hour of OT leaves in hand: hourly rate × OT multiplier, less the percentage payroll
    deductions (the same ones the salary rule takes from OT). Unknown without a rate."""
    rate = _d((profile or {}).get("hourly_rate"))
    if rate <= 0:
        return None
    multiplier = _d((profile or {}).get("overtime_multiplier") or "1.5")
    share = sum((_d(row.get("amount")) for row in deductions
                 if str(row.get("deduction_type") or "").lower().strip() == "percentage"), Decimal("0")) / 100
    net = rate * multiplier * (1 - share)
    return net if net > 0 else None


def ot_hours_to_cover(result: Any, hour_net: Decimal | None) -> int | None:
    """Whole OT hours that bring a negative statement back to zero; None when it isn't negative or
    an OT hour's value is unknown."""
    deficit = -_d(result)
    if deficit <= 0 or not hour_net:
        return None
    return ceil(deficit / hour_net)


def _ot_inputs(conn, workspace_id: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    profile = conn.execute(
        "SELECT hourly_rate, overtime_multiplier FROM employment_profile WHERE workspace_id=%s ORDER BY id DESC LIMIT 1",
        (workspace_id,),
    ).fetchone()
    deductions = conn.execute("SELECT deduction_type, amount FROM payroll_deductions WHERE workspace_id=%s", (workspace_id,)).fetchall()
    return (dict(profile) if profile else None), [dict(row) for row in deductions]


def _paid_installment_debt_ids(conn, workspace_id: str, start: date, end_exclusive: date) -> set[int]:
    rows = conn.execute(
        """SELECT DISTINCT debt_id FROM debt_payments WHERE workspace_id=%s AND payment_type='monthly_payment'
           AND payment_date >= %s AND payment_date < %s AND debt_id IS NOT NULL""",
        (workspace_id, start, end_exclusive),
    ).fetchall()
    return {int(row["debt_id"]) for row in rows}


def _funded_elsewhere(conn, workspace_id: str, start: date, end_exclusive: date) -> Decimal:
    from backend.user_product.owner_ledger import _transaction_date_sql

    transaction_date = _transaction_date_sql()
    row = conn.execute(
        f"""SELECT COALESCE(SUM(amount),0) AS total FROM transactions WHERE workspace_id=%s
            AND LOWER(BTRIM(COALESCE(transaction_type,'')))='debt_payment' AND source = ANY(%s)
            AND {transaction_date} >= %s AND {transaction_date} < %s""",
        (workspace_id, list(FUNDED_ELSEWHERE), start, end_exclusive),
    ).fetchone()
    return _d(row["total"])


def _fixed_items(start: date, end_exclusive: date) -> list[dict[str, Any]]:
    from backend.finance.fixed_expenses import get_fixed_expense_status

    months, month = [], start.replace(day=1)
    while month < end_exclusive:
        months.append(month.strftime("%Y-%m"))
        month = (month + timedelta(days=32)).replace(day=1)
    return [item for key in months for item in get_fixed_expense_status(key).get("items") or []]


def project(conn, workspace_id: str, cycle: dict[str, Any], savings: dict[str, Any], debts: list[dict[str, Any]],
            base_currency: str) -> dict[str, Any]:
    """The Owner's statement (``owner_cycle_totals``) projected whole. SELECT only."""
    from backend.ai.strategy_dashboard import _is_debt_like_fixed_expense
    from backend.user_product import pending_conversion

    start = date.fromisoformat(cycle["period_start"])
    last = date.fromisoformat(cycle["period_end"])
    end_exclusive = last + timedelta(days=1)
    installments = pending_installments(debts, _paid_installment_debt_ids(conn, workspace_id, start, end_exclusive), end_exclusive)
    debt_names = {str(debt.get("name") or "").lower().strip() for debt in debts}
    fixed = pending_fixed(_fixed_items(start, end_exclusive), start, end_exclusive,
                          lambda row: _is_debt_like_fixed_expense(row, debt_names))
    dollars = pending_conversion.estimate_between(conn, workspace_id, base_currency, start, last)
    result = projected(cycle, installments=installments["total"], fixed=fixed, savings_total=savings.get("total"), dollars=dollars,
                       funded_elsewhere=_funded_elsewhere(conn, workspace_id, start, end_exclusive))
    try:
        profile, deductions = _ot_inputs(conn, workspace_id)
        hours = ot_hours_to_cover(result["result"], ot_hour_net(profile, deductions))
    except Exception as exc:  # noqa: BLE001 — the OT hint is optional
        logger.warning("owner_ot_hours_unavailable error_type=%s", type(exc).__name__)
        hours = None
    return {**result, "unknown_installments": installments["unknown"], "ot_hours_to_cover": hours}


def statement_result() -> float | None:
    """Hoy's statement result for the signed-in Owner, read on its own (the plan of the month splits
    it). SELECT only. None when it can't be read: the plan then keeps its own estimate."""
    try:
        from backend.ai.owner_commitments import cycle_automatic_savings
        from backend.ai.owner_debt_block_store import stored_blocks
        from backend.ai.preferences import get_preference
        from backend.auth.current_user import get_current_account_id, get_current_workspace_id
        from backend.ai import strategy_dashboard  # its connection: the strategy's tests answer it in memory
        from backend.core.time import costa_rica_today
        from backend.user_product import owner_ledger
        from backend.user_product.debt_payments import with_known_payments
        from backend.user_product.debt_rates import with_known_rates
        from backend.user_product.entry_currency import account_base_currency

        today = costa_rica_today()
        account_id, workspace_id = get_current_account_id(), get_current_workspace_id()
        with strategy_dashboard.get_connection() as conn:
            cycle = owner_ledger.owner_cycle_totals(conn, workspace_id, today)
            savings = cycle_automatic_savings(get_preference("salvavidas") or {}, stored_blocks(), date.fromisoformat(cycle["period_start"]),
                                              date.fromisoformat(cycle["period_end"]), today)
            debts = with_known_payments(with_known_rates([dict(row) for row in conn.execute(
                """SELECT id,name,remaining_amount,total_amount,monthly_payment,monthly_payment_known,interest_rate,interest_rate_known,debt_type,
                          payment_day,next_payment_date FROM debts WHERE workspace_id=%s AND remaining_amount>0 ORDER BY id""",
                (workspace_id,)).fetchall()]))
            return project(conn, workspace_id, cycle, savings, debts, account_base_currency(conn, account_id))["result"]
    except Exception as exc:  # noqa: BLE001 — the plan never fails because of it
        logger.warning("owner_statement_result_unavailable error_type=%s", type(exc).__name__)
        return None


def free_share(result: float) -> float | None:
    """What the Owner's strategy leaves for him (``vida_controlada``) when it splits the statement's
    result: the same split as JARVIS's exact distribution. Nothing left: 0. Unavailable: None."""
    if result <= 0:
        return 0.0
    try:
        from backend.ai.strategy_dashboard import _owner_strategy_blueprint

        return round(float(_owner_strategy_blueprint(statement_base=round(result, 2)).get("safe_to_spend") or 0), 2)
    except Exception as exc:  # noqa: BLE001 — Hoy never fails because of the strategy
        logger.warning("owner_free_share_unavailable error_type=%s", type(exc).__name__)
        return None
