"""The one representation of a movement's direction.

finva_email_candidates.movement_direction is constrained by
finva_candidates_direction_check to exactly DIRECTIONS (see
database/migrations/20260921170000_phase_1b_canonical_financial_candidates.sql).
Every writer, and every reader that writes a value back (the candidate
resolution re-applies the direction stored in raw_payload), goes through
canonical_direction, so no producer value outside the domain can reach the table.
"""
from __future__ import annotations

from typing import Any

DIRECTIONS = ("in", "out", "internal", "unknown")
# When the producer could not tell, the transaction type decides where it can.
TYPE_DIRECTION = {"expense": "out", "income": "in", "debt_payment": "out"}


def canonical_direction(value: Any, transaction_type: Any = None) -> str:
    direction = str(value or "").strip().lower()
    if direction not in DIRECTIONS:
        direction = "unknown"
    if direction == "unknown":
        direction = TYPE_DIRECTION.get(str(transaction_type or "").strip().lower(), "unknown")
    return direction
