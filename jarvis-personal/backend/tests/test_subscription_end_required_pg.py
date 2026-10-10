"""A paid plan is live only until a known end, on every server path (real PostgreSQL).

- An App Store / Google Play subscription without a known end is not live: an unknown end is
  never "forever" (it used to be read as `'infinity'`).
- Background mail (OAuth callbacks, Pub/Sub delivery, the maintenance job) uses the same rule as
  the interactive routes (`require_feature`, 402) and the daily history job: a paid self-service
  VIP needs a live store subscription. Courtesy grants keep their own end, and the Owner's
  `owner` access is unchanged.

Skipped when the embedded server (pgserver) is not installed. Synthetic accounts only.
"""
from __future__ import annotations

import base64
import json
import os
import uuid

import pytest
from fastapi import HTTPException

pgserver = pytest.importorskip("pgserver")
psycopg2 = pytest.importorskip("psycopg2")

from backend.auth import plan_lifecycle, saas  # noqa: E402
from backend.core import database  # noqa: E402
from backend.product_ops import service as billing  # noqa: E402
from backend.user_product import gmail_service  # noqa: E402

SCHEMA = """
CREATE TABLE accounts (id UUID PRIMARY KEY, role TEXT NOT NULL DEFAULT 'user', status TEXT NOT NULL DEFAULT 'active',
    onboarding_completed BOOLEAN, onboarding_level TEXT, plan_selected BOOLEAN, updated_at TIMESTAMPTZ);
CREATE TABLE plans (id BIGSERIAL PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT, is_active BOOLEAN NOT NULL DEFAULT TRUE);
INSERT INTO plans(code, name) VALUES ('free', 'Gratis'), ('basic', 'Basic'), ('vip', 'VIP');
CREATE TABLE features (id BIGSERIAL PRIMARY KEY, code TEXT UNIQUE);
CREATE TABLE plan_features (plan_id BIGINT, feature_id BIGINT, enabled BOOLEAN);
CREATE TABLE account_subscriptions (
    id BIGSERIAL PRIMARY KEY,
    account_id UUID NOT NULL UNIQUE REFERENCES accounts(id) ON DELETE CASCADE,
    plan_id BIGINT NOT NULL REFERENCES plans(id),
    status TEXT NOT NULL DEFAULT 'active',
    access_source TEXT NOT NULL DEFAULT 'self_service' CHECK (access_source IN ('self_service','courtesy','owner')),
    started_at TIMESTAMPTZ, expires_at TIMESTAMPTZ, last_payment_at TIMESTAMPTZ, courtesy_note TEXT,
    granted_by UUID, granted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE store_subscriptions (account_id UUID PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
    provider TEXT NOT NULL, plan_code TEXT NOT NULL, status TEXT NOT NULL,
    trial_ends_at TIMESTAMPTZ, current_period_end TIMESTAMPTZ);
CREATE TABLE finva_gmail_connections (id BIGSERIAL PRIMARY KEY, account_id UUID NOT NULL REFERENCES accounts(id),
    google_email TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active', granted_scopes TEXT[] NOT NULL DEFAULT '{}');
"""


@pytest.fixture
def db(tmp_path, monkeypatch):
    server = pgserver.get_server(str(os.environ.get("DINCR_PGSERVER_DIR") or tmp_path / "pg"), cleanup_mode="stop")
    admin = psycopg2.connect(server.get_uri())
    admin.autocommit = True
    name = f"subend_{os.getpid()}_{abs(hash(str(tmp_path))) % 10**8}"
    with admin.cursor() as c:
        c.execute(f"CREATE DATABASE {name}")
    uri = server.get_uri(name)
    conn = psycopg2.connect(uri)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(SCHEMA)
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    monkeypatch.setattr(plan_lifecycle, "_supported_until", 0.0)
    yield cur
    conn.close()
    with admin.cursor() as c:
        c.execute(f"DROP DATABASE {name} WITH (FORCE)")
    admin.close()


def _account(cur, plan: str, source: str = "self_service", courtesy_end: str | None = None) -> str:
    account = str(uuid.uuid4())
    cur.execute("INSERT INTO accounts(id) VALUES (%s)", (account,))
    cur.execute(
        """INSERT INTO account_subscriptions(account_id, plan_id, access_source, expires_at)
           VALUES (%s, (SELECT id FROM plans WHERE code=%s), %s, %s::timestamptz)""",
        (account, plan, source, courtesy_end),
    )
    return account


def _store(cur, account: str, plan: str, status: str = "active", period_end: str | None = None, trial_end: str | None = None):
    cur.execute(
        """INSERT INTO store_subscriptions(account_id, provider, plan_code, status, trial_ends_at, current_period_end)
           VALUES (%s, 'google', %s, %s, %s::timestamptz, %s::timestamptz)""",
        (account, plan, status, trial_end, period_end),
    )


def _entitled(account: str, plan: str = "vip") -> bool:
    with database.get_connection() as conn:
        return billing.has_store_entitlement(conn, account, plan)


def _background(account: str) -> bool:
    with database.get_connection() as conn:
        return gmail_service._has_active_vip_access(conn, account)


FUTURE = "now() + interval '20 days'"
PAST = "now() - interval '1 day'"


def _at(cur, expression: str) -> str:
    cur.execute(f"SELECT ({expression})::text")
    return cur.fetchone()[0]


def test_a_store_subscription_without_a_known_end_is_not_live(db):
    live = _account(db, "vip")
    _store(db, live, "vip", period_end=_at(db, FUTURE))
    unknown_end = _account(db, "vip")
    _store(db, unknown_end, "vip", period_end=None)
    ended = _account(db, "vip")
    _store(db, ended, "vip", period_end=_at(db, PAST))
    trial = _account(db, "vip")
    _store(db, trial, "vip", status="trialing", trial_end=_at(db, FUTURE))
    trial_unknown_end = _account(db, "vip")
    _store(db, trial_unknown_end, "vip", status="trialing")

    assert _entitled(live) is True
    assert _entitled(unknown_end) is False, "an unknown end is never forever"
    assert _entitled(ended) is False
    assert _entitled(trial) is True
    assert _entitled(trial_unknown_end) is False
    with database.get_connection() as conn:
        assert plan_lifecycle.store_plan(conn, unknown_end) is None
        assert plan_lifecycle.store_plan(conn, live) == "vip"


def test_the_interactive_gate_refuses_a_paid_plan_without_a_known_end(db, monkeypatch):
    account = _account(db, "vip")
    _store(db, account, "vip", period_end=None)
    monkeypatch.setattr(saas, "get_current_user", lambda: {"role": "user", "account_id": account})
    monkeypatch.setattr(saas, "get_current_account_id", lambda: account)
    with pytest.raises(HTTPException) as refused:
        saas.require_feature("gmail_automation")
    assert refused.value.status_code == 402


def test_background_mail_uses_the_same_entitlement_as_the_interactive_routes(db):
    store_vip = _account(db, "vip")
    _store(db, store_vip, "vip", period_end=_at(db, FUTURE))
    lapsed_vip = _account(db, "vip")  # self-service VIP whose store subscription ended
    _store(db, lapsed_vip, "vip", period_end=_at(db, PAST))
    no_store_vip = _account(db, "vip")  # self-service VIP with no store subscription at all
    unknown_end_vip = _account(db, "vip")
    _store(db, unknown_end_vip, "vip", period_end=None)
    courtesy = _account(db, "vip", source="courtesy", courtesy_end=_at(db, FUTURE))
    courtesy_ended = _account(db, "vip", source="courtesy", courtesy_end=_at(db, PAST))
    owner = _account(db, "vip", source="owner")
    basic = _account(db, "basic")
    _store(db, basic, "basic", period_end=_at(db, FUTURE))

    assert _background(store_vip) is True
    assert _background(lapsed_vip) is False, "as require_feature (402): no live store subscription"
    assert _background(no_store_vip) is False
    assert _background(unknown_end_vip) is False
    assert _background(courtesy) is True, "a courtesy grant keeps its own end"
    assert _background(courtesy_ended) is False
    assert _background(owner) is True, "the Owner's access is unchanged"
    assert _background(basic) is False, "Gmail automation is VIP"


def _connections(db):
    accounts = {"live": _account(db, "vip"), "lapsed": _account(db, "vip")}
    _store(db, accounts["live"], "vip", period_end=_at(db, FUTURE))
    _store(db, accounts["lapsed"], "vip", period_end=None)
    ids = {}
    for key, account in accounts.items():
        db.execute(
            "INSERT INTO finva_gmail_connections(account_id, google_email, granted_scopes) VALUES (%s, %s, %s) RETURNING id",
            (account, f"{key}@correo.test", [gmail_service.GMAIL_SCOPE]),
        )
        ids[key] = db.fetchone()[0]
    return ids


def test_the_maintenance_job_only_syncs_entitled_mailboxes(db, monkeypatch):
    ids = _connections(db)
    synced = []
    monkeypatch.setenv("FINVA_GMAIL_CRON_SECRET", "s3cret")
    monkeypatch.setattr(gmail_service.mail_oauth, "discard_stale_flows", lambda conn: None)
    monkeypatch.setattr(gmail_service, "end_unentitled_mail_connections", lambda conn: 0)
    monkeypatch.setattr(gmail_service, "_connection_with_token", lambda connection_id: ({}, "token"))
    monkeypatch.setattr(gmail_service, "_credentials", lambda token: object())
    monkeypatch.setattr(gmail_service, "_start_watch", lambda *args, **kwargs: None)
    monkeypatch.setattr(gmail_service, "_sync_connection", lambda connection_id, **kwargs: synced.append(connection_id))
    monkeypatch.setattr(gmail_service, "apply_gmail_retention", lambda: {})
    result = gmail_service.gmail_maintenance("s3cret")
    assert synced == [ids["live"]], "a VIP whose store subscription has no known end is not synced"
    assert result["connections"] == 1


def test_a_gmail_push_for_an_unentitled_mailbox_is_ignored(db, monkeypatch):
    ids = _connections(db)
    synced = []
    monkeypatch.setenv("FINVA_GMAIL_PUBSUB_VERIFICATION_TOKEN", "t0ken")
    monkeypatch.setattr(gmail_service, "_sync_connection", lambda connection_id, **kwargs: synced.append(connection_id))

    def push(email: str) -> dict:
        data = base64.urlsafe_b64encode(json.dumps({"emailAddress": email, "historyId": "1"}).encode()).decode()
        return gmail_service.process_gmail_push({"message": {"data": data}}, "t0ken")

    assert push("lapsed@correo.test") == {"status": "ignored"}
    assert synced == []
    assert push("live@correo.test")["completed"] == 1
    assert synced == [ids["live"]]
