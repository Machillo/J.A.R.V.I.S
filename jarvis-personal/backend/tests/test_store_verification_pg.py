"""Verified store purchases -> plan, on PostgreSQL (embedded pgserver).

Uses migration 20260926160000 on the identity baseline plus the production shape of
plans, account_subscriptions and store_subscriptions. Purchase states here are what
store_apple / store_google return after verifying with the store. Synthetic data only.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

pgserver = pytest.importorskip("pgserver")
psycopg2 = pytest.importorskip("psycopg2")

from backend.core import database  # noqa: E402
from backend.product_ops import store_state, store_verification  # noqa: E402

ROOT = Path(__file__).resolve().parents[2] / "database"
BASELINE = ROOT / "baseline" / "v1_identity_ownership.sql"
MIGRATION = ROOT / "migrations" / "20260926160000_store_verification.sql"
ROLLBACK = ROOT / "rollback" / "20260926160000_store_verification_rollback.sql"
NOW = datetime.now(timezone.utc)
SCHEMA = """
CREATE TABLE plans (id BIGSERIAL PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL, is_active BOOLEAN NOT NULL DEFAULT TRUE);
INSERT INTO plans(code, name) VALUES ('free','Free'), ('basic','Basic'), ('vip','VIP');
CREATE TABLE account_subscriptions (
    id BIGSERIAL PRIMARY KEY, account_id UUID NOT NULL UNIQUE, plan_id BIGINT NOT NULL REFERENCES plans(id),
    status TEXT NOT NULL, access_source TEXT NOT NULL, started_at TIMESTAMPTZ, expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE store_subscriptions (
    account_id UUID PRIMARY KEY, workspace_id UUID, provider TEXT NOT NULL, plan_code TEXT NOT NULL,
    billing_period TEXT NOT NULL, product_id TEXT NOT NULL, status TEXT NOT NULL, provider_subscription_id TEXT,
    original_transaction_id TEXT, trial_ends_at TIMESTAMPTZ, current_period_start TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ, cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
    auto_renew BOOLEAN NOT NULL DEFAULT TRUE, last_verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pending_plan_code TEXT, pending_billing_period TEXT, pending_product_id TEXT, pending_effective_at TIMESTAMPTZ);
CREATE TABLE store_subscription_events (
    id BIGSERIAL PRIMARY KEY, account_id UUID, provider TEXT NOT NULL, event_type TEXT NOT NULL,
    provider_event_id TEXT, plan_code TEXT, billing_period TEXT,
    effective_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), payload_hash TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE UNIQUE INDEX uq_store_event_provider_id ON store_subscription_events(provider, provider_event_id)
    WHERE provider_event_id IS NOT NULL;
"""


@pytest.fixture
def db(tmp_path, monkeypatch):
    server = pgserver.get_server(str(os.environ.get("DINCR_PGSERVER_DIR") or tmp_path / "pg"), cleanup_mode="stop")
    admin = psycopg2.connect(server.get_uri())
    admin.autocommit = True
    name = f"store_{uuid.uuid4().hex[:12]}"
    with admin.cursor() as c:
        for role in ("anon", "authenticated"):
            c.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,))
            if not c.fetchone():
                c.execute(f'CREATE ROLE "{role}" NOLOGIN')
        c.execute(f"CREATE DATABASE {name}")
    uri = server.get_uri(name)
    conn = psycopg2.connect(uri)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(BASELINE.read_text(encoding="utf-8"))
    cur.execute(SCHEMA)
    cur.execute(MIGRATION.read_text(encoding="utf-8"))
    accounts = {}
    for n, label in enumerate(("a", "b"), start=1):
        accounts[label] = str(uuid.uuid4())
        cur.execute("INSERT INTO allowed_users(id,email,role,status) VALUES(%s,%s,'user','active')", (n, f"{label}@example.test"))
        cur.execute("INSERT INTO accounts(id,legacy_allowed_user_id,primary_email) VALUES(%s,%s,%s)", (accounts[label], n, f"{label}@example.test"))
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    monkeypatch.delenv("DINCR_STORE_ACCEPT_SANDBOX", raising=False)
    try:
        yield {"cur": cur, "accounts": accounts}
    finally:
        conn.close()
        with admin.cursor() as c:
            c.execute(f"DROP DATABASE {name} WITH (FORCE)")
        admin.close()


def _token(account_id):
    with database.get_connection() as conn:
        token = store_state.customer_token(conn, account_id)
        conn.commit()
    return token


def _state(key="orig-1", *, provider="apple", product="finva.vip.monthly", status="active", end=NOW + timedelta(days=20),
           token=None, **extra):
    return {"provider": provider, "purchase_key": key, "event_id": f"{provider}:{key}:{status}:{end}", "customer_token": token,
            "environment": "production", "product_id": product, "status": status, "auto_renew": status == "active",
            "trial_ends_at": end if status == "trialing" else None, "current_period_end": end,
            "grace_ends_at": None, "revoked_at": None, "pending_product_id": None, "superseded_key": None, **extra}


def _record(state, claimed=None):
    with database.get_connection() as conn:
        result = store_state.record_verified_purchase(conn, state, claimed_account_id=claimed)
        conn.commit()
    return result


def _plan(cur, account_id):
    cur.execute("""SELECT p.code, s.access_source FROM account_subscriptions s JOIN plans p ON p.id = s.plan_id
                   WHERE s.account_id = %s""", (account_id,))
    row = cur.fetchone()
    return row[0] if row else None


def test_a_verified_purchase_for_the_accounts_token_grants_its_plan(db):
    a = db["accounts"]["a"]
    assert _record(_state(token=_token(a)), claimed=a)["plan"] == "vip"
    assert _plan(db["cur"], a) == "vip"
    db["cur"].execute("SELECT provider, status, original_transaction_id FROM store_subscriptions WHERE account_id=%s", (a,))
    assert db["cur"].fetchone() == ("apple", "active", "orig-1")


def test_the_token_always_decides_the_account(db):
    a, b = db["accounts"]["a"], db["accounts"]["b"]
    token_a = _token(a)
    result = _record(_state(token=token_a), claimed=b)  # B presents A's purchase
    assert result["conflict"] and result["account_id"] == a
    db["cur"].execute("SELECT count(*) FROM store_purchase_conflicts WHERE claimed_account_id=%s", (b,))
    assert db["cur"].fetchone() == (1,)
    assert _plan(db["cur"], b) is None


def test_a_purchase_without_token_binds_to_the_first_account_forever(db):
    a, b = db["accounts"]["a"], db["accounts"]["b"]
    assert _record(_state(), claimed=a)["account_id"] == a
    assert _record(_state(status="active", end=NOW + timedelta(days=40)), claimed=b)["conflict"]
    assert _plan(db["cur"], a) == "vip" and _plan(db["cur"], b) is None


def test_an_unknown_token_product_or_sandbox_grants_nothing(db, monkeypatch):
    a = db["accounts"]["a"]
    with pytest.raises(HTTPException) as unknown_token:
        _record(_state(token=str(uuid.uuid4())), claimed=a)
    assert unknown_token.value.status_code == 409
    with pytest.raises(HTTPException) as unknown_product:
        _record(_state(product="com.other.product"), claimed=a)
    assert unknown_product.value.status_code == 422
    with pytest.raises(HTTPException) as sandbox:
        _record(_state(environment="sandbox"), claimed=a)
    assert sandbox.value.status_code == 409
    assert _plan(db["cur"], a) is None
    monkeypatch.setenv("DINCR_STORE_ACCEPT_SANDBOX", "1")  # QA environments only
    assert _record(_state(environment="sandbox"), claimed=a)["plan"] == "vip"


def test_an_older_state_never_overwrites_a_newer_one_but_a_refund_always_applies(db):
    a = db["accounts"]["a"]
    _record(_state(end=NOW + timedelta(days=40)), claimed=a)
    assert _record(_state(status="expired", end=NOW - timedelta(days=1)))["applied"] is False
    assert _plan(db["cur"], a) == "vip"
    assert _record(_state(status="revoked", end=NOW + timedelta(days=40), revoked_at=NOW))["plan"] == "free"
    assert _plan(db["cur"], a) == "free"
    assert _record(_state(end=NOW + timedelta(days=80)))["applied"] is False  # a refunded purchase stays refunded


def test_the_best_live_purchase_across_stores_wins(db):
    a = db["accounts"]["a"]
    token = _token(a)
    _record(_state("apple-basic", product="finva.basic.monthly", token=token), claimed=a)
    _record(_state("google-vip", provider="google", end=NOW + timedelta(days=5), token=token), claimed=a)
    assert _plan(db["cur"], a) == "vip"
    _record(_state("google-vip", provider="google", status="expired", end=NOW + timedelta(days=5), token=token))
    assert _plan(db["cur"], a) == "basic"


def test_grace_keeps_the_plan_until_the_stores_grace_end(db):
    a = db["accounts"]["a"]
    grace_end = NOW + timedelta(days=3)
    _record(_state(status="grace_period", end=NOW - timedelta(hours=1), grace_ends_at=grace_end), claimed=a)
    assert _plan(db["cur"], a) == "vip"
    db["cur"].execute("SELECT status, current_period_end, grace_ends_at FROM store_subscriptions WHERE account_id=%s", (a,))
    status, entitlement_end, stored_grace = db["cur"].fetchone()
    assert status == "grace_period" and entitlement_end == stored_grace == grace_end
    with database.get_connection() as conn:
        assert store_state.expire_lapsed(conn, now=grace_end + timedelta(minutes=1)) == 1
        conn.commit()
    assert _plan(db["cur"], a) == "free"


def test_a_replacing_google_purchase_supersedes_the_old_one(db):
    a = db["accounts"]["a"]
    _record(_state("old", provider="google", product="finva.basic.monthly"), claimed=a)
    _record(_state("new", provider="google", superseded_key="old"), claimed=a)
    db["cur"].execute("SELECT purchase_key, status FROM store_purchases ORDER BY purchase_key")
    assert db["cur"].fetchall() == [("new", "active"), ("old", "superseded")]
    assert _plan(db["cur"], a) == "vip"


def test_owner_and_courtesy_access_are_never_changed_by_stores(db):
    a, cur = db["accounts"]["a"], db["cur"]
    cur.execute("""INSERT INTO account_subscriptions(account_id,plan_id,status,access_source)
                   SELECT %s,id,'active','courtesy' FROM plans WHERE code='vip'""", (a,))
    _record(_state(product="finva.basic.monthly", status="expired", end=NOW - timedelta(days=1)), claimed=a)
    cur.execute("SELECT access_source FROM account_subscriptions WHERE account_id=%s", (a,))
    assert cur.fetchone() == ("courtesy",) and _plan(cur, a) == "vip"


def test_a_repeated_store_event_is_applied_once(db, monkeypatch):
    a = db["accounts"]["a"]
    state = _state(token=_token(a))
    first = store_verification._apply(dict(state), event_type="apple:DID_RENEW", event_id="apple-notification:n-1")
    again = store_verification._apply(dict(state), event_type="apple:DID_RENEW", event_id="apple-notification:n-1")
    assert first["status"] == "applied" and again == {"status": "duplicate"}


def test_a_conflict_is_recorded_even_though_the_request_is_refused(db):
    a, b = db["accounts"]["a"], db["accounts"]["b"]
    _record(_state(), claimed=a)
    with pytest.raises(HTTPException) as refused:
        store_verification._apply(_state(end=NOW + timedelta(days=41)), event_type="client_verification",
                                  event_id="apple:x", claimed_account_id=b)
    assert refused.value.status_code == 409
    db["cur"].execute("SELECT count(*) FROM store_purchase_conflicts")
    assert db["cur"].fetchone() == (1,)


def test_migration_is_idempotent_and_the_rollback_refuses_to_drop_paid_history(db):
    cur, a = db["cur"], db["accounts"]["a"]
    cur.execute(MIGRATION.read_text(encoding="utf-8"))
    tail = MIGRATION.read_text(encoding="utf-8").split("-- Postflight (read-only)")[-1]
    cur.execute("\n".join(line[3:] for line in tail.splitlines()[1:] if line.startswith("-- ")))
    assert cur.fetchall() == []
    _record(_state(), claimed=a)
    with pytest.raises(psycopg2.Error) as refused:
        cur.execute(ROLLBACK.read_text(encoding="utf-8"))
    assert refused.value.pgcode == "SV001"
