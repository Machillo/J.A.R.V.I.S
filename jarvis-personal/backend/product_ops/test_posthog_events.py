import pytest

from backend.product_ops import posthog_events
from backend.user_product import routes as product_routes
from backend.auth import routes as auth_routes
from fastapi import BackgroundTasks
from starlette.responses import RedirectResponse


def test_disabled_backend_capture_never_sends(monkeypatch):
    monkeypatch.delenv("POSTHOG_API_KEY", raising=False)
    monkeypatch.setenv("POSTHOG_HOST", "https://us.i.posthog.com")
    monkeypatch.setattr(posthog_events.requests, "post", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected POST")))
    posthog_events.capture_backend_event("gmail_connected")


def test_only_aggregate_fields_leave_render(monkeypatch):
    monkeypatch.setenv("POSTHOG_API_KEY", "test-project-token")
    monkeypatch.setenv("POSTHOG_HOST", "https://us.i.posthog.com")
    sent = []

    class Response:
        def raise_for_status(self):
            return None

    def fake_post(url, *, json, timeout):
        sent.append((url, json, timeout))
        return Response()

    monkeypatch.setattr(posthog_events.requests, "post", fake_post)
    posthog_events.capture_backend_event("account_deletion_completed")
    assert len(sent) == 1
    assert sent[0][0] == "https://us.i.posthog.com/capture/"
    payload = sent[0][1]
    assert set(payload) == {"api_key", "distinct_id", "event", "properties"}
    assert payload["properties"] == {
        "success": True,
        "source_type": "server",
        "$process_person_profile": False,
        "$geoip_disable": True,
    }
    assert payload["distinct_id"].startswith("dincr_server_")
    assert "account_id" not in payload["properties"]
    assert "workspace_id" not in payload["properties"]
    posthog_events.capture_backend_event("bank_statement_received")
    assert len(sent) == 1


def test_invalid_host_and_network_error_are_fail_open(monkeypatch):
    monkeypatch.setenv("POSTHOG_API_KEY", "test-project-token")
    monkeypatch.setenv("POSTHOG_HOST", "https://untrusted.example.com")
    monkeypatch.setattr(posthog_events.requests, "post", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected POST")))
    posthog_events.capture_backend_event("gmail_connected")
    monkeypatch.setenv("POSTHOG_HOST", "https://us.i.posthog.com")
    monkeypatch.setattr(posthog_events.requests, "post", lambda *args, **kwargs: (_ for _ in ()).throw(posthog_events.requests.Timeout()))
    posthog_events.capture_backend_event("gmail_connected")


def test_gmail_connected_is_reported_only_when_the_session_completes_the_link(monkeypatch):
    # The public callback only parks the authorization; it never reports a connection.
    monkeypatch.setattr(product_routes, "finish_gmail_connection", lambda **kwargs: RedirectResponse("com.finva.app://gmail/callback?gmail=authorized"))
    product_routes.vip_gmail_callback(code="code", state="state")
    monkeypatch.setattr(product_routes, "require_feature", lambda *_args: True)
    request = product_routes.MailConnectionCompleteRequest(flow="00000000-0000-0000-0000-000000000000", completion="c")
    tasks = BackgroundTasks()
    monkeypatch.setattr(product_routes, "complete_mail_connection", lambda *_args: (_ for _ in ()).throw(RuntimeError("rejected")))
    with pytest.raises(RuntimeError):
        product_routes.vip_mail_oauth_complete(request, tasks)
    assert tasks.tasks == []
    monkeypatch.setattr(product_routes, "complete_mail_connection", lambda *_args: {"status": "connected", "provider": "microsoft"})
    product_routes.vip_mail_oauth_complete(request, tasks)
    assert tasks.tasks == []
    monkeypatch.setattr(product_routes, "complete_mail_connection", lambda *_args: {"status": "connected", "provider": "gmail"})
    product_routes.vip_mail_oauth_complete(request, tasks)
    assert len(tasks.tasks) == 1
    assert tasks.tasks[0].args == ("gmail_connected",)


def test_deletion_reports_only_after_success(monkeypatch):
    tasks = BackgroundTasks()
    def failed_delete():
        raise RuntimeError("failed")
    monkeypatch.setattr(auth_routes, "delete_current_account", failed_delete)
    try:
        auth_routes.remove_my_account(tasks)
    except RuntimeError:
        pass
    assert tasks.tasks == []
    monkeypatch.setattr(auth_routes, "delete_current_account", lambda: {"status": "OK"})
    assert auth_routes.remove_my_account(tasks) == {"status": "OK"}
    assert tasks.tasks[0].args == ("account_deletion_completed",)
