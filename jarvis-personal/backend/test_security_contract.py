from fastapi import HTTPException
from pathlib import Path
from types import SimpleNamespace

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
