"""Owner is an authenticated server role, never a plan or a client-side flag."""
from contextlib import contextmanager
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.auth import owner_bridge, service
from backend.auth.current_user import require_roles, reset_current_user, set_current_user
from backend.auth.models import PlanSelectionRequest
from backend.ai import routes as internal_ai_routes
from backend.integrations.internet_search import is_owner


@pytest.mark.parametrize("plan", ["free", "basic", "vip"])
def test_client_plan_or_owner_flag_cannot_grant_owner(plan):
    user = {"role": "user", "plan": plan, "isOwner": True, "email": "customer@example.com"}
    token = set_current_user(user)
    try:
        with pytest.raises(HTTPException) as exc:
            require_roles("owner")
        assert exc.value.status_code == 403
        assert is_owner() is False
        with pytest.raises(HTTPException) as internal_exc:
            internal_ai_routes.require_internal_role()
        assert internal_exc.value.status_code == 403
        with pytest.raises(ValidationError):
            PlanSelectionRequest(plan="owner")
    finally:
        reset_current_user(token)


def test_owner_cannot_be_provisioned_by_admin_request():
    with pytest.raises(HTTPException) as exc:
        service.create_allowed_user("customer@example.com", role="owner")
    assert exc.value.status_code == 403


def test_all_private_ai_routes_have_server_role_dependency():
    for route in internal_ai_routes.router.routes:
        assert internal_ai_routes.require_internal_role in [dependency.dependency for dependency in route.dependencies]


def test_valid_owner_retains_private_ai_access():
    token = set_current_user({"role": "owner", "plan": "vip"})
    try:
        assert internal_ai_routes.require_internal_role()["role"] == "owner"
        assert is_owner() is True
    finally:
        reset_current_user(token)


def test_bridge_issuance_rejects_non_owner_database_role(monkeypatch):
    uid = str(uuid4())

    class Connection:
        def execute(self, query, params):
            assert params == (uid,)
            return self
        def fetchone(self):
            return {"id": 7, "email": "customer@example.com", "supabase_user_id": uid, "role": "user", "status": "active"}

    @contextmanager
    def connection():
        yield Connection()

    monkeypatch.setattr(owner_bridge, "get_connection", connection)
    with pytest.raises(HTTPException) as exc:
        owner_bridge.verify_personal_owner(uid)
    assert exc.value.status_code == 403


def test_owner_bridge_rejects_client_forgery_and_respects_db_role(monkeypatch):
    uid = str(uuid4())
    monkeypatch.setattr(owner_bridge, "BRIDGE_API_KEY", "test-server-secret")
    row = {"id": 7, "email": "owner@example.com", "supabase_user_id": uid, "role": "owner", "status": "active"}

    class Connection:
        def execute(self, query, params):
            assert params == (7, uid)
            return self
        def fetchone(self):
            return row

    @contextmanager
    def connection():
        yield Connection()

    monkeypatch.setattr(owner_bridge, "get_connection", connection)
    monkeypatch.setattr(owner_bridge, "resolve_personal_workspace_context", lambda conn, account_id: {"workspace_id": "owner-workspace", "account_id": "owner-account"})
    issued = owner_bridge.issue_owner_bridge_session  # token issuance requires DB lookup; stub only that lookup
    monkeypatch.setattr(owner_bridge, "verify_personal_owner", lambda _: {"personal_supabase_user_id": uid, "personal_allowed_user_id": 7})
    signed = issued(uid)["token"]
    with pytest.raises(HTTPException) as exc:
        owner_bridge.authenticate_owner_bridge_token(signed + "tampered")
    assert exc.value.status_code == 401
    assert owner_bridge.authenticate_owner_bridge_token(signed)["role"] == "owner"
    row["role"] = "user"
    with pytest.raises(HTTPException) as exc:
        owner_bridge.authenticate_owner_bridge_token(signed)
    assert exc.value.status_code == 403
