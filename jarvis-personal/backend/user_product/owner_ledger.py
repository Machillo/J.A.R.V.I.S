"""The Owner's monthly ledger: one rule per movement type for every Owner screen.

Specification: the Owner financial-information audit, Fase 1 §2 (single ledger). It applies the
taxonomy the codebase already defines (``finance/balance_movements.py``,
``email_monitor/movement_taxonomy.py``, ``finance/receivable_semantics.py``) the same way on Hoy,
Movimientos > Resumen del mes, the Movimientos list and JARVIS > Análisis financiero:

- earned income: ``income`` movements plus the ``salaries``, ``payroll_events`` (amount > 0, by the
  event's date) and ``bonuses`` tables;
- spending: ``expense`` movements plus the ``expenses`` table, net of ``refund`` movements (a
  refund is never income; spending never goes below 0, the rest is an unmatched refund);
- debt payments: ``debt_payment`` movements, a line of their own;
- other inflows (money in that was not earned): loans received, receivable collections, asset
  sales;
- not counted: receivable offsets (no money moved) and confirmed own transfers;
- unclassified: ``transfer`` and any type this specification does not decide. They are reported
  as a count and never guessed into income or spending.

Owner only: callers use it when ``owner_context()`` is true (the server-authenticated role).
Free, Basic and VIP keep their current totals. Reading never writes.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Iterable

INCOME = "income"
EXPENSES = "expenses"
REFUNDS = "refunds"
DEBT_PAYMENTS = "debt_payments"
OTHER_INFLOWS = "other_inflows"
NOT_COUNTED = "not_counted"
UNCLASSIFIED = "unclassified"

CONCEPT_BY_TYPE = {
    "income": INCOME,
    "expense": EXPENSES,
    "refund": REFUNDS,
    "debt_payment": DEBT_PAYMENTS,
    "loan_received": OTHER_INFLOWS,
    "loan_disbursement": OTHER_INFLOWS,
    "receivable_payment": OTHER_INFLOWS,
    "asset_sale": OTHER_INFLOWS,
    "receivable_offset": NOT_COUNTED,
    "internal_transfer": NOT_COUNTED,
    "transfer": UNCLASSIFIED,
}


def normalized_type(transaction_type: object) -> str:
    return str(transaction_type or "").strip().lower()


def concept_of(transaction_type: object) -> str:
    """The concept a movement counts in; a type the specification does not decide is unclassified."""
    return CONCEPT_BY_TYPE.get(normalized_type(transaction_type), UNCLASSIFIED)


def _money(value: object) -> float:
    return round(float(Decimal(str(value or 0))), 2)


def month_totals(groups: Iterable[tuple[object, object, int]], *, salaries: object = 0, payroll: object = 0,
                 bonuses: object = 0, expenses_table: object = 0) -> dict:
    """The month's figures from ``(transaction_type, amount, count)`` groups of ``transactions`` and
    the sums of the other ledger tables. Exact (Decimal) arithmetic, rounded once at the end."""
    sums = {concept: Decimal("0") for concept in (INCOME, EXPENSES, REFUNDS, DEBT_PAYMENTS, OTHER_INFLOWS)}
    unclassified = 0
    for transaction_type, amount, count in groups:
        concept = concept_of(transaction_type)
        if concept == UNCLASSIFIED:
            unclassified += int(count or 0)
        elif concept in sums:
            sums[concept] += Decimal(str(amount or 0))
    income = sums[INCOME] + sum(Decimal(str(value or 0)) for value in (salaries, payroll, bonuses))
    gross = sums[EXPENSES] + Decimal(str(expenses_table or 0))
    refunds = sums[REFUNDS]
    spending = max(gross - refunds, Decimal("0"))
    balance = income - spending - sums[DEBT_PAYMENTS]
    return {
        "income": _money(income),
        "expenses": _money(spending),
        "gross_expenses": _money(gross),
        "refunds": _money(refunds),
        "unmatched_refunds": _money(max(refunds - gross, Decimal("0"))),
        "debt_paid": _money(sums[DEBT_PAYMENTS]),
        "other_inflows": _money(sums[OTHER_INFLOWS]),
        "balance": _money(balance),
        "cash_flow": _money(balance + sums[OTHER_INFLOWS]),
        "unclassified_count": unclassified,
    }


def _transaction_date_sql() -> str:
    # The same date basis as Movimientos > Resumen del mes (free_service._transaction_date_sql).
    raw = "NULLIF(BTRIM(transaction_date::text),'')"
    return f"CASE WHEN {raw} ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}' THEN SUBSTRING({raw} FROM 1 FOR 10)::date ELSE NULL END"


def owner_month_totals(conn, workspace_id: str, start: date, end: date) -> dict:
    """The month ``[start, end)`` of one workspace by the rules above. SELECT only."""
    transaction_date = _transaction_date_sql()
    groups = conn.execute(
        f"""SELECT LOWER(BTRIM(COALESCE(transaction_type,''))) AS ledger_type, COALESCE(SUM(amount),0) AS total, COUNT(*) AS count
            FROM transactions WHERE workspace_id=%s AND {transaction_date} >= %s AND {transaction_date} < %s
            GROUP BY 1""",
        (workspace_id, start, end),
    ).fetchall()
    other = conn.execute(
        """SELECT
             COALESCE((SELECT SUM(amount) FROM salaries WHERE workspace_id=%s AND created_at::date >= %s AND created_at::date < %s),0) AS salaries,
             COALESCE((SELECT SUM(amount) FROM payroll_events WHERE workspace_id=%s AND amount>0
                        AND COALESCE(event_date, created_at::date) >= %s AND COALESCE(event_date, created_at::date) < %s),0) AS payroll,
             COALESCE((SELECT SUM(amount) FROM bonuses WHERE workspace_id=%s AND created_at::date >= %s AND created_at::date < %s),0) AS bonuses,
             COALESCE((SELECT SUM(amount) FROM expenses WHERE workspace_id=%s AND created_at::date >= %s AND created_at::date < %s),0) AS expenses_table""",
        (workspace_id, start, end, workspace_id, start, end, workspace_id, start, end, workspace_id, start, end),
    ).fetchone()
    return month_totals(
        [(row["ledger_type"], row["total"], row["count"]) for row in groups],
        salaries=other["salaries"], payroll=other["payroll"], bonuses=other["bonuses"], expenses_table=other["expenses_table"],
    )


def classify_movement(row: dict) -> dict:
    """A Movimientos row with its real kind and the concept it counts in (Owner list)."""
    kind = normalized_type(row.get("ledger_type") or row.get("transaction_type"))
    return {**row, "movement_kind": kind or None, "counts_in": concept_of(kind)}
