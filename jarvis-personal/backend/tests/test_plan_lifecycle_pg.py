"""Plan changes on a real PostgreSQL: downgrades keep the current plan until its stored end;
paid plans come only from App Store / Google Play subscriptions.

Skipped when the embedded server (pgserver) is not installed.
"""
from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException

pgserver = pytest.importorskip("pgserver")
psycopg2 = pytest.importorskip("psycopg2")

from backend.auth import plan_lifecycle, saas  # noqa: E402
from backend.core import database  # noqa: E402
from backend.product_ops import service as billing  # noqa: E402

MIGRATION = Path(__file__).resolve().parents[2] / "database" / "migrations" / "20260926100000_plan_change_lifecycle.sql"
ROLLBACK = Path(__file__).resolve().parents[2] / "database" / "rollback" / "20260926100000_plan_change_lifecycle_rollback.sql"
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
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('pending','active','expired','suspended')),
    access_source TEXT NOT NULL DEFAULT 'self_service' CHECK (access_source IN ('self_service','courtesy','owner')),
    started_at TIMESTAMPTZ, expires_at TIMESTAMPTZ, last_payment_at TIMESTAMPTZ, courtesy_note TEXT,
    granted_by UUID, granted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
-- Still read by main's _expire_unpaid_subscription until the off-store tables are retired.
CREATE TABLE billing_subscriptions (
    account_id UUID PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE, workspace_id UUID,
    plan_code TEXT NOT NULL CHECK (plan_code IN ('basic','vip')),
    status TEXT NOT NULL CHECK (status IN ('payment_pending','active','past_due','canceled','expired','refunded')),
    provider TEXT NOT NULL DEFAULT 'sinpe_mobile', current_period_start TIMESTAMPTZ, current_period_end TIMESTAMPTZ,
    cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE billing_orders (id BIGSERIAL PRIMARY KEY, account_id UUID, status TEXT, updated_at TIMESTAMPTZ);
CREATE TABLE store_subscriptions (account_id UUID PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
    provider TEXT NOT NULL, plan_code TEXT NOT NULL, status TEXT NOT NULL,
    trial_ends_at TIMESTAMPTZ, current_period_end TIMESTAMPTZ);
"""
PROMO = billing.LAUNCH_PROMOTION_CODE


@pytest.fixture
def db(tmp_path, monkeypatch):
    server = pgserver.get_server(str(os.environ.get("DINCR_PGSERVER_DIR") or tmp_path / "pg"), cleanup_mode="stop")
    admin = psycopg2.connect(server.get_uri())
    admin.autocommit = True
    name = f"plans_{os.getpid()}_{abs(hash(str(tmp_path))) % 10**8}"
    with admin.cursor() as c:
        c.execute(f"CREATE DATABASE {name}")
    uri = server.get_uri(name)
    conn = psycopg2.connect(uri)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(SCHEMA)
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    monkeypatch.setattr(plan_lifecycle, "_supported_until", 0.0)  # each test database starts unknown
    monkeypatch.setattr(billing, "ensure_schema", lambda conn: None)
    monkeypatch.setattr(billing, "record_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(saas, "enrich_identity", lambda user: {**user, "subscription": _subscription(user["account_id"])})
    state = {"account": None, "role": "user"}
    monkeypatch.setattr(saas, "get_current_user", lambda: {"role": state["role"], "account_id": state["account"]})
    monkeypatch.setattr(saas, "get_current_account_id", lambda: state["account"])
    monkeypatch.setattr(billing, "get_current_account_id", lambda: state["account"])
    yield {"cur": cur, "state": state, "uri": uri}
    conn.close()
    with admin.cursor() as c:
        c.execute(f"DROP DATABASE {name} WITH (FORCE)")
    admin.close()


@pytest.fixture
def migrated(db):
    db["cur"].execute(MIGRATION.read_text(encoding="utf-8"))
    return db


def _subscription(account_id):
    with database.get_connection() as conn:
        row = saas._subscription(conn, account_id)
        conn.commit()
    return row


def _account(db, plan="vip", source="courtesy", note=PROMO, expires="NOW() + INTERVAL '90 days'", role="user"):
    account = str(uuid.uuid4())
    cur = db["cur"]
    cur.execute("INSERT INTO accounts(id, role, onboarding_completed, onboarding_level, plan_selected) VALUES (%s, %s, TRUE, %s, TRUE)",
                (account, role, plan))
    cur.execute(f"""INSERT INTO account_subscriptions(account_id, plan_id, status, access_source, started_at, expires_at, courtesy_note)
                    SELECT %s, id, 'active', %s, NOW(), {expires}, %s FROM plans WHERE code = %s""",
                (account, source, note, plan))
    db["state"]["account"], db["state"]["role"] = account, role
    return account


def _row(db, account):
    db["cur"].execute("""SELECT p.code, s.access_source, s.expires_at, pp.code, s.pending_effective_at
                         FROM account_subscriptions s JOIN plans p ON p.id = s.plan_id
                         LEFT JOIN plans pp ON pp.id = s.pending_plan_id WHERE s.account_id = %s""", (account,))
    return db["cur"].fetchone()


def _expire(db, account, column="expires_at"):
    db["cur"].execute(f"UPDATE account_subscriptions SET {column} = NOW() - INTERVAL '1 minute' WHERE account_id = %s", (account,))
    db["cur"].execute("""UPDATE account_subscriptions SET pending_effective_at = NOW() - INTERVAL '1 minute'
                         WHERE account_id = %s AND pending_plan_id IS NOT NULL""", (account,))


def _no_checkout(*args, **kwargs):
    raise AssertionError("keeping or scheduling must not activate a plan")


@pytest.mark.parametrize("target", ["free", "basic"])
def test_a_downgrade_keeps_vip_until_the_stored_end(migrated, monkeypatch, target):
    account = _account(migrated)
    monkeypatch.setattr(billing, "create_checkout", _no_checkout)
    expires = _row(migrated, account)[2]

    response = saas.select_plan(target)

    assert response["status"] == "downgrade_scheduled"
    assert response["pending_plan"] == target
    code, source, still_expires, pending, effective = _row(migrated, account)
    assert (code, source, still_expires, pending, effective) == ("vip", "courtesy", expires, target, expires)
    assert response["profile"]["subscription"]["plan"] == "vip"
    assert response["profile"]["subscription"]["pending_plan"] == target
    assert saas.require_feature("strategy_vip") is True


def test_at_the_end_of_the_promotion_the_pending_free_plan_applies(migrated):
    account = _account(migrated)
    saas.select_plan("free")
    _expire(migrated, account)

    subscription = _subscription(account)

    assert subscription["plan"] == "free"
    assert subscription["access_notice"]["code"] == "promotion_ended"
    assert _row(migrated, account)[3:] == (None, None)
    with pytest.raises(HTTPException) as denied:
        saas.require_feature("strategy_vip")
    assert denied.value.status_code == 403


def _store(db, account, plan, status="active", period="NOW() + INTERVAL '20 days'", trial="NULL", provider="google"):
    db["cur"].execute(f"""INSERT INTO store_subscriptions(account_id, provider, plan_code, status, trial_ends_at, current_period_end)
                          VALUES (%s, %s, %s, %s, {trial}, {period})""", (account, provider, plan, status))


def test_a_pending_basic_needs_a_store_subscription_after_the_promotion(migrated):
    account = _account(migrated)
    saas.select_plan("basic")
    _expire(migrated, account)
    assert _subscription(account)["plan"] == "free"  # nobody bought Basic: DINCR never grants it

    paid = _account(migrated)
    saas.select_plan("basic")
    _store(migrated, paid, "basic")  # bought in the store before the promotion ended
    _expire(migrated, paid)
    assert _subscription(paid)["plan"] == "basic"


def test_the_store_subscription_decides_the_plan_after_the_courtesy(migrated):
    """A pending Free cannot cancel a store purchase; the store is authoritative for paid plans."""
    account = _account(migrated)
    saas.select_plan("free")
    _store(migrated, account, "vip")
    _expire(migrated, account)

    subscription = _subscription(account)

    assert subscription["plan"] == "vip" and subscription["access_source"] == "self_service"
    assert subscription["pending_plan"] is None
    assert saas.require_feature("strategy_vip") is True  # the store plan is usable, not only displayed


def test_a_pending_paid_plan_says_it_needs_a_store_subscription(migrated):
    _account(migrated)
    assert saas.select_plan("basic")["profile"]["subscription"]["pending_requires_payment"] is True
    _account(migrated)
    assert saas.select_plan("free")["profile"]["subscription"]["pending_requires_payment"] is False
    covered = _account(migrated)
    saas.select_plan("basic")
    _store(migrated, covered, "basic")
    assert _subscription(covered)["pending_requires_payment"] is False


def test_an_ended_period_is_applied_before_the_decision(migrated, monkeypatch):
    """A courtesy that already ended is not 'kept': the request sees the real plan."""
    monkeypatch.setattr(billing, "launch_promotion_status", lambda: {"active": True})  # independent of today's date
    account = _account(migrated)
    saas.select_plan("free")
    _expire(migrated, account)
    assert saas.select_plan("vip")["status"] != "plan_kept"
    assert _row(migrated, account)[3:] == (None, None)


def test_choosing_the_current_plan_again_keeps_it(migrated, monkeypatch):
    account = _account(migrated)
    saas.select_plan("free")
    monkeypatch.setattr(billing, "create_checkout", _no_checkout)

    response = saas.select_plan("vip")

    assert response["status"] == "plan_kept"
    assert _row(migrated, account)[0] == "vip" and _row(migrated, account)[3:] == (None, None)
    _expire(migrated, account)
    assert _subscription(account)["plan"] == "free"  # no pending plan: the promotion ends normally


def test_an_upgrade_is_immediate_and_replaces_a_scheduled_downgrade(migrated, monkeypatch):
    account = _account(migrated, plan="basic")
    saas.select_plan("free")
    assert _row(migrated, account)[3] == "free"
    monkeypatch.setattr(billing, "launch_promotion_status", lambda: {"active": True})

    response = saas.select_plan("vip")

    assert response["status"] == "promotion_active"
    assert _row(migrated, account)[0] == "vip" and _row(migrated, account)[3:] == (None, None)


def test_repeated_requests_leave_one_consistent_pending_change(migrated):
    account = _account(migrated)
    expires = _row(migrated, account)[2]
    for target in ("free", "free", "basic", "basic"):
        saas.select_plan(target)
    assert _row(migrated, account) == ("vip", "courtesy", expires, "basic", expires)
    migrated["cur"].execute("SELECT count(*) FROM pg_constraint WHERE conrelid = 'public.account_subscriptions'::regclass "
                            "AND contype = 'f' AND confrelid = 'public.plans'::regclass")
    assert migrated["cur"].fetchone() == (2,)  # plan_id and pending_plan_id, each once


def test_concurrent_requests_are_serialized_and_never_downgrade_immediately(migrated):
    account = _account(migrated)
    errors = []

    def request(target):
        try:
            saas.select_plan(target)
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=request, args=(t,)) for t in ("free", "basic") * 5]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    code, source, _, pending, _ = _row(migrated, account)
    assert (code, source) == ("vip", "courtesy") and pending in {"free", "basic"}


def test_a_plan_without_a_running_grant_changes_now(migrated):
    """No courtesy end and no store subscription: nothing is left to keep."""
    account = _account(migrated, source="self_service", note=None, expires="NULL")
    assert saas.select_plan("free")["status"] == "ok"
    assert _row(migrated, account)[0] == "free"


def test_an_expired_owner_courtesy_returns_to_free_features(migrated):
    account = _account(migrated, note="support grant", expires="NOW() - INTERVAL '1 day'")
    subscription = _subscription(account)
    assert subscription["plan"] == "free" and subscription["status"] == "active"
    assert subscription["access_notice"]["code"] == "courtesy_ended"
    assert saas.require_feature("debts") is True


def test_the_owner_is_never_changed(migrated, monkeypatch):
    account = _account(migrated, source="owner", note=None, expires="NULL", role="owner")
    monkeypatch.setattr(billing, "create_checkout", _no_checkout)
    assert saas.select_plan("free")["status"] == "ok"
    assert _row(migrated, account)[:2] == ("vip", "owner")


@pytest.mark.parametrize("source", ["self_service", "courtesy"])
@pytest.mark.parametrize("target", ["free", "basic"])
def test_a_store_managed_plan_is_changed_only_in_the_store(migrated, source, target):
    account = _account(migrated, source=source, note=None if source == "self_service" else PROMO,
                       expires="NULL" if source == "self_service" else "NOW() + INTERVAL '90 days'")
    _store(migrated, account, "vip")
    with pytest.raises(HTTPException) as refused:
        saas.select_plan(target)
    assert refused.value.status_code == 409 and "App Store" in refused.value.detail
    assert _row(migrated, account)[0] == "vip" and _row(migrated, account)[3] is None


@pytest.mark.parametrize(("status", "trial", "period"), [
    ("expired", "NULL", "NOW() + INTERVAL '5 days'"),
    ("revoked", "NULL", "NOW() + INTERVAL '5 days'"),
    ("canceled", "NULL", "NOW() + INTERVAL '5 days'"),
    ("active", "NULL", "NOW() - INTERVAL '1 minute'"),
    ("grace_period", "NULL", "NOW() - INTERVAL '1 minute'"),
    ("trialing", "NOW() - INTERVAL '1 minute'", "NOW() + INTERVAL '30 days'"),
])
def test_a_store_subscription_that_ended_grants_nothing(migrated, status, trial, period):
    account = _account(migrated)
    _store(migrated, account, "vip", status=status, trial=trial, period=period)
    assert saas.select_plan("free")["status"] == "downgrade_scheduled"  # not store-managed any more
    _expire(migrated, account)
    assert _subscription(account)["plan"] == "free"


@pytest.mark.parametrize(("status", "trial"), [("trialing", "NOW() + INTERVAL '3 days'"), ("grace_period", "NULL")])
def test_a_trial_or_grace_period_is_a_live_store_subscription(migrated, status, trial):
    account = _account(migrated)
    _store(migrated, account, "basic", status=status, trial=trial)
    _expire(migrated, account)
    assert _subscription(account)["plan"] == "basic"
    assert saas.require_feature("debts") is True


def test_a_free_account_still_selects_free_during_onboarding(migrated):
    account = _account(migrated, plan="free", source="self_service", note=None, expires="NULL")
    migrated["cur"].execute("UPDATE accounts SET plan_selected = FALSE WHERE id = %s", (account,))
    assert saas.select_plan("free")["status"] == "ok"
    migrated["cur"].execute("SELECT plan_selected FROM accounts WHERE id = %s", (account,))
    assert migrated["cur"].fetchone() == (True,)


def test_without_the_migration_a_downgrade_is_refused_not_applied(db):
    account = _account(db)
    with pytest.raises(HTTPException) as refused:
        saas.select_plan("free")
    assert refused.value.status_code == 409
    db["cur"].execute("SELECT p.code, s.expires_at IS NOT NULL FROM account_subscriptions s JOIN plans p ON p.id = s.plan_id WHERE account_id = %s", (account,))
    assert db["cur"].fetchone() == ("vip", True)


def test_the_migration_is_idempotent_constrained_and_reversible(db):
    cur = db["cur"]
    cur.execute(MIGRATION.read_text(encoding="utf-8"))
    cur.execute(MIGRATION.read_text(encoding="utf-8"))
    cur.execute("SELECT count(*) FROM pg_constraint WHERE conrelid = 'public.account_subscriptions'::regclass AND contype = 'f' "
                "AND conkey = ARRAY[(SELECT attnum FROM pg_attribute WHERE attrelid = 'public.account_subscriptions'::regclass "
                "AND attname = 'pending_plan_id')]")
    assert cur.fetchone() == (1,)  # a second run adds no duplicate FK
    account = _account(db)
    with pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute("UPDATE account_subscriptions SET pending_plan_id = (SELECT id FROM plans WHERE code = 'free') WHERE account_id = %s", (account,))
    postflight = "\n".join(line[3:] for line in MIGRATION.read_text(encoding="utf-8").split("-- Postflight (read-only)")[-1].splitlines()[1:]
                           if line.startswith("-- "))
    cur.execute(postflight)
    assert cur.fetchall() == []
    cur.execute(ROLLBACK.read_text(encoding="utf-8"))
    cur.execute("SELECT count(*) FROM pg_attribute WHERE attrelid = 'public.account_subscriptions'::regclass AND attname LIKE 'pending%' AND NOT attisdropped")
    assert cur.fetchone() == (0,)


def test_a_simulated_sandbox_subscription_is_not_a_store_plan(migrated):
    """The Owner-only QA simulator writes provider 'sandbox': it neither blocks changes nor grants a plan."""
    account = _account(migrated)
    _store(migrated, account, "vip", provider="sandbox")
    assert saas.select_plan("free")["status"] == "downgrade_scheduled"
    _expire(migrated, account)
    assert _subscription(account)["plan"] == "free"


@pytest.mark.parametrize(("store", "plan_after"), [("basic", "basic"), (None, "free")])
def test_revoking_a_courtesy_keeps_a_store_purchase(migrated, monkeypatch, store, plan_after):
    account = _account(migrated)
    if store:
        _store(migrated, account, store)
    monkeypatch.setattr(saas, "get_managed_user", lambda account_id: {"account_id": account_id})
    saas.revoke_courtesy(account)
    assert _row(migrated, account)[:2] == (plan_after, "self_service")


def test_scheduling_during_onboarding_marks_the_plan_as_chosen(migrated):
    account = _account(migrated)
    migrated["cur"].execute("UPDATE accounts SET plan_selected = FALSE WHERE id = %s", (account,))
    assert saas.select_plan("free")["status"] == "downgrade_scheduled"
    migrated["cur"].execute("SELECT plan_selected FROM accounts WHERE id = %s", (account,))
    assert migrated["cur"].fetchone() == (True,)
