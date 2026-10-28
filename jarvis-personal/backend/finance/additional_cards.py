"""Additional cards: cards billed to the user but carried by someone else.

The user names which card (last 4 digits) belongs to which person. From then on a mail
notice of a purchase on that card is what that person owes, not the user's expense: the
notice is settled (confirmed without a transaction of the user's) and the person's
receivable for that card cycle is brought up to date in the same transaction. Nothing is
inferred from names in a notice or from configuration: only the cards the user marked.

Owner only: receivables (Control de dinero) are Owner-only, so the routes live on the
internal finance router and the mail hook runs only for the Owner's account.

Only email notices are settled automatically. A statement row of the same purchase is
matched to the notice by the cross-source dedupe; a statement row without a notice stays
in review, so one purchase is never charged to the person twice.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from fastapi import HTTPException

from backend.auth.current_user import get_current_account_id, get_current_user_id, get_current_workspace_id
from backend.core.database import get_connection
from backend.finance import receivable_semantics

ROUTED_REASON = receivable_semantics.ADDITIONAL_CARD_REASON
ADDITIONAL_RELATIONSHIP = "adicional"
# "Not additional any more": the user carries the card's cost again (a holder relationship).
HOLDER_RELATIONSHIP = "titular"
CARD_LAST4_SQL = "RIGHT(REGEXP_REPLACE(COALESCE(source_account_reference, ''), '[^0-9]', '', 'g'), 4)"


def _clean_last4(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) != 4:
        raise HTTPException(status_code=422, detail="Indicá los últimos 4 dígitos de la tarjeta.")
    return digits


def _clean_person(value: Any) -> str:
    person = re.sub(r"\s+", " ", str(value or "")).strip()
    if not person or len(person) > 80:
        raise HTTPException(status_code=422, detail="Indicá el nombre de la persona (máximo 80 caracteres).")
    return person


def additional_holder(conn, workspace_id: str, card_last4: str) -> str | None:
    """The person the workspace marked as carrying this card, or None if it is not additional."""
    row = conn.execute(
        """SELECT owner_label FROM card_aliases
           WHERE workspace_id = %s AND card_last4 = %s AND NOT COALESCE(is_primary, FALSE)
             AND LOWER(TRIM(COALESCE(relationship, ''))) <> ALL(%s)""",
        (workspace_id, card_last4, list(receivable_semantics.HOLDER_RELATIONSHIPS)),
    ).fetchone()
    return str(row["owner_label"]) if row and row.get("owner_label") else None


def _refresh_cycles(conn, workspace_id: str, days: set[Any]) -> None:
    # The database layer may hand dates back as ISO text.
    cycles = {receivable_semantics.card_cycle_bounds(date.fromisoformat(str(day)[:10]))[0] for day in days}
    for cycle_start in sorted(cycles):
        receivable_semantics.mirror_additional_card_cycle(conn, workspace_id, cycle_start)


def route_purchase(conn, candidate_id: int, *, account_id: str, workspace_id: str) -> bool:
    """Settle a pending purchase notice of an additional card as owed by its person.

    Called by the mail sync for the Owner only, in the sync's transaction. Returns False
    (and changes nothing) for anything that is not a pending email notice of a purchase
    made with a card the workspace marked as additional.
    """
    row = conn.execute(
        f"""SELECT id, transaction_date, {CARD_LAST4_SQL} AS card_last4
            FROM finva_email_candidates
            WHERE id = %s AND account_id = %s AND workspace_id = %s AND status = 'pending'
              AND transaction_id IS NULL AND source_type = 'email'
              AND movement_kind = 'card_purchase' AND movement_direction = 'out'
            FOR UPDATE""",
        (candidate_id, account_id, workspace_id),
    ).fetchone()
    if not row or not row.get("card_last4") or not additional_holder(conn, workspace_id, row["card_last4"]):
        return False
    conn.execute(
        """UPDATE finva_email_candidates
           SET status = 'confirmed', resolution_reason = %s, reviewed_at = NOW(), updated_at = NOW()
           WHERE id = %s AND account_id = %s AND workspace_id = %s AND status = 'pending'""",
        (ROUTED_REASON, candidate_id, account_id, workspace_id),
    )
    _refresh_cycles(conn, workspace_id, {row["transaction_date"]})
    return True


def list_additional_cards() -> dict[str, Any]:
    """The workspace's cards marked as carried by someone else. Read only."""
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT card_last4, owner_label AS person_name FROM card_aliases
               WHERE workspace_id = %s AND NOT COALESCE(is_primary, FALSE)
                 AND LOWER(TRIM(COALESCE(relationship, ''))) <> ALL(%s)
               ORDER BY owner_label, card_last4""",
            (workspace_id, list(receivable_semantics.HOLDER_RELATIONSHIPS)),
        ).fetchall()
    return {"status": "ok", "items": [dict(row) for row in rows]}


def save_additional_card(card_last4: Any, person_name: Any) -> dict[str, Any]:
    """Mark a card as carried by ``person_name`` and settle its pending purchase notices."""
    last4, person = _clean_last4(card_last4), _clean_person(person_name)
    account_id, workspace_id = get_current_account_id(), get_current_workspace_id()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO card_aliases (workspace_id, user_id, card_last4, owner_label, relationship, is_primary)
               VALUES (%s, %s, %s, %s, %s, FALSE)
               ON CONFLICT (workspace_id, card_last4) DO UPDATE
               SET owner_label = EXCLUDED.owner_label, relationship = EXCLUDED.relationship,
                   is_primary = FALSE, updated_at = NOW()""",
            (workspace_id, get_current_user_id(), last4, person, ADDITIONAL_RELATIONSHIP),
        )
        pending = conn.execute(
            f"""SELECT id FROM finva_email_candidates
                WHERE account_id = %s AND workspace_id = %s AND status = 'pending' AND {CARD_LAST4_SQL} = %s
                ORDER BY id""",
            (account_id, workspace_id, last4),
        ).fetchall()
        settled = sum(route_purchase(conn, int(r["id"]), account_id=account_id, workspace_id=workspace_id) for r in pending)
        # A person renamed on an existing card: the open cycle is charged to the new name.
        _refresh_cycles(conn, workspace_id, {date.today()})
        conn.commit()
    return {"status": "ok", "item": {"card_last4": last4, "person_name": person}, "settled_purchases": settled}


def stop_additional_card(card_last4: Any) -> dict[str, Any]:
    """The card is not additional any more: its settled notices go back to review.

    Nothing is deleted. The alias keeps its person but becomes a holder card, the
    person's charges for the affected cycles are recalculated (archived when empty), and
    the purchases wait in review for the user to decide again.
    """
    last4 = _clean_last4(card_last4)
    account_id, workspace_id = get_current_account_id(), get_current_workspace_id()
    with get_connection() as conn:
        updated = conn.execute(
            """UPDATE card_aliases SET relationship = %s, is_primary = FALSE, updated_at = NOW()
               WHERE workspace_id = %s AND card_last4 = %s RETURNING id""",
            (HOLDER_RELATIONSHIP, workspace_id, last4),
        ).fetchone()
        if not updated:
            raise HTTPException(status_code=404, detail="Esa tarjeta no está marcada como adicional.")
        released = conn.execute(
            f"""UPDATE finva_email_candidates
                SET status = 'pending', resolution_reason = NULL, reviewed_at = NULL, updated_at = NOW()
                WHERE account_id = %s AND workspace_id = %s AND status = 'confirmed' AND resolution_reason = %s
                  AND transaction_id IS NULL AND {CARD_LAST4_SQL} = %s
                RETURNING transaction_date""",
            (account_id, workspace_id, ROUTED_REASON, last4),
        ).fetchall()
        _refresh_cycles(conn, workspace_id, {row["transaction_date"] for row in released} | {date.today()})
        conn.commit()
    return {"status": "ok", "released_purchases": len(released)}
