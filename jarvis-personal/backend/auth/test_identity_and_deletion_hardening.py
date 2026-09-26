"""Stable Supabase identity binding and retry-safe account deletion.

Everything here is synthetic: example.com addresses and made-up UUIDs. The fake
database keeps per-connection snapshots, so commit/rollback behave like
PostgreSQL transactions and fault injection shows what survives each failure.
"""
import base64
import copy
import json
import logging
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend import main
from backend.auth import routes as auth_routes
from backend.auth import service as auth_service
from backend.auth.current_user import reset_current_user, set_current_user
from backend.core.i18n import use_language

EMAIL = "person@example.com"
OTHER_EMAIL = "someone.else@example.com"
AUTH_ID = "aaaaaaaa-1111-4111-8111-111111111111"
NEW_AUTH_ID = "bbbbbbbb-2222-4222-8222-222222222222"
OTHER_AUTH_ID = "cccccccc-3333-4333-8333-333333333333"
ACCOUNT_ID = "11111111-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OTHER_ACCOUNT_ID = "22222222-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
SECRET_GOOGLE = "dddddddd-0000-4000-8000-000000000001"
SECRET_OTHER = "dddddddd-0000-4000-8000-000000000009"
DEPENDENTS = [{"schema_name": "public", "table_name": "memory_items", "column_name": "user_id"}]


def _norm(value):
    return str(value or "").strip().lower()


def _token(auth_id: str, provider: str = "google") -> str:
    claims = base64.urlsafe_b64encode(json.dumps({"amr": [{"method": "oauth"}]}).encode()).decode().rstrip("=")
    return f"header.{claims}.{auth_id}.{provider}"


def _state(*, allowed_sid=AUTH_ID, account_sid=AUTH_ID, status="active", role="user", with_account=True):
    accounts = {
        OTHER_ACCOUNT_ID: {"id": OTHER_ACCOUNT_ID, "legacy_allowed_user_id": 7, "supabase_user_id": OTHER_AUTH_ID,
                           "primary_email": OTHER_EMAIL, "role": "user"},
    }
    if with_account:
        accounts[ACCOUNT_ID] = {"id": ACCOUNT_ID, "legacy_allowed_user_id": 42, "supabase_user_id": account_sid,
                                "primary_email": EMAIL, "role": role}
    return {
        "allowed_users": {
            42: {"id": 42, "email": EMAIL, "role": role, "status": status, "supabase_user_id": allowed_sid},
            7: {"id": 7, "email": OTHER_EMAIL, "role": "user", "status": "active", "supabase_user_id": OTHER_AUTH_ID},
        },
        "accounts": accounts,
        "users": [{"email": EMAIL}, {"email": OTHER_EMAIL}],
        "vault": {SECRET_GOOGLE: "google-refresh-example", SECRET_OTHER: "other-refresh-example"},
        "gmail": [
            {"account_id": ACCOUNT_ID, "refresh_token_secret_id": SECRET_GOOGLE, "granted_scopes": [auth_service.GMAIL_SCOPE]},
            {"account_id": OTHER_ACCOUNT_ID, "refresh_token_secret_id": SECRET_OTHER, "granted_scopes": [auth_service.GMAIL_SCOPE]},
        ],
        "payroll": [{"account_id": ACCOUNT_ID}, {"account_id": OTHER_ACCOUNT_ID}],
        # product_events: account FK is ON DELETE SET NULL, so the flow deletes them explicitly.
        "events": [{"account_id": ACCOUNT_ID}, {"account_id": ACCOUNT_ID}, {"account_id": OTHER_ACCOUNT_ID}],
        "finance": [{"account_id": ACCOUNT_ID}, {"account_id": OTHER_ACCOUNT_ID}],
        # A table whose FK points at allowed_users(id): it does not cascade from accounts.
        "memory_items": [{"user_id": 42, "text": "synthetic note"}, {"user_id": 7, "text": "other note"}],
    }


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchone(self): return self.rows[0] if self.rows else None
    def fetchall(self): return self.rows


class FakeDB:
    def __init__(self, state):
        self.state = state
        self.log = []
        self.fail_on = None
        self.fail_commits = set()
        self.commit_attempts = 0
        self.hooks = {}
        self.dependents = DEPENDENTS

    def writes(self):
        return [(sql, params) for sql, params in self.log if sql.startswith(("UPDATE", "DELETE", "INSERT"))]

    def committed(self):
        return [sql for sql, _ in self.log if sql == "COMMIT"]


class FakeConnection:
    def __init__(self, db):
        self.db = db
        self.work = copy.deepcopy(db.state)

    def __enter__(self): return self

    def __exit__(self, exc_type, *_args):
        if exc_type:
            self.db.log.append(("ROLLBACK", ()))
        return False

    def commit(self):
        self.db.commit_attempts += 1
        if self.db.commit_attempts in self.db.fail_commits:
            raise RuntimeError("injected commit failure")
        self.db.state = copy.deepcopy(self.work)
        self.db.log.append(("COMMIT", ()))

    def execute(self, query, params=()):
        sql = " ".join(query.split())
        self.db.log.append((sql, tuple(params)))
        for fragment, hook in list(self.db.hooks.items()):
            if fragment in sql:
                hook(self)
        if self.db.fail_on and self.db.fail_on in sql:
            self.db.fail_on = None
            raise RuntimeError("injected statement failure")
        return Result(self._run(sql, params))

    def _run(self, sql, params):
        if sql.startswith("SELECT set_config('dincr.delete_workspace'"):
            return []  # transaction-local declaration for the financial delete guard
        w = self.work
        accounts = w["accounts"]
        if sql.startswith("SELECT id, email, role, status, supabase_user_id"):
            return [dict(row) for row in w["allowed_users"].values() if row["email"] == params[0]]
        if sql.startswith("SELECT supabase_user_id, role, last_login_at FROM accounts WHERE legacy_allowed_user_id"):
            return [{"supabase_user_id": a["supabase_user_id"], "role": a.get("role"), "last_login_at": a.get("last_login_at")}
                    for a in accounts.values() if a["legacy_allowed_user_id"] == params[0]]
        if sql.startswith("UPDATE allowed_users SET supabase_user_id"):
            sid, uid, expected = params
            row = w["allowed_users"].get(uid)
            if row and (row["supabase_user_id"] is None or _norm(row["supabase_user_id"]) == expected):
                row.update(supabase_user_id=sid)
                return [{"id": uid}]
            return []
        if sql.startswith("UPDATE accounts SET supabase_user_id"):
            sid, legacy, expected = params
            updated = []
            for account in accounts.values():
                if account["legacy_allowed_user_id"] == legacy and account["supabase_user_id"] in (None, expected):
                    account.update(supabase_user_id=sid)
                    updated.append({"id": account["id"]})
            return updated
        if "FROM accounts a" in sql and "JOIN workspaces" in sql:
            return [{
                "account_id": a["id"], "account_role": a["role"], "account_status": "active",
                "workspace_id": f"ws-{a['id']}", "workspace_name": "Personal", "workspace_type": "personal",
                "workspace_status": "active", "member_role": "owner", "membership_status": "active",
            } for a in accounts.values() if a["legacy_allowed_user_id"] == params[0]]
        if sql.startswith("INSERT INTO allowed_users"):
            new_id = max(w["allowed_users"], default=0) + 1
            w["allowed_users"][new_id] = {"id": new_id, "email": params[0], "role": "user", "status": "active", "supabase_user_id": params[1]}
            return [{"id": new_id}]
        if sql.startswith("INSERT INTO accounts"):
            new_id = f"99999999-0000-4000-8000-{params[0]:012d}"
            accounts[new_id] = {"id": new_id, "legacy_allowed_user_id": params[0], "supabase_user_id": params[1],
                                "primary_email": params[2], "role": "user"}
            return [{"id": new_id}]
        if sql.startswith("INSERT INTO workspaces"):
            return [{"id": f"ws-{params[1]}"}]
        if sql.startswith("INSERT INTO workspace_members"):
            return []
        if sql.startswith("SELECT (SELECT COUNT(*) FROM accounts"):
            legacy, email = params
            return [{
                "accounts_left": sum(a["legacy_allowed_user_id"] == legacy for a in accounts.values()),
                "users_left": sum(u["email"].lower() == email.lower() for u in w["users"]),
            }]
        if sql.startswith("SELECT * FROM allowed_users WHERE id = %s"):
            row = w["allowed_users"].get(params[0])
            return [dict(row)] if row else []
        if sql == "DELETE FROM allowed_users WHERE id = %s":
            w["allowed_users"].pop(params[0], None)
            return []
        if sql.startswith("DELETE FROM allowed_users"):
            assert "lower(trim(supabase_user_id))=%s" in sql
            if "status='deletion_pending'" in sql:
                uid, sid = params
                expected_status = "deletion_pending"
            else:
                uid, expected_status, sid = params
            row = w["allowed_users"].get(uid)
            if row and row["status"] == expected_status and _norm(row["supabase_user_id"]) == sid:
                del w["allowed_users"][uid]
                return [{"id": uid}]
            return []
        if sql.startswith("SELECT legacy_allowed_user_id, supabase_user_id, primary_email FROM accounts WHERE id=%s"):
            account = accounts.get(params[0])
            return [dict(account)] if account else []
        if sql.startswith("UPDATE allowed_users SET status=%s"):
            assert "lower(trim(supabase_user_id))=%s" in sql
            new_status, uid, sid = params
            row = w["allowed_users"].get(uid)
            if row and _norm(row["supabase_user_id"]) == sid:
                row["status"] = new_status
                return [{"id": uid}]
            return []
        if sql.startswith("SELECT id, supabase_user_id, primary_email FROM accounts WHERE legacy_allowed_user_id"):
            return [dict(a) for a in accounts.values() if a["legacy_allowed_user_id"] == params[0]]
        if "pg_constraint" in sql and "confrelid='public.allowed_users'::regclass" in sql:
            return [dict(ref) for ref in self.db.dependents]
        if "pg_constraint" in sql:
            return []
        if sql.startswith('DELETE FROM "public"."memory_items" WHERE "user_id"=%s'):
            w["memory_items"] = [m for m in w["memory_items"] if m["user_id"] != params[0]]
            return []
        if "FROM finva_gmail_connections" in sql:
            return [{
                "refresh_token_secret_id": g["refresh_token_secret_id"], "granted_scopes": g["granted_scopes"],
                "decrypted_secret": w["vault"].get(g["refresh_token_secret_id"]),
            } for g in w["gmail"] if g["account_id"] == params[0]]
        if "to_regclass('public.mail_oauth_flows')" in sql:
            return [{"present": None}]
        if "to_regclass('public.payroll_salary_reports')" in sql:
            return [{"present": "payroll_salary_reports"}]
        if "to_regclass('public.product_events')" in sql:
            return [{"present": "product_events"}]
        if sql.startswith("DELETE FROM product_events"):
            deleted = [e for e in w["events"] if e["account_id"] == params[0]]
            w["events"] = [e for e in w["events"] if e["account_id"] != params[0]]
            return [{"id": index} for index, _ in enumerate(deleted)]
        if sql.startswith("DELETE FROM vault.secrets"):
            for secret_id in params[0]:
                w["vault"].pop(secret_id, None)
            return []
        if sql.startswith("DELETE FROM payroll_salary_reports"):
            w["payroll"] = [p for p in w["payroll"] if p["account_id"] != params[0]]
            return []
        if sql.startswith("DELETE FROM accounts WHERE id=%s"):
            if params[0] not in accounts:
                return []
            del accounts[params[0]]
            # ON DELETE CASCADE through workspaces.
            w["gmail"] = [g for g in w["gmail"] if g["account_id"] != params[0]]
            w["finance"] = [f for f in w["finance"] if f["account_id"] != params[0]]
            return [{"id": params[0]}]
        if sql.startswith("DELETE FROM users WHERE lower(email)=lower(%s)"):
            w["users"] = [u for u in w["users"] if u["email"].lower() != params[0].lower()]
            return []
        raise AssertionError(f"Unexpected SQL in fake: {sql}")


class FakeSupabase:
    def __init__(self, auth_users=(AUTH_ID, OTHER_AUTH_ID)):
        self.auth_users = set(auth_users)
        self.delete_results = []
        self.admin_get_result = None
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        if url.endswith("/auth/v1/user"):
            _header, _claims, auth_id, provider = headers["Authorization"].removeprefix("Bearer ").split(".")
            if auth_id not in self.auth_users:
                return SimpleNamespace(status_code=401, json=lambda: {})
            providers = ["google", "apple"] if provider == "apple" else [provider]
            payload = {"id": auth_id, "email": EMAIL.upper() if provider == "apple" else EMAIL,
                       "app_metadata": {"provider": provider, "providers": providers}, "user_metadata": {}}
            return SimpleNamespace(status_code=200, json=lambda: payload)
        assert "/auth/v1/admin/users/" in url and timeout == 10
        self.calls.append(("ADMIN_GET", url.rsplit("/", 1)[1]))
        result = self.admin_get_result
        if isinstance(result, Exception):
            raise result
        if result is None:
            result = 200 if url.rsplit("/", 1)[1] in self.auth_users else 404
        return SimpleNamespace(status_code=result)

    def delete(self, url, headers=None, timeout=None):
        auth_id = url.rsplit("/", 1)[1]
        self.calls.append(("ADMIN_DELETE", auth_id))
        result = self.delete_results.pop(0) if self.delete_results else 204
        if isinstance(result, Exception):
            raise result
        if result in {200, 204}:
            self.auth_users.discard(auth_id)
        return SimpleNamespace(status_code=result)

    def post(self, url, params=None, timeout=None):
        self.calls.append(("REVOKE", params["token"]))
        return SimpleNamespace(status_code=200)


@pytest.fixture
def env(monkeypatch):
    holder = SimpleNamespace(db=FakeDB(_state()), supabase=FakeSupabase())
    monkeypatch.setattr(auth_service, "get_connection", lambda: FakeConnection(holder.db))
    monkeypatch.setattr(auth_service, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(auth_service, "SUPABASE_ANON_KEY", "anon-example")
    monkeypatch.setattr(auth_service, "SUPABASE_ADMIN_KEY", "sb_secret_example")
    monkeypatch.setenv("OWNER_EMAILS", "")
    monkeypatch.setattr(auth_service, "enrich_identity", lambda identity: identity)
    monkeypatch.setattr(auth_service.requests, "get", lambda *a, **k: holder.supabase.get(*a, **k))
    monkeypatch.setattr(auth_service.requests, "delete", lambda *a, **k: holder.supabase.delete(*a, **k))
    monkeypatch.setattr(auth_service.requests, "post", lambda *a, **k: holder.supabase.post(*a, **k))
    return holder


def _login(env, auth_id=AUTH_ID, provider="google", **kwargs):
    return auth_service.authenticate_access_token(_token(auth_id, provider), **kwargs)


def _delete_as(identity):
    token = set_current_user(identity)
    try:
        return auth_service.delete_current_account()
    finally:
        reset_current_user(token)


def _assert_other_account_untouched(state):
    assert state["allowed_users"][7] == {"id": 7, "email": OTHER_EMAIL, "role": "user", "status": "active", "supabase_user_id": OTHER_AUTH_ID}
    assert OTHER_ACCOUNT_ID in state["accounts"]
    assert state["vault"].get(SECRET_OTHER) == "other-refresh-example"
    assert {"account_id": OTHER_ACCOUNT_ID} in state["payroll"] and {"account_id": OTHER_ACCOUNT_ID} in state["finance"]
    assert {"email": OTHER_EMAIL} in state["users"]
    assert {"user_id": 7, "text": "other note"} in state["memory_items"]


def _assert_writes_scoped(db, allowed_ids=(42,), account_ids=(ACCOUNT_ID,), emails=(EMAIL,)):
    """Every UPDATE/DELETE carries the caller's own identifiers, never another account's."""
    own = {*allowed_ids, *account_ids, *emails}
    for sql, params in db.writes():
        if sql.startswith("INSERT"):
            continue
        if sql.startswith("DELETE FROM vault.secrets"):
            assert SECRET_OTHER not in params[0]
            continue
        assert own & set(params), f"write not scoped to the caller: {sql}"
        assert not {7, OTHER_ACCOUNT_ID, OTHER_EMAIL, OTHER_AUTH_ID} & set(params)


def _assert_all_data_gone(state):
    assert ACCOUNT_ID not in state["accounts"]
    assert SECRET_GOOGLE not in state["vault"]
    assert {"account_id": ACCOUNT_ID} not in state["payroll"]
    assert state["events"] == [{"account_id": OTHER_ACCOUNT_ID}]  # analytics of the person go, nobody else's
    assert {"account_id": ACCOUNT_ID} not in state["finance"]
    assert all(g["account_id"] != ACCOUNT_ID for g in state["gmail"])
    assert {"email": EMAIL} not in state["users"]
    assert all(m["user_id"] != 42 for m in state["memory_items"])


def _assert_data_intact(state):
    assert ACCOUNT_ID in state["accounts"]
    assert state["vault"].get(SECRET_GOOGLE) == "google-refresh-example"
    assert {"account_id": ACCOUNT_ID} in state["payroll"] and {"account_id": ACCOUNT_ID} in state["finance"]
    assert {"email": EMAIL} in state["users"]
    assert {"user_id": 42, "text": "synthetic note"} in state["memory_items"]


def _assert_pending_409(error):
    assert error.value.status_code == 409
    assert error.value.detail["code"] == auth_service.DELETION_PENDING_CODE
    assert error.value.detail["message"]


# --- A) Stable identity binding -------------------------------------------------


def test_first_login_binds_null_ids_of_a_preauthorized_account(env):
    env.db = FakeDB(_state(allowed_sid=None, account_sid=None))
    identity = _login(env)
    assert identity["account_id"] == ACCOUNT_ID and identity["supabase_user_id"] == AUTH_ID
    assert env.db.state["allowed_users"][42]["supabase_user_id"] == AUTH_ID
    assert env.db.state["accounts"][ACCOUNT_ID]["supabase_user_id"] == AUTH_ID
    binds = [sql for sql, _ in env.db.writes()]
    assert len(binds) == 2 and all("supabase_user_id IS NULL OR" in sql for sql in binds)


def test_stored_id_with_uppercase_and_whitespace_still_binds(env):
    env.db = FakeDB(_state(allowed_sid=f"  {AUTH_ID.upper()} ", account_sid=AUTH_ID))
    assert _login(env)["account_id"] == ACCOUNT_ID
    bind_params = next(params for sql, params in env.db.writes() if sql.startswith("UPDATE allowed_users"))
    assert bind_params[-1] == AUTH_ID  # compared against the normalized token id
    assert env.db.state["allowed_users"][42]["supabase_user_id"] == AUTH_ID


def test_repeat_login_with_the_bound_id_keeps_working(env):
    for _ in range(2):
        assert _login(env)["account_id"] == ACCOUNT_ID
    assert env.db.state["allowed_users"][42]["supabase_user_id"] == AUTH_ID
    _assert_other_account_untouched(env.db.state)


def test_same_email_with_a_different_auth_id_fails_closed_before_any_write(env, caplog):
    env.supabase.auth_users.add(NEW_AUTH_ID)
    before = copy.deepcopy(env.db.state)
    with caplog.at_level(logging.WARNING, logger=auth_service.__name__):
        with pytest.raises(HTTPException) as error:
            _login(env, NEW_AUTH_ID)
    assert error.value.status_code == 403
    assert error.value.detail == auth_service.IDENTITY_REJECTED_ES
    assert env.db.writes() == [] and env.db.committed() == []
    assert env.db.state == before
    logged = caplog.text
    assert "allowed_user_id=42" in logged
    assert EMAIL not in logged and NEW_AUTH_ID not in logged and AUTH_ID not in logged


def test_mismatch_is_checked_before_status_so_state_is_not_revealed(env):
    env.db = FakeDB(_state(status="blocked"))
    env.supabase.auth_users.add(NEW_AUTH_ID)
    with pytest.raises(HTTPException) as error:
        _login(env, NEW_AUTH_ID)
    assert error.value.detail == auth_service.IDENTITY_REJECTED_ES


def test_rejections_follow_the_response_language(env):
    env.supabase.auth_users.add(NEW_AUTH_ID)
    with use_language("en"):
        with pytest.raises(HTTPException) as error:
            _login(env, NEW_AUTH_ID)
    assert error.value.detail == auth_service.IDENTITY_REJECTED_EN
    env.db = FakeDB(_state(status="deletion_pending"))
    with use_language("en"):
        with pytest.raises(HTTPException) as pending_en:
            _login(env)
    with pytest.raises(HTTPException) as pending_es:
        _login(env)
    assert pending_en.value.detail["message"].startswith("Your deletion is in progress")
    assert pending_es.value.detail["message"].startswith("Tu eliminación quedó en proceso")


@pytest.mark.parametrize(("allowed_sid", "account_sid"), [(None, AUTH_ID), (AUTH_ID, None)])
def test_null_id_in_only_one_table_is_bound_to_the_matching_id(env, allowed_sid, account_sid):
    env.db = FakeDB(_state(allowed_sid=allowed_sid, account_sid=account_sid))
    assert _login(env)["account_id"] == ACCOUNT_ID
    assert env.db.state["allowed_users"][42]["supabase_user_id"] == AUTH_ID
    assert env.db.state["accounts"][ACCOUNT_ID]["supabase_user_id"] == AUTH_ID


def test_null_allowed_user_but_account_bound_to_another_id_fails_closed(env):
    env.db = FakeDB(_state(allowed_sid=None, account_sid=OTHER_AUTH_ID.replace("c", "e")))
    with pytest.raises(HTTPException) as error:
        _login(env)
    assert error.value.status_code == 403
    assert env.db.writes() == [] and env.db.state["allowed_users"][42]["supabase_user_id"] is None


@pytest.mark.parametrize("race_on", ["UPDATE allowed_users SET supabase_user_id", "UPDATE accounts SET supabase_user_id"])
def test_concurrent_bind_by_another_id_loses_and_rolls_back(env, race_on):
    env.db = FakeDB(_state(allowed_sid=None, account_sid=None))

    def concurrent_bind(conn):
        # Another login committed a different id first; the row lock re-check sees it.
        if race_on.startswith("UPDATE allowed_users"):
            conn.work["allowed_users"][42]["supabase_user_id"] = NEW_AUTH_ID
        else:
            conn.work["accounts"][ACCOUNT_ID]["supabase_user_id"] = NEW_AUTH_ID

    env.db.hooks[race_on] = concurrent_bind
    with pytest.raises(HTTPException) as error:
        _login(env)
    assert error.value.status_code == 403
    assert env.db.committed() == [] and ("ROLLBACK", ()) in env.db.log
    assert env.db.state["allowed_users"][42]["supabase_user_id"] is None
    assert env.db.state["accounts"][ACCOUNT_ID]["supabase_user_id"] is None


def test_owner_email_with_a_different_auth_id_is_rejected_and_role_not_rewritten(env, monkeypatch):
    env.db = FakeDB(_state(role="owner"))
    monkeypatch.setenv("OWNER_EMAILS", EMAIL)
    env.supabase.auth_users.add(NEW_AUTH_ID)
    with pytest.raises(HTTPException) as error:
        _login(env, NEW_AUTH_ID)
    assert error.value.status_code == 403
    assert env.db.writes() == []
    # The bound Owner identity keeps its role.
    assert _login(env)["role"] == "owner"


def test_being_listed_never_makes_a_user_an_owner(env, monkeypatch):
    monkeypatch.setenv("OWNER_EMAILS", EMAIL)
    assert _login(env)["role"] == "user"
    assert env.db.state["allowed_users"][42]["role"] == env.db.state["accounts"][ACCOUNT_ID]["role"] == "user"


@pytest.mark.parametrize("configured", ["", "someone-else@example.com", " , "])
def test_an_owner_missing_from_the_allowlist_gets_no_session_and_is_not_demoted(env, monkeypatch, configured):
    """Removing the email ends Owner access at once; a transient bad value never rewrites the role."""
    env.db = FakeDB(_state(role="owner"))
    monkeypatch.setenv("OWNER_EMAILS", configured)
    with pytest.raises(HTTPException) as refused:
        _login(env)
    assert refused.value.status_code == 403  # neither Owner nor a downgraded User session
    assert env.db.writes() == []
    assert env.db.state["allowed_users"][42]["role"] == env.db.state["accounts"][ACCOUNT_ID]["role"] == "owner"
    monkeypatch.setenv("OWNER_EMAILS", f"x@example.com,{EMAIL.upper()}")  # the configuration is fixed
    assert _login(env)["role"] == "owner"


def test_login_never_writes_a_role(env, monkeypatch):
    env.db = FakeDB(_state(role="owner"))
    monkeypatch.setenv("OWNER_EMAILS", EMAIL)
    _login(env)
    assert not [sql for sql, _ in env.db.writes() if "role" in sql.split("WHERE")[0].lower()]


def test_google_and_linked_apple_identity_share_the_same_account(env):
    google = _login(env, provider="google")
    apple = _login(env, provider="apple")
    assert google["account_id"] == apple["account_id"] == ACCOUNT_ID
    assert apple["email"] == EMAIL


def test_deletion_pending_non_delete_request_by_bound_user_gets_409_code(env):
    env.db = FakeDB(_state(status="deletion_pending", with_account=False))
    with pytest.raises(HTTPException) as error:
        _login(env)
    _assert_pending_409(error)
    assert env.db.writes() == []
    assert not any(call[0] == "ADMIN_GET" for call in env.supabase.calls)


def test_deletion_pending_other_id_gets_generic_403_without_revealing_deletion(env):
    env.db = FakeDB(_state(status="deletion_pending", with_account=False))
    env.supabase.auth_users.add(NEW_AUTH_ID)  # old Auth user still exists: admin GET says 200
    with pytest.raises(HTTPException) as error:
        _login(env, NEW_AUTH_ID)
    assert error.value.status_code == 403
    assert error.value.detail == auth_service.IDENTITY_REJECTED_ES
    assert "elimin" not in error.value.detail.lower()
    assert env.db.writes() == []


def test_admin_api_refuses_to_delete_a_deletion_pending_row(env):
    env.db = FakeDB(_state(status="deletion_pending", with_account=False))
    result = auth_service.delete_allowed_user(42)
    assert result["status"] == "ERROR"
    assert 42 in env.db.state["allowed_users"]
    assert not any(sql.startswith("DELETE") for sql, _ in env.db.log)


def test_deletion_pending_delete_me_gets_a_minimal_identity(env):
    env.db = FakeDB(_state(status="deletion_pending"))
    identity = _login(env, allow_deletion_pending=True)
    assert identity == {"id": 42, "email": EMAIL, "role": "user", "status": "deletion_pending", "supabase_user_id": AUTH_ID}
    assert env.db.writes() == []


def test_middleware_relaxes_deletion_pending_only_for_delete_auth_me(monkeypatch):
    seen = []

    def fake_authenticate(token, **kwargs):
        seen.append(kwargs)
        return {"id": 42, "email": EMAIL, "role": "user", "status": "deletion_pending", "supabase_user_id": AUTH_ID}

    monkeypatch.setattr(main, "authenticate_access_token", fake_authenticate)
    monkeypatch.setattr(auth_routes, "delete_current_account", lambda: {"status": "OK"})
    monkeypatch.setattr(auth_routes, "capture_backend_event", lambda *_args: None)
    client = TestClient(main.app, raise_server_exceptions=False)
    headers = {"Authorization": "Bearer synthetic-token"}
    assert client.delete("/auth/me", headers=headers).status_code == 200
    client.get("/auth/me", headers=headers)
    client.delete("/auth/allowed-users/42", headers=headers)
    assert seen == [{"allow_deletion_pending": True}, {}, {}]


# --- B) Retry-safe account deletion ------------------------------------------------


def test_full_deletion_removes_data_auth_user_and_tombstone(env):
    result = _delete_as(_login(env))
    assert result["status"] == "OK"
    state = env.db.state
    _assert_all_data_gone(state)
    assert 42 not in state["allowed_users"]
    assert AUTH_ID not in env.supabase.auth_users
    assert ("REVOKE", "google-refresh-example") in env.supabase.calls
    assert env.db.committed() == ["COMMIT"] * 3  # login + (mark + data) + finalize
    assert state["memory_items"] == [{"user_id": 7, "text": "other note"}]
    mark = next(i for i, (sql, _) in enumerate(env.db.log) if sql.startswith("UPDATE allowed_users SET status"))
    data = next(i for i, (sql, _) in enumerate(env.db.log) if sql.startswith("DELETE FROM accounts"))
    commits = [i for i, (sql, _) in enumerate(env.db.log) if sql == "COMMIT"]
    assert commits[0] < mark < data < commits[1]  # one transaction for tombstone + data
    _assert_other_account_untouched(state)
    _assert_writes_scoped(env.db)


def test_missing_admin_key_fails_closed_before_marking(env, monkeypatch):
    identity = _login(env)
    monkeypatch.setattr(auth_service, "SUPABASE_ADMIN_KEY", None)
    env.db.log.clear()
    with pytest.raises(HTTPException) as error:
        _delete_as(identity)
    assert error.value.status_code == 503
    assert env.db.log == [] and env.db.state["allowed_users"][42]["status"] == "active"


@pytest.mark.parametrize("fault", [
    "UPDATE allowed_users SET status", "DELETE FROM vault.secrets", "DELETE FROM payroll_salary_reports", "DELETE FROM product_events",
    "DELETE FROM accounts", 'DELETE FROM "public"."memory_items"', "DELETE FROM users", "data_commit",
])
def test_failure_before_the_data_commit_leaves_a_normal_active_account(env, fault):
    identity = _login(env)
    before = copy.deepcopy(env.db.state)
    if fault == "data_commit":
        env.db.fail_commits = {env.db.commit_attempts + 1}
    else:
        env.db.fail_on = fault
    with pytest.raises(HTTPException) as error:
        _delete_as(identity)
    assert error.value.status_code == 500
    assert env.db.state == before  # no tombstone, all data intact
    assert env.db.state["allowed_users"][42]["status"] == "active"
    _assert_data_intact(env.db.state)
    assert ("ROLLBACK", ()) in env.db.log
    assert not any(call[0] in {"ADMIN_DELETE", "REVOKE"} for call in env.supabase.calls)

    # Still a normal account: it logs in and a retry is a fresh, complete deletion.
    fresh_identity = _login(env)
    assert fresh_identity["account_id"] == ACCOUNT_ID
    assert _delete_as(fresh_identity)["status"] == "OK"
    _assert_all_data_gone(env.db.state)
    assert 42 not in env.db.state["allowed_users"]
    assert AUTH_ID not in env.supabase.auth_users
    assert ("REVOKE", "google-refresh-example") in env.supabase.calls
    _assert_other_account_untouched(env.db.state)
    _assert_writes_scoped(env.db)


def test_unsafe_dependent_identifier_aborts_without_deleting(env):
    identity = _login(env)
    before = copy.deepcopy(env.db.state)
    env.db.dependents = [{"schema_name": "public", "table_name": "memory_items; drop table x", "column_name": "user_id"}]
    with pytest.raises(HTTPException) as error:
        _delete_as(identity)
    assert error.value.status_code == 500
    assert env.db.state == before
    assert not any("drop table" in sql.lower() for sql, _ in env.db.log)


def test_dependents_query_skips_set_null_foreign_keys(env):
    # Rows behind ON DELETE SET NULL/SET DEFAULT (e.g. an actor column) must outlive the user.
    identity = _login(env)
    _delete_as(identity)
    catalog = next(sql for sql, _ in env.db.log if "pg_constraint" in sql and "allowed_users" in sql)
    assert "c.confdeltype IN ('a','r','c')" in catalog


@pytest.mark.parametrize("failure", [500, TimeoutError("admin timeout")])
def test_supabase_failure_leaves_no_data_and_retry_finishes(env, failure):
    identity = _login(env)
    env.supabase.delete_results = [failure]
    with pytest.raises(HTTPException) as error:
        _delete_as(identity)
    assert error.value.status_code == 409
    assert error.value.detail["message"].startswith("Tu eliminación quedó en proceso")
    assert error.value.detail["code"] == auth_service.DELETION_PENDING_CODE
    assert error.value.detail["stage"] == "SUPABASE_AUTH_DELETE" and error.value.detail["deletion_id"]
    state = env.db.state
    _assert_all_data_gone(state)
    assert state["allowed_users"][42]["status"] == "deletion_pending"
    assert AUTH_ID in env.supabase.auth_users
    # The bound user can still sign in only to learn the deletion is pending.
    with pytest.raises(HTTPException) as pending:
        _login(env)
    _assert_pending_409(pending)
    # Tokens were revoked right after the data commit, before the Auth failure.
    assert ("REVOKE", "google-refresh-example") in env.supabase.calls

    env.db.log.clear()
    retry = _delete_as(_login(env, allow_deletion_pending=True))
    assert retry["status"] == "OK"
    assert 42 not in env.db.state["allowed_users"]
    assert AUTH_ID not in env.supabase.auth_users
    # The resumed attempt finds no account left: nothing but users/tombstone is touched.
    assert not any(sql.startswith(("DELETE FROM accounts", "DELETE FROM vault", "UPDATE")) for sql, _ in env.db.writes())
    _assert_other_account_untouched(env.db.state)
    _assert_writes_scoped(env.db)


def test_supabase_404_counts_as_already_deleted(env):
    identity = _login(env)
    env.supabase.delete_results = [404]
    assert _delete_as(identity)["status"] == "OK"
    assert 42 not in env.db.state["allowed_users"]


def test_repeated_delete_on_a_pending_user_is_idempotent(env):
    identity = _login(env)
    env.supabase.delete_results = [502, 502, 502]
    for attempt in range(3):
        with pytest.raises(HTTPException) as error:
            _delete_as(identity if attempt == 0 else _login(env, allow_deletion_pending=True))
        assert error.value.status_code == 409
        state = copy.deepcopy(env.db.state)
        _assert_all_data_gone(state)
        assert state["allowed_users"][42]["status"] == "deletion_pending"
    assert _delete_as(_login(env, allow_deletion_pending=True))["status"] == "OK"
    # After completion the old session is rejected by Supabase itself.
    with pytest.raises(HTTPException) as gone:
        _login(env, allow_deletion_pending=True)
    assert gone.value.status_code == 401


def test_finalize_failure_then_resignup_gets_a_fresh_empty_account(env):
    identity = _login(env)
    env.db.fail_commits = {env.db.commit_attempts + 2}
    assert _delete_as(identity)["status"] == "OK"
    assert env.db.state["allowed_users"][42]["status"] == "deletion_pending"
    assert AUTH_ID not in env.supabase.auth_users

    # Same email, brand-new Supabase user: admin GET confirms the old one is gone.
    env.supabase.auth_users.add(NEW_AUTH_ID)
    fresh = _login(env, NEW_AUTH_ID)
    assert ("ADMIN_GET", AUTH_ID) in env.supabase.calls
    state = env.db.state
    assert 42 not in state["allowed_users"]
    assert fresh["id"] != 42 and fresh["account_id"] != ACCOUNT_ID
    assert fresh["supabase_user_id"] == NEW_AUTH_ID
    assert all(g["account_id"] != fresh["account_id"] for g in state["gmail"])
    assert all(f["account_id"] != fresh["account_id"] for f in state["finance"])
    assert all(p["account_id"] != fresh["account_id"] for p in state["payroll"])
    _assert_all_data_gone(state)
    _assert_other_account_untouched(state)


@pytest.mark.parametrize("admin_result", [200, 500, TimeoutError("admin timeout")])
def test_tombstone_is_kept_unless_supabase_confirms_the_old_user_is_gone(env, admin_result):
    env.db = FakeDB(_state(status="deletion_pending", with_account=False))
    env.db.state["users"] = [{"email": OTHER_EMAIL}]
    env.supabase.auth_users.add(NEW_AUTH_ID)
    env.supabase.admin_get_result = admin_result
    before = copy.deepcopy(env.db.state)
    with pytest.raises(HTTPException) as error:
        _login(env, NEW_AUTH_ID)
    assert error.value.status_code == 403
    assert error.value.detail == auth_service.IDENTITY_REJECTED_ES
    assert env.db.state == before and env.db.writes() == []


def test_self_heal_refuses_while_old_account_data_remains(env):
    # Tx2 never ran (data intact) and the Auth user was removed out of band.
    env.db = FakeDB(_state(status="deletion_pending"))
    env.supabase.auth_users = {NEW_AUTH_ID, OTHER_AUTH_ID}
    before = copy.deepcopy(env.db.state)
    with pytest.raises(HTTPException) as error:
        _login(env, NEW_AUTH_ID)
    assert error.value.status_code == 403
    assert env.db.state == before
    assert ("ROLLBACK", ()) in env.db.log


def test_same_id_on_a_pending_account_must_finish_via_delete(env):
    env.db = FakeDB(_state(status="deletion_pending", with_account=False))
    with pytest.raises(HTTPException) as error:
        _login(env)
    _assert_pending_409(error)
    assert not any(call[0] == "ADMIN_GET" for call in env.supabase.calls)
    assert 42 in env.db.state["allowed_users"]


# --- Fresh identities skip the refresh writes, never the checks -------------------

def _recently_seen(env, minutes=1):
    from datetime import datetime, timedelta, timezone
    seen = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    env.db.state["allowed_users"][42]["last_login_at"] = seen
    env.db.state["accounts"][ACCOUNT_ID]["last_login_at"] = seen


def test_a_bound_recent_identity_authenticates_without_writes(env):
    _recently_seen(env)
    identity = _login(env)
    assert identity["account_id"] == ACCOUNT_ID
    assert not [sql for sql, _ in env.db.writes() if sql.startswith(("UPDATE allowed_users", "UPDATE accounts"))]


def test_the_fresh_path_still_rejects_another_auth_identity(env):
    _recently_seen(env)
    with pytest.raises(HTTPException) as rejected:
        _login(env, auth_id=OTHER_AUTH_ID)
    assert rejected.value.status_code in {401, 403}


def test_an_old_login_still_writes_and_no_login_changes_the_role(env, monkeypatch):
    """Login writes only the binding and last_login_at (backend/auth/owner_role.py): being
    listed in OWNER_EMAILS neither forces a write nor promotes anyone."""
    _recently_seen(env)
    monkeypatch.setenv("OWNER_EMAILS", EMAIL)
    _login(env)
    assert env.db.state["allowed_users"][42]["role"] == "user"
    assert not any(sql.startswith("UPDATE allowed_users") for sql, _ in env.db.writes())

    env.db.log.clear()
    _recently_seen(env, minutes=10)
    _login(env)
    assert any(sql.startswith("UPDATE allowed_users") for sql, _ in env.db.writes())
    assert env.db.state["allowed_users"][42]["role"] == "user"


def test_a_first_sign_in_that_loses_the_race_uses_the_winners_account(env, monkeypatch):
    """Authentication runs in parallel: two first requests of a new user both try to create it."""
    import psycopg2

    winner = env.db.state["allowed_users"].pop(42)
    winner_account = env.db.state["accounts"].pop(ACCOUNT_ID)

    def created_by_the_other_request(conn, supabase_user):
        env.db.state["allowed_users"][42] = winner
        env.db.state["accounts"][ACCOUNT_ID] = winner_account
        raise psycopg2.errors.UniqueViolation()

    monkeypatch.setattr(auth_service, "_create_personal_account", created_by_the_other_request)
    identity = _login(env)
    assert identity["account_id"] == ACCOUNT_ID
