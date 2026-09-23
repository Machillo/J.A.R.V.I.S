from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timedelta
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


def _possible_cross_source_match(conn, candidate: dict[str, Any]) -> int | None:
    """Link, but never auto-discard, a weaker email-to-statement match."""
    if candidate.get("source_type") != "statement":
        return None
    rows = conn.execute(
        """SELECT id,description,source_account_reference,destination_account_reference
           FROM finva_email_candidates
           WHERE account_id=%s AND workspace_id=%s AND source_type<>'statement'
             AND transaction_date=%s AND amount=%s AND currency=%s AND bank=%s
             AND status<>'rejected'
           ORDER BY id""",
        (
            candidate["account_id"], candidate["workspace_id"], candidate["transaction_date"],
            candidate["amount"], candidate.get("currency") or "CRC", candidate.get("bank") or "unknown",
        ),
    ).fetchall()
    description = _plain(candidate.get("description"))
    account = _last4(candidate.get("source_account_reference") or candidate.get("destination_account_reference"))
    matches = []
    for row in rows:
        row = dict(row)
        other_account = _last4(row.get("source_account_reference") or row.get("destination_account_reference"))
        if _plain(row.get("description")) == description and (not account or not other_account or account == other_account):
            matches.append(int(row["id"]))
    return matches[0] if len(matches) == 1 else None


def _paired_owned_transfer(conn, candidate: dict[str, Any], own_account_id: int | None) -> int | None:
    """Match opposite notifications only with two distinct confirmed owned accounts.

    A same-amount purchase must never disappear merely because a transfer was
    made that day. Require an explicit endpoint, shared bank reference or close
    transaction times; ambiguous matches stay pending for review.
    """
    direction = (candidate.get("raw_payload") or {}).get("movement_direction") or candidate.get("movement_direction")
    if candidate.get("movement_kind") != "transfer" or direction not in {"in", "out"} or not own_account_id:
        return None
    own_reference = _last4(candidate.get("source_account_reference") if direction == "out" else candidate.get("destination_account_reference"))
    if not own_reference:
        return None
    opposite = "in" if direction == "out" else "out"
    rows = conn.execute(
        """SELECT c.id,c.transaction_time,c.transaction_date,c.external_reference,
                  c.source_account_reference,c.destination_account_reference,
                  a.account_last4
           FROM finva_email_candidates c
           JOIN account_balances a ON a.id=c.financial_account_id
           WHERE c.account_id=%s AND c.workspace_id=%s AND c.id<>%s
             AND c.transaction_date BETWEEN %s::date-1 AND %s::date+1
             AND c.amount=%s AND c.currency=%s AND c.movement_kind='transfer'
             AND COALESCE(c.raw_payload->>'movement_direction',c.movement_direction)=%s
             AND c.status='pending' AND c.transaction_id IS NULL
             AND a.id<>%s AND a.account_id=%s AND a.workspace_id=%s
             AND a.ownership_status='own' AND a.is_active=TRUE
           ORDER BY c.id""",
        (candidate["account_id"], candidate["workspace_id"], candidate["id"],
         candidate["transaction_date"], candidate["transaction_date"], candidate["amount"],
         candidate.get("currency") or "CRC", opposite, own_account_id,
         candidate["account_id"], candidate["workspace_id"]),
    ).fetchall()
    matches = []
    for row in rows:
        other = dict(row)
        other_own = _last4(other["account_last4"])
        if not other_own or other_own == own_reference:
            continue
        if direction == "out":
            destination, origin = _last4(candidate.get("destination_account_reference")), _last4(other.get("source_account_reference"))
        else:
            destination, origin = _last4(other.get("destination_account_reference")), _last4(candidate.get("source_account_reference"))
        if destination and destination != (other_own if direction == "out" else own_reference):
            continue
        if origin and origin != (own_reference if direction == "out" else other_own):
            continue
        reference = _plain(candidate.get("external_reference"))
        shared_reference = reference and reference == _plain(other.get("external_reference"))
        cross_reference = bool(destination and origin)
        close_time = False
        if candidate.get("transaction_time") and other.get("transaction_time"):
            try:
                first = datetime.fromisoformat(f"{candidate['transaction_date']}T{str(candidate['transaction_time'])[:8]}")
                second = datetime.fromisoformat(f"{other['transaction_date']}T{str(other['transaction_time'])[:8]}")
                close_time = abs(first - second) <= timedelta(minutes=30)
            except ValueError:
                pass
        if shared_reference or cross_reference or close_time:
            matches.append(int(other["id"]))
    return matches[0] if len(matches) == 1 else None


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

    possible_match_id = _possible_cross_source_match(conn, candidate)
    source_id = _confirmed_account(conn, candidate, candidate.get("source_account_reference"))
    destination_id = _confirmed_account(conn, candidate, candidate.get("destination_account_reference"))
    is_internal = bool(source_id and destination_id and source_id != destination_id)
    original_direction = (candidate.get("raw_payload") or {}).get("movement_direction") or candidate.get("movement_direction")
    pair_id = _paired_owned_transfer(
        conn, candidate, source_id if original_direction == "out" else destination_id,
    )
    is_internal = is_internal or bool(pair_id)
    reason = "paired_owned_transfer" if pair_id else "confirmed_owned_endpoints" if is_internal else "possible_cross_source_match" if possible_match_id else None
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
               related_candidate_id=%s,resolution_reason=%s,updated_at=NOW()
           WHERE id=%s""",
        (
            fingerprint, is_internal, is_internal, base_type, is_internal, base_direction,
            is_internal, base_category, pair_id or possible_match_id, reason, candidate_id,
        ),
    )
    if pair_id:
        conn.execute(
            """UPDATE finva_email_candidates SET is_internal_transfer=TRUE,
                   transaction_type='internal_transfer',movement_direction='internal',
                   category='Movimiento interno',related_candidate_id=%s,
                   resolution_reason='paired_owned_transfer',updated_at=NOW()
               WHERE id=%s AND account_id=%s AND workspace_id=%s
                 AND status='pending' AND transaction_id IS NULL""",
            (candidate_id, pair_id, candidate["account_id"], candidate["workspace_id"]),
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
