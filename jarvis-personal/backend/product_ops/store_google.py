"""Google Play: read a subscription purchase from the Play Developer API.

A purchase token from the app proves nothing by itself: the state used is the one
the Play Developer API (purchases.subscriptionsv2.get) returns for DINCR's package,
read with DINCR's service account. Real-time developer notifications (Pub/Sub push)
are accepted only with a valid Google-signed OIDC token for the configured push
service account and audience, and then only trigger a fresh API read.
The purchase token is never stored or logged: purchases are keyed by its SHA-256.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Callable

ANDROID_PUBLISHER_SCOPE = "https://www.googleapis.com/auth/androidpublisher"
ACTIVE_STATES = {"SUBSCRIPTION_STATE_ACTIVE": "active", "SUBSCRIPTION_STATE_IN_GRACE_PERIOD": "grace_period"}


class GoogleVerificationError(ValueError):
    """The purchase or notification cannot be verified for DINCR."""


def purchase_key(purchase_token: str) -> str:
    return hashlib.sha256(str(purchase_token).encode("utf-8")).hexdigest()


def package_name() -> str:
    name = os.getenv("FINVA_GOOGLE_PACKAGE_NAME", "").strip()
    if not name:
        raise GoogleVerificationError("Google Play package is not configured")
    return name


def _publisher():  # pragma: no cover - network client, replaced in tests
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    info = os.getenv("DINCR_GOOGLE_PLAY_SERVICE_ACCOUNT_JSON", "").strip()
    if not info:
        raise GoogleVerificationError("Google Play service account is not configured")
    credentials = service_account.Credentials.from_service_account_info(json.loads(info), scopes=[ANDROID_PUBLISHER_SCOPE])
    return build("androidpublisher", "v3", credentials=credentials, cache_discovery=False)


def fetch_subscription(purchase_token: str, *, publisher: Callable[[], Any] = _publisher) -> dict[str, Any]:
    try:
        return publisher().purchases().subscriptionsv2().get(
            packageName=package_name(), token=purchase_token).execute()
    except GoogleVerificationError:
        raise
    except Exception as exc:
        # No token or response body in the message: it can reach logs.
        raise GoogleVerificationError(f"Play Developer API read failed: {type(exc).__name__}") from exc


def acknowledge(purchase_token: str, product_id: str, *, publisher: Callable[[], Any] = _publisher) -> None:
    """Acknowledge within 3 days or Google refunds the purchase."""
    try:
        publisher().purchases().subscriptions().acknowledge(
            packageName=package_name(), subscriptionId=product_id, token=purchase_token, body={}).execute()
    except Exception as exc:
        raise GoogleVerificationError(f"Play acknowledgement failed: {type(exc).__name__}") from exc


def _time(value: Any) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def purchase_state(purchase_token: str, subscription: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Map a subscriptionsv2 resource to DINCR's per-purchase state (read now, so it is the newest)."""
    now = now or datetime.now(timezone.utc)
    items = subscription.get("lineItems") or []
    if len(items) != 1:
        raise GoogleVerificationError("unexpected number of line items")
    item = items[0]
    state = subscription.get("subscriptionState")
    expiry = _time(item.get("expiryTime"))
    offer = (item.get("offerDetails") or {})
    trial = "free-trial" in (offer.get("offerTags") or []) or "trial" in str(offer.get("offerId") or "").lower()
    if state == "SUBSCRIPTION_STATE_EXPIRED" or state == "SUBSCRIPTION_STATE_PAUSED":
        status = "expired"
    elif state in ("SUBSCRIPTION_STATE_ON_HOLD", "SUBSCRIPTION_STATE_PENDING",
                   "SUBSCRIPTION_STATE_PENDING_PURCHASE_CANCELED", "SUBSCRIPTION_STATE_UNSPECIFIED", None):
        status = "expired"  # never paid or payment on hold: no access
    elif state == "SUBSCRIPTION_STATE_IN_GRACE_PERIOD":
        status = "grace_period"
    elif state in ("SUBSCRIPTION_STATE_ACTIVE", "SUBSCRIPTION_STATE_CANCELED") and expiry and expiry > now:
        status = "trialing" if trial else "active"
    else:
        status = "expired"
    auto_renew = bool((item.get("autoRenewingPlan") or {}).get("autoRenewEnabled"))
    identifiers = subscription.get("externalAccountIdentifiers") or {}
    # The order this state is about; never built from a missing value.
    order = item.get("latestSuccessfulOrderId") or subscription.get("latestOrderId") or (
        f"expiry:{item.get('expiryTime')}" if item.get("expiryTime") else None)
    if not order:
        raise GoogleVerificationError("purchase without order or expiry")
    return {
        "provider": "google",
        "purchase_key": purchase_key(purchase_token),
        "transaction_id": str(order),
        "state_version": int(now.timestamp() * 1000),  # a fresh API read is the newest state
        "customer_token": str(identifiers.get("obfuscatedExternalAccountId") or "").lower() or None,
        "environment": "sandbox" if subscription.get("testPurchase") is not None else "production",
        "product_id": str(item.get("productId") or ""),
        "status": status,
        "auto_renew": auto_renew,
        "trial_ends_at": expiry if status == "trialing" else None,
        "current_period_end": expiry,
        # Google reports the grace end as the line item's expiry while in grace.
        "grace_ends_at": expiry if status == "grace_period" else None,
        "revoked_at": None,
        "pending_product_id": None,
        "superseded_key": purchase_key(subscription["linkedPurchaseToken"]) if subscription.get("linkedPurchaseToken") else None,
        "acknowledged": subscription.get("acknowledgementState") == "ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED",
    }


def verify_push(authorization: str | None, *, verifier: Callable[..., dict[str, Any]] | None = None) -> None:
    """Accept a Pub/Sub push only with Google's OIDC token for DINCR's push identity."""
    audience = os.getenv("DINCR_GOOGLE_RTDN_AUDIENCE", "").strip()
    email = os.getenv("DINCR_GOOGLE_RTDN_SERVICE_ACCOUNT", "").strip()
    if not audience or not email:
        raise GoogleVerificationError("RTDN verification is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise GoogleVerificationError("missing push token")
    if verifier is None:  # pragma: no cover - network call, replaced in tests
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token

        def verifier(token, request, audience):
            return id_token.verify_oauth2_token(token, request, audience=audience)

        request = google_requests.Request()
    else:
        request = None
    try:
        claims = verifier(authorization.split(" ", 1)[1], request, audience=audience)
    except Exception as exc:
        raise GoogleVerificationError("push token is invalid") from exc
    if claims.get("email") != email or not claims.get("email_verified"):
        raise GoogleVerificationError("push token is from another identity")


def decode_push(body: dict[str, Any]) -> dict[str, Any]:
    """The developer notification inside a Pub/Sub push body."""
    try:
        message = body["message"]
        data = message["data"]
        notification = json.loads(base64.b64decode(data))
        if not isinstance(notification, dict):
            raise ValueError("not a JSON object")
    except (KeyError, ValueError, TypeError) as exc:
        raise GoogleVerificationError("malformed push body") from exc
    if notification.get("packageName") != package_name():
        raise GoogleVerificationError("notification is for another app")
    # Pub/Sub always sets messageId; the hash of the data is a stable fallback.
    message_id = str(message.get("messageId") or hashlib.sha256(str(data).encode("utf-8")).hexdigest())
    return {"message_id": message_id, **notification}
