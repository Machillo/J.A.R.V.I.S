"""Reconcile the retired Owner Gmail reader with the standard mailbox flow.

Before launch, DINCR Owner read one Gmail mailbox with server-held credentials
(backend/email_monitor, tables email_ingested_messages and
email_transaction_candidates) and created transactions from it. When the Owner
connects that mailbox through the standard OAuth flow, the initial scan sees the
same Gmail messages again. Gmail message ids are stable per mailbox, so a message
the legacy reader already turned into a transaction in the same workspace is a
deterministic duplicate: the new candidate is marked ``duplicate`` with the
auditable reason ``legacy_owner_import`` instead of asking the Owner to confirm
it a second time. Nothing is deleted or rewritten; statement rows and messages
the legacy reader never committed stay reviewable as usual.
"""
from __future__ import annotations

from typing import Any

LEGACY_REASON = "legacy_owner_import"


def legacy_transaction_for_message(conn, *, workspace_id: str, provider_message_id: str) -> int | None:
    """Existing transaction the legacy reader created from this Gmail message, if any."""
    present = conn.execute(
        "SELECT to_regclass('public.email_transaction_candidates') AS present"
    ).fetchone()
    if not present or not present.get("present"):
        return None
    row = conn.execute(
        """SELECT t.id
           FROM email_ingested_messages m
           JOIN email_transaction_candidates c
             ON c.email_message_id=m.id AND c.workspace_id=m.workspace_id
           JOIN transactions t
             ON t.id=COALESCE(c.transaction_id,c.canonical_transaction_id)
            AND t.workspace_id=m.workspace_id
           WHERE m.workspace_id=%s AND m.provider='gmail' AND m.provider_message_id=%s
           ORDER BY c.id LIMIT 1""",
        (workspace_id, provider_message_id),
    ).fetchone()
    return int(row["id"]) if row else None


def mark_legacy_duplicate(conn, *, candidate_id: int, resolution: dict[str, Any]) -> dict[str, Any]:
    """Resolve a still-pending candidate as already imported by the legacy reader."""
    if resolution.get("status") != "pending":
        return resolution
    conn.execute(
        """UPDATE finva_email_candidates
           SET status='duplicate',resolution_reason=%s,updated_at=NOW()
           WHERE id=%s AND status='pending' AND transaction_id IS NULL""",
        (LEGACY_REASON, candidate_id),
    )
    return {"status": "duplicate", "resolution_reason": LEGACY_REASON}
