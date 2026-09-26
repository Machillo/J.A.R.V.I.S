"""Store purchase endpoints: client verification, store notifications, lapse cron.

- The app asks for its customer token before buying and passes it to the store
  (StoreKit appAccountToken / Play obfuscatedExternalAccountId).
- After a purchase or restore, the app sends Apple's signed transaction, or the
  Google purchase token; the server verifies it with the store and derives the plan.
  A client can confirm or extend a live purchase, never end one.
- Apple (App Store Server Notifications V2) and Google (RTDN over Pub/Sub) notify
  renewals, grace, expirations, refunds and revocations; each is verified, and
  Google's only triggers a fresh read from the Play Developer API. A notification
  DINCR must refuse for good is answered 200 "ignored" so the store does not retry it
  for days; a temporary failure is answered 5xx so it does.
- A cron recomputes accounts whose entitlement ended without a notification.
Logs carry event types and counts only: never tokens, transaction ids or accounts.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import Any

from fastapi import HTTPException

from backend.auth.current_user import get_current_account_id
from backend.core.database import get_connection
from backend.product_ops import store_apple, store_google
from backend.product_ops.store_state import (
    customer_token, expire_lapsed, recompute_account, record_verified_purchase,
)

logger = logging.getLogger(__name__)


def _record_event(conn, account_id: str | None, provider: str, event_type: str, event_id: str, plan: str | None) -> None:
    conn.execute(
        """INSERT INTO store_subscription_events(account_id,provider,event_type,provider_event_id,plan_code,payload_hash)
           VALUES(%s,%s,%s,%s,%s,%s)
           ON CONFLICT DO NOTHING
           RETURNING id""",
        (account_id, provider, event_type, event_id, plan, hashlib.sha256(event_id.encode("utf-8")).hexdigest()),
    )


def _apply(state: dict[str, Any], *, event_type: str, event_id: str, claimed_account_id: str | None = None,
           from_client: bool = False, notification: bool = False, reversed_refund: bool = False) -> dict:
    with get_connection() as conn:
        if notification and conn.execute(
            "SELECT 1 FROM store_subscription_events WHERE provider=%s AND provider_event_id=%s",
            (state["provider"], event_id),
        ).fetchone():
            conn.commit()
            return {"status": "duplicate"}
        result = record_verified_purchase(conn, state, claimed_account_id=claimed_account_id,
                                          from_client=from_client, reversed_refund=reversed_refund)
        if result.get("conflict"):
            conn.commit()  # keep the conflict record
            logger.warning("Store purchase refused: bound to another account provider=%s", state["provider"])
            raise HTTPException(409, "Esta compra pertenece a otra cuenta DINCR.")
        _record_event(conn, result["account_id"], state["provider"], event_type, event_id, result["plan"])
        conn.commit()
    return {"status": "applied" if result["applied"] else "unchanged", "plan": result["plan"],
            "store_status": result["status"], "resolved": bool(result["account_id"])}


def _notification(apply) -> dict:
    """Run a notification's work; a permanent refusal is acknowledged so the store stops retrying."""
    try:
        return apply()
    except HTTPException as exc:
        if exc.status_code in (409, 422):
            logger.warning("Store notification ignored status=%s", exc.status_code)
            return {"status": "ignored"}
        raise


def my_customer_token() -> dict[str, str]:
    account_id = get_current_account_id()
    with get_connection() as conn:
        token = customer_token(conn, account_id)
        conn.commit()
    return {"token": token}


def verify_apple_transaction(signed_transaction: str) -> dict:
    try:
        transaction = store_apple.verify_transaction(signed_transaction)
        state = store_apple.purchase_state(transaction)
    except store_apple.AppleVerificationError as exc:
        logger.warning("Apple transaction rejected reason=%s", exc)
        raise HTTPException(422, "No pudimos verificar la compra con App Store.") from exc
    if state is None:
        return {"status": "superseded"}  # an upgraded transaction; the newer one decides
    return _apply(state, event_type="client_verification",
                  event_id=f"apple-client:{state['purchase_key']}:{state['transaction_id']}:{state['status']}",
                  claimed_account_id=get_current_account_id(), from_client=True)


def verify_google_purchase(purchase_token: str, product_id: str) -> dict:
    try:
        subscription = store_google.fetch_subscription(purchase_token)
        state = store_google.purchase_state(purchase_token, subscription)
    except store_google.GoogleVerificationError as exc:
        logger.warning("Google purchase rejected reason=%s", exc)
        raise HTTPException(422, "No pudimos verificar la compra con Google Play.") from exc
    if state["product_id"] != product_id:
        raise HTTPException(422, "La compra no corresponde al plan elegido.")
    result = _apply(state, event_type="client_verification",
                    event_id=f"google-client:{state['purchase_key']}:{state['transaction_id']}:{state['status']}",
                    claimed_account_id=get_current_account_id(), from_client=True)
    if result.get("resolved") and state["status"] in ("trialing", "active") and not state.get("acknowledged"):
        try:
            store_google.acknowledge(purchase_token, state["product_id"])
        except store_google.GoogleVerificationError as exc:
            # The plan is granted; the app retries this call (idempotent) until acknowledged.
            logger.warning("Google acknowledgement pending reason=%s", exc)
            result["acknowledgement"] = "pending"
    return result


def apple_notification(signed_payload: str) -> dict:
    try:
        notification = store_apple.verify_notification(signed_payload)
        kind = str(notification.get("notificationType") or "")
        state = store_apple.purchase_state(notification["transaction"], notification.get("renewal")) \
            if notification.get("transaction") else None
    except (store_apple.AppleVerificationError, KeyError) as exc:
        logger.warning("Apple notification rejected reason=%s", exc)
        raise HTTPException(400, "Notificación no válida.") from exc
    if state is None:
        return {"status": "ignored", "type": kind}  # TEST, or an upgraded transaction
    if kind in ("REFUND", "REVOKE") and state["status"] != "revoked":
        state["status"], state["revoked_at"] = "revoked", state["revoked_at"] or state["current_period_end"]
    uuid_ = notification.get("notificationUUID") or hashlib.sha256(signed_payload.encode("utf-8")).hexdigest()
    result = _notification(lambda: _apply(state, event_type=f"apple:{kind}", event_id=f"apple-notification:{uuid_}",
                                          notification=True, reversed_refund=kind == "REFUND_REVERSED"))
    logger.info("Apple notification type=%s status=%s", kind, state["status"])
    return result


def google_notification(authorization: str | None, body: dict[str, Any]) -> dict:
    try:
        store_google.verify_push(authorization)
        notification = store_google.decode_push(body)
    except store_google.GoogleVerificationError as exc:
        logger.warning("Google notification rejected reason=%s", exc)
        raise HTTPException(401, "Notificación no válida.") from exc
    voided = notification.get("voidedPurchaseNotification")
    if voided and voided.get("purchaseToken") and voided.get("orderId"):
        # One order was refunded: revoke that order, not the whole subscription.
        with get_connection() as conn:
            account_id = void_order(conn, store_google.purchase_key(voided["purchaseToken"]), str(voided["orderId"]))
            conn.commit()
        return {"status": "applied", "resolved": bool(account_id)}
    purchase = notification.get("subscriptionNotification")
    if not purchase or not purchase.get("purchaseToken"):
        return {"status": "ignored"}  # test notification or a one-time product
    token = purchase["purchaseToken"]
    try:
        state = store_google.purchase_state(token, store_google.fetch_subscription(token))
    except store_google.GoogleVerificationError as exc:
        logger.warning("Google notification read failed reason=%s", exc)
        raise HTTPException(503, "No pudimos leer la compra en Google Play.") from exc  # Pub/Sub retries
    kind = f"google:{purchase.get('notificationType')}"
    result = _notification(lambda: _apply(state, event_type=kind, event_id=f"google-notification:{notification['message_id']}",
                                          notification=True))
    if result.get("resolved") and state["status"] in ("trialing", "active") and not state.get("acknowledged"):
        try:
            store_google.acknowledge(token, state["product_id"])
        except store_google.GoogleVerificationError as exc:
            logger.warning("Google acknowledgement failed reason=%s", exc)
            raise HTTPException(503, "Reconocimiento pendiente en Google Play.") from exc  # retried; state is idempotent
    return result


def void_order(conn, purchase_key: str, order_id: str) -> str | None:
    """Record a refunded Google order; revoke the purchase only if that order is its current one."""
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"store-purchase:google:{purchase_key}",))
    conn.execute(
        """INSERT INTO store_revocations(provider,transaction_id,purchase_key) VALUES('google',%s,%s)
           ON CONFLICT(provider,transaction_id) DO UPDATE SET reversed_at=NULL RETURNING transaction_id""",
        (order_id, purchase_key),
    )
    row = conn.execute(
        """UPDATE store_purchases SET status='revoked',revoked_at=NOW(),updated_at=NOW()
           WHERE provider='google' AND purchase_key=%s AND last_transaction_id=%s
           RETURNING account_id::text AS account_id""",
        (purchase_key, order_id),
    ).fetchone()
    if row:
        recompute_account(conn, row["account_id"])
        return row["account_id"]
    return None


def lapse_cron(secret: str | None) -> dict:
    expected = os.getenv("DINCR_STORE_CRON_SECRET", "").strip()
    if not expected:
        raise HTTPException(503, "El cron de tiendas no está configurado.")
    if not secret or not hmac.compare_digest(secret.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(403, "Cron secret inválido.")
    with get_connection() as conn:
        count = expire_lapsed(conn)
        conn.commit()
    return {"status": "OK", "recomputed": count}
