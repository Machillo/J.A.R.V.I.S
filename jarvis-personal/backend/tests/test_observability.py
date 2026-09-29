"""Production observability: redaction, fingerprints, dedup/cooldown/budget,
recovery, severity, alert payload safety, health endpoints and logging."""
import json
import logging
import re

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.core import observability as ops
from backend.product_ops import observability_routes


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def gate(**kwargs):
    clock = Clock()
    return ops.AlertGate(clock=clock, **{"cooldown_seconds": 600, "quiet_seconds": 900, "budget": 12,
                                         "budget_window_seconds": 600, **kwargs}), clock


def signal(event="server_error", severity="error", **kwargs):
    return ops.Signal("api", event, severity, **{"route": "/user-product/free/movements/{movement_id}", "status": 500,
                                                 "error_class": "OperationalError", **kwargs}).clean()


# --- Redaction ------------------------------------------------------------------

SECRETS = [
    "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NSJ9.c2lnbmF0dXJl",
    "Authorization: Bearer opaqueTok_4f2",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NSJ9.c2lnbmF0dXJl",
    "access_token=ya29.a0AfH6SMBxyz",
    "refresh_token: 1//0gAbCdEfGhIj",
    "password=hunter2",
    "code=4/0AX4XfWjYpQ",
    '"client_secret": "GOCSPX-abcdef"',
    "postgresql://dincr_app:SuperSecret@db.example.supabase.co:5432/postgres",
    "https://discord.com/api/webhooks/123456789012345678/AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcdefghij",
    "https://api.dincr.com/user-product/vip/gmail/callback?code=4/0AX&state=abc",
    "ghp_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
    "sk_live_51HAbCdEfGhIjKlMn",
    "AKIAIOSFODNN7EXAMPLE",
    "persona@example.com",
    "CR05015202001026284066",
    "4111 1111 1111 1111",
    "₡1.234.567,89",
    "cron_secret=hunter2",
    "gmail_token=ya29.a0AfH6SMBxyz",
    "{'password': 'hunter2'}",
    "Authorization: Basic dXNlcjpwYXNz",
]
LEAKS = ["dXNlcjpwYXNz", "opaqueTok", "eyJ", "ya29", "1//0g", "hunter2", "4/0AX", "GOCSPX", "SuperSecret", "AbCdEfGhIjKlMn", "persona", "example.com",
         "05015202001026284066", "4111", "1.234.567", "AKIAIOSFODNN", "state=abc", "sk_live"]


@pytest.mark.parametrize("secret", SECRETS)
def test_sanitize_removes_secrets_pii_and_financial_numbers(secret):
    cleaned = ops.sanitize_text(f"failure detail: {secret} end", 400)
    assert not any(leak in cleaned for leak in LEAKS), cleaned


def test_sanitize_blocks_log_and_discord_injection():
    cleaned = ops.sanitize_text("line1\r\nFAKE LINE ```\n@everyone <@&123456> \x1b[31mred", 200)
    assert "\n" not in cleaned and "\r" not in cleaned and "\x1b" not in cleaned
    assert "`" not in cleaned and "@" not in cleaned
    assert len(ops.sanitize_text("x" * 10000, 50)) <= 50


def test_route_normalization_drops_ids_and_queries():
    assert ops.normalize_route("/user-product/free/movements/expense:42?x=1") == "/user-product/free/movements/:id"
    assert ops.normalize_route("/a/0f6b6c1e-1111-4222-8333-000000000001/b/77#frag") == "/a/:id/b/:id"
    assert ops.normalize_route("/x/<script>alert(1)</script>") == "/x/scriptalert1/script"


def test_signal_clean_rejects_hostile_fields():
    s = ops.Signal("api\n@everyone", "boom", "catastrophic", status=999, request_id="bad id!", duration_ms=-5,
                   error_class="ValueError: persona@example.com").clean()
    assert s.severity == "error" and s.status is None and s.request_id is None and s.duration_ms == 0
    assert "@" not in s.component and "persona" not in s.error_class


def test_fingerprint_ignores_request_specific_data_but_separates_problems():
    a = signal(request_id="aaaaaaaaaaaa", duration_ms=10)
    b = signal(request_id="bbbbbbbbbbbb", duration_ms=9999)
    assert a.fingerprint() == b.fingerprint()
    assert a.fingerprint() != signal(error_class="TimeoutError").fingerprint()
    assert a.fingerprint() != signal(status=502).fingerprint()
    assert a.fingerprint() != signal(route="/auth/me").fingerprint()


# --- Gate: dedup, cooldown, escalation, budget, recovery --------------------------------

def test_first_occurrence_alerts_then_repeats_are_counted_not_sent():
    g, clock = gate()
    assert [a.kind for a in g.record(signal())] == ["new"]
    for _ in range(99):
        clock.now += 1
        assert g.record(signal()) == []
    assert g.snapshot()[0]["occurrences"] == 100


def test_after_the_cooldown_one_summary_reports_the_count():
    g, clock = gate()
    g.record(signal())
    for _ in range(46):
        clock.now += 10
        g.record(signal())
    clock.now = 1000 + 601
    alerts = g.record(signal())
    assert [(a.kind, a.count) for a in alerts] == [("ongoing", 47)]
    text = ops.format_alert(alerts[0], clock.now)
    assert "Ocurrencias: 47 en 10 min" in text and "CONTINÚA" in text


def test_higher_severity_alerts_immediately():
    g, clock = gate()
    g.record(signal(severity="error"))
    clock.now += 5
    assert [a.kind for a in g.record(signal(severity="critical"))] == ["escalated"]


def test_below_minimum_severity_is_logged_not_alerted():
    g, _ = gate()
    assert g.record(signal(severity="warning"), alert_min="error") == []
    assert g.record(signal(event="info_event", severity="info"), alert_min="error") == []


def test_global_budget_caps_alerts_and_sends_one_storm_notice():
    g, clock = gate(budget=3)
    kinds = []
    for index in range(50):
        clock.now += 1
        kinds += [a.kind for a in g.record(signal(error_class=f"Error{index}"))]
    assert kinds.count("new") == 3 and kinds.count("storm") == 1 and len(kinds) == 4
    clock.now += 601
    assert [a.kind for a in g.record(signal(error_class="Fresh"))] == ["new"]


def test_quiet_incident_recovers_once():
    g, clock = gate()
    g.record(signal())
    clock.now += 901
    alerts = g.sweep()
    assert [a.kind for a in alerts] == ["recovered"]
    assert "RECOVERED" in ops.format_alert(alerts[0], clock.now)
    assert g.sweep() == []


def test_probe_success_resolves_only_its_component():
    g, _ = gate()
    g.record(ops.Signal("database", "unreachable", "critical").clean())
    g.record(signal())
    alerts = g.resolve("database")
    assert [(a.kind, a.signal.component) for a in alerts] == [("recovered", "database")]
    assert [row["component"] for row in g.snapshot()] == ["api"]


def test_unalerted_incidents_recover_silently():
    g, clock = gate()
    g.record(signal(severity="warning"), alert_min="error")
    clock.now += 901
    assert g.sweep() == []


def test_tracked_incidents_are_bounded():
    g, clock = gate(max_tracked=5, budget=1000)
    for index in range(50):
        clock.now += 1
        g.record(signal(error_class=f"E{index}"))
    assert len(g.snapshot()) == 5


# --- report(): logs, spike detection, escalation, delivery safety -----------------------

@pytest.fixture
def fresh(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(ops, "GATE", ops.AlertGate(clock=clock))
    monkeypatch.setattr(ops, "SERVER_ERRORS", ops.SpikeCounter(clock=clock))
    monkeypatch.setattr(ops, "_ESCALATIONS", {})
    sent = []
    monkeypatch.setattr(ops.DISPATCHER, "submit", lambda text, critical: sent.append((text, critical)) or True)
    monkeypatch.setenv("OPS_ALERTS_ENABLED", "true")
    monkeypatch.delenv("OPS_ALERT_MIN_SEVERITY", raising=False)
    return clock, sent


def test_report_sends_one_alert_for_a_burst_and_logs_every_occurrence(fresh, caplog):
    _clock, sent = fresh
    with caplog.at_level(logging.INFO, logger="dincr.ops"):
        for _ in range(100):
            ops.report("database", "connect_failed", "critical", error_class="OperationalError")
    assert len(sent) == 1 and sent[0][1] is True  # critical: role mention allowed
    lines = [json.loads(r.getMessage()) for r in caplog.records if r.getMessage().startswith("{") and "ts" in r.getMessage()]
    assert len(lines) == 100 and lines[0]["component"] == "database" and lines[0]["env"]


def test_alerts_stay_local_until_explicitly_enabled(fresh, monkeypatch):
    _clock, sent = fresh
    monkeypatch.delenv("OPS_ALERTS_ENABLED")
    ops.report("database", "connect_failed", "critical")
    assert sent == []


def test_alert_text_never_carries_secrets(fresh):
    _clock, sent = fresh
    ops.report("api", "server_error", "error", route="/auth/me?token=abc", error_class="ValueError persona@example.com",
               error_code="password=hunter2", request_id="req_12345678")
    text = sent[0][0]
    assert "hunter2" not in text and "persona" not in text and "token=abc" not in text
    assert "Request ID: req_12345678" in text and "Entorno:" in text and "Huella:" in text


def test_5xx_spike_raises_a_critical_alert(fresh, monkeypatch):
    _clock, sent = fresh
    monkeypatch.setattr(ops, "GATE", ops.AlertGate(clock=_clock, budget=1000))
    for _ in range(ops.SPIKE_THRESHOLD):
        ops.report("api", "server_error", "error", route="/r", status=500)
    assert any("5xx_spike" in text and "CRITICAL" in text for text, _ in sent)


def test_deliberate_5xx_never_count_toward_a_spike(fresh):
    """Anyone can trigger a deliberate 503 anonymously (store off, secret unset): no paging."""
    _clock, sent = fresh
    for index in range(ops.SPIKE_THRESHOLD * 3):
        ops.report("api", "server_error", "warning", route=f"/r{index % 3}", status=503)
    assert sent == []


def test_spike_counter_is_bounded():
    counter = ops.SpikeCounter(window_seconds=300, cap=50)
    assert max(counter.add() for _ in range(10000)) == 50


def test_one_slow_route_does_not_escalate_the_others(fresh):
    _clock, sent = fresh
    for _ in range(10):
        ops.report("api", "slow_request", "warning", route="/slow", status=200, escalate_after=10)
    ops.report("api", "slow_request", "warning", route="/other", status=200, escalate_after=10)
    assert [("/slow" in text) for text, _ in sent] == [True]


def test_alert_shows_the_latest_request_id(fresh, monkeypatch):
    clock, sent = fresh
    ops.report("api", "server_error", "error", route="/r", status=500, request_id="first_request_1")
    ops.report("api", "server_error", "error", route="/r", status=500, request_id="latest_request_2")
    clock.now += 601
    ops.report("api", "server_error", "error", route="/r", status=500, request_id="latest_request_3")
    assert "Request ID: latest_request_3" in sent[-1][0]


def test_repeated_warnings_escalate_to_an_error_alert(fresh):
    _clock, sent = fresh
    for _ in range(4):
        ops.report("mail", "gmail_sync_failed", "warning", escalate_after=5)
    assert sent == []
    ops.report("mail", "gmail_sync_failed", "warning", escalate_after=5)
    assert len(sent) == 1 and "ERROR" in sent[0][0]


def test_report_never_raises(monkeypatch):
    monkeypatch.setattr(ops, "GATE", None)
    ops.report("api", "server_error", "error")  # no exception


def test_dispatcher_queue_is_bounded():
    dispatcher = ops._Dispatcher(maxsize=2)
    dispatcher.sender = lambda text, critical: __import__("time").sleep(0.2) or True
    results = [dispatcher.submit("x", False) for _ in range(20)]
    assert results.count(False) >= 15 and dispatcher.dropped >= 15


def test_discord_post_allows_no_mentions_and_never_logs_the_webhook(monkeypatch, caplog):
    import requests

    webhook = "https://discord.com/api/webhooks/123456789012345678/SECRETtokenValue0123456789"
    monkeypatch.setenv("OPS_DISCORD_WEBHOOK_URL", webhook)
    monkeypatch.setenv("SUPPORT_DISCORD_ALERT_ROLE_ID", "1234567890")
    posts = []

    def boom(url, json, timeout):
        posts.append(json)
        raise requests.ConnectionError(f"cannot reach {url}")

    monkeypatch.setattr(requests, "post", boom)
    with caplog.at_level(logging.ERROR, logger="dincr.ops"):
        assert ops._post_discord("hello @everyone", critical=False) is False
    assert posts[0]["allowed_mentions"] == {"parse": []}
    assert "SECRETtoken" not in caplog.text
    monkeypatch.setattr(requests, "post", lambda url, json, timeout: posts.append(json) or type("R", (), {"status_code": 204})())
    assert ops._post_discord("x", critical=True) is True
    assert posts[-1]["allowed_mentions"] == {"parse": [], "roles": ["1234567890"]}


def test_discord_rejects_a_non_discord_webhook(monkeypatch):
    import requests

    monkeypatch.setenv("OPS_DISCORD_WEBHOOK_URL", "https://evil.example.com/api/webhooks/1/x")
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("posted to a foreign host"))
    assert ops._post_discord("x", critical=True) is False


def test_heartbeat_failure_alerts_and_success_recovers(fresh):
    _clock, sent = fresh
    ops.heartbeat("store_lapse", ok=False, error_class="OperationalError")
    ops.heartbeat("store_lapse", ok=True)
    assert "store_lapse_failed" in sent[0][0] and "RECOVERED" in sent[1][0]
    assert ops.heartbeats()["store_lapse"]["failures"] >= 1


# --- Access log and uvicorn redaction ------------------------------------------------

def test_access_log_is_one_json_line_with_route_template(caplog):
    route = type("Route", (), {"path": "/user-product/free/movements/{movement_id}"})()
    with caplog.at_level(logging.INFO, logger="dincr.access"):
        ops.access(route, "/user-product/free/movements/expense:42?token=x", "PUT", 200, 12, "req_12345678")
    record = json.loads(caplog.records[-1].getMessage())
    assert record["route"] == "/user-product/free/movements/{movement_id}" and record["status"] == 200
    assert record["duration_ms"] == 12 and record["request_id"] == "req_12345678" and "token" not in json.dumps(record)


def test_slow_requests_report_but_batch_endpoints_are_exempt(fresh):
    _clock, sent = fresh
    reported = []
    original = ops.report
    ops_report = lambda *a, **k: reported.append((a, k)) or original(*a, **k)
    import backend.core.observability as module
    module.report = ops_report
    try:
        ops.access(None, "/auth/me", "GET", 200, ops.SLOW_REQUEST_MS + 1, None)
        ops.access(None, "/user-product/vip/gmail/maintenance", "POST", 200, ops.SLOW_REQUEST_MS * 10, None)
    finally:
        module.report = original
    assert [a[1] for a, _k in reported] == ["slow_request"]


def test_uvicorn_access_log_drops_query_strings():
    record = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
                               ("1.2.3.4:5", "GET", "/user-product/vip/gmail/push?token=SECRET", "1.1", 200), None)
    ops._StripQueryString().filter(record)
    assert "SECRET" not in record.getMessage() and "?[redacted]" in record.getMessage()


def test_exception_summary_never_includes_the_message():
    try:
        raise ValueError("persona@example.com owes 123456789")
    except ValueError as exc:
        summary = ops.exception_summary(exc)
    assert summary.startswith("ValueError") and "persona" not in summary and "123456789" not in summary


# --- Health endpoints ---------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(observability_routes, "_probe", {"at": None, "ok": None})
    monkeypatch.setattr(observability_routes, "check_jobs", lambda: None)  # covered by its own tests
    return TestClient(main.app)


def test_liveness_needs_no_session_and_touches_nothing(client, monkeypatch):
    monkeypatch.setattr(observability_routes, "_database_answers", lambda: pytest.fail("liveness touched the database"))
    response = client.get("/health/live")
    assert response.status_code == 200 and response.json() == {"status": "alive"}
    assert response.headers.get("X-Request-ID")


def test_readiness_is_minimal_and_reports_database_state(client, monkeypatch):
    monkeypatch.setattr(observability_routes, "_database_answers", lambda: True)
    monkeypatch.setattr(ops, "GATE", ops.AlertGate())
    ok = client.get("/health/ready")
    assert ok.status_code == 200 and ok.json() == {"status": "healthy", "checks": {"database": "ok"}}
    monkeypatch.setattr(observability_routes, "_probe", {"at": None, "ok": None})
    monkeypatch.setattr(observability_routes, "_database_answers", lambda: False)
    down = client.get("/health/ready")
    assert down.status_code == 503 and down.json() == {"status": "unhealthy", "checks": {"database": "fail"}}
    assert not re.search(r"postgres|supabase|host|dsn|version|trace", down.text, re.I)


def test_readiness_is_degraded_with_open_server_incidents(client, monkeypatch):
    monkeypatch.setattr(observability_routes, "_database_answers", lambda: True)
    g = ops.AlertGate()
    g.record(signal(), alert_min="critical")
    monkeypatch.setattr(ops, "GATE", g)
    assert client.get("/health/ready").json()["status"] == "degraded"


def test_readiness_probe_is_shared_so_a_flood_is_one_database_check(client, monkeypatch):
    calls = []
    monkeypatch.setattr(observability_routes, "_database_answers", lambda: calls.append(1) or False)
    for _ in range(25):
        client.get("/health/ready")
    assert len(calls) == 1


def test_database_probe_failure_reports_type_only(monkeypatch):
    import psycopg2

    reported = []
    monkeypatch.setattr(observability_routes.database, "DATABASE_URL", "postgresql://u:p@h/db")
    monkeypatch.setattr(psycopg2, "connect", lambda *a, **k: (_ for _ in ()).throw(psycopg2.OperationalError("password authentication failed for u at h")))
    monkeypatch.setattr(ops, "report", lambda *a, **k: reported.append((a, k)))
    assert observability_routes._database_answers() is False
    (args, kwargs), = reported
    assert args[:3] == ("database", "unreachable", "critical") and kwargs["error_class"] == "OperationalError"
    assert "password" not in repr(kwargs)


def test_owner_observability_requires_the_owner(client, monkeypatch):
    monkeypatch.setattr(main, "authenticate_access_token", lambda _t, **_k: {"id": 1, "role": "user", "account_id": "a", "workspace_id": "w"})
    assert client.get("/product-ops/owner/observability", headers={"Authorization": "Bearer t"}).status_code == 403
    assert client.get("/product-ops/owner/observability").status_code == 401


def test_owner_observability_never_includes_the_webhook(client, monkeypatch):
    monkeypatch.setenv("SUPPORT_DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1/SECRETVALUE")
    monkeypatch.setattr(main, "authenticate_access_token", lambda _t, **_k: {"id": 1, "role": "owner", "account_id": "a", "workspace_id": "w"})
    monkeypatch.setattr(observability_routes, "_database_answers", lambda: True)
    body = client.get("/product-ops/owner/observability", headers={"Authorization": "Bearer t"})
    assert body.status_code == 200 and "SECRETVALUE" not in body.text and body.json()["webhook_configured"] is True


# --- API wiring ---------------------------------------------------------------------

def test_unhandled_error_reports_once_and_hides_details(monkeypatch):
    reported = []
    monkeypatch.setattr(main.ops, "report", lambda *a, **k: reported.append((a, k)))
    monkeypatch.setattr(main, "authenticate_access_token", lambda _t, **_k: {"id": 1, "role": "user", "account_id": "a", "workspace_id": "w"})

    @main.app.get("/__test_observability_boom")
    def boom():
        raise ValueError("persona@example.com leaked")

    try:
        response = TestClient(main.app, raise_server_exceptions=False).get("/__test_observability_boom", headers={"Authorization": "Bearer t"})
    finally:
        main.app.router.routes[:] = [r for r in main.app.router.routes if getattr(r, "path", "") != "/__test_observability_boom"]
    assert response.status_code == 500 and "persona" not in response.text
    (args, kwargs), = reported
    assert args == ("api", "server_error", "error") and kwargs["error_class"] == "ValueError" and kwargs["status"] == 500
    assert kwargs["request_id"] == response.headers["X-Request-ID"]


def test_deliberate_503_is_a_warning_not_an_alert(monkeypatch):
    from fastapi import HTTPException

    reported = []
    monkeypatch.setattr(main.ops, "report", lambda *a, **k: reported.append((a, k)))
    request = type("R", (), {"method": "GET", "scope": {}, "url": type("U", (), {"path": "/x"})(), "state": object()})()
    main._report_server_error(request, 503, HTTPException(503, "paused"))
    # One DB outage pages once (database.* is CRITICAL); each route stays ERROR.
    main._report_server_error(request, 500, type("OperationalError", (Exception,), {})())
    assert [a[2] for a, _k in reported] == ["warning", "error"]


def test_client_disconnect_is_not_a_server_error(monkeypatch):
    from starlette.requests import ClientDisconnect

    reported = []
    monkeypatch.setattr(main.ops, "report", lambda *a, **k: reported.append((a, k)))
    request = type("R", (), {"method": "POST", "scope": {}, "url": type("U", (), {"path": "/x"})(), "state": object()})()
    main._report_server_error(request, 500, ClientDisconnect())
    assert [(a[1], a[2]) for a, _k in reported] == [("client_disconnected", "info")]
    assert "status" not in reported[0][1], "must not count toward the 5xx spike"


def test_readiness_never_waits_for_a_running_probe(monkeypatch):
    monkeypatch.setattr(observability_routes, "_probe", {"at": None, "ok": False})
    monkeypatch.setattr(observability_routes, "_database_answers", lambda: pytest.fail("a second probe ran"))
    assert observability_routes._probe_lock.acquire(blocking=False)
    try:
        assert observability_routes.database_ready() is False  # last known result, immediately
    finally:
        observability_routes._probe_lock.release()


def test_probe_success_recovers_only_its_own_incident(monkeypatch):
    import psycopg2

    recovered = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, *_a):
            pass

        def fetchone(self):
            return (1,)

    connection = type("C", (), {"cursor": lambda _s: Cursor(), "close": lambda _s: None})()
    monkeypatch.setattr(psycopg2, "connect", lambda *a, **k: connection)
    monkeypatch.setattr(ops, "recovered", lambda component, event=None: recovered.append((component, event)))
    assert observability_routes._database_answers() is True
    assert recovered == [("database", "unreachable")]


def test_public_degraded_ignores_owner_integrations_and_jobs(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(observability_routes, "_probe", {"at": None, "ok": None})
    monkeypatch.setattr(observability_routes, "check_jobs", lambda: None)
    monkeypatch.setattr(observability_routes, "_database_answers", lambda: True)
    g = ops.AlertGate()
    g.record(ops.Signal("job", "ibkr_flex_failed", "error").clean(), alert_min="critical")
    g.record(ops.Signal("deploy", "render_failed", "error").clean(), alert_min="critical")
    monkeypatch.setattr(ops, "GATE", g)
    assert client.get("/health/ready").json()["status"] == "healthy"


def test_liveness_answers_on_the_event_loop():
    import inspect

    assert inspect.iscoroutinefunction(observability_routes.live)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422])
def test_expected_client_errors_never_report(monkeypatch, status):
    from fastapi import HTTPException

    reported = []
    monkeypatch.setattr(main.ops, "report", lambda *a, **k: reported.append(a))
    monkeypatch.setattr(main, "authenticate_access_token", lambda _t, **_k: {"id": 1, "role": "user", "account_id": "a", "workspace_id": "w"})

    @main.app.get("/__test_client_error")
    def client_error():
        raise HTTPException(status, "nope")

    try:
        TestClient(main.app).get("/__test_client_error", headers={"Authorization": "Bearer t"})
    finally:
        main.app.router.routes[:] = [r for r in main.app.router.routes if getattr(r, "path", "") != "/__test_client_error"]
    assert reported == []


def test_request_id_is_echoed_only_when_well_formed(client):
    assert client.get("/health/live", headers={"X-Request-ID": "support_ref_1234"}).headers["X-Request-ID"] == "support_ref_1234"
    for bad in ("bad id; <script>", "short", "x" * 81, "persona@example.com"):
        hostile = client.get("/health/live", headers={"X-Request-ID": bad}).headers["X-Request-ID"]
        assert re.fullmatch(r"[0-9a-f]{32}", hostile), bad


# --- Stale background jobs ------------------------------------------------------------

class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows


class _Conn:
    def __init__(self, active, recent, stuck):
        self.values = {"active": active, "recent": recent, "stuck": stuck}
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params=()):
        self.queries.append(query)
        if "finva_gmail_connections" in query:
            return _Rows({"active": self.values["active"], "recent": self.values["recent"]})
        if "notification_jobs" in query:
            return _Rows({"stuck": self.values["stuck"]})
        return _Rows({})

    def commit(self):
        pass


@pytest.mark.parametrize(("active", "recent", "stuck", "expected"), [
    (5, 0, 0, [("report", "mail_sync_stale"), ("recovered", "notifications_stuck")]),
    (5, 2, 0, [("recovered", "mail_sync_stale"), ("recovered", "notifications_stuck")]),
    (0, 0, 3, [("recovered", "mail_sync_stale"), ("report", "notifications_stuck")]),
])
def test_stale_jobs_are_detected_from_existing_state(monkeypatch, active, recent, stuck, expected):
    conn = _Conn(active, recent, stuck)
    calls = []
    monkeypatch.setattr(observability_routes.database, "get_connection", lambda: conn)
    monkeypatch.setattr(observability_routes, "tables_exist", lambda _c, _t: True)
    monkeypatch.setattr(ops, "report", lambda component, event, *a, **k: calls.append(("report", event)))
    monkeypatch.setattr(ops, "recovered", lambda component, event=None: calls.append(("recovered", event)))
    observability_routes._stale_jobs()
    assert calls == expected
    assert all("account" not in q and "email" not in q for q in conn.queries), "aggregates only"


def test_job_checks_run_at_most_every_ten_minutes(monkeypatch):
    runs = []
    monkeypatch.setattr(observability_routes, "_stale_jobs", lambda: runs.append(1))
    monkeypatch.setattr(observability_routes, "_jobs_checked", {"at": None})
    for _ in range(5):
        observability_routes.check_jobs()
    assert runs == [1]
    assert observability_routes.JOB_CHECK_SECONDS < ops.GATE.quiet


# --- Integration points --------------------------------------------------------------

def test_user_caused_mail_failures_never_escalate_provider_failures(monkeypatch):
    from fastapi import HTTPException

    from backend.user_product import mail_sync_analytics

    reports = []
    monkeypatch.setattr(mail_sync_analytics, "capture_backend_event_later", lambda *a, **k: None)
    monkeypatch.setattr(ops, "report", lambda component, event, severity, **k: reports.append((event, severity, k.get("escalate_after"))))

    def fail(exc):
        def run():
            raise exc
        with pytest.raises(type(exc)):
            mail_sync_analytics.observe_mail_sync("gmail", "maintenance", run)

    fail(HTTPException(409, "reconnect"))
    fail(HTTPException(403, "denied"))
    fail(RuntimeError("provider down"))
    assert reports == [("gmail_sync_needs_user", "info", None), ("gmail_sync_needs_user", "info", None),
                       ("gmail_sync_failed", "warning", 5)]


class _MaintenanceConn:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, *_a, **_k):
        return type("Q", (), {"fetchall": lambda _s: self.rows})()

    def commit(self):
        pass


@pytest.mark.parametrize(("outcomes", "ok"), [
    (["reauth", "reauth", "reauth"], True),   # only reconnects needed: the job ran fine
    (["boom", "boom", "reauth"], False),      # everything that could sync failed
    (["boom", "ok", "reauth"], True),         # partial failure: reported per connection, run ok
    ([], True),
])
def test_gmail_maintenance_heartbeat_counts_real_failures_only(monkeypatch, outcomes, ok):
    from fastapi import HTTPException

    from backend.user_product import gmail_service

    rows = [{"id": index + 1, "granted_scopes": []} for index in range(len(outcomes))]
    monkeypatch.setenv("FINVA_GMAIL_CRON_SECRET", "cron-secret-value")
    monkeypatch.setattr(gmail_service, "get_connection", lambda: _MaintenanceConn(rows))
    monkeypatch.setattr(gmail_service.mail_oauth, "discard_stale_flows", lambda conn: None)
    monkeypatch.setattr(gmail_service, "end_unentitled_mail_connections", lambda conn: 0)
    monkeypatch.setattr(gmail_service, "apply_gmail_retention", lambda: {})
    monkeypatch.setattr(gmail_service, "_credentials", lambda token: object())
    monkeypatch.setattr(gmail_service, "_start_watch", lambda *a, **k: None)
    monkeypatch.setattr(gmail_service, "_sync_connection", lambda *a, **k: {})

    def token(connection_id):
        outcome = outcomes[connection_id - 1]
        if outcome == "reauth":
            raise HTTPException(409, "reconnect")
        if outcome == "boom":
            raise RuntimeError("provider")
        return {}, "t"

    monkeypatch.setattr(gmail_service, "_connection_with_token", token)
    beats = []
    monkeypatch.setattr(gmail_service.observability, "heartbeat", lambda job, ok, **k: beats.append((job, ok)))
    monkeypatch.setattr(gmail_service.observability, "report", lambda *a, **k: None)
    gmail_service.gmail_maintenance("cron-secret-value")
    assert beats == [("gmail_maintenance", ok)]
