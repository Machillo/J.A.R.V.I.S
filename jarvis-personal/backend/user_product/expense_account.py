"""A manual expense's "paid with" account or card (`expenses.financial_account_id`, migration 20261026130000).

The user says which of their own accounts or cards paid an expense; a USD expense paid with a card
waits for that card's statement cut to be converted (a later change). NULL is "not told": DINCR
never infers the card, and an expense without one is still an expense.

Only the caller's own active accounts (same account and workspace, `ownership_status='own'`) can be
linked: another workspace's id is simply not found. A request that does not send the field leaves
the link as it is (older app versions never clear it).

The column may not exist yet (the migration is applied separately): listings then carry a null link,
the options say "unavailable", and only a request that links an account answers 503, never 500.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from backend.auth.current_user import get_current_account_id, get_current_workspace_id
from backend.core.database import get_connection
from backend.core.i18n import tx
from backend.core.schema_state import columns_exist

COLUMN = "financial_account_id"
FIELD = "financial_account_id"


def paid_with_available(conn) -> bool:
    return columns_exist(conn, "expenses", [COLUMN])


# The link selected from an `expenses` row, NULL while the column does not exist: read through the
# row's JSON, so listings need no extra catalog query and never fail before the migration.
SELECT_SQL = f"(to_jsonb(expenses)->>'{COLUMN}')::bigint AS {COLUMN}"


def paid_with_options() -> dict[str, Any]:
    """The caller's own active accounts and cards an expense can say it was paid with (read-only)."""
    account_id, workspace_id = get_current_account_id(), get_current_workspace_id()
    with get_connection() as conn:
        available = paid_with_available(conn)
        rows = conn.execute(
            """SELECT id,account_name,bank_name,institution_code,account_type,account_last4,currency
               FROM account_balances
               WHERE account_id=%s AND workspace_id=%s AND is_active=TRUE AND ownership_status='own'
               ORDER BY CASE account_type WHEN 'credit_card' THEN 0 ELSE 1 END,bank_name,account_name,id""",
            (account_id, workspace_id),
        ).fetchall() if available else []
    return {"status": "ok", "available": available, "items": [dict(row) for row in rows]}


def requested_link(conn, payload, *, account_id: str, workspace_id: str) -> tuple[bool, int | None]:
    """(write?, value) for the link a create or update request carries.

    Not sent: nothing to write. Sent as null: clear it (nothing to clear while the column does not
    exist). Sent as an id: it must be one of the caller's own active accounts.
    """
    if FIELD not in getattr(payload, "model_fields_set", set()):
        return False, None
    value = getattr(payload, FIELD, None)
    available = paid_with_available(conn)
    if value is None:
        return available, None
    if not available:
        raise HTTPException(status_code=503, detail={"code": "paid_with_unavailable",
                                                     "message": tx("Indicar con qué pagaste todavía no está disponible.", "Saying what you paid with isn’t available yet.")})
    found = conn.execute(
        "SELECT ownership_status FROM account_balances WHERE id=%s AND account_id=%s AND workspace_id=%s AND is_active=TRUE",
        (value, account_id, workspace_id),
    ).fetchone()
    if not found:
        raise HTTPException(status_code=404, detail={"code": "paid_with_account_not_found",
                                                     "message": tx("Cuenta financiera no encontrada.", "Financial account not found.")})
    if found["ownership_status"] != "own":
        raise HTTPException(status_code=409, detail={"code": "paid_with_not_own",
                                                     "message": tx("Confirmá primero que la cuenta es tuya.", "Confirm first that the account is yours.")})
    return True, int(value)


def write_link(conn, expense_id: int, value: int | None, *, workspace_id: str) -> None:
    """Store the validated link on the caller's expense, in the caller's transaction."""
    conn.execute(f"UPDATE expenses SET {COLUMN}=%s WHERE id=%s AND workspace_id=%s", (value, expense_id, workspace_id))
