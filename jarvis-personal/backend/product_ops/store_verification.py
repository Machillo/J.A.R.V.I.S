"""Store purchase endpoints: client verification, store notifications, lapse cron.

- The app asks for its customer token before buying and passes it to the store
  (StoreKit appAccountToken / Play obfuscatedExternalAccountId).
- After a purchase or restore, the app sends Apple's signed transaction, or the
  Google purchase token; the server verifies it with the store and derives the plan.
- Apple (App Store Server Notifications V2) and Google (RTDN over Pub/Sub) notify
  renewals, grace, expirations, refunds and revocations; each is verified, and
  Google's only triggers a fresh read from the Play Developer API.
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
from backend.product_ops.store_state import customer_token, expire_lapsed, record_verified_purchase

logger = logging.getLogger(__name__)


def _record_event(conn, account_id: str | None, provider: str, event_type: str, event_id: str | None, result: dict) -> bool:
    """Idempotency and audit: one row per provider event id. False when already seen."""
    row = conn.execute(
        """INSERT INTO store_subscription_events(account_id,provider,event_type,provider_event_id,plan_code,payload_hash)
           VALUES(%s,%s,%s,%s,%s,%s)
           ON CONFLICT DO NOTHING
           RETURNING id""",
        (account_id, provider, event_type, event_id, result.get("plan"),
         hashlib.sha256(str(event_id or "").encode("utf-8")).hexdigest()),
    ).fetchone()
    return bool(row)


def _apply(state: dict[str, Any], *, event_type: str, event_id: str | None, claimed_account_id: str | None = None) -> dict:
    with get_connection() as conn:
        if event_id and conn.execute(
            "SELECT 1 FROM store_subscription_events WHERE provider=%s AND provider_event_id=%s",
            (state["provider"], event_id),
        ).fetchone():
            conn.commit()
            return {"status": "duplicate"}
        result = record_verified_purchase(conn, state, claimed_account_id=claimed_account_id)
        if result.get("conflict"):
            conn.commit()  # keep the conflict record
            logger.warning("Store purchase refused: bound to another account provider=%s", state["provider"])
            raise HTTPException(409, "Esta compra pertenece a otra cuenta DINCR.")
        _record_event(conn, result["account_id"], state["provider"], event_type, event_id, result)
        conn.commit()
    return {"status": "applied" if result["applied"] else "unchanged", "plan": result["plan"],
            "store_status": result["status"], "resolved": bool(result["account_id"])}


def my_customer_token() -> dict[str, str]:
    account_id = get_current_account_id()
    with get_connection() as conn:
        token = customer_token(conn, account_id)
        conn.commit()
    return {"token": token}


def verify_apple_transaction(signed_transaction: str) -> dict:
    try:
        transaction = store_apple.verify_transaction(signed_transaction)
    except store_apple.AppleVerificationError as exc:
        logger.warning("Apple transaction rejected reason=%s", exc)
        raise HTTPException(422, "No pudimos verificar la compra con App Store.") from exc
    state = store_apple.purchase_state(transaction)
    return _apply(state, event_type="client_verification", event_id=state["event_id"],
                  claimed_account_id=get_current_account_id())


def verify_google_purchase(purchase_token: str, product_id: str) -> dict:
    try:
        subscription = store_google.fetch_subscription(purchase_token)
        state = store_google.purchase_state(purchase_token, subscription)
    except store_google.GoogleVerificationError as exc:
        logger.warning("Google purchase rejected reason=%s", exc)
        raise HTTPException(422, "No pudimos verificar la compra con Google Play.") from exc
    if state["product_id"] != product_id:
        raise HTTPException(422, "La compra no corresponde al plan elegido.")
    result = _apply(state, event_type="client_verification", event_id=state["event_id"],
                    claimed_account_id=get_current_account_id())
    if state["status"] in ("trialing", "active") and not state.get("acknowledged"):
        store_google.acknowledge(purchase_token, state["product_id"])
    return result


def apple_notification(signed_payload: str) -> dict:
    try:
        notification = store_apple.verify_notification(signed_payload)
    except (store_apple.AppleVerificationError, KeyError) as exc:
        logger.warning("Apple notification rejected reason=%s", exc)
        raise HTTPException(400, "Notificación no válida.") from exc
    kind = str(notification.get("notificationType") or "")
    if not notification.get("transaction"):
        return {"status": "ignored", "type": kind}  # e.g. TEST
    state = store_apple.purchase_state(notification["transaction"], notification.get("renewal"))
    if kind in ("REFUND", "REVOKE") and state["status"] != "revoked":
        state["status"], state["revoked_at"] = "revoked", state["revoked_at"] or state["current_period_end"]
    result = _apply(state, event_type=f"apple:{kind}", event_id=f"apple-notification:{notification.get('notificationUUID')}")
    logger.info("Apple notification applied type=%s status=%s", kind, state["status"])
    return result


def google_notification(authorization: str | None, body: dict[str, Any]) -> dict:
    try:
        store_google.verify_push(authorization)
        notification = store_google.decode_push(body)
    except store_google.GoogleVerificationError as exc:
        logger.warning("Google notification rejected reason=%s", exc)
        raise HTTPException(401, "Notificación no válida.") from exc
    purchase = notification.get("subscriptionNotification") or notification.get("voidedPurchaseNotification")
    if not purchase or not purchase.get("purchaseToken"):
        return {"status": "ignored"}  # test notification or a one-time product
    token = purchase["purchaseToken"]
    try:
        state = store_google.purchase_state(token, store_google.fetch_subscription(token))
    except store_google.GoogleVerificationError as exc:
        logger.warning("Google notification read failed reason=%s", exc)
        raise HTTPException(503, "No pudimos leer la compra en Google Play.") from exc  # Pub/Sub retries
    if notification.get("voidedPurchaseNotification"):
        state["status"] = "revoked"
    kind = f"google:{purchase.get('notificationType', 'voided')}"
    return _apply(state, event_type=kind, event_id=f"google-notification:{notification['message_id']}")


def lapse_cron(secret: str | None) -> dict:
    expected = os.getenv("DINCR_STORE_CRON_SECRET", "").strip()
    if not expected:
        raise HTTPException(503, "El cron de tiendas no está configurado.")
    if not secret or not hmac.compare_digest(secret, expected):
        raise HTTPException(403, "Cron secret inválido.")
    with get_connection() as conn:
        count = expire_lapsed(conn)
        conn.commit()
    return {"status": "OK", "recomputed": count}
