from __future__ import annotations

import hashlib
import re
from typing import Any

from backend.email_monitor.statement_reconciliation import parse_bac_statement, parse_multimoney_statement
from backend.email_monitor.popular_pdf import parse_popular_statement
from backend.finance.category_catalog import normalize_category


PARSER_NAME = "finva_statement"
PARSER_VERSION = "1"


def statement_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _account_last4(text: str) -> str | None:
    patterns = (
        r"(?:cuenta|iban|tarjeta|account)[^\n]{0,80}(?:\*|x){2,}[^\n]{0,20}(\d{4})\b",
        r"\*{4,}(\d{4})\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text or "", re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def parse_statement_movements(bank: str, text: str) -> list[dict[str, Any]]:
    bank_code = str(bank or "").lower()
    if bank_code == "bac":
        return parse_bac_statement(text)
    if bank_code == "multimoney":
        return parse_multimoney_statement(text)
    if bank_code == "popular":
        return parse_popular_statement(text)
    return []


def statement_candidate(
    movement: dict[str, Any], *, bank: str, document_hash: str,
    movement_index: int, statement_text: str,
) -> dict[str, Any]:
    """Adapt a signed statement row to FINVA's canonical candidate contract."""
    direction = str(movement.get("direction") or "unknown").lower()
    parser_type = str(movement.get("transaction_type") or "")
    # A parser may recognize an own-transfer phrase, but ownership remains a
    # Phase 1D decision based on accounts explicitly confirmed by the user.
    transaction_type = "transfer" if parser_type == "internal_transfer" else parser_type
    currency = str(movement.get("currency") or "CRC").upper()
    original_currency = str(movement.get("original_currency") or "").upper() or None
    account_last4 = str(movement.get("card_last4") or _account_last4(statement_text) or "") or None
    source_reference = account_last4 if direction == "out" else None
    destination_reference = account_last4 if direction == "in" else None
    reference = str(movement.get("reference") or "")[:200] or None
    amount = movement.get("amount")
    transaction_date = movement.get("transaction_date")
    movement_kind = "card_purchase" if movement.get("card_last4") and direction == "out" else "transfer" if parser_type == "internal_transfer" else "other"
    return {
        "movement_index": movement_index,
        "source_type": "statement",
        "source_provider": "pdf",
        "source_record_key": f"statement:{document_hash}:{movement_index}",
        "institution_country": "CR",
        "transaction_date": transaction_date,
        "transaction_time": None,
        "description": str(movement.get("description") or "Movimiento de estado de cuenta")[:500],
        "amount": amount,
        "currency": currency,
        "original_amount": movement.get("original_amount"),
        "original_currency": original_currency,
        "transaction_type": transaction_type,
        "movement_direction": direction if direction in {"in", "out"} else "unknown",
        "movement_kind": movement_kind,
        "category": normalize_category(movement.get("category"), transaction_type),
        "bank": str(bank or "unknown").lower(),
        "source_account_label": f"{str(bank or 'Banco').upper()} •••• {account_last4}" if account_last4 else str(bank or "Banco").upper(),
        "source_account_reference": source_reference,
        "destination_account_reference": destination_reference,
        "counterparty": None,
        "external_reference": reference,
        "parser_name": PARSER_NAME,
        "parser_version": PARSER_VERSION,
        "extraction_method": "parser",
        "confidence": 0.96,
        "uncertainty_reason": None,
        "dedupe_key": f"statement|{bank}|{transaction_date}|{reference or ''}|{amount}|{currency}",
        "is_internal_transfer": False,
        "raw_payload": {
            **movement,
            "transaction_type": transaction_type,
            "movement_direction": direction,
            "category": normalize_category(movement.get("category"), transaction_type),
        },
    }
