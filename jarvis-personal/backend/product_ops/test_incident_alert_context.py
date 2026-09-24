"""A CRITICAL alert must say which request failed, and still nothing private.

Regression: "DINCR · CRITICAL · Pantalla: finva_strategy" arrived from Android and
iOS, but VIP Strategy fires five requests and the alert did not say which one
failed, so the cause could not be told apart from the alert. The alert now carries
the operation (method + path template, ids replaced) and the HTTP status.
Synthetic data only.
"""
from types import SimpleNamespace

from backend.product_ops import service
from backend.product_ops.test_incident_alert_budget import _Conn


def _incident(monkeypatch, path, status):
    captured = {}
    monkeypatch.setattr(service, "get_current_user", lambda: {"account_id": "account-a", "workspace_id": "workspace-a"})
    monkeypatch.setattr(service, "get_connection", lambda: _Conn(0))
    monkeypatch.setattr(service, "ensure_schema", lambda _conn: None)
    monkeypatch.setattr(service, "_incident_fingerprint", lambda _p: "fp")
    monkeypatch.setattr(service, "_send_support_email", lambda **_k: True)
    monkeypatch.setattr(service, "_send_support_discord", lambda **kw: captured.update(kw) or True)
    monkeypatch.setattr(service, "_mark_discord_alerted", lambda _id: None)
    monkeypatch.setattr(service, "_record_event_safely", lambda *_a, **_k: None)
    service.create_automatic_incident(SimpleNamespace(
        path=path, method="get", status=status, screen="finva_strategy", request_id="req-1",
        error_reference="ref-1", retry_count=2, app_version="1.9.11", platform="ios", error_type="http_500",
    ))
    return captured


def test_alert_names_the_failed_operation_with_ids_and_query_removed(monkeypatch):
    sent = _incident(monkeypatch, "/user-product/finance/debts/123?extra_cash=50000", 500)
    assert sent["severity"] == "critical"
    assert sent["payload"].operation == "GET /user-product/finance/debts/:id"
    assert sent["payload"].http_status == 500


def test_discord_message_shows_operation_and_status_but_no_private_data(monkeypatch):
    observed = {}
    monkeypatch.setenv("SUPPORT_DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/123/example-token")
    monkeypatch.setattr(service.requests, "post", lambda url, json, timeout: observed.update(json) or SimpleNamespace(status_code=204))
    assert service._send_support_discord(public_id="DINCR-000009", plan="vip", severity="critical", payload=SimpleNamespace(
        category="error", app_version="1.9.11", platform="android", screen="finva_strategy", error_reference="ref-1",
        operation="GET /user-product/vip/salvavidas", http_status=500,
        message="saldo 350000", email="private@example.com",
    ))
    content = observed["content"]
    assert "Operación: GET /user-product/vip/salvavidas" in content
    assert "HTTP: 500" in content
    for private in ("350000", "private@example.com", "example-token"):
        assert private not in content


def test_alert_without_an_operation_keeps_the_previous_format(monkeypatch):
    observed = {}
    monkeypatch.setenv("SUPPORT_DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/123/example-token")
    monkeypatch.setattr(service.requests, "post", lambda url, json, timeout: observed.update(json) or SimpleNamespace(status_code=204))
    service._send_support_discord(public_id="DINCR-000010", plan="vip", severity="critical", payload=SimpleNamespace(
        category="health", app_version="server", platform="backend", screen="operaciones", error_reference="x",
    ))
    assert "Operación" not in observed["content"]
