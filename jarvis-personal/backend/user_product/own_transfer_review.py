"""Review opposite bank notices without assuming their references are identical."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException

from backend.auth.current_user import get_current_account_id, get_current_workspace_id
from backend.core.database import get_connection


def _direction(item: dict[str, Any]) -> str:
    raw = item.get("raw_payload") or {}
    direction = raw.get("movement_direction") or item.get("movement_direction")
    return direction if direction in {"in", "out"} else "unknown"


def _time(item: dict[str, Any]) -> datetime | None:
    value = item.get("transaction_time")
    if not value:
        return None
    try:
        return datetime.fromisoformat(f"{item['transaction_date']}T{str(value)[:8]}")
    except (ValueError, TypeError):
        return None


def _eligible(first: dict[str, Any], second: dict[str, Any], unknown_direction: str | None = None) -> bool:
    """Suggest only opposite, equal-value transfer notices; never auto-approve."""
    if first["id"] == second["id"] or first.get("email_message_id") == second.get("email_message_id"):
        return False
    if any(row.get("status") not in {"pending", "confirmed"} or
           row.get("movement_kind") != "transfer" or row.get("is_internal_transfer")
           for row in (first, second)):
        return False
    try:
        if Decimal(str(first["amount"])) != Decimal(str(second["amount"])) or Decimal(str(first["amount"])) <= 0:
            return False
    except (ValueError, TypeError, InvalidOperation):
        return False
    if (first.get("currency") or "CRC") != (second.get("currency") or "CRC"):
        return False
    try:
        first_day = date.fromisoformat(str(first["transaction_date"])[:10])
        second_day = date.fromisoformat(str(second["transaction_date"])[:10])
    except (ValueError, TypeError):
        return False
    if first_day != second_day:
        return False
    first_time, second_time = _time(first), _time(second)
    if first_time and second_time and abs(first_time - second_time) > timedelta(hours=12):
        return False
    directions = [_direction(first), _direction(second)]
    if directions.count("unknown") > 1:
        return False
    if "unknown" in directions:
        if unknown_direction not in {"in", "out"}:
            return unknown_direction is None  # Display a possible pair, require explicit direction to confirm.
        directions[directions.index("unknown")] = unknown_direction
    return set(directions) == {"in", "out"}


def _preview(item: dict[str, Any]) -> dict[str, Any]:
    # A reference is evidence within a bank, not a cross-bank join key.
    reference = re.sub(r"[^a-zA-Z0-9]", "", str(item.get("external_reference") or ""))
    return {
        "candidate_id": int(item["id"]), "bank": item.get("bank"),
        "amount": float(item["amount"]), "currency": item.get("currency") or "CRC",
        "date": str(item["transaction_date"]), "direction": _direction(item),
        "reference_end": reference[-4:] if reference else None,
        "already_saved": bool(item.get("transaction_id")),
    }


def list_own_transfer_suggestions() -> dict[str, Any]:
    account_id, workspace_id = get_current_account_id(), get_current_workspace_id()
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id,email_message_id,bank,transaction_date,transaction_time,amount,currency,
                      movement_kind,movement_direction,external_reference,transaction_id,status,
                      is_internal_transfer
               FROM finva_email_candidates
               WHERE account_id=%s AND workspace_id=%s AND status IN ('pending','confirmed')
                 AND movement_kind='transfer' AND is_internal_transfer=FALSE
               ORDER BY transaction_date DESC,id DESC LIMIT 400""",
            (account_id, workspace_id),
        ).fetchall()
    candidates = [dict(row) for row in rows]
    suggestions = []
    for index, candidate in enumerate(candidates):
        for other in candidates[index + 1:]:
            if _eligible(candidate, other):
                suggestions.append({"first": _preview(candidate), "second": _preview(other)})
    return {"items": suggestions[:100]}


def confirm_own_transfer(first_id: int, second_id: int, unknown_direction: str | None = None) -> dict[str, Any]:
    if first_id == second_id or first_id < 1 or second_id < 1:
        raise HTTPException(status_code=422, detail="Elegí dos movimientos distintos.")
    account_id, workspace_id = get_current_account_id(), get_current_workspace_id()
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id,email_message_id,account_id,workspace_id,bank,transaction_date,transaction_time,
                      amount,currency,movement_kind,movement_direction,external_reference,
                      transaction_id,status,is_internal_transfer
               FROM finva_email_candidates
               WHERE account_id=%s AND workspace_id=%s AND id IN (%s,%s)
               ORDER BY id FOR UPDATE""",
            (account_id, workspace_id, first_id, second_id),
        ).fetchall()
        candidates = {int(row["id"]): dict(row) for row in rows}
        if len(candidates) != 2:
            raise HTTPException(status_code=404, detail="No se encontraron ambos movimientos en tu cuenta.")
        first, second = candidates[first_id], candidates[second_id]
        if not _eligible(first, second, unknown_direction):
            raise HTTPException(status_code=409, detail="Los movimientos no cumplen los criterios de una transferencia propia. Revisalos por separado.")
        if "unknown" in {_direction(first), _direction(second)} and unknown_direction not in {"in", "out"}:
            raise HTTPException(status_code=422, detail="Indicá si el aviso sin dirección es un crédito o un débito.")

        # Validate before editing either candidate; this keeps a failed repair atomic.
        for item in (first, second):
            if item.get("transaction_id"):
                linked = conn.execute(
                    """SELECT id,transaction_type FROM transactions
                       WHERE id=%s AND workspace_id=%s AND source IN ('finva_gmail','finva_statement')
                       FOR UPDATE""",
                    (item["transaction_id"], workspace_id),
                ).fetchone()
                if not linked:
                    raise HTTPException(status_code=409, detail="Un movimiento guardado cambió. Revisalo antes de continuar.")

        for item, counterpart in ((first, second), (second, first)):
            if item.get("transaction_id"):
                conn.execute(
                    """UPDATE transactions SET transaction_type='internal_transfer',
                          category='Movimiento interno',
                          notes=CONCAT_WS(' | ',NULLIF(notes,''),'Transferencia entre cuentas propias confirmada por el usuario.')
                       WHERE id=%s AND workspace_id=%s""",
                    (item["transaction_id"], workspace_id),
                )
                conn.execute(
                    """UPDATE financial_input_events SET payload=
                          jsonb_set(jsonb_set(jsonb_set(payload,'{reclassified_from}',
                                    to_jsonb(payload->>'transaction_type'),true),
                                    '{transaction_type}','"internal_transfer"'::jsonb,true),
                                    '{category}','"Movimiento interno"'::jsonb,true)
                       WHERE transaction_id=%s AND workspace_id=%s AND account_id=%s""",
                    (item["transaction_id"], workspace_id, account_id),
                )
            conn.execute(
                """UPDATE finva_email_candidates SET status='confirmed',reviewed_at=NOW(),
                      transaction_type='internal_transfer',movement_direction='internal',
                      category='Movimiento interno',is_internal_transfer=TRUE,
                      related_candidate_id=%s,resolution_reason='user_confirmed_own_transfer',updated_at=NOW()
                   WHERE id=%s AND account_id=%s AND workspace_id=%s""",
                (counterpart["id"], item["id"], account_id, workspace_id),
            )
            conn.execute(
                """UPDATE finva_email_messages SET status='confirmed'
                   WHERE id=%s AND account_id=%s AND workspace_id=%s""",
                (item["email_message_id"], account_id, workspace_id),
            )
        conn.commit()
    return {"status": "confirmed", "candidate_ids": [first_id, second_id], "excluded_from_income_expenses": True}
