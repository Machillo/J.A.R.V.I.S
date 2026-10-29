"""Bank SMS readers (shortcut_sms.py). Every sample below is SYNTHETIC: invented names, amounts
and references written in the exact shape of real, anonymized BAC SMS (2026-10-29)."""
from decimal import Decimal

import pytest

from backend.user_product import shortcut_sms

RECEIVED = [
    # (synthetic SMS, amount, description, reference)
    ("Ha recibido 36,455.00 Colones de PERSONA EJEMPLO UNO por SINPE Movil, Pendiente viaje -6. Referencia 2026010112000010000000001.",
     Decimal("36455.00"), "SINPE de PERSONA EJEMPLO UNO · Pendiente viaje -6", "2026010112000010000000001"),
    ("Ha recibido 28,898.00 Colones de NOMBRE§DE§PRUEBA§ por SINPE Movil, Sin Descripcion. Referencia 900000001.",
     Decimal("28898.00"), "SINPE de NOMBRE DE PRUEBA", "900000001"),
    ("Ha recibido 20,601.86 Colones de OTRO_NOMBRE_FICTICIO_ por SINPE Movil, Sin Descripcion. Referencia 900000002.",
     Decimal("20601.86"), "SINPE de OTRO NOMBRE FICTICIO", "900000002"),
    ("Ha recibido 500.00 Colones de A B por SINPE Movil,\nSin Descripcion. Referencia 900000003",  # line break, no final dot
     Decimal("500.00"), "SINPE de A B", "900000003"),
]


@pytest.mark.parametrize(("text", "amount", "description", "reference"), RECEIVED)
def test_a_received_sinpe_is_income_in_colones(text, amount, description, reference):
    movement = shortcut_sms.parse(text)
    assert movement == shortcut_sms.SmsMovement(bank="bac", kind="sinpe_in", amount=amount, currency="CRC",
                                                description=description, reference=reference)
    assert shortcut_sms.KINDS[movement.kind][0] == "income"


@pytest.mark.parametrize("text", [
    "Ha recibido 36,455 Colones de PERSONA por SINPE Movil, Sin Descripcion. Referencia 900000001.",   # no cents
    "Ha recibido 36.455,00 Colones de PERSONA por SINPE Movil, Sin Descripcion. Referencia 900000001.",  # other separators
    "Ha recibido 36,455.00 Dolares de PERSONA por SINPE Movil, Sin Descripcion. Referencia 900000001.",  # no real USD sample
    "Ha recibido 0.00 Colones de PERSONA por SINPE Movil, Sin Descripcion. Referencia 900000001.",
    "Ha recibido 36,455.00 Colones de PERSONA por SINPE Movil, Sin Descripcion.",                        # no reference
    "Ha enviado 36,455.00 Colones a PERSONA por SINPE Movil, Sin Descripcion. Referencia 900000001.",   # sent: no sample yet
    "Su codigo de verificacion es 123456",
])
def test_anything_else_is_not_recognized(text):
    assert shortcut_sms.parse(text) is None


def test_text_validation_and_bank_counter():
    assert shortcut_sms.valid_text("  hola  ") == "hola"
    for bad in ("", "   ", "x" * 1001, "a\x00b", None, 3):
        assert shortcut_sms.valid_text(bad) is None
    assert shortcut_sms.detect_bank("Aviso de BAC Credomatic") == "bac"
    assert shortcut_sms.detect_bank("Ha recibido 1.00 Colones") == "unknown"
