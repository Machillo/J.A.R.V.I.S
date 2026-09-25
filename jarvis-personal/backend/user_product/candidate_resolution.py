from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from backend.user_product.movement_direction import canonical_direction


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


# Notification <-> statement reconciliation (deterministic, Phase 1E follow-up).
CROSS_SOURCE_REASON = "same_movement_other_source"
RECONCILED_REASON = "reconciled_with_existing_transaction"
SAME_STATEMENT_ROW_REASON = "same_statement_row"
POSSIBLE_MATCH_REASON = "possible_cross_source_match"
CROSS_SOURCE_REASONS = (CROSS_SOURCE_REASON, RECONCILED_REASON)
# Statement rows can post a few days after the notification; only a review hint.
POSSIBLE_MATCH_DAYS = 3
TRANSFER_TYPES = frozenset({"transfer", "internal_transfer"})
# Words that differ between a notification and a statement for the same merchant.
DESCRIPTION_NOISE = frozenset({
    "sa", "srl", "ltda", "inc", "cia", "de", "del", "la", "el", "los", "las", "y", "en",
    "compra", "pago", "cr", "costa", "rica", "sj", "www", "com",
})


def _merchant_tokens(value: Any) -> set[str]:
    return {token for token in _plain(value).split()
            if len(token) >= 2 and not token.isdigit() and token not in DESCRIPTION_NOISE}


def _same_merchant(first: Any, second: Any) -> bool:
    """One normalized description is contained in the other (accents, case, legal suffixes).

    A single generic word ("UBER" vs "UBER EATS") is not enough: it needs two
    shared words or the same words exactly.
    """
    left, right = _merchant_tokens(first), _merchant_tokens(second)
    if not left or not right:
        return False
    small, large = sorted((left, right), key=len)
    return small <= large and any(len(token) >= 3 for token in small) and (len(small) >= 2 or small == large)


def _related_merchant(first: Any, second: Any) -> bool:
    """Review hint only: shared word, or one name inside the other ignoring spaces
    ("AUTO MERCADO" / "AUTOMERCADO", truncated "ZAPOT" / "ZAPOTE")."""
    left, right = _merchant_tokens(first), _merchant_tokens(second)
    if not left or not right or any(len(token) >= 3 for token in left & right):
        return True
    compact_short, compact_long = _plain(first).replace(" ", ""), _plain(second).replace(" ", "")
    compact_short, compact_long = sorted((compact_short, compact_long), key=len)
    return len(compact_short) >= 4 and compact_short in compact_long


def _money_key(candidate: dict[str, Any]) -> tuple[str, Decimal] | None:
    """Amount in the movement's original currency: a USD purchase converted to colones
    by two sources at different rates is compared in USD, never against colones."""
    original = str(candidate.get("original_currency") or "").upper()
    currency = str(candidate.get("currency") or "CRC").upper()
    if original and original != currency and candidate.get("original_amount") is not None:
        return original, Decimal(str(candidate["original_amount"])).quantize(Decimal("0.01"))
    if candidate.get("amount") is None:
        return None
    return currency, Decimal(str(candidate["amount"])).quantize(Decimal("0.01"))


def _movement_type(candidate: dict[str, Any]) -> str:
    return str((candidate.get("raw_payload") or {}).get("transaction_type") or candidate.get("transaction_type") or "")


def _transfer_like(candidate: dict[str, Any]) -> bool:
    return candidate.get("movement_kind") == "transfer" or _movement_type(candidate) in TRANSFER_TYPES \
        or str(candidate.get("transaction_type") or "") in TRANSFER_TYPES


def _endpoint(candidate: dict[str, Any]) -> str:
    return _last4(candidate.get("source_account_reference") or candidate.get("destination_account_reference"))


def _root(conn, candidate: dict[str, Any], start_id: int) -> int | None:
    """Follow duplicate links to the row that represents the movement.

    Duplicates always point at a root, so re-resolving a released row can never
    make two duplicates point at each other and hide the movement.
    """
    seen, current = {int(candidate["id"])}, int(start_id)
    for _ in range(10):
        if current in seen:
            return None
        seen.add(current)
        row = conn.execute(
            """SELECT id,status,related_candidate_id FROM finva_email_candidates
               WHERE id=%s AND account_id=%s AND workspace_id=%s""",
            (current, candidate["account_id"], candidate["workspace_id"]),
        ).fetchone()
        if not row:
            return None
        if row["status"] != "duplicate" or not row.get("related_candidate_id"):
            return int(row["id"])
        current = int(row["related_candidate_id"])
    return None


def _same_statement_row(conn, candidate: dict[str, Any]) -> int | None:
    """The same row of the same statement document (resent or forwarded) is one movement;
    the oldest copy is the root, also when rows are resolved again after a release."""
    if candidate.get("source_type") != "statement" or not candidate.get("source_record_key"):
        return None
    row = conn.execute(
        """SELECT id FROM finva_email_candidates
           WHERE account_id=%s AND workspace_id=%s AND source_record_key=%s AND id<%s
           ORDER BY id LIMIT 1""",
        (candidate["account_id"], candidate["workspace_id"], candidate["source_record_key"], candidate["id"]),
    ).fetchone()
    return _root(conn, candidate, int(row["id"])) if row else None


def cross_source_resolution(conn, candidate: dict[str, Any]) -> tuple[str | None, int | None, str | None]:
    """Match a statement row against notifications (or the reverse) deterministically.

    Always required: same account/workspace, the other source type, same bank,
    same currency (CRC and USD are never mixed), same exact amount, same movement
    type, a still-usable counterpart (pending or saved) not already claimed by
    another row. A *strong* match additionally needs the same last 4 digits and
    either the same bank reference, or the same date and an equivalent
    normalized description, and must be the only one. It becomes a duplicate of
    the counterpart, so the movement is saved at most once. Transfers are never
    collapsed automatically. Anything weaker or ambiguous stays pending for the
    user with the counterpart linked as a hint.
    """
    statement = candidate.get("source_type") == "statement"
    rows = [dict(row) for row in conn.execute(
        f"""SELECT c.id,c.status,c.transaction_id,c.transaction_date,c.description,c.transaction_type,
                  c.movement_kind,c.external_reference,c.source_account_reference,c.destination_account_reference,
                  c.amount,c.currency,c.original_amount,c.original_currency
           FROM finva_email_candidates c
           WHERE c.account_id=%s AND c.workspace_id=%s AND c.id<>%s
             AND c.source_type{"<>" if statement else "="}'statement'
             AND (c.amount=%s OR c.original_amount=%s) AND c.currency=%s AND c.bank=%s
             AND c.transaction_date BETWEEN %s::date-{POSSIBLE_MATCH_DAYS} AND %s::date+{POSSIBLE_MATCH_DAYS}
             AND c.status IN ('pending','confirmed','auto_saved')
             AND NOT EXISTS (
                 SELECT 1 FROM finva_email_candidates claimed
                 WHERE claimed.related_candidate_id=c.id AND claimed.id<>%s AND claimed.status='duplicate'
                   AND (claimed.resolution_reason IN (%s,%s)
                        OR (claimed.resolution_reason='same_semantic_movement' AND claimed.source_type<>c.source_type)))
           ORDER BY c.id""",
        (candidate["account_id"], candidate["workspace_id"], candidate["id"],
         candidate["amount"], candidate.get("original_amount"), candidate.get("currency") or "CRC",
         candidate.get("bank") or "unknown", candidate["transaction_date"], candidate["transaction_date"],
         candidate["id"], *CROSS_SOURCE_REASONS),
    ).fetchall()]
    kind, money = _movement_type(candidate), _money_key(candidate)
    rows = [row for row in rows if _movement_type(row) == kind and money and _money_key(row) == money]
    account, reference = _endpoint(candidate), _plain(candidate.get("external_reference"))
    strong = [] if _transfer_like(candidate) else [
        row for row in rows
        if not _transfer_like(row) and account and _endpoint(row) == account and (
            (reference and _plain(row.get("external_reference")) == reference)
            or (str(row["transaction_date"])[:10] == str(candidate["transaction_date"])[:10]
                and _same_merchant(row.get("description"), candidate.get("description")))
        )
    ]
    if len(strong) == 1:
        # Lock the counterpart: a concurrent reject waits for this transaction (or this
        # one sees it rejected), so a row is never left pointing at a rejected movement.
        match = conn.execute(
            """SELECT id,status,transaction_id FROM finva_email_candidates
               WHERE id=%s AND account_id=%s AND workspace_id=%s FOR UPDATE""",
            (int(strong[0]["id"]), candidate["account_id"], candidate["workspace_id"]),
        ).fetchone()
        if not match or match["status"] not in ("pending", "confirmed", "auto_saved"):
            return None, None, None
        return "duplicate", int(match["id"]), RECONCILED_REASON if match.get("transaction_id") else CROSS_SOURCE_REASON
    possible = strong or [
        row for row in rows
        if (not account or not _endpoint(row) or _endpoint(row) == account)
        and _related_merchant(row.get("description"), candidate.get("description"))
    ]
    if possible:
        return "pending", int(possible[0]["id"]) if len(possible) == 1 else None, POSSIBLE_MATCH_REASON
    return None, None, None


def release_cross_source_duplicates(conn, *, candidate_id: int, account_id: str, workspace_id: str) -> int:
    """A rejected row no longer covers the copies from the *other* source (statement
    vs notification) nor copies of those rows: all go back to review and are
    resolved again, oldest first. Same-source copies of the rejected notification
    stay rejected with it."""
    rows = conn.execute(
        """SELECT id FROM finva_email_candidates
           WHERE account_id=%s AND workspace_id=%s AND related_candidate_id=%s AND status='duplicate'
             AND (resolution_reason IN (%s,%s,%s)
                  OR (resolution_reason='same_semantic_movement'
                      AND source_type<>(SELECT source_type FROM finva_email_candidates WHERE id=%s)))
           ORDER BY id""",
        (account_id, workspace_id, candidate_id, *CROSS_SOURCE_REASONS, SAME_STATEMENT_ROW_REASON, candidate_id),
    ).fetchall()
    released = [int(row["id"]) for row in rows]
    for released_id in released:
        conn.execute(
            """UPDATE finva_email_candidates
               SET status='pending',related_candidate_id=NULL,resolution_reason=NULL,updated_at=NOW()
               WHERE id=%s AND account_id=%s AND workspace_id=%s""",
            (released_id, account_id, workspace_id),
        )
    for released_id in released:
        resolve_candidate(conn, released_id)
    return len(released)


def _paired_owned_transfer(conn, candidate: dict[str, Any], own_account_id: int | None) -> int | None:
    """Match opposite notifications only with two distinct confirmed owned accounts.

    A same-amount purchase must never disappear merely because a transfer was
    made that day. Require an explicit endpoint, shared bank reference or close
    transaction times; ambiguous matches stay pending for review.
    """
    direction = canonical_direction((candidate.get("raw_payload") or {}).get("movement_direction") or candidate.get("movement_direction"))
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
    same_row_id = _same_statement_row(conn, candidate)
    if same_row_id:
        conn.execute(
            """UPDATE finva_email_candidates
               SET semantic_fingerprint=%s,status='duplicate',related_candidate_id=%s,
                   resolution_reason=%s,updated_at=NOW()
               WHERE id=%s""",
            (fingerprint, same_row_id, SAME_STATEMENT_ROW_REASON, candidate_id),
        )
        return {"status": "duplicate", "related_candidate_id": same_row_id}
    duplicate = None
    if fingerprint:
        duplicate = conn.execute(
            """SELECT id FROM finva_email_candidates
               WHERE account_id=%s AND workspace_id=%s AND semantic_fingerprint=%s
                 AND id<%s AND status<>'rejected'
               ORDER BY id LIMIT 1""",
            (candidate["account_id"], candidate["workspace_id"], fingerprint, candidate_id),
        ).fetchone()
    duplicate_id = _root(conn, candidate, int(duplicate["id"])) if duplicate else None
    if duplicate_id:
        conn.execute(
            """UPDATE finva_email_candidates
               SET semantic_fingerprint=%s,status='duplicate',related_candidate_id=%s,
                   resolution_reason='same_semantic_movement',updated_at=NOW()
               WHERE id=%s""",
            (fingerprint, duplicate_id, candidate_id),
        )
        return {"status": "duplicate", "related_candidate_id": duplicate_id}

    cross_status, cross_id, cross_reason = cross_source_resolution(conn, candidate)
    if cross_status == "duplicate":
        conn.execute(
            """UPDATE finva_email_candidates
               SET semantic_fingerprint=%s,status='duplicate',related_candidate_id=%s,
                   resolution_reason=%s,updated_at=NOW()
               WHERE id=%s""",
            (fingerprint, cross_id, cross_reason, candidate_id),
        )
        return {"status": "duplicate", "related_candidate_id": cross_id}
    possible_match_id = cross_id if cross_reason == POSSIBLE_MATCH_REASON else None
    source_id = _confirmed_account(conn, candidate, candidate.get("source_account_reference"))
    destination_id = _confirmed_account(conn, candidate, candidate.get("destination_account_reference"))
    is_internal = bool(source_id and destination_id and source_id != destination_id)
    original_direction = canonical_direction((candidate.get("raw_payload") or {}).get("movement_direction") or candidate.get("movement_direction"))
    pair_id = _paired_owned_transfer(
        conn, candidate, source_id if original_direction == "out" else destination_id,
    )
    is_internal = is_internal or bool(pair_id)
    reason = "paired_owned_transfer" if pair_id else "confirmed_owned_endpoints" if is_internal else POSSIBLE_MATCH_REASON if cross_reason == POSSIBLE_MATCH_REASON else None
    raw = candidate.get("raw_payload") or {}
    base_type = str(raw.get("transaction_type") or candidate.get("transaction_type") or "transfer")
    # raw_payload may predate the canonical contract: never write a value the CHECK rejects.
    base_direction = canonical_direction(raw.get("movement_direction") or candidate.get("movement_direction"), base_type)
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
