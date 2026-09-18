from datetime import datetime, timedelta, timezone

from backend.product_ops.store_billing import PRODUCTS, _claim_store_event, _public_state, store_catalog


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
        "pending_plan_code": None,
        "pending_billing_period": None,
        "pending_effective_at": None,
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


def test_trial_returns_free_after_trial_end_even_if_period_is_still_future():
    row = _row(status="trialing", plan="vip", end_delta_days=30)
    row["trial_ends_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    state = _public_state(row)
    assert state["entitlement"] == "free"
    assert state["plan"] == "free"
    assert state["status"] == "trialing"


def test_trial_accepts_database_serialized_trial_timestamp():
    row = _row(status="trialing", plan="basic", end_delta_days=30)
    row["trial_ends_at"] = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    state = _public_state(row)
    assert state["entitlement"] == "basic"


def test_grace_period_keeps_entitlement_temporarily():
    assert _public_state(_row(status="grace_period", plan="vip"))["entitlement"] == "vip"


def test_monthly_and_annual_entitlements_report_period():
    assert _public_state(_row(period="monthly"))["billing_period"] == "monthly"
    assert _public_state(_row(period="annual", end_delta_days=365))["billing_period"] == "annual"


def test_active_entitlement_accepts_database_serialized_timestamp():
    row = _row(plan="basic")
    row["current_period_end"] = row["current_period_end"].isoformat()
    state = _public_state(row)
    assert state["entitlement"] == "basic"


def test_expired_entitlement_accepts_database_serialized_timestamp():
    row = _row(plan="vip", end_delta_days=-1)
    row["current_period_end"] = row["current_period_end"].isoformat()
    state = _public_state(row)
    assert state["entitlement"] == "free"


def test_public_state_reports_scheduled_downgrade_without_losing_vip():
    row = _row(status="active", plan="vip", period="annual", end_delta_days=365)
    row["pending_plan_code"] = "basic"
    row["pending_billing_period"] = "annual"
    row["pending_effective_at"] = row["current_period_end"]
    state = _public_state(row)
    assert state["entitlement"] == "vip"
    assert state["plan"] == "vip"
    assert state["pending_plan"] == "basic"
    assert state["pending_billing_period"] == "annual"
    assert state["pending_effective_at"] == row["current_period_end"]


class _ClaimResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _ClaimConnection:
    def __init__(self, row):
        self.row = row
        self.query = None
        self.params = None

    def execute(self, query, params=()):
        self.query = query
        self.params = params
        return _ClaimResult(self.row)


def test_claim_store_event_binds_provider_id_and_uses_atomic_conflict_guard():
    conn = _ClaimConnection({"id": 123})
    claimed = _claim_store_event(conn, "acct", "google", "renewed", "evt-001", "basic", "monthly")
    assert claimed is True
    assert "ON CONFLICT DO NOTHING" in conn.query
    assert conn.params == ("acct", "google", "renewed", "evt-001", "basic", "monthly")


def test_claim_store_event_reports_duplicate_when_conflict_returns_no_row():
    conn = _ClaimConnection(None)
    claimed = _claim_store_event(conn, "acct", "apple", "renewed", "evt-duplicate", "vip", "annual")
    assert claimed is False
