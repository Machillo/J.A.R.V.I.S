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


def test_routes_the_harness_cannot_run_are_known(monkeypatch):
    # A route that errors on an empty database escapes the gate: keep that set explicit.
    unreachable = {path for path, result in call_every_get(monkeypatch, "owner").items() if result["status"] >= 500}
    known = {entry["path"] for entry in EXCEPTIONS["not_executable_in_harness"] if entry.get("reason")}
    assert unreachable <= known, f"GET routes the harness can no longer run (they escape the gate): {sorted(unreachable - known)}"
