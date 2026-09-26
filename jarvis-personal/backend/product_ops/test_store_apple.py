"""App Store signed payloads: only a chain to the pinned Apple root, for DINCR, verifies.

A synthetic certificate chain (root -> intermediate -> leaf with Apple's marker
OIDs) stands in for Apple's; the pinned root fingerprint points at it.
"""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import NameOID

from backend.product_ops import store_apple

NOW = datetime(2026, 9, 26, 12, tzinfo=timezone.utc)
MS = lambda dt: int(dt.timestamp() * 1000)  # noqa: E731


def _name(cn):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _cert(subject, issuer, key, issuer_key, *, oid=None, ca=False, not_after=NOW + timedelta(days=365)):
    builder = (x509.CertificateBuilder().subject_name(_name(subject)).issuer_name(_name(issuer))
               .public_key(key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(NOW - timedelta(days=30)).not_valid_after(not_after)
               .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
    if oid:
        builder = builder.add_extension(x509.UnrecognizedExtension(x509.ObjectIdentifier(oid), b"\x05\x00"), critical=False)
    return builder.sign(issuer_key, hashes.SHA256())


def _chain(*, leaf_oid=store_apple.APPLE_LEAF_OID.dotted_string, leaf_not_after=NOW + timedelta(days=365)):
    root_key, inter_key, leaf_key = (ec.generate_private_key(ec.SECP256R1()) for _ in range(3))
    root = _cert("Synthetic Root", "Synthetic Root", root_key, root_key, ca=True)
    inter = _cert("Synthetic Intermediate", "Synthetic Root", inter_key, root_key, ca=True,
                  oid=store_apple.APPLE_INTERMEDIATE_OID.dotted_string)
    leaf = _cert("Synthetic Leaf", "Synthetic Intermediate", leaf_key, inter_key, oid=leaf_oid, not_after=leaf_not_after)
    return leaf_key, [leaf, inter, root]


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _sign(payload: dict, key, chain, *, alg="ES256") -> str:
    header = {"alg": alg, "x5c": [base64.b64encode(c.public_bytes(Encoding.DER)).decode() for c in chain]}
    signing_input = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(payload).encode())}"
    r, s = decode_dss_signature(key.sign(signing_input.encode("ascii"), ec.ECDSA(hashes.SHA256())))
    return f"{signing_input}.{_b64url(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"


@pytest.fixture
def apple(monkeypatch):
    key, chain = _chain()
    monkeypatch.setattr(store_apple, "APPLE_ROOT_CA_G3_SHA256", hashlib.sha256(chain[2].public_bytes(Encoding.DER)).hexdigest())
    monkeypatch.setenv("FINVA_APPLE_BUNDLE_ID", "com.dincr.app")
    monkeypatch.delenv("DINCR_APPLE_ENVIRONMENTS", raising=False)
    return key, chain


def _transaction(**overrides):
    base = {"bundleId": "com.dincr.app", "environment": "Production", "productId": "finva.vip.monthly",
            "transactionId": "2000", "originalTransactionId": "1000", "appAccountToken": "AAAA-bbbb",
            "purchaseDate": MS(NOW - timedelta(days=10)), "expiresDate": MS(NOW + timedelta(days=20)),
            "type": "Auto-Renewable Subscription", "inAppOwnershipType": "PURCHASED"}
    return {**base, **overrides}


def test_a_payload_signed_through_the_pinned_chain_verifies(apple):
    key, chain = apple
    assert store_apple.verify_transaction(_sign(_transaction(), key, chain), now=NOW)["productId"] == "finva.vip.monthly"


def test_a_tampered_payload_is_rejected(apple):
    key, chain = apple
    header, _payload, signature = _sign(_transaction(), key, chain).split(".")
    forged = _b64url(json.dumps(_transaction(productId="finva.vip.annual")).encode())
    with pytest.raises(store_apple.AppleVerificationError, match="signature"):
        store_apple.verify_transaction(f"{header}.{forged}.{signature}", now=NOW)


def test_a_chain_to_another_root_is_rejected(apple):
    other_key, other_chain = _chain()  # valid structure, not the pinned root
    with pytest.raises(store_apple.AppleVerificationError, match="pinned"):
        store_apple.verify_transaction(_sign(_transaction(), other_key, other_chain), now=NOW)


@pytest.mark.parametrize("case", ["no_oid", "expired", "short_chain", "alg_none", "garbage"])
def test_malformed_or_foreign_certificates_are_rejected(apple, monkeypatch, case):
    key, chain = apple
    if case == "no_oid":
        key, chain = _chain(leaf_oid="1.2.3.4")
    elif case == "expired":
        key, chain = _chain(leaf_not_after=NOW - timedelta(days=1))
    if case in ("no_oid", "expired"):
        monkeypatch.setattr(store_apple, "APPLE_ROOT_CA_G3_SHA256", hashlib.sha256(chain[2].public_bytes(Encoding.DER)).hexdigest())
    token = {"short_chain": lambda: _sign(_transaction(), key, chain[:2]),
             "alg_none": lambda: _sign(_transaction(), key, chain, alg="none"),
             "garbage": lambda: "not.a.jws"}.get(case, lambda: _sign(_transaction(), key, chain))()
    with pytest.raises(store_apple.AppleVerificationError):
        store_apple.verify_transaction(token, now=NOW)


@pytest.mark.parametrize("overrides", [{"bundleId": "com.other.app"}, {"environment": "Sandbox"}])
def test_other_apps_and_sandbox_are_rejected_by_default(apple, overrides):
    key, chain = apple
    with pytest.raises(store_apple.AppleVerificationError):
        store_apple.verify_transaction(_sign(_transaction(**overrides), key, chain), now=NOW)


def test_the_pinned_root_is_apple_root_ca_g3_and_no_setting_replaces_it(monkeypatch):
    monkeypatch.setenv("DINCR_APPLE_ROOT_CA_SHA256", "00" * 32)
    assert store_apple._pinned_root() == store_apple.APPLE_ROOT_CA_G3_SHA256 == \
        "63343abfb89a6a03ebb57e9b3f5fa7be7c4f5c756f3017b3a8c488c3653e9179"


@pytest.mark.parametrize("overrides", [{"inAppOwnershipType": "FAMILY_SHARED"}, {"type": "Consumable"}])
def test_family_shared_and_non_subscription_purchases_grant_nothing(apple, overrides):
    key, chain = apple
    with pytest.raises(store_apple.AppleVerificationError):
        store_apple.verify_transaction(_sign(_transaction(**overrides), key, chain), now=NOW)


def test_a_header_that_is_not_an_object_is_rejected_not_a_500(apple):
    token = f"{_b64url(b'[1]')}.{_b64url(b'{}')}.{_b64url(bytes(64))}"
    with pytest.raises(store_apple.AppleVerificationError):
        store_apple.verify_transaction(token, now=NOW)


def test_an_upgraded_transaction_describes_nothing():
    assert store_apple.purchase_state(_transaction(isUpgraded=True), now=NOW) is None


def test_a_notification_decodes_its_signed_transaction_and_renewal(apple):
    key, chain = apple
    renewal = _sign({"autoRenewStatus": 1, "autoRenewProductId": "finva.basic.monthly"}, key, chain)
    notification = {"notificationType": "DID_CHANGE_RENEWAL_PREF", "notificationUUID": "n-1",
                    "data": {"bundleId": "com.dincr.app", "environment": "Production",
                             "signedTransactionInfo": _sign(_transaction(), key, chain), "signedRenewalInfo": renewal}}
    decoded = store_apple.verify_notification(_sign(notification, key, chain), now=NOW)
    state = store_apple.purchase_state(decoded["transaction"], decoded["renewal"], now=NOW)
    assert state["status"] == "active" and state["pending_product_id"] == "finva.basic.monthly" and state["auto_renew"]


@pytest.mark.parametrize(("transaction", "renewal", "status"), [
    ({}, None, "active"),
    ({"offerType": 1, "offerDiscountType": "FREE_TRIAL"}, None, "trialing"),
    ({"offerType": 1, "offerDiscountType": "PAY_AS_YOU_GO", "price": 990}, None, "active"),  # paid intro offer
    ({"expiresDate": MS(NOW - timedelta(days=1))}, {"gracePeriodExpiresDate": MS(NOW + timedelta(days=5))}, "grace_period"),
    ({"expiresDate": MS(NOW - timedelta(days=1))}, None, "expired"),
    ({"revocationDate": MS(NOW - timedelta(hours=1))}, None, "revoked"),
])
def test_purchase_state_covers_the_lifecycle(transaction, renewal, status):
    state = store_apple.purchase_state(_transaction(**transaction), renewal, now=NOW)
    assert state["status"] == status
    assert state["purchase_key"] == "1000" and state["customer_token"] == "aaaa-bbbb"
    assert state["transaction_id"] == "2000" and state["state_version"] == MS(NOW - timedelta(days=10))
