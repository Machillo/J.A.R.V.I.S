"""What the bank did with an extra payment, when the user only learns it later.

After an extra payment the bank may shorten the term or lower the installment, and sometimes it
says so days later (the next statement). The user can then say "el banco me avisa después" with a
day: the debt is marked pending (the workspace's ``pending_debt_adjustments`` preference) and the
phone reminds that day (``Reminders``). A confirmed distribution marks every debt it paid extra into
as pending (no day). Answering — installments left, new installment, or nothing changed — applies it
(``finance/debt_extra_payment.adjust_after_extra``) and clears the mark; a new day only moves the
reminder. Nothing is guessed. Reads never write; every write is the user's explicit command, scoped
by the session's workspace (the debt must be the workspace's).
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from fastapi import HTTPException

from backend.auth.current_user import get_current_workspace_id
from backend.core.database import get_connection
from backend.core.i18n import tx
from backend.core.time import costa_rica_today
from backend.finance.debt_extra_payment import MAX_INSTALLMENTS, adjust_after_extra

PREFERENCE_KEY = "pending_debt_adjustments"
MAX_DAYS_AHEAD = 62


def _items(value: Any) -> dict[str, dict[str, Any]]:
    items = (value or {}).get("items") if isinstance(value, dict) else None
    return {str(key): item for key, item in (items or {}).items() if isinstance(item, dict)} if isinstance(items, dict) else {}


def pending(conn, workspace_id: str) -> dict[str, dict[str, Any]]:
    """The debts waiting for the bank's answer, by debt id (SELECT only)."""
    row = conn.execute("SELECT preference_value FROM user_preferences WHERE workspace_id=%s AND preference_key=%s",
                       (workspace_id, PREFERENCE_KEY)).fetchone()
    return _items(row["preference_value"] if row else None)


def _save(conn, workspace_id: str, items: dict[str, dict[str, Any]]) -> None:
    conn.execute(
        """INSERT INTO user_preferences (workspace_id, preference_key, preference_value) VALUES (%s, %s, %s::jsonb)
           ON CONFLICT (workspace_id, preference_key) DO UPDATE SET preference_value = EXCLUDED.preference_value, updated_at = NOW()""",
        (workspace_id, PREFERENCE_KEY, json.dumps({"items": items}, ensure_ascii=False)),
    )


def list_pending() -> dict[str, Any]:
    """GET: the session workspace's debts waiting for the bank's answer, by debt id (read-only)."""
    with get_connection() as conn:
        return {"items": pending(conn, get_current_workspace_id())}


def mark_pending(conn, workspace_id: str, debt_id: int, *, remind_on: date | None, source: str) -> None:
    """The debt waits for the bank's answer (inside the caller's transaction). A known day is kept
    when a later mark has none."""
    conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"{PREFERENCE_KEY}:{workspace_id}",))
    items = pending(conn, workspace_id)
    previous = items.get(str(debt_id)) or {}
    items[str(debt_id)] = {"remind_on": remind_on.isoformat() if remind_on else previous.get("remind_on"),
                           "since": previous.get("since") or costa_rica_today().isoformat(), "source": source}
    _save(conn, workspace_id, items)


def remind_day(value: Any) -> date | None:
    """A reminder day from today to ``MAX_DAYS_AHEAD`` ahead; 422 otherwise."""
    if value is None:
        return None
    try:
        day = value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
    except ValueError:
        day = None
    today = costa_rica_today()
    if day is None or not today <= day <= today + timedelta(days=MAX_DAYS_AHEAD):
        raise HTTPException(status_code=422, detail=tx("Elegí un día de hoy a dos meses.", "Choose a day from today to two months ahead."))
    return day


def answer(debt_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """The bank's answer for a debt (installments left, new installment or nothing changed), or a new
    day to be reminded. Exactly one of them."""
    remaining, installment = payload.get("remaining_installments"), payload.get("new_monthly_payment")
    unchanged, remind_on = bool(payload.get("unchanged")), remind_day(payload.get("remind_on"))
    given = [remaining is not None, installment is not None, unchanged, remind_on is not None]
    if sum(given) != 1:
        raise HTTPException(status_code=422, detail=tx("Indicá una sola respuesta.", "Give one answer."))
    if remaining is not None and not (isinstance(remaining, int) and 1 <= remaining <= MAX_INSTALLMENTS):
        raise HTTPException(status_code=422, detail=tx("Indicá cuántas cuotas te quedan.", "Enter how many installments are left."))
    if installment is not None and not float(installment) > 0:
        raise HTTPException(status_code=422, detail=tx("Indicá la cuota nueva.", "Enter the new installment."))
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        debt = conn.execute("SELECT id FROM debts WHERE id=%s AND workspace_id=%s FOR UPDATE", (debt_id, workspace_id)).fetchone()
        if not debt:   # another workspace's debt is simply not found
            raise HTTPException(status_code=404, detail=tx("Deuda no encontrada.", "Debt not found."))
        if remind_on is not None:
            mark_pending(conn, workspace_id, debt_id, remind_on=remind_on, source="later")
        else:
            adjust_after_extra(conn, workspace_id, debt_id, remaining_installments=remaining,
                               new_monthly_payment=float(installment) if installment is not None else None)
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"{PREFERENCE_KEY}:{workspace_id}",))
            items = pending(conn, workspace_id)
            if items.pop(str(debt_id), None) is not None:
                _save(conn, workspace_id, items)
        conn.commit()
    return {"status": "OK", "debt_id": debt_id, "pending": remind_on is not None,
            "remind_on": remind_on.isoformat() if remind_on else None}
