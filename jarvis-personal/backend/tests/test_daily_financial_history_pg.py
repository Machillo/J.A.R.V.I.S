"""The daily financial-history job on a real PostgreSQL (P0.2).

Tables come from database/schema.sql and the migrations that create the history tables, so
eligibility, the per-day health upsert, the advisor workspace lock and the reads run against
the real columns and constraints. Only the input services are synthetic (p02_parity_harness).
"""
from __future__ import annotations

import datetime as dt
import os
import re
import threading
import time
import uuid
from pathlib import Path

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg2 = pytest.importorskip("psycopg2")
from psycopg2.extras import RealDictCursor  # noqa: E402

from backend.auth.current_user import reset_current_user, set_current_user  # noqa: E402
from backend.core import database  # noqa: E402
from backend.tests import p02_parity_harness as h  # noqa: E402

ROOT = Path(__file__).resolve().parents[2] / "database"
SCHEMA = (ROOT / "schema.sql").read_text(encoding="utf-8")
OWNER_EMAIL = "owner@example.test"
DAY1, DAY2 = dt.date(2026, 9, 14), dt.date(2026, 9, 15)


def _block(text: str, name: str) -> str:
    match = re.search(rf"CREATE TABLE IF NOT EXISTS (?:public\.)?{name} \(.*?\n\);", text, re.S)
    assert match, f"{name} moved"
    return match.group(0)


def _ddl() -> list[str]:
    statements = [_block(SCHEMA, name) for name in
                  ("allowed_users", "accounts", "workspaces", "workspace_members", "plans", "features", "plan_features", "account_subscriptions", "transactions")]
    statements.append("ALTER TABLE transactions ADD COLUMN workspace_id UUID")  # added by a later migration
    statements.append(_block((ROOT / "migrations" / "20260925130000_request_path_schema.sql").read_text(encoding="utf-8"), "store_subscriptions"))
    statements.append((ROOT / "migrations" / "20260908_financial_health_snapshots.sql").read_text(encoding="utf-8"))
    legacy = (ROOT / "migrations" / "20260926125000_owner_legacy_schema.sql").read_text(encoding="utf-8")
    statements += [_block(legacy, "advisor_current_strategy"), _block(legacy, "advisor_strategy_history")]
    return statements


@pytest.fixture
def db(tmp_path, monkeypatch):
    server = pgserver.get_server(str(os.environ.get("DINCR_PGSERVER_DIR") or tmp_path / "pg"), cleanup_mode="stop")
    admin = psycopg2.connect(server.get_uri())
    admin.autocommit = True
    name = f"history_{os.getpid()}_{abs(hash(str(tmp_path))) % 10**8}"
    with admin.cursor() as c:
        c.execute(f"CREATE DATABASE {name}")
    uri = server.get_uri(name)
    conn = psycopg2.connect(uri, cursor_factory=RealDictCursor)
    conn.autocommit = True
    cur = conn.cursor()
    for statement in _ddl():
        cur.execute(statement)
    cur.execute("INSERT INTO plans(code, name) VALUES ('free','Gratis'), ('basic','Basic'), ('vip','VIP')")
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    monkeypatch.setenv("OWNER_EMAILS", OWNER_EMAIL)
    yield {"cur": cur, "uri": uri}
    conn.close()
    with admin.cursor() as c:
        c.execute(f"DROP DATABASE {name} WITH (FORCE)")
    admin.close()


def _account(cur, email, *, role="user", plan="vip", source="courtesy", status="active", expires="2099-01-01",
             account_status="active", store=None, legacy=True, membership="active"):
    legacy_id = None
    if legacy:
        cur.execute("INSERT INTO allowed_users(email, role, status) VALUES (%s, %s, 'active') RETURNING id", (email, role))
        legacy_id = cur.fetchone()["id"]
    account = str(uuid.uuid4())
    cur.execute("INSERT INTO accounts(id, legacy_allowed_user_id, primary_email, role, status) VALUES (%s,%s,%s,%s,%s)",
                (account, legacy_id, email, role, account_status))
    workspace = str(uuid.uuid4())
    cur.execute("INSERT INTO workspaces(id, workspace_key, owner_account_id, name) VALUES (%s, %s, %s, 'Personal')",
                (workspace, f"personal:{account}", account))
    cur.execute("INSERT INTO workspace_members(workspace_id, account_id, status) VALUES (%s, %s, %s)",
                (workspace, account, membership))
    if plan:
        cur.execute("""INSERT INTO account_subscriptions(account_id, plan_id, status, access_source, expires_at)
                       SELECT %s, id, %s, %s, %s FROM plans WHERE code = %s""", (account, status, source, expires, plan))
    if store:
        cur.execute("""INSERT INTO store_subscriptions(account_id, provider, plan_code, billing_period, product_id, status, current_period_end)
                       VALUES (%s, 'apple', %s, 'monthly', 'synthetic', %s, %s)""", (account, plan, store[0], store[1]))
    for row in h.TRANSACTIONS:
        cur.execute("""INSERT INTO transactions(transaction_date, description, amount, transaction_type, category, workspace_id)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (row["transaction_date"], row["description"], row["amount"], row["transaction_type"], row["category"], workspace))
    return {"account": account, "workspace": workspace, "legacy": legacy_id}


def _eligible():
    from backend.finance.daily_history import eligible_workspaces

    with database.get_connection() as conn:
        return {item["workspace_id"]: item for item in eligible_workspaces(conn)}


def test_eligibility_is_vip_and_the_verified_owner_only(db):
    cur = db["cur"]
    owner = _account(cur, OWNER_EMAIL, role="owner", source="owner")
    vip = _account(cur, "vip@example.test")
    vip_store = _account(cur, "vipstore@example.test", source="self_service", store=("active", "2099-01-01"))
    excluded = {
        "free": _account(cur, "free@example.test", plan="free", source="self_service"),
        "basic": _account(cur, "basic@example.test", plan="basic", source="self_service", store=("active", "2099-01-01")),
        "expired courtesy": _account(cur, "expired@example.test", expires="2020-01-01"),
        "pending": _account(cur, "pending@example.test", status="pending"),
        "store lapsed": _account(cur, "lapsed@example.test", source="self_service", store=("expired", "2020-01-01")),
        "no store purchase": _account(cur, "nostore@example.test", source="self_service"),
        "blocked account": _account(cur, "blocked@example.test", account_status="blocked"),
        "no legacy identity": _account(cur, "nolegacy@example.test", legacy=False),
        "unlisted owner": _account(cur, "owner2@example.test", role="owner", source="owner"),
        "disabled membership": _account(cur, "disabled@example.test", membership="disabled"),
    }
    eligible = _eligible()
    assert set(eligible) == {owner["workspace"], vip["workspace"], vip_store["workspace"]}
    assert eligible[owner["workspace"]]["role"] == "owner"
    assert eligible[vip["workspace"]]["role"] == "user"
    assert eligible[vip["workspace"]] == {"id": vip["legacy"], "account_id": vip["account"], "workspace_id": vip["workspace"],
                                          "role": "user", "status": "active"}
    assert not {item["workspace"] for item in excluded.values()} & set(eligible)


def test_a_plan_granting_strategy_vip_through_plan_features_is_eligible(db):
    cur = db["cur"]
    cur.execute("INSERT INTO plans(code, name) VALUES ('partner','Partner') RETURNING id")
    plan_id = cur.fetchone()["id"]
    cur.execute("INSERT INTO features(code) VALUES ('strategy_vip') RETURNING id")
    cur.execute("INSERT INTO plan_features(plan_id, feature_id) VALUES (%s, %s)", (plan_id, cur.fetchone()["id"]))
    partner = _account(cur, "partner@example.test", plan="partner")
    assert partner["workspace"] in _eligible()


def _counts(cur):
    cur.execute("""SELECT (SELECT count(*) FROM financial_health_snapshots) AS health,
                          (SELECT count(*) FROM advisor_current_strategy) AS current,
                          (SELECT count(*) FROM advisor_strategy_history) AS history,
                          (SELECT COALESCE(max(updated_at), 'epoch') FROM advisor_current_strategy) AS updated""")
    return dict(cur.fetchone())


def _identity(account):
    return {"id": account["legacy"], "account_id": account["account"], "workspace_id": account["workspace"], "role": "user", "status": "active"}


def test_day1_day2_history_end_to_end(db, monkeypatch):
    from backend.advisor.core import build_advisor_strategy
    from backend.finance.daily_history import run_daily_financial_history
    from backend.finance.deterioration import get_financial_deterioration

    cur = db["cur"]
    owner = _account(cur, OWNER_EMAIL, role="owner", source="owner")
    vip = _account(cur, "vip@example.test")
    free = _account(cur, "free@example.test", plan="free", source="self_service")
    h.install(monkeypatch, None, real_database=True)

    # DAY 1: the job records health and strategy A for VIP and the Owner only.
    first = run_daily_financial_history(DAY1)
    assert first == {"status": "OK", "date": "2026-09-14", "eligible": 2, "recorded": 2, "strategy_changed": 1, "failed": 0}
    cur.execute("SELECT workspace_id::text, snapshot_date FROM financial_health_snapshots ORDER BY 1")
    assert sorted((r["workspace_id"], r["snapshot_date"]) for r in cur.fetchall()) == sorted(
        [(owner["workspace"], DAY1), (vip["workspace"], DAY1)])
    cur.execute("SELECT count(*) AS n FROM financial_health_snapshots WHERE workspace_id = %s", (free["workspace"],))
    assert cur.fetchone()["n"] == 0

    # The same day again: no duplicate observation, no duplicate history (A -> A).
    again = run_daily_financial_history(DAY1)
    assert again["strategy_changed"] == 0 and _counts(cur)["health"] == 2 and _counts(cur)["history"] == 1
    cur.execute("SELECT count(*) AS n FROM advisor_strategy_history WHERE workspace_id = %s", (vip["workspace"],))
    assert cur.fetchone()["n"] == 0          # VIP reads never stored a strategy; the job stores none either

    # DAY 2, before the job: the condition deteriorated; reads compare with DAY 1 and write nothing.
    h.install(monkeypatch, None, real_database=True,
              debts=[{**h.DEBTS[0], "remaining_amount": 1_600_000}, h.DEBTS[1]],
              accounts=[{**h.ACCOUNTS[0], "balance_crc": 150_000}, h.ACCOUNTS[1]])
    before = _counts(cur)
    token = set_current_user(_identity(vip))
    try:
        report = get_financial_deterioration(DAY2)
        get_financial_deterioration(DAY2)
    finally:
        reset_current_user(token)
    token = set_current_user({**_identity(owner), "role": "owner"})
    try:
        strategy = build_advisor_strategy()
    finally:
        reset_current_user(token)
    assert _counts(cur) == before                                   # two reads: database identical
    assert report["context"]["previous_snapshot_date"] == str(DAY1)
    assert {"liquidity_history", "debt_history"} <= {signal["code"] for signal in report["signals"]}
    assert strategy["persistence"]["changed"] is True and strategy["persistence"]["persisted"] is False

    # DAY 2 job: strategy B adds exactly one history row per workspace (A -> B), current is B.
    second = run_daily_financial_history(DAY2)
    assert second["strategy_changed"] == 1 and _counts(cur)["history"] == 2 and _counts(cur)["health"] == 4
    cur.execute("SELECT strategy_hash FROM advisor_current_strategy WHERE workspace_id = %s", (owner["workspace"],))
    assert cur.fetchone()["strategy_hash"] == strategy["persistence"]["strategy_hash"]


def test_concurrent_same_day_health_observations_converge_on_one_row(db):
    from backend.finance.deterioration import persist_health_observation

    vip = _account(db["cur"], "vip@example.test")
    barrier, errors = threading.Barrier(4), []

    def write(value):
        try:
            barrier.wait()
            with database.get_connection() as conn:
                persist_health_observation(conn, vip["workspace"], DAY1, {
                    "liquidity": value, "recurring_monthly": 1, "debt_balance": 1, "debt_monthly": 1,
                    "salvavidas_coverage": 1, "net_worth": 1})
                conn.commit()
        except Exception as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(value,)) for value in (100, 200, 300, 400)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    db["cur"].execute("SELECT count(*) AS n FROM financial_health_snapshots WHERE workspace_id = %s AND snapshot_date = %s",
                      (vip["workspace"], DAY1))
    assert db["cur"].fetchone()["n"] == 1


def test_a_concurrent_strategy_run_waits_for_the_workspace_lock_and_adds_no_duplicate(db):
    from backend.advisor.core import _persist_strategy, _strategy_fingerprint

    vip = _account(db["cur"], "vip@example.test")
    token = set_current_user(_identity(vip))
    try:
        assert _persist_strategy({"summary": "A"})["changed"] is True
    finally:
        reset_current_user(token)
    canonical_b, hash_b = _strategy_fingerprint({"summary": "B"})

    # Another run of the job is mid-transaction: it holds the workspace lock and has stored B.
    other = psycopg2.connect(db["uri"])
    with other.cursor() as c:
        c.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"advisor-strategy:{vip['workspace']}",))
        c.execute("INSERT INTO advisor_strategy_history(workspace_id, advisor_version, strategy_hash, strategy) VALUES (%s,'v',%s,%s::jsonb)",
                  (vip["workspace"], hash_b, canonical_b))
        c.execute("UPDATE advisor_current_strategy SET strategy_hash=%s WHERE workspace_id=%s", (hash_b, vip["workspace"]))
    result = {}

    def run():
        inner = set_current_user(_identity(vip))
        try:
            result.update(_persist_strategy({"summary": "B"}))
        finally:
            reset_current_user(inner)

    thread = threading.Thread(target=run)
    thread.start()
    time.sleep(0.5)
    assert thread.is_alive(), "the second run must wait for the workspace lock"
    other.commit()
    other.close()
    thread.join(10)
    assert result == {"strategy_hash": hash_b, "changed": False, "persisted": True}
    db["cur"].execute("SELECT strategy_hash FROM advisor_strategy_history WHERE workspace_id = %s ORDER BY id", (vip["workspace"],))
    assert [row["strategy_hash"] for row in db["cur"].fetchall()][1:] == [hash_b]   # B once, not twice


def test_a_second_run_while_one_is_in_progress_returns_without_writing(db, monkeypatch):
    from backend.finance.daily_history import RUN_LOCK, run_daily_financial_history

    _account(db["cur"], "vip@example.test")
    h.install(monkeypatch, None, real_database=True)
    other = psycopg2.connect(db["uri"])
    with other.cursor() as c:
        c.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (RUN_LOCK,))
    try:
        assert run_daily_financial_history(DAY1) == {"status": "ALREADY_RUNNING", "date": "2026-09-14"}
        assert _counts(db["cur"])["health"] == 0
    finally:
        other.rollback()
        other.close()
    assert run_daily_financial_history(DAY1)["recorded"] == 1      # the guard ends with the other run


def test_the_database_refuses_a_legacy_admin_role(db):
    # P0.2d migration: only "user" and the single "owner" can be stored (accounts and allowlist).
    with pytest.raises(psycopg2.errors.CheckViolation):
        _account(db["cur"], "legacy@example.test", role="admin")


def test_history_by_identity_free_basic_vip_owner(db, monkeypatch):
    from backend.finance.daily_history import run_daily_financial_history

    cur = db["cur"]
    people = {
        "free": _account(cur, "free@example.test", plan="free", source="self_service"),
        "basic": _account(cur, "basic@example.test", plan="basic", source="self_service", store=("active", "2099-01-01")),
        "vip": _account(cur, "vip@example.test"),
        "owner": _account(cur, OWNER_EMAIL, role="owner", source="owner"),
        # Listed in OWNER_EMAILS but stored as a user: never the Owner.
        "listed user": _account(cur, "listed@example.test", plan="free", source="self_service"),
    }
    monkeypatch.setenv("OWNER_EMAILS", f"{OWNER_EMAIL},listed@example.test")
    h.install(monkeypatch, None, real_database=True)
    run_daily_financial_history(DAY1)

    def rows(table, person):
        cur.execute(f"SELECT count(*) AS n FROM {table} WHERE workspace_id = %s", (people[person]["workspace"],))
        return cur.fetchone()["n"]

    expected = {  # person: (health history, strategy history)
        "free": (0, 0), "basic": (0, 0), "vip": (1, 0), "owner": (1, 1),
        "listed user": (0, 0),
    }
    actual = {person: (rows("financial_health_snapshots", person),
                       int(rows("advisor_current_strategy", person) > 0 or rows("advisor_strategy_history", person) > 0))
              for person in people}
    assert actual == expected

