"""Route and gate inventory of the FastAPI app (functional protection gates, R1).

Reads the gate of every route from the app itself, deterministically:

- ``internal_only``: mounted with ``main.INTERNAL_ONLY`` (the verified-Owner router dependency);
- ``router_roles:<roles>``: a router-level ``require_roles(...)`` / ``require_owner()`` dependency;
- ``feature:<code>``: the endpoint calls ``require_feature("<code>")``;
- ``roles:<roles>``: the endpoint calls ``require_roles(...)`` (``require_owner()`` is ``roles:owner``);
- ``owner_service``: the endpoint calls an Owner guard helper (``_require_owner_user``, ``_owner_only``);
- ``public``: none of the above (auth middleware only, or explicitly public routes).

For GET routes the written inventory also records ``user_get``: ``denied`` when a regular
account gets 403 (measured by calling the route, see get_route_harness.py), else ``allowed``.
That catches guards the source scan cannot see (e.g. a role check inside a service).

The inventory is compared against ``fixtures/route_gate_inventory.json`` by
``test_route_gate_inventory.py``. Regenerate it only for a deliberate change:
``python -m backend.tests.route_gates --write`` (from ``jarvis-personal``).
"""
from __future__ import annotations

import inspect
import json
import re
import sys
from pathlib import Path

INVENTORY = Path(__file__).parent / "fixtures" / "route_gate_inventory.json"
_FEATURE = re.compile(r"require_feature\(\s*[\"'](\w+)[\"']")
_ROLES = re.compile(r"require_roles\(([^)]*)\)")
_OWNER_SERVICE = re.compile(r"_require_owner_user\(|_owner_only\(")
# The canonical verified-Owner guard (backend/auth/current_user.py): require_roles("owner").
_REQUIRE_OWNER = re.compile(r"\brequire_owner\(\)")


def _roles(arguments: str) -> str:
    return ",".join(sorted(re.findall(r"[\"'](\w+)[\"']", arguments)))


def _source(function) -> str:
    try:
        return inspect.getsource(inspect.unwrap(function))
    except (OSError, TypeError):
        return ""


def gates_of(route, internal_only) -> list[str]:
    gates: list[str] = []
    for dependency in getattr(route, "dependencies", []) or []:
        if dependency is internal_only:
            gates.append("internal_only")
            continue
        dependency_source = _source(dependency.dependency)
        found = _ROLES.search(dependency_source)
        if found:
            gates.append(f"router_roles:{_roles(found.group(1))}")
        elif _REQUIRE_OWNER.search(dependency_source) or getattr(dependency.dependency, "__name__", "") == "require_owner":
            gates.append("router_roles:owner")
    source = _source(route.endpoint)
    gates += [f"feature:{code}" for code in sorted(set(_FEATURE.findall(source)))]
    gates += [f"roles:{_roles(found)}" for found in sorted(set(_ROLES.findall(source)))]
    if _REQUIRE_OWNER.search(source):
        gates.append("roles:owner")
    if _OWNER_SERVICE.search(source):
        gates.append("owner_service")
    return sorted(set(gates)) or ["public"]


def inventory() -> list[dict]:
    from backend import main

    rows = []
    for route in main.app.routes:
        methods = sorted((getattr(route, "methods", None) or set()) - {"HEAD", "OPTIONS"})
        path = getattr(route, "path", "")
        if not methods or not hasattr(route, "endpoint") or path.startswith(("/docs", "/redoc", "/openapi")):
            continue
        for method in methods:
            rows.append({"method": method, "path": path, "gates": gates_of(route, main.INTERNAL_ONLY[0])})
    return sorted(rows, key=lambda row: (row["path"], row["method"]))


def with_user_access(rows: list[dict]) -> list[dict]:
    import pytest

    from backend.tests.get_route_harness import call_every_get

    with pytest.MonkeyPatch.context() as monkeypatch:
        results = call_every_get(monkeypatch, "user")
    for row in rows:
        if row["method"] == "GET":
            row["user_get"] = "denied" if results[row["path"]]["status"] == 403 else "allowed"
    return rows


def main(argv: list[str]) -> int:
    rows = with_user_access(inventory())
    if "--write" in argv:
        INVENTORY.parent.mkdir(exist_ok=True)
        INVENTORY.write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {len(rows)} routes to {INVENTORY}")
    else:
        print(json.dumps(rows, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
