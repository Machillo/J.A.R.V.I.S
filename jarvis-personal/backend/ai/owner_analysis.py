"""The Owner's distribution as an analysis of his month, instead of a fixed table of percentages.

Everything comes from what the app already has, and nothing here reads or writes the database: the
caller gives his income, installments, fixed expenses, the living costs seen in his closed months
and his dividend plan. Deterministic arithmetic, no generative AI. Owner only: the Users' strategy
keeps its own rules and never reaches this module.

What is left to split goes, in this order:
1. Living costs still to come this cycle, as seen in his closed months (unknown: the old 15%).
2. The Salvavidas, what keeps it on course to its current stage; all of the gap without debts.
3. Debts or investing, by what each colón returns. Investing needs no debt at 10% a year or more,
   3 months of Salvavidas and a dividend above every rate; otherwise it goes to debts.

Which debt comes first (rule agreed with the Owner): while his month is negative, what relieves the
month most, the installment freed per colón plus its interest; once it is not, the highest rate.
Unknown is never 0: an unknown rate or living cost is said, and never makes a decision look safe.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.core.i18n import tx

MAX_STOCK_DEBT_APR = 10.0
STOCK_SALVAVIDAS_MONTHS = 3
FALLBACK_LIFE_SHARE = 0.15
MINI_FUND_MONTHS, STAGE_MONTHS = 6, 12
PROJECTION_LIMIT_MONTHS = 600


def _f(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


@dataclass(frozen=True)
class OwnerMonth:
    """His usual month. `lived_variable` None: no closed months to read it from."""
    income: float
    installments: float
    fixed_expenses: float
    lived_variable: float | None
    spent_this_cycle: float
    net_dividend_yield: float | None = None

    @property
    def margin(self) -> float:
        """What a usual month leaves after everything; without known living costs, before them."""
        return self.income - self.installments - self.fixed_expenses - (self.lived_variable or 0.0)


def relief_per_colon(debt: dict[str, Any]) -> float:
    """What one colón paid frees each month: its share of the installment, plus the interest."""
    balance = max(_f(debt.get("remaining_amount")), 0.01)
    return _f(debt.get("monthly_payment")) / balance + _f(debt.get("interest_rate")) / 1200


def relief_order(debts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(debts, key=lambda debt: (-relief_per_colon(debt), int(debt.get("id") or 0)))


def rate_order(debts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(debts, key=lambda debt: (-_f(debt.get("interest_rate")), int(debt.get("id") or 0)))


def project(debts: list[dict[str, Any]], order, monthly_extra: float, year_month: int = 12) -> dict[str, Any]:
    """Debts month by month: every installment is paid, what one frees and the extra go to the first in `order`."""
    balances = {debt["id"]: max(_f(debt.get("remaining_amount")), 0.0) for debt in debts}
    rates = {debt["id"]: _f(debt.get("interest_rate")) / 1200 for debt in debts}
    payments = {debt["id"]: max(_f(debt.get("monthly_payment")), 0.0) for debt in debts}
    budget = sum(payments.values()) + max(monthly_extra, 0.0)
    interest, month, after_a_year = 0.0, 0, None
    while sum(balances.values()) > 1 and month < PROJECTION_LIMIT_MONTHS:
        month += 1
        for key in balances:
            charged = balances[key] * rates[key]
            interest += charged
            balances[key] += charged
        left = budget
        for key in balances:
            paid = min(payments[key], balances[key], left)
            balances[key] -= paid
            left -= paid
        for debt in order([d for d in debts if balances[d["id"]] > 0.01]):
            if left <= 0:
                break
            paid = min(left, balances[debt["id"]])
            balances[debt["id"]] -= paid
            left -= paid
        if month == year_month:
            after_a_year = sum(payments[key] for key, balance in balances.items() if balance > 0.01)
    if sum(balances.values()) > 1:
        return {"months": None, "interest": None, "installments_after_a_year": None}
    return {"months": month, "interest": round(interest, 2),
            "installments_after_a_year": round(after_a_year or 0.0, 2)}


def decide(remaining: float, month: OwnerMonth, debts: list[dict[str, Any]], savings: float, monthly_base: float,
           target_months: int | None, mini_target: float, highest_apr: float | None) -> dict[str, Any]:
    """How `remaining` splits, why, and which debt comes first. The weights add up to 1."""
    has_debt = any(_f(debt.get("remaining_amount")) > 1 for debt in debts)
    if month.lived_variable is None:
        life = remaining * FALLBACK_LIFE_SHARE
    else:
        life = min(max(month.lived_variable - month.spent_this_cycle, 0.0), remaining)
    after_life = remaining - life

    stage_target = monthly_base * (target_months or 1)
    if not has_debt:
        keep_on_course = stage_target - savings
    elif savings < mini_target:
        keep_on_course = (mini_target - savings) / MINI_FUND_MONTHS
    else:
        keep_on_course = (stage_target - savings) / STAGE_MONTHS
    emergency = min(max(keep_on_course, 0.0), after_life)
    rest = after_life - emergency

    # A debt without a known rate leaves `highest_apr` None: it never reads as cheap.
    cheap_debt_only = highest_apr is not None and highest_apr < MAX_STOCK_DEBT_APR
    safe_enough = monthly_base > 0 and savings >= monthly_base * STOCK_SALVAVIDAS_MONTHS
    investing_beats_debt = month.net_dividend_yield is not None and highest_apr is not None and month.net_dividend_yield > highest_apr
    alongside_debt = has_debt and cheap_debt_only and safe_enough and investing_beats_debt
    without_debt = not has_debt and highest_apr is not None and savings >= monthly_base and monthly_base > 0

    debt_share = investment = 0.0
    if has_debt and not alongside_debt:
        debt_share = rest
    elif alongside_debt or without_debt:
        investment = rest
    else:
        emergency += rest

    relief_first = has_debt and month.margin < 0
    ordered = relief_order(debts) if relief_first else rate_order(debts)
    by_relief = project(debts, relief_order, max(month.margin, 0.0)) if has_debt else None
    by_rate = project(debts, rate_order, max(month.margin, 0.0)) if has_debt else None

    weight = (lambda amount: amount / remaining) if remaining > 0 else (lambda _amount: 0.0)
    return {
        "weights": {"debt": weight(debt_share), "emergency": weight(emergency), "life": weight(life), "investment": weight(investment)},
        "investment_allowed": investment > 0,
        "reason": _reason(month, relief_first, has_debt, ordered),
        "analysis": {
            "usual_income": round(month.income, 2), "installments": round(month.installments, 2),
            "fixed_expenses": round(month.fixed_expenses, 2),
            "lived_variable": None if month.lived_variable is None else round(month.lived_variable, 2),
            "lived_variable_known": month.lived_variable is not None,
            "margin": round(month.margin, 2), "order": "relief" if relief_first else "rate",
            "debt_order": [debt.get("id") for debt in ordered],
            "compared": {"relief": by_relief, "rate": by_rate} if has_debt else None,
        },
    }


def _reason(month: OwnerMonth, relief_first: bool, has_debt: bool, ordered: list[dict[str, Any]]) -> str:
    known = month.lived_variable is not None
    if not has_debt:
        return tx("Sin deudas: primero tu vida y tu Salvavidas; lo demás puede construir patrimonio.",
                  "No debts: your living costs and emergency fund first; the rest can build wealth.")
    first = str(ordered[0].get("name") or tx("tu primera deuda", "your first debt")) if ordered else ""
    if relief_first:
        return tx(f"Un mes normal tuyo no alcanza{'' if known else ' (sin contar gastos de vida, que todavía no se conocen)'}: primero lo que más alivia el mes. El siguiente colón va a {first}.",
                  f"A usual month of yours falls short{'' if known else ' (not counting living costs, still unknown)'}: what relieves the month most goes first. The next colón goes to {first}.")
    return tx(f"Tu mes alcanza{'' if known else ' (sin contar gastos de vida, que todavía no se conocen)'}: primero la tasa más alta. El siguiente colón va a {first}.",
              f"Your month covers itself{'' if known else ' (not counting living costs, still unknown)'}: the highest rate goes first. The next colón goes to {first}.")
