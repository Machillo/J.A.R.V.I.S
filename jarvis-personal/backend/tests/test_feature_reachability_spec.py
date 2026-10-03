"""The feature reachability spec is well formed and agrees with the backend (master plan R1, P0.0).

`native/feature-reachability.json` is the single source of truth for what each plan can reach.
The iOS and Android reachability tests read the same file; these tests check its shape and that
every backend route it names exists with the gate the spec expects, and that the plan a gate
requires never exceeds the plans that use the route.
"""
import json
from pathlib import Path

import pytest

from backend.auth.saas import BUILTIN_FEATURE_MIN_PLAN
from backend.tests.route_gates import inventory

SPEC_PATH = Path(__file__).resolve().parents[2] / "native" / "feature-reachability.json"
SPEC = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
PLANS = ("free", "basic", "vip", "owner")
RANK = {"free": 1, "basic": 2, "vip": 3}
OWNER_GATES = ("internal_only", "router_roles:admin,owner", "roles:owner", "roles:admin,owner", "owner_service")


def _features():
    return SPEC["features"]


def test_the_spec_names_every_plan_and_only_known_states():
    assert tuple(SPEC["plans"]) == PLANS
    states = set(SPEC["states"])
    assert states == {"AVAILABLE", "VISIBLE_LOCKED", "OWNER_ONLY", "HIDDEN_BY_SECURITY", "HIDDEN_BY_PLAN"}
    ids = [feature["id"] for feature in _features()]
    assert len(ids) == len(set(ids)), "feature ids must be unique"
    for feature in _features():
        assert set(feature["plans"]) == set(PLANS), feature["id"]
        assert set(feature["plans"].values()) <= states, feature["id"]
        for platform, overrides in feature.get("platform_states", {}).items():
            assert platform in ("ios", "android") and set(overrides) <= set(PLANS), feature["id"]
            assert set(overrides.values()) <= states, feature["id"]


def test_every_feature_traces_to_a_decision():
    # R1: a feature's reachability changes only with an explicit decision.
    for feature in _features():
        assert feature.get("decision") in SPEC["decisions"], feature["id"]


def test_baseline_only_hidden_states_name_the_pr_that_resolves_them():
    for feature in _features():
        states = list(feature["plans"].values()) + [s for o in feature.get("platform_states", {}).values() for s in o.values()]
        if "HIDDEN_BY_PLAN" in states:
            assert feature.get("target") or feature.get("parity_gap"), f"{feature['id']}: HIDDEN_BY_PLAN needs a target PR"


def test_owner_only_features_are_owner_only_for_every_other_plan():
    for feature in _features():
        if "OWNER_ONLY" in feature["plans"].values():
            assert feature["plans"]["owner"] == "AVAILABLE", feature["id"]
            assert all(feature["plans"][plan] == "OWNER_ONLY" for plan in ("free", "basic", "vip")), feature["id"]


def test_each_feature_is_located_on_both_platforms_or_names_its_gap():
    for feature in _features():
        for platform in ("ios", "android"):
            location = feature.get(platform)
            assert location or feature.get(f"{platform}_gap"), f"{feature['id']}: no {platform} location and no gap"
            if location:
                assert location.get("tab_button") or location.get("tab"), feature["id"]


ROUTES = {(row["method"], row["path"]): row["gates"] for row in inventory()}
LINKS = [(feature["id"], link) for feature in _features() for link in feature.get("backend", [])]


@pytest.mark.parametrize(("feature", "link"), LINKS, ids=[f"{f}:{l['method']} {l['path']}" for f, l in LINKS])
def test_spec_backend_routes_exist_with_their_gate(feature, link):
    gates = ROUTES.get((link["method"], link["path"]))
    assert gates is not None, f"{feature}: {link['method']} {link['path']} disappeared from the backend"
    assert link["gate"] in gates, f"{feature}: {link['path']} gate changed: expected {link['gate']}, found {gates}"
    if link["gate"].startswith("feature:"):
        minimum = BUILTIN_FEATURE_MIN_PLAN[link["gate"].split(":", 1)[1]]
        for plan in link["used_by"]:
            assert RANK[plan] >= RANK[minimum], f"{feature}: {plan} uses {link['path']} but its gate needs {minimum}"


def test_owner_only_features_use_owner_gated_routes_only():
    for feature in _features():
        if feature["plans"]["free"] == "OWNER_ONLY":
            for link in feature.get("backend", []):
                assert link["gate"] in OWNER_GATES, f"{feature['id']}: {link['path']} is not owner-gated"
                assert not link["used_by"], f"{feature['id']}: an Owner-only route is used by a plan"
