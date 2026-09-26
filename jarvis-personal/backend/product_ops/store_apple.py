"""App Store: verify Apple's signed payloads (JWS) and read the purchase state.

StoreKit 2 transactions and App Store Server Notifications V2 are JWS objects
signed by Apple: the header carries the certificate chain (x5c) that ends in the
Apple Root CA - G3. A payload is trusted only when:
- the chain is exactly leaf -> intermediate -> root, each signed by the next;
- the root is the pinned Apple Root CA - G3 (SHA-256 of its DER);
- every certificate is valid now and the leaf/intermediate carry Apple's marker
  OIDs for App Store receipt signing;
- the ES256 signature over header.payload verifies with the leaf key;
- the bundle id is DINCR's and the environment is allowed.
Nothing the client says about a purchase is used without this check.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

from cryptography import x509
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

# SHA-256 of the DER of "Apple Root CA - G3" (https://www.apple.com/certificateauthority/).
# PRE-RELEASE CHECK (human): compare with the certificate published by Apple. It is a
# constant on purpose: no configuration value can replace the trust anchor.
APPLE_ROOT_CA_G3_SHA256 = "63343abfb89a6a03ebb57e9b3f5fa7be7c4f5c756f3017b3a8c488c3653e9179"
APPLE_LEAF_OID = x509.ObjectIdentifier("1.2.840.113635.100.6.11.1")
APPLE_INTERMEDIATE_OID = x509.ObjectIdentifier("1.2.840.113635.100.6.2.1")


class AppleVerificationError(ValueError):
    """The payload is not a valid Apple-signed payload for DINCR."""


def _b64url(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _pinned_root() -> str:
    return APPLE_ROOT_CA_G3_SHA256


def _verify_chain(chain: list[x509.Certificate], now: datetime) -> None:
    if len(chain) != 3:
        raise AppleVerificationError("unexpected certificate chain length")
    leaf, intermediate, root = chain
    if hashlib.sha256(root.public_bytes(_der())).hexdigest() != _pinned_root():
        raise AppleVerificationError("root certificate is not the pinned Apple root")
    for cert in chain:
        if not (cert.not_valid_before_utc <= now <= cert.not_valid_after_utc):
            raise AppleVerificationError("certificate outside its validity period")
    for child, parent in ((leaf, intermediate), (intermediate, root), (root, root)):
        if child.issuer != parent.subject:
            raise AppleVerificationError("certificate chain is broken")
        try:
            parent.public_key().verify(child.signature, child.tbs_certificate_bytes,
                                       ec.ECDSA(child.signature_hash_algorithm))
        except (InvalidSignature, UnsupportedAlgorithm, TypeError, AttributeError, ValueError) as exc:
            raise AppleVerificationError("certificate signature is invalid") from exc
    for cert, oid in ((leaf, APPLE_LEAF_OID), (intermediate, APPLE_INTERMEDIATE_OID)):
        try:
            cert.extensions.get_extension_for_oid(oid)
        except x509.ExtensionNotFound as exc:
            raise AppleVerificationError("certificate is not an App Store signing certificate") from exc


def _der():
    from cryptography.hazmat.primitives.serialization import Encoding

    return Encoding.DER


def verify_jws(token: str, *, now: datetime | None = None) -> dict[str, Any]:
    """Return the payload of an Apple-signed JWS, or raise AppleVerificationError."""
    try:
        header_b64, payload_b64, signature_b64 = str(token).split(".")
        header = json.loads(_b64url(header_b64))
        payload = json.loads(_b64url(payload_b64))
        raw_signature = _b64url(signature_b64)
        if not isinstance(header, dict) or not isinstance(payload, dict):
            raise ValueError("not a JSON object")
        chain = [x509.load_der_x509_certificate(base64.b64decode(item)) for item in header.get("x5c") or []]
    except (ValueError, TypeError, AttributeError) as exc:
        raise AppleVerificationError("malformed signed payload") from exc
    if header.get("alg") != "ES256" or len(raw_signature) != 64:
        raise AppleVerificationError("unexpected signature algorithm")
    _verify_chain(chain, now or datetime.now(timezone.utc))
    signature = encode_dss_signature(int.from_bytes(raw_signature[:32], "big"), int.from_bytes(raw_signature[32:], "big"))
    try:
        chain[0].public_key().verify(signature, f"{header_b64}.{payload_b64}".encode("ascii"), ec.ECDSA(hashes.SHA256()))
    except (InvalidSignature, UnsupportedAlgorithm, TypeError, AttributeError, ValueError) as exc:
        raise AppleVerificationError("payload signature is invalid") from exc
    return payload


def allowed_environments() -> set[str]:
    configured = os.getenv("DINCR_APPLE_ENVIRONMENTS", "Production")
    return {item.strip() for item in configured.split(",") if item.strip()}


def _check_app(payload: dict[str, Any]) -> None:
    bundle_id = os.getenv("FINVA_APPLE_BUNDLE_ID", "").strip()
    if not bundle_id or payload.get("bundleId") != bundle_id:
        raise AppleVerificationError("payload is for another app")
    if payload.get("environment") not in allowed_environments():
        raise AppleVerificationError("payload environment is not accepted")


def _ms(value: Any) -> datetime | None:
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc) if value not in (None, "") else None


def verify_transaction(signed_transaction: str, *, now: datetime | None = None) -> dict[str, Any]:
    """Verified JWSTransactionDecodedPayload of DINCR: an auto-renewable subscription
    bought by this Apple account (Family Sharing does not extend a DINCR plan)."""
    payload = verify_jws(signed_transaction, now=now)
    _check_app(payload)
    if payload.get("type") not in (None, "Auto-Renewable Subscription"):
        raise AppleVerificationError("not a subscription")
    if payload.get("inAppOwnershipType") not in (None, "PURCHASED"):
        raise AppleVerificationError("family-shared purchases do not grant a plan")
    return payload


def verify_notification(signed_payload: str, *, now: datetime | None = None) -> dict[str, Any]:
    """Verified App Store Server Notification V2 with its transaction and renewal info decoded."""
    notification = verify_jws(signed_payload, now=now)
    data = notification.get("data") or {}
    if data.get("bundleId") != os.getenv("FINVA_APPLE_BUNDLE_ID", "").strip():
        raise AppleVerificationError("notification is for another app")
    if data.get("environment") not in allowed_environments():
        raise AppleVerificationError("notification environment is not accepted")
    notification["transaction"] = verify_transaction(data["signedTransactionInfo"], now=now) if data.get("signedTransactionInfo") else None
    notification["renewal"] = verify_jws(data["signedRenewalInfo"], now=now) if data.get("signedRenewalInfo") else None
    return notification


def purchase_state(transaction: dict[str, Any], renewal: dict[str, Any] | None = None, *,
                   now: datetime | None = None) -> dict[str, Any] | None:
    """Map a verified transaction (+ renewal info) to DINCR's per-purchase state.

    None for a transaction that was replaced by an upgrade (isUpgraded): the newer
    transaction of the same subscription describes the plan.
    """
    if transaction.get("isUpgraded"):
        return None
    now = now or datetime.now(timezone.utc)
    expires = _ms(transaction.get("expiresDate"))
    revoked = _ms(transaction.get("revocationDate"))
    grace = _ms((renewal or {}).get("gracePeriodExpiresDate"))
    trial = transaction.get("offerDiscountType") == "FREE_TRIAL" or (
        transaction.get("offerType") == 1 and "offerDiscountType" not in transaction and not transaction.get("price"))
    if revoked:
        status = "revoked"
    elif expires and expires > now:
        status = "trialing" if trial else "active"
    elif grace and grace > now:
        status = "grace_period"
    else:
        status = "expired"
    auto_renew_product = (renewal or {}).get("autoRenewProductId")
    transaction_id = str(transaction.get("transactionId") or "")
    purchased = transaction.get("purchaseDate") or transaction.get("signedDate")
    if not transaction_id or purchased in (None, ""):
        raise AppleVerificationError("transaction without id or purchase date")
    return {
        "provider": "apple",
        "purchase_key": str(transaction["originalTransactionId"]),
        "transaction_id": transaction_id,
        # A later purchase (renewal, upgrade) of the same subscription has a later date.
        "state_version": int(purchased),
        "customer_token": str(transaction.get("appAccountToken") or "").lower() or None,
        "environment": "sandbox" if transaction.get("environment") == "Sandbox" else "production",
        "product_id": str(transaction.get("productId") or ""),
        "status": status,
        "auto_renew": (renewal or {}).get("autoRenewStatus") == 1,
        "trial_ends_at": expires if status == "trialing" else None,
        "current_period_end": expires,
        "grace_ends_at": grace,
        "revoked_at": revoked,
        "pending_product_id": auto_renew_product if auto_renew_product and auto_renew_product != transaction.get("productId") else None,
        "superseded_key": None,
    }
