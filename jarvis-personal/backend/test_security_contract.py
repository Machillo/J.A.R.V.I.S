from fastapi import HTTPException

from backend import main
from backend.notifications import routes as notification_routes


def test_public_status_contains_no_identity_or_configuration():
    assert main.status() == {"status": "ok"}
    assert main._is_public_path("/status") is True
    assert main._is_public_path("/openapi.json") is False
    assert main._is_public_path("/docs") is False


def test_internal_error_payload_never_exposes_exception_details():
    payload = main._internal_error_payload("public-reference")
    assert payload == {
        "detail": "Ocurrió un error interno. Intentá nuevamente.",
        "error_id": "public-reference",
    }
    assert "error" not in payload
    assert "error_type" not in payload
    assert "path" not in payload


def test_notification_cron_fails_closed_without_secret(monkeypatch):
    monkeypatch.delenv("NOTIFICATION_CRON_SECRET", raising=False)
    monkeypatch.delenv("EMAIL_MONITOR_CRON_SECRET", raising=False)
    called = False

    def fake_send():
        nonlocal called
        called = True

    monkeypatch.setattr(notification_routes, "send_due_notifications", fake_send)
    try:
        notification_routes.notifications_cron(None)
        assert False, "The cron must reject requests when no secret is configured."
    except HTTPException as exc:
        assert exc.status_code == 503
    assert called is False


def test_notification_cron_rejects_wrong_secret(monkeypatch):
    monkeypatch.setenv("NOTIFICATION_CRON_SECRET", "correct-secret")
    try:
        notification_routes.notifications_cron("wrong-secret")
        assert False, "The cron must reject an invalid secret."
    except HTTPException as exc:
        assert exc.status_code == 403
