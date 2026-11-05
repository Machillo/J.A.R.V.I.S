"""Where the Owner's investment share goes (Owner only): a savings account he names, not stocks.

Stored as the workspace's ``investment_destination`` preference: ``{"name": ..., "annual_rate": ...}``
(the account's fixed yearly rate, in percent). When it is set, his strategy names that account on
the investment share and its recommendation says how much to put there; the rate stands in for the
dividend yield when the engine compares investing with paying debts. The share itself, and when it
opens, do not change. Nothing here is a user's: it is the Owner's own configuration, read only from
his workspace. Read-only.
"""
from __future__ import annotations

from typing import Any

from backend.ai.preferences import get_preference
from backend.core.i18n import tx

PREFERENCE_KEY = "investment_destination"
MAX_RATE = 50.0


def destination(read=None) -> dict[str, Any] | None:
    """``read``: the preference reader (the strategy passes its own). A failed read is no destination:
    the strategy then keeps its usual investment share."""
    try:
        raw = (read or get_preference)(PREFERENCE_KEY, None)
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or "").strip()[:60]
    try:
        rate = float(raw.get("annual_rate"))
    except (TypeError, ValueError):
        rate = None
    if not name or rate is None or not 0 < rate <= MAX_RATE:
        return None
    return {"name": name, "annual_rate": round(rate, 2)}


def _rate_text(rate: float) -> str:
    return f"{rate:g}".replace(".", ",")


def label(found: dict[str, Any]) -> str:
    return tx(f"{found['name']} · {_rate_text(found['annual_rate'])}% anual", f"{found['name']} · {found['annual_rate']:g}% a year")


def apply(items: list[dict[str, Any]], priority: dict[str, Any], found: dict[str, Any] | None) -> dict[str, Any]:
    """Names the destination on the investment share and, when that is the priority, says how much to save there."""
    if not found:
        return priority
    amount = 0.0
    for item in items:
        if item.get("key") == "inversion":
            item["target_name"] = label(found)
            amount = float(item.get("amount") or 0)
    if priority.get("kind") != "investment" or amount <= 0:
        return priority
    shown = "₡" + f"{round(amount):,}".replace(",", ".")
    return {**priority,
            "title": tx(f"Guardá {shown} en {found['name']}", f"Save {shown} in {found['name']}"),
            "detail": tx(f"Las obligaciones están cubiertas: tu parte de inversión va a {found['name']} ({_rate_text(found['annual_rate'])}% anual).",
                         f"Obligations are covered: your investment share goes to {found['name']} ({found['annual_rate']:g}% a year).")}
