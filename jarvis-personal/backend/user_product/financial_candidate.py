from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.finance.category_catalog import normalize_category


PARSER_NAME = "jarvis_financial_email"
PARSER_VERSION = "1"


def _movement_kind(parsed: dict[str, Any]) -> str:
    """Describe what happened without equating every debit with an expense."""
    explicit = str(parsed.get("movement_kind") or "").strip().lower()
    if explicit:
        return explicit
    prefix = str(parsed.get("dedupe_key") or "").split("|", 1)[0]
    if prefix == "bac_card":
        return "card_purchase"
    if prefix in {"sinpe", "sinpe_movil_in", "sinpe_internal", "multimoney", "multimoney_internal"}:
        return "transfer"
    if str(parsed.get("transaction_type") or "") == "debt_payment":
        return "debt_payment"
    return "other"


def canonical_candidate(
    parsed: dict[str, Any],
    *,
    provider_message_id: str,
    subject: str,
    movement_index: int = 0,
) -> dict[str, Any]:
    """Adapt a producer payload into FINVA's provider-independent candidate shape."""
    transaction_type = str(parsed.get("transaction_type") or "")
    original_currency = str(parsed.get("original_currency") or "").upper() or None
    # Parser amounts are normalized to CRC today; preserve the source currency
    # separately so consumers never interpret a converted amount as USD.
    currency = str(parsed.get("currency") or "CRC").upper()
    direction = str(parsed.get("movement_direction") or "unknown").lower()
    if direction not in {"in", "out", "internal", "unknown"}:
        direction = "unknown"
    if direction == "unknown":
        direction = {"expense": "out", "income": "in", "debt_payment": "out"}.get(
            transaction_type,
            "unknown",
        )

    return {
        "movement_index": movement_index,
        "source_type": "email",
        "source_provider": "gmail",
        "source_record_key": f"gmail:{provider_message_id}:{movement_index}",
        "institution_country": str(parsed.get("institution_country") or "CR").upper(),
        "transaction_date": parsed.get("transaction_date") or datetime.utcnow().date().isoformat(),
        "transaction_time": parsed.get("transaction_time"),
        "description": str(parsed.get("description") or subject)[:500],
        "amount": parsed.get("amount"),
        "currency": currency,
        "original_amount": parsed.get("original_amount"),
        "original_currency": original_currency,
        "transaction_type": transaction_type,
        "movement_direction": direction,
        "movement_kind": _movement_kind(parsed),
        "category": normalize_category(parsed.get("category"), transaction_type),
        "bank": str(parsed.get("bank") or "unknown"),
        "source_account_label": str(parsed.get("account") or "")[:200] or None,
        "source_account_reference": str(
            parsed.get("origin_account") or parsed.get("card_last4") or ""
        )[:200] or None,
        "destination_account_reference": str(parsed.get("destination_account") or "")[:200] or None,
        "counterparty": str(parsed.get("counterparty") or parsed.get("payer_name") or "")[:200] or None,
        "external_reference": str(parsed.get("reference") or "")[:200] or None,
        "parser_name": str(parsed.get("parser_name") or PARSER_NAME),
        "parser_version": str(parsed.get("parser_version") or PARSER_VERSION),
        "extraction_method": str(parsed.get("extraction_method") or "parser"),
        "confidence": float(parsed.get("confidence") or 0),
        "uncertainty_reason": str(parsed.get("confidence_reason") or "")[:1000] or None,
        "dedupe_key": str(parsed.get("dedupe_key") or "")[:1000] or None,
        # Parser hints are not proof of ownership. Phase 1D only marks an
        # internal transfer after both endpoints match user-confirmed accounts.
        "is_internal_transfer": False,
        "raw_payload": parsed,
    }
