from datetime import datetime, timedelta, timezone

from backend.product_ops.store_billing import PRODUCTS, _public_state, store_catalog


def test_store_catalog_has_monthly_and_annual_products():
    catalog = store_catalog()
    assert catalog["currency"] == "CRC"
    assert catalog["trial_days"] > 0
    plans = {item["code"]: item for item in catalog["plans"]}
    assert set(plans) == {"basic", "vip"}
    assert plans["basic"]["monthly"]["price_crc"] == 2990
    assert plans["basic"]["annual"]["price_crc"] == 29900
    assert plans["vip"]["monthly"]["price_crc"] == 5990
    assert plans["vip"]["annual"]["price_crc"] == 59900
    for code in ("basic", "vip"):
        assert plans[code]["monthly"]["product_id"] == PRODUCTS[code]["monthly"]["product_id"]
        assert plans[code]["annual"]["product_id"] == PRODUCTS[code]["annual"]["product_id"]
        assert plans[code]["annual"]["price_crc"] == plans[code]["monthly"]["price_crc"] * 10


def _row(status="active", plan="basic", period="monthly", end_delta_days=30,
         cancel_at_period_end=False, auto_renew=True):
    now = datetime.now(timezone.utc)
    return {
        "status": status,
        "plan_code": plan,
        "provider": "sandbox",
        "billing_period": period,
        "product_id": PRODUCTS[plan][period]["product_id"],
        "trial_ends_at": None,
        "current_period_end": now + timedelta(days=end_delta_days),
        "cancel_at_period_end": cancel_at_period_end,
        "auto_renew": auto_renew,
        "last_verified_at": now,
    }


def test_free_without_subscription():
    state = _public_state(None)
    assert state["plan"] == "free"
    assert state["entitlement"] == "free"
    assert state["auto_renew"] is False


def test_active_basic_grants_basic():
    assert _public_state(_row())["entitlement"] == "basic"


def test_active_vip_grants_vip():
    assert _public_state(_row(plan="vip"))["entitlement"] == "vip"


def test_cancel_requested_keeps_access_until_period_end():
    state = _public_state(_row(cancel_at_period_end=True, auto_renew=False))
    assert state["entitlement"] == "basic"
    assert state["cancel_at_period_end"] is True
    assert state["auto_renew"] is False


def test_expired_period_returns_free_even_if_status_was_active():
    assert _public_state(_row(end_delta_days=-1))["entitlement"] == "free"


def test_expired_and_revoked_return_free():
    assert _public_state(_row(status="expired"))["entitlement"] == "free"
    assert _public_state(_row(status="revoked"))["entitlement"] == "free"


def test_trial_grants_selected_plan_until_trial_end():
    row = _row(status="trialing", plan="vip")
    row["trial_ends_at"] = datetime.now(timezone.utc) + timedelta(days=7)
    state = _public_state(row)
    assert state["entitlement"] == "vip"
    assert state["status"] == "trialing"


def test_grace_period_keeps_entitlement_temporarily():
    assert _public_state(_row(status="grace_period", plan="vip"))["entitlement"] == "vip"


def test_monthly_and_annual_entitlements_report_period():
    assert _public_state(_row(period="monthly"))["billing_period"] == "monthly"
    assert _public_state(_row(period="annual", end_delta_days=365))["billing_period"] == "annual"
