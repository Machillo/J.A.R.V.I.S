"""Synthetic parser battery: amounts, dates, senders and end-to-end templates.

All names, merchants, references and card digits are fictitious.
"""
import pytest

from backend.email_monitor import parser as p
from backend.user_product.gmail_service import bank_sender_allowed

BAC = "BAC Credomatic <notificacion@notificacionesbaccr.com>"


def bac_purchase(amount: str, kind: str = "COMPRA") -> str:
    return (
        "Hola MARIA PRUEBA:\nA continuación le detallamos la transacción realizada:\n"
        "Comercio:\nSUPERMERCADO EJEMPLO\nCiudad y país:\nSAN JOSE, Costa Rica\n"
        "Fecha:\nSep 22, 2026, 10:15\nVISA\n************1234\nAutorización:\n123456\n"
        f"Referencia:\n000011112222\nTipo de Transacción:\n{kind}\nMonto:\n{amount}"
    )


@pytest.mark.parametrize("raw, amount, currency", [
    ("₡15.000", 15_000, "CRC"),            # CR thousands without decimals
    ("CRC 15.000,00", 15_000, "CRC"),
    ("CRC 1,234", 1_234, "CRC"),
    ("CRC 25000", 25_000, "CRC"),
    ("₡ 500", 500, "CRC"),
    ("CRC 1.234.567,89", 1_234_567.89, "CRC"),
    ("USD 1,234.56", 1_234.56, "USD"),
    ("$12.50", 12.50, "USD"),
    ("12,5 dólares", 12.5, "USD"),
])
def test_labeled_amounts_keep_their_magnitude(raw, amount, currency):
    assert p._parse_labeled_amount_value(raw) == (amount, currency)


@pytest.mark.parametrize("text, amount", [
    ("por un monto de 7.250 colones", 7_250),
    ("Monto: CRC 3.500", 3_500),
    ("Monto: ₡10,000.00", 10_000),
    ("Se debitaron ₡ 2.000 de su cuenta", 2_000),
])
def test_context_amounts_keep_their_magnitude(text, amount):
    assert p._parse_context_amount(text)[0] == amount


@pytest.mark.parametrize("raw, value", [
    ("15.000", 15_000), ("1.234", 1_234), ("1,234", 1_234), ("1,5", 1.5), ("1,50", 1.5),
    ("12.5", 12.5), ("1.234.567", 1_234_567), ("1.234,56", 1_234.56), ("1,234.56", 1_234.56),
    ("", None), ("12345678901", None),
])
def test_number_normalization(raw, value):
    assert p._parse_number(raw) == value


@pytest.mark.parametrize("raw", ["CRC 0", "CRC 20.000.001", "sin monto"])
def test_zero_absurd_or_missing_amounts_are_rejected(raw):
    assert p._parse_labeled_amount_value(raw)[0] is None


def test_fallback_dates_are_costa_rica_calendar_days():
    # 01:30 UTC on the 24th is 19:30 on the 23rd in Costa Rica (UTC-6).
    assert p.parse_date("", "2026-09-24T01:30:00Z") == "2026-09-23"
    assert p._base_result("bac", "movement", "2026-09-24T01:30:00+00:00")["transaction_date"] == "2026-09-23"
    assert p._base_result("bac", "movement", "2026-09-24T12:00:00Z")["transaction_date"] == "2026-09-24"
    # A date written in the email always wins over the received time.
    assert p.parse_date("Fecha 22/09/2026", "2026-09-24T01:30:00Z") == "2026-09-22"


@pytest.mark.parametrize("sender, allowed", [
    ("BAC Credomatic <notificacion@notificacionesbaccr.com>", True),
    ("alerta@baccredomatic.com", True),
    ("Banco Popular <avisos@bancopopular.fi.cr>", True),
    ("MultiMoney <multimoneycr@multimoney.com>", True),
    ('"alerta@baccredomatic.com" <attacker@example.com>', False),  # forged display name
    ("Notificaciones <other@notificacionesbaccr.com>", False),      # unknown mailbox on a bank domain
    ("x@evilbancopopular.fi.cr", False),                              # look-alike domain
    ("", False),
])
def test_only_exact_bank_senders_reach_bank_templates(sender, allowed):
    assert bank_sender_allowed(sender) is allowed


def test_bac_purchase_without_decimals_end_to_end():
    parsed = p.parse_financial_email("Notificación de transacción SUPERMERCADO EJEMPLO", BAC, bac_purchase("CRC 15.000"), "2026-09-22T16:15:00Z")
    assert parsed["email_kind"] == "movement"
    assert parsed["transaction_type"] == "expense"
    assert parsed["amount"] == 15_000
    assert parsed["transaction_date"] == "2026-09-22"
    assert parsed["card_last4"] == "1234"


@pytest.mark.parametrize("kind", ["DEVOLUCION", "REVERSION"])
def test_bac_refunds_are_income(kind):
    parsed = p.parse_financial_email("Notificación de transacción", BAC, bac_purchase("CRC 15.000,00", kind), "2026-09-22T16:15:00Z")
    assert parsed["transaction_type"] == "income"
    assert parsed["amount"] == 15_000


def test_sinpe_movil_without_decimals_is_incoming_money():
    parsed = p._parse_bac_sinpe_movil(
        "Transferencia SINPE Móvil", "avisos@baccredomatic.com",
        "Le informamos que Juan Prueba realizó una transferencia por medio de SINPE Móvil "
        "a nombre de Carla Prueba. Referencia 123456789 Fecha 22/09/2026 Monto ₡10.000 Detalle traslado",
        "2026-09-22T10:00:00Z",
    )
    assert parsed["amount"] == 10_000
    assert parsed["movement_direction"] == "in"


def test_multimoney_credit_without_decimals():
    parsed = p._parse_multimoney_transfer(
        "Notificación de transferencia", "avisos@multimoney.com",
        "MultiMoney\nSe aplico un credito en tiempo real\nMonto: CRC 10.000\nFecha: 22/09/2026\n"
        "Referencia: 987654321\nConcepto: traslado",
        "2026-09-22T10:00:00Z",
    )
    assert parsed["amount"] == 10_000
    assert parsed["transaction_type"] == "income"


def test_unknown_bank_is_ignored_not_guessed():
    # Banco Nacional has no parser yet: it must never become a movement.
    parsed = p.parse_financial_email("Aviso BN", "avisos@bncr.fi.cr", "Banco Nacional le informa compra por CRC 5.000", "2026-09-22T16:15:00Z")
    assert parsed["email_kind"] == "ignored"
    assert parsed["bank"] == "unknown"
    assert parsed["transaction_type"] == "ignored"


def test_rejected_or_security_emails_never_create_movements():
    rejected = p.parse_financial_email("Transacción rechazada", BAC, bac_purchase("CRC 15.000") + "\nLa transacción fue rechazada", "2026-09-22T16:15:00Z")
    assert rejected["transaction_type"] == "ignored"
    login = p.parse_financial_email("Tu sesión se inició", BAC, "Tu sesión se inició en BAC. Si no fuiste vos, llamanos.", "2026-09-22T16:15:00Z")
    assert login["transaction_type"] == "ignored"


def test_email_fingerprint_is_stable_for_retries():
    args = ("Notificación de transacción", BAC, bac_purchase("CRC 15.000"), "2026-09-22T16:15:00Z")
    assert p.fingerprint_email(*args) == p.fingerprint_email(*args)
    assert p.fingerprint_email(*args) != p.fingerprint_email(args[0], args[1], bac_purchase("CRC 16.000"), args[3])
