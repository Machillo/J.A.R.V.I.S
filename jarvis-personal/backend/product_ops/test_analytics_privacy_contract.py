"""Central privacy guard for server analytics (PostHog).

Analytics observes product behavior, never the user's financial content. These
tests make it hard to add a sensitive field by accident: the property contract
is checked by name, every capture call in the backend is checked statically, and
hostile values are proven to be dropped before the network.
"""
import ast
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend import main
from backend.product_ops import posthog_events
from backend.user_product import mail_sync_analytics

BACKEND = Path(__file__).resolve().parents[1]
SENSITIVE = re.compile(
    r"amount|balance|salary|income|debt|iban|account|workspace|card|sinpe|subject|body|snippet|sender|recipient|"
    r"counterpart|payee|payer|email|mail_?address|name|token|secret|password|cookie|auth|header|raw|payload|"
    r"description|merchant|url|query|stack|(^|_)message($|_)|(^|_)ip($|_)|phone|user|person|mailbox|connection",
    re.I,
)
HOSTILE = {
    "amount": 12500, "balance": 1, "salary": 1, "debt": 1, "iban": "CR05015202001026284066", "card": "4111111111111111",
    "sinpe": "88888888", "subject": "Pago recibido", "body": "Hola", "snippet": "Compra", "sender": "banco@example.com",
    "counterparty": "Persona", "email": "a@example.com", "access_token": "ya29.secret", "refresh_token": "1//secret",
    "authorization": "Bearer secret", "cookie": "sb=secret", "password": "p", "raw_payload": {"amount": 1},
    "account_id": "00000000-0000-0000-0000-000000000001", "workspace_id": "w", "connection_id": 7,
    # Allowed names with values that must still be refused:
    "provider": "yahoo", "trigger": "Bearer x", "route": "/user-product/vip/gmail/42?token=secret",
    "exception_type": "ValueError: CR05015202001026284066", "messages_scanned": -3, "status_code": "500",
    "duration_ms": True, "plan": "platinum", "error_code": "invalid_grant for a@example.com",
}


def test_no_allowed_server_property_name_is_sensitive():
    for event, names in posthog_events.SERVER_EVENTS.items():
        for name in names:
            assert not SENSITIVE.search(name), f"{event}.{name} looks sensitive"


@pytest.mark.parametrize("event", sorted(posthog_events.SERVER_EVENTS))
def test_hostile_values_never_pass(event):
    assert posthog_events.safe_server_properties(event, HOSTILE) == {}


def test_valid_values_pass_bounded():
    safe = posthog_events.safe_server_properties("mail_sync_completed", {
        "provider": "gmail", "trigger": "push", "scan_scope": "recent", "initial_scan_complete": True,
        "duration_ms": 1234.5, "messages_scanned": 250_000, "candidates_pending": 2, "duplicates": 0, "payroll_reports": 1,
    })
    assert safe == {"provider": "gmail", "trigger": "push", "scan_scope": "recent", "initial_scan_complete": True,
                    "duration_ms": 1200, "messages_scanned": 100_000, "candidates_pending": 2, "duplicates": 0, "payroll_reports": 1}


def _capture_calls():
    for path in BACKEND.rglob("*.py"):
        if path.name.startswith("test_") or "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if name in {"capture_backend_event", "capture_backend_event_later"} and path.name != "posthog_events.py":
                    yield path, node
                if name == "add_task" and node.args and getattr(node.args[0], "id", None) == "capture_backend_event":
                    yield path, SimpleNamespace(args=node.args[1:], lineno=node.lineno)


def test_every_capture_call_uses_a_contract_event_and_allowed_keys():
    calls = list(_capture_calls())
    assert len(calls) >= 6  # deletion, gmail_connected, sync x2, server_error, subscription
    for path, call in calls:
        event = call.args[0]
        assert isinstance(event, ast.Constant) and event.value in posthog_events.SERVER_EVENTS, f"{path}:{call.lineno}"
        if len(call.args) > 1 and isinstance(call.args[1], ast.Dict):
            keys = {key.value for key in call.args[1].keys}
            assert keys <= posthog_events.SERVER_EVENTS[event.value], f"{path}:{call.lineno} sends {keys}"


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("POSTHOG_API_KEY", "phc_test_project_key")
    monkeypatch.setenv("POSTHOG_HOST", "https://us.i.posthog.com")
    monkeypatch.delenv("ANALYTICS_ENVIRONMENT", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    sent = []

    class Response:
        def raise_for_status(self):
            return None

    monkeypatch.setattr(posthog_events.requests, "post", lambda url, *, json, timeout: sent.append(json) or Response())
    # Run queued events inline so tests can inspect them.
    monkeypatch.setattr(posthog_events, "_executor", SimpleNamespace(submit=lambda fn, *args: fn(*args)))
    return sent


def test_payload_is_anonymous_and_tenant_free(configured):
    posthog_events.capture_backend_event_later("mail_sync_completed", {"provider": "gmail", **HOSTILE, "provider": "gmail"})
    posthog_events.capture_backend_event_later("mail_sync_completed", {"provider": "gmail"})
    first, second = configured
    assert first["distinct_id"] != second["distinct_id"] and first["distinct_id"].startswith("dincr_server_")
    text = repr(first)
    for secret in ("CR05015202001026284066", "a@example.com", "secret", "Pago", "00000000-0000-0000-0000-000000000001", "12500"):
        assert secret not in text
    assert first["properties"]["$process_person_profile"] is False and first["properties"]["$geoip_disable"] is True
    assert first["properties"]["provider"] == "gmail"


def test_disabled_analytics_queues_and_sends_nothing(monkeypatch):
    monkeypatch.delenv("POSTHOG_API_KEY", raising=False)
    monkeypatch.setattr(posthog_events, "_executor", SimpleNamespace(submit=lambda *_a: (_ for _ in ()).throw(AssertionError("queued"))))
    monkeypatch.setattr(posthog_events.requests, "post", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("sent")))
    posthog_events.capture_backend_event_later("mail_sync_failed", {"provider": "gmail"})
    posthog_events.capture_backend_event("server_error", {"status_code": 500})


def test_analytics_failure_never_breaks_the_caller(configured, monkeypatch):
    monkeypatch.setattr(posthog_events.requests, "post", lambda *_a, **_k: (_ for _ in ()).throw(posthog_events.requests.ConnectionError()))
    posthog_events.capture_backend_event_later("server_error", {"status_code": 500})
    monkeypatch.setattr(posthog_events, "_executor", SimpleNamespace(submit=lambda *_a: (_ for _ in ()).throw(RuntimeError("shutdown"))))
    posthog_events.capture_backend_event_later("server_error", {"status_code": 500})
    assert mail_sync_analytics.observe_mail_sync("gmail", "manual", lambda: {"status": "ok", "found": 1}) == {"status": "ok", "found": 1}


@pytest.mark.parametrize(("environment", "render", "expected"), [
    ("staging", "true", "staging"), ("", "true", "production"), ("", "", "development"), ("weird", "", "development"),
])
def test_environments_are_distinguished(configured, monkeypatch, environment, render, expected):
    monkeypatch.setenv("ANALYTICS_ENVIRONMENT", environment)
    monkeypatch.setenv("RENDER", render)
    posthog_events.capture_backend_event("gmail_connected")
    assert configured[-1]["properties"]["environment"] == expected


def test_each_sync_reports_exactly_one_outcome(configured):
    result = {"status": "ok", "scan_scope": "recent", "initial_scan_complete": True, "found": 4, "pending": 2,
              "duplicates": 1, "payroll_reports": 0, "auto_saved": 0}
    assert mail_sync_analytics.observe_mail_sync("microsoft", "maintenance", lambda: result) is result
    assert [event["event"] for event in configured] == ["mail_sync_completed"]
    properties = configured[0]["properties"]
    assert (properties["provider"], properties["trigger"], properties["messages_scanned"], properties["candidates_pending"]) == ("microsoft", "maintenance", 4, 2)
    assert properties["success"] is True

    def expired():
        raise HTTPException(status_code=409, detail="La conexión de Gmail venció para a@example.com")

    with pytest.raises(HTTPException):
        mail_sync_analytics.observe_mail_sync("gmail", "push", expired)
    failed = configured[-1]
    assert failed["event"] == "mail_sync_failed" and failed["properties"]["error_code"] == "reauth_required"
    assert failed["properties"]["success"] is False and "a@example.com" not in repr(failed)
    assert len(configured) == 2


def test_server_errors_report_the_route_template_not_the_url(monkeypatch):
    seen = []
    monkeypatch.setattr(main, "capture_backend_event_later", lambda event, properties: seen.append((event, properties)))
    request = SimpleNamespace(method="POST", scope={"route": SimpleNamespace(path="/user-product/vip/gmail/candidates/{candidate_id}/accept")},
                              url=SimpleNamespace(path="/user-product/vip/gmail/candidates/42/accept"))
    main._report_server_error(request, 500, ValueError("CR05015202001026284066 for a@example.com"))
    event, properties = seen[0]
    safe = posthog_events.safe_server_properties(event, properties)
    assert safe == {"route": "/user-product/vip/gmail/candidates/{candidate_id}/accept", "method": "POST",
                    "status_code": 500, "exception_type": "ValueError"}


def test_signups_baseline_is_aggregate_deterministic_and_dry_by_default(monkeypatch, capsys):
    from datetime import date

    from backend.scripts import posthog_signups_baseline as baseline

    days = [(date(2026, 9, 1), 3), (date(2026, 9, 2), 0), (date(2026, 9, 3), 1)]
    first, again = baseline.baseline_events(days), baseline.baseline_events(days)
    assert first == again  # same uuids and timestamps on every run
    assert [event["properties"]["count"] for event in first] == [3, 1]  # empty days are skipped
    for event in first:
        assert set(event) == {"event", "uuid", "distinct_id", "timestamp", "properties"}
        assert event["distinct_id"] == "dincr_baseline"
        assert set(event["properties"]) == {"count", "source_type", "environment", "$process_person_profile", "$geoip_disable"}
    assert "role <> 'owner'" in baseline.QUERY and "COUNT(*)" in baseline.QUERY

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def execute(self, _query):
            return SimpleNamespace(fetchall=lambda: [{"day": date(2026, 9, 1), "total": 2}])

    monkeypatch.setattr(baseline, "get_connection", Conn)
    monkeypatch.setattr(baseline.requests, "post", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("dry run sent")))
    assert baseline.main([]) == 0
    assert "Nothing was sent" in capsys.readouterr().out
