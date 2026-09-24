"""Exactly-once guarantees of the X-Idempotency-Key recovery queue.

No real Postgres is available in CI, so this module models the parts of
operation_idempotency that matter: per-connection uncommitted state, commit /
rollback, row locks that block other connections (READ COMMITTED re-read after the
lock is granted) and the conditional UPDATE/DELETE predicates. The fake refuses any
SQL shape it does not know, so dropping a lease or status predicate from the real
queries fails these tests instead of silently passing.
"""
from __future__ import annotations

import ast
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import APIRouter, Response
from fastapi.testclient import TestClient

from backend import main
from backend.core import idempotency


BACKEND = Path(__file__).resolve().parents[1]
KEY = "retry-key-0001"
PATH = "/user-product/transactions"


# --------------------------------------------------------------------------- fake DB

class FakeDatabase:
    def __init__(self):
        self.now = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
        self.ops: dict[tuple[str, str], dict] = {}
        self.ledger: list[dict] = []
        self.locks: dict[tuple[str, str], "FakeConnection"] = {}
        self.cond = threading.Condition()
        self.waiting = threading.Event()
        self.fail_complete = False

    def clock(self) -> str:
        # clock_timestamp(): strictly increasing, microsecond precision, serialized
        # to ISO text exactly like backend.core.database.serialize_row does.
        self.now += timedelta(microseconds=1)
        return self.now.isoformat()

    def advance(self, **delta):
        self.now += timedelta(**delta)

    def connect(self):
        return FakeConnection(self)


class Result:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.rowcount = len(self.rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


_DELETED = object()


class FakeConnection:
    def __init__(self, db: FakeDatabase):
        self.db = db
        self.staged_ops: dict[tuple[str, str], object] = {}
        self.staged_ledger: list[dict] = []
        self.held: set[tuple[str, str]] = set()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        if exc_type:
            self.rollback()
        self.close()

    # -- transaction control
    def commit(self):
        with self.db.cond:
            for pk, row in self.staged_ops.items():
                if row is _DELETED:
                    self.db.ops.pop(pk, None)
                else:
                    self.db.ops[pk] = row
            self.db.ledger.extend(self.staged_ledger)
            self._release()

    def rollback(self):
        with self.db.cond:
            self._release()

    def close(self):
        self.rollback()

    def _release(self):
        self.staged_ops, self.staged_ledger = {}, []
        for pk in self.held:
            self.db.locks.pop(pk, None)
        self.held = set()
        self.db.cond.notify_all()

    # -- locking / visibility
    def _lock(self, pk):
        with self.db.cond:
            while self.db.locks.get(pk) not in (None, self):
                self.db.waiting.set()
                if not self.db.cond.wait(timeout=5):
                    raise TimeoutError("fake row lock wait timed out")
            self.db.locks[pk] = self
            self.held.add(pk)

    def _row(self, pk):
        if pk in self.staged_ops:
            row = self.staged_ops[pk]
            return None if row is _DELETED else dict(row)
        row = self.db.ops.get(pk)
        return dict(row) if row else None

    # -- SQL
    def execute(self, query: str, params=()):
        sql = " ".join(query.split())
        if "operation_idempotency" in sql:
            return self._idempotency(sql, params)
        if sql.startswith("INSERT INTO fake_ledger"):
            self.staged_ledger.append({"account_id": params[0], "amount": params[1]})
            return Result([{"id": len(self.db.ledger) + len(self.staged_ledger)}])
        raise AssertionError(f"unexpected SQL: {sql}")

    def _idempotency(self, sql, params):
        db = self.db
        if sql.startswith("INSERT INTO operation_idempotency"):
            assert "clock_timestamp()" in sql and "ON CONFLICT(account_id,idempotency_key) DO NOTHING" in sql
            assert "RETURNING updated_at" in sql
            account, key, digest, method, path = params
            pk = (account, key)
            with db.cond:
                # A concurrent uncommitted INSERT of the same key blocks; an existing
                # row (even if locked by an UPDATE) does not.
                while (other := db.locks.get(pk)) not in (None, self) and pk in other.staged_ops and pk not in db.ops:
                    db.waiting.set()
                    db.cond.wait(timeout=5)
                if self._row(pk):
                    return Result([])
                db.locks[pk] = self
                self.held.add(pk)
            lease = db.clock()
            self.staged_ops[pk] = {
                "account_id": account, "idempotency_key": key, "request_hash": digest,
                "method": method, "path": path, "status": "processing",
                "response_status": None, "response_body": None,
                "updated_at": lease, "expires_at": db.now + timedelta(hours=24),
            }
            return Result([{"updated_at": lease}])

        if sql.startswith("SELECT request_hash,status"):
            assert sql.endswith("FOR UPDATE")
            pk = tuple(params)
            self._lock(pk)
            row = self._row(pk)
            if not row:
                return Result([])
            row["stale"] = datetime.fromisoformat(row["updated_at"]) < db.now - timedelta(minutes=2)
            row["expired"] = row["expires_at"] <= db.now
            return Result([row])

        if sql.startswith("UPDATE operation_idempotency SET status='processing'"):
            assert "updated_at=clock_timestamp()" in sql and "RETURNING updated_at" in sql
            pk = tuple(params)
            self._lock(pk)
            row = self._row(pk)
            lease = db.clock()
            row.update(status="processing", response_status=None, response_body=None,
                       updated_at=lease, expires_at=db.now + timedelta(hours=24))
            self.staged_ops[pk] = row
            return Result([{"updated_at": lease}])

        if sql.startswith("UPDATE operation_idempotency SET status='completed' WHERE"):
            # mark_applied: must be conditional on processing + lease, must not touch updated_at.
            assert "status='processing' AND updated_at=%s::timestamptz" in sql
            assert "updated_at=clock_timestamp()" not in sql and "updated_at=NOW()" not in sql
            account, key, lease = params
            pk = (account, key)
            self._lock(pk)
            row = self._row(pk)
            if not row or row["status"] != "processing" or row["updated_at"] != lease:
                return Result([])
            row["status"] = "completed"
            self.staged_ops[pk] = row
            return Result([{"idempotency_key": key}])

        if sql.startswith("UPDATE operation_idempotency SET status='completed',response_status"):
            assert "updated_at=%s::timestamptz AND status IN ('processing','completed')" in sql
            if db.fail_complete:
                raise RuntimeError("database went away")
            status_code, body, account, key, lease = params
            pk = (account, key)
            self._lock(pk)
            row = self._row(pk)
            if row and row["updated_at"] == lease and row["status"] in {"processing", "completed"}:
                row.update(status="completed", response_status=status_code,
                           response_body=json.loads(body), updated_at=db.clock())
                self.staged_ops[pk] = row
            return Result([])

        if sql.startswith("DELETE FROM operation_idempotency"):
            assert "status='processing' AND updated_at=%s::timestamptz" in sql
            account, key, lease = params
            pk = (account, key)
            self._lock(pk)
            row = self._row(pk)
            if row and row["status"] == "processing" and row["updated_at"] == lease:
                self.staged_ops[pk] = _DELETED
            return Result([])

        raise AssertionError(f"unexpected idempotency SQL: {sql}")


# --------------------------------------------------------------------------- app wiring

class Gate:
    """Lets a test pause the fake financial service at a precise point."""

    def __init__(self):
        self.pause_before_mark: threading.Event | None = None
        self.pause_before_commit: threading.Event | None = None
        self.reached = threading.Event()
        self.after_commit = None  # callable -> Response | raise
        self.fail_before_mark = False
        self.calls = 0


@pytest.fixture
def env(monkeypatch):
    db = FakeDatabase()
    gate = Gate()
    monkeypatch.setattr(idempotency, "get_connection", db.connect)
    accounts = {
        "token-a": {"id": 1, "account_id": "account-a", "workspace_id": "ws-a", "role": "user"},
        "token-b": {"id": 2, "account_id": "account-b", "workspace_id": "ws-b", "role": "user"},
    }
    monkeypatch.setattr(main, "authenticate_access_token", lambda token, **_: accounts[token])
    monkeypatch.setattr(main, "disabled_feature_for_request", lambda *_a, **_k: None)

    from backend.auth.current_user import get_current_account_id

    def fake_financial_write(payload: dict):
        # Same shape as the real services: one transaction, write, mark_applied, commit.
        gate.calls += 1
        with db.connect() as conn:
            conn.execute("INSERT INTO fake_ledger(account_id,amount) VALUES(%s,%s)",
                         (get_current_account_id(), payload.get("amount")))
            if gate.fail_before_mark:
                raise RuntimeError("failure before the write is bound")
            pause = gate.pause_before_mark
            if pause:
                gate.reached.set()
                assert pause.wait(5)
            idempotency.mark_applied(conn)
            pause = gate.pause_before_commit
            if pause:
                gate.reached.set()
                assert pause.wait(5)
            conn.commit()
        if gate.after_commit:
            return gate.after_commit()
        return {"status": "ok", "amount": payload.get("amount")}

    router = APIRouter()
    router.add_api_route(PATH, fake_financial_write, methods=["POST"])
    def non_financial(payload: dict):
        return {"status": "no-write"}

    router.add_api_route("/user-product/goals", non_financial, methods=["POST"])
    # Put the fake routes ahead of the real /user-product routes.
    saved_routes = list(main.app.router.routes)
    main.app.router.routes[:] = list(router.routes) + saved_routes
    try:
        yield db, gate
    finally:
        main.app.router.routes[:] = saved_routes


def body(amount=100) -> bytes:
    return json.dumps({"amount": amount}).encode()


def post(token="token-a", key=KEY, amount=100, path=PATH):
    client = TestClient(main.app, raise_server_exceptions=False)
    return client.post(path, content=body(amount), headers={
        "Authorization": f"Bearer {token}", "X-Idempotency-Key": key, "Content-Type": "application/json",
    })


def in_thread(fn):
    box = {}
    thread = threading.Thread(target=lambda: box.setdefault("value", fn()))
    thread.start()
    return thread, box


# --------------------------------------------------------------------------- tests

def test_normal_request_applies_once_and_stores_response(env):
    db, _ = env
    response = post()
    assert response.status_code == 200 and response.json() == {"status": "ok", "amount": 100}
    assert len(db.ledger) == 1
    row = db.ops[("account-a", KEY)]
    assert row["status"] == "completed" and row["response_status"] == 200


def test_same_key_twice_replays_stored_response(env):
    db, gate = env
    first, second = post(), post()
    assert second.status_code == 200 and second.json() == first.json()
    assert second.headers["X-Idempotency-Replayed"] == "true"
    assert len(db.ledger) == 1 and gate.calls == 1


def test_immediate_retry_while_processing_is_409(env):
    db, gate = env
    gate.pause_before_mark = threading.Event()
    thread, box = in_thread(post)
    assert gate.reached.wait(5)
    retry = post()
    assert retry.status_code == 409 and retry.headers["X-Idempotency-Status"] == "processing"
    gate.pause_before_mark.set()
    thread.join(5)
    assert box["value"].status_code == 200 and len(db.ledger) == 1


def test_stale_retry_after_crash_before_write_reruns_once(env):
    db, gate = env
    # First attempt reserved and the process died before any business write.
    reservation = idempotency.reserve_operation(account_id="account-a", key=KEY, method="POST", path=PATH,
                                                digest=idempotency.request_hash("POST", PATH, body()))
    assert reservation.state == "reserved"
    assert post().status_code == 409  # still fresh: another attempt may be alive
    db.advance(minutes=3)
    response = post()
    assert response.status_code == 200 and len(db.ledger) == 1
    assert post().headers["X-Idempotency-Replayed"] == "true" and len(db.ledger) == 1


def _crashed_after_commit(db, amount=100):
    """Reserve + business commit with mark_applied, then 'crash' before complete_operation."""
    reservation = idempotency.reserve_operation(
        account_id="account-a", key=KEY, method="POST", path=PATH,
        digest=idempotency.request_hash("POST", PATH, body(amount)),
    )
    token = idempotency.activate_operation(account_id="account-a", key=KEY, lease=reservation.lease)
    try:
        with db.connect() as conn:
            conn.execute("INSERT INTO fake_ledger(account_id,amount) VALUES(%s,%s)", ("account-a", amount))
            idempotency.mark_applied(conn)
            conn.commit()
    finally:
        idempotency.deactivate_operation(token)


@pytest.mark.parametrize("minutes_later", [0, 3, 60 * 23])
def test_crash_after_business_commit_replays_already_applied(env, minutes_later):
    db, gate = env
    _crashed_after_commit(db)
    db.advance(minutes=minutes_later)
    response = post()
    assert response.status_code == 200 and response.json() == {"status": "already_applied"}
    assert response.headers["X-Idempotency-Replayed"] == "true"
    assert len(db.ledger) == 1 and gate.calls == 0


def test_complete_operation_failure_after_commit_does_not_duplicate(env):
    db, gate = env
    db.fail_complete = True
    assert post().status_code == 200
    db.fail_complete = False
    retry = post()
    assert retry.status_code == 200 and retry.json() == {"status": "already_applied"}
    assert len(db.ledger) == 1 and gate.calls == 1


@pytest.mark.parametrize("response", [
    lambda: Response(content=b"not json", media_type="application/json"),
    lambda: {"blob": "x" * (70 * 1024)},
])
def test_unstorable_response_after_commit_does_not_duplicate(env, response):
    db, gate = env
    gate.after_commit = response
    assert post().status_code == 200
    gate.after_commit = None
    retry = post()
    assert retry.json() == {"status": "already_applied"} and len(db.ledger) == 1 and gate.calls == 1


def test_exception_after_handler_commit_does_not_duplicate(env):
    db, gate = env

    def boom():
        raise RuntimeError("post-commit failure")

    gate.after_commit = boom
    assert post().status_code == 500
    gate.after_commit = None
    retry = post()
    assert retry.json() == {"status": "already_applied"} and len(db.ledger) == 1 and gate.calls == 1


def test_slow_original_superseded_by_stale_reservation_rolls_back(env):
    db, gate = env
    slow_gate = threading.Event()
    gate.pause_before_mark = slow_gate
    slow, slow_box = in_thread(post)
    assert gate.reached.wait(5)  # original wrote (uncommitted) and stalls before mark_applied
    gate.pause_before_mark = None
    db.advance(minutes=3)
    retry = post()  # stale lease: re-reserved and applied by the retry
    assert retry.status_code == 200 and len(db.ledger) == 1
    slow_gate.set()
    slow.join(5)
    assert slow_box["value"].status_code == 409
    assert slow_box["value"].headers["X-Idempotency-Status"] == "processing"
    assert len(db.ledger) == 1 and gate.calls == 2
    # The winner's stored response survived the loser's cleanup and still replays.
    replay = post()
    assert replay.headers["X-Idempotency-Replayed"] == "true" and replay.json() == retry.json()


def test_original_marking_first_makes_stale_retry_wait_then_replay(env):
    db, gate = env
    commit_gate = threading.Event()
    gate.pause_before_commit = commit_gate
    original, original_box = in_thread(post)
    assert gate.reached.wait(5)  # marked (row locked), not committed yet
    gate.pause_before_commit = None
    db.advance(minutes=3)
    db.waiting.clear()
    retry, retry_box = in_thread(post)
    assert db.waiting.wait(5)  # the retry blocks on the row lock
    commit_gate.set()
    original.join(5)
    retry.join(5)
    assert original_box["value"].status_code == 200
    assert retry_box["value"].status_code == 200
    assert retry_box["value"].headers["X-Idempotency-Replayed"] == "true"
    assert len(db.ledger) == 1 and gate.calls == 1


def test_concurrent_same_key_single_effect(env):
    db, gate = env
    results = []
    barrier = threading.Barrier(4)

    def worker():
        barrier.wait()
        results.append(post())

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    codes = sorted(r.status_code for r in results)
    assert len(db.ledger) == 1 and gate.calls == 1
    assert codes.count(200) >= 1 and set(codes) <= {200, 409}


def test_same_key_in_two_accounts_is_independent(env):
    db, gate = env
    a, b = post("token-a"), post("token-b")
    assert a.status_code == b.status_code == 200
    assert "X-Idempotency-Replayed" not in b.headers
    assert [row["account_id"] for row in db.ledger] == ["account-a", "account-b"]
    # A different payload under the same key is only a conflict inside the same account.
    assert post("token-b", amount=999).status_code == 409
    assert post("token-a").headers["X-Idempotency-Replayed"] == "true"
    assert len(db.ledger) == 2


def test_same_key_other_payload_is_conflict_without_write(env):
    db, gate = env
    assert post(amount=100).status_code == 200
    conflict = post(amount=250)
    assert conflict.status_code == 409 and "X-Idempotency-Status" not in conflict.headers
    assert len(db.ledger) == 1 and gate.calls == 1


def test_non_financial_handler_keeps_stored_response_behaviour(env):
    db, _ = env
    first = post(path="/user-product/goals")
    assert first.json() == {"status": "no-write"}
    row = db.ops[("account-a", KEY)]
    assert row["status"] == "completed" and row["response_body"] == {"status": "no-write"}


def test_failure_before_mark_rolls_back_and_releases_the_key(env):
    db, gate = env
    gate.fail_before_mark = True
    assert post().status_code == 500
    assert ("account-a", KEY) not in db.ops and db.ledger == []
    gate.fail_before_mark = False
    assert post().status_code == 200 and len(db.ledger) == 1


def test_mark_applied_without_active_operation_is_noop():
    class Conn:
        def execute(self, *_a, **_k):
            raise AssertionError("must not touch the database")

    idempotency.mark_applied(Conn())


def test_mark_applied_raises_when_lease_was_superseded():
    db = FakeDatabase()
    db.ops[("acc", KEY)] = {"status": "processing", "updated_at": db.clock(), "expires_at": db.now}
    token = idempotency.activate_operation(account_id="acc", key=KEY, lease="2000-01-01T00:00:00+00:00")
    try:
        with pytest.raises(idempotency.OperationSuperseded):
            with db.connect() as conn:
                conn.execute("INSERT INTO fake_ledger(account_id,amount) VALUES(%s,%s)", ("acc", 1))
                idempotency.mark_applied(conn)
                conn.commit()
    finally:
        idempotency.deactivate_operation(token)
    assert db.ledger == [] and db.ops[("acc", KEY)]["status"] == "processing"


# --------------------------------------------------------------------------- static contract

MARKED_SERVICES = {
    "user_product/service.py": {
        "create_income", "update_income", "create_expense_entry", "update_expense", "create_user_debt",
        "update_user_debt", "pay_user_debt", "create_user_goal", "update_user_goal", "contribute_user_goal",
        "create_savings_plan", "update_savings_plan", "contribute_savings_plan", "create_user_transaction",
        "update_financial_situation",
    },
    "user_product/basic_service.py": {"save_guided_budget", "create_recurring_item", "update_recurring_item"},
}


def _calls(node):
    found = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            name = func.id if isinstance(func, ast.Name) else (
                f"{func.value.id}.{func.attr}" if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) else None
            )
            if name:
                found.append((child.lineno, child.col_offset, name))
    return sorted(found)


@pytest.mark.parametrize("relative", sorted(MARKED_SERVICES))
def test_every_recoverable_financial_write_marks_before_its_single_commit(relative):
    tree = ast.parse((BACKEND / relative).read_text(encoding="utf-8"))
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    for name in MARKED_SERVICES[relative]:
        calls = [call[2] for call in _calls(functions[name])]
        assert calls.count("conn.commit") == 1, f"{name}: exactly one financial commit expected"
        assert calls.count("mark_applied") == 1, f"{name}: mark_applied missing"
        commit_at = calls.index("conn.commit")
        assert calls[commit_at - 1] == "mark_applied", f"{name}: mark_applied must immediately precede commit"
        assert "conn.execute" not in calls[commit_at:], f"{name}: no writes after the commit"


def test_every_recoverable_route_calls_a_marked_service():
    tree = ast.parse((BACKEND / "user_product/routes.py").read_text(encoding="utf-8"))
    marked = set().union(*MARKED_SERVICES.values())
    checked = 0
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if not (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)):
                continue
            method = decorator.func.attr.upper()
            path = "/user-product" + decorator.args[0].value.replace("{", "").replace("}", "")
            if not idempotency.is_recoverable_operation(method, path):
                continue
            services = {name for stmt in node.body for *_, name in _calls(stmt)} - {"require_feature"}
            assert services and services <= marked, f"{method} {path} calls unmarked {services - marked}"
            checked += 1
    assert checked == 18
