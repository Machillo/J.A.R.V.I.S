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
