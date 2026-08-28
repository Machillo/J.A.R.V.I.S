from __future__ import annotations

import re
from datetime import time
from typing import Any

from .normalization import is_generic_mirror_description, normalize_description


def extract_time_from_notes(notes: str | None) -> str | None:
    match = re.search(r"hora:\s*(\d{1,2}:\d{2}(?::\d{2})?)", notes or "", re.I)
    if not match:
        return None
    value = match.group(1)
    parts = value.split(":")
    if len(parts) == 2:
        value += ":00"
    return value


def canonical_score(description: str, account: str | None = None, source: str | None = None) -> int:
    """Higher score means a better primary row for duplicate groups.

    Prefer direct merchants/services over mirror rows from investment accounts,
    generic debit notices or balance movements.
    """
    normalized = normalize_description(description)
    score = 50
    if normalized and normalized != "SIN DESCRIPCION":
        score += 10
    if is_generic_mirror_description(description):
        score -= 40
    clean = f"{description or ''} {account or ''} {source or ''}".upper()
    if "SINPE" in clean:
        score += 5
    if "BAC" in clean and "TARJETA" in clean:
        score += 8
    if any(token in clean for token in ["OPENAI", "APPLE", "UBER", "TACO", "BARBER", "TEMU", "SHEIN", "SUPERCELL"]):
        score += 15
    return score


def resolve_transaction_time(candidate: dict[str, Any]) -> str | None:
    value = candidate.get("transaction_time") or extract_time_from_notes(candidate.get("notes"))
    if not value:
        return None
    if isinstance(value, time):
        return value.isoformat()
    value = str(value)
    if re.fullmatch(r"\d{1,2}:\d{2}", value):
        return f"{value}:00"
    if re.fullmatch(r"\d{1,2}:\d{2}:\d{2}", value):
        return value
    return None


def find_semantic_duplicate(conn, user_id: int, candidate: dict[str, Any], current_fingerprint: str | None = None):
    """Find duplicate candidates using amount + same date + ±10 min.

    If either side lacks transaction_time, we still match same-day movements but
    rely on canonical scoring and status review instead of silently saving both.
    """
    tx_time = resolve_transaction_time(candidate)
    rows = conn.execute(
        """
        SELECT id, description, account, source, created_at,
               CASE
                 WHEN transaction_time IS NULL OR %s::time IS NULL THEN 1
                 WHEN ABS(EXTRACT(EPOCH FROM ((transaction_date + transaction_time) - (%s::date + %s::time)))) <= 600 THEN 1
                 ELSE 0
               END AS in_window
        FROM email_transaction_candidates
        WHERE user_id = %s
          AND transaction_date = %s
          AND ABS(amount - %s) < 0.01
          AND status IN ('pending','confirmed','auto_saved')
          AND (%s IS NULL OR fingerprint <> %s)
        ORDER BY created_at ASC
        """,
        (
            tx_time,
            candidate["transaction_date"],
            tx_time,
            user_id,
            candidate["transaction_date"],
            candidate["amount"],
            current_fingerprint,
            current_fingerprint,
        ),
    ).fetchall()
    candidates = [row for row in rows if int(row["in_window"] or 0) == 1]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda row: (-canonical_score(row["description"], row["account"], row["source"]), row["created_at"]),
    )[0]
