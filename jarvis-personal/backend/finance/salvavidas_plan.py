"""Salvavidas automatic contributions (VIP and the Owner) and the Owner's earned interest.

The user tells DINCR that a fixed amount goes into the Salvavidas on a schedule (for example a
bank's automatic transfer every Thursday). The Salvavidas balance then grows by itself:

- the declared balance stays what the user last declared (``base_amount`` on ``base_date``);
- every scheduled date after ``base_date``, from ``start_date`` up to today (and not after an
  ``end_date``), adds ``amount``: ``contributions_amount`` = count x amount;
- the Owner may also give the annual interest rate the savings earn: simple daily interest on
  the declared balance since ``base_date`` and on each contribution since its date (an
  estimate; the bank credits the real interest).

This is derived when the screen is read; nothing is written by a read, so opening the screen
never changes a balance. Declaring a new balance (the real one, from the bank) moves
``base_date`` to that day and the count starts again from there, so a contribution is never
counted twice. Deterministic: the same plan, balance and day give the same numbers.
"""
from __future__ import annotations

import calendar
import math
from datetime import date, timedelta
from typing import Any

from backend.core.i18n import tx

FREQUENCIES = ("weekly", "biweekly", "monthly")
MAX_CONTRIBUTION = 999_999_999.99
MAX_INTEREST_RATE = 50.0  # % per year; a savings rate above this is a typo
# Enough for decades of weekly contributions; stops a corrupt plan from looping forever.
MAX_SCHEDULED = 5000


def _day(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def normalize_plan(raw: Any) -> dict[str, Any] | None:
    """The stored plan if it is complete and valid, else None (treated as no plan)."""
    if not isinstance(raw, dict):
        return None
    amount = _number(raw.get("amount"))
    start = _day(raw.get("start_date"))
    frequency = str(raw.get("frequency") or "")
    if amount is None or amount <= 0 or start is None or frequency not in FREQUENCIES:
        return None
    end = _day(raw.get("end_date"))
    return {
        "enabled": bool(raw.get("enabled")),
        "amount": round(amount, 2),
        "frequency": frequency,
        "start_date": start.isoformat(),
        "end_date": end.isoformat() if end and end >= start else None,
    }


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _monthly_on(start: date, months: int) -> date:
    year, month = divmod(start.month - 1 + months, 12)
    year, month = start.year + year, month + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def scheduled_dates(plan: dict[str, Any], after: date, until: date) -> list[date]:
    """Contribution dates d with ``after < d <= until`` (and within the plan's start/end)."""
    start = _day(plan["start_date"])
    end = _day(plan.get("end_date")) or until
    last = min(until, end)
    dates: list[date] = []
    for index in range(MAX_SCHEDULED):
        if plan["frequency"] == "monthly":
            day = _monthly_on(start, index)
        else:
            day = start + timedelta(days=index * (7 if plan["frequency"] == "weekly" else 14))
        if day > last:
            break
        if day > after:
            dates.append(day)
    return dates


def next_date(plan: dict[str, Any], today: date) -> date | None:
    upcoming = scheduled_dates(plan, today, date(today.year + 2, today.month, 1))
    return upcoming[0] if upcoming else None


def progress(plan: dict[str, Any] | None, *, base_amount: float, base_date: date, today: date,
             annual_interest_rate: float | None) -> dict[str, Any] | None:
    """What the plan added to the declared balance by ``today`` (None without an active plan)."""
    if not plan or not plan["enabled"]:
        return None
    dates = scheduled_dates(plan, base_date, today)
    contributions = round(len(dates) * plan["amount"], 2)
    interest = 0.0
    rate = (annual_interest_rate or 0.0) / 100.0
    if rate > 0:
        interest = base_amount * rate * max((today - base_date).days, 0) / 365.0
        interest += sum(plan["amount"] * rate * (today - day).days / 365.0 for day in dates)
    upcoming = next_date(plan, today)
    return {
        **plan,
        "base_amount": round(base_amount, 2),
        "base_date": base_date.isoformat(),
        "contributions_count": len(dates),
        "contributions_amount": contributions,
        "estimated_interest": round(interest, 2),
        "next_date": upcoming.isoformat() if upcoming else None,
        "total": round(base_amount + contributions + interest, 2),
    }


def validated_plan(raw: Any) -> dict[str, Any]:
    """A plan sent by the app, checked; ValueError (Spanish/English message) when invalid."""
    if not isinstance(raw, dict):
        raise ValueError(tx("Los aportes automáticos no son válidos.", "The automatic contributions are not valid."))
    enabled = bool(raw.get("enabled"))
    amount = _number(raw.get("amount"))
    if amount is None or amount <= 0 or amount > MAX_CONTRIBUTION:
        raise ValueError(tx("Indicá un monto de aporte mayor que cero.", "Enter a contribution above zero."))
    frequency = str(raw.get("frequency") or "")
    if frequency not in FREQUENCIES:
        raise ValueError(tx("La frecuencia debe ser semanal, quincenal o mensual.",
                            "The frequency must be weekly, every two weeks or monthly."))
    start = _day(raw.get("start_date"))
    if start is None:
        raise ValueError(tx("Indicá la fecha del primer aporte.", "Enter the date of the first contribution."))
    end = _day(raw.get("end_date")) if raw.get("end_date") else None
    if raw.get("end_date") and (end is None or end < start):
        raise ValueError(tx("La fecha final debe ser después del primer aporte.",
                            "The end date must be after the first contribution."))
    return {"enabled": enabled, "amount": round(amount, 2), "frequency": frequency,
            "start_date": start.isoformat(), "end_date": end.isoformat() if end else None}


def validated_interest_rate(value: Any) -> float:
    rate = _number(value)
    if rate is None or rate < 0 or rate > MAX_INTEREST_RATE:
        raise ValueError(tx("Indicá una tasa de interés anual entre 0 % y 50 %.",
                            "Enter an annual interest rate between 0% and 50%."))
    return round(rate, 4)
