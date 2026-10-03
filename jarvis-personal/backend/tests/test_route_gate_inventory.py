"""No route disappears, appears or changes its gate without a deliberate change (master plan R1, P0.0).

`fixtures/route_gate_inventory.json` is the reviewed inventory of every route: method, path, the
gate read from the code (backend/tests/route_gates.py) and, for GET routes, whether a regular
account is denied (403) or allowed when it calls it. A PR that removes or adds a route, changes a
plan or role gate, or opens an Owner GET to regular accounts fails here until the inventory is
regenerated on purpose (`python -m backend.tests.route_gates --write`) and reviewed in the diff.
"""
import json

from backend.tests.get_route_harness import call_every_get
from backend.tests.route_gates import INVENTORY, inventory

OWNER_GATES = {"internal_only", "router_roles:admin,owner", "roles:owner", "roles:admin,owner", "owner_service"}


def _key(row):
    return f"{row['method']} {row['path']}"


def _reviewed():
    return {_key(row): row for row in json.loads(INVENTORY.read_text(encoding="utf-8"))}


def test_every_route_and_gate_matches_the_reviewed_inventory():
    reviewed, current = _reviewed(), {_key(row): row for row in inventory()}
    missing = sorted(set(reviewed) - set(current))
    added = sorted(set(current) - set(reviewed))
    changed = sorted(key for key in set(reviewed) & set(current) if reviewed[key]["gates"] != current[key]["gates"])
    assert not missing, f"routes removed without updating the inventory (R1): {missing}"
    assert not added, f"new routes must be added to the reviewed inventory with their gate: {added}"
    assert not changed, "gates changed: " + "; ".join(f"{k}: {reviewed[k]['gates']} -> {current[k]['gates']}" for k in changed)


def test_regular_accounts_are_denied_exactly_the_reviewed_get_routes(monkeypatch):
    reviewed = _reviewed()
    results = call_every_get(monkeypatch, "user")
    expected_denied = {row["path"] for row in reviewed.values() if row["method"] == "GET" and row.get("user_get") == "denied"}
    denied = {path for path, result in results.items() if result["status"] == 403}
    opened = sorted(expected_denied - denied)
    newly_denied = sorted(denied - expected_denied)
    assert not opened, f"Owner GET routes now reachable by a regular account: {opened}"
    assert not newly_denied, f"public GET routes now denied to regular accounts (capability hidden?): {newly_denied}"


def test_routes_with_an_owner_gate_are_denied_to_regular_accounts():
    for row in _reviewed().values():
        if row["method"] == "GET" and OWNER_GATES & set(row["gates"]):
            assert row.get("user_get") == "denied", f"{_key(row)} has an Owner gate but is not denied"
