"""One purchase seen by an iOS Shortcuts capture and by a bank notice is one movement.

An Apple Pay payment also produces a bank SMS and often a mail notice; a SINPE Móvil may
arrive by SMS and by mail. Whichever of them reaches DINCR later is compared with the earlier
ones (deterministic, same account and workspace, never across them):

- always required: one side is a Shortcuts capture (``source_type='api'``) and the other is a
  different source (mail notice, statement row, or the other capture provider); same money in
  the movement's own currency (USD is compared in USD); same movement type; close in time
  (within CAPTURE_WINDOW when both carry a time, else the same day); a counterpart still
  usable (pending or saved) and not already claimed by another copy;
- **duplicate**: exactly one such counterpart, not a transfer, and the same merchant
  (normalized description). The later copy is recorded as a duplicate of it, so the movement
  is reviewed and saved once and the copy never shows in "Por revisar";
- **possible duplicate**: anything weaker (no merchant match, a transfer, or several
  candidates). The copy stays pending with the counterpart linked, shown as a possible match.

Rejecting the counterpart releases the copy back to review (candidate_resolution
``release_cross_source_duplicates`` treats these links like the other cross-source ones).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

CAPTURE_SOURCE = "api"
CAPTURE_WINDOW = timedelta(minutes=30)
MAX_DAYS_APART = 1


def _when(row: dict[str, Any]) -> tuple[str, datetime | None]:
    day = str(row.get("transaction_date") or "")[:10]
    clock = str(row.get("transaction_time") or "")[:8]
    if not day or not clock:
        return day, None
    try:
        return day, datetime.fromisoformat(f"{day}T{clock}")
    except ValueError:
        return day, None


def _close_in_time(first: dict[str, Any], second: dict[str, Any]) -> bool:
    (day_a, at_a), (day_b, at_b) = _when(first), _when(second)
    if at_a and at_b:
        return abs(at_a - at_b) <= CAPTURE_WINDOW
    return bool(day_a) and day_a == day_b


def capture_resolution(conn, candidate: dict[str, Any]) -> tuple[str | None, int | None, str | None]:
    """(status, counterpart id, reason) for a capture vs notice match, or (None, None, None)."""
    from backend.user_product.candidate_resolution import (
        CROSS_SOURCE_REASON, CROSS_SOURCE_REASONS, POSSIBLE_MATCH_REASON, RECONCILED_REASON,
        _money_key, _movement_type, _same_merchant, _transfer_like,
    )

    is_capture = candidate.get("source_type") == CAPTURE_SOURCE
    money = _money_key(candidate)
    if money is None:
        return None, None, None
    rows = [dict(row) for row in conn.execute(
        f"""SELECT c.id,c.status,c.transaction_id,c.transaction_date,c.transaction_time,c.description,
                   c.transaction_type,c.movement_kind,c.source_type,c.source_provider,c.raw_payload,
                   c.amount,c.currency,c.original_amount,c.original_currency
            FROM finva_email_candidates c
            WHERE c.account_id=%s AND c.workspace_id=%s AND c.id<>%s
              AND c.transaction_date BETWEEN %s::date-{MAX_DAYS_APART} AND %s::date+{MAX_DAYS_APART}
              AND c.status IN ('pending','confirmed','auto_saved')
              AND {"(c.source_type<>'api' OR c.source_provider<>%s)" if is_capture else "c.source_type='api'"}
              AND NOT EXISTS (
                  SELECT 1 FROM finva_email_candidates claimed
                  WHERE claimed.related_candidate_id=c.id AND claimed.id<>%s AND claimed.status='duplicate'
                    AND claimed.resolution_reason IN (%s,%s))
            ORDER BY c.id""",
        (candidate["account_id"], candidate["workspace_id"], candidate["id"],
         candidate["transaction_date"], candidate["transaction_date"],
         *([candidate.get("source_provider")] if is_capture else []),
         candidate["id"], *CROSS_SOURCE_REASONS),
    ).fetchall()]
    kind = _movement_type(candidate)
    rows = [row for row in rows if _movement_type(row) == kind and _money_key(row) == money and _close_in_time(row, candidate)]
    if not rows:
        return None, None, None
    strong = [] if _transfer_like(candidate) else [
        row for row in rows if not _transfer_like(row) and _same_merchant(row.get("description"), candidate.get("description"))
    ]
    if len(strong) == 1:
        match = conn.execute(
            """SELECT id,status,transaction_id FROM finva_email_candidates
               WHERE id=%s AND account_id=%s AND workspace_id=%s FOR UPDATE""",
            (int(strong[0]["id"]), candidate["account_id"], candidate["workspace_id"]),
        ).fetchone()
        if match and match["status"] in ("pending", "confirmed", "auto_saved"):
            return "duplicate", int(match["id"]), RECONCILED_REASON if match.get("transaction_id") else CROSS_SOURCE_REASON
        return None, None, None
    return "pending", int(rows[0]["id"]) if len(rows) == 1 else None, POSSIBLE_MATCH_REASON


def apply_capture_resolution(conn, candidate_id: int, *, account_id: str, workspace_id: str) -> dict[str, Any] | None:
    """After the usual resolution left a candidate pending: link it to the other source's copy.

    A duplicate is recorded as such (``{"status": "duplicate"}``); a possible duplicate stays
    pending with the counterpart linked, unless the usual resolution already linked a hint.
    Only inside the caller's account and workspace.
    """
    row = conn.execute(
        """SELECT * FROM finva_email_candidates WHERE id=%s AND account_id=%s AND workspace_id=%s
             AND status='pending' FOR UPDATE""",
        (candidate_id, account_id, workspace_id),
    ).fetchone()
    if not row:
        return None
    status, related_id, reason = capture_resolution(conn, dict(row))
    if status == "duplicate":
        conn.execute(
            """UPDATE finva_email_candidates SET status='duplicate',related_candidate_id=%s,resolution_reason=%s,updated_at=NOW()
               WHERE id=%s AND account_id=%s AND workspace_id=%s""",
            (related_id, reason, candidate_id, account_id, workspace_id),
        )
        return {"status": "duplicate", "related_candidate_id": related_id}
    if status == "pending" and not row.get("resolution_reason"):
        conn.execute(
            """UPDATE finva_email_candidates SET related_candidate_id=%s,resolution_reason=%s,updated_at=NOW()
               WHERE id=%s AND account_id=%s AND workspace_id=%s""",
            (related_id, reason, candidate_id, account_id, workspace_id),
        )
    return None

