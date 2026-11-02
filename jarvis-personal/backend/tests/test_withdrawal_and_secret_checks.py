"""Withdrawing an authorization never waits on anything; a malformed secret is a refusal, not a crash.

- Disconnecting a mailbox and unlinking a shortcut must work for someone who declined new legal
  texts or while a switch is off: otherwise an authorization stays stored against the user's wish.
- A non-ASCII value in a secret header or query made `compare_digest(str, str)` raise TypeError, so
  an unauthenticated request got a 500 and raised an error signal instead of a plain refusal.
- Internal support notes are not the user's data: neither their ticket list nor their export has them.
"""
import pytest
from fastapi import HTTPException

from backend.auth import legal, owner_bridge
from backend.auth.data_export import EXCLUDED_COLUMNS
from backend.core.feature_flags import _request_flags
from backend.integrations import ibkr_readonly
from backend.notifications import routes as notification_routes
from backend.product_ops import service as product_ops
from backend.user_product import gmail_service

MALFORMED = "contraseña-ñ"


@pytest.mark.parametrize("path", ["/user-product/vip/gmail", "/user-product/vip/shortcuts/token"])
def test_withdrawing_an_authorization_does_not_wait_for_the_legal_acceptance(path, monkeypatch):
    monkeypatch.setattr(legal, "_has_accepted", lambda _account: False)
    user = {"role": "user", "account_id": "00000000-0000-4000-8000-0000000000b1"}
    assert legal.acceptance_required(user, "DELETE", path) is False


def test_other_mail_and_shortcut_routes_still_wait_for_it(monkeypatch):
    monkeypatch.setattr(legal, "_has_accepted", lambda _account: False)
    user = {"role": "user", "account_id": "00000000-0000-4000-8000-0000000000b1"}
    assert legal.acceptance_required(user, "GET", "/user-product/vip/gmail/status") is True
    assert legal.acceptance_required(user, "POST", "/user-product/vip/shortcuts/token") is True


def test_unlinking_a_shortcut_does_not_pause_with_the_switch():
    assert _request_flags("DELETE", "/user-product/vip/shortcuts/token") == []
    assert "vip_intelligence" in _request_flags("POST", "/user-product/vip/shortcuts/token")


def _refused(call, status):
    with pytest.raises(HTTPException) as refused:
        call()
    assert refused.value.status_code == status


def test_a_non_ascii_secret_is_a_refusal_on_every_cron_and_bridge(monkeypatch):
    for name in ("FINVA_GMAIL_CRON_SECRET", "NOTIFICATION_CRON_SECRET", "IBKR_BRIDGE_SECRET", "IBKR_FLEX_CRON_SECRET"):
        monkeypatch.setenv(name, "the-real-secret")
    monkeypatch.setattr(owner_bridge, "BRIDGE_API_KEY", "the-real-secret")
    _refused(lambda: gmail_service.gmail_maintenance(MALFORMED), 403)
    _refused(lambda: notification_routes.notifications_cron(x_cron_secret=MALFORMED), 403)
    _refused(lambda: ibkr_readonly.sync_flex_cron(x_jarvis_cron_secret=MALFORMED), 403)
    _refused(lambda: owner_bridge.require_owner_bridge_key(x_jarvis_bridge_key=MALFORMED), 401)


def test_internal_support_notes_are_not_the_users_data(monkeypatch):
    assert "owner_notes" in EXCLUDED_COLUMNS
    seen = []

    class Result:
        def fetchall(self):
            return []

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def commit(self):
            pass

        def execute(self, query, params=()):
            seen.append(query)
            return Result()

    monkeypatch.setattr(product_ops, "get_connection", Conn)
    monkeypatch.setattr(product_ops, "ensure_schema", lambda _conn: None)
    monkeypatch.setattr(product_ops, "get_current_account_id", lambda: "00000000-0000-4000-8000-0000000000b1")
    assert product_ops.list_feedback() == []
    assert seen and all("owner_notes" not in query for query in seen)
