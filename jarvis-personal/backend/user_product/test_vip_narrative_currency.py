"""VIP Home advice names amounts in the account's base currency, not always ₡."""
import pytest

from backend.auth.current_user import reset_current_user, set_current_user
from backend.user_product import gmail_service, service, vip_service
from backend.user_product.test_mail_preserves_financial_state import ACCOUNT, ALLOWED_USER_ID, WORKSPACE, LedgerDB


@pytest.fixture
def home(monkeypatch):
    database = LedgerDB()
    for module in (vip_service, service, gmail_service):
        monkeypatch.setattr(module, "get_connection", database.connect)
    monkeypatch.setattr(service, "require_feature", lambda *_args, **_kwargs: None)

    def as_account(base_currency):
        token = set_current_user({"id": ALLOWED_USER_ID, "account_id": ACCOUNT, "workspace_id": WORKSPACE,
                                  "role": "user", "base_currency": base_currency})
        try:
            return vip_service.get_vip_command_center()
        finally:
            reset_current_user(token)

    return as_account


def _advice(center):
    texts = [center["director"]["next_action"]]
    texts += [alert["context"] for alert in center.get("alerts", []) if alert.get("title") in ("Cierre mensual negativo", "Negative monthly close")]
    return texts


def test_usd_account_reads_dollars_in_its_advice(home):
    advice = _advice(home("USD"))
    assert all("₡" not in text for text in advice), advice
    assert "$" in advice[0]


def test_crc_account_keeps_colones(home):
    advice = _advice(home("CRC"))
    assert all("₡" in text for text in advice), advice


def test_missing_base_currency_keeps_the_previous_colones(home):
    assert "₡" in _advice(home(None))[0]


def test_same_data_same_numbers_whatever_the_currency_label(home):
    crc, usd = home("CRC"), home("USD")
    assert crc["director"]["priority"] == usd["director"]["priority"]
    assert crc["safe_to_spend"] == usd["safe_to_spend"], "only the label changes; no conversion happens"


def test_money_text_formats_each_base_currency():
    token = set_current_user({"id": 1, "account_id": "a", "workspace_id": "w", "role": "user", "base_currency": "USD"})
    try:
        assert vip_service._money_text(1234.6) == "$1,234.60"
    finally:
        reset_current_user(token)
    for base, expected in (("CRC", "₡1,235"), ("EUR", "1,235 EUR")):
        token = set_current_user({"id": 1, "account_id": "a", "workspace_id": "w", "role": "user", "base_currency": base})
        try:
            assert vip_service._money_text(1234.6) == expected
        finally:
            reset_current_user(token)
