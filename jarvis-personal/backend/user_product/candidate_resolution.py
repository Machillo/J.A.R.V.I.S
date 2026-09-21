from __future__ import annotations

import hashlib
import re
import unicodedata
from decimal import Decimal
from typing import Any


def _plain(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char)).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _last4(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits[-4:] if len(digits) >= 4 else ""


def semantic_fingerprint(candidate: dict[str, Any]) -> str | None:
    """Build a conservative source-independent identity for one movement.

    A bank reference is preferred. Without one, time, an account endpoint and
    normalized description are required so same-day equal purchases are not
    silently collapsed.
    """
    amount = candidate.get("amount")
    transaction_date = candidate.get("transaction_date")
    if amount is None or not transaction_date:
        return None
    reference = _plain(candidate.get("external_reference"))
    bank = _plain(candidate.get("bank"))
    currency = str(candidate.get("currency") or "CRC").upper()
    amount_text = format(Decimal(str(amount)).quantize(Decimal("0.01")), "f")
    if reference:
        evidence = ["ref", bank, str(transaction_date), amount_text, currency, reference]
    else:
        transaction_time = str(candidate.get("transaction_time") or "")[:8]
        account = _last4(candidate.get("source_account_reference") or candidate.get("destination_account_reference"))
        description = _plain(candidate.get("description"))
        if not transaction_time or not account or not description:
            return None
        evidence = ["movement", bank, str(transaction_date), transaction_time, amount_text, currency, account, description]
    return hashlib.sha256("|".join(evidence).encode("utf-8")).hexdigest()


def _confirmed_account(conn, candidate: dict[str, Any], reference: Any) -> int | None:
    last4 = _last4(reference)
    if not last4:
        return None
    row = conn.execute(
        """SELECT id FROM account_balances
           WHERE account_id=%s AND workspace_id=%s AND ownership_status='own'
             AND is_active=TRUE AND account_last4=%s AND currency=%s
           ORDER BY id LIMIT 1""",
        (candidate["account_id"], candidate["workspace_id"], last4, candidate.get("currency") or "CRC"),
    ).fetchone()
    return int(row["id"]) if row else None


def resolve_candidate(conn, candidate_id: int) -> dict[str, Any]:
    """Resolve semantic duplicates and own-account transfers conservatively."""
    row = conn.execute(
        """SELECT * FROM finva_email_candidates WHERE id=%s FOR UPDATE""",
        (candidate_id,),
    ).fetchone()
    if not row:
        return {"status": "missing"}
    candidate = dict(row)
    fingerprint = semantic_fingerprint(candidate)
    duplicate = None
    if fingerprint:
        duplicate = conn.execute(
            """SELECT id FROM finva_email_candidates
               WHERE account_id=%s AND workspace_id=%s AND semantic_fingerprint=%s
                 AND id<>%s AND status<>'rejected'
               ORDER BY id LIMIT 1""",
            (candidate["account_id"], candidate["workspace_id"], fingerprint, candidate_id),
        ).fetchone()
    if duplicate:
        duplicate_id = int(duplicate["id"])
        conn.execute(
            """UPDATE finva_email_candidates
               SET semantic_fingerprint=%s,status='duplicate',related_candidate_id=%s,
                   resolution_reason='same_semantic_movement',updated_at=NOW()
               WHERE id=%s""",
            (fingerprint, duplicate_id, candidate_id),
        )
        return {"status": "duplicate", "related_candidate_id": duplicate_id}

    source_id = _confirmed_account(conn, candidate, candidate.get("source_account_reference"))
    destination_id = _confirmed_account(conn, candidate, candidate.get("destination_account_reference"))
    is_internal = bool(source_id and destination_id and source_id != destination_id)
    reason = "confirmed_owned_endpoints" if is_internal else None
    raw = candidate.get("raw_payload") or {}
    base_type = str(raw.get("transaction_type") or candidate.get("transaction_type") or "transfer")
    base_direction = str(raw.get("movement_direction") or candidate.get("movement_direction") or "unknown")
    base_category = str(raw.get("category") or candidate.get("category") or "Transferencia")
    conn.execute(
        """UPDATE finva_email_candidates
           SET semantic_fingerprint=%s,is_internal_transfer=%s,
               transaction_type=CASE WHEN %s THEN 'internal_transfer' ELSE %s END,
               movement_direction=CASE WHEN %s THEN 'internal' ELSE %s END,
               category=CASE WHEN %s THEN 'Movimiento interno' ELSE %s END,
               resolution_reason=%s,updated_at=NOW()
           WHERE id=%s""",
        (
            fingerprint, is_internal, is_internal, base_type, is_internal, base_direction,
            is_internal, base_category, reason, candidate_id,
        ),
    )
    return {"status": "internal_transfer" if is_internal else "pending"}


def reevaluate_workspace_candidates(conn, *, account_id: str, workspace_id: str) -> int:
    rows = conn.execute(
        """SELECT id FROM finva_email_candidates
           WHERE account_id=%s AND workspace_id=%s AND status='pending'
             AND movement_kind='transfer'
           ORDER BY id""",
        (account_id, workspace_id),
    ).fetchall()
    for row in rows:
        resolve_candidate(conn, int(row["id"]))
    return len(rows)
