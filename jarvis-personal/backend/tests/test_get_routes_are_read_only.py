"""GET = READ, for every GET route of the app (CLAUDE.md §4.C; master plan R1, P0.0).

Every GET route runs, as the Owner and as a regular account, against a database that answers
like a brand-new account and records every write (backend/tests/get_route_harness.py). A write
fails the gate unless `fixtures/read_purity_exceptions.json` lists that route and table with the
reason and the PR that removes it. An exception that no longer writes fails too, so the list
only shrinks. Routes the harness cannot run to a response are listed there as well, so a new
one is noticed instead of silently escaping the gate.
"""
import json
from pathlib import Path

from backend.tests.get_route_harness import call_every_get

EXCEPTIONS_PATH = Path(__file__).parent / "fixtures" / "read_purity_exceptions.json"
EXCEPTIONS = json.loads(EXCEPTIONS_PATH.read_text(encoding="utf-8"))


def _allowed():
    allowed = {}
    for entry in EXCEPTIONS["known_get_writes"]:
        assert entry.get("reason") and entry.get("removed_by"), f"{entry['path']}: every exception names its reason and PR"
        allowed[entry["path"]] = {tuple(write) for write in entry["writes"]}
    return allowed


def test_no_get_route_writes_except_the_listed_temporary_exceptions(monkeypatch):
    allowed = _allowed()
    observed = {}
    for role in ("owner", "user"):
        for path, result in call_every_get(monkeypatch, role).items():
            observed.setdefault(path, set()).update(tuple(write) for write in result["writes"])
    unexpected = {path: sorted(writes - allowed.get(path, set())) for path, writes in observed.items() if writes - allowed.get(path, set())}
    stale = {path: sorted(writes - observed.get(path, set())) for path, writes in allowed.items() if writes - observed.get(path, set())}
    assert not unexpected, f"GET routes that write (fix them, or list them with a reason and the PR that removes the write): {unexpected}"
    assert not stale, f"exceptions that no longer write: remove them from read_purity_exceptions.json: {stale}"


def test_every_exception_is_one_exact_route_with_its_risk_and_pr():
    from backend.tests.get_route_harness import get_routes

    routes = set(get_routes())
    for entry in EXCEPTIONS["known_get_writes"]:
        assert entry["path"] in routes, f"{entry['path']}: not a GET route (no wildcards)"
        assert entry.get("risk") and entry.get("removed_by") and entry.get("reason") and entry.get("scope"), entry["path"]
    paths = [entry["path"] for entry in EXCEPTIONS["not_executable_in_harness"]]
    assert len(paths) == len(set(paths)), "each non-runnable route is listed once"
    for entry in EXCEPTIONS["not_executable_in_harness"]:
        assert entry["path"] in routes and entry.get("reason"), f"{entry['path']}: exact GET route with a concrete reason"


def test_the_routes_the_harness_cannot_run_are_baselined_by_identity(monkeypatch):
    # A route that errors on an empty database escapes the gate, so the set is frozen: a new one
    # fails until it is classified here; one that runs again must be removed (it is now verified).
    unreachable = {path for path, result in call_every_get(monkeypatch, "owner").items() if result["status"] >= 500}
    known = {entry["path"] for entry in EXCEPTIONS["not_executable_in_harness"]}
    assert not unreachable - known, f"new GET routes the harness cannot run (classify them): {sorted(unreachable - known)}"
    assert not known - unreachable, f"routes that run again: remove them from not_executable_in_harness: {sorted(known - unreachable)}"
