"""A credit card's statement cut day (`account_balances.statement_cut_day`, migration 20261026120000).

The user declares it on one of their own credit cards; USD expenses paid with that card wait for
it to be converted (a later change). NULL is "not declared": DINCR never assumes a cut day and
never uses the Owner's legacy card settings for anyone.

The column may not exist yet (the migration is applied separately): reads then report the cut day
as unavailable (`statement_cut_day_available: False`) and writes answer 503, never an error 500.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from backend.auth.current_user import get_current_account_id, get_current_workspace_id
from backend.core.database import get_connection
from backend.core.i18n import tx
from backend.core.schema_state import columns_exist

COLUMN = "statement_cut_day"


def cut_day_available(conn) -> bool:
    return columns_exist(conn, "account_balances", [COLUMN])


def add_cut_days(conn, items: list[dict], *, account_id: str, workspace_id: str) -> bool:
    """Set each item's `statement_cut_day` from the caller's own rows (None when not declared or
    while the column does not exist). Returns whether the column exists."""
    available = cut_day_available(conn)
    days: dict[int, Any] = {}
    if available and items:
        rows = conn.execute(
            f"SELECT id,{COLUMN} FROM account_balances WHERE account_id=%s AND workspace_id=%s AND id = ANY(%s)",
            (account_id, workspace_id, [int(item["id"]) for item in items]),
        ).fetchall()
        days = {int(row["id"]): row[COLUMN] for row in rows}
    for item in items:
        item[COLUMN] = days.get(int(item["id"]))
    return available


def set_statement_cut_day(account_balance_id: int, day: int | None) -> dict[str, Any]:
    """Declare (1–31) or clear (None) the cut day of one of the caller's own active credit cards."""
    if day is not None and not 1 <= int(day) <= 31:
        raise HTTPException(status_code=422, detail={"code": "invalid_cut_day", "message": tx("El día de corte va de 1 a 31.", "The cut day is 1 to 31.")})
    account_id, workspace_id = get_current_account_id(), get_current_workspace_id()
    with get_connection() as conn:
        if not cut_day_available(conn):
            raise HTTPException(status_code=503, detail={"code": "statement_cut_day_unavailable",
                                                         "message": tx("El día de corte todavía no está disponible.", "The cut day isn’t available yet.")})
        row = conn.execute(
            f"""UPDATE account_balances SET {COLUMN}=%s, updated_at=NOW()
                WHERE id=%s AND account_id=%s AND workspace_id=%s AND is_active=TRUE
                  AND account_type='credit_card' AND ownership_status='own'
                RETURNING id,account_name,account_type,account_last4,currency,ownership_status,{COLUMN}""",
            (day, account_balance_id, account_id, workspace_id),
        ).fetchone()
        if not row:
            # Why not: another workspace's id is simply not found (never confirmed to exist).
            found = conn.execute(
                "SELECT account_type,ownership_status FROM account_balances WHERE id=%s AND account_id=%s AND workspace_id=%s AND is_active=TRUE",
                (account_balance_id, account_id, workspace_id),
            ).fetchone()
            if not found:
                raise HTTPException(status_code=404, detail={"code": "account_not_found", "message": tx("Cuenta financiera no encontrada.", "Financial account not found.")})
            if found["account_type"] != "credit_card":
                raise HTTPException(status_code=422, detail={"code": "not_a_credit_card",
                                                             "message": tx("Solo las tarjetas de crédito tienen día de corte.", "Only credit cards have a cut day.")})
            raise HTTPException(status_code=409, detail={"code": "not_own_account",
                                                         "message": tx("Confirmá primero que la tarjeta es tuya.", "Confirm first that the card is yours.")})
        conn.commit()
    return {"status": "ok", "item": dict(row)}
