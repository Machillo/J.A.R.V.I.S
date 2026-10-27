"""SEC-01: the server enforces the legal acceptance for commercial users (real PostgreSQL + the app).

Before accepting the current Terms and Privacy Policy, a signed-in user reaches only their identity,
the acceptance, their privacy rights (export, deletion), support and the read-only operational
state; every other route answers 403 `legal_acceptance_required` without running. After accepting,
the same request runs. The Owner is unchanged (decision V1-5a). Without an answer from the database
the request does not run (503), because an unknown acceptance is not an acceptance.

Skipped when the embedded server (pgserver) is not installed. Synthetic accounts only.
"""
from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

pgserver = pytest.importorskip("pgserver")
psycopg2 = pytest.importorskip("psycopg2")

from backend import main  # noqa: E402
from backend.auth import legal, routes as auth_routes  # noqa: E402
from backend.core import database  # noqa: E402
from backend.user_product import routes as user_routes  # noqa: E402

pytestmark = pytest.mark.legal_gate

SCHEMA = """
CREATE TABLE accounts (id UUID PRIMARY KEY);
CREATE TABLE legal_acceptances (
    id BIGSERIAL PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    terms_version TEXT NOT NULL, privacy_version TEXT NOT NULL,
    terms_accepted_at TIMESTAMPTZ NOT NULL, privacy_accepted_at TIMESTAMPTZ NOT NULL,
    ip_address TEXT, user_agent TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(account_id, terms_version, privacy_version));
"""


@pytest.fixture
def app(tmp_path, monkeypatch):
    server = pgserver.get_server(str(os.environ.get("DINCR_PGSERVER_DIR") or tmp_path / "pg"), cleanup_mode="stop")
    admin = psycopg2.connect(server.get_uri())
    admin.autocommit = True
    name = f"legal_{os.getpid()}_{abs(hash(str(tmp_path))) % 10**8}"
    with admin.cursor() as c:
        c.execute(f"CREATE DATABASE {name}")
    uri = server.get_uri(name)
    conn = psycopg2.connect(uri)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(SCHEMA)
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    state = {"user": None, "ran": []}
    monkeypatch.setattr(main, "authenticate_access_token", lambda _token, **_kw: state["user"])
    monkeypatch.setattr(main, "disabled_feature_for_request", lambda *args, **kwargs: None)
    # The handlers behind the gate are replaced: this file tests whether a request runs, not its answer.
    monkeypatch.setattr(user_routes, "require_feature", lambda feature: True)
    monkeypatch.setattr(user_routes, "get_free_dashboard", lambda: state["ran"].append("dashboard") or {"ok": True})
    monkeypatch.setattr(auth_routes, "enrich_identity", lambda user: state["ran"].append("me") or {"id": user["id"]})
    monkeypatch.setattr(auth_routes, "export_current_account_data", lambda: state["ran"].append("export") or {"ok": True})
    monkeypatch.setattr(auth_routes, "delete_current_account", lambda: state["ran"].append("delete") or {"status": "OK"})
    client = TestClient(main.app, raise_server_exceptions=False)
    yield {"client": client, "cur": cur, "state": state}
    conn.close()
    with admin.cursor() as c:
        c.execute(f"DROP DATABASE {name} WITH (FORCE)")
    admin.close()


def _user(app, role: str = "user") -> str:
    account = str(uuid.uuid4())
    app["cur"].execute("INSERT INTO accounts(id) VALUES (%s)", (account,))
    app["state"]["user"] = {"id": 7, "account_id": account, "workspace_id": str(uuid.uuid4()), "role": role, "email": "x@correo.test"}
    return account


def _get(app, path: str, method: str = "GET", **kwargs):
    return app["client"].request(method, path, headers={"Authorization": "Bearer t", "Accept-Language": "es"}, **kwargs)


ACCEPT = {"accept_terms": True, "accept_privacy": True, "terms_version": legal.TERMS_VERSION, "privacy_version": legal.PRIVACY_VERSION}


def test_before_accepting_a_financial_route_does_not_run(app):
    _user(app)
    response = _get(app, "/user-product/free/dashboard")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "legal_acceptance_required"
    assert response.json()["detail"]["message"].startswith("Antes de continuar")
    assert app["state"]["ran"] == [], "the handler never ran"


def test_before_accepting_identity_privacy_rights_and_acceptance_stay_open(app):
    _user(app)
    assert _get(app, "/auth/me").status_code == 200
    assert _get(app, "/auth/me/export").status_code == 200
    assert _get(app, "/auth/me", method="DELETE").status_code == 200
    assert app["state"]["ran"] == ["me", "export", "delete"]
    for path in ["/product-ops/feature-flags", "/product-ops/health", "/product-ops/feedback"]:
        assert _get(app, path).status_code != 403, path


def test_after_accepting_the_same_request_runs(app):
    account = _user(app)
    assert _get(app, "/user-product/free/dashboard").status_code == 403
    accepted = _get(app, "/auth/legal/accept", method="POST", json=ACCEPT)
    assert accepted.status_code == 200 and accepted.json()["required"] is False
    response = _get(app, "/user-product/free/dashboard")
    assert response.status_code == 200
    assert app["state"]["ran"] == ["dashboard"]
    app["cur"].execute("SELECT count(*) FROM legal_acceptances WHERE account_id=%s", (account,))
    assert app["cur"].fetchone()[0] == 1


def test_an_acceptance_of_an_older_version_is_not_the_current_one(app):
    account = _user(app)
    app["cur"].execute(
        """INSERT INTO legal_acceptances(account_id, terms_version, privacy_version, terms_accepted_at, privacy_accepted_at)
           VALUES (%s, 'older-terms', %s, NOW(), NOW())""", (account, legal.PRIVACY_VERSION))
    assert _get(app, "/user-product/free/dashboard").status_code == 403


def test_the_owner_is_unchanged(app):
    _user(app, role="owner")
    assert _get(app, "/user-product/free/dashboard").status_code == 200
    assert app["state"]["ran"] == ["dashboard"]


def test_an_unknown_acceptance_is_not_an_acceptance(app, monkeypatch):
    _user(app)

    def unreachable(account_id):
        raise psycopg2.OperationalError("database unreachable")

    monkeypatch.setattr(legal, "_has_accepted", unreachable)
    response = _get(app, "/user-product/free/dashboard")
    assert response.status_code == 503
    assert app["state"]["ran"] == []


def test_a_request_without_an_account_waits_for_the_acceptance(app):
    _user(app)
    app["state"]["user"].pop("account_id")
    assert _get(app, "/user-product/free/dashboard").status_code == 403
