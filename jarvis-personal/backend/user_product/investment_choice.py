"""Whether a VIP wants investing in their plan: their choice, off until they turn it on.

Stored as the workspace's `investment_choice` preference. Off, the strategy gives investing nothing,
whatever else would allow it. DINCR never picks a stock. Reading never writes; saving is the user's
explicit command. The Owner's strategy has its own rules and doesn't read this.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from backend.ai.preferences import get_preference, set_preference

PREFERENCE_KEY = "investment_choice"


def wants_investing() -> bool:
    raw = get_preference(PREFERENCE_KEY, {})
    return isinstance(raw, dict) and raw.get("wants_investing") is True


def get_choice() -> dict[str, bool]:
    return {"wants_investing": wants_investing()}


def update_choice(payload: dict[str, Any]) -> dict[str, bool]:
    wanted = payload.get("wants_investing")
    if not isinstance(wanted, bool):
        raise HTTPException(status_code=422, detail="Elegí si querés incluir inversiones.")
    set_preference(PREFERENCE_KEY, {"wants_investing": wanted})
    return {"wants_investing": wanted}
