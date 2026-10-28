"""iOS Shortcuts capture (Apple Pay, bank SMS) on a real PostgreSQL.

- The Shortcuts token: issued once (only its SHA-256 stored), one active per account, revoked;
  a missing, malformed, unknown or revoked token is 401 and writes nothing.
- The identity is the token's account and workspace: a body can never write elsewhere.
- A capture is a pending review candidate in the same inbox and review flow as a mail notice;
  a retry with the same Idempotency-Key never creates a second one.
- Money is a decimal string (Decimal), CRC/USD, > 0, under a cap; the merchant is <= 120 chars.
- The plan check runs in the backend for the token routes and the capture routes.
- An Apple Pay capture and the bank notice of the same purchase are one movement: the later
  copy is a duplicate (same merchant) or a possible duplicate (weaker), never a second expense.
- A bank SMS no parser recognizes is discarded: nothing stored.

Uses the server of test_accounts_mail_strategy_pg.py. Synthetic data only.
"""
from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal

import pytest

from backend.tests.test_account_ownership_relink_pg import ACCOUNTS
from backend.tests.test_accounts_mail_strategy_pg import A, B, _as, pg  # noqa: F401  (fixture)
from backend.tests.test_mail_candidate_currency_pg import admin_uri  # noqa: F401  (module fixture)

psycopg2 = pytest.importorskip("psycopg2")
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend import main  # noqa: E402
from backend.user_product import gmail_service, shortcut_capture, shortcut_routes, shortcut_sms, shortcut_tokens  # noqa: E402

# What the capture flow writes on top of the review schema of the shared fixture, plus the
# migration's own objects (20261028120000_ios_shortcut_capture.sql).
CAPTURE_SCHEMA = ACCOUNTS + """
-- Production's transactions.transaction_date is a DATE (the shared fixture keeps TEXT).
ALTER TABLE transactions ALTER COLUMN transaction_date TYPE DATE USING transaction_date::date;
ALTER TABLE finva_email_candidates ADD COLUMN IF NOT EXISTS movement_index INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS source_record_key TEXT, ADD COLUMN IF NOT EXISTS institution_country TEXT,
    ADD COLUMN IF NOT EXISTS transaction_time TIME, ADD COLUMN IF NOT EXISTS external_reference TEXT,
    ADD COLUMN IF NOT EXISTS dedupe_key TEXT, ADD COLUMN IF NOT EXISTS semantic_fingerprint TEXT;
ALTER TABLE finva_email_candidates ALTER COLUMN email_message_id DROP NOT NULL;
CREATE UNIQUE INDEX uq_finva_candidates_capture_key ON finva_email_candidates (account_id, workspace_id, source_record_key)
    WHERE source_type = 'api' AND source_record_key IS NOT NULL;
CREATE TABLE shortcut_tokens (
    id BIGSERIAL PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), last_used_at TIMESTAMPTZ, revoked_at TIMESTAMPTZ);
CREATE UNIQUE INDEX uq_shortcut_tokens_hash ON shortcut_tokens (token_hash);
CREATE UNIQUE INDEX uq_shortcut_tokens_active_account ON shortcut_tokens (account_id) WHERE revoked_at IS NULL;
"""
PLANS = {}  # account id -> plan; the Owner role always passes (auth.saas.require_feature)


@pytest.fixture
def db(pg, monkeypatch):  # noqa: F811
    with pg.cursor() as cur:
        cur.execute(CAPTURE_SCHEMA)
        for ident in (A, B):
            cur.execute("INSERT INTO workspace_members(workspace_id,account_id,status) VALUES(%s,%s,'active') ON CONFLICT DO NOTHING",
                        (ident["workspace"], ident["account"]))
    PLANS.clear()
    PLANS.update({A["account"]: "vip", B["account"]: "vip"})

    def require_feature(code):
        from backend.auth.current_user import get_current_account_id
        assert code == "ios_shortcuts"
        if PLANS.get(get_current_account_id()) != "vip":
            raise HTTPException(status_code=403, detail="Esta función no está incluida en tu plan.")
        return True

    # Subscriptions, legal acceptance and feature flags have their own tests; here they are the
    # plan table above, "accepted" and "on".
    monkeypatch.setattr(shortcut_routes, "require_feature", require_feature)
    monkeypatch.setattr(shortcut_routes, "acceptance_required", lambda *_a: False)
    monkeypatch.setattr(shortcut_tokens, "enrich_identity", lambda user: user)
    monkeypatch.setattr(main, "disabled_feature_for_request", lambda *_a, **_k: None)
    monkeypatch.setattr(shortcut_capture, "capture_backend_event_later", lambda *_a, **_k: None)
    return pg


def _issue(ident):
    return _as(ident, shortcut_routes.shortcuts_link)["token"]


def _post(path, token, body, key=None):
    headers = {"Idempotency-Key": key or uuid.uuid4().hex}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return TestClient(main.app, raise_server_exceptions=False).post(f"/user-product/vip/shortcuts/{path}", json=body, headers=headers)


def _candidates(db, ident=None):
    with db.cursor() as cur:
        cur.execute("""SELECT id,account_id::text,workspace_id::text,amount,currency,description,status,source_type,source_provider,
                              email_message_id,related_candidate_id,resolution_reason,transaction_type
                       FROM finva_email_candidates WHERE (%s IS NULL OR workspace_id=%s::uuid) ORDER BY id""",
                    (ident and ident["workspace"], ident and ident["workspace"]))
        return cur.fetchall()


PURCHASE = {"amount": "12500.50", "currency": "CRC", "merchant": "SUPERMERCADO EJEMPLO", "card": "Visa ejemplo"}


def test_a_token_is_stored_only_as_its_hash_one_active_per_account_and_revocable(db):
    first = _issue(A)
    assert first.startswith("dsc_") and _as(A, shortcut_routes.shortcuts_status)["linked"] is True
    second = _issue(A)
    with db.cursor() as cur:
        cur.execute("SELECT token_hash, revoked_at IS NULL AS active FROM shortcut_tokens ORDER BY id")
        rows = cur.fetchall()
    assert [r["active"] for r in rows] == [False, True], "issuing again revokes the previous token"
    assert all(first not in r["token_hash"] and second not in r["token_hash"] and len(r["token_hash"]) == 64 for r in rows)
    assert _post("apple-pay", first, PURCHASE).status_code == 401
    assert _post("apple-pay", second, PURCHASE).status_code == 201
    _as(A, shortcut_routes.shortcuts_unlink)
    assert _as(A, shortcut_routes.shortcuts_status)["linked"] is False
    assert _post("apple-pay", second, PURCHASE).status_code == 401
    assert len(_candidates(db)) == 1


@pytest.mark.parametrize("token", [None, "", "dsc_short", "dsc_" + "x" * 43, "Basic abc", "dsc_" + "y" * 43 + "!"])
def test_a_missing_malformed_or_unknown_token_writes_nothing(db, token):
    _issue(A)
    response = _post("apple-pay", token, PURCHASE)
    assert response.status_code == 401 and "Atajos" in response.json()["detail"]
    assert _candidates(db) == []


def test_the_capture_is_a_pending_review_candidate_of_the_tokens_account_only(db):
    token = _issue(A)
    # The body cannot choose the account or workspace.
    response = _post("apple-pay", token, {**PURCHASE, "account_id": B["account"], "workspace_id": B["workspace"]})
    assert response.status_code == 201 and response.json() == {"status": "created"}
    [row] = _candidates(db)
    assert (row["account_id"], row["workspace_id"]) == (A["account"], A["workspace"])
    assert (row["status"], row["source_type"], row["source_provider"], row["email_message_id"]) == ("pending", "api", "apple_pay_shortcut", None)
    assert (row["amount"], row["currency"], row["transaction_type"]) == (Decimal("12500.50"), "CRC", "expense")
    # The same inbox and review flow as a mail notice; B sees nothing.
    pending = _as(A, gmail_service.list_gmail_emails, "pending")["items"]
    assert [item["candidate_id"] for item in pending] == [row["id"]] and pending[0]["email_id"] is None
    assert _as(B, gmail_service.list_gmail_emails, "pending")["items"] == []
    _as(A, gmail_service.review_gmail_candidate, row["id"], "reject")
    assert _candidates(db)[0]["status"] == "rejected"


def test_approving_a_capture_records_the_expense_once(db):
    assert _post("apple-pay", _issue(A), PURCHASE).status_code == 201
    [row] = _candidates(db)
    _as(A, gmail_service.review_gmail_candidate, row["id"], "accept")
    again = _as(A, gmail_service.review_gmail_candidate, row["id"], "accept")
    assert again.get("already_reviewed") is True
    with db.cursor() as cur:
        cur.execute("SELECT amount, transaction_type, source, workspace_id::text AS ws FROM transactions")
        [saved] = cur.fetchall()
    assert (saved["amount"], saved["transaction_type"], saved["source"], saved["ws"]) == (Decimal("12500.50"), "expense", "ios_shortcuts", A["workspace"])


def test_a_usd_purchase_stays_in_dollars(db):
    assert _post("apple-pay", _issue(A), {"amount": "4.99", "currency": "USD", "merchant": "TIENDA EN LINEA EJEMPLO"}).status_code == 201
    [row] = _candidates(db)
    assert (row["amount"], row["currency"]) == (Decimal("4.99"), "USD")


def test_a_retry_with_the_same_key_never_creates_a_second_candidate(db):
    token, key = _issue(A), uuid.uuid4().hex
    assert _post("apple-pay", token, PURCHASE, key).json() == {"status": "created"}
    retry = _post("apple-pay", token, PURCHASE, key)
    assert retry.status_code == 200 and retry.json() == {"status": "already_received"}
    assert len(_candidates(db)) == 1
    # The same key from another account is that account's own capture.
    assert _post("apple-pay", _issue(B), PURCHASE, key).status_code == 201
    assert len(_candidates(db, B)) == 1


@pytest.mark.parametrize("body", [
    {**PURCHASE, "amount": 12500.5},            # a number, not a decimal string
    {**PURCHASE, "amount": "0"},
    {**PURCHASE, "amount": "-5"},
    {**PURCHASE, "amount": "12,500.50"},
    {**PURCHASE, "amount": "1e3"},
    {**PURCHASE, "amount": "1.234"},
    {**PURCHASE, "amount": "50000000.01"},      # over the CRC cap
    {**PURCHASE, "amount": "100000.01", "currency": "USD"},
    {**PURCHASE, "currency": "EUR"},
    {**PURCHASE, "currency": None},
    {**PURCHASE, "merchant": ""},
    {**PURCHASE, "merchant": "x" * 121},
    {**PURCHASE, "card": "y" * 61},
])
def test_invalid_money_currency_or_labels_are_refused_and_write_nothing(db, body):
    assert _post("apple-pay", _issue(A), body).status_code == 422
    assert _candidates(db) == []


@pytest.mark.parametrize("key", ["", "short", "x" * 129, "has space here", "bad/char"])
def test_a_missing_or_invalid_idempotency_key_is_refused(db, key):
    response = TestClient(main.app, raise_server_exceptions=False).post(
        "/user-product/vip/shortcuts/apple-pay", json=PURCHASE,
        headers={"Authorization": f"Bearer {_issue(A)}", "Idempotency-Key": key})
    assert response.status_code == 422 and _candidates(db) == []


def test_the_plan_is_checked_by_the_backend_for_linking_and_for_each_capture(db):
    token = _issue(A)
    PLANS[A["account"]] = "basic"
    with pytest.raises(HTTPException) as refused:
        _as(A, shortcut_routes.shortcuts_link)
    assert refused.value.status_code == 403
    assert _post("apple-pay", token, PURCHASE).status_code == 403
    assert _post("bank-sms", token, {"text": "Mensaje sintetico"}).status_code == 403
    assert _candidates(db) == []
    _as(A, shortcut_routes.shortcuts_unlink)  # unlinking never needs the plan


def test_an_unrecognized_sms_is_discarded(db):
    response = _post("bank-sms", _issue(A), {"text": "BANCO EJEMPLO: aviso sintetico sin formato conocido"})
    assert response.status_code == 200 and response.json() == {"status": "not_recognized"}
    assert _candidates(db) == []


@pytest.mark.parametrize("text", ["", " ", "x" * 1001, "texto\x00binario", 42, None])
def test_an_invalid_sms_text_is_refused(db, text):
    assert _post("bank-sms", _issue(A), {"text": text}).status_code == 422


# SYNTHETIC FORMAT (no real bank writes this): it exercises the SMS pipeline until real,
# anonymized samples define each bank's parsers.
def _synthetic_parser(text):
    import re
    match = re.fullmatch(r"SINTETICO (ENVIADO|RECIBIDO|COMPRA) CRC ([\d.,]+) (.+)", text)
    if not match:
        return None
    kind = {"ENVIADO": "sinpe_out", "RECIBIDO": "sinpe_in", "COMPRA": "card_purchase"}[match.group(1)]
    amount = shortcut_sms.amount_from(match.group(2), decimal_separator=",")
    return shortcut_sms.SmsMovement(bank="unknown", kind=kind, amount=amount, currency="CRC", description=match.group(3))


@pytest.mark.parametrize(("text", "expected"), [
    ("SINTETICO RECIBIDO CRC 15.000,00 PERSONA EJEMPLO", ("income", Decimal("15000.00"))),
    ("SINTETICO ENVIADO CRC 2.500,00 PERSONA EJEMPLO", ("expense", Decimal("2500.00"))),
    ("SINTETICO COMPRA CRC 7.800,50 COMERCIO EJEMPLO", ("expense", Decimal("7800.50"))),
])
def test_a_recognized_sms_is_income_or_spending_and_its_text_is_not_stored(db, monkeypatch, text, expected):
    monkeypatch.setattr(shortcut_sms, "PARSERS", [_synthetic_parser])
    assert _post("bank-sms", _issue(A), {"text": text}).json() == {"status": "created"}
    [row] = _candidates(db)
    assert (row["transaction_type"], row["amount"], row["source_provider"]) == (*expected, "bank_sms_shortcut")
    with db.cursor() as cur:
        cur.execute("SELECT row_to_json(c)::text AS stored FROM finva_email_candidates c")
        assert text not in cur.fetchone()["stored"]


def _mail_notice(db, ident, *, amount, description, day=None, currency="CRC", original=None):
    with db.cursor() as cur:
        cur.execute("""INSERT INTO finva_email_messages(connection_id,account_id,workspace_id,provider_message_id,sender,subject,received_at,bank)
                       VALUES(%s,%s,%s,%s,'avisos@banco.example','Notificación de transacción',NOW(),'bac') RETURNING id""",
                    (ident["connection"], ident["account"], ident["workspace"], uuid.uuid4().hex))
        message_id = cur.fetchone()["id"]
    candidate = {
        "movement_index": 0, "source_type": "email", "source_provider": "gmail", "source_record_key": f"gmail:{message_id}:0",
        "institution_country": "CR", "transaction_date": (day or date.today()).isoformat(), "transaction_time": None,
        "description": description, "amount": amount, "currency": currency, "original_amount": original,
        "original_currency": "USD" if original else None, "transaction_type": "expense", "movement_direction": "out",
        "movement_kind": "card_purchase", "category": "Compras", "bank": "bac", "source_account_label": None,
        "source_account_reference": None, "destination_account_reference": None, "counterparty": None,
        "external_reference": None, "parser_name": "p", "parser_version": "1", "extraction_method": "parser",
        "confidence": 0.9, "uncertainty_reason": None, "dedupe_key": None, "is_internal_transfer": False,
        "raw_payload": {"transaction_type": "expense", "movement_direction": "out"},
    }
    from backend.core.database import get_connection
    with get_connection() as conn:
        gmail_service._insert_finva_candidate(conn, email_message_id=message_id, candidate=candidate,
                                              connection={"account_id": ident["account"], "workspace_id": ident["workspace"]})
        conn.commit()


def test_the_bank_notice_of_an_apple_pay_purchase_does_not_show_again_in_review(db):
    assert _post("apple-pay", _issue(A), {"amount": "8593.00", "currency": "CRC", "merchant": "Uber Eats"}).status_code == 201
    _mail_notice(db, A, amount=8593, description="DLC*UBER EATS")
    capture, notice = _candidates(db)
    assert notice["status"] == "duplicate" and notice["related_candidate_id"] == capture["id"]
    assert [item["candidate_id"] for item in _as(A, gmail_service.list_gmail_emails, "pending")["items"]] == [capture["id"]]
    # Rejecting the capture sends the bank notice back to review: never lost.
    _as(A, gmail_service.review_gmail_candidate, capture["id"], "reject")
    assert _candidates(db)[1]["status"] == "pending"


def test_a_usd_notice_matches_the_dollar_capture_and_a_different_merchant_is_only_a_possible_duplicate(db):
    token = _issue(A)
    _post("apple-pay", token, {"amount": "4.99", "currency": "USD", "merchant": "TIENDA EN LINEA EJEMPLO"})
    _mail_notice(db, A, amount=2470, original=Decimal("4.99"), description="TIENDA EN LINEA EJEMPLO")  # converted by the bank
    _post("apple-pay", token, {"amount": "3000.00", "currency": "CRC", "merchant": "CAFE EJEMPLO"})
    _mail_notice(db, A, amount=3000, description="PANADERIA OTRA")
    usd_capture, usd_notice, crc_capture, other_notice = _candidates(db)
    assert usd_notice["status"] == "duplicate" and usd_notice["related_candidate_id"] == usd_capture["id"]
    assert other_notice["status"] == "pending" and other_notice["related_candidate_id"] == crc_capture["id"]
    assert other_notice["resolution_reason"] == "possible_cross_source_match"


def test_another_account_never_matches(db):
    _post("apple-pay", _issue(A), {"amount": "8593.00", "currency": "CRC", "merchant": "Uber Eats"})
    _mail_notice(db, B, amount=8593, description="DLC*UBER EATS")
    assert [row["status"] for row in _candidates(db, B)] == ["pending"]
    assert _candidates(db, B)[0]["related_candidate_id"] is None


def test_nothing_sensitive_reaches_analytics(db, monkeypatch):
    sent = []
    monkeypatch.setattr(shortcut_capture, "capture_backend_event_later", lambda name, props: sent.append((name, props)))
    _post("apple-pay", _issue(A), PURCHASE)
    _post("bank-sms", _issue(A), {"text": "BANCO EJEMPLO aviso sintetico"})
    assert sent == [("candidate_created", {"source": "apple_pay_shortcut"}), ("shortcut_sms_unrecognized", {"sms_bank": "unknown"})]
    assert "12500" not in json.dumps(sent) and "SUPERMERCADO" not in json.dumps(sent)
