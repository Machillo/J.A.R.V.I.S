"""P0.2: lifecycle, deterioration and advisor reads are pure; the daily job keeps their history.

Synthetic inputs (backend/tests/p02_parity_harness.py) replace the input services only; the
calculations run unchanged and are compared with the responses the code gave before P0.2
(fixtures/p02_read_parity_golden.json). The real-PostgreSQL side (eligibility, idempotency,
concurrency, DAY1 -> DAY2 and A -> A -> B end to end) is in test_daily_financial_history_pg.py.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.tests import p02_parity_harness as h

GOLDEN = json.loads((Path(__file__).resolve().parent / "fixtures" / "p02_read_parity_golden.json").read_text(encoding="utf-8"))
GOLDEN_HASH = GOLDEN["advisor_strategy"]["__strategy_hash"]


def _writes(store):
    return [s for s in store["statements"] if s.upper().startswith(("INSERT", "UPDATE", "DELETE"))]


def _read(scenario):
    from backend.advisor.core import build_advisor_strategy
    from backend.ai.premium_orchestrator import get_current_strategy_summary
    from backend.finance.deterioration import get_financial_deterioration
    from backend.financial_lifecycle.state import build_financial_state

    if scenario.startswith("deterioration"):
        return get_financial_deterioration()
    if scenario == "advisor_strategy":
        full = build_advisor_strategy()
        out = {key: value for key, value in full.items() if key != "persistence"}
        out["__strategy_hash"] = full["persistence"]["strategy_hash"]
        return out
    if scenario == "lifecycle_state":
        return build_financial_state()
    return get_current_strategy_summary()


SCENARIOS = ["deterioration_with_previous", "deterioration_baseline", "advisor_strategy", "lifecycle_state", "premium_strategy_summary"]


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_reads_match_the_pre_p02_responses_and_write_nothing(monkeypatch, scenario):
    store = h.new_store(previous=scenario != "deterioration_baseline")
    h.install(monkeypatch, store)
    out = json.loads(json.dumps(h.without_volatile(_read(scenario)), default=str))
    assert out == GOLDEN[scenario]              # same signals, scores, strategy, recommendations and hash
    assert _writes(store) == [] and store["commits"] == 0


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_two_consecutive_reads_leave_the_database_identical(monkeypatch, scenario):
    store = h.new_store()
    h.install(monkeypatch, store)
    before = copy.deepcopy({key: store[key] for key in ("health", "current", "history")})
    _read(scenario)
    _read(scenario)
    assert {key: store[key] for key in ("health", "current", "history")} == before
    assert store["commits"] == 0


def test_the_persistence_block_reports_without_persisting(monkeypatch):
    from backend.advisor.core import build_advisor_strategy

    store = h.new_store()
    h.install(monkeypatch, store)
    first = build_advisor_strategy()["persistence"]
    assert first == {"strategy_hash": GOLDEN_HASH, "changed": True, "persisted": False}
    store["current"][h.WORKSPACE] = GOLDEN_HASH          # the job stored this strategy
    assert build_advisor_strategy()["persistence"] == {"strategy_hash": GOLDEN_HASH, "changed": False, "persisted": False}
    store["current"][h.WORKSPACE] = "another-hash"
    assert build_advisor_strategy()["persistence"]["changed"] is True
    assert _writes(store) == [] and store["commits"] == 0


def test_the_strategy_history_read_writes_and_commits_nothing(monkeypatch):
    from backend.advisor import core

    store = h.new_store()
    h.install(monkeypatch, store)
    store["statements"].clear()

    class _HistoryConnection(h.FakeConnection):
        def execute(self, query, params=()):
            sql = " ".join(query.split())
            if "FROM advisor_strategy_history" in sql:
                self.store["statements"].append(sql)
                return h._Result(rows=[{"id": 1, "advisor_version": "v", "strategy_hash": "a", "strategy": {}, "created_at": "t"}])
            return super().execute(query, params)

    monkeypatch.setattr(core, "get_connection", lambda: _HistoryConnection(store))
    assert core.get_strategy_history(5)[0]["strategy_hash"] == "a"
    assert _writes(store) == [] and store["commits"] == 0


# Explicit persistence: the health observation and the strategy.
DAY1, DAY2 = dt.date(2026, 9, 14), dt.date(2026, 9, 15)
WORSE_DEBTS = [{**h.DEBTS[0], "remaining_amount": 1_600_000}, h.DEBTS[1]]
WORSE_ACCOUNTS = [{**h.ACCOUNTS[0], "balance_crc": 150_000}, h.ACCOUNTS[1]]


def test_a_daily_observation_lets_the_next_days_read_prove_decline(monkeypatch):
    from backend.finance.deterioration import get_financial_deterioration, record_daily_health_snapshot

    store = h.new_store(previous=False)
    h.install(monkeypatch, store, today=DAY1)
    record_daily_health_snapshot(DAY1)                   # DAY 1: the job records the observation
    assert list(store["health"]) == [(h.WORKSPACE, DAY1)]
    assert get_financial_deterioration(DAY1)["context"]["previous_snapshot_date"] is None

    h.install(monkeypatch, store, today=DAY2, debts=WORSE_DEBTS, accounts=WORSE_ACCOUNTS)
    store["statements"].clear()
    report = get_financial_deterioration(DAY2)            # DAY 2: the condition deteriorated
    codes = {signal["code"] for signal in report["signals"]}
    assert report["context"]["previous_snapshot_date"] == str(DAY1)
    assert {"liquidity_history", "debt_history"} <= codes
    assert report["health"] == "deteriorating"
    assert _writes(store) == []                          # the read compared, and stored nothing


def test_the_same_day_observation_is_one_row_however_many_runs(monkeypatch):
    from backend.finance.deterioration import record_daily_health_snapshot

    store = h.new_store(previous=False)
    h.install(monkeypatch, store, today=DAY1)
    for _ in range(3):
        record_daily_health_snapshot(DAY1)
    assert list(store["health"]) == [(h.WORKSPACE, DAY1)]
    assert all("ON CONFLICT(workspace_id,snapshot_date) DO UPDATE" in s for s in _writes(store))


def test_strategy_history_grows_only_when_the_strategy_changes(monkeypatch):
    from backend.advisor.core import _persist_strategy, build_advisor_strategy, compute_advisor_strategy

    store = h.new_store()
    h.install(monkeypatch, store)
    first = _persist_strategy(compute_advisor_strategy())            # run 1: strategy A
    assert first == {"strategy_hash": GOLDEN_HASH, "changed": True, "persisted": True}
    assert store["history"] == [(h.WORKSPACE, GOLDEN_HASH)] and store["current"][h.WORKSPACE] == GOLDEN_HASH
    assert _persist_strategy(compute_advisor_strategy())["changed"] is False   # run 2: A again
    assert len(store["history"]) == 1

    h.install(monkeypatch, store, debts=WORSE_DEBTS)                    # the strategy changes: B
    second = _persist_strategy(compute_advisor_strategy())
    assert second["changed"] is True and second["strategy_hash"] != GOLDEN_HASH
    assert [item[1] for item in store["history"]] == [GOLDEN_HASH, second["strategy_hash"]]
    assert store["current"][h.WORKSPACE] == second["strategy_hash"]

    store["statements"].clear()
    read = build_advisor_strategy()                                     # GET computes B, writes nothing
    assert read["persistence"] == {"strategy_hash": second["strategy_hash"], "changed": False, "persisted": False}
    assert _writes(store) == []


def test_the_strategy_write_takes_the_workspace_lock_before_reading(monkeypatch):
    from backend.advisor.core import _persist_strategy, compute_advisor_strategy

    store = h.new_store()
    h.install(monkeypatch, store)
    store["statements"].clear()
    _persist_strategy(compute_advisor_strategy())
    statements = [s for s in store["statements"] if "advisor" in s.lower() or "pg_advisory" in s.lower()]
    assert statements[0].startswith("SELECT pg_advisory_xact_lock")
    assert statements[1].startswith("SELECT strategy_hash FROM advisor_current_strategy")


def test_the_explicit_lifecycle_snapshot_still_records_the_health_observation(monkeypatch):
    from backend.financial_lifecycle import snapshots

    recorded = []
    monkeypatch.setattr(snapshots, "record_daily_health_snapshot", lambda: recorded.append(True) or {"health": "stable"})
    monkeypatch.setattr(snapshots, "build_financial_state", lambda: {"period": "2026-09", "schema_version": "financial-state-v1"})
    monkeypatch.setattr(snapshots, "get_current_workspace_id", lambda: h.WORKSPACE)
    monkeypatch.setattr(snapshots, "get_current_account_id", lambda: "00000000-0000-4000-8000-0000000000b1")
    monkeypatch.setattr(snapshots, "build_proactive_advisor", lambda **kw: {"alerts": []})
    statements = []

    class _SnapshotConnection:
        def __enter__(self): return self
        def __exit__(self, *_a): return False
        def commit(self): statements.append("COMMIT")

        def execute(self, query, params=()):
            statements.append(" ".join(query.split())[:40])
            if query.lstrip().startswith("SELECT"):
                return h._Result(one=None)
            return h._Result(one={"id": 1, "snapshot_date": "2026-09-15", "captured_at": "t"})

    monkeypatch.setattr(snapshots, "get_connection", lambda: _SnapshotConnection())
    result = snapshots.capture_financial_snapshot()
    assert result["status"] == "OK" and recorded == [True]
    assert any(s.startswith("INSERT INTO financial_state_snapshots") for s in statements) and "COMMIT" in statements


# The daily job: identity per workspace, isolation, failures.
WS_A, WS_B, WS_C = (f"00000000-0000-4000-8000-0000000000c{i}" for i in (1, 2, 3))


def _identity(workspace, role="user"):
    return {"id": 10, "account_id": workspace.replace("c", "d"), "workspace_id": workspace, "role": role, "status": "active"}


def _job(monkeypatch, identities, *, failing=None):
    from backend.advisor import core
    from backend.auth import current_user
    from backend.finance import daily_history, deterioration

    store = h.new_store(previous=False)
    h.install(monkeypatch, store, today=DAY1)
    for module in (deterioration, core):   # the real identity of each workspace, not the harness constant
        monkeypatch.setattr(module, "get_current_workspace_id", current_user.get_current_workspace_id)
    if failing:
        original = deterioration.list_account_balances

        def balances():
            if current_user.get_current_workspace_id() == failing:
                raise RuntimeError("synthetic failure")
            return original()
        monkeypatch.setattr(deterioration, "list_account_balances", balances)
    monkeypatch.setattr(daily_history, "get_connection", lambda: h.FakeConnection(store))
    monkeypatch.setattr(daily_history, "eligible_workspaces", lambda conn: [dict(item) for item in identities])
    return daily_history.run_daily_financial_history(DAY1), store


def test_the_job_records_each_workspace_under_its_own_identity(monkeypatch):
    result, store = _job(monkeypatch, [_identity(WS_A), _identity(WS_B, "owner"), _identity(WS_C, "admin")])
    assert result == {"status": "OK", "date": "2026-09-14", "eligible": 3, "recorded": 3, "strategy_changed": 2, "failed": 0}
    assert sorted(store["health"]) == [(WS_A, DAY1), (WS_B, DAY1), (WS_C, DAY1)]
    # The strategy is kept only where reads kept it (Owner, admin); a VIP gets no new strategy data.
    assert sorted(store["current"]) == [WS_B, WS_C] and sorted(item[0] for item in store["history"]) == [WS_B, WS_C]
    from backend.finance.category_catalog import owner_context
    assert owner_context() is False                     # no identity leaks out of the job


def test_a_workspace_failing_before_any_write_writes_nothing_and_never_stops_the_others(monkeypatch):
    result, store = _job(monkeypatch, [_identity(WS_A), _identity(WS_B), _identity(WS_C)], failing=WS_B)
    assert result["eligible"] == 3 and result["recorded"] == 2 and result["failed"] == 1
    assert sorted(store["health"]) == [(WS_A, DAY1), (WS_C, DAY1)]
    assert WS_B not in store["current"] and all(item[0] != WS_B for item in store["history"])


def test_a_failure_after_the_health_observation_leaves_only_that_idempotent_row(monkeypatch):
    # The health observation commits on its own; a strategy failure afterwards counts the
    # workspace as failed and stores no strategy. A rerun the same day converges on one row.
    from backend.advisor import core
    from backend.finance import daily_history

    monkeypatch.setattr(daily_history, "compute_advisor_strategy", lambda: (_ for _ in ()).throw(RuntimeError("synthetic")))
    result, store = _job(monkeypatch, [_identity(WS_A, "owner")])
    assert result["failed"] == 1 and result["recorded"] == 0
    assert list(store["health"]) == [(WS_A, DAY1)] and store["current"] == {} and store["history"] == []
    monkeypatch.setattr(daily_history, "compute_advisor_strategy", core.compute_advisor_strategy)
    again = daily_history.run_daily_financial_history(DAY1)
    assert again["failed"] == 0 and list(store["health"]) == [(WS_A, DAY1)] and len(store["history"]) == 1


def test_repeated_runs_of_the_same_day_add_no_history(monkeypatch):
    from backend.finance import daily_history

    result, store = _job(monkeypatch, [_identity(WS_A, "owner")])
    again = daily_history.run_daily_financial_history(DAY1)
    assert again["strategy_changed"] == 0 and again["recorded"] == 1
    assert len(store["history"]) == 1 and list(store["health"]) == [(WS_A, DAY1)]


def test_the_job_logs_no_financial_data(monkeypatch, caplog):
    result, _ = _job(monkeypatch, [_identity(WS_A), _identity(WS_B)], failing=WS_B)
    assert result["failed"] == 1
    text = caplog.text
    assert "RuntimeError" in text and WS_B not in text and "350000" not in text and "synthetic failure" not in text


def test_an_overlapping_run_does_nothing(monkeypatch):
    from backend.finance import daily_history

    result, store = _job(monkeypatch, [_identity(WS_A, "owner")])
    store["run_locked"] = True                               # another run holds the guard
    before = (dict(store["health"]), dict(store["current"]), list(store["history"]))
    assert daily_history.run_daily_financial_history(DAY1) == {"status": "ALREADY_RUNNING", "date": "2026-09-14"}
    assert (dict(store["health"]), dict(store["current"]), list(store["history"])) == before


def test_the_cron_answers_409_while_a_run_is_in_progress(monkeypatch):
    from backend.finance import daily_history_routes

    monkeypatch.setenv("NOTIFICATION_CRON_SECRET", "synthetic-secret")
    monkeypatch.setattr(daily_history_routes, "run_daily_financial_history", lambda: {"status": "ALREADY_RUNNING", "date": "2026-09-14"})
    with pytest.raises(HTTPException) as error:
        daily_history_routes.financial_history_cron("synthetic-secret")
    assert error.value.status_code == 409


# Cron authorization: the existing /notifications/cron mechanism.
def test_the_cron_fails_closed_without_a_configured_secret(monkeypatch):
    from backend.finance import daily_history_routes

    monkeypatch.delenv("NOTIFICATION_CRON_SECRET", raising=False)
    monkeypatch.delenv("EMAIL_MONITOR_CRON_SECRET", raising=False)
    monkeypatch.setattr(daily_history_routes, "run_daily_financial_history", lambda: pytest.fail("must not run"))
    with pytest.raises(HTTPException) as error:
        daily_history_routes.financial_history_cron("anything")
    assert error.value.status_code == 503


@pytest.mark.parametrize("supplied", [None, "", "wrong-secret", "s\xffcret"])
def test_the_cron_rejects_a_missing_or_wrong_secret(monkeypatch, supplied):
    from backend.finance import daily_history_routes

    monkeypatch.setenv("NOTIFICATION_CRON_SECRET", "synthetic-secret")
    monkeypatch.setattr(daily_history_routes, "run_daily_financial_history", lambda: pytest.fail("must not run"))
    with pytest.raises(HTTPException) as error:
        daily_history_routes.financial_history_cron(supplied)
    assert error.value.status_code == 403


def test_the_cron_runs_with_the_right_secret_and_takes_no_workspace_from_the_caller(monkeypatch):
    import inspect
    from backend.finance import daily_history_routes

    monkeypatch.setenv("NOTIFICATION_CRON_SECRET", "synthetic-secret")
    monkeypatch.setattr(daily_history_routes, "run_daily_financial_history",
                        lambda: {"status": "OK", "date": "2026-09-14", "eligible": 1, "recorded": 1, "strategy_changed": 0, "failed": 0})
    assert daily_history_routes.financial_history_cron("synthetic-secret")["recorded"] == 1
    assert list(inspect.signature(daily_history_routes.financial_history_cron).parameters) == ["x_cron_secret"]


def test_the_cron_route_is_public_only_behind_its_secret(monkeypatch):
    from fastapi.testclient import TestClient
    from backend import main

    monkeypatch.setenv("NOTIFICATION_CRON_SECRET", "synthetic-secret")
    response = TestClient(main.app).post("/financial-history/cron", headers={"X-Cron-Secret": "wrong"})
    assert response.status_code == 403                 # reaches the secret check, never runs the job
    assert main._is_public_path("/financial-history/cron")


def test_the_job_with_the_real_finance_services_writes_only_the_history_tables(monkeypatch):
    # No input is stubbed here: the job runs every real finance service over the recording
    # database of the P0.0 GET gate (an empty, migrated database). Any write outside the three
    # history tables fails, whichever service it comes from.
    import socket
    from backend.core import database
    from backend.finance import daily_history
    from backend.tests import get_route_harness as gate

    recorder = gate.Recorder()
    monkeypatch.setattr(database.PostgresConnection, "__init__", lambda self: setattr(self, "_released", False))
    def execute(self, query, params=()):
        if "pg_try_advisory_xact_lock" in query:   # the run guard is free
            return database.PostgresCursorResult(rows=[{"acquired": True}], rowcount=1)
        return recorder.execute(query)
    monkeypatch.setattr(database.PostgresConnection, "execute", execute)
    for name in ("commit", "rollback", "close"):
        monkeypatch.setattr(database.PostgresConnection, name, lambda self: None)
    monkeypatch.setattr(socket.socket, "connect", gate._refuse_network)
    identities = [{**{k: gate.USERS[role][k] for k in ("id", "account_id", "workspace_id", "role")}, "status": "active"}
                  for role in ("user", "owner")]
    monkeypatch.setattr(daily_history, "eligible_workspaces", lambda conn: [dict(item) for item in identities])

    result = daily_history.run_daily_financial_history(DAY1)
    assert result["failed"] == 0 and result["recorded"] == 2
    tables = {table for _, table in recorder.writes}
    assert tables == {"financial_health_snapshots", "advisor_current_strategy", "advisor_strategy_history"}
