"""DINCR Users income-source precedence (deterministic, shared by Home and VIP Strategy).

Sources, per account/workspace only:
- declared income: financial_profiles (fixed salary, or hourly x hours x days);
- recurring income items (finva_recurring_items, item_type='income');
- recorded income: salaries, positive payroll events and transactions of type
  'income' (internal transfers are never income; reconciled duplicates never
  become transactions);
- imported income: the part of recorded income from bank-email imports
  (transactions.source finva_gmail / finva_statement).

Policy v1:
1. A declared income is the monthly baseline. Bank-email imports never lower or
   raise it: email history is incomplete by nature (partial scan window,
   pagination, banks that don't email every deposit, unsupported senders).
2. Income the user records manually may lower it (conservative cap):
   baseline = min(declared, average of the last 3 months with recorded income,
   imports excluded).
3. Without a declared income, all recorded income, imports included, is the
   only evidence: baseline = average of the last 3 months with income.
4. Recurring income items are added on top of the baseline.
5. Declared and recorded income are never added together (no double counting).
Reports and history always show every recorded movement; only the planning
baseline follows this policy.
"""
from __future__ import annotations

from datetime import date
from statistics import pstdev
from typing import Any

IMPORTED_SOURCES = ("finva_gmail", "finva_statement")
POLICY_VERSION = "income-policy-v1"
_RECURRING_FACTORS = {"weekly": 52 / 12, "biweekly": 26 / 12, "monthly": 1, "quarterly": 1 / 3, "annual": 1 / 12}


def _money(value: Any) -> float:
    return round(float(value or 0), 2)


def declared_monthly_income(profile: dict | None) -> float:
    profile = profile or {}
    if profile.get("income_type") == "fixed":
        return _money(profile.get("fixed_monthly_salary"))
    return round(_money(profile.get("hourly_rate")) * _money(profile.get("hours_per_day"))
                 * _money(profile.get("work_days_per_week")) * 52 / 12, 2)


def recurring_monthly_income(recurring: list[dict]) -> float:
    return round(sum(
        round(_money(row.get("amount")) * _RECURRING_FACTORS.get(row.get("frequency"), 1), 2)
        for row in recurring if row.get("item_type") == "income" and row.get("is_active", True)
    ), 2)


def imported_income_by_month(conn, workspace_id: str, since: date) -> dict[str, float]:
    rows = conn.execute(
        f"""SELECT to_char(transaction_date::date,'YYYY-MM') AS month,SUM(amount) AS total
           FROM transactions
           WHERE workspace_id=%s AND transaction_type='income'
             AND source IN ({",".join(["%s"] * len(IMPORTED_SOURCES))})
             AND transaction_date::date >= %s
           GROUP BY 1""",
        (workspace_id, *IMPORTED_SOURCES, since),
    ).fetchall()
    return {row["month"]: _money(row["total"]) for row in rows}


def income_baseline(
    profile: dict | None, months: list[dict], imported_income: dict[str, float], recurring: list[dict] | None = None,
) -> dict[str, Any]:
    """Apply the policy to already loaded, workspace-scoped inputs.

    months: [{"month": "YYYY-MM", "income": recorded income}], oldest first.
    """
    declared = declared_monthly_income(profile)
    observed = [
        round(_money(row["income"]) - (imported_income.get(row["month"], 0) if declared > 0 else 0), 2)
        for row in months
    ]
    positive = [value for value in observed if value > 0]
    recent = positive[-3:]
    average = sum(recent) / len(recent) if recent else None
    if declared > 0:
        baseline = min(declared, average) if average is not None else declared
        source = "declared_capped_by_recorded" if average is not None and average < declared else "declared"
    else:
        baseline = average or 0.0
        source = "recorded" if average else "none"
    window = positive[-6:]
    variability = round(pstdev(window) / (sum(window) / len(window)) * 100, 1) if len(window) > 1 and sum(window) else 0
    recurring_income = recurring_monthly_income(recurring or [])
    return {
        "policy": POLICY_VERSION,
        "declared": declared,
        "baseline": round(baseline, 2),
        "recurring": recurring_income,
        "monthly_income": round(baseline + recurring_income, 2),
        "source": source,
        "observed_incomes": positive,
        "variability_percent": variability,
    }


def load_income_baseline(conn, *, account_id: str, workspace_id: str, today: date | None = None) -> dict[str, Any]:
    """Load the inputs for one account/workspace and apply the policy (same window as Home)."""
    from backend.user_product.basic_service import _basic_tables_ready, _ledger_totals, _next_month, _profile, _shift_month

    current = (today or date.today()).replace(day=1)
    months = []
    for offset in range(-11, 1):
        start = _shift_month(current, offset)
        months.append({"month": start.strftime("%Y-%m"), **_ledger_totals(conn, workspace_id, start, _next_month(start))})
    # No recurring items exist until the Basic migration creates their table.
    recurring = [dict(row) for row in conn.execute(
        "SELECT amount,frequency,item_type,is_active FROM finva_recurring_items WHERE workspace_id=%s AND is_active=TRUE",
        (workspace_id,),
    ).fetchall()] if _basic_tables_ready(conn) else []
    return income_baseline(
        _profile(conn, account_id, workspace_id), months,
        imported_income_by_month(conn, workspace_id, _shift_month(current, -11)), recurring,
    )
