"""Google Play: states come from the Play Developer API; pushes need Google's OIDC token."""
from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.product_ops import store_google

NOW = datetime(2026, 9, 26, 12, tzinfo=timezone.utc)
ISO = lambda dt: dt.isoformat().replace("+00:00", "Z")  # noqa: E731


def _subscription(state="SUBSCRIPTION_STATE_ACTIVE", expiry=NOW + timedelta(days=20), **extra):
    item = {"productId": "finva.vip.monthly", "expiryTime": ISO(expiry), "autoRenewingPlan": {"autoRenewEnabled": True}}
    item.update(extra.pop("item", {}))
    return {"subscriptionState": state, "latestOrderId": "GPA.1", "lineItems": [item],
            "externalAccountIdentifiers": {"obfuscatedExternalAccountId": "TOKEN-A"}, **extra}


@pytest.mark.parametrize(("state", "expiry", "extra", "status"), [
    ("SUBSCRIPTION_STATE_ACTIVE", NOW + timedelta(days=5), {}, "active"),
    ("SUBSCRIPTION_STATE_CANCELED", NOW + timedelta(days=5), {}, "active"),  # paid until the end
    ("SUBSCRIPTION_STATE_CANCELED", NOW - timedelta(days=1), {}, "expired"),
    ("SUBSCRIPTION_STATE_IN_GRACE_PERIOD", NOW + timedelta(days=3), {}, "grace_period"),
    ("SUBSCRIPTION_STATE_ON_HOLD", NOW + timedelta(days=3), {}, "expired"),
    ("SUBSCRIPTION_STATE_PENDING", NOW + timedelta(days=3), {}, "expired"),
    ("SUBSCRIPTION_STATE_EXPIRED", NOW - timedelta(days=1), {}, "expired"),
    ("SUBSCRIPTION_STATE_ACTIVE", NOW + timedelta(days=5), {"item": {"offerDetails": {"offerTags": ["free-trial"]}}}, "trialing"),
])
def test_play_states_map_to_dincr_states(state, expiry, extra, status):
    result = store_google.purchase_state("token-1", _subscription(state, expiry, **extra), now=NOW)
    assert result["status"] == status
    assert result["purchase_key"] == store_google.purchase_key("token-1") != "token-1"  # the token is never stored
    assert result["customer_token"] == "token-a"


def test_a_replacing_purchase_names_the_one_it_supersedes():
    result = store_google.purchase_state("new", _subscription(linkedPurchaseToken="old"), now=NOW)
    assert result["superseded_key"] == store_google.purchase_key("old")


def test_test_purchases_are_sandbox():
    assert store_google.purchase_state("t", _subscription(testPurchase={}), now=NOW)["environment"] == "sandbox"


def test_a_multi_item_purchase_is_refused():
    subscription = _subscription()
    subscription["lineItems"] *= 2
    with pytest.raises(store_google.GoogleVerificationError):
        store_google.purchase_state("t", subscription, now=NOW)


@pytest.fixture
def push_env(monkeypatch):
    monkeypatch.setenv("DINCR_GOOGLE_RTDN_AUDIENCE", "https://api.example.invalid/rtdn")
    monkeypatch.setenv("DINCR_GOOGLE_RTDN_SERVICE_ACCOUNT", "push@example.iam.gserviceaccount.com")
    monkeypatch.setenv("FINVA_GOOGLE_PACKAGE_NAME", "com.dincr.app")


def test_a_push_with_googles_token_for_the_push_identity_is_accepted(push_env):
    seen = {}

    def verifier(token, _request, audience):
        seen.update(token=token, audience=audience)
        return {"email": "push@example.iam.gserviceaccount.com", "email_verified": True}

    store_google.verify_push("Bearer oidc-token", verifier=verifier)
    assert seen == {"token": "oidc-token", "audience": "https://api.example.invalid/rtdn"}


@pytest.mark.parametrize("authorization,claims,error", [
    (None, {}, "missing"),
    ("Bearer x", {"email": "attacker@example.com", "email_verified": True}, "another identity"),
    ("Bearer x", {"email": "push@example.iam.gserviceaccount.com", "email_verified": False}, "another identity"),
    ("Bearer x", Exception("bad signature"), "invalid"),
])
def test_other_pushes_are_rejected(push_env, authorization, claims, error):
    def verifier(*_args, **_kwargs):
        if isinstance(claims, Exception):
            raise claims
        return claims

    with pytest.raises(store_google.GoogleVerificationError, match=error):
        store_google.verify_push(authorization, verifier=verifier)


def test_push_verification_fails_closed_without_configuration(monkeypatch):
    monkeypatch.delenv("DINCR_GOOGLE_RTDN_AUDIENCE", raising=False)
    with pytest.raises(store_google.GoogleVerificationError, match="not configured"):
        store_google.verify_push("Bearer x", verifier=lambda *_a, **_k: {})


def test_a_push_for_another_package_is_rejected(push_env):
    data = base64.b64encode(json.dumps({"packageName": "com.other.app"}).encode()).decode()
    with pytest.raises(store_google.GoogleVerificationError, match="another app"):
        store_google.decode_push({"message": {"data": data, "messageId": "1"}})
    data = base64.b64encode(json.dumps({"packageName": "com.dincr.app",
                                        "subscriptionNotification": {"purchaseToken": "t", "notificationType": 2}}).encode()).decode()
    assert store_google.decode_push({"message": {"data": data, "messageId": "7"}})["message_id"] == "7"


def test_the_order_is_the_latest_successful_one_and_never_a_missing_value():
    with_line_order = _subscription(item={"latestSuccessfulOrderId": "GPA.2"})
    assert store_google.purchase_state("t", with_line_order, now=NOW)["transaction_id"] == "GPA.2"
    assert store_google.purchase_state("t", _subscription(), now=NOW)["transaction_id"] == "GPA.1"
    without = _subscription()
    without.pop("latestOrderId")
    assert store_google.purchase_state("t", without, now=NOW)["transaction_id"].startswith("expiry:")
    without["lineItems"][0].pop("expiryTime")
    with pytest.raises(store_google.GoogleVerificationError):
        store_google.purchase_state("t", without, now=NOW)
