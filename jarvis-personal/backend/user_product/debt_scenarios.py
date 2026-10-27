"""Debt what-if scenarios (VIP): pay a debt off, make an extra payment, or take a new debt.

Every scenario answers one question: how much money is left each month after essential expenses
and debt payments (the strategy's margin, `build_basic_strategy`). It reads the caller's own
snapshot, never writes, and returns the same numbers for the same inputs in any language.

Missing data is never zero: with no estimable income the month is unknown; a debt without a
monthly payment or interest rate leaves what depends on it unknown, with a warning.

An extra payment shows both lender policies, because the lender decides: a lower installment
(same remaining term; frees money every month) or a shorter term (same installment; saves more
interest).
"""
from __future__ import annotations

from typing import Any, Literal

from backend.core.i18n import tx
from backend.user_product.strategy_engine import _money, build_basic_strategy

RULE_VERSION = "debt-scenarios-v1"
MAX_MONTHS = 1200
Kind = Literal["pay_off", "extra_payment", "new_debt"]


class DebtScenarioError(ValueError):
    """An input the scenario cannot use; `code` is stable for clients."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _known(value: Any) -> float | None:
    return None if value is None else _money(value)


def monthly_leftover(snapshot: dict) -> float | None:
    """Income minus essentials minus debt payments; None while the income is unknown."""
    strategy = build_basic_strategy(snapshot)
    if strategy["status"] == "needs_income":
        return None
    return round(float(strategy["strategic_margin"]), 2)


def amortized_payment(principal: float, annual_rate: float | None, months: int | None) -> float | None:
    """The fixed payment that repays `principal` in `months` at `annual_rate` (% a year)."""
    if annual_rate is None or not months or months <= 0:
        return None
    principal = _money(principal)
    if annual_rate <= 0:
        return round(principal / months, 2)
    rate = float(annual_rate) / 100 / 12
    return round(principal * rate / (1 - (1 + rate) ** -months), 2)


def schedule(balance: float, payment: float | None, annual_rate: float | None) -> tuple[int, float] | None:
    """Months and total interest to repay `balance` with a fixed `payment`. None when the payment
    or the rate is unknown, or the payment never repays the debt."""
    if payment is None or annual_rate is None:
        return None
    balance, payment = _money(balance), _money(payment)
    if balance <= 0:
        return 0, 0.0
    if payment <= 0:
        return None
    rate = float(annual_rate) / 100 / 12
    remaining, interest_total = balance, 0.0
    for month in range(1, MAX_MONTHS + 1):
        interest = remaining * rate
        if rate > 0 and payment <= interest:
            return None
        interest_total += interest
        remaining = remaining + interest - payment
        if remaining <= 0.01:
            return month, round(interest_total, 2)
    return None


def _change(current: float | None, delta: float | None) -> dict:
    if current is None or delta is None:
        return {"current": current, "scenario": None, "change": None}
    return {"current": current, "scenario": round(current + delta, 2), "change": round(delta, 2)}


def _savings_after(snapshot: dict, amount: float) -> float | None:
    savings = _known(snapshot.get("liquid_savings"))
    return None if savings is None else round(savings - amount, 2)


def _debt_view(debt: dict) -> dict:
    return {key: debt.get(key) for key in ("id", "name", "remaining_amount", "monthly_payment", "interest_rate", "debt_type")}


def _find_debt(snapshot: dict, debt_id: int | None) -> dict:
    if debt_id is None:
        raise DebtScenarioError("debt_required", tx("Elegí una de tus deudas.", "Choose one of your debts."))
    for debt in snapshot.get("debts", []):
        if debt.get("id") == debt_id and _money(debt.get("remaining_amount")) > 0:
            return debt
    raise DebtScenarioError("debt_not_found", tx("No encontramos esa deuda.", "We couldn’t find that debt."))


def _missing_warnings(payment: float | None, rate: float | None) -> list[str]:
    warnings = []
    if payment is None:
        warnings.append(tx("Esta deuda no tiene cuota mensual; DINCR no la inventó.", "This debt has no monthly payment; DINCR didn’t make it up."))
    if rate is None:
        warnings.append(tx("Esta deuda no tiene tasa de interés conocida; lo que depende de ella queda sin calcular.",
                           "This debt has no known interest rate; what depends on it is not calculated."))
    return warnings


def build_debt_scenario(snapshot: dict, kind: Kind, *, debt_id: int | None = None, amount: float | None = None,
                        monthly_payment: float | None = None, annual_rate: float | None = None,
                        term_months: int | None = None, name: str | None = None) -> dict:
    current = monthly_leftover(snapshot)
    base_warnings = list(build_basic_strategy(snapshot).get("warnings", []))
    result: dict[str, Any] = {"rule_version": RULE_VERSION, "kind": kind, "options": None, "payoff": None}

    if kind == "pay_off":
        debt = _find_debt(snapshot, debt_id)
        balance, payment, rate = _money(debt["remaining_amount"]), _known(debt.get("monthly_payment")), _known(debt.get("interest_rate"))
        left = schedule(balance, payment, rate)
        result.update(
            debt=_debt_view(debt), monthly_leftover=_change(current, payment), one_time_amount=balance,
            liquid_savings_after=_savings_after(snapshot, balance),
            payoff={"months": left[0] if left else None, "interest": left[1] if left else None},
            warnings=base_warnings + _missing_warnings(payment, rate),
            explanation=tx(f"Si pagás {debt['name']} completa, esa cuota queda libre cada mes.",
                           f"If you pay {debt['name']} off, that payment is free every month."),
        )
        return result

    if kind == "extra_payment":
        debt = _find_debt(snapshot, debt_id)
        if amount is None or _money(amount) <= 0:
            raise DebtScenarioError("amount_required", tx("Indicá cuánto querés abonar.", "Enter how much you want to pay."))
        balance, payment, rate = _money(debt["remaining_amount"]), _known(debt.get("monthly_payment")), _known(debt.get("interest_rate"))
        amount = _money(amount)
        if amount >= balance:
            raise DebtScenarioError("covers_debt", tx("Ese abono cubre toda la deuda: probá el escenario de pagarla.",
                                                      "That payment covers the whole debt: try the pay-off scenario."))
        remaining = round(balance - amount, 2)
        now, after = schedule(balance, payment, rate), schedule(remaining, payment, rate)
        new_payment = amortized_payment(remaining, rate, now[0]) if now else None
        lower_delta = None if new_payment is None or payment is None else payment - new_payment
        result.update(
            debt=_debt_view(debt), monthly_leftover={"current": current, "scenario": None, "change": None},
            one_time_amount=amount, liquid_savings_after=_savings_after(snapshot, amount),
            options={
                "lower_installment": {"monthly_payment": new_payment, **_lower(current, lower_delta)},
                "shorter_term": {
                    "monthly_payment": payment, "monthly_leftover": current,
                    "months_saved": now[0] - after[0] if now and after else None,
                    "interest_saved": round(now[1] - after[1], 2) if now and after else None,
                },
            },
            warnings=base_warnings + _missing_warnings(payment, rate),
            explanation=tx("Tu banco decide si el abono baja la cuota o acorta el plazo: bajar la cuota libera dinero cada mes; acortar el plazo ahorra más intereses.",
                           "Your lender decides whether the payment lowers the installment or shortens the term: a lower installment frees money every month; a shorter term saves more interest."),
        )
        return result

    if kind == "new_debt":
        if amount is None or _money(amount) <= 0:
            raise DebtScenarioError("amount_required", tx("Indicá el monto de la deuda nueva.", "Enter the new debt’s amount."))
        principal = _money(amount)
        if monthly_payment is not None and _money(monthly_payment) > 0:
            payment, source = _money(monthly_payment), "declared"
        else:
            payment, source = amortized_payment(principal, annual_rate, term_months), "computed"
            if payment is None:
                raise DebtScenarioError("payment_or_terms_required", tx("Indicá la cuota, o la tasa y el plazo, de la deuda nueva.",
                                                                        "Enter the new debt’s payment, or its rate and term."))
        left = schedule(principal, payment, annual_rate)
        label = (name or "").strip() or tx("Deuda nueva", "New debt")
        result.update(
            debt={"id": None, "name": label, "remaining_amount": principal, "monthly_payment": payment,
                  "monthly_payment_source": source, "interest_rate": annual_rate, "debt_type": None},
            monthly_leftover=_change(current, -payment), one_time_amount=None, liquid_savings_after=None,
            payoff={"months": left[0] if left else None, "interest": left[1] if left else None},
            warnings=base_warnings,
            # Amounts travel as numbers (the app formats them); the sentence carries none.
            explanation=tx(f"La cuota de {label} saldría de tu mes.", f"{label}’s payment would come out of your month."),
        )
        return result

    raise DebtScenarioError("unknown_kind", tx("Ese escenario no existe.", "That scenario doesn’t exist."))


def simulate_debt_scenario(request) -> dict:
    """POST /finance/strategy-vip/debt-scenario: the caller's own workspace snapshot (its debts only),
    read-only. A debt id from another workspace is not in the snapshot: 404, never another's debt."""
    from fastapi import HTTPException

    from backend.auth.saas import require_feature
    from backend.user_product.service import _strategy_snapshot

    require_feature("strategy_vip")
    try:
        return build_debt_scenario(
            _strategy_snapshot(), request.kind, debt_id=request.debt_id, amount=request.amount,
            monthly_payment=request.monthly_payment, annual_rate=request.annual_rate,
            term_months=request.term_months, name=request.name,
        )
    except DebtScenarioError as error:
        raise HTTPException(status_code=404 if error.code == "debt_not_found" else 422,
                            detail={"code": error.code, "message": str(error)}) from None


def _lower(current: float | None, delta: float | None) -> dict:
    view = _change(current, delta)
    return {"monthly_leftover": view["scenario"], "change": view["change"]}
