"""AG-1 — what to do with the aguinaldo before it arrives: a simple, fixed split (no AI, no advice
beyond the rule), from the Owner's own Salvavidas and debts.

The aguinaldo is a once-a-year windfall: it never becomes monthly income. The split follows the
windfall order (dincr-finance → savings-liquidity §13–14), in this order:

1. December: a share for the season (gifts, marchamo, the month's extra spending) — 15 % when
   there is high-cost debt, else 20 %. Enjoying part of it is legitimate.
2. Salvavidas to one month of obligations, if it is below that.
3. High-cost debt (a known annual rate of 20 % or more), the highest rate first, never more than
   what is owed.
4. The rest: the Salvavidas up to three months, then goals or savings.

Unknown is never zero: a debt without a known rate is not targeted (and is named), an unknown
Salvavidas balance is not filled blindly, and without an amount there is no plan. Pure: no database.
"""
from __future__ import annotations

from typing import Any

HIGH_COST_RATE = 20.0


def _f(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def build(amount: Any, salvavidas: dict[str, Any] | None, debts: list[dict[str, Any]]) -> dict[str, Any] | None:
    total = _f(amount)
    if not total or total <= 0:
        return None
    left = round(total, 2)
    items: list[dict[str, Any]] = []

    def take(key: str, label: str, wanted: float, reason: str) -> None:
        nonlocal left
        value = round(min(max(wanted, 0.0), left), 2)
        if value > 0:
            items.append({"key": key, "label": label, "amount": value, "reason": reason})
            left = round(left - value, 2)

    active = [d for d in debts if (_f(d.get("remaining_amount")) or 0) > 0.01]
    costly = sorted((d for d in active if (_f(d.get("interest_rate")) or -1) >= HIGH_COST_RATE),
                    key=lambda d: _f(d.get("interest_rate")) or 0, reverse=True)
    take("december", "Diciembre", total * (0.15 if costly else 0.20),
         "Regalos, marchamo y los gastos extra de fin de año, sin usar la tarjeta.")

    current = _f((salvavidas or {}).get("current_amount"))
    base = _f((salvavidas or {}).get("monthly_base")) or 0.0
    if current is not None and base > 0 and current < base:
        take("salvavidas", "Salvavidas", base - current, "Que tu Salvavidas cubra al menos un mes de obligaciones.")

    for debt in costly:
        take(f"debt-{debt.get('id')}", str(debt.get("name") or "Deuda"), _f(debt.get("remaining_amount")) or 0,
             f"Es tu deuda más cara ({_f(debt.get('interest_rate')):g} % al año): abonarle es lo que más intereses te ahorra.")

    if left > 0:
        reserve = ([i for i in items if i["key"] == "salvavidas"] or [None])[0]
        already = (current or 0) + (reserve["amount"] if reserve else 0)
        if current is not None and base > 0 and already < base * 3:
            extra = min(left, base * 3 - already)
            if reserve:
                reserve["amount"] = round(reserve["amount"] + extra, 2)
                left = round(left - extra, 2)
            else:
                take("salvavidas", "Salvavidas", extra, "Acercar tu Salvavidas a tres meses de obligaciones.")
    take("goals", "Metas o ahorro", left, "Lo que queda: tus metas o tu ahorro.")

    unknown = [str(d.get("name") or "Deuda") for d in active if _f(d.get("interest_rate")) is None]
    return {"amount": round(total, 2), "items": items, "unknown_rates": unknown}
