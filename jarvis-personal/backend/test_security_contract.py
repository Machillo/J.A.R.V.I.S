from fastapi import HTTPException
from pathlib import Path
from types import SimpleNamespace
import pytest

from backend import main
from backend.auth import legal
from backend.auth import service as auth_service
from backend.auth.current_user import reset_current_user, set_current_user
from backend.auth.models import ProfileSetupRequest
from backend.notifications import routes as notification_routes
from backend.product_ops import service as product_ops_service
from backend.user_product import gmail_service
from backend.user_product.models import OvertimeCreateRequest


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
        "request_id": "public-reference",
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


def test_internal_function_hardening_is_explicit_and_future_safe():
    migration = (
        Path(__file__).parents[1]
        / "database"
        / "migrations"
        / "20260916_internal_function_hardening.sql"
    ).read_text(encoding="utf-8")

    assert migration.count("SET search_path = pg_catalog, public") == 2
    assert "REVOKE ALL ON FUNCTION public.jarvis_workspace_backfill_audit() FROM PUBLIC, anon, authenticated" in migration
    assert "REVOKE ALL ON FUNCTION public.jarvis_link_financial_account() FROM PUBLIC, anon, authenticated" in migration
    assert "ALTER DEFAULT PRIVILEGES IN SCHEMA public" in migration


def test_finva_gmail_scope_is_read_only_and_identity_adapter_is_user_specific():
    assert gmail_service.GMAIL_SCOPE == "https://www.googleapis.com/auth/gmail.readonly"
    text = gmail_service._adapt_identity(
        "Compra para María Fernanda por ₡12.500",
        "María Fernanda Solano",
    )
    assert "María" not in text
    assert "Kenneth" in text


def test_finva_gmail_oauth_state_is_signed_and_does_not_require_database(monkeypatch):
    monkeypatch.setenv("FINVA_GMAIL_CLIENT_ID", "client")
    monkeypatch.setenv("FINVA_GMAIL_CLIENT_SECRET", "secret")
    monkeypatch.setenv("FINVA_GMAIL_REDIRECT_URI", "https://example.test/callback")
    state = gmail_service._encode_oauth_state("account-1", "workspace-1")
    assert gmail_service._decode_oauth_state(state)["account_id"] == "account-1"
    assert gmail_service._decode_oauth_state(f"{state}tampered") is None

    source = Path(gmail_service.__file__).read_text(encoding="utf-8")
    connect_source = source.split("def begin_gmail_connection", 1)[1].split("def finish_gmail_connection", 1)[0]
    assert "finva_gmail_oauth_states" not in connect_source


def test_overtime_accepts_decimal_hours_and_common_multipliers():
    overtime = OvertimeCreateRequest(hours=2.5, hourly_rate=2500, multiplier=1.5)
    assert overtime.hours * overtime.hourly_rate * overtime.multiplier == 9375


def test_profile_setup_normalizes_name_and_preserves_base_currency():
    request = ProfileSetupRequest(
        display_name="  Ana   María  ",
        usage_goal="save",
        base_currency="USD",
        enabled_currencies=["ARS", "USD", "ARS"],
    )

    assert request.display_name == "Ana María"
    assert request.enabled_currencies == ["USD", "ARS"]


def test_profile_setup_migration_does_not_modify_financial_records():
    migration = (
        Path(__file__).parents[1]
        / "database"
        / "migrations"
        / "20260917174227_finva_profile_onboarding.sql"
    ).read_text(encoding="utf-8")

    assert "ALTER TABLE public.accounts" in migration
    assert "profile_setup_completed" in migration
    assert "ALTER TABLE public.financial_profiles" not in migration
    assert "UPDATE public.financial_profiles" not in migration


def test_self_deletion_fails_closed_without_server_admin_key(monkeypatch):
    monkeypatch.setattr(auth_service, "SUPABASE_ADMIN_KEY", None)
    token = set_current_user({
        "id": 42,
        "account_id": "11111111-1111-1111-1111-111111111111",
        "supabase_user_id": "22222222-2222-2222-2222-222222222222",
        "email": "person@example.com",
    })
    try:
        auth_service.delete_current_account()
        assert False, "Account deletion must reject requests when no server-only key is configured."
    except HTTPException as exc:
        assert exc.status_code == 503
    finally:
        reset_current_user(token)


def test_supabase_admin_headers_support_current_secret_keys():
    headers = auth_service._supabase_admin_headers("sb_secret_example")
    assert headers == {"apikey": "sb_secret_example"}


def test_supabase_admin_headers_keep_legacy_service_role_authorization():
    headers = auth_service._supabase_admin_headers("legacy.service.role")
    assert headers["apikey"] == "legacy.service.role"
    assert headers["Authorization"] == "Bearer legacy.service.role"


@pytest.mark.parametrize("plan", ["free", "basic", "vip"])
def test_self_deletion_uses_same_account_owned_flow_for_every_plan(monkeypatch, plan):
    queries = []

    class Result:
        def __init__(self, row=None, rows=None): self.row = row; self.rows = rows or []
        def fetchone(self): return self.row
        def fetchall(self): return self.rows

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def commit(self): queries.append("COMMIT")
        def execute(self, query, params=()):
            normalized = " ".join(query.split())
            queries.append((normalized, params))
            if normalized.startswith("SELECT legacy_allowed_user_id"):
                return Result({
                    "legacy_allowed_user_id": 42,
                    "supabase_user_id": "22222222-2222-2222-2222-222222222222",
                    "primary_email": "person@example.com",
                })
            if normalized.startswith("DELETE FROM accounts"):
                return Result({"id": "11111111-1111-1111-1111-111111111111"})
            return Result()

    monkeypatch.setattr(auth_service, "get_connection", lambda: Connection())
    monkeypatch.setattr(auth_service, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(auth_service, "SUPABASE_ADMIN_KEY", "sb_secret_example")
    monkeypatch.setattr(auth_service.requests, "delete", lambda *_args, **_kwargs: SimpleNamespace(status_code=204))
    token = set_current_user({
        "id": 42, "account_id": "11111111-1111-1111-1111-111111111111",
        "supabase_user_id": "22222222-2222-2222-2222-222222222222",
        "email": "person@example.com", "plan": plan,
    })
    try:
        assert auth_service.delete_current_account()["status"] == "OK"
    finally:
        reset_current_user(token)

    sql = [entry[0] for entry in queries if isinstance(entry, tuple)]
    assert any("pg_constraint" in query for query in sql)
    assert any(query.startswith("DELETE FROM accounts") for query in sql)
    legacy_delete = next(query for query in sql if query.startswith("DELETE FROM users"))
    assert "lower(email)" in legacy_delete
    assert "allowed_user_id" not in legacy_delete
    assert any(query.startswith("DELETE FROM allowed_users") for query in sql)


def test_account_deletion_stage_contract_is_complete():
    assert auth_service.DELETION_STAGES == (
        "IDENTITY", "FK_CHECK", "ACCOUNT_DELETE", "LEGACY_DELETE",
        "SUPABASE_AUTH_DELETE", "COMMIT", "DONE",
    )


def test_database_baseline_v1_matches_production_legacy_identity():
    baseline = (
        Path(__file__).parents[1] / "database" / "baseline" / "v1_identity_ownership.sql"
    ).read_text(encoding="utf-8")
    assert "users_email_ci" in baseline
    assert "allowed_user_id" not in baseline.split("CREATE TABLE IF NOT EXISTS public.users", 1)[1].split(";", 1)[0]
    assert "ON DELETE CASCADE" in baseline
    assert "ON DELETE SET NULL" in baseline
    assert "ENABLE ROW LEVEL SECURITY" in baseline


def test_support_email_configuration_reports_missing_secret_without_exposing_it(monkeypatch):
    monkeypatch.setenv("SUPPORT_SMTP_USER", "soporte.finva@gmail.com")
    monkeypatch.delenv("SUPPORT_SMTP_APP_PASSWORD", raising=False)
    status = product_ops_service.support_email_configuration()
    assert status["configured"] is False
    assert status["missing"] == ["SUPPORT_SMTP_APP_PASSWORD"]
    assert "password" not in status


def test_support_email_normalizes_google_app_password(monkeypatch):
    observed = {}

    class FakeSmtp:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def login(self, username, password): observed.update(username=username, password=password)
        def send_message(self, message): observed["recipient"] = message["To"]

    monkeypatch.setenv("SUPPORT_SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SUPPORT_SMTP_PORT", "465")
    monkeypatch.setenv("SUPPORT_SMTP_USER", "soporte.finva@gmail.com")
    monkeypatch.setenv("SUPPORT_EMAIL_TO", "soporte.finva@gmail.com")
    monkeypatch.setenv("SUPPORT_SMTP_APP_PASSWORD", "abcd efgh ijkl mnop")
    monkeypatch.setattr(product_ops_service.smtplib, "SMTP_SSL", lambda *_args, **_kwargs: FakeSmtp())

    sent = product_ops_service._send_support_email(
        public_id="FINVA-000001",
        email="person@example.com",
        plan="vip",
        payload=SimpleNamespace(
            category="error", subject="Prueba", message="Mensaje",
            app_version="1.9.5", screen="soporte", error_reference=None,
        ),
    )

    assert sent is True
    assert observed["password"] == "abcdefghijklmnop"
    assert observed["recipient"] == "soporte.finva@gmail.com"


def test_discord_incident_notification_is_privacy_minimized(monkeypatch):
    observed = {}

    def fake_post(url, json, timeout):
        observed.update(url=url, payload=json, timeout=timeout)
        return SimpleNamespace(status_code=204)

    monkeypatch.setenv(
        "SUPPORT_DISCORD_WEBHOOK_URL",
        "https://discord.com/api/webhooks/123/example-token",
    )
    monkeypatch.setattr(product_ops_service.requests, "post", fake_post)
    sent = product_ops_service._send_support_discord(
        public_id="FINVA-000008",
        plan="vip",
        severity="critical",
        payload=SimpleNamespace(
            category="error",
            app_version="2.0.0",
            platform="android",
            screen="settings",
            error_reference="request-safe-reference",
            message="tarjeta 4111111111111111",
            email="private@example.com",
        ),
    )

    assert sent is True
    content = observed["payload"]["content"]
    assert "FINVA-000008" in content
    assert "request-safe-reference" in content
    assert "4111111111111111" not in content
    assert "private@example.com" not in content
    assert "example-token" not in content
    assert observed["payload"]["allowed_mentions"] == {"parse": []}


def test_discord_rejects_non_discord_webhook(monkeypatch):
    called = False

    def fake_post(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setenv("SUPPORT_DISCORD_WEBHOOK_URL", "https://evil.example/webhook")
    monkeypatch.setattr(product_ops_service.requests, "post", fake_post)
    assert product_ops_service._send_support_discord(
        public_id="FINVA-000009",
        plan="free",
        payload=SimpleNamespace(category="error", app_version=None, platform=None, screen=None, error_reference=None),
    ) is False
    assert called is False


def test_phase_0c_suppresses_warning_discord_alerts_by_default(monkeypatch):
    called = False

    def fake_post(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setenv("SUPPORT_DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/123/token")
    monkeypatch.delenv("SUPPORT_DISCORD_MIN_SEVERITY", raising=False)
    monkeypatch.setattr(product_ops_service.requests, "post", fake_post)

    sent = product_ops_service._send_support_discord(
        public_id="FINVA-000010",
        plan="free",
        severity="warning",
        payload=SimpleNamespace(
            category="error", app_version="1.9.7", platform="android",
            screen="finance", error_reference="safe-reference",
        ),
    )

    assert sent is False
    assert called is False


def test_phase_0c_critical_alert_can_ping_only_configured_role(monkeypatch):
    observed = {}

    def fake_post(_url, json, timeout):
        observed.update(payload=json, timeout=timeout)
        return SimpleNamespace(status_code=204)

    monkeypatch.setenv("SUPPORT_DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/123/token")
    monkeypatch.setenv("SUPPORT_DISCORD_ALERT_ROLE_ID", "123456789012345678")
    monkeypatch.setattr(product_ops_service.requests, "post", fake_post)

    sent = product_ops_service._send_support_discord(
        public_id="FINVA-000011",
        plan="vip",
        severity="critical",
        payload=SimpleNamespace(
            category="error", app_version="1.9.7", platform="android",
            screen="settings", error_reference="safe-reference",
        ),
    )

    assert sent is True
    assert observed["payload"]["content"].startswith("<@&123456789012345678>")
    assert observed["payload"]["allowed_mentions"] == {
        "parse": [], "roles": ["123456789012345678"],
    }


def test_phase_0c_migration_tracks_discord_delivery_without_public_access():
    migration = (
        Path(__file__).parents[1]
        / "database"
        / "migrations"
        / "20260920090000_phase_0c_severity_alerts.sql"
    ).read_text(encoding="utf-8")
    routes = (Path(__file__).parent / "product_ops" / "routes.py").read_text(encoding="utf-8")

    assert "discord_alerted_at TIMESTAMPTZ" in migration
    assert "idx_feedback_unalerted_critical" in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "REVOKE ALL PRIVILEGES" in migration
    assert '/owner/support/discord/test' in routes


def test_phase_0a_incident_contract_is_deduplicated_and_backend_only():
    migration = (
        Path(__file__).parents[1]
        / "database"
        / "migrations"
        / "20260920050000_phase_0a_incident_reporting.sql"
    ).read_text(encoding="utf-8")
    service = Path(product_ops_service.__file__).read_text(encoding="utf-8")

    assert "idx_feedback_incident_dedupe" in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "REVOKE ALL PRIVILEGES" in migration
    assert "source IN ('user', 'automatic')" in migration
    assert "NOW()-INTERVAL '15 minutes'" in service
    assert "occurrence_count=occurrence_count+1" in service
    assert "pg_advisory_xact_lock" in service
    assert "feedback_reports_user_resolution_check" in migration


def test_user_feedback_resolution_is_scoped_to_own_account(monkeypatch):
    queries = []

    class Result:
        def __init__(self, row=None): self.row = row
        def fetchone(self): return self.row

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def commit(self): queries.append(("COMMIT", ()))
        def execute(self, query, params=()):
            normalized = " ".join(query.split())
            queries.append((normalized, params))
            if normalized.startswith("SELECT f.id"):
                return Result({
                    "id": 5, "category": "error", "subject": "No carga",
                    "message": "detalle", "plan_code": "vip", "app_version": "1.9.6",
                    "screen": "settings", "error_reference": None,
                    "email": "person@example.com",
                })
            if normalized.startswith("UPDATE feedback_reports"):
                return Result({
                    "id": 5, "category": "error", "subject": "No carga",
                    "status": "reviewing", "user_resolution": "still_happening",
                    "user_resolution_at": "now", "updated_at": "now",
                })
            return Result()

    monkeypatch.setattr(product_ops_service, "get_connection", lambda: Connection())
    monkeypatch.setattr(product_ops_service, "ensure_schema", lambda _conn: None)
    monkeypatch.setattr(product_ops_service, "get_current_user", lambda: {"account_id": "account-1"})
    monkeypatch.setattr(product_ops_service, "_send_support_email", lambda **_kwargs: True)
    monkeypatch.setattr(product_ops_service, "_send_support_discord", lambda **_kwargs: False)

    result = product_ops_service.update_user_feedback_resolution(5, "still_happening")

    assert result["status"] == "reviewing"
    select_params = next(params for query, params in queries if query.startswith("SELECT f.id"))
    update_params = next(params for query, params in queries if query.startswith("UPDATE feedback_reports"))
    assert select_params == (5, "account-1")
    assert update_params[-2:] == (5, "account-1")


def test_automatic_incident_fingerprint_excludes_user_content():
    common = dict(
        method="GET", path="/finance/overview", status=503,
        error_type="http_503", app_version="2.0.0",
    )
    first = SimpleNamespace(**common, message="salary 1000000", email="a@example.com")
    second = SimpleNamespace(**common, message="debt 999999", email="b@example.com")

    assert product_ops_service._incident_fingerprint(first) == product_ops_service._incident_fingerprint(second)
    assert product_ops_service._incident_severity("/auth/me", "DELETE", 409) == "critical"
    assert product_ops_service._incident_severity("/user-product/finance/income", "POST", 0) == "critical"
    assert product_ops_service._incident_severity("/reports", "GET", 429) == "warning"
    assert product_ops_service._sanitize_incident_path(
        "/transactions/123?account=456&amount=999"
    ) == "/transactions/:id"
    assert product_ops_service._sanitize_incident_path(
        "/goals/11111111-1111-1111-1111-111111111111"
    ) == "/goals/:id"


def test_phase_0b_groups_a_screen_failure_burst_into_one_incident():
    first = SimpleNamespace(
        method="POST", path="/user-product/finance/debts", status=0,
        error_type="network_error", app_version="1.9.6", platform="android", screen="debts",
    )
    second = SimpleNamespace(
        method="GET", path="/user-product/finance/debts", status=0,
        error_type="network_error", app_version="1.9.6", platform="android", screen="debts",
    )
    third = SimpleNamespace(
        method="POST", path="/product-ops/events", status=0,
        error_type="network_error", app_version="1.9.6", platform="android", screen="debts",
    )

    assert product_ops_service._incident_fingerprint(first) == product_ops_service._incident_fingerprint(second)
    assert product_ops_service._incident_fingerprint(first) == product_ops_service._incident_fingerprint(third)


@pytest.mark.parametrize(
    ("affected", "critical", "expected"),
    [(0, 0, "operational"), (2, 1, "degraded"), (3, 3, "major_outage")],
)
def test_phase_0b_health_status_uses_distinct_accounts(monkeypatch, affected, critical, expected):
    class Result:
        def fetchone(self):
            return {
                "active_incidents": affected,
                "occurrences": affected * 3,
                "affected_accounts": affected,
                "critical_accounts": critical,
                "last_incident_at": None,
            }

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, _query, _params=()): return Result()
        def commit(self): pass

    monkeypatch.setattr(product_ops_service, "get_connection", lambda: Connection())
    monkeypatch.setattr(product_ops_service, "ensure_schema", lambda _conn: None)

    health = product_ops_service.platform_health()
    assert health["status"] == expected
    assert health["affected_accounts"] == affected
    assert "email" not in health
    assert "account_id" not in health


def test_phase_0b_migration_preserves_private_health_contract():
    migration = (
        Path(__file__).parents[1]
        / "database"
        / "migrations"
        / "20260920070000_phase_0b_health_center.sql"
    ).read_text(encoding="utf-8")
    assert "affected_operations TEXT[]" in migration
    assert "idx_feedback_health_window" in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "REVOKE ALL PRIVILEGES" in migration


def test_self_deletion_migration_cascades_owned_data():
    migration = (
        Path(__file__).parents[1]
        / "database"
        / "migrations"
        / "20260919_account_self_deletion.sql"
    ).read_text(encoding="utf-8")

    assert "REFERENCES public.accounts(id) ON DELETE CASCADE" in migration
    assert "REFERENCES public.workspaces(id) ON DELETE CASCADE" in migration
    assert "c.confdeltype <> 'c'" in migration


def test_self_deletion_followup_cascades_gmail_and_validates_constraints():
    migration = (
        Path(__file__).parents[1]
        / "database"
        / "migrations"
        / "20260919183000_fix_account_deletion_cascades.sql"
    ).read_text(encoding="utf-8")

    assert "finva_gmail_connections_legacy_user_id_fkey" in migration
    assert "REFERENCES public.users(id) ON DELETE CASCADE" in migration
    assert "VALIDATE CONSTRAINT" in migration
