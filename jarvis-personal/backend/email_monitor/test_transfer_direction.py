from backend.email_monitor.parser import _parse_bac_sinpe, _parse_bac_sinpe_movil, _parse_multimoney_transfer


def test_bac_sinpe_mobile_can_parse_a_named_recipient_other_than_developer():
    parsed = _parse_bac_sinpe_movil(
        "Transferencia SINPE Móvil", "avisos@baccredomatic.com",
        "Le informamos que Juan Perez realizó una transferencia por medio de SINPE Móvil "
        "a nombre de Carlos Perez. Referencia 123456789 Fecha 22/09/2026 "
        "Monto ₡10,000.00 Detalle traslado", "2026-09-22T10:00:00Z",
    )
    assert parsed["recipient_name"] == "Carlos Perez"
    assert parsed["movement_direction"] == "in"


def test_bac_ambiguous_debit_and_credit_is_left_for_review():
    parsed = _parse_bac_sinpe(
        "Transferencia SINPE", "avisos@baccredomatic.com",
        "Se debitó su cuenta y se acreditó otra cuenta. Monto ₡10,000.00 "
        "Día y hora 22/09/2026 10:00 Referencia 123456789", "2026-09-22T10:00:00Z",
    )
    assert parsed["movement_direction"] == "unknown"
    assert parsed["transaction_type"] == "transfer"


def test_multimoney_credit_is_parsed_from_explicit_posting_wording():
    parsed = _parse_multimoney_transfer(
        "Notificación de transferencia", "avisos@multimoney.com",
        "MultiMoney\nSe aplico un credito en tiempo real\nMonto: CRC 10,000.00\n"
        "Fecha: 22/09/2026\nReferencia: 987654321\nConcepto: traslado",
        "2026-09-22T10:00:00Z",
    )
    assert parsed["movement_direction"] == "in"
    assert parsed["transaction_type"] == "income"
