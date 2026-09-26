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
