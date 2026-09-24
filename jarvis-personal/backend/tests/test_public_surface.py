"""The unauthenticated surface is a reviewed, closed list.

A new public route (like the removed /auth/check-access, which leaked account
roles) must be added here on purpose, and secret-protected entry points must
refuse anonymous calls before touching any data. Recovered from #220, whose
tests never reached main, and adapted to the current routes.
"""
import pytest
from fastapi.testclient import TestClient

from backend import main

ANONYMOUS = {"/", "/status", "/product-ops/release-policy", "/auth/health"}
# Provider redirects: the signed, single-use OAuth state is the credential.
OAUTH_RETURNS = {"/user-product/vip/gmail/callback", "/user-product/vip/mail/microsoft/callback"}
# Crons, webhooks and bridges: each must verify its own secret/signature.
SECRET_PROTECTED = {
    "/user-product/vip/gmail/maintenance", "/user-product/vip/gmail/push", "/notifications/cron",
    "/deployment-monitor/webhook/github", "/deployment-monitor/webhook/vercel", "/deployment-monitor/webhook/render",
    "/integrations/ibkr/snapshot", "/integrations/ibkr/flex/cron", "/internal/owner-bridge/verify",
}
# The retired Owner Gmail reader (#233): still public so leftover crons and a Pub/Sub
# subscription get a definitive answer, but they never read mail or data.
RETIRED = {"/email-monitor/cron", "/email-monitor/gmail-watch", "/email-monitor/gmail-push"}


def test_public_paths_are_exactly_the_reviewed_list():
    assert main.PUBLIC_PATHS == ANONYMOUS | OAUTH_RETURNS | SECRET_PROTECTED | RETIRED


@pytest.mark.parametrize("path", sorted(RETIRED))
def test_retired_owner_gmail_endpoints_answer_without_reading_anything(path, monkeypatch):
    from backend.email_monitor import service as email_monitor_service

    monkeypatch.setattr(email_monitor_service, "get_connection", lambda: (_ for _ in ()).throw(AssertionError("no data access")))
    response = TestClient(main.app, raise_server_exceptions=False).post(path, json={"message": {"data": "e30"}})
    assert response.status_code == 410 or response.json() == {"status": "retired"}, (path, response.status_code)


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
    for path in ("/auth/me", "/user-product/free/movements", "/auth/me/export", "/product-ops/feature-flags", "/jarvis/memory"):
        assert client.get(path).status_code == 401, path
