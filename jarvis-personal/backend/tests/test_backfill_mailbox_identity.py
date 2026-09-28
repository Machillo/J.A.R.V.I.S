"""The mailbox identity backfill writes nothing when its result is ambiguous."""
import pytest

from backend.scripts.backfill_mailbox_identity import Ambiguous, _resolver, plan, provider_of

ROWS = [{"id": 1}, {"id": 2}, {"id": 3}]


def test_resolved_rows_get_the_provider_identity_and_unresolved_keep_the_address():
    keys = {1: "google:1", 2: None, 3: "email:x@example.com"}
    updates, counts = plan(ROWS, set(), lambda row: keys[row["id"]])
    assert updates == {1: "google:1"} and counts == {"resolved": 1, "unresolved": 2}


def test_two_connections_resolving_to_one_identity_abort():
    with pytest.raises(Ambiguous):
        plan(ROWS[:2], set(), lambda row: "google:same")


def test_an_identity_already_live_elsewhere_aborts():
    with pytest.raises(Ambiguous):
        plan(ROWS[:1], {"google:1"}, lambda row: "google:1")


@pytest.mark.parametrize(("scopes", "provider"), [
    (["https://www.googleapis.com/auth/gmail.readonly"], "gmail"), (["Mail.Read"], "microsoft"), ([], None), (None, None)])
def test_the_provider_comes_only_from_the_stored_scope(scopes, provider):
    assert provider_of({"granted_scopes": scopes}) == provider


@pytest.mark.parametrize("apply", [False, True])
def test_no_token_is_read_or_sent_for_a_row_without_a_provider_or_for_outlook_in_a_dry_run(monkeypatch, apply):
    from backend.user_product import gmail_service

    monkeypatch.setattr(gmail_service, "_vault_read", lambda *_a: pytest.fail("a token was read"))
    resolve = _resolver(object(), apply=apply)
    assert resolve({"granted_scopes": [], "refresh_token_secret_id": "x"}) is None
    if not apply:
        assert resolve({"granted_scopes": ["Mail.Read"], "refresh_token_secret_id": "x"}) is None


def test_a_gmail_token_is_read_on_behalf_of_the_account_that_owns_it(monkeypatch):
    """The Vault boundary needs the owning account: a wrong call must not pass as "unresolved"."""
    from types import SimpleNamespace

    from backend.user_product import gmail_service

    reads = []

    def vault_read(conn, secret_id, account_id):  # the boundary's exact signature
        reads.append((secret_id, account_id))
        return "synthetic-refresh-token"

    monkeypatch.setattr(gmail_service, "_vault_read", vault_read)
    monkeypatch.setattr(gmail_service, "_google_config", lambda: ("client", "secret", "uri"))
    monkeypatch.setattr(gmail_service.requests, "post",
                        lambda *_a, **_k: SimpleNamespace(status_code=200, json=lambda: {"access_token": "a"}))
    monkeypatch.setattr(gmail_service, "_google_subject", lambda access, client_id: "108")
    row = {"granted_scopes": [gmail_service.GMAIL_SCOPE], "refresh_token_secret_id": "s1",
           "account_id": "00000000-0000-4000-8000-0000000000a1", "google_email": "a@example.com"}
    assert _resolver(object(), apply=False)(row) == "google:108"
    assert reads == [("s1", "00000000-0000-4000-8000-0000000000a1")]
