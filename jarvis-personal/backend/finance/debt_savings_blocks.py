"""Locked savings blocks for the Owner's long debts ("ahorro bloqueado para deudas"), as pure arithmetic.

The Owner saves every payday (Thursday) into a bank savings that cannot be touched for the block's
term (the bank's minimum is 3 months). When the block matures, everything saved is paid into one
debt at once. The point is discipline: the money never sits where it can be spent.

Rules (decided by the Owner, 2026-11-01):

- The debt is the strategy's, never picked by hand: the Owner's payoff order (strategy_dashboard).
- The weekly amount is safe money only: the strategy's monthly debt attack from the base net salary
  (no overtime, bonus or VGH), after debts, fixed expenses and the automatic savings already set up,
  turned into a weekly amount and rounded down.
- A debt the strategy pays off within ``MIN_TERM_MONTHS`` is short: it keeps being paid as today,
  and meanwhile ``PRESAVE_SHARE`` of the weekly amount is saved for the next long debt.
- The term is computed so the block matures BEFORE the debt would be paid anyway. The payoff uses
  the probable income (the last months with overtime and bonus), so the money is never left
  waiting in a locked account after the debt is gone; a block that would save more than the debt
  will owe is shortened or made smaller.
- The savings' own interest is never counted: if it comes, it is a bonus.
- What locking costs against paying the same money every week straight into the debt (the
  debt's interest on the money while it waits) is shown, never hidden.

Deterministic and read-only: the same inputs and day give the same proposal; nothing is stored.
"""
from __future__ import annotations

import calendar
import math
from datetime import date, timedelta
from typing import Any

MIN_TERM_MONTHS = 3        # the bank's minimum lock
DEFAULT_TERM_MONTHS = 6    # a block for a long debt
PRESAVE_SHARE = 0.25       # of the weekly amount while short debts are paid first
STEP = 500.0               # weekly amounts are whole multiples of ₡500, rounded down
PAYDAY = 3                 # Thursday (date.weekday())
WEEKS_PER_MONTH = 52 / 12


def _f(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def weekly_amount(monthly: float) -> float:
    """A monthly amount as a weekly contribution, rounded down to ``STEP`` (never negative)."""
    return math.floor(max(_f(monthly), 0.0) / WEEKS_PER_MONTH / STEP) * STEP


def next_payday(today: date) -> date:
    """Today when it is Thursday, else the next Thursday."""
    return today + timedelta(days=(PAYDAY - today.weekday()) % 7)


def add_months(day: date, months: int) -> date:
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return day.replace(year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1]))


def contribution_dates(start: date, maturity: date) -> list[date]:
    """Every payday from ``start`` (a Thursday) up to the day before ``maturity``."""
    return [start + timedelta(days=7 * week) for week in range(((maturity - start).days + 6) // 7)
            if start + timedelta(days=7 * week) < maturity]


def balance_after(balance: float, annual_rate: float | None, monthly_payment: float, months: int) -> float:
    """The debt's balance after ``months`` of interest and payments. An unknown rate counts no
    interest: the balance falls faster, so a block is never sized above what will be owed."""
    rate = max(_f(annual_rate), 0.0) / 1200
    for _ in range(months):
        balance = max(balance * (1 + rate) - monthly_payment, 0.0)
    return round(balance, 2)


def lock_cost(weekly: float, dates: list[date], maturity: date, annual_rate: float | None) -> float | None:
    """The debt's interest on each contribution while it waits in the block (None: unknown rate)."""
    if annual_rate is None or _f(annual_rate) <= 0:
        return None if annual_rate is None else 0.0
    daily = _f(annual_rate) / 100 / 365
    return round(sum(weekly * daily * (maturity - day).days for day in dates), 2)


def _debt(item: dict[str, Any]) -> dict[str, Any]:
    rate = item.get("interest_rate")
    return {"id": item.get("id"), "name": item.get("name"), "remaining_amount": round(_f(item.get("remaining_amount")), 2),
            "interest_rate": None if rate is None else _f(rate)}


def _is_short(item: dict[str, Any]) -> bool:
    months = item.get("payoff_month")
    return months is not None and 0 < int(months) <= MIN_TERM_MONTHS


def _block(target: dict[str, Any], weekly: float, max_term: int, direct_monthly: float, today: date) -> dict[str, Any] | None:
    """The longest term (``max_term`` down to the minimum) whose savings do not exceed what the debt
    will owe at maturity; at the minimum term a smaller weekly amount that fits. None: nothing fits."""
    start = next_payday(today)
    balance, rate = _f(target.get("remaining_amount")), target.get("interest_rate")
    monthly_payment = _f(target.get("minimum_payment")) + max(direct_monthly, 0.0)
    for term in range(max_term, MIN_TERM_MONTHS - 1, -1):
        maturity = add_months(start, term)
        dates = contribution_dates(start, maturity)
        owed = balance_after(balance, None if rate is None else _f(rate), monthly_payment, term)
        amount = weekly
        if term == MIN_TERM_MONTHS and amount * len(dates) > owed:
            amount = math.floor(owed / len(dates) / STEP) * STEP if dates else 0.0
        if amount >= STEP and amount * len(dates) <= owed:
            saved = round(amount * len(dates), 2)
            return {"weekly_amount": amount, "contributions": len(dates), "term_months": term,
                    "start_date": start.isoformat(), "maturity_date": maturity.isoformat(), "total_saved": saved,
                    "abono_amount": saved, "balance_at_maturity": owed, "balance_after_abono": round(owed - saved, 2),
                    "lock_cost": lock_cost(amount, dates, maturity, None if rate is None else _f(rate))}
    return None


def _recommendation(rate: float | None) -> dict[str, str]:
    """Banks decide whether an extra payment lowers the term or the installment; both work (a
    lower installment is added to the next block). Lowering the term saves the most interest."""
    if rate is not None and _f(rate) > 0:
        return {"choice": "reduce_term", "reason": "saves_interest"}
    return {"choice": "reduce_term", "reason": "finishes_sooner"}


def propose(*, today: date, safe_monthly_attack: float, probable_monthly_attack: float,
            debts: list[dict[str, Any]], warnings: list[str] | None = None) -> dict[str, Any]:
    """The next block, or why there is none.

    ``debts``: the active debts in the strategy's payoff order, each with ``remaining_amount``,
    ``interest_rate`` (None: unknown), ``minimum_payment`` and ``payoff_month`` (the probable
    payoff month; None: not within the plan).
    """
    safe = max(_f(safe_monthly_attack), 0.0)
    probable = max(_f(probable_monthly_attack), safe)
    base = {"safe_monthly_attack": round(safe, 2), "probable_monthly_attack": round(probable, 2),
            "weekly_safe_amount": weekly_amount(safe), "savings_interest_counted": False,
            "min_term_months": MIN_TERM_MONTHS, "presave_share": PRESAVE_SHARE,
            "warnings": list(warnings or []), "proposal": None}
    active = [item for item in debts if _f(item.get("remaining_amount")) > 0.01]
    if not active:
        return {**base, "status": "no_debts"}
    if base["weekly_safe_amount"] < STEP:
        return {**base, "status": "no_surplus"}

    shorts = []
    for item in active:
        if not _is_short(item):
            break
        shorts.append(item)
    target = active[len(shorts)] if len(shorts) < len(active) else None
    short_view = [{**_debt(item), "payoff_month": int(item["payoff_month"])} for item in shorts]
    if target is None:
        return {**base, "status": "short_debts_only", "short_debts": short_view}

    if shorts:
        mode, weekly = "presave", math.floor(base["weekly_safe_amount"] * PRESAVE_SHARE / STEP) * STEP
        max_term = MIN_TERM_MONTHS
        direct = 0.0   # the rest of the attack goes to the short debts, not to this one
    else:
        mode, weekly = "block", base["weekly_safe_amount"]
        months = target.get("payoff_month")
        max_term = DEFAULT_TERM_MONTHS if months is None else min(DEFAULT_TERM_MONTHS, int(months) - 1)
        direct = probable - weekly * WEEKS_PER_MONTH   # overtime and bonus still go straight to the debt
    if weekly < STEP:
        return {**base, "status": "no_surplus", "short_debts": short_view}

    block = _block(target, weekly, max(max_term, MIN_TERM_MONTHS), direct, today)
    if block is None:
        return {**base, "status": "pay_directly", "short_debts": short_view, "debt": _debt(target)}
    rate = target.get("interest_rate")
    return {**base, "status": "proposal", "short_debts": short_view,
            "proposal": {"mode": mode, "debt": _debt(target), **block,
                         "recommendation": _recommendation(None if rate is None else _f(rate))}}
