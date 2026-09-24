"""OAuth account-linking protection for Gmail and Outlook.

A stateful fake database (flows, connections, Vault, clock) and a fake OAuth
provider that enforces PKCE drive the real begin -> callback -> complete code.
"""
import base64
import copy
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from fastapi import HTTPException

from backend import main
from backend.auth.current_user import reset_current_user, set_current_user
from backend.user_product import gmail_service, mail_oauth
from backend.user_product import microsoft_mail as ms

A = {"id": 11, "account_id": "aaaaaaaa-0000-0000-0000-00000000000a", "workspace_id": "wa000000-0000-0000-0000-00000000000a", "role": "user"}
A2 = {**A, "workspace_id": "wa000000-0000-0000-0000-0000000000a2"}  # same account, second workspace
B = {"id": 22, "account_id": "bbbbbbbb-0000-0000-0000-00000000000b", "workspace_id": "wb000000-0000-0000-0000-00000000000b", "role": "user"}
GMAIL_CLIENT = ("google-client", "google-client-secret", "https://api.dincr.com/user-product/vip/gmail/callback")
MS_CLIENT = ("ms-client", "ms-client-secret", "https://api.dincr.com/user-product/vip/mail/microsoft/callback")


class Clock:
    now = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)


class FakeDb:
    def __init__(self):
        self.state = {"flows": {}, "connections": {}, "vault": {}}
        self.vip = {A["account_id"], B["account_id"]}

    def connect(self):
        return FakeConnection(self)


class FakeConnection:
    def __init__(self, db):
        self.db, self.work = db, copy.deepcopy(db.state)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False  # uncommitted work is discarded, like PostgresConnection

    def commit(self):
        self.db.state = copy.deepcopy(self.work)

    @staticmethod
    def _rows(rows):
        rows = [dict(row) for row in rows]
        return SimpleNamespace(fetchone=lambda: rows[0] if rows else None, fetchall=lambda: rows)

    def execute(self, query, params=()):
        q, now = " ".join(query.split()), Clock.now
        flows, connections, vault = self.work["flows"], self.work["connections"], self.work["vault"]
        if q.startswith("SELECT id,pending_secret_id FROM mail_oauth_flows"):
            return self._rows(f for f in flows.values()
                              if (f["expires_at"] <= now or f["status"] == "failed") and f["status"] != "completed"
                              and (not params or f["account_id"] == params[0]))
        if q.startswith("DELETE FROM mail_oauth_flows"):
            for flow_id in params[0]:
                flows.pop(flow_id, None)
            return self._rows([])
        if q.startswith("INSERT INTO mail_oauth_flows"):
            state_hash, provider, account, workspace, verifier, import_scope, minutes = params
            assert all(f["state_hash"] != state_hash for f in flows.values())
            flow_id = str(uuid4())
            flows[flow_id] = {"id": flow_id, "state_hash": state_hash, "provider": provider, "account_id": account,
                              "workspace_id": workspace, "status": "started", "code_verifier": verifier,
                              "import_scope": import_scope,
                              "completion_hash": None, "pending_secret_id": None, "mailbox_address": None,
                              "granted_scopes": None, "expires_at": now + timedelta(minutes=minutes)}
            return self._rows([])
        if q.startswith("UPDATE mail_oauth_flows SET status='callback'"):
            match = [f for f in flows.values() if f["state_hash"] == params[0] and f["provider"] == params[1]
                     and f["status"] == "started" and f["expires_at"] > now]
            for f in match:
                f["status"] = "callback"
            return self._rows({k: f[k] for k in ("id", "account_id", "workspace_id", "code_verifier")} for f in match)
        if q.startswith("SELECT provider,status FROM mail_oauth_flows WHERE state_hash"):
            return self._rows(f for f in flows.values() if f["state_hash"] == params[0])
        if q.startswith("UPDATE mail_oauth_flows SET status='failed',code_verifier=NULL"):
            f = flows.get(params[0])
            if f and f["status"] in ("started", "callback"):
                f.update(status="failed", code_verifier=None)
            return self._rows([])
        if q.startswith("UPDATE mail_oauth_flows SET status='authorized'"):
            completion_hash, secret_id, mailbox, scopes, minutes, flow_id = params
            f = flows.get(flow_id)
            if not f or f["status"] != "callback":
                return self._rows([])
            f.update(status="authorized", code_verifier=None, completion_hash=completion_hash, pending_secret_id=secret_id,
                     mailbox_address=mailbox, granted_scopes=scopes, expires_at=now + timedelta(minutes=minutes))
            return self._rows([{"id": flow_id}])
        if q.startswith("SELECT id,provider,account_id,workspace_id,status,completion_hash"):
            f = flows.get(params[0])
            return self._rows([{**f, "active": f["expires_at"] > now}] if f else [])
        if q.startswith("SELECT provider,account_id FROM mail_oauth_flows"):
            f = flows.get(params[0])
            return self._rows([f] if f else [])
        if q.startswith("UPDATE mail_oauth_flows SET status='failed',pending_secret_id=NULL"):
            flows[params[0]].update(status="failed", pending_secret_id=None, completion_hash=None)
            return self._rows([])
        if q.startswith("UPDATE mail_oauth_flows SET status='completed'"):
            assert "completion_hash" not in q  # kept for the initiator's idempotent retry
            flows[params[0]].update(status="completed", pending_secret_id=None)
            return self._rows([])
        if q.startswith("SELECT vault.create_secret"):
            secret_id = str(uuid4())
            vault[secret_id] = params[0]
            return self._rows([{"secret_id": secret_id}])
        if q.startswith("DELETE FROM vault.secrets"):
            vault.pop(params[0], None)
            return self._rows([])
        if q.startswith("SELECT 1 FROM account_subscriptions"):
            return self._rows([{"allowed": 1}] if params[0] in self.db.vip else [])
        if q.startswith("SELECT id,refresh_token_secret_id,granted_scopes,import_scope,import_since FROM finva_gmail_connections"):
            account, workspace, email = params
            return self._rows(c for c in connections.values()
                              if (c["account_id"], c["workspace_id"], c["google_email"]) == (account, workspace, email))
        if q.startswith("UPDATE finva_gmail_connections SET"):
            connection = connections[params[-1]]
            _legacy, secret_id, scopes, import_scope, since, restart, _restart = params[:7]
            connection.update(refresh_token_secret_id=secret_id, granted_scopes=scopes, status="active",
                              import_scope=import_scope, import_since=since)
            if restart:
                connection.update(initial_scan_page_token=None, initial_scan_completed_at=None)
            return self._rows([{"id": connection["id"]}])
        if q.startswith("INSERT INTO finva_gmail_connections"):
            account, workspace, legacy, email, secret_id, scopes, import_scope, since = params
            connection_id = len(connections) + 1
            connections[connection_id] = {"id": connection_id, "account_id": account, "workspace_id": workspace,
                                          "google_email": email, "refresh_token_secret_id": secret_id,
                                          "granted_scopes": scopes, "status": "active",
                                          "import_scope": import_scope, "import_since": since,
                                          "initial_scan_page_token": None, "initial_scan_completed_at": None}
            return self._rows([{"id": connection_id}])
        raise AssertionError(f"Unexpected query: {q[:90]}")


class FakeProvider:
    """Issues codes bound to a PKCE challenge and a mailbox; redeems each code once."""

    def __init__(self):
        self.codes, self.token_requests = {}, []

    def authorize(self, url: str, mailbox: str) -> tuple[str, str]:
        params = parse_qs(urlparse(url).query)
        code = f"code-{uuid4().hex}"
        self.codes[code] = (params["code_challenge"][0], mailbox)
        return code, params["state"][0]

    def token(self, url, data=None, **_kwargs):
        self.token_requests.append(dict(data))
        challenge, mailbox = self.codes.pop(data.get("code"), (None, None))
        verifier = data.get("code_verifier") or ""
        computed = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        if not challenge or computed != challenge:
            return SimpleNamespace(status_code=400, json=lambda: {"error": "invalid_grant"})
        return SimpleNamespace(status_code=200, json=lambda: {
            "access_token": f"access-for-{mailbox}", "refresh_token": f"refresh-for-{mailbox}",
            "scope": "https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/User.Read"})


@pytest.fixture
def env(monkeypatch):
    db, provider, synced = FakeDb(), FakeProvider(), []
    for module in (mail_oauth, gmail_service, ms):
        monkeypatch.setattr(module, "get_connection", db.connect)
    monkeypatch.setattr(gmail_service, "require_gmail_consent", lambda: None)
    monkeypatch.setattr(ms, "require_gmail_consent", lambda: None)
    monkeypatch.setattr(gmail_service, "_google_config", lambda: GMAIL_CLIENT)
    monkeypatch.setattr(ms, "_config", lambda: MS_CLIENT)
    monkeypatch.setattr(gmail_service.requests, "post", provider.token)
    monkeypatch.setattr(gmail_service, "_credentials", lambda token: SimpleNamespace(users=lambda: SimpleNamespace(
        getProfile=lambda userId: SimpleNamespace(execute=lambda: {"emailAddress": token.removeprefix("refresh-for-")}))))
    monkeypatch.setattr(ms, "_graph_get", lambda token, path, *_a: {"mail": token.removeprefix("access-for-")} if path == "/me" else {"value": []})
    monkeypatch.setattr(gmail_service, "_financial_user_id_for_account", lambda account_id: 900)
    monkeypatch.setattr(gmail_service, "_after_gmail_connected", lambda connection_id: synced.append(("gmail", connection_id)))
    monkeypatch.setattr(ms, "sync_connection", lambda connection_id: synced.append(("microsoft", connection_id)))
    return SimpleNamespace(db=db, provider=provider, synced=synced)


def _as(user, fn, *args):
    token = set_current_user(user)
    try:
        return fn(*args)
    finally:
        reset_current_user(token)


BEGIN = {"gmail": lambda: gmail_service.begin_gmail_connection(), "microsoft": lambda: ms.begin_connection()}
CALLBACK = {"gmail": gmail_service.finish_gmail_connection, "microsoft": ms.finish_connection}


def start(provider, user):
    return _as(user, BEGIN[provider])["authorization_url"]


def callback(provider, code, state, error=None):
    location = CALLBACK[provider](code=code, state=state, error=error).headers["location"]
    params = {key: values[0] for key, values in parse_qs(urlparse(location).query).items()}
    return params.get(provider), params


def complete(user, params):
    return _as(user, mail_oauth.complete_mail_connection, params.get("flow"), params.get("completion"))


def connections_of(env, user):
    return [(c["google_email"], c["workspace_id"]) for c in env.db.state["connections"].values() if c["account_id"] == user["account_id"]]


PROVIDERS = ["gmail", "microsoft"]


@pytest.mark.parametrize("provider", PROVIDERS)
def test_initiator_completes_the_flow_and_the_mailbox_is_attached(env, provider):
    url = start(provider, A)
    query = parse_qs(urlparse(url).query)
    assert query["code_challenge_method"] == ["S256"] and len(query["state"][0]) >= 43
    status, params = callback(provider, *env.provider.authorize(url, "a@example.com"))
    assert status == "authorized" and "flow" in params and "completion" in params
    assert connections_of(env, A) == []  # the callback alone never attaches a mailbox
    assert complete(A, params) == {"status": "connected", "provider": provider}
    assert connections_of(env, A) == [("a@example.com", A["workspace_id"])]
    assert env.synced == [(provider, 1)]
    assert env.provider.token_requests[0]["code_verifier"]  # PKCE verifier sent to the provider
    flow = next(iter(env.db.state["flows"].values()))
    assert flow["status"] == "completed" and flow["pending_secret_id"] is None and flow["code_verifier"] is None


@pytest.mark.parametrize("provider", PROVIDERS)
def test_account_linking_csrf_attackers_link_cannot_attach_the_victims_mailbox(env, provider):
    """The attacker (A) starts a flow and sends the authorization link to the victim (B)."""
    attacker_link = start(provider, A)
    # The victim consents with their own mailbox in their own browser.
    status, params = callback(provider, *env.provider.authorize(attacker_link, "victim@example.com"))
    assert status == "authorized"
    # The deep link reaches the victim's device; the victim's DINCR session is not the initiator.
    with pytest.raises(HTTPException) as refused:
        complete(B, params)
    assert refused.value.status_code == 403
    # The attacker never receives the completion code and cannot redeem the flow.
    for guess in ({"flow": params["flow"], "completion": "guess"}, {"flow": params["flow"], "completion": params["flow"]}):
        with pytest.raises(HTTPException) as guessed:
            complete(A, guess)
        assert guessed.value.status_code == 409
    # Even with the leaked completion code the flow is already closed.
    with pytest.raises(HTTPException):
        complete(A, params)
    assert connections_of(env, A) == [] and connections_of(env, B) == []
    assert env.db.state["vault"] == {}  # the victim's refresh token was discarded


@pytest.mark.parametrize("provider", PROVIDERS)
def test_altered_missing_and_expired_states_are_rejected_before_any_token_exchange(env, provider):
    url = start(provider, A)
    code, state = env.provider.authorize(url, "a@example.com")
    assert callback(provider, code, state[:-2] + ("AA" if not state.endswith("AA") else "BB"))[0] == "invalid_state"
    assert callback(provider, code, None)[0] == "invalid_state"
    assert callback(provider, code, "")[0] == "invalid_state"
    Clock.now += timedelta(minutes=11)
    try:
        assert callback(provider, code, state)[0] == "invalid_state"
    finally:
        Clock.now -= timedelta(minutes=11)
    assert env.provider.token_requests == []


@pytest.mark.parametrize("provider", PROVIDERS)
def test_state_is_single_use(env, provider):
    url = start(provider, A)
    code, state = env.provider.authorize(url, "a@example.com")
    assert callback(provider, code, state)[0] == "authorized"
    status, params = callback(provider, code, state)
    assert status == "already_processed"  # still rejected: no exchange, no completion code
    assert "completion" not in params and "flow" not in params
    assert len(env.provider.token_requests) == 1


@pytest.mark.parametrize(("started", "used"), [("gmail", "microsoft"), ("microsoft", "gmail")])
def test_state_cannot_be_used_with_another_provider(env, started, used):
    code, state = env.provider.authorize(start(started, A), "a@example.com")
    assert callback(used, code, state)[0] == "invalid_state"
    assert env.provider.token_requests == []
    assert callback(started, code, state)[0] == "authorized"  # the original provider still works


@pytest.mark.parametrize("provider", PROVIDERS)
def test_completion_cannot_switch_account_or_workspace(env, provider):
    _, params = callback(provider, *env.provider.authorize(start(provider, A), "a@example.com"))
    with pytest.raises(HTTPException) as other_workspace:
        complete(A2, params)
    assert other_workspace.value.status_code == 403
    assert connections_of(env, A) == [] and env.db.state["vault"] == {}


def test_concurrent_users_cannot_cross_their_connections(env):
    link_a, link_b = start("gmail", A), start("microsoft", B)
    _, params_b = callback("microsoft", *env.provider.authorize(link_b, "b@example.com"))
    _, params_a = callback("gmail", *env.provider.authorize(link_a, "a@example.com"))
    with pytest.raises(HTTPException):
        complete(A, params_b)  # A tries B's completion: rejected and B's pending token discarded
    complete(A, params_a)
    assert connections_of(env, A) == [("a@example.com", A["workspace_id"])]
    assert connections_of(env, B) == []
    # B restarts cleanly and only ever gets their own mailbox.
    _, params_b2 = callback("microsoft", *env.provider.authorize(start("microsoft", B), "b@example.com"))
    complete(B, params_b2)
    assert connections_of(env, B) == [("b@example.com", B["workspace_id"])]


def test_workspaces_of_one_account_stay_isolated(env):
    _, first = callback("gmail", *env.provider.authorize(start("gmail", A), "a@example.com"))
    _, second = callback("gmail", *env.provider.authorize(start("gmail", A2), "a@example.com"))
    complete(A, first)
    complete(A2, second)
    assert sorted(connections_of(env, A)) == sorted([("a@example.com", A["workspace_id"]), ("a@example.com", A2["workspace_id"])])


@pytest.mark.parametrize("provider", PROVIDERS)
def test_legitimate_reconnection_replaces_the_token(env, provider):
    for _ in range(2):
        _, params = callback(provider, *env.provider.authorize(start(provider, A), "a@example.com"))
        complete(A, params)
    assert connections_of(env, A) == [("a@example.com", A["workspace_id"])]
    assert list(env.db.state["vault"].values()) == ["refresh-for-a@example.com"]  # old secret deleted


@pytest.mark.parametrize("provider", PROVIDERS)
def test_pkce_blocks_a_code_issued_for_another_flow(env, provider):
    """Authorization-code injection: a code minted for flow X is replayed into flow Y."""
    stolen_code, _ = env.provider.authorize(start(provider, A), "victim@example.com")
    _, own_state = env.provider.authorize(start(provider, A), "a@example.com")
    assert callback(provider, stolen_code, own_state)[0] == "exchange_failed"
    assert connections_of(env, A) == [] and env.db.state["vault"] == {}


@pytest.mark.parametrize("provider", PROVIDERS)
def test_provider_error_and_non_vip_fail_closed(env, provider):
    code, state = env.provider.authorize(start(provider, A), "a@example.com")
    assert callback(provider, None, state, error="access_denied")[0] == "denied"
    assert callback(provider, code, state)[0] == "invalid_state"  # the state was consumed
    env.db.vip.discard(A["account_id"])
    code, state = env.provider.authorize(start(provider, A), "a@example.com")
    assert callback(provider, code, state)[0] == "vip_required"
    assert env.db.state["vault"] == {}


@pytest.mark.parametrize("provider", PROVIDERS)
def test_downgrade_before_completion_attaches_nothing(env, provider):
    _, params = callback(provider, *env.provider.authorize(start(provider, A), "a@example.com"))
    env.db.vip.discard(A["account_id"])
    with pytest.raises(HTTPException) as error:
        complete(A, params)
    assert error.value.status_code == 403 and connections_of(env, A) == []


def test_abandoned_flows_release_their_pending_tokens(env):
    callback("gmail", *env.provider.authorize(start("gmail", A), "a@example.com"))
    assert len(env.db.state["vault"]) == 1
    Clock.now += timedelta(minutes=11)
    try:
        with env.db.connect() as conn:
            mail_oauth.discard_stale_flows(conn)
            conn.commit()
    finally:
        Clock.now -= timedelta(minutes=11)
    assert env.db.state["vault"] == {} and env.db.state["flows"] == {}


@pytest.mark.parametrize("provider", PROVIDERS)
def test_codes_tokens_states_and_secrets_never_reach_logs(env, provider, caplog):
    with caplog.at_level(logging.DEBUG):
        url = start(provider, A)
        code, state = env.provider.authorize(url, "a@example.com")
        callback(provider, code, state[:-1] + "x")  # rejected attempt is logged
        _, params = callback(provider, code, state)
        with pytest.raises(HTTPException):
            complete(B, params)  # rejected completion is logged
    verifier = env.provider.token_requests[0]["code_verifier"]
    sensitive = [code, state, params["completion"], verifier, "refresh-for-a@example.com", "access-for-a@example.com",
                 GMAIL_CLIENT[1], MS_CLIENT[1], "a@example.com"]
    assert not any(value in caplog.text for value in sensitive)


def test_only_the_provider_callbacks_are_public():
    for path in ("/user-product/vip/gmail/callback", "/user-product/vip/mail/microsoft/callback"):
        assert main._is_public_path(path) is True
    for path in ("/user-product/vip/mail/oauth/complete", "/user-product/vip/gmail/connect",
                 "/user-product/vip/mail/microsoft/connect", "/user-product/vip/gmail/sync",
                 "/user-product/vip/gmail"):
        assert main._is_public_path(path) is False


# --- Duplicate deliveries (retried GET, restored tab, OS replaying the deep link) ---

@pytest.mark.parametrize("provider", PROVIDERS)
def test_replayed_callback_never_breaks_the_first_connection(env, provider):
    code, state = env.provider.authorize(start(provider, A), "a@example.com")
    status, first = callback(provider, code, state)
    assert status == "authorized"
    # The browser delivers the same provider redirect again before and after completion.
    assert callback(provider, code, state)[0] == "already_processed"
    assert complete(A, first) == {"status": "connected", "provider": provider}
    replay_status, replay = callback(provider, code, state)
    assert replay_status == "already_processed" and "completion" not in replay
    assert connections_of(env, A) == [("a@example.com", A["workspace_id"])]
    assert len(env.provider.token_requests) == 1 and env.synced == [(provider, 1)]


@pytest.mark.parametrize("provider", PROVIDERS)
def test_each_return_link_is_unique(env, provider):
    code, state = env.provider.authorize(start(provider, A), "a@example.com")
    _, first = callback(provider, code, state)
    _, second = callback(provider, code, state)
    _, third = callback(provider, code, state)
    assert len({first["ret"], second["ret"], third["ret"]}) == 3


@pytest.mark.parametrize("provider", PROVIDERS)
def test_initiator_can_confirm_a_completion_whose_response_was_lost(env, provider):
    _, params = callback(provider, *env.provider.authorize(start(provider, A), "a@example.com"))
    assert complete(A, params)["status"] == "connected"
    # The app retries because the first response never arrived: same result, nothing re-attached.
    assert complete(A, params) == {"status": "connected", "provider": provider}
    assert connections_of(env, A) == [("a@example.com", A["workspace_id"])]
    assert env.synced == [(provider, 1)]
    assert list(env.db.state["vault"].values()) == ["refresh-for-a@example.com"]


@pytest.mark.parametrize("provider", PROVIDERS)
def test_completed_flow_rejects_other_sessions_wrong_codes_and_expiry(env, provider):
    _, params = callback(provider, *env.provider.authorize(start(provider, A), "a@example.com"))
    complete(A, params)
    for user in (B, A2):
        with pytest.raises(HTTPException) as other:
            complete(user, params)
        assert other.value.status_code == 403
    with pytest.raises(HTTPException) as wrong:
        complete(A, {**params, "completion": "not-the-code"})
    assert wrong.value.status_code == 409
    Clock.now += timedelta(minutes=11)
    try:
        with pytest.raises(HTTPException) as expired:
            complete(A, params)
        assert expired.value.status_code == 409
    finally:
        Clock.now -= timedelta(minutes=11)
    flow = next(iter(env.db.state["flows"].values()))
    assert flow["status"] == "completed"  # the rejected replays did not disturb the connection
    assert connections_of(env, A) == [("a@example.com", A["workspace_id"])]
    assert connections_of(env, B) == []


@pytest.mark.parametrize("provider", PROVIDERS)
def test_authorized_flow_expires_before_completion(env, provider):
    _, params = callback(provider, *env.provider.authorize(start(provider, A), "a@example.com"))
    Clock.now += timedelta(minutes=11)
    try:
        with pytest.raises(HTTPException) as expired:
            complete(A, params)
        assert expired.value.status_code == 409
    finally:
        Clock.now -= timedelta(minutes=11)
    assert connections_of(env, A) == []


@pytest.mark.parametrize(("started", "used"), [("gmail", "microsoft"), ("microsoft", "gmail")])
def test_replay_on_another_provider_is_not_reported_as_processed(env, started, used):
    code, state = env.provider.authorize(start(started, A), "a@example.com")
    assert callback(started, code, state)[0] == "authorized"
    assert callback(used, code, state)[0] == "invalid_state"
