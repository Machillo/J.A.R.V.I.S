"""The Owner's pension balances, from his monthly "Estado de cuenta BAC Pensiones" (Owner only).

The PDF's summary lists each fund with its balance. They replace the ROP in Retiro and keep the FCL
beside it, so they update by themselves. Only the two balances and the statement's month are stored,
never the document or its movements. Deterministic text rules, no generative AI. An older statement
never replaces a newer one, and a fund the document doesn't show keeps its value (unknown is not 0).
"""
from __future__ import annotations

import json
import re
from email.utils import parseaddr
from typing import Any

from backend.user_product.retirement import PREFERENCE_KEY

SENDER = "estadosdecuenta@baccredomatic.cr"
_MONEY = r"(\d{1,3}(?:,\d{3})*\.\d{2})"
_ROP = re.compile(r"R[ÉE]GIMEN OBLIGATORIO DE PENSIONES\s+\S+\s+" + _MONEY + r"\s+CRC", re.I)
_FCL = re.compile(r"FONDO DE CAPITALIZACI[ÓO]N LABORAL \(FCL\)\s+\S+\s+" + _MONEY + r"\s+CRC", re.I)
_FILE_MONTH = re.compile(r"EstadoCta_\d+_(20\d{2})(0[1-9]|1[0-2])_", re.I)


def _amount(match: re.Match | None) -> float | None:
    return float(match.group(1).replace(",", "")) if match else None


def parse_statement(subject: str, sender: str, text: str, attachment_names: list[str], received_at: str | None) -> dict[str, Any] | None:
    """The balances and the month of a pension statement; None for any other mail."""
    # The real address, never a display name an attacker controls.
    if parseaddr(sender or "")[1].lower() != SENDER or "pensiones" not in (subject or "").lower():
        return None
    rop, fcl = _amount(_ROP.search(text or "")), _amount(_FCL.search(text or ""))
    if rop is None and fcl is None:
        return None
    named = next((found for found in map(_FILE_MONTH.search, attachment_names or []) if found), None)
    received_month = str(received_at or "")[:7]
    month = f"{named.group(1)}-{named.group(2)}" if named else received_month
    if not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", month):
        return None
    # A statement can't be newer than its mail. Without this check, one file named far in the
    # future would block every real statement, because an older month never replaces a newer one.
    if not received_month or month > received_month:
        return None
    return {"rop_balance": rop, "fcl_balance": fcl, "month": month}


def apply_statement(conn, workspace_id: str, statement: dict[str, Any]) -> bool:
    """Stores the balances in the workspace's retirement preference, inside the caller's transaction.
    Returns whether it changed anything: the same or an older month does nothing."""
    row = conn.execute(
        "SELECT preference_value FROM user_preferences WHERE workspace_id=%s AND preference_key=%s FOR UPDATE",
        (workspace_id, PREFERENCE_KEY),
    ).fetchone()
    stored = row["preference_value"] if row and isinstance(row["preference_value"], dict) else {}
    if str(stored.get("pensions_as_of") or "") >= statement["month"]:
        return False
    updated = {**stored, "pensions_as_of": statement["month"]}
    for key in ("rop_balance", "fcl_balance"):
        if statement.get(key) is not None:
            updated[key] = statement[key]
    conn.execute(
        """INSERT INTO user_preferences (workspace_id, preference_key, preference_value) VALUES (%s, %s, %s::jsonb)
           ON CONFLICT (workspace_id, preference_key) DO UPDATE SET preference_value = EXCLUDED.preference_value, updated_at = NOW()""",
        (workspace_id, PREFERENCE_KEY, json.dumps(updated, ensure_ascii=False)),
    )
    return True
