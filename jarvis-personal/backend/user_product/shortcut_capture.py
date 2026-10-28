"""Apple Pay purchases and bank SMS sent by the iOS Shortcuts automations become review candidates.

Both go through the review inbox exactly like a mail notice: the candidate is inserted and
resolved by ``gmail_service._insert_finva_candidate`` (account discovery, semantic and
cross-source duplicates), stays ``pending`` and is approved or rejected with the same review
endpoint. Nothing here writes a transaction.

- Identity: the Shortcuts token's account and workspace (``shortcut_tokens.authenticate``);
  never a value of the request body.
- Idempotency: the ``Idempotency-Key`` header becomes the candidate's ``source_record_key``
  (unique per account, workspace and key); a retry answers ``already_received``.
- Money: a decimal string read with Decimal, > 0 and under a per-currency cap; CRC or USD.
- Privacy: no amount, merchant, card, SMS text or token in logs, errors or analytics; an SMS
  text is never stored (only the reading of a recognized format becomes the candidate).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import psycopg2
from fastapi import HTTPException

from backend.core.database import get_connection
from backend.core.time import COSTA_RICA_TZ
from backend.finance.category_catalog import normalize_category, owner_account_context
from backend.product_ops.posthog_events import capture_backend_event_later
from backend.user_product import shortcut_sms

logger = logging.getLogger(__name__)

APPLE_PAY = "apple_pay_shortcut"
BANK_SMS = "bank_sms_shortcut"
IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
AMOUNT = re.compile(r"^\d{1,10}(\.\d{1,2})?$")
# The most a single captured movement may be (a typo or a misread variable, not a purchase).
MAX_AMOUNT = {"CRC": Decimal("50000000"), "USD": Decimal("100000")}
MAX_MERCHANT, MAX_CARD = 120, 60


def _idempotency(key: str | None) -> str:
    clean = str(key or "").strip()
    if not IDEMPOTENCY_KEY.fullmatch(clean):
        raise HTTPException(status_code=422, detail="Falta un identificador válido del envío (Idempotency-Key).")
    return clean


def money(amount: Any, currency: Any) -> tuple[Decimal, str]:
    """The amount as Decimal and the currency, or 422. The amount must be a decimal string."""
    code = str(currency or "").strip().upper()
    if code not in MAX_AMOUNT:
        raise HTTPException(status_code=422, detail="La moneda debe ser CRC o USD.")
    if not isinstance(amount, str) or not AMOUNT.fullmatch(amount.strip()):
        raise HTTPException(status_code=422, detail="El monto no es válido.")
    try:
        value = Decimal(amount.strip())
    except InvalidOperation:
        raise HTTPException(status_code=422, detail="El monto no es válido.") from None
    if value <= 0:
        raise HTTPException(status_code=422, detail="El monto debe ser mayor que cero.")
    if value > MAX_AMOUNT[code]:
        raise HTTPException(status_code=422, detail="El monto es demasiado grande.")
    return value, code


def _clean_label(value: Any, limit: int, *, required: bool, what: str) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        if required:
            raise HTTPException(status_code=422, detail=f"Falta {what}.")
        return None
    if len(text) > limit or any(ord(char) < 32 for char in text):
        raise HTTPException(status_code=422, detail=f"{what[0].upper()}{what[1:]} no es válido.")
    return text


def _now() -> datetime:
    return datetime.now(COSTA_RICA_TZ)


def _candidate(*, provider: str, key: str, amount: Decimal, currency: str, description: str,
               transaction_type: str, movement_kind: str, direction: str, bank: str, owner: bool = False,
               card: str | None = None, account_reference: str | None = None,
               reference: str | None = None) -> dict[str, Any]:
    now = _now()
    category = normalize_category(None, transaction_type, owner=owner)
    return {
        "movement_index": 0,
        "source_type": "api",
        "source_provider": provider,
        "source_record_key": f"{provider}:{key}",
        "institution_country": "CR",
        "transaction_date": now.date().isoformat(),
        "transaction_time": now.strftime("%H:%M:%S"),
        "description": description[:500],
        # Native money: a USD capture is stored in USD (never converted with an invented rate).
        "amount": amount,
        "currency": currency,
        "original_amount": None,
        "original_currency": None,
        "transaction_type": transaction_type,
        "movement_direction": direction,
        "movement_kind": movement_kind,
        "category": category,
        "bank": bank,
        "source_account_label": card,
        "source_account_reference": account_reference,
        "destination_account_reference": None,
        "counterparty": None,
        "external_reference": reference,
        "parser_name": provider,
        "parser_version": "1",
        "extraction_method": "parser",
        "confidence": 1.0,
        "uncertainty_reason": None,
        "dedupe_key": None,
        "is_internal_transfer": False,
        # Only what the candidate shows; never the SMS text or the token.
        "raw_payload": {"transaction_type": transaction_type, "movement_direction": direction, "category": category,
                        "capture": provider},
    }


def _store(user: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Insert and resolve the candidate once per capture key; a retry is ``already_received``."""
    from backend.user_product.gmail_service import _insert_finva_candidate

    account_id, workspace_id = str(user["account_id"]), str(user["workspace_id"])
    with get_connection() as conn:
        existing = conn.execute(
            """SELECT id FROM finva_email_candidates
               WHERE account_id=%s AND workspace_id=%s AND source_type='api' AND source_record_key=%s""",
            (account_id, workspace_id, candidate["source_record_key"]),
        ).fetchone()
        if existing:
            return {"status": "already_received"}
        try:
            _insert_finva_candidate(
                conn, email_message_id=None, candidate=candidate,
                connection={"account_id": account_id, "workspace_id": workspace_id},
            )
            conn.commit()
        except psycopg2.errors.UniqueViolation:
            # The same key sent twice at once: the other request created it.
            conn.rollback()
            return {"status": "already_received"}
    capture_backend_event_later("candidate_created", {"source": candidate["source_provider"]})
    return {"status": "created"}


def capture_apple_pay(user: dict[str, Any], body: dict[str, Any], idempotency_key: str | None) -> dict[str, Any]:
    key = _idempotency(idempotency_key)
    amount, currency = money(body.get("amount"), body.get("currency"))
    merchant = _clean_label(body.get("merchant"), MAX_MERCHANT, required=True, what="el comercio")
    card = _clean_label(body.get("card"), MAX_CARD, required=False, what="la tarjeta")
    with get_connection() as conn:
        owner = owner_account_context(conn, user["account_id"], user["workspace_id"])
    return _store(user, _candidate(
        provider=APPLE_PAY, key=key, amount=amount, currency=currency, description=merchant,
        transaction_type="expense", movement_kind="card_purchase", direction="out", bank="apple_pay",
        owner=owner, card=card,
    ))


def capture_bank_sms(user: dict[str, Any], body: dict[str, Any], idempotency_key: str | None) -> dict[str, Any]:
    key = _idempotency(idempotency_key)
    text = shortcut_sms.valid_text(body.get("text"))
    if text is None:
        raise HTTPException(status_code=422, detail="El mensaje no es válido.")
    movement = shortcut_sms.parse(text)
    if movement is None:
        capture_backend_event_later("shortcut_sms_unrecognized", {"sms_bank": shortcut_sms.detect_bank(text)})
        return {"status": "not_recognized"}
    if movement.amount > MAX_AMOUNT[movement.currency]:
        raise HTTPException(status_code=422, detail="El monto es demasiado grande.")
    transaction_type, movement_kind, direction = shortcut_sms.KINDS[movement.kind]
    with get_connection() as conn:
        owner = owner_account_context(conn, user["account_id"], user["workspace_id"])
    return _store(user, _candidate(
        provider=BANK_SMS, key=key, amount=movement.amount, currency=movement.currency,
        description=movement.description or movement.kind, transaction_type=transaction_type,
        movement_kind=movement_kind, direction=direction, bank=movement.bank, owner=owner,
        account_reference=movement.card_last4, reference=movement.reference,
    ))
