"""VIP Home advice names amounts in the account's base currency, not always ₡.

Only the label changes: the amounts, the priority and every other figure of the
command center are the same whatever the base currency. All data is synthetic.
"""
import pytest

from backend.auth.current_user import reset_current_user, set_current_user
from backend.core.i18n import use_language
from backend.user_product import gmail_service, service, vip_service
from backend.user_product.test_mail_preserves_financial_state import ACCOUNT, ALLOWED_USER_ID, WORKSPACE, LedgerDB

MISSING = object()


def _identity(base_currency):
    identity = {"id": ALLOWED_USER_ID, "account_id": ACCOUNT, "workspace_id": WORKSPACE, "role": "user"}
    if base_currency is not MISSING:
        identity["base_currency"] = base_currency
    return identity


@pytest.fixture
def ledger(monkeypatch):
    database = LedgerDB()
    for module in (vip_service, service, gmail_service):
        monkeypatch.setattr(module, "get_connection", database.connect)
    monkeypatch.setattr(service, "require_feature", lambda *_args, **_kwargs: None)
    return database


@pytest.fixture
def home(ledger):
    def as_account(base_currency, language="es"):
        token = set_current_user(_identity(base_currency))
        try:
            with use_language(language):
                return vip_service.get_vip_command_center()
        finally:
            reset_current_user(token)

    return as_account


@pytest.fixture
def deficit(ledger):
    """Known commitments above income: Home shows both money narratives."""
    ledger.state["profiles"][ACCOUNT]["essential_monthly_expenses"] = 1_200_000
    return ledger


def _advice(center):
    critical = [alert["context"] for alert in center["alerts"] if alert["severity"] == "critical"]
    return [center["director"]["next_action"], *critical]


def _without_advice(center):
    """The whole command center except the two money narratives."""
    director = {key: value for key, value in center["director"].items() if key != "next_action"}
    alerts = [{key: value for key, value in alert.items() if not (alert["severity"] == "critical" and key == "context")}
              for alert in center["alerts"]]
    return {**center, "director": director, "alerts": alerts}


def _amounts(texts):
    words = " ".join(texts).replace("₡", " ").replace("$", " ").replace(",", "").split()
    return [float(word.rstrip(".")) for word in words if word.rstrip(".").replace(".", "").isdigit()]


def test_usd_account_reads_dollars_in_both_narratives(deficit, home):
    center = home("USD")
    advice = _advice(center)
    assert center["director"]["priority"] == "stabilize" and len(advice) == 2, advice
    assert advice == ["Asigná $250,000.00 a esta prioridad.", "Faltan $250,000.00 para cubrir compromisos conocidos."]
    assert all("₡" not in text for text in advice)


def test_usd_account_reads_dollars_in_english(deficit, home):
    assert _advice(home("USD", "en")) == ["Assign $250,000.00 to this priority.", "$250,000.00 is missing to cover known commitments."]


def test_crc_account_keeps_the_exact_previous_text(deficit, home):
    center = home("CRC")
    gap = abs(center["safe_to_spend"]["monthly_margin"])
    # The text Home produced before this change, byte for byte.
    assert _advice(center) == [f"Asigná ₡{gap:,.0f} a esta prioridad.", f"Faltan ₡{gap:,.0f} para cubrir compromisos conocidos."]


@pytest.mark.parametrize("code", ["EUR", "ARS", "MXN", "COP", "GTQ", "PAB"])
def test_legacy_base_currency_is_named_by_its_code_and_not_converted(deficit, home, code):
    advice = _advice(home(code))
    assert advice == [f"Asigná 250,000 {code} a esta prioridad.", f"Faltan 250,000 {code} para cubrir compromisos conocidos."]
    assert all("₡" not in text and "$" not in text for text in advice)


@pytest.mark.parametrize("base_currency", [None, "", MISSING])
def test_identity_without_a_currency_keeps_the_previous_colones(deficit, home, base_currency):
    assert _advice(home(base_currency)) == _advice(home("CRC"))


@pytest.mark.parametrize("fixture_name", ["ledger", "deficit"])
def test_only_the_label_changes_never_the_numbers_or_the_decision(request, home, fixture_name):
    request.getfixturevalue(fixture_name)
    centers = {code: home(code) for code in ("CRC", "USD", "EUR", None)}
    reference = centers["CRC"]
    for code, center in centers.items():
        assert _without_advice(center) == _without_advice(reference), f"{code}: only the currency label may change"
        assert _amounts(_advice(center)) == _amounts(_advice(reference)), code


def test_break_even_month_never_reads_minus_zero(ledger, home):
    # Commitments equal the income to the cent; float subtraction leaves -0.0.
    profile = ledger.state["profiles"][ACCOUNT]
    profile["fixed_monthly_salary"], profile["essential_monthly_expenses"] = 445330.06, 416070.03
    ledger.state["debts"][0]["monthly_payment"] = 29260.03
    assert home("CRC")["director"]["next_action"] == "Asigná ₡0 a esta prioridad."
    assert home("USD")["director"]["next_action"] == "Asigná $0.00 a esta prioridad."
    assert home("EUR")["director"]["next_action"] == "Asigná 0 EUR a esta prioridad."


@pytest.mark.parametrize(("base", "value", "expected"), [
    ("USD", 1234.6, "$1,234.60"),
    ("USD", -1234.6, "-$1,234.60"),
    ("USD", 0, "$0.00"),
    ("USD", -0.001, "$0.00"),
    ("USD", 1234567890.125, "$1,234,567,890.12"),
    ("CRC", 1234.6, "₡1,235"),
    ("CRC", -1234.6, "-₡1,235"),
    ("CRC", 0, "₡0"),
    ("CRC", -0.4, "₡0"),
    ("CRC", 1234567890.4, "₡1,234,567,890"),
    ("EUR", 1234.6, "1,235 EUR"),
    ("EUR", -1234.6, "-1,235 EUR"),
    ("EUR", 0, "0 EUR"),
    ("usd", 1234.6, "$1,234.60"),
])
def test_money_text_only_formats(base, value, expected):
    token = set_current_user({"id": 1, "account_id": "a", "workspace_id": "w", "role": "user", "base_currency": base})
    try:
        assert vip_service._money_text(value) == expected
    finally:
        reset_current_user(token)


def test_money_text_without_an_identity_keeps_colones():
    assert vip_service._money_text(1234.6) == "₡1,235"
