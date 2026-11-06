"""The Owner's monthly ledger: one rule per movement type for every Owner screen.

Specification: the Owner financial-information audit, Fase 1 §2 (single ledger). It applies the
taxonomy the codebase already defines (``finance/balance_movements.py``,
``email_monitor/movement_taxonomy.py``, ``finance/receivable_semantics.py``) the same way on Hoy,
Movimientos > Resumen del mes, the Movimientos list and JARVIS > Análisis financiero:

- income: ``income`` movements plus the month's salary, decided by the salary rule below;
- the salary (the Owner's alone: his pay is known before it arrives). A month's salary is the
  projected net salary (``finance/salary_projection.py``, the JARVIS formula: base net plus that
  month's overtime and bonuses net of deductions, minus its VGH) for the month in course, from
  its first day, and for a closed month with no salary received. A closed month with salary
  received keeps what was received: salary deposits (``income`` movements in "Salario") plus the
  ``salaries`` table. Without a projection (no employment profile and no base salary) the salary
  is what was received. The estimate replaces the received deposits of its month, never adds to
  them; a closed month whose salary is estimated is not complete (``salary_estimated``);
- gross payroll is also reported apart (``payroll_accrued``): overtime and VGH (``payroll_events``,
  VGH negative) and ``bonuses``. Only their net reaches income, inside the salary;
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

import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable

from backend.core.time import costa_rica_today
from backend.finance import salary_projection

INCOME = "income"
EXPENSES = "expenses"
REFUNDS = "refunds"
DEBT_PAYMENTS = "debt_payments"
OTHER_INFLOWS = "other_inflows"
PAYROLL_ACCRUED = "payroll_accrued"
SALARY_ESTIMATED = "salary_estimated"
SALARY_CATEGORY = "Salario"
OWNER_CUT_DAY = 21
OWNER_PAYMENT_DAY = 5
# Zero-rate and mini installments are charged on the card: they are already the statement's expenses.
CARD_INSTALLMENT_TYPES = {"tasa_cero", "minicuotas"}
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
# The ``salaries`` rows that are salary (the app's "Salario" and "Boleta de pago", and rows without a
# category from before categories existed); every other category is another income.
SALARY_ROWS_SQL = """SELECT COALESCE(SUM(amount),0) AS total FROM salaries WHERE workspace_id=%s
        AND (category IS NULL OR LOWER(BTRIM(category)) IN ('salario','boleta de pago'))
        AND (created_at - interval '6 hours')::date >= %s AND (created_at - interval '6 hours')::date < %s"""

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
OPTIONAL_TABLES = LEDGER_TABLES + ("finva_email_candidates", "employment_profile", "payroll_deductions")


def _existing_tables(conn) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM unnest(%s::text[]) AS name WHERE to_regclass('public.' || name) IS NOT NULL",
        (list(OPTIONAL_TABLES),),
    ).fetchall()
    return {row["name"] for row in rows}


def owner_month_totals(conn, workspace_id: str, start: date, end: date, *, salary: dict | None = None) -> dict:
    """The month ``[start, end)`` of one workspace by the rules above. SELECT only. A table that does
    not exist holds no rows (as ``basic_service._basic_tables_ready``). ``salary``: the salary of a
    period that is not made of calendar months (``owner_cycle_totals``)."""
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
    salary = salary or owner_salary(conn, workspace_id, start, end, tables)
    # The rule's salary replaces what was received in its months (salaries table and "Salario" deposits).
    record["salaries"] = _decimal(record["salaries"]) + salary["salary"] - salary["received"]
    totals = month_totals([(row["ledger_type"], row["total"], row["count"]) for row in groups], pending_mail=pending, **record)
    if salary["closed_estimated"]:
        totals["incomplete_reasons"] = totals["incomplete_reasons"] + [SALARY_ESTIMATED]
        totals["complete"] = False
    return {**totals, "salary": _money(salary["salary"]), "salary_estimated": salary["estimated"]}


def _next_month(month: date) -> date:
    return date(month.year + (month.month == 12), 1 if month.month == 12 else month.month + 1, 1)


def _months(start: date, end: date) -> list[date]:
    months, month = [], start.replace(day=1)
    while month < end:
        months.append(month)
        month = _next_month(month)
    return months


def _rows(conn, sql: str, params: tuple) -> list[dict]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def owner_cycle_window(today: date) -> tuple[date, date, date]:
    """The card statement Hoy shows: ``(start, end_exclusive, payment_date)``.

    The cut is on the 21st, included in its statement, and it is paid on the 5th of the next month.
    A statement stays on screen until it is paid: the next one takes over on the 6th. On 2 Nov that
    is 22 Sep to 21 Oct (paid on 5 Nov); from 6 Nov, 22 Oct to 21 Nov (paid on 5 Dec).
    """
    anchor = today.replace(day=1)
    if today.day <= OWNER_PAYMENT_DAY:
        anchor = (anchor - timedelta(days=1)).replace(day=1)
    previous = (anchor - timedelta(days=1)).replace(day=1)
    return (previous.replace(day=OWNER_CUT_DAY + 1), anchor.replace(day=OWNER_CUT_DAY + 1),
            _next_month(anchor).replace(day=OWNER_PAYMENT_DAY))


def owner_cycle_totals(conn, workspace_id: str, today: date) -> dict:
    """The statement of ``owner_cycle_window`` by the ledger's rules, with one month of salary. SELECT only."""
    start, end, payment = owner_cycle_window(today)
    tables = _existing_tables(conn)
    salary = _period_salary(conn, workspace_id, start, end, _salary_inputs(conn, workspace_id, tables), tables, is_open=end > today)
    totals = owner_month_totals(conn, workspace_id, start, end, salary=salary)
    return {**totals, "month": start.strftime("%Y-%m"), "period_start": start.isoformat(), "period_end": (end - timedelta(days=1)).isoformat(),
            "payment_date": payment.isoformat()}


def payments_outside_the_card(debts: list[dict]) -> float:
    """What the Owner's debts ask for every month beyond what his statement already holds."""
    return round(sum(_money(debt.get("monthly_payment")) for debt in debts
                     if str(debt.get("debt_type") or "").lower() not in CARD_INSTALLMENT_TYPES), 2)


def _salary_inputs(conn, workspace_id: str, tables: set[str]) -> dict:
    profile = (conn.execute(
        "SELECT hourly_rate, regular_hours_per_week FROM employment_profile WHERE workspace_id=%s ORDER BY id DESC LIMIT 1",
        (workspace_id,)).fetchone() if "employment_profile" in tables else None)
    deductions = (_rows(conn, "SELECT name, deduction_type, amount, frequency FROM payroll_deductions WHERE workspace_id=%s",
                        (workspace_id,)) if "payroll_deductions" in tables else [])
    base = (conn.execute(
        """SELECT amount FROM salaries WHERE workspace_id=%s
           ORDER BY CASE WHEN LOWER(source) LIKE '%%base%%' THEN 0 WHEN LOWER(source) LIKE '%%mensual%%' THEN 1 ELSE 2 END, id DESC
           LIMIT 1""", (workspace_id,)).fetchone() if "salaries" in tables else None)
    base_net = salary_projection.as_float(base["amount"] if base else 0)
    return {"profile": profile, "deductions": deductions, "base_net": base_net}


def _period_salary(conn, workspace_id: str, start: date, end: date, inputs: dict, tables: set[str], *, is_open: bool) -> dict:
    """One month of salary earned in ``[start, end)``: projected while the period is open, and once
    closed if none was received; otherwise what was received. The salary rule for one period."""
    transaction_date = _transaction_date_sql()
    deposits = conn.execute(
        f"""SELECT COALESCE(SUM(amount),0) AS total FROM transactions WHERE workspace_id=%s
            AND LOWER(BTRIM(COALESCE(transaction_type,'')))='income' AND LOWER(BTRIM(COALESCE(category,'')))='salario'
            AND {transaction_date} >= %s AND {transaction_date} < %s""", (workspace_id, start, end)).fetchone()["total"]
    # Only salary rows are what the rule replaces: a "Bono" or "Otros ingresos" typed in the app is
    # also kept in ``salaries`` and adds to the period on top of the salary.
    declared = conn.execute(SALARY_ROWS_SQL, (workspace_id, start, end)).fetchone()["total"] if "salaries" in tables else 0
    received = _decimal(deposits) + _decimal(declared)
    if not (inputs["profile"] or inputs["base_net"] > 0) or (not is_open and received > 0):
        return {"salary": received, "received": received, "estimated": False, "closed_estimated": False}
    events = (_rows(conn, """SELECT amount FROM payroll_events WHERE workspace_id=%s
                AND (created_at - interval '6 hours')::date >= %s AND (created_at - interval '6 hours')::date < %s""",
                    (workspace_id, start, end)) if "payroll_events" in tables else [])
    bonuses = (_rows(conn, """SELECT amount FROM bonuses WHERE workspace_id=%s
                AND (created_at - interval '6 hours')::date >= %s AND (created_at - interval '6 hours')::date < %s""",
                     (workspace_id, start, end)) if "bonuses" in tables else [])
    projected = salary_projection.project(dict(inputs["profile"]) if inputs["profile"] else None, inputs["deductions"], events, bonuses, inputs["base_net"])
    return {"salary": _decimal(projected["results"]["projected_net"]), "received": received, "estimated": True, "closed_estimated": not is_open}


def owner_salary(conn, workspace_id: str, start: date, end: date, tables: set[str] | None = None) -> dict:
    """The salary of ``[start, end)`` by the salary rule, month by month: ``salary`` (what counts),
    ``received`` (deposits and ``salaries`` rows it replaces), ``estimated`` (any month projected)
    and ``closed_estimated`` (a closed month projected). SELECT only."""
    tables = _existing_tables(conn) if tables is None else tables
    current = costa_rica_today().replace(day=1)
    inputs = _salary_inputs(conn, workspace_id, tables)
    result = {"salary": Decimal("0"), "received": Decimal("0"), "estimated": False, "closed_estimated": False}
    for month in _months(start, end):
        if month > current:
            # A future month holds what was already received, never a projection.
            month_salary = _period_salary(conn, workspace_id, month, _next_month(month), {**inputs, "profile": None, "base_net": 0}, tables, is_open=False)
        else:
            month_salary = _period_salary(conn, workspace_id, month, _next_month(month), inputs, tables, is_open=month == current)
        result["salary"] += month_salary["salary"]
        result["received"] += month_salary["received"]
        result["estimated"] = result["estimated"] or month_salary["estimated"]
        result["closed_estimated"] = result["closed_estimated"] or month_salary["closed_estimated"]
    return result


# The note the daily debt schedule writes on each installment it posts (finance.service.apply_due_installments).
_SCHEDULED_INSTALLMENT = re.compile(r"debt_id:\d+;installment:\d+")


def is_automatic_installment(row: dict) -> bool:
    """A movement the daily debt schedule posted by itself (not one the Owner recorded)."""
    return row.get("origin") == "transaction" and bool(_SCHEDULED_INSTALLMENT.fullmatch(str(row.get("notes") or "")))


def salary_estimate_rows(conn, workspace_id: str, rows: list[dict]) -> list[dict]:
    """Movimientos' rows for the salary the app knows but no deposit shows yet: the month in course, and
    a closed month without a deposit. What the salary rule counts (base and extra hours, net) minus the
    deposits already listed, so the month's income adds up to the same in every screen; the extra hours
    stay listed apart and count as accrued, not as income. Read-only rows: nothing is stored and they
    can't be edited. SELECT only."""
    tables = _existing_tables(conn)
    current = costa_rica_today().replace(day=1)
    inputs = _salary_inputs(conn, workspace_id, tables)
    months = {current}
    for row in rows:
        day = str(row.get("transaction_date") or "")[:7]
        if len(day) == 7:
            months.add(date.fromisoformat(f"{day}-01"))
    estimates = []
    for month in sorted(item for item in months if item <= current):
        salary = _period_salary(conn, workspace_id, month, _next_month(month), inputs, tables, is_open=month == current)
        if not salary["estimated"]:
            continue
        prefix = month.isoformat()[:7]
        amount = salary["salary"] - salary["received"]
        if amount <= 0:
            continue
        estimates.append({
            "movement_id": f"salary_estimate:{prefix}", "source_id": None, "origin": "salary_estimate",
            "transaction_date": month, "description": "Salario del mes (estimado)", "amount": amount,
            "transaction_type": "income", "ledger_type": "income", "category": "Salario", "notes": "",
            "editable": False, "original_amount": None, "original_currency": None, "exchange_rate": None,
            "financial_account_id": None,
        })
    return estimates


def classify_movement(row: dict) -> dict:
    """A Movimientos row with its real kind and the concept it counts in (Owner list)."""
    kind = normalized_type(row.get("ledger_type") or row.get("transaction_type"))
    return {**row, "movement_kind": kind or None, "counts_in": concept_of(kind)}
