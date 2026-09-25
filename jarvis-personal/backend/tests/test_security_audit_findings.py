"""Regression tests for the 2026-09 security audit findings (docs/security/security-audit-2026-09.md)."""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid

import pytest

from backend.auth import data_export, saas
from backend.core import feature_flags
from backend.user_product import gmail_service

CCSS_BODY = ("Caja Costarricense de Seguro Social Orden Patronal Digital\n"
             "julio 2026 1,000.00 1,000.00 9,999,999.00 0.00\nCodigo verificador: ABC123")
CONNECTION = {"id": 3, "account_id": "account-a", "workspace_id": "workspace-a", "legacy_user_id": 7, "display_name": ""}


class _Recorder:
    def __init__(self):
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        self.queries.append(" ".join(query.split()))

        class _Row:
            def fetchone(self):
                return None if query.lstrip().upper().startswith("SELECT ID,STATUS FROM FINVA_EMAIL_MESSAGES") else {"id": 1}

            def fetchall(self):
                return []
        return _Row()

    def commit(self):
        pass


@pytest.mark.parametrize(("sender", "stored"), [
    ("Atacante <attacker@example.com>", False),
    ("CCSS <noreply@ccss.sa.cr> <otro@example.com>", False),
    ("noreply@ccss.sa.cr.evil.example", False),
    ("CCSS <noreply@ccss.sa.cr>", True),
])
def test_a_ccss_payroll_order_is_only_read_from_the_ccss(monkeypatch, sender, stored):
    """Any sender could email a forged 'Orden Patronal' and overwrite the victim's salary history."""
    recorder = _Recorder()
    monkeypatch.setattr(gmail_service, "get_connection", lambda: recorder)
    monkeypatch.setattr(gmail_service, "link_received_payroll", lambda *a, **k: None, raising=False)
    gmail_service._ingest_message(CONNECTION, "m-1", subject="Generación de Orden Patronal Digital",
                                  sender=sender, body=CCSS_BODY)
    wrote = any(query.startswith("INSERT INTO payroll_salary_reports") for query in recorder.queries)
    assert wrote is stored


def test_the_aguinaldo_search_never_lists_mail_by_subject_alone():
    query = gmail_service._aguinaldo_gmail_query()
    assert "subject:" not in query and "from:ccss.sa.cr" in query


def test_owner_grant_details_never_reach_the_user(monkeypatch):
    subscription = {"plan": "vip", "status": "active", "access_source": "courtesy",
                    "granted_by": str(uuid.uuid4()), "courtesy_note": "Owner internal note", "expires_at": "2027-01-01"}

    class _Conn(_Recorder):
        def execute(self, query, params=()):
            class _Row:
                def fetchone(self):
                    return {}
            return _Row()

    monkeypatch.setattr(saas, "get_connection", lambda: _Conn())
    monkeypatch.setattr(saas, "ensure_default_subscription", lambda *a, **k: subscription)
    monkeypatch.setattr(saas, "_activate_self_service_if_ready", lambda *a, **k: subscription)
    monkeypatch.setattr("backend.auth.legal.legal_status", lambda *a, **k: {})
    profile = saas.enrich_identity({"account_id": "account-a", "role": "user"})
    assert "granted_by" not in profile["subscription"] and "courtesy_note" not in profile["subscription"]
    assert profile["subscription"]["plan"] == "vip"
    assert {"granted_by", "courtesy_note"} <= data_export.EXCLUDED_COLUMNS


@pytest.mark.parametrize(("method", "path", "flags"), [
    ("POST", "/user-product/vip/mail/oauth/complete", {"gmail_automation"}),
    ("POST", "/user-product/vip/mail/microsoft/connect", {"gmail_automation"}),
    ("GET", "/user-product/vip/mail/microsoft/callback", {"gmail_automation"}),
    ("PUT", "/user-product/basic/budget", {"financial_writes"}),
    ("POST", "/user-product/basic/recurring", {"financial_writes"}),
    ("PUT", "/user-product/vip/salvavidas", {"vip_intelligence", "financial_writes"}),
    ("PUT", "/user-product/vip/financial-identity/accounts/7", {"gmail_automation", "vip_intelligence", "financial_writes"}),
    ("POST", "/user-product/vip/lifecycle/snapshots", {"vip_intelligence", "financial_writes"}),
    ("POST", "/auth/onboarding", {"financial_writes"}),
    ("GET", "/user-product/basic/budget", set()),
    ("GET", "/user-product/vip/gmail/status", {"gmail_automation"}),
])
def test_kill_switches_cover_every_route_they_pause(method, path, flags):
    assert set(feature_flags._request_flags(method, path)) == flags


def test_any_disabled_switch_pauses_a_route_it_covers(monkeypatch):
    state = {"vip_intelligence": True, "financial_writes": False}
    monkeypatch.setattr(feature_flags, "load_feature_flags",
                        lambda: {key: {"enabled": value, "flag_key": key} for key, value in state.items()})
    paused = feature_flags.disabled_feature_for_request("PUT", "/user-product/vip/salvavidas", {"role": "user"})
    assert paused and paused["flag_key"] == "financial_writes"
    state.update(vip_intelligence=False, financial_writes=True)
    paused = feature_flags.disabled_feature_for_request("PUT", "/user-product/vip/salvavidas", {"role": "user"})
    assert paused and paused["flag_key"] == "vip_intelligence"


def test_a_discord_connection_error_never_logs_the_webhook_secret(monkeypatch, caplog):
    import requests
    from types import SimpleNamespace

    from backend.product_ops import service

    secret = "SYNTHETICWEBHOOKTOKEN"
    monkeypatch.setenv("SUPPORT_DISCORD_WEBHOOK_URL", f"https://discord.com/api/webhooks/1/{secret}")

    def fail(url, **_kwargs):
        raise requests.ConnectionError(f"Max retries exceeded with url: /api/webhooks/1/{secret}")

    monkeypatch.setattr(service.requests, "post", fail)
    payload = SimpleNamespace(category="bug", subject="s", message="m", severity="critical", screen=None,
                              app_version=None, platform=None, diagnostic_label=None)
    with caplog.at_level(logging.DEBUG):
        try:
            service._send_support_discord(public_id="DINCR-000001", plan="free", payload=payload, severity="critical")
        except Exception:
            pass
    assert secret not in caplog.text


# --- PostgreSQL ------------------------------------------------------------------

pgserver = pytest.importorskip("pgserver")
psycopg2 = pytest.importorskip("psycopg2")


@pytest.fixture
def pg(tmp_path, monkeypatch):
    from backend.core import database

    server = pgserver.get_server(str(os.environ.get("DINCR_PGSERVER_DIR") or tmp_path / "pg"), cleanup_mode="stop")
    admin = psycopg2.connect(server.get_uri())
    admin.autocommit = True
    name = f"secaudit_{os.getpid()}_{abs(hash(str(tmp_path))) % 10**8}"
    with admin.cursor() as c:
        c.execute(f"CREATE DATABASE {name}")
    uri = server.get_uri(name)
    conn = psycopg2.connect(uri)
    conn.autocommit = True
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    yield conn.cursor()
    conn.close()
    with admin.cursor() as c:
        c.execute(f"DROP DATABASE {name} WITH (FORCE)")
    admin.close()


def test_two_concurrent_debt_payments_both_reduce_the_balance(pg, monkeypatch):
    from backend.core import database
    from backend.user_product import service

    pg.execute("""CREATE TABLE debts (id BIGSERIAL PRIMARY KEY, workspace_id UUID, name TEXT, remaining_amount NUMERIC,
                  monthly_payment NUMERIC, updated_at TIMESTAMPTZ);
                  CREATE TABLE transactions (id BIGSERIAL PRIMARY KEY, user_id BIGINT, workspace_id UUID, transaction_date DATE,
                  description TEXT, amount NUMERIC, transaction_type TEXT, category TEXT, account TEXT, source TEXT,
                  notes TEXT, created_at TIMESTAMPTZ)""")
    workspace = str(uuid.uuid4())
    pg.execute("INSERT INTO debts(workspace_id, name, remaining_amount, monthly_payment) VALUES (%s, 'Tarjeta', 1000, 100) RETURNING id",
               (workspace,))
    debt_id = pg.fetchone()[0]
    monkeypatch.setattr(service, "_legacy_financial_user_id", lambda: 7)
    monkeypatch.setattr(service, "get_current_workspace_id", lambda: workspace)
    monkeypatch.setattr(service, "mark_applied", lambda conn: None)
    real_execute = database.PostgresConnection.execute

    def slow_after_reading_the_balance(self, query, params=()):
        result = real_execute(self, query, params)
        if "FROM debts WHERE id=%s" in query:
            time.sleep(0.3)  # the other payment reads the balance meanwhile, unless the row is locked
        return result

    monkeypatch.setattr(database.PostgresConnection, "execute", slow_after_reading_the_balance)
    threads = [threading.Thread(target=service.pay_user_debt, args=(debt_id, 100)) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    pg.execute("SELECT remaining_amount FROM debts WHERE id=%s", (debt_id,))
    assert float(pg.fetchone()[0]) == 800  # both payments applied, none lost
    pg.execute("SELECT count(*) FROM transactions")
    assert pg.fetchone()[0] == 2


def test_the_ibkr_owner_is_resolved_in_one_identity_space(pg, monkeypatch):
    """The Owner's users.id equals another person's allowed_users.id: the snapshot must still go to the Owner."""
    from backend.core.database import get_connection
    from backend.integrations import ibkr_readonly

    pg.execute("""CREATE TABLE users (id BIGINT PRIMARY KEY, email TEXT);
                  CREATE TABLE allowed_users (id BIGINT PRIMARY KEY, email TEXT, role TEXT);
                  CREATE TABLE accounts (id UUID PRIMARY KEY, legacy_allowed_user_id BIGINT, role TEXT);
                  CREATE TABLE workspaces (id UUID PRIMARY KEY, owner_account_id UUID, workspace_type TEXT, created_at TIMESTAMPTZ DEFAULT NOW())""")
    owner_account, other_account = str(uuid.uuid4()), str(uuid.uuid4())
    owner_ws, other_ws = str(uuid.uuid4()), str(uuid.uuid4())
    pg.execute("INSERT INTO users VALUES (7, 'owner@example.test'), (1, 'someone@example.test')")
    pg.execute("INSERT INTO allowed_users VALUES (1, 'owner@example.test', 'owner'), (7, 'someone@example.test', 'user')")
    pg.execute("INSERT INTO accounts VALUES (%s, 1, 'owner'), (%s, 7, 'user')", (owner_account, other_account))
    pg.execute("INSERT INTO workspaces(id, owner_account_id, workspace_type) VALUES (%s, %s, 'personal'), (%s, %s, 'personal')",
               (owner_ws, owner_account, other_ws, other_account))
    monkeypatch.setenv("OWNER_EMAIL", "owner@example.test")
    with get_connection() as conn:
        user_id, workspace_id = ibkr_readonly._owner_identity(conn)
    assert workspace_id == owner_ws and user_id == 7
