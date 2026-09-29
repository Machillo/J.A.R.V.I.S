"""Email Monitor lab: synthetic email -> real parser -> candidate -> Accept/Reject -> transaction.

No Gmail, no Microsoft Graph, no OAuth: messages come from labs/email_fixtures
(invented, in formats the parsers already support). The parser and the review
command are DINCR's own code; the database is the Labs database, and the
reviewer is a synthetic identity set in-process (no HTTP, no token).
"""
from __future__ import annotations

import json
import re
import uuid
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

from labs import db, runtime

FIXTURES = Path(__file__).resolve().parent / "email_fixtures" / "bank_emails.json"
_LONG_DIGITS = re.compile(r"\d{5,}")


def load_fixtures() -> dict[str, Any]:
    data = json.loads(FIXTURES.read_text(encoding="utf-8"))
    if data.get("synthetic") is not True:
        raise ValueError("email fixtures must be marked synthetic")
    return data


def fixture(name: str) -> dict[str, Any]:
    data = load_fixtures()
    for case in data["cases"]:
        if case["name"] == name:
            return {**case, "received_at": case.get("received_at") or data["received_at"]}
    raise KeyError(f"unknown email fixture {name!r}; see `python -m labs parse --list`")


def _sanitize(text: Any) -> str | None:
    if text is None:
        return None
    return _LONG_DIGITS.sub(lambda m: "•" * len(m.group(0)), str(text))[:200]


def parse(message: dict[str, Any]) -> dict[str, Any]:
    """Run DINCR's parser on one synthetic message; pure (no database, no network)."""
    from backend.email_monitor import parser
    from backend.user_product.financial_candidate import canonical_candidate

    parsed = parser.parse_financial_email(message["subject"], message["sender"], message["body"],
                                          message.get("received_at"))
    candidate = None
    if parsed.get("email_kind") == "movement" and parsed.get("amount"):
        candidate = canonical_candidate(parsed, provider_message_id=f"labs-{uuid.uuid5(uuid.NAMESPACE_URL, message['body'])}",
                                        subject=message["subject"], source_provider="labs-fixture")
    return {"parsed": parsed, "candidate": candidate}


def report(message: dict[str, Any]) -> dict[str, Any]:
    """What the parser playground shows: sanitized, no body, no raw payload."""
    result = parse(message)
    parsed, candidate = result["parsed"], result["candidate"]
    return {
        "fixture": message.get("name"),
        "bank": parsed.get("bank"),
        "parser": (candidate or {}).get("parser_name") or parsed.get("parser_name") or "jarvis_financial_email",
        "kind": parsed.get("email_kind"),
        "type": parsed.get("transaction_type"),
        "amount": None if not parsed.get("amount") else str(parsed.get("amount")),
        "currency": parsed.get("currency") or ("CRC" if parsed.get("amount") else None),
        "original": None if parsed.get("original_amount") is None else
        f"{parsed.get('original_currency')} {parsed.get('original_amount')}",
        "date": parsed.get("transaction_date"),
        "description": _sanitize(parsed.get("description")),
        "confidence": parsed.get("confidence"),
        "reason": parsed.get("confidence_reason") or parsed.get("parse_reason") or parsed.get("reason"),
        "dedupe_key": _sanitize(parsed.get("dedupe_key")),
        "candidate": None if candidate is None else {
            "movement_kind": candidate["movement_kind"], "direction": candidate["movement_direction"],
            "category": candidate["category"], "amount": str(candidate["amount"]), "currency": candidate["currency"],
            "original_amount": None if candidate["original_amount"] is None else str(candidate["original_amount"]),
            "original_currency": candidate["original_currency"],
        },
    }


@contextmanager
def acting_as(identity: dict[str, Any]):
    """Fake auth for Labs: an in-process synthetic identity. Refused outside an active Labs process."""
    runtime.require_active()
    if identity.get("role") != "user" or not str(identity.get("email", "")).endswith(".invalid"):
        raise PermissionError("Labs identities are synthetic users only (role 'user', .invalid email)")
    from backend.auth.current_user import reset_current_user, set_current_user

    token = set_current_user(identity)
    try:
        yield identity
    finally:
        reset_current_user(token)


def store_candidate(user, message: dict[str, Any]) -> int | None:
    """Insert the parsed candidate for a synthetic user in the Labs database; return its id."""
    result = parse(message)
    candidate = result["candidate"]
    if candidate is None:
        return None
    conn = db.connect_labs()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM finva_gmail_connections WHERE workspace_id=%s", (user.workspace_id,))
            connection_id = cur.fetchone()["id"]
            cur.execute("""INSERT INTO finva_email_messages(connection_id,account_id,workspace_id,provider_message_id)
                           VALUES(%s,%s,%s,%s) RETURNING id""",
                        (connection_id, user.account_id, user.workspace_id, candidate["source_record_key"] + uuid.uuid4().hex))
            message_id = cur.fetchone()["id"]
            cur.execute(
                """INSERT INTO finva_email_candidates(email_message_id,account_id,workspace_id,transaction_date,description,
                       amount,currency,original_amount,original_currency,transaction_type,category,bank,source_type,
                       source_provider,parser_name,parser_version,movement_kind,confidence,dedupe_key)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (message_id, user.account_id, user.workspace_id, candidate["transaction_date"], candidate["description"],
                 Decimal(str(candidate["amount"])), candidate["currency"],
                 None if candidate["original_amount"] is None else Decimal(str(candidate["original_amount"])),
                 candidate["original_currency"], candidate["transaction_type"], candidate["category"], candidate["bank"],
                 "email", "gmail", candidate["parser_name"], candidate["parser_version"], candidate["movement_kind"],
                 Decimal(str(candidate["confidence"])).quantize(Decimal("0.0001")), candidate["dedupe_key"]),
            )
            candidate_id = cur.fetchone()["id"]
        conn.commit()
        return candidate_id
    finally:
        conn.close()


def review(user, candidate_id: int, action: str, corrections: dict[str, Any] | None = None) -> dict[str, Any]:
    """DINCR's real Accept/Reject command, as the synthetic user, on the Labs database."""
    from backend.user_product import gmail_service

    with acting_as(user.identity()):
        return gmail_service.review_gmail_candidate(candidate_id, action, corrections)
