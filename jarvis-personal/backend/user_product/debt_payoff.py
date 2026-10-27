"""When each debt is expected to be paid off, for the debts list (Owner and Users alike).

A read-only, deterministic estimate from the debt's own row: the remaining balance, the monthly
payment and the rate DINCR knows. It never writes and never guesses: an unknown rate (UNKNOWN ≠ 0%,
see debt_rates), no payment or a payment that does not cover the interest give no estimate
(None), never a date. The months are the strategy engine's own (`_months_to_payoff`).
"""
from __future__ import annotations

import calendar
from datetime import date
from typing import Any

from backend.user_product.debt_rates import known_interest_rate
from backend.user_product.strategy_engine import _months_to_payoff


def _add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year, month = day.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _first_payment(debt: dict[str, Any], today: date) -> date:
    """The next installment still to pay: the stored next payment date when it has not passed,
    else the next payment day from today (today itself when it falls today)."""
    stored = debt.get("next_payment_date")
    if isinstance(stored, str):
        try:
            stored = date.fromisoformat(stored[:10])
        except ValueError:
            stored = None
    if isinstance(stored, date) and stored >= today:
        return stored
    payment_day = debt.get("payment_day")
    if not isinstance(payment_day, int) or not 1 <= payment_day <= 31:
        return today
    for ahead in (0, 1):
        month = _add_months(date(today.year, today.month, 1), ahead)
        due = month.replace(day=min(payment_day, calendar.monthrange(month.year, month.month)[1]))
        if due >= today:
            return due
    return today


def payoff_estimate(debt: dict[str, Any], today: date) -> dict[str, Any]:
    """`estimated_payoff_months` and `estimated_payoff_date` (ISO) for one debt row; both None
    when DINCR cannot know them. A paid debt answers 0 months and no date."""
    remaining = float(debt.get("remaining_amount") or 0)
    if remaining <= 0:
        return {"estimated_payoff_months": 0, "estimated_payoff_date": None}
    rate = known_interest_rate(debt)
    if rate is None:
        return {"estimated_payoff_months": None, "estimated_payoff_date": None}
    months = _months_to_payoff(remaining, float(debt.get("monthly_payment") or 0), rate)
    if months is None:
        return {"estimated_payoff_months": None, "estimated_payoff_date": None}
    last = _add_months(_first_payment(debt, today), months - 1)
    return {"estimated_payoff_months": months, "estimated_payoff_date": last.isoformat()}
