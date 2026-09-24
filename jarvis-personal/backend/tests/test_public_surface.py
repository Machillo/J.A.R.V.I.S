"""The unauthenticated surface is a reviewed, closed list.

A new public route (like the removed /auth/check-access, which leaked account
roles) must be added here on purpose, and secret-protected entry points must
refuse anonymous calls before touching any data.
"""
import pytest
from fastapi.testclient import TestClient

from backend import main

ANONYMOUS = {"/", "/status", "/product-ops/release-policy", "/auth/health"}
# Provider redirects: the signed, single-use OAuth state is the credential.
OAUTH_RETURNS = {"/user-product/vip/gmail/callback", "/user-product/vip/mail/microsoft/callback"}
# Crons, webhooks and bridges: each must verify its own secret/signature.
SECRET_PROTECTED = {
    "/email-monitor/cron", "/email-monitor/gmail-watch", "/email-monitor/gmail-push",
    "/user-product/vip/gmail/maintenance", "/user-product/vip/gmail/push", "/notifications/cron",
    "/deployment-monitor/webhook/github", "/deployment-monitor/webhook/vercel", "/deployment-monitor/webhook/render",
    "/integrations/ibkr/snapshot", "/integrations/ibkr/flex/cron", "/internal/owner-bridge/verify",
}


def test_public_paths_are_exactly_the_reviewed_list():
    assert main.PUBLIC_PATHS == ANONYMOUS | OAUTH_RETURNS | SECRET_PROTECTED


@pytest.mark.parametrize("path", sorted(SECRET_PROTECTED))
def test_secret_protected_entry_points_refuse_anonymous_calls(path, monkeypatch):
    monkeypatch.setattr(main, "get_connection", lambda: (_ for _ in ()).throw(AssertionError("no data access")), raising=False)
    client = TestClient(main.app, raise_server_exceptions=False)
    # Templated routes (/deployment-monitor/webhook/{provider}) have no exact match: they are POST webhooks.
    methods = [route.methods for route in main.app.routes if getattr(route, "path", "") == path] or [{"POST"}]
    method = sorted(methods[0] - {"HEAD", "OPTIONS"})[0].lower()
    response = getattr(client, method)(path, headers={"X-Forwarded-For": "203.0.113.9"})
    assert response.status_code in {400, 401, 403, 404, 405, 422, 503}, (path, response.status_code, response.text[:200])


def test_any_other_route_requires_a_session():
    client = TestClient(main.app, raise_server_exceptions=False)
    for path in ("/auth/me", "/user-product/free/movements", "/auth/me/export", "/product-ops/feature-flags", "/jarvis/ask"):
        assert client.get(path).status_code == 401, path
