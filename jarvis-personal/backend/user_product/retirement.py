"""RT-1 — Retiro (VIP and the Owner): what the user has put aside for retirement, declared by hand.

Stored as the workspace's `retirement` preference (`user_preferences`, the same store the Salvavidas
uses): the ROP balance, a voluntary pension balance, the year of birth and the age the user wants to
retire at. Every field is optional; an unknown one stays unknown (null), never 0. The reading
(the age reference, what to add each month) is worded by the app (`RetirementReading`); this module
only validates and stores. Reading never writes; saving is the user's explicit command.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import HTTPException

from backend.ai.preferences import get_preference, set_preference

PREFERENCE_KEY = "retirement"
DEFAULT_RETIRE_AGE = 65


def _amount(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = round(float(value), 2)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def normalize(raw: Any) -> dict[str, Any]:
    """The stored values that can be used; anything invalid is unknown."""
    raw = raw if isinstance(raw, dict) else {}
    year = raw.get("birth_year")
    year = int(year) if isinstance(year, int) and 1930 <= year <= date.today().year else None
    age = raw.get("retire_age")
    age = int(age) if isinstance(age, int) and 50 <= age <= 80 else DEFAULT_RETIRE_AGE
    return {"rop_balance": _amount(raw.get("rop_balance")), "voluntary_balance": _amount(raw.get("voluntary_balance")),
            "birth_year": year, "retire_age": age}


def get_retirement() -> dict[str, Any]:
    return {"config": normalize(get_preference(PREFERENCE_KEY, {}))}


def update_retirement(payload: dict[str, Any]) -> dict[str, Any]:
    """Saves what was sent; a field left out keeps its value, a null clears it."""
    current = normalize(get_preference(PREFERENCE_KEY, {}))
    for key in ("rop_balance", "voluntary_balance"):
        if key in payload:
            value = payload[key]
            if value is not None and _amount(value) is None:
                raise HTTPException(status_code=422, detail="Los saldos no pueden ser negativos.")
            current[key] = _amount(value)
    if "birth_year" in payload:
        year = payload["birth_year"]
        if year is not None and not (isinstance(year, int) and 1930 <= year <= date.today().year):
            raise HTTPException(status_code=422, detail="Revisá tu año de nacimiento.")
        current["birth_year"] = year
    if "retire_age" in payload and payload["retire_age"] is not None:
        age = payload["retire_age"]
        if not (isinstance(age, int) and 50 <= age <= 80):
            raise HTTPException(status_code=422, detail="La edad de retiro va de 50 a 80 años.")
        current["retire_age"] = age
    set_preference(PREFERENCE_KEY, current)
    return {"config": current}
