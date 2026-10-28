"""The Owner's monthly ledger: one rule per movement type for every Owner screen.

Specification: the Owner financial-information audit, Fase 1 §2 (single ledger). It applies the
taxonomy the codebase already defines (``finance/balance_movements.py``,
``email_monitor/movement_taxonomy.py``, ``finance/receivable_semantics.py``) the same way on Hoy,
Movimientos > Resumen del mes, the Movimientos list and JARVIS > Análisis financiero:

- income is money received: ``income`` movements (deposits) plus the ``salaries`` table (the
  declared net salary that actually arrives);
- gross payroll is reported apart and never added to income or to the result: overtime and VGH
  (``payroll_events``, VGH negative) and ``bonuses``. The salary projection takes CCSS and income
  tax from these amounts and the money arrives inside the salary deposit, so adding them would
  count the deposit twice;
- spending: ``expense`` movements plus the ``expenses`` table, net of ``refund`` movements (a
  refund is never income; spending never goes below 0, the rest is an unmatched refund);
- debt payments: ``debt_payment`` movements, a line of their own;
- other inflows (money in that was not earned): loans received, receivable collections, asset
  sales;
- not counted: receivable offsets (no money moved) and confirmed own transfers;
- unclassified: ``transfer`` and any type this specification does not decide. They are reported
  as a count and never guessed into income or spending.

Dates: movements use their ``transaction_date`` (a date). The record tables only keep
``created_at``, written as UTC wall time (``NOW()`` in a UTC session, or the work date at 12:00
by the app); it is read as a Costa Rica date (UTC-6, no daylight saving). No work date is
invented: ``payroll_events.event_date`` exists only outside the repository schema and is empty.

A month is complete only when nothing is waiting: no pending mail notices dated in it, no
unclassified movements, and no gross payroll without a deposit. Otherwise ``complete`` is false
with the reasons, so its totals are never presented as reconciled.

Owner only: the shared Users services use it when ``owner_account_context()`` says the account
and workspace are the verified Owner's (stored identity); the Owner-only analysis route uses the
server-authenticated role. Free, Basic and VIP keep their current totals. Reading never writes.
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
PAYROLL_ACCRUED = "payroll_accrued"
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
    "payroll_accrued": PAYROLL_ACCRUED,
    "receivable_offset": NOT_COUNTED,
    "internal_transfer": NOT_COUNTED,
    "transfer": UNCLASSIFIED,
}

# Why a month is not complete, in a stable order.
PENDING_MAIL_REVIEW = "pending_mail_review"
UNCLASSIFIED_MOVEMENTS = "unclassified_movements"
PAYROLL_WITHOUT_DEPOSIT = "payroll_without_deposit"


def normalized_type(transaction_type: object) -> str:
    return str(transaction_type or "").strip().lower()


def concept_of(transaction_type: object) -> str:
    """The concept a movement counts in; a type the specification does not decide is unclassified."""
    return CONCEPT_BY_TYPE.get(normalized_type(transaction_type), UNCLASSIFIED)


def _money(value: object) -> float:
    return round(float(Decimal(str(value or 0))), 2)


def _decimal(value: object) -> Decimal:
    return Decimal(str(value or 0))


def month_totals(groups: Iterable[tuple[object, object, int]], *, salaries: object = 0, overtime: object = 0,
                 vgh: object = 0, bonuses: object = 0, expenses_table: object = 0, pending_mail: int = 0) -> dict:
    """The month's figures from ``(transaction_type, amount, count)`` groups of ``transactions``, the
    sums of the record tables and the count of pending mail notices dated in the month. Exact
    (Decimal) arithmetic, rounded once at the end."""
    sums = {concept: Decimal("0") for concept in (INCOME, EXPENSES, REFUNDS, DEBT_PAYMENTS, OTHER_INFLOWS)}
    inflows = {"loan_received": Decimal("0"), "receivable_payments": Decimal("0"), "asset_sale_proceeds": Decimal("0")}
    unclassified = 0
    for transaction_type, amount, count in groups:
        kind, value = normalized_type(transaction_type), _decimal(amount)
        concept = concept_of(kind)
        if concept == UNCLASSIFIED:
            unclassified += int(count or 0)
        elif concept in sums:
            sums[concept] += value
        if kind in ("loan_received", "loan_disbursement"):
            inflows["loan_received"] += value
        elif kind == "receivable_payment":
            inflows["receivable_payments"] += value
        elif kind == "asset_sale":
            inflows["asset_sale_proceeds"] += value
    income = sums[INCOME] + _decimal(salaries)
    gross = sums[EXPENSES] + _decimal(expenses_table)
    refunds = sums[REFUNDS]
    spending = max(gross - refunds, Decimal("0"))
    balance = income - spending - sums[DEBT_PAYMENTS]
    accrued = {"overtime_gross": _decimal(overtime), "vgh_gross": _decimal(vgh), "bonuses_gross": _decimal(bonuses)}
    accrued_total = sum(accrued.values(), Decimal("0"))
    pending = int(pending_mail or 0)
    reasons = []
    if pending:
        reasons.append(PENDING_MAIL_REVIEW)
    if unclassified:
        reasons.append(UNCLASSIFIED_MOVEMENTS)
    if any(accrued.values()) and income == 0:
        reasons.append(PAYROLL_WITHOUT_DEPOSIT)
    return {
        "income": _money(income),
        "expenses": _money(spending),
        "gross_expenses": _money(gross),
        "refunds": _money(refunds),
        "unmatched_refunds": _money(max(refunds - gross, Decimal("0"))),
        "debt_paid": _money(sums[DEBT_PAYMENTS]),
        "other_inflows": _money(sums[OTHER_INFLOWS]),
        **{key: _money(value) for key, value in inflows.items()},
        "balance": _money(balance),
        "cash_flow": _money(balance + sums[OTHER_INFLOWS]),
        "unclassified_count": unclassified,
        "payroll_accrued": {**{key: _money(value) for key, value in accrued.items()}, "total_gross": _money(accrued_total)},
        "pending_mail_count": pending,
        "complete": not reasons,
        "incomplete_reasons": reasons,
    }


def _transaction_date_sql() -> str:
    # The same date basis as Movimientos > Resumen del mes (free_service._transaction_date_sql).
    raw = "NULLIF(BTRIM(transaction_date::text),'')"
    return f"CASE WHEN {raw} ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}' THEN SUBSTRING({raw} FROM 1 FOR 10)::date ELSE NULL END"


# A record timestamp (UTC wall time) is read as its Costa Rica date, ``(created_at - interval
# '6 hours')::date``: UTC-6, no daylight saving, so it needs no time-zone database and no session
# time zone. Every statement names its table literally, so the role-grant scanner sees it
# (tests/test_dincr_app_grants.py): no interpolated table names.
RECORD_SUMS = {
    "salaries": ("salaries", """SELECT COALESCE(SUM(amount),0) AS total FROM salaries WHERE workspace_id=%s
        AND (created_at - interval '6 hours')::date >= %s AND (created_at - interval '6 hours')::date < %s"""),
    "overtime": ("payroll_events", """SELECT COALESCE(SUM(amount),0) AS total FROM payroll_events WHERE workspace_id=%s AND amount>0
        AND (created_at - interval '6 hours')::date >= %s AND (created_at - interval '6 hours')::date < %s"""),
    "vgh": ("payroll_events", """SELECT COALESCE(SUM(amount),0) AS total FROM payroll_events WHERE workspace_id=%s AND amount<0
        AND (created_at - interval '6 hours')::date >= %s AND (created_at - interval '6 hours')::date < %s"""),
    "bonuses": ("bonuses", """SELECT COALESCE(SUM(amount),0) AS total FROM bonuses WHERE workspace_id=%s
        AND (created_at - interval '6 hours')::date >= %s AND (created_at - interval '6 hours')::date < %s"""),
    "expenses_table": ("expenses", """SELECT COALESCE(SUM(amount),0) AS total FROM expenses WHERE workspace_id=%s
        AND (created_at - interval '6 hours')::date >= %s AND (created_at - interval '6 hours')::date < %s"""),
}

# The months that hold record rows (JARVIS > Análisis financiero lists every month with data).
RECORD_MONTHS = {
    "salaries": "SELECT to_char((created_at - interval '6 hours')::date, 'YYYY-MM') AS month FROM salaries WHERE workspace_id = %s",
    "payroll_events": "SELECT to_char((created_at - interval '6 hours')::date, 'YYYY-MM') AS month FROM payroll_events WHERE workspace_id = %s",
    "bonuses": "SELECT to_char((created_at - interval '6 hours')::date, 'YYYY-MM') AS month FROM bonuses WHERE workspace_id = %s",
    "expenses": "SELECT to_char((created_at - interval '6 hours')::date, 'YYYY-MM') AS month FROM expenses WHERE workspace_id = %s",
}

LEDGER_TABLES = ("salaries", "payroll_events", "bonuses", "expenses")
OPTIONAL_TABLES = LEDGER_TABLES + ("finva_email_candidates",)


def _existing_tables(conn) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM unnest(%s::text[]) AS name WHERE to_regclass('public.' || name) IS NOT NULL",
        (list(OPTIONAL_TABLES),),
    ).fetchall()
    return {row["name"] for row in rows}


def owner_month_totals(conn, workspace_id: str, start: date, end: date) -> dict:
    """The month ``[start, end)`` of one workspace by the rules above. SELECT only. A table that does
    not exist holds no rows (as ``basic_service._basic_tables_ready``)."""
    transaction_date = _transaction_date_sql()
    groups = conn.execute(
        f"""SELECT LOWER(BTRIM(COALESCE(transaction_type,''))) AS ledger_type, COALESCE(SUM(amount),0) AS total, COUNT(*) AS count
            FROM transactions WHERE workspace_id=%s AND {transaction_date} >= %s AND {transaction_date} < %s
            GROUP BY 1""",
        (workspace_id, start, end),
    ).fetchall()
    tables = _existing_tables(conn)
    record = {key: (conn.execute(sql, (workspace_id, start, end)).fetchone()["total"] if table in tables else 0)
              for key, (table, sql) in RECORD_SUMS.items()}

    pending = 0
    if "finva_email_candidates" in tables:
        pending = conn.execute(
            "SELECT COUNT(*) AS count FROM finva_email_candidates WHERE workspace_id=%s AND status='pending' "
            "AND NOT COALESCE(is_internal_transfer,FALSE) AND transaction_date >= %s AND transaction_date < %s",
            (workspace_id, start, end),
        ).fetchone()["count"]
    return month_totals([(row["ledger_type"], row["total"], row["count"]) for row in groups], pending_mail=pending, **record)


def classify_movement(row: dict) -> dict:
    """A Movimientos row with its real kind and the concept it counts in (Owner list)."""
    kind = normalized_type(row.get("ledger_type") or row.get("transaction_type"))
    return {**row, "movement_kind": kind or None, "counts_in": concept_of(kind)}
