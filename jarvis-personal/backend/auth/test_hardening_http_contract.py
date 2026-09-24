"""HTTP-level contract for the auth hardening: what the app actually receives.

Service-level tests cannot see the middleware stack (error handlers, language,
CORS), which is where these guarantees could silently break.
"""
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend import main
from backend.auth import routes as auth_routes
from backend.auth import service as auth_service
from backend.core.i18n import tx

AUTH = {"Authorization": "Bearer test-token"}
USER = {"id": 50, "account_id": "account-u", "workspace_id": "workspace-u", "role": "user", "email": "persona@example.com"}


def test_deletion_pending_code_reaches_the_app(monkeypatch):
    monkeypatch.setattr(main, "authenticate_access_token", lambda _token, **_kwargs: USER)

    def pending():
        raise HTTPException(status_code=409, detail={
            "message": "pending", "code": auth_service.DELETION_PENDING_CODE, "deletion_id": "d-1", "stage": "SUPABASE_AUTH_DELETE"})

    monkeypatch.setattr(auth_routes, "delete_current_account", pending)
    response = TestClient(main.app, raise_server_exceptions=False).delete("/auth/me", headers=AUTH)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "account_deletion_pending", "not replaced by the generic 5xx handler"


def test_pending_account_on_get_me_returns_the_code(monkeypatch):
    def reject(_token, **_kwargs):
        raise HTTPException(status_code=409, detail={"code": auth_service.DELETION_PENDING_CODE, "message": "x"})

    monkeypatch.setattr(main, "authenticate_access_token", reject)
    response = TestClient(main.app, raise_server_exceptions=False).get("/auth/me", headers=AUTH)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "account_deletion_pending"


def test_only_delete_auth_me_may_run_on_a_pending_account(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "authenticate_access_token", lambda _token, **kwargs: calls.append(kwargs) or USER)
    monkeypatch.setattr(auth_routes, "delete_current_account", lambda: {"status": "OK"})
    client = TestClient(main.app, raise_server_exceptions=False)
    client.delete("/auth/me", headers=AUTH)
    client.get("/auth/me", headers=AUTH)
    assert calls[0] == {"allow_deletion_pending": True}
    assert calls[1] == {}


def test_identity_messages_follow_accept_language(monkeypatch):
    def reject(_token, **_kwargs):
        raise HTTPException(status_code=403, detail=tx(auth_service.IDENTITY_REJECTED_ES, auth_service.IDENTITY_REJECTED_EN))

    monkeypatch.setattr(main, "authenticate_access_token", reject)
    client = TestClient(main.app, raise_server_exceptions=False)
    en = client.get("/auth/me", headers={**AUTH, "Accept-Language": "en-US"})
    es = client.get("/auth/me", headers={**AUTH, "Accept-Language": "es-CR"})
    assert en.json()["detail"] == auth_service.IDENTITY_REJECTED_EN
    assert es.json()["detail"] == auth_service.IDENTITY_REJECTED_ES


def test_cors_exposes_the_recovery_headers():
    response = TestClient(main.app).get("/status", headers={"Origin": "capacitor://localhost"})
    exposed = response.headers.get("access-control-expose-headers", "").lower()
    for header in ("x-idempotency-status", "x-idempotency-replayed", "retry-after"):
        assert header in exposed, header
