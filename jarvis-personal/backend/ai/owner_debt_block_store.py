"""The Owner's locked savings blocks once created at the bank (part 2 of "ahorro bloqueado").

Stored as the workspace's ``debt_savings_blocks`` preference (``user_preferences``, the same store the
Salvavidas and Retiro use). The Owner creates a block at the bank, then tells DINCR (POST): which debt,
how much every payday, from when and for how many months. From then on:

- the plan sets the block's contributions aside like the Salvavidas automatic savings
  (``owner_commitments``), so that money is never shown as free;
- the next proposal only uses what is left of the weekly amount and never targets a debt that
  already has a block.

Reading never writes; creating and cancelling are the Owner's explicit commands. Owner only (the
JARVIS router). Nothing is inferred from bank data.
"""
from __future__ import annotations

import math
import uuid
from datetime import date, timedelta
from typing import Any

from fastapi import HTTPException

from backend.ai.preferences import get_preference, set_preference
from backend.core.i18n import tx
from backend.core.time import costa_rica_today
from backend.finance import debt_savings_blocks
from backend.finance.service import get_debts

PREFERENCE_KEY = "debt_savings_blocks"
MAX_TERM_MONTHS = 60
MAX_WEEKLY = 999_999_999.99
START_WINDOW_DAYS = (-31, 62)   # a block started up to a month ago, or starting within two months


def _day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _amount(value: Any) -> float | None:
    try:
        number = round(float(value), 2)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and 0 < number <= MAX_WEEKLY else None


def normalize(raw: Any) -> list[dict[str, Any]]:
    """The stored blocks that are complete and valid; anything else is ignored (never guessed)."""
    blocks = (raw or {}).get("blocks") if isinstance(raw, dict) else None
    result = []
    for block in blocks if isinstance(blocks, list) else []:
        if not isinstance(block, dict):
            continue
        start, maturity, weekly = _day(block.get("start_date")), _day(block.get("maturity_date")), _amount(block.get("weekly_amount"))
        if not block.get("id") or block.get("debt_id") is None or not start or not maturity or maturity <= start or weekly is None:
            continue
        result.append({"id": str(block["id"]), "debt_id": block["debt_id"], "debt_name": block.get("debt_name"),
                       "mode": block.get("mode") if block.get("mode") in ("block", "presave") else "block",
                       "weekly_amount": weekly, "start_date": start.isoformat(), "maturity_date": maturity.isoformat(),
                       "term_months": block.get("term_months"), "created_at": block.get("created_at")})
    return result


def stored_blocks() -> list[dict[str, Any]]:
    return normalize(get_preference(PREFERENCE_KEY, {}))


def contributions(block: dict[str, Any], after: date, until: date) -> list[date]:
    """The block's payday contributions d with ``after < d <= until`` (none on or after maturity)."""
    start, maturity = _day(block["start_date"]), _day(block["maturity_date"])
    return [day for day in debt_savings_blocks.contribution_dates(start, maturity) if after < day <= until]


def with_progress(block: dict[str, Any], today: date) -> dict[str, Any]:
    """The block with what it holds by today (the bank's interest never counted) and its next payday."""
    start, maturity = _day(block["start_date"]), _day(block["maturity_date"])
    dates = debt_savings_blocks.contribution_dates(start, maturity)
    done = [day for day in dates if day <= today]
    upcoming = next((day for day in dates if day > today), None)
    return {**block, "contributions_total": len(dates), "contributions_done": len(done),
            "saved_so_far": round(len(done) * block["weekly_amount"], 2),
            "total_at_maturity": round(len(dates) * block["weekly_amount"], 2),
            "next_date": upcoming.isoformat() if upcoming else None,
            "matured": today >= maturity}


def active(blocks: list[dict[str, Any]], today: date) -> list[dict[str, Any]]:
    """Blocks not yet matured: they still take money every payday."""
    return [block for block in blocks if _day(block["maturity_date"]) > today]


def weekly_committed(blocks: list[dict[str, Any]], today: date) -> float:
    return round(sum(block["weekly_amount"] for block in active(blocks, today)), 2)


def create_block(payload: dict[str, Any]) -> dict[str, Any]:
    """The Owner created a block at the bank: record it (one block per debt at a time)."""
    today = costa_rica_today()
    weekly = _amount(payload.get("weekly_amount"))
    start = _day(payload.get("start_date"))
    term = payload.get("term_months")
    if weekly is None:
        raise HTTPException(status_code=422, detail=tx("Indicá cuánto ahorrás cada jueves.", "Say how much you save every Thursday."))
    if not isinstance(term, int) or not debt_savings_blocks.MIN_TERM_MONTHS <= term <= MAX_TERM_MONTHS:
        raise HTTPException(status_code=422, detail=tx("El plazo va de 3 a 60 meses.", "The term is 3 to 60 months."))
    if not start or not today + timedelta(days=START_WINDOW_DAYS[0]) <= start <= today + timedelta(days=START_WINDOW_DAYS[1]):
        raise HTTPException(status_code=422, detail=tx("Revisá la fecha del primer ahorro.", "Check the first saving's date."))
    debt = next((row for row in (get_debts() or [])
                 if str(row.get("id")) == str(payload.get("debt_id")) and float(row.get("remaining_amount") or 0) > 0.01), None)
    if debt is None:   # get_debts reads only this workspace: another's debt id is simply not found
        raise HTTPException(status_code=404, detail=tx("No encontramos esa deuda.", "We couldn't find that debt."))
    blocks = stored_blocks()
    if any(str(block["debt_id"]) == str(debt["id"]) for block in active(blocks, today)):
        raise HTTPException(status_code=409, detail=tx("Esa deuda ya tiene un ahorro bloqueado.", "That debt already has a locked saving."))
    block = {"id": uuid.uuid4().hex, "debt_id": debt["id"], "debt_name": debt.get("name"),
             "mode": payload.get("mode") if payload.get("mode") in ("block", "presave") else "block",
             "weekly_amount": weekly, "start_date": start.isoformat(),
             "maturity_date": debt_savings_blocks.add_months(start, term).isoformat(), "term_months": term,
             "created_at": today.isoformat()}
    set_preference(PREFERENCE_KEY, {"blocks": blocks + [block]})
    return {"status": "OK", "block": with_progress(normalize({"blocks": [block]})[0], today)}


def cancel_block(block_id: str) -> dict[str, Any]:
    """The Owner removed a block (created by mistake or closed at the bank)."""
    blocks = stored_blocks()
    kept = [block for block in blocks if block["id"] != block_id]
    if len(kept) == len(blocks):
        raise HTTPException(status_code=404, detail=tx("No encontramos ese ahorro.", "We couldn't find that saving."))
    set_preference(PREFERENCE_KEY, {"blocks": kept})
    return {"status": "OK", "deleted": block_id}
