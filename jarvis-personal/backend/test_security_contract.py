from fastapi import HTTPException
from pathlib import Path

from backend import main
from backend.auth import legal
from backend.notifications import routes as notification_routes
from backend.product_ops import service as product_ops_service


class RecordingConnection:
    def __init__(self):
        self.queries = []

    def execute(self, query, params=()):
        self.queries.append(" ".join(query.split()))


def _contains_sql(queries, expected):
    normalized = " ".join(expected.split()).lower()
    return any(normalized in query.lower() for query in queries)


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


def test_product_operations_runtime_schema_is_closed_to_data_api_roles():
    connection = RecordingConnection()
    product_ops_service.ensure_schema(connection)

    for table_name in (
        "finva_beta_programs",
        "billing_orders",
        "billing_subscriptions",
        "product_events",
        "feedback_reports",
    ):
        assert _contains_sql(
            connection.queries,
            f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY",
        )
        assert _contains_sql(
            connection.queries,
            f"REVOKE ALL PRIVILEGES ON TABLE {table_name} FROM anon, authenticated",
        )


def test_legal_runtime_schema_is_closed_to_data_api_roles():
    connection = RecordingConnection()
    legal.ensure_legal_schema(connection)

    assert _contains_sql(
        connection.queries,
        "ALTER TABLE legal_acceptances ENABLE ROW LEVEL SECURITY",
    )
    assert _contains_sql(
        connection.queries,
        "REVOKE ALL PRIVILEGES ON TABLE legal_acceptances FROM anon, authenticated",
    )


def test_rls_lockdown_migration_fails_if_public_tables_remain_unprotected():
    migration = (
        Path(__file__).parents[1]
        / "database"
        / "migrations"
        / "20260916_lock_down_public_tables_rls.sql"
    ).read_text(encoding="utf-8")

    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "REVOKE ALL PRIVILEGES" in migration
    assert "ALL SEQUENCES IN SCHEMA public" in migration
    assert "Public application tables still missing RLS" in migration
