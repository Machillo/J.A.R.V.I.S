"""Debt monthly payments: known vs unknown (UNKNOWN ≠ 0).

`debts.monthly_payment` is NOT NULL, and create_user_debt / update_user_debt stored "no payment
given" as 0. `debts.monthly_payment_known` (migration 20261010120000) records whether DINCR knows
the payment:
- `monthly_payment_known` FALSE → unknown. The stored 0 is a placeholder, never a payment;
- `monthly_payment_known` TRUE → the stored payment is known (0 is a real 0);
- historical rows (`monthly_payment_known` NULL, written before the column existed, and every row
  the Owner's own finance paths write) are read exactly as before: the stored value. Telling a
  historical "no payment given" 0 from a real 0 is a later, separate decision; no row is
  reinterpreted or rewritten here.

Only the Users read paths (the debts list, the Basic strategy, the VIP command center and the VIP
strategy dashboard) apply this. The Owner's finance engines read the table as before.
"""
from __future__ import annotations

from typing import Any

# The same rule in SQL (`monthly_payment_known` may be absent from older selects: always select it).
UNKNOWN_PAYMENT_SQL = "(monthly_payment IS NULL OR monthly_payment_known IS FALSE)"


def known_monthly_payment(debt: dict[str, Any]) -> float | None:
    """The debt's monthly payment when DINCR knows it, else None (never 0 for "unknown")."""
    value = debt.get("monthly_payment")
    if value is None or debt.get("monthly_payment_known") is False:
        return None
    return float(value)


def with_known_payments(debts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The rows with `monthly_payment` replaced by the known payment (None when unknown) and
    `monthly_payment_known` by whether DINCR knows it."""
    rows = []
    for debt in debts:
        payment = known_monthly_payment(debt)
        rows.append({**debt, "monthly_payment": payment, "monthly_payment_known": payment is not None})
    return rows


def payment_for_create(payment: float | None) -> tuple[float, bool]:
    """A new debt: no payment given → unknown (0 placeholder, FALSE); any given payment, 0 included,
    is known. The column stays NOT NULL, so the Owner's engines never read a NULL."""
    return (0.0, False) if payment is None else (float(payment), True)


def payment_for_update(stored: dict[str, Any], payment: float | None) -> tuple[float, bool | None]:
    """The (monthly_payment, monthly_payment_known) to store when a debt is edited.

    Clearing a known payment makes it unknown. An unknown payment sent back empty stays as stored.
    A 0 sent for an unknown payment is not evidence: older clients turn an empty field into 0
    (Number(null) is 0), so it stays unknown. Any other given payment becomes known.
    """
    stored_value, stored_known = stored.get("monthly_payment"), stored.get("monthly_payment_known")
    stored_unknown = known_monthly_payment(stored) is None
    if payment is None:
        if stored_unknown:
            return float(stored_value or 0), stored_known
        return 0.0, False
    payment = float(payment)
    if stored_unknown and payment == 0:
        return float(stored_value or 0), stored_known
    return payment, True
