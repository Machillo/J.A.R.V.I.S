"""Adversarial authorization tests from the pre-launch audit.

Any Google/Apple login provisions a DINCR account, so "authenticated" is not a
trust boundary: owner-only capabilities must check the role server-side.
"""
import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.email_monitor import routes as email_monitor_routes

AUTH = {"Authorization": "Bearer test-token"}
USERS = {
    "user": {"id": 50, "account_id": "account-u", "workspace_id": "workspace-u", "role": "user", "email": "u@example.com"},
    "owner": {"id": 1, "account_id": "account-o", "workspace_id": "workspace-o", "role": "owner", "email": "o@example.com"},
}


@pytest.fixture
def as_role(monkeypatch):
    def client(role):
        monkeypatch.setattr(main, "authenticate_access_token", lambda _token: USERS[role])
        monkeypatch.setattr(main, "disabled_feature_for_request", lambda *_a, **_k: None)
        return TestClient(main.app, raise_server_exceptions=False)
    return client


def test_regular_account_cannot_read_the_owners_gmail(as_role, monkeypatch):
    """Before the fix any account could list the owner's mailbox with an arbitrary Gmail query."""
    calls = []
    monkeypatch.setattr(email_monitor_routes, "sync_gmail_for_owner",
                        lambda **kwargs: calls.append(kwargs) or {"processed": [{"subject": "secret", "sender": "x"}]})

    response = as_role("user").post("/email-monitor/sync-gmail?query=in:anywhere&current_month_only=false", headers=AUTH)

    assert response.status_code == 403
    assert calls == [] and "secret" not in response.text


def test_owner_can_still_sync_their_gmail(as_role, monkeypatch):
    calls = []
    monkeypatch.setattr(email_monitor_routes, "sync_gmail_for_owner", lambda **kwargs: calls.append(kwargs) or {"status": "OK"})
    assert as_role("owner").post("/email-monitor/sync-gmail", headers=AUTH).status_code == 200
    assert len(calls) == 1


# Legacy DINCR Owner (JARVIS Personal) APIs: scoped to the caller's workspace, but they
# bypassed plans, edited bank-confirmed movements and let any account trigger the
# owner's IBKR sync. The public app only uses /user-product, /product-ops and /auth.
LEGACY = [
    ("get", "/finance/summary"), ("delete", "/finance/debts/1"), ("get", "/goals/"), ("put", "/transactions/1"),
    ("delete", "/transactions/1"), ("get", "/reports/monthly"), ("get", "/advisor/summary"),
    ("post", "/decisions/extra-money"), ("post", "/imports/bac-pdf/preview"),
    ("post", "/finance/investment-center/sync-ibkr"), ("get", "/finance/business-center"),
    ("post", "/ask"), ("get", "/events"), ("get", "/logs"), ("get", "/deployment-monitor"),
]


@pytest.mark.parametrize(("method", "path"), LEGACY)
def test_regular_accounts_cannot_use_owner_apis(as_role, method, path):
    assert getattr(as_role("user"), method)(path, headers=AUTH).status_code == 403


@pytest.mark.parametrize(("method", "path"), LEGACY)
def test_owner_keeps_access_to_owner_apis(as_role, method, path):
    assert getattr(as_role("owner"), method)(path, headers=AUTH).status_code != 403


def test_every_legacy_route_requires_an_internal_role():
    prefixes = ("/finance", "/goals", "/transactions", "/reports", "/advisor", "/decisions", "/imports")
    for route in main.app.routes:
        path = getattr(route, "path", "")
        if path.startswith(prefixes) or path in {"/ask", "/events", "/logs"}:
            assert main.INTERNAL_ONLY[0] in route.dependencies, f"{path} must require owner/admin"


def test_public_dincr_app_routes_are_not_role_gated(as_role):
    # DINCR customers keep their product APIs (they fail later on the missing test DB, not with 403).
    for path in ("/user-product/free/movements", "/auth/me", "/product-ops/feature-flags"):
        assert as_role("user").get(path, headers=AUTH).status_code != 403

def test_account_existence_cannot_be_probed_without_login():
    # /auth/check-access returned the full allowed_users row (role, supabase id) for any email.
    response = TestClient(main.app, raise_server_exceptions=False).post("/auth/check-access", json={"email": "victim@example.com"})
    assert response.status_code in {401, 404}
    assert "victim@example.com" not in response.text and "role" not in response.text
    assert all(getattr(route, "path", "") != "/auth/check-access" for route in main.app.routes)


@pytest.mark.parametrize(("method", "path"), [
    ("get", "/notifications/status"), ("get", "/notifications/vapid-public-key"),
    ("post", "/notifications/subscribe"), ("post", "/notifications/test"),
    ("post", "/email-monitor/statements/reconcile"),
])
def test_owner_push_and_reconciliation_are_not_user_apis(as_role, method, path):
    kwargs = {"json": {"endpoint": "http://169.254.169.254/latest", "statement_id": 1}} if method == "post" else {}
    assert getattr(as_role("user"), method)(path, headers=AUTH, **kwargs).status_code == 403


def test_push_subscriptions_only_accept_real_push_services(as_role, monkeypatch):
    from backend.notifications import service as notifications

    monkeypatch.setattr(notifications, "get_current_user_id", lambda: 1)
    monkeypatch.setattr(notifications, "get_current_workspace_id", lambda: "workspace-o")
    monkeypatch.setattr(notifications, "get_connection", lambda: (_ for _ in ()).throw(AssertionError("must not store")))
    for endpoint in ("http://169.254.169.254/latest", "https://internal.example.com/push", "https://fcm.googleapis.com.evil.io/x"):
        assert notifications.save_push_subscription({"endpoint": endpoint})["status"] == "ERROR"
    assert notifications._is_push_service_endpoint("https://fcm.googleapis.com/fcm/send/abc")
    assert notifications._is_push_service_endpoint("https://web.push.apple.com/abc")
