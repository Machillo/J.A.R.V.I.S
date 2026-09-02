from __future__ import annotations

import re
import unicodedata
from typing import Any


def _normalize(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip().lower()


def _account_last4(value: str | None) -> str | None:
    matches = re.findall(r"\d{4}", value or "")
    return matches[-1] if matches else None


def _tables_available(conn) -> bool:
    row = conn.execute(
        """
        SELECT
            to_regclass('public.email_financial_accounts') IS NOT NULL AS accounts_ready,
            to_regclass('public.email_classification_rules') IS NOT NULL AS rules_ready
        """
    ).fetchone()
    return bool(row and row["accounts_ready"] and row["rules_ready"])


def _matches_text(value: str, pattern: str, mode: str) -> bool:
    normalized_value = _normalize(value)
    normalized_pattern = _normalize(pattern)
    if not normalized_pattern:
        return True
    if mode == "exact":
        return normalized_value == normalized_pattern
    if mode == "regex":
        try:
            return re.search(pattern, value or "", re.I) is not None
        except re.error:
            return False
    return normalized_pattern in normalized_value


def apply_workspace_email_rules(conn, workspace_id: str, parsed: dict[str, Any]) -> dict[str, Any]:
    """Apply private workspace knowledge after deterministic email parsing."""
    parsed = dict(parsed or {})
    parsed.setdefault("auto_commit_allowed", False)
    if parsed.get("email_kind") != "movement" or not _tables_available(conn):
        return parsed

    rows = conn.execute(
        """
        SELECT account_key, account_last4, ownership, display_name
        FROM email_financial_accounts
        WHERE workspace_id = %s AND active = TRUE
        """,
        (workspace_id,),
    ).fetchall()
    accounts = {str(row["account_last4"]): dict(row) for row in rows}
    origin = accounts.get(_account_last4(parsed.get("origin_account")) or "")
    destination = accounts.get(_account_last4(parsed.get("destination_account")) or "")
    parsed["origin_account_key"] = origin.get("account_key") if origin else None
    parsed["destination_account_key"] = destination.get("account_key") if destination else None

    if origin and destination and origin["ownership"] == "own" and destination["ownership"] == "own":
        parsed.update(
            email_kind="ignored",
            transaction_type="internal_transfer",
            category="Transferencia interna",
            confidence=1.0,
            auto_commit_allowed=False,
            ignore_reason="Transferencia entre cuentas propias reconocida por el perfil privado.",
            confidence_reason="Ambos extremos pertenecen al mismo workspace.",
        )
        return parsed

    rules = conn.execute(
        """
        SELECT * FROM email_classification_rules
        WHERE workspace_id = %s AND active = TRUE
        ORDER BY priority DESC, id ASC
        """,
        (workspace_id,),
    ).fetchall()
    description = str(parsed.get("raw_description") or parsed.get("description") or "")
    direction = str(parsed.get("movement_direction") or "unknown")

    for raw_rule in rules:
        rule = dict(raw_rule)
        if rule.get("direction") and rule["direction"] != direction:
            continue
        if rule.get("origin_account_key") and rule["origin_account_key"] != parsed.get("origin_account_key"):
            continue
        if rule.get("destination_account_key") and rule["destination_account_key"] != parsed.get("destination_account_key"):
            continue
        if not _matches_text(description, rule.get("concept_pattern") or "", rule.get("match_mode") or "contains"):
            continue

        action = rule.get("action") or "review"
        reason = rule.get("review_reason") or f"Regla personal aplicada: {rule.get('name') or rule.get('id')}"
        if action == "ignore":
            parsed.update(
                email_kind="ignored",
                transaction_type="internal_transfer",
                category="Transferencia interna",
                confidence=1.0,
                auto_commit_allowed=False,
                ignore_reason=reason,
                confidence_reason=reason,
            )
            return parsed

        if rule.get("output_description"):
            parsed["description"] = rule["output_description"]
        if rule.get("transaction_type"):
            parsed["transaction_type"] = rule["transaction_type"]
        if rule.get("category"):
            parsed["category"] = rule["category"]
        parsed["confidence"] = 1.0 if action == "classify" else min(float(parsed.get("confidence") or 0), 0.5)
        parsed["auto_commit_allowed"] = bool(rule.get("allow_auto_commit")) and action == "classify"
        parsed["confidence_reason"] = reason
        parsed["personal_rule_id"] = int(rule["id"])
        parsed["personal_rule_metadata"] = rule.get("metadata") or {}
        return parsed

    parsed["auto_commit_allowed"] = False
    return parsed
