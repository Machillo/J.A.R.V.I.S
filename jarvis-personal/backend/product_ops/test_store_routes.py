"""Store billing wiring: which paths are public, and the simulator stays off."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend import main
from backend.product_ops import store_billing, store_verification


def test_only_store_notifications_and_the_cron_skip_user_authentication():
    public = {path for path in main.PUBLIC_PATHS if "/billing/store/" in path}
    assert public == {"/product-ops/billing/store/apple/notifications",
                      "/product-ops/billing/store/google/notifications",
                      "/product-ops/billing/store/cron"}
    routes = {route.path for route in main.app.routes}
    assert {"/product-ops/billing/store/customer-token", "/product-ops/billing/store/apple/transactions",
            "/product-ops/billing/store/google/purchases"} <= routes  # authenticated like any user route


def test_the_sandbox_simulator_is_off_unless_explicitly_enabled(monkeypatch):
    monkeypatch.delenv("DINCR_STORE_SIMULATOR", raising=False)
    with pytest.raises(HTTPException) as disabled:
        store_billing.simulate_lifecycle("vip", "monthly", "purchased")
    assert disabled.value.status_code == 404


@pytest.mark.parametrize("secret", [None, "", "wrong"])
def test_the_lapse_cron_needs_its_secret(monkeypatch, secret):
    monkeypatch.setenv("DINCR_STORE_CRON_SECRET", "synthetic-cron-secret")
    with pytest.raises(HTTPException) as refused:
        store_verification.lapse_cron(secret)
    assert refused.value.status_code == 403


def test_the_lapse_cron_fails_closed_without_configuration(monkeypatch):
    monkeypatch.delenv("DINCR_STORE_CRON_SECRET", raising=False)
    with pytest.raises(HTTPException) as refused:
        store_verification.lapse_cron("anything")
    assert refused.value.status_code == 503


def test_an_unverifiable_apple_notification_changes_nothing(monkeypatch):
    monkeypatch.setattr(store_verification, "get_connection", lambda: pytest.fail("nothing may be written"))
    with pytest.raises(HTTPException) as rejected:
        store_verification.apple_notification("not.a.jws")
    assert rejected.value.status_code == 400


def test_an_unauthenticated_google_push_changes_nothing(monkeypatch):
    monkeypatch.setattr(store_verification, "get_connection", lambda: pytest.fail("nothing may be written"))
    monkeypatch.setenv("DINCR_GOOGLE_RTDN_AUDIENCE", "https://api.example.invalid/rtdn")
    monkeypatch.setenv("DINCR_GOOGLE_RTDN_SERVICE_ACCOUNT", "push@example.iam.gserviceaccount.com")
    with pytest.raises(HTTPException) as rejected:
        store_verification.google_notification(None, {"message": {"data": "e30=", "messageId": "1"}})
    assert rejected.value.status_code == 401
