"""OAuth account-linking protection for Gmail and Outlook.

A stateful fake database (flows, connections, Vault, clock) and a fake OAuth
provider that enforces PKCE drive the real begin -> callback -> complete code.
"""
import base64
import copy
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import psycopg2
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
        self.state = {"flows": {}, "connections": {}, "vault": {}, "vault_owner": {}, "takeovers": []}
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

    def rollback(self):
        self.work = copy.deepcopy(self.db.state)

    @staticmethod
    def _rows(rows):
        rows = [dict(row) for row in rows]
        return SimpleNamespace(fetchone=lambda: rows[0] if rows else None, fetchall=lambda: rows)

    def execute(self, query, params=()):
        q, now = " ".join(query.split()), Clock.now
        flows, connections, vault = self.work["flows"], self.work["connections"], self.work["vault"]
        takeovers, vault_owner = self.work["takeovers"], self.work["vault_owner"]
        if q.startswith("SELECT id,account_id,pending_secret_id FROM mail_oauth_flows"):
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
                              "granted_scopes": None, "provider_subject": None, "provider_tenant": None,
                              "expires_at": now + timedelta(minutes=minutes)}
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
            completion_hash, secret_id, mailbox, scopes, subject, tenant, minutes, flow_id = params
            f = flows.get(flow_id)
            if not f or f["status"] != "callback":
                return self._rows([])
            f.update(status="authorized", code_verifier=None, completion_hash=completion_hash, pending_secret_id=secret_id,
                     mailbox_address=mailbox, granted_scopes=scopes, provider_subject=subject, provider_tenant=tenant,
                     expires_at=now + timedelta(minutes=minutes))
            return self._rows([{"id": flow_id}])
        if q.startswith("SELECT id,provider,account_id,workspace_id,status,completion_hash"):
            f = flows.get(params[0])
            return self._rows([{**f, "active": f["expires_at"] > now}] if f else [])
        if q.startswith("SELECT status,pending_secret_id FROM mail_oauth_flows WHERE id=%s::uuid FOR UPDATE"):
            f = flows.get(params[0])
            return self._rows([f] if f else [])
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
        if q.startswith("SELECT dincr_private.mail_secret_create"):
            secret_id = str(uuid4())
            vault[secret_id] = params[0]
            vault_owner[secret_id] = params[1]
            return self._rows([{"secret_id": secret_id}])
        if q.startswith("SELECT dincr_private.mail_secret_delete"):
            assert vault_owner.get(params[0], params[1]) == params[1], "a token deleted on behalf of another account"
            vault.pop(params[0], None)
            return self._rows([])
        if q.startswith("SELECT s.access_source FROM account_subscriptions"):
            # A VIP here holds a grant that is not a store subscription (the store path has its own PG tests).
            return self._rows([{"access_source": "courtesy"}] if params[0] in self.db.vip else [])
        if q.startswith("SELECT id,account_id,status,refresh_token_secret_id,mailbox_key,mailbox_email FROM finva_gmail_connections WHERE status<>'disabled'"):
            account, workspace, key, emails, display, scope = params
            return self._rows(c for c in sorted(connections.values(), key=lambda c: c["id"])
                              if c["status"] != "disabled" and (c["account_id"], c["workspace_id"]) != (account, workspace)
                              and (c["mailbox_key"] == key or c["mailbox_email"] in emails
                                   or (c["mailbox_email"] is None and c["google_email"].strip().lower() == display
                                       and scope in c["granted_scopes"])))
        if q.startswith("UPDATE finva_gmail_connections SET status='disabled',history_id=NULL,watch_expiration=NULL,initial_scan_page_token=NULL, last_error=%s"):
            connections[params[1]].update(status="disabled", last_error=params[0])
            return self._rows([])
        if q.startswith("INSERT INTO mail_connection_takeovers"):
            takeovers.append(dict(zip(("provider", "previous_connection_id", "previous_account_id", "new_account_id", "reason"), params)))
            return self._rows([])
        if q.startswith("SELECT id,refresh_token_secret_id,granted_scopes,import_scope,import_since") and "FROM finva_gmail_connections WHERE account_id" in q:
            account, workspace, key, email, display = params
            by_display = "OR lower(btrim(google_email))=%s)" in " ".join(query.split())  # Outlook: own row by display address
            matches = [c for c in connections.values() if (c["account_id"], c["workspace_id"]) == (account, workspace)
                       and (c["mailbox_key"] == key or c["mailbox_email"] == email
                            or ((by_display or c["mailbox_email"] is None) and c["google_email"].strip().lower() == display))]
            return self._rows(sorted(matches, key=lambda c: (c["status"] == "disabled", c["id"]))[:1])
        if q.startswith("UPDATE finva_gmail_connections SET"):
            connection = connections[params[-1]]
            _legacy, secret_id, scopes, display, email, key, subject = params[:7]
            import_scope, since, restart = params[-5], params[-4], params[-3]
            connection.update(refresh_token_secret_id=secret_id, granted_scopes=scopes, status="active",
                              google_email=display, mailbox_email=email, mailbox_key=key, provider_subject=subject,
                              import_scope=import_scope, import_since=since)
            if restart:
                connection.update(initial_scan_page_token=None, initial_scan_completed_at=None)
            return self._rows([{"id": connection["id"]}])
        if q.startswith("INSERT INTO finva_gmail_connections"):
            account, workspace, legacy, display, email, key, subject = params[:7]
            secret_id, scopes, import_scope, since = params[-4:]
            for other in connections.values():  # the live-mailbox unique indexes
                if other["status"] != "disabled" and (other["mailbox_key"] == key or other["mailbox_email"] == email):
                    raise psycopg2.errors.UniqueViolation("duplicate live mailbox")
            connection_id = len(connections) + 1
            connections[connection_id] = {"id": connection_id, "account_id": account, "workspace_id": workspace,
                                          "google_email": display, "mailbox_email": email, "mailbox_key": key,
                                          "provider_subject": subject, "refresh_token_secret_id": secret_id,
                                          "granted_scopes": scopes, "status": "active",
                                          "import_scope": import_scope, "import_since": since,
                                          "initial_scan_page_token": None, "initial_scan_completed_at": None}
            return self._rows([{"id": connection_id}])
        raise AssertionError(f"Unexpected query: {q[:90]}")


class FakeProvider:
    """Issues codes bound to a PKCE challenge and a mailbox; redeems each code once."""

    def __init__(self):
        self.codes, self.token_requests, self.subjects, self.urls, self.revoked = {}, [], {}, [], []
        self.google_scope = "https://www.googleapis.com/auth/gmail.readonly"

    def authorize(self, url: str, mailbox: str) -> tuple[str, str]:
        params = parse_qs(urlparse(url).query)
        code = f"code-{uuid4().hex}"
        self.codes[code] = (params["code_challenge"][0], mailbox)
        return code, params["state"][0]

    def token(self, url, data=None, **_kwargs):
        self.urls.append(url)
        if url.endswith("/tokeninfo"):  # Google reports the account id of the token it issued
            mailbox = data["access_token"].removeprefix("access-for-")
            return SimpleNamespace(status_code=200, json=lambda: {
                "aud": GMAIL_CLIENT[0], "azp": GMAIL_CLIENT[0], "sub": self.subjects.get(mailbox, str(abs(hash(mailbox)) % 10**12))})
        if url.endswith("/revoke"):
            self.revoked.append(data["token"])
            return SimpleNamespace(status_code=200, json=lambda: {})
        self.token_requests.append(dict(data))
        challenge, mailbox = self.codes.pop(data.get("code"), (None, None))
        verifier = data.get("code_verifier") or ""
        computed = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        if not challenge or computed != challenge:
            return SimpleNamespace(status_code=400, json=lambda: {"error": "invalid_grant"})
        scope = ("https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/User.Read" if "microsoft" in url
                 else self.google_scope)
        return SimpleNamespace(status_code=200, json=lambda: {
            "access_token": f"access-for-{mailbox}", "refresh_token": f"refresh-for-{mailbox}", "scope": scope})


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
    def graph_get(token, path, *_a):
        """A personal Microsoft account per mailbox: the same mailbox signs in as the same principal."""
        mailbox = token.removeprefix("access-for-")
        principal = mailbox.strip().lower()
        return ({"mail": mailbox, "id": provider.subjects.get(principal, f"{abs(hash(principal)) % 16**16:016x}")}
                if path == "/me" else {"value": []})

    monkeypatch.setattr(ms, "_graph_get", graph_get)
    monkeypatch.setattr(gmail_service, "_financial_user_id_for_account", lambda account_id: 900)
    monkeypatch.setattr(gmail_service, "_after_gmail_connected", lambda connection_id: synced.append(("gmail", connection_id)))
    monkeypatch.setattr(ms, "sync_connection", lambda connection_id, **_kwargs: synced.append(("microsoft", connection_id)))
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


def test_one_mailbox_is_never_live_in_two_workspaces_of_one_account(env):
    _, first = callback("gmail", *env.provider.authorize(start("gmail", A), "a@example.com"))
    _, second = callback("gmail", *env.provider.authorize(start("gmail", A2), "a@example.com"))
    complete(A, first)
    with pytest.raises(HTTPException) as refused:
        complete(A2, second)
    assert refused.value.status_code == 409 and refused.value.detail == mail_oauth.MAILBOX_UNAVAILABLE
    assert connections_of(env, A) == [("a@example.com", A["workspace_id"])]


def _connect(env, provider, user, mailbox):
    _, params = callback(provider, *env.provider.authorize(start(provider, user), mailbox))
    return complete(user, params), params


@pytest.mark.parametrize(("first", "second"), [("gmail", "gmail"), ("microsoft", "microsoft")])
def test_another_account_cannot_connect_a_live_mailbox(env, first, second):
    _connect(env, first, A, "shared@example.com")
    _, params = callback(second, *env.provider.authorize(start(second, B), "Shared@Example.com "))
    with pytest.raises(HTTPException) as refused:
        complete(B, params)
    # Generic: the same text whatever the reason, with no address, account or workspace in it.
    assert refused.value.status_code == 409 and refused.value.detail == mail_oauth.MAILBOX_UNAVAILABLE
    assert "shared" not in refused.value.detail.lower() and A["account_id"] not in refused.value.detail
    assert connections_of(env, B) == []
    # B's refresh token is not left behind, and the flow cannot be retried.
    assert len(env.db.state["vault"]) == 1
    assert env.db.state["flows"][params["flow"]]["status"] == "failed"
    with pytest.raises(HTTPException) as replayed:
        complete(B, params)
    assert replayed.value.status_code == 409


def _row_of(env, user):
    return next(c for c in env.db.state["connections"].values() if c["account_id"] == user["account_id"])


@pytest.mark.parametrize(("stale", "reason"), [("reauthorization", "access_lost"), ("plan", "plan_inactive")])
@pytest.mark.parametrize("provider", PROVIDERS)
def test_a_stale_mailbox_is_taken_over_by_a_new_real_consent(env, provider, stale, reason):
    """A lost provider access or no longer has VIP; B proves control of the mailbox through the provider."""
    _connect(env, provider, A, "shared@example.com")
    old = _row_of(env, A)
    old_secret = old["refresh_token_secret_id"]
    if stale == "reauthorization":
        old["status"] = "reauthorization_required"
    else:
        env.db.vip.discard(A["account_id"])
    result, _params = _connect(env, provider, B, "shared@example.com")

    assert result == {"status": "connected", "provider": provider}  # nothing about A is returned
    new = _row_of(env, B)
    assert new["status"] == "active" and new["refresh_token_secret_id"] != old_secret
    previous = env.db.state["connections"][old["id"]]
    assert previous["status"] == "disabled" and previous["last_error"] == mail_oauth.MAILBOX_TAKEN_OVER
    assert previous["account_id"] == A["account_id"]  # A keeps its row (and everything it imported): nothing moves
    assert old_secret not in env.db.state["vault"]  # A's token is deleted, never reused
    assert list(env.db.state["vault"]) == [new["refresh_token_secret_id"]]
    assert not [url for url in env.provider.urls if "revoke" in url]  # revoking A's token would kill B's grant too
    assert env.db.state["takeovers"] == [{"provider": provider, "previous_connection_id": old["id"],
                                          "previous_account_id": A["account_id"], "new_account_id": B["account_id"],
                                          "reason": reason}]


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a_live_mailbox_of_a_vip_account_is_never_taken_over(env, provider):
    _connect(env, provider, A, "shared@example.com")
    _, params = callback(provider, *env.provider.authorize(start(provider, B), "shared@example.com"))
    with pytest.raises(HTTPException) as refused:
        complete(B, params)
    assert refused.value.detail == mail_oauth.MAILBOX_UNAVAILABLE
    assert _row_of(env, A)["status"] == "active" and env.db.state["takeovers"] == []


def test_a_takeover_needs_the_same_mailbox_not_a_similar_address(env):
    _connect(env, "gmail", A, "shared@example.com")
    _row_of(env, A)["status"] = "reauthorization_required"
    _connect(env, "gmail", B, "shared.other@example.com")
    assert _row_of(env, A)["status"] == "reauthorization_required" and env.db.state["takeovers"] == []


@pytest.mark.parametrize("variant", ["FirstLast@gmail.com", "first.last+bank@gmail.com", "first.last@googlemail.com"])
def test_gmail_address_variants_are_one_mailbox(env, variant):
    _connect(env, "gmail", A, "first.last@gmail.com")
    env.provider.subjects[variant.lower()] = "7" * 12  # even with another account id, the address is the same mailbox
    _, params = callback("gmail", *env.provider.authorize(start("gmail", B), variant))
    with pytest.raises(HTTPException) as refused:
        complete(B, params)
    assert refused.value.detail == mail_oauth.MAILBOX_UNAVAILABLE


@pytest.mark.parametrize("provider", PROVIDERS)
def test_the_provider_identity_follows_a_renamed_address(env, provider):
    """Reconnecting the same provider account under a new address reuses its connection."""
    stable = "0123456789abcdef" if provider == "microsoft" else "123456789012"
    env.provider.subjects.update({"old@example.com": stable, "new@example.com": stable})
    _connect(env, provider, A, "old@example.com")
    first = _row_of(env, A)
    _connect(env, provider, A, "new@example.com")
    rows = [c for c in env.db.state["connections"].values() if c["account_id"] == A["account_id"]]
    assert [c["id"] for c in rows] == [first["id"]] and rows[0]["google_email"] == "new@example.com"
    expected = f"google:{stable}" if provider == "gmail" else f"microsoft:{ms.CONSUMER_TENANT}:{stable}"
    assert rows[0]["mailbox_key"] == expected


def test_a_google_account_id_is_trusted_only_for_dincrs_client(env, monkeypatch):
    def foreign(url, data=None, **_kwargs):
        return SimpleNamespace(status_code=200, json=lambda: {"aud": "someone-else", "azp": "someone-else", "sub": "999"})
    monkeypatch.setattr(gmail_service.requests, "post", foreign)
    assert gmail_service._google_subject("token", GMAIL_CLIENT[0]) is None


def test_canonical_mailbox():
    assert mail_oauth.canonical_mailbox(" First.Last+x@GoogleMail.com ") == "firstlast@gmail.com"
    assert mail_oauth.canonical_mailbox("first.last+x@outlook.com") == "first.last+x@outlook.com"
    assert mail_oauth.mailbox_key("gmail", "a@gmail.com") == "email:gmail:a@gmail.com"
    assert mail_oauth.mailbox_key("microsoft", "a@x.com", "id") == "email:microsoft:a@x.com"  # no tenant: address identity
    assert mail_oauth.mailbox_email("gmail", "a@x.com") != mail_oauth.mailbox_email("microsoft", "a@x.com")


@pytest.mark.parametrize("stale", [False, True])
def test_a_microsoft_account_reporting_a_gmail_address_never_touches_that_gmail_mailbox(env, stale):
    """A Microsoft sign-in name or mail attribute can be a gmail.com address: it is not that Gmail mailbox."""
    _connect(env, "gmail", A, "victim@gmail.com")
    if stale:
        _row_of(env, A)["status"] = "reauthorization_required"
    assert _connect(env, "microsoft", B, "victim@gmail.com")[0] == {"status": "connected", "provider": "microsoft"}
    assert _row_of(env, A)["status"] == ("reauthorization_required" if stale else "active")
    assert env.db.state["takeovers"] == []
    assert len(env.db.state["vault"]) == 2  # the Gmail token is untouched


def test_a_disconnected_mailbox_can_be_connected_by_whoever_controls_it(env):
    """A connects X, then disconnects it (token deleted, row disabled); B then proves control of X."""
    _connect(env, "gmail", A, "shared@example.com")
    next(iter(env.db.state["connections"].values()))["status"] = "disabled"
    assert _connect(env, "gmail", B, "shared@example.com")[0] == {"status": "connected", "provider": "gmail"}
    assert connections_of(env, B) == [("shared@example.com", B["workspace_id"])]
    # While B holds it, A cannot take it back.
    _, params = callback("gmail", *env.provider.authorize(start("gmail", A), "shared@example.com"))
    with pytest.raises(HTTPException) as refused:
        complete(A, params)
    assert refused.value.detail == mail_oauth.MAILBOX_UNAVAILABLE


@pytest.mark.parametrize("provider", PROVIDERS)
def test_losing_the_database_race_is_the_same_generic_refusal(env, monkeypatch, provider):
    """Two completions pass the check at once; the unique index rejects the second insert."""
    import psycopg2

    def lose_the_race(*_args, **_kwargs):
        raise psycopg2.errors.UniqueViolation()

    monkeypatch.setattr(gmail_service if provider == "gmail" else ms,
                        "_attach_gmail_connection" if provider == "gmail" else "_attach_microsoft_connection", lose_the_race)
    _, params = callback(provider, *env.provider.authorize(start(provider, B), "shared@example.com"))
    with pytest.raises(HTTPException) as refused:
        complete(B, params)
    assert refused.value.status_code == 409 and refused.value.detail == mail_oauth.MAILBOX_UNAVAILABLE
    assert env.db.state["vault"] == {} and env.db.state["flows"][params["flow"]]["status"] == "failed"


def test_a_refusal_never_deletes_a_token_another_completion_already_used(env, monkeypatch):
    """The refusal's cleanup runs after its rollback: if the same flow was completed
    meanwhile (another device, same account), its token and result are left alone."""
    _, params = callback("gmail", *env.provider.authorize(start("gmail", B), "b@example.com"))
    flow_id = params["flow"]

    def completed_elsewhere_then_refused(conn, flow, _legacy):
        env.db.state["flows"][flow_id].update(status="completed", pending_secret_id=None)
        raise HTTPException(status_code=409, detail=mail_oauth.MAILBOX_UNAVAILABLE)

    monkeypatch.setattr(gmail_service, "_attach_gmail_connection", completed_elsewhere_then_refused)
    secret = env.db.state["flows"][flow_id]["pending_secret_id"]
    with pytest.raises(HTTPException):
        complete(B, params)
    assert env.db.state["flows"][flow_id]["status"] == "completed"
    assert secret in env.db.state["vault"]


def test_status_writers_never_revive_a_disconnected_mailbox():
    """A sync or token refresh that finishes after a disconnect must not make the row live again:
    it would hold the mailbox against every other account with no usable token."""
    import inspect
    import re

    gmail = inspect.getsource(gmail_service)
    outlook = inspect.getsource(ms)
    success = re.search(r"SET status='active',last_sync_at=NOW\(\).*?WHERE id=%s([^\"]*)\"\"\"", gmail, re.S)
    assert success and "status<>'disabled'" in success.group(1)
    assert re.search(r"SET status='reauthorization_required',last_error=%s,updated_at=NOW\(\)\s+WHERE id=%s AND status='active'", gmail)
    assert "SET status='reauthorization_required' WHERE id=%s AND status='active'" in outlook


@pytest.mark.parametrize("provider", PROVIDERS)
def test_reconnecting_your_own_mailbox_still_works(env, provider):
    _connect(env, provider, A, "a@example.com")
    assert _connect(env, provider, A, "A@example.com")[0]["status"] == "connected"
    assert connections_of(env, A) == [("a@example.com", A["workspace_id"])]


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


@pytest.mark.parametrize(("status", "stored"), [("disabled", False), ("active", True)])
def test_a_rotated_outlook_token_is_never_stored_on_a_disconnected_or_taken_over_row(monkeypatch, status, stored):
    """A sync that started before a takeover must not give the old row a live token back."""
    created = []

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def execute(self, query, params=()):
            row = {"refresh_token_secret_id": "old-secret", "status": status} if query.lstrip().startswith("SELECT") else None
            return SimpleNamespace(fetchone=lambda: row)

        def commit(self):
            pass

    monkeypatch.setattr(ms, "_config", lambda: MS_CLIENT)
    monkeypatch.setattr(ms, "get_connection", _Conn)
    monkeypatch.setattr(ms, "_vault_create", lambda *a: created.append(a) or "new-secret")
    monkeypatch.setattr(ms, "_vault_delete", lambda *a: None)
    monkeypatch.setattr(ms.requests, "post", lambda *a, **k: SimpleNamespace(
        status_code=200, raise_for_status=lambda: None, json=lambda: {"access_token": "a", "refresh_token": "rotated"}))
    ms._refresh({"id": 1, "account_id": A["account_id"], "refresh_token_secret_id": "old-secret"}, "old-token")
    assert bool(created) is stored


def test_gmail_asks_for_exactly_the_read_only_scope(env):
    query = parse_qs(urlparse(start("gmail", A)).query)
    assert query["scope"] == [gmail_service.GMAIL_SCOPE]
    assert "include_granted_scopes" not in query  # no earlier grant (e.g. sign-in) is merged into the Gmail token


@pytest.mark.parametrize("granted", ["", "openid https://www.googleapis.com/auth/userinfo.email",
                                     "https://www.googleapis.com/auth/gmail.metadata"])
def test_gmail_consent_without_the_read_permission_attaches_nothing(env, granted):
    """Google's granular consent lets the user untick Gmail and still return an authorization code."""
    env.provider.google_scope = granted
    status, params = callback("gmail", *env.provider.authorize(start("gmail", A), "a@example.com"))
    assert status == "permission_missing" and "completion" not in params
    assert env.provider.revoked == []  # never revoked: it would revoke the user's other grants to DINCR's client
    assert env.db.state["vault"] == {}  # and never stored
    assert connections_of(env, A) == []
    assert next(iter(env.db.state["flows"].values()))["status"] == "failed"


@pytest.mark.parametrize("recorded", [[], ["https://www.googleapis.com/auth/gmail.metadata"]])
def test_gmail_completion_never_attaches_a_flow_without_the_read_permission(env, recorded):
    """Defense in depth: even an authorized flow is attached only if it recorded gmail.readonly."""
    _, params = callback("gmail", *env.provider.authorize(start("gmail", A), "a@example.com"))
    next(iter(env.db.state["flows"].values()))["granted_scopes"] = recorded
    with pytest.raises(HTTPException) as refused:
        complete(A, params)
    assert refused.value.status_code == 409
    assert connections_of(env, A) == []


# --- F2: an Outlook mailbox is its Microsoft principal (tenant + Graph id), never its address ---

WORK_TENANT, OTHER_TENANT = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"


def _jwt(claims: dict) -> str:
    def encode(part):
        return base64.urlsafe_b64encode(json.dumps(part).encode()).decode().rstrip("=")
    return f"{encode({'alg': 'none'})}.{encode(claims)}.signature"


@pytest.fixture
def principals(env, monkeypatch):
    """Microsoft principals by sign-in label: {label: {"id", "mail", "tid" (work/school) or no tid (personal)}}.

    Work and school tokens are JWTs carrying ``tid``; personal tokens are opaque. Graph /me
    returns the principal's id and whatever mail attribute its tenant set.
    """
    table: dict[str, dict] = {}
    exchange = env.provider.token

    def token(url, data=None, **kwargs):
        response = exchange(url, data, **kwargs)
        if "microsoft" not in url or response.status_code != 200:
            return response
        body = response.json()
        label = body["access_token"].removeprefix("access-for-")
        principal = table.get(label)
        if principal and principal.get("tid"):
            body = {**body, "access_token": _jwt({"tid": principal["tid"], "label": label})}
        return SimpleNamespace(status_code=200, json=lambda: body)

    def graph_get(access_token, path, *_a):
        if path != "/me":
            return {"value": []}
        if access_token.count(".") == 2:
            label = json.loads(base64.urlsafe_b64decode(access_token.split(".")[1] + "==")).get("label")
        else:
            label = access_token.removeprefix("access-for-")
        principal = table[label]
        return {key: principal[key] for key in ("id", "mail") if principal.get(key) is not None}

    monkeypatch.setattr(gmail_service.requests, "post", token)
    monkeypatch.setattr(ms, "_graph_get", graph_get)
    return table


def _outlook_row(env, user):
    return next(c for c in env.db.state["connections"].values()
                if c["account_id"] == user["account_id"] and "Mail.Read" in c["granted_scopes"])


def test_f2_the_same_work_principal_reconnects_to_its_own_row(env, principals):
    principals["alice"] = {"id": "0f0e0d0c-0000-4000-8000-00000000a11c", "mail": "alice@contoso.com", "tid": WORK_TENANT}
    _connect(env, "microsoft", A, "alice")
    first = _outlook_row(env, A)
    _connect(env, "microsoft", A, "alice")
    rows = [c for c in env.db.state["connections"].values() if c["account_id"] == A["account_id"]]
    assert [c["id"] for c in rows] == [first["id"]] and rows[0]["status"] == "active"
    assert rows[0]["mailbox_key"] == rows[0]["mailbox_email"] == f"microsoft:{WORK_TENANT}:0f0e0d0c-0000-4000-8000-00000000a11c"
    assert len(env.db.state["vault"]) == 1  # the old token is replaced, not kept


@pytest.mark.parametrize("victim_status", ["active", "reauthorization_required"])
def test_f2_another_principal_reporting_the_same_address_takes_nothing(env, principals, victim_status):
    """Same visible address, different principal: a different mailbox. No takeover, no refusal, no squat."""
    principals["victim"] = {"id": "0123456789abcdef", "mail": "shared@outlook.com"}  # personal account
    principals["attacker"] = {"id": "aaaaaaaa-0000-4000-8000-00000000000a", "mail": "shared@outlook.com", "tid": OTHER_TENANT}
    _connect(env, "microsoft", A, "victim")
    victim = _outlook_row(env, A)
    victim["status"] = victim_status
    victim_token = victim["refresh_token_secret_id"]
    assert _connect(env, "microsoft", B, "attacker")[0] == {"status": "connected", "provider": "microsoft"}
    assert env.db.state["connections"][victim["id"]]["status"] == victim_status  # untouched
    assert victim_token in env.db.state["vault"] and env.db.state["takeovers"] == []
    assert _outlook_row(env, B)["mailbox_key"] == f"microsoft:{OTHER_TENANT}:aaaaaaaa-0000-4000-8000-00000000000a"


def test_f2_an_address_claimed_first_never_blocks_the_real_mailbox(env, principals):
    """A tenant sets its user's mail to the victim's address and connects first: the victim still connects."""
    principals["attacker"] = {"id": "aaaaaaaa-0000-4000-8000-00000000000a", "mail": "victim@outlook.com", "tid": OTHER_TENANT}
    principals["victim"] = {"id": "0123456789abcdef", "mail": "victim@outlook.com"}
    _connect(env, "microsoft", B, "attacker")
    assert _connect(env, "microsoft", A, "victim")[0] == {"status": "connected", "provider": "microsoft"}
    assert _outlook_row(env, B)["status"] == "active" and env.db.state["takeovers"] == []


def test_f2_a_changed_mail_attribute_keeps_the_identity(env, principals):
    principals["bob"] = {"id": "b0b00000-0000-4000-8000-000000000b0b", "mail": "bob@contoso.com", "tid": WORK_TENANT}
    _connect(env, "microsoft", A, "bob")
    row = _outlook_row(env, A)
    key = row["mailbox_key"]
    principals["bob"]["mail"] = "robert@contoso.com"  # the tenant renames the user's address
    _connect(env, "microsoft", A, "bob")
    renamed = _outlook_row(env, A)
    assert renamed["id"] == row["id"] and renamed["mailbox_key"] == renamed["mailbox_email"] == key
    assert renamed["google_email"] == "robert@contoso.com"  # display follows the address


def test_f2_the_same_principal_is_refused_elsewhere_and_taken_over_only_when_stale(env, principals):
    principals["carol"] = {"id": "c0c00000-0000-4000-8000-00000000c0c0", "mail": "carol@contoso.com", "tid": WORK_TENANT}
    _connect(env, "microsoft", A, "carol")
    _, params = callback("microsoft", *env.provider.authorize(start("microsoft", B), "carol"))
    with pytest.raises(HTTPException) as refused:
        complete(B, params)
    assert refused.value.detail == mail_oauth.MAILBOX_UNAVAILABLE  # live, VIP: refused, generically
    _outlook_row(env, A)["status"] = "reauthorization_required"
    assert _connect(env, "microsoft", B, "carol")[0] == {"status": "connected", "provider": "microsoft"}
    assert [t["reason"] for t in env.db.state["takeovers"]] == ["access_lost"]


def test_f2_a_microsoft_gmail_address_never_becomes_a_google_identity(env, principals):
    principals["m"] = {"id": "0123456789abcdef", "mail": "victim@gmail.com"}
    _connect(env, "microsoft", B, "m")
    row = _outlook_row(env, B)
    assert row["mailbox_key"] == row["mailbox_email"] == f"microsoft:{ms.CONSUMER_TENANT}:0123456789abcdef"
    assert not row["mailbox_key"].startswith(("google:", "gmail:", "email:"))


def test_f2_personal_account_identity(env, principals):
    principals["p"] = {"id": "00112233445566ff", "mail": "p@outlook.com"}  # opaque token, 16-hex id
    _connect(env, "microsoft", A, "p")
    row = _outlook_row(env, A)
    assert row["mailbox_key"] == row["mailbox_email"] == f"microsoft:{ms.CONSUMER_TENANT}:00112233445566ff"


def test_f2_work_or_school_account_identity(env, principals):
    principals["w"] = {"id": "0d0d0d0d-0000-4000-8000-0000000000dd", "mail": "w@school.example", "tid": WORK_TENANT}
    _connect(env, "microsoft", A, "w")
    row = _outlook_row(env, A)
    assert row["mailbox_key"] == row["mailbox_email"] == f"microsoft:{WORK_TENANT}:0d0d0d0d-0000-4000-8000-0000000000dd"
    assert row["provider_subject"] == "0d0d0d0d-0000-4000-8000-0000000000dd"


@pytest.mark.parametrize("principal", [
    {"id": "0d0d0d0d-0000-4000-8000-0000000000dd", "mail": "w@contoso.com"},  # work id with an opaque token: no tenant
    {"mail": "noid@contoso.com", "tid": WORK_TENANT},                           # Graph returned no id
    {"id": "0123456789abcdef"},                                                  # no address at all
])
def test_f2_without_an_authoritative_identity_nothing_is_stored(env, principals, principal):
    principals["x"] = principal
    status, params = callback("microsoft", *env.provider.authorize(start("microsoft", A), "x"))
    assert status in ("mailbox_unavailable", "mailbox_missing") and "completion" not in params
    assert env.db.state["vault"] == {} and connections_of(env, A) == []
    assert next(iter(env.db.state["flows"].values()))["status"] == "failed"


def test_f2_an_authorized_flow_without_a_principal_is_never_attached(env, principals):
    """A flow authorized before the principal identity (or tampered) cannot attach by address."""
    principals["d"] = {"id": "0123456789abcdef", "mail": "d@outlook.com"}
    _, params = callback("microsoft", *env.provider.authorize(start("microsoft", A), "d"))
    next(iter(env.db.state["flows"].values())).update(provider_subject=None, provider_tenant=None)
    with pytest.raises(HTTPException) as refused:
        complete(A, params)
    assert refused.value.status_code == 409 and connections_of(env, A) == []


def _legacy_outlook(env, user, label, status):
    """A connection identified by its address only (from before the principal identity)."""
    assert _connect(env, "microsoft", user, label)[0]["status"] == "connected"
    row = _outlook_row(env, user)
    address = row["google_email"]
    row.update(status=status, mailbox_key=mail_oauth.mailbox_key("microsoft", address),
               mailbox_email=mail_oauth.mailbox_email("microsoft", address), provider_subject=None, provider_tenant=None)
    return row


def test_f2_a_live_legacy_outlook_row_refuses_a_principal_reporting_its_address(env, principals):
    principals["legacy"] = {"id": "0123456789abcdef", "mail": "legacy@outlook.com"}
    principals["new"] = {"id": "fedcba9876543210", "mail": "legacy@outlook.com"}
    old = _legacy_outlook(env, A, "legacy", "active")
    _, params = callback("microsoft", *env.provider.authorize(start("microsoft", B), "new"))
    with pytest.raises(HTTPException) as refused:
        complete(B, params)
    assert refused.value.detail == mail_oauth.MAILBOX_UNAVAILABLE
    assert env.db.state["connections"][old["id"]]["status"] == "active" and env.db.state["takeovers"] == []


@pytest.mark.parametrize("stale", ["reauthorization", "plan"])
def test_f2_a_stale_legacy_outlook_row_is_never_taken_over_by_address(env, principals, stale):
    principals["legacy"] = {"id": "0123456789abcdef", "mail": "legacy@outlook.com"}
    principals["new"] = {"id": "fedcba9876543210", "mail": "legacy@outlook.com"}
    old = _legacy_outlook(env, A, "legacy", "reauthorization_required" if stale == "reauthorization" else "active")
    old_status, old_token = old["status"], old["refresh_token_secret_id"]
    if stale == "plan":
        env.db.vip.discard(A["account_id"])
    assert _connect(env, "microsoft", B, "new")[0] == {"status": "connected", "provider": "microsoft"}
    assert env.db.state["connections"][old["id"]]["status"] == old_status  # left alone
    assert old_token in env.db.state["vault"] and env.db.state["takeovers"] == []


def test_f2_another_principal_never_reuses_an_own_row_it_only_shares_an_address_with(env, principals):
    """In one workspace, P2 reporting P1's address must not drop P1's token or inherit its import window."""
    principals["p1"] = {"id": "0123456789abcdef", "mail": "same@outlook.com"}
    principals["p2"] = {"id": "fedcba9876543210", "mail": "same@outlook.com"}
    _connect(env, "microsoft", A, "p1")
    p1 = _outlook_row(env, A)
    p1_token = p1["refresh_token_secret_id"]
    _, params = callback("microsoft", *env.provider.authorize(start("microsoft", A), "p2"))
    with pytest.raises(HTTPException) as refused:
        complete(A, params)
    assert refused.value.status_code == 409
    assert env.db.state["connections"][p1["id"]]["mailbox_key"] == p1["mailbox_key"]
    assert p1_token in env.db.state["vault"] and len(env.db.state["vault"]) == 1  # P2's pending token is deleted


def test_f2_the_same_principal_upgrades_its_own_legacy_row(env, principals):
    """An own row identified by address (before the principal identity) is reused and gets the principal."""
    principals["own"] = {"id": "0123456789abcdef", "mail": "own@outlook.com"}
    legacy = _legacy_outlook(env, A, "own", "active")
    _connect(env, "microsoft", A, "own")
    rows = [c for c in env.db.state["connections"].values() if c["account_id"] == A["account_id"]]
    assert [c["id"] for c in rows] == [legacy["id"]]
    assert rows[0]["mailbox_key"] == rows[0]["mailbox_email"] == f"microsoft:{ms.CONSUMER_TENANT}:0123456789abcdef"


@pytest.mark.parametrize("token", [
    "a.b.c.d.e",                                                  # an encrypted (JWE) token
    _jwt({"oid": "0d0d0d0d-0000-4000-8000-0000000000dd"}),        # a JWT without tid
    "not-a-jwt",                                                  # an opaque token
])
def test_f2_a_work_id_without_a_readable_tenant_has_no_identity(token):
    assert ms._graph_identity({"id": "0d0d0d0d-0000-4000-8000-0000000000dd"}, token) == (None, None)


def test_f2_a_personal_id_needs_no_token_claim():
    assert ms._graph_identity({"id": "00112233445566FF"}, "opaque") == ("00112233445566ff", ms.CONSUMER_TENANT)
    assert ms._graph_identity({}, "opaque") == (None, None)
