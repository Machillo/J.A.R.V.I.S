"""DINCR has one administrative authority: the single verified Owner (master plan P0.2d).

The identities are Free, Basic and VIP (role "user"; the plan decides the tier) and the Owner.
There is no "admin": a stored legacy "admin" (or any other role) never gets a session, never
gets an administrative route, never gets Owner behavior and is never promoted, even with its
email in OWNER_EMAILS. Synthetic values only.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.auth import owner_role
from backend.auth.current_user import require_owner, reset_current_user, set_current_user
from backend.tests import get_route_harness as gate

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
INVENTORY = json.loads((BACKEND / "tests" / "fixtures" / "route_gate_inventory.json").read_text(encoding="utf-8"))
OWNER_GATES = {"internal_only", "router_roles:owner", "roles:owner", "owner_service"}
OWNER_EMAIL = "owner@example.test"

IDENTITIES = {
    "free": {"id": 50, "role": "user", "plan": "free"},
    "basic": {"id": 51, "role": "user", "plan": "basic"},
    "vip": {"id": 52, "role": "user", "plan": "vip"},
    "legacy admin": {"id": 53, "role": "admin", "plan": "vip"},
    "legacy viewer": {"id": 54, "role": "viewer", "plan": "vip"},
    "legacy member": {"id": 56, "role": "member", "plan": "vip"},
    "client-flag owner": {"id": 55, "role": "user", "plan": "vip", "is_owner": True, "access_source": "owner"},
    # Every account owns its personal workspace: data ownership, never DINCR authority.
    "workspace data owner": {"id": 57, "role": "user", "plan": "free", "workspace_role": "owner", "account_role": "user"},
    # A store review account: a normal user whose plan is a courtesy (plan only, never authority).
    "vip courtesy review account": {"id": 58, "role": "user", "plan": "vip", "access_source": "courtesy",
                                    "courtesy_note": "Cuenta demo para revisión de Google Play / App Store"},
}


# --- the canonical guard -------------------------------------------------------------------
def test_the_verified_owner_passes_the_owner_guard():
    token = set_current_user({"id": 1, "role": "owner", "plan": "vip"})
    try:
        assert require_owner()["role"] == "owner"
    finally:
        reset_current_user(token)


@pytest.mark.parametrize("name", list(IDENTITIES))
def test_no_plan_flag_or_legacy_role_passes_the_owner_guard(name):
    token = set_current_user(IDENTITIES[name])
    try:
        with pytest.raises(HTTPException) as error:
            require_owner()
        assert error.value.status_code == 403
    finally:
        reset_current_user(token)


def test_no_route_gate_names_admin_and_every_administrative_gate_is_the_owner():
    assert not [row for row in INVENTORY if any("admin" in g for g in row["gates"])]
    # Owner-gated GET routes are denied to regular accounts (the inventory's measured user_get).
    owner_gets = [row for row in INVENTORY if row["method"] == "GET" and set(row["gates"]) & OWNER_GATES]
    assert owner_gets and all(row.get("user_get") == "denied" for row in owner_gets)


# --- over HTTP: every Owner GET, and the administrative writes ---------------------------------
@pytest.fixture
def as_role(monkeypatch):
    for name, user in IDENTITIES.items():
        monkeypatch.setitem(gate.USERS, name, {**user, "account_id": "00000000-0000-4000-8000-0000000000c1",
                                               "workspace_id": "00000000-0000-4000-8000-00000000000c", "email": f"{name.replace(' ', '-')}@example.test"})
    return lambda role: gate.harness(monkeypatch, role)


OWNER_GET_PATHS = sorted({row["path"] for row in INVENTORY if row["method"] == "GET" and set(row["gates"]) & OWNER_GATES})


@pytest.mark.parametrize("role", ["legacy admin", "vip", "free"])
def test_every_owner_get_is_denied_to_a_legacy_admin_and_to_every_plan(monkeypatch, as_role, role):
    as_role(role)  # registers the identities
    results = gate.call_every_get(monkeypatch, role)
    allowed = [path for path in OWNER_GET_PATHS if results[path]["status"] != 403]
    assert allowed == [], f"{role} reached Owner GET routes: {allowed}"


def test_the_owner_keeps_every_owner_get(monkeypatch):
    # R1: nothing administrative became unreachable for the Owner.
    results = gate.call_every_get(monkeypatch, "owner")
    denied = [path for path in OWNER_GET_PATHS if results[path]["status"] == 403]
    assert denied == []


ADMINISTRATIVE_WRITES = [
    ("POST", "/auth/allowed-users", {"email": "new@example.test", "role": "admin", "status": "active"}),
    ("DELETE", "/auth/allowed-users/7", None),
    ("POST", "/notifications/subscribe", {"endpoint": "https://fcm.googleapis.com/x", "keys": {"p256dh": "a", "auth": "b"}}),
    ("POST", "/notifications/test", None),
    ("POST", "/email-monitor/statements/reconcile", {"statement_id": 1}),
    ("POST", "/jarvis/chat", {"message": "hola"}),
    ("POST", "/ask", {"question": "hola"}),
    ("POST", "/events", {"title": "x", "event_date": "2026-10-10"}),
    ("POST", "/finance/expenses", {"amount": 1000, "category": "Comida", "description": "x"}),
]


@pytest.mark.parametrize("role", ["legacy admin", "vip", "basic", "free"])
def test_administrative_writes_are_denied_to_a_legacy_admin_and_to_every_plan(as_role, role):
    with as_role(role) as (client, recorder):
        for method, path, body in ADMINISTRATIVE_WRITES:
            response = client.request(method, path, headers=gate.AUTH, json=body)
            assert response.status_code == 403, (role, method, path, response.status_code)
        assert recorder.writes == []


def test_the_owner_reaches_the_administrative_writes(as_role):
    with as_role("owner") as (client, _):
        for method, path, body in ADMINISTRATIVE_WRITES:
            assert client.request(method, path, headers=gate.AUTH, json=body).status_code != 403, (method, path)


# --- sessions: a stored legacy role is invalid, never promoted ---------------------------------
@pytest.mark.parametrize("stored", ["admin", "viewer", "member", "Admin", "superuser"])
def test_a_stored_role_other_than_user_or_owner_gets_no_session(monkeypatch, stored):
    monkeypatch.setenv("OWNER_EMAILS", OWNER_EMAIL)
    with pytest.raises(HTTPException) as error:
        owner_role.effective_role(stored, "someone@example.test")
    assert error.value.status_code == 403


def test_an_allowlisted_admin_is_never_the_owner(monkeypatch):
    # OWNER_EMAILS alone never makes anyone the Owner: only the stored Owner role with it.
    monkeypatch.setenv("OWNER_EMAILS", f"{OWNER_EMAIL},listed-admin@example.test")
    with pytest.raises(HTTPException):
        owner_role.effective_role("admin", "listed-admin@example.test")
    assert owner_role.session_role("admin", "listed-admin@example.test") == "user"
    assert owner_role.effective_role("user", "listed-admin@example.test") == "user"


@pytest.mark.parametrize("stored", ["user", "member", "admin", "viewer"])
def test_owner_emails_alone_never_promotes_a_non_owner_account(monkeypatch, stored):
    monkeypatch.setenv("OWNER_EMAILS", f"{OWNER_EMAIL},listed@example.test")
    try:
        assert owner_role.effective_role(stored, "listed@example.test") != "owner"
    except HTTPException as error:
        assert error.status_code == 403
    assert owner_role.session_role(stored, "listed@example.test") == "user"


def test_session_roles_for_user_and_owner(monkeypatch):
    monkeypatch.setenv("OWNER_EMAILS", OWNER_EMAIL)
    assert owner_role.effective_role("user", "a@example.test") == "user"
    assert owner_role.effective_role(None, "a@example.test") == "user"
    assert owner_role.effective_role("owner", OWNER_EMAIL) == "owner"
    with pytest.raises(HTTPException):
        owner_role.effective_role("owner", "unlisted@example.test")
    assert owner_role.session_role("owner", "unlisted@example.test") == "user"
    assert owner_role.session_role("viewer", OWNER_EMAIL) == "user"


# --- the allowlist API never creates an administrative role ----------------------------------
class _AllowlistConnection:
    def __init__(self):
        self.inserted = []

    def __enter__(self): return self
    def __exit__(self, *_a): return False
    def commit(self): pass

    def execute(self, query, params=()):
        if query.lstrip().startswith("INSERT INTO allowed_users"):
            self.inserted.append(params)

        class _R:
            lastrowid = 9
            def fetchone(self): return None
        return _R()


@pytest.mark.parametrize("role", ["admin", "viewer", "Admin", "superuser"])
def test_the_allowlist_api_refuses_any_role_but_user(monkeypatch, role):
    from backend.auth import service

    connection = _AllowlistConnection()
    monkeypatch.setattr(service, "get_connection", lambda: connection)
    assert service.create_allowed_user("new@example.test", role=role) == {"status": "ERROR", "message": "Rol inválido."}
    assert connection.inserted == []


def test_the_allowlist_api_never_creates_an_owner_and_still_creates_users(monkeypatch):
    from backend.auth import service

    connection = _AllowlistConnection()
    monkeypatch.setattr(service, "get_connection", lambda: connection)
    with pytest.raises(HTTPException) as error:
        service.create_allowed_user("new@example.test", role="owner")
    assert error.value.status_code == 403
    assert service.create_allowed_user("new@example.test", role="user")["status"] == "OK"
    assert connection.inserted == [("new@example.test", "user", "active")]


# --- product behavior: only the Owner -------------------------------------------------------
def test_only_the_owner_is_exempt_from_a_feature_kill_switch(monkeypatch):
    from backend.core import feature_flags

    monkeypatch.setattr(feature_flags, "_request_flags", lambda method, path: ["financial_writes"])
    monkeypatch.setattr(feature_flags, "load_feature_flags", lambda: {"financial_writes": {"flag_key": "financial_writes", "enabled": False,
                                                                                           "disabled_message_es": "x"}})
    assert feature_flags.disabled_feature_for_request("POST", "/user-product/x", {"role": "owner"}) is None
    for user in IDENTITIES.values():
        assert feature_flags.disabled_feature_for_request("POST", "/user-product/x", user) is not None, user


@pytest.mark.parametrize("module, function", [
    ("backend.sports.service", "enqueue_owner_sports_digest_notifications"),
    ("backend.notifications.service", "send_system_push"),
])
def test_owner_jobs_select_only_the_owner_role(module, function):
    import importlib
    import inspect

    source = inspect.getsource(getattr(importlib.import_module(module), function))
    assert "au.role = 'owner'" in source and "admin" not in source


# --- no runtime code recognises admin --------------------------------------------------------
ROLE_ADMIN = re.compile(r"""(?:==|!=|===|!==|\bin\b|IN\s*\(|contains\()[^\n]{0,40}["']admin["']|["']admin["'][^\n]{0,20}(?:==|===)""")
ALLOWED_RUNTIME = {
    # Fake servers of the native apps: the legacy value exists only to prove the apps refuse it.
    "native/ios/DincrKit/Sources/DincrCore/FixtureBackend.swift",
    "native/android/core/data/src/main/kotlin/com/dincr/data/FakeBackend.kt",
}


def _runtime_files():
    patterns = [("backend", "*.py"), ("frontend/src", "*.js"), ("frontend/src", "*.jsx"),
                ("native/ios/DincrKit/Sources", "*.swift"), ("native/ios/DINCR", "*.swift"),
                ("native/android/app/src/main", "*.kt"), ("native/android/core/data/src/main", "*.kt")]
    for folder, pattern in patterns:
        for path in (ROOT / folder).rglob(pattern):
            relative = path.relative_to(ROOT).as_posix()
            if "/tests/" in relative or Path(relative).name.startswith("test_") or relative in ALLOWED_RUNTIME:
                continue
            yield relative, path.read_text(encoding="utf-8", errors="replace")


def test_no_runtime_code_grants_anything_to_an_admin_role():
    offenders = [(relative, line.strip()[:120]) for relative, source in _runtime_files()
                 for line in source.splitlines() if ROLE_ADMIN.search(line)]
    assert offenders == []
    assert "require_roles(\"owner\", \"admin\")" not in (BACKEND / "main.py").read_text(encoding="utf-8")
    from backend.auth.service import VALID_ROLES
    assert VALID_ROLES == {"user"}


# --- DINCR Owner != workspace data owner -----------------------------------------------------
class _ContextConnection:
    def __init__(self, row):
        self.row = row

    def execute(self, query, params=()):
        assert "member_role" not in query, "membership has no role (P0.2d)"

        class _R:
            def __init__(self, row): self.row = row
            def fetchone(self): return self.row
        return _R(self.row)


def test_workspace_membership_and_ownership_carry_no_dincr_authority():
    # Every account owns its personal workspace and has an active membership of it: that is
    # data ownership and isolation, and the resolved context carries no role at all.
    from backend.auth.workspace_context import resolve_personal_workspace_context

    context = resolve_personal_workspace_context(_ContextConnection({
        "account_id": "00000000-0000-4000-8000-0000000000d1", "account_role": "user", "account_status": "active",
        "workspace_id": "00000000-0000-4000-8000-0000000000d2", "workspace_name": "Personal", "workspace_type": "personal",
        "workspace_status": "active", "membership_status": "active",
    }), 77)
    assert "workspace_role" not in context and "role" not in context
    token = set_current_user({"id": 77, "role": "user", **context})
    try:
        with pytest.raises(HTTPException) as error:
            require_owner()
        assert error.value.status_code == 403
    finally:
        reset_current_user(token)


def test_an_inactive_membership_still_closes_the_session():
    # workspace_members.status = 'active' stays required (P0.2d removes only the role).
    from backend.auth.workspace_context import resolve_personal_workspace_context

    with pytest.raises(HTTPException) as error:
        resolve_personal_workspace_context(_ContextConnection({
            "account_id": "a", "account_role": "user", "account_status": "active", "workspace_id": "w",
            "workspace_status": "active", "membership_status": "disabled"}), 1)
    assert error.value.status_code == 403


def test_no_runtime_code_reads_member_role_or_a_workspace_role():
    import backend.auth.current_user as current_user

    assert not hasattr(current_user, "get_current_workspace_role")
    offenders = [relative for relative, source in _runtime_files()
                 if relative.startswith("backend/") and re.search(r"member_role|workspace_role", source)]
    assert offenders == []

