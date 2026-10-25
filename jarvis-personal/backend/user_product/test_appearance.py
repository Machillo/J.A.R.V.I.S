"""Personal appearance (phase 1, Owner only): gate, validation, per-account storage, defaults.

The routes run through the real app (auth middleware, require_owner) over an in-memory stand-in
for `user_preferences` that understands exactly the three statements appearance.py issues; the
real SQL is proven on PostgreSQL in test_appearance_pg.py. Synthetic identities only.
"""
from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.user_product import appearance

AUTH = {"Authorization": "Bearer test-token"}
WS_OWNER = "00000000-0000-4000-8000-00000000000a"
WS_OTHER = "00000000-0000-4000-8000-00000000000c"
USERS = {
    "owner": {"id": 1, "account_id": "00000000-0000-4000-8000-0000000000a1", "workspace_id": WS_OWNER, "role": "owner", "plan": "vip"},
    "free": {"id": 50, "account_id": "00000000-0000-4000-8000-0000000000b1", "workspace_id": "00000000-0000-4000-8000-00000000000b", "role": "user", "plan": "free"},
    "basic": {"id": 51, "account_id": "00000000-0000-4000-8000-0000000000b2", "workspace_id": "00000000-0000-4000-8000-00000000000d", "role": "user", "plan": "basic"},
    "vip": {"id": 52, "account_id": "00000000-0000-4000-8000-0000000000b3", "workspace_id": "00000000-0000-4000-8000-00000000000e", "role": "user", "plan": "vip"},
}
CHOICE = {"theme": "dark", "palette": "arena", "accent": "ciruela", "text_size": "l", "typeface": "editorial", "density": "compact", "surfaces": "tonal"}


class Store:
    """`user_preferences` as {(workspace_id, preference_key): (value, updated_at)}."""

    def __init__(self):
        self.rows: dict[tuple[str, str], tuple[dict, str]] = {}
        self.statements: list[str] = []
        self.clock = 0

    def connection(self):
        store = self

        class Result:
            def __init__(self, rows):
                self.rows = rows

            def fetchone(self):
                return self.rows[0] if self.rows else None

        class Conn:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def commit(self):
                pass

            def execute(self, query, params=()):
                sql = re.sub(r"\s+", " ", query).strip()
                assert "user_preferences" in sql, sql
                store.statements.append(sql.split(" ")[0].upper())
                if sql.startswith("SELECT"):
                    assert "WHERE workspace_id = %s AND preference_key = %s" in sql
                    row = store.rows.get((params[0], params[1]))
                    return Result([{"preference_value": row[0], "updated_at": row[1]}] if row else [])
                if sql.startswith("INSERT"):
                    assert "ON CONFLICT (workspace_id, preference_key)" in sql
                    store.clock += 1
                    stamp = f"2026-10-22T10:00:{store.clock:02d}+00:00"
                    store.rows[(params[0], params[1])] = (json.loads(params[2]), stamp)
                    return Result([{"updated_at": stamp}])
                raise AssertionError(f"unexpected statement: {sql}")

        return Conn()


@pytest.fixture
def store(monkeypatch):
    s = Store()
    monkeypatch.setattr(appearance, "get_connection", s.connection)
    return s


@pytest.fixture
def as_user(monkeypatch):
    current = {"user": USERS["owner"]}
    monkeypatch.setattr(main, "authenticate_access_token", lambda _token: current["user"])
    monkeypatch.setattr(main, "disabled_feature_for_request", lambda *_a, **_k: None)
    client = TestClient(main.app, raise_server_exceptions=False)

    def use(who):
        current["user"] = USERS[who] if isinstance(who, str) else who
        return client

    return use


def test_the_owner_starts_on_the_defaults_and_a_read_never_writes(store, as_user):
    response = as_user("owner").get("/user-product/appearance", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["preferences"] == body["defaults"] == appearance.DEFAULTS.model_dump()
    assert body["stored"] is False and body["updated_at"] is None and body["version"] == 1
    assert store.statements == ["SELECT"] and store.rows == {}


def test_the_owner_saves_reads_back_and_restores_the_defaults(store, as_user):
    client = as_user("owner")
    saved = client.put("/user-product/appearance", headers=AUTH, json=CHOICE)
    assert saved.status_code == 200 and saved.json()["preferences"] == CHOICE and saved.json()["stored"] is True
    assert client.get("/user-product/appearance", headers=AUTH).json()["preferences"] == CHOICE
    again = {**CHOICE, "accent": "tinta"}
    assert client.put("/user-product/appearance", headers=AUTH, json=again).json()["preferences"] == again
    assert len(store.rows) == 1, "one row per account, updated in place"
    reset = client.delete("/user-product/appearance", headers=AUTH)
    assert reset.status_code == 200 and reset.json()["preferences"] == appearance.DEFAULTS.model_dump() and reset.json()["stored"] is False
    assert [value for value, _stamp in store.rows.values()] == [{}], "a reset clears the value (the app role has no DELETE)"
    assert "DELETE" not in store.statements
    assert client.get("/user-product/appearance", headers=AUTH).json()["stored"] is False


@pytest.mark.parametrize("who", ["free", "basic", "vip"])
def test_free_basic_and_vip_are_refused_by_the_server_on_every_route(store, as_user, who):
    client = as_user(who)
    assert client.get("/user-product/appearance", headers=AUTH).status_code == 403
    assert client.put("/user-product/appearance", headers=AUTH, json=CHOICE).status_code == 403
    assert client.delete("/user-product/appearance", headers=AUTH).status_code == 403
    assert store.statements == [] and store.rows == {}, "nothing is read or written for a refused account"


@pytest.mark.parametrize("change", [
    {"palette": "neon"},
    {"accent": "#FF0000"},
    {"text_size": "xxl"},
    {"theme": None},
    {"density": 1},
    {"surfaces": "glass"},
    {"workspace_id": WS_OTHER},
    {"account_id": "00000000-0000-4000-8000-0000000000b1"},
])
def test_only_complete_catalog_values_are_accepted(store, as_user, change):
    response = as_user("owner").put("/user-product/appearance", headers=AUTH, json={**CHOICE, **change})
    assert response.status_code == 422
    assert store.rows == {}


def test_a_partial_body_is_refused(store, as_user):
    partial = {key: value for key, value in CHOICE.items() if key != "typeface"}
    assert as_user("owner").put("/user-product/appearance", headers=AUTH, json=partial).status_code == 422


def test_preferences_are_per_account_even_inside_one_workspace(store, as_user):
    # Two (hypothetical) Owner-role sessions: another account in the same workspace and one in
    # another workspace. Each one keeps its own appearance; nobody sees or resets another's.
    same_workspace = {**USERS["owner"], "account_id": "00000000-0000-4000-8000-0000000000a2"}
    other_workspace = {**USERS["owner"], "account_id": "00000000-0000-4000-8000-0000000000a3", "workspace_id": WS_OTHER}
    as_user("owner").put("/user-product/appearance", headers=AUTH, json=CHOICE)
    for other in (same_workspace, other_workspace):
        assert as_user(other).get("/user-product/appearance", headers=AUTH).json()["stored"] is False
        as_user(other).delete("/user-product/appearance", headers=AUTH)
    assert as_user("owner").get("/user-product/appearance", headers=AUTH).json()["preferences"] == CHOICE
    stored = {key: value for (_workspace, key), (value, _stamp) in store.rows.items() if value}
    assert stored == {f"appearance.v1.account.{USERS['owner']['account_id']}": CHOICE}


def test_an_unreadable_stored_value_falls_back_field_by_field(store, as_user):
    key = (WS_OWNER, f"appearance.v1.account.{USERS['owner']['account_id']}")
    store.rows[key] = ({"theme": "dark", "palette": "retired", "accent": 7, "extra": "ignored"}, "2026-10-22T09:00:00+00:00")
    body = as_user("owner").get("/user-product/appearance", headers=AUTH).json()
    expected = {**appearance.DEFAULTS.model_dump(), "theme": "dark"}
    assert body["preferences"] == expected and body["stored"] is True
    store.rows[key] = ("not json at all", "2026-10-22T09:00:00+00:00")
    assert as_user("owner").get("/user-product/appearance", headers=AUTH).json()["preferences"] == appearance.DEFAULTS.model_dump()
