"""Debt interest rates: known vs unknown (UNKNOWN ≠ 0%).

`debts.interest_rate_known` (migration 20261006120000) records whether DINCR knows the rate was
really given or confirmed:
- NULL rate, or `interest_rate_known` FALSE → the rate is unknown;
- `interest_rate_known` TRUE → the stored rate is known (0 is a real 0%);
- historical rows (`interest_rate_known` NULL, written before the column existed): a rate above 0
  was given by the user; a 0 may be the old "no rate given → 0" of create_user_debt, so it is
  unknown — except for zero-rate financing (`debt_type` "tasa_cero"), whose type states 0%.
Historical rows are interpreted here, never rewritten (reconciliation is a later, separate step).
"""
from __future__ import annotations

from typing import Any

ZERO_RATE_TYPE = "tasa_cero"
# Stable code in `missing` lists (the #326 contract) when a decision needs a debt's rate.
MISSING_CODE = "debt_interest_rates"

# The same rule in SQL, for counts (`d` may be omitted: column names are unqualified).
UNKNOWN_RATE_SQL = (
    "(interest_rate IS NULL OR interest_rate_known IS FALSE"
    " OR (interest_rate_known IS NULL AND interest_rate = 0 AND COALESCE(debt_type, '') <> 'tasa_cero'))"
)


def known_interest_rate(debt: dict[str, Any]) -> float | None:
    """The debt's annual rate when DINCR knows it, else None (never 0 for "unknown")."""
    rate = debt.get("interest_rate")
    known = debt.get("interest_rate_known")
    if rate is None or known is False:
        return None
    rate = float(rate)
    if known is True or rate > 0:
        return rate
    return 0.0 if (debt.get("debt_type") or "") == ZERO_RATE_TYPE else None


def with_known_rates(debts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The rows with `interest_rate` replaced by the known rate (None when unknown) and
    `interest_rate_known` by whether DINCR knows it (the same meaning as the debts list)."""
    rows = []
    for debt in debts:
        rate = known_interest_rate(debt)
        rows.append({**debt, "interest_rate": rate, "interest_rate_known": rate is not None})
    return rows


def unknown_rate_count(debts: list[dict[str, Any]]) -> int:
    """How many of these (already normalized) debts have no known rate."""
    return sum(1 for debt in debts if debt.get("interest_rate") is None)


def rate_for_create(rate: float | None) -> tuple[float | None, bool]:
    """A new debt: no rate given → unknown (NULL, FALSE); any given rate, 0 included → known."""
    return (None, False) if rate is None else (float(rate), True)


def rate_for_update(stored: dict[str, Any], rate: float | None, confirmed: bool | None) -> tuple[Any, Any]:
    """The (interest_rate, interest_rate_known) to store when a debt is edited.

    Saving a debt never confirms a rate by itself: a client that sends back the rate it loaded
    leaves both columns as they were (an unconfirmed historical 0 stays unconfirmed). The rate
    becomes known only when the user changed it, or the client says the user confirmed it
    (`confirmed`). Clearing a known rate makes it unknown; an unknown rate sent back empty stays
    as stored.
    """
    stored_rate, stored_known = stored.get("interest_rate"), stored.get("interest_rate_known")
    stored_unknown = known_interest_rate(stored) is None
    if rate is None:
        if stored_unknown:
            return stored_rate, stored_known
        return None, False
    rate = float(rate)
    if confirmed:
        return rate, True
    # A 0 sent for an unknown rate is not evidence: older clients turn an empty field into 0
    # (Number(null) is 0). Only an explicit confirmation makes it a known 0%.
    if stored_unknown and rate == 0:
        return stored_rate, stored_known
    if stored_rate is None or float(stored_rate) != rate:
        return rate, True
    return stored_rate, stored_known
