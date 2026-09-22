from backend.email_monitor.popular_pdf import (
    is_popular_sender,
    parse_popular_card_statement,
    parse_popular_email_document,
    parse_popular_loan_payment,
    parse_popular_loan_snapshot,
    parse_popular_sinpe_receipt,
)
from backend.email_monitor.service import _with_popular_gmail_sources


def test_popular_sender_is_restricted_to_official_domains():
    assert is_popular_sender("Notificaciones <avisos@bancopopular.fi.cr>")
    assert is_popular_sender("Tarjetas <popular@bancopopularinforma.fi.cr>")
    assert is_popular_sender("BP <notifica@bpdc.fi.cr>")
    assert not is_popular_sender("Banco Popular <fraude@gmail.com>")


def test_jarvis_persisted_query_is_upgraded_with_all_popular_sources():
    upgraded = _with_popular_gmail_sources("(from:baccredomatic.cr OR from:bancopopular.fi.cr)")
    assert "from:bancopopular.fi.cr" in upgraded
    assert "from:bancopopularinforma.fi.cr" in upgraded
    assert "from:bpdc.fi.cr" in upgraded
    assert _with_popular_gmail_sources(upgraded) == upgraded


def test_parse_popular_payroll_loan_payment_with_breakdown():
    text = """
    COMPROBANTEDEPAGODE PRESTAMOS
    Número de Operación 1040900012345
    Fecha Aplicación 07/09/2026 08:15:20
    Patrono 123456 - EMPRESA PRUEBA SA
    Número Comprobante 20260907007302
    Fecha Planilla AGOSTO 2026
    Monto delPago ₡ 65 480,40
    Saldo Anterior ₡ 1,500,000.00
    Amortización Saldo ₡ 45 000,00
    Intereses Corrientes ₡ 15 000,00
    Intereses de Mora ₡ 0,00
    Cargos por Pólizas ₡ 5 480,40
    Fracciones o Excesos ₡ 0,00
    Otros Cargos ₡ 0,00
    Nuevo Saldo ₡ 1 455 000,00
    Tasa Anual 12,00 %
    Medio de Pago 04-PLANILLAS
    """
    parsed = parse_popular_loan_payment(text, "2026-09-08T14:44:47Z")
    assert parsed is not None
    assert parsed["transaction_date"] == "2026-09-07"
    assert parsed["amount"] == 65480.40
    assert parsed["loan_breakdown"]["principal"] == 45000.0
    assert parsed["loan_breakdown"]["interest"] == 15000.0
    assert parsed["loan_breakdown"]["insurance"] == 5480.40
    assert parsed["confidence"] < 0.95


def test_parse_popular_sinpe_receipt_as_pending_candidate():
    text = """
    Transaccion SINPE
    Referencia SINPE: 2026090916122180024894547
    Número Comprobante: FT1234567V01
    Fecha: 09/09/2026 16:12:21
    Estado dela Transacción: Aplicada
    CanalOrigen: PIN SIPO
    Servicio SINPE: Pagos Inmediatos
    IbanOrigen: CR12**************1111
    Entidad Destino: BAC San José S.A.
    IbanDestino: CR34**************2222
    Monto Enviado: 125,000.00
    Moneda: CRC
    Descripcion: PAGO CUENTA PROPIA
    Tipo de movimiento: Débito
    """
    parsed = parse_popular_sinpe_receipt(text)
    assert parsed is not None
    assert parsed["amount"] == 125000.0
    assert parsed["transaction_date"] == "2026-09-09"
    assert parsed["transaction_type"] == "expense"
    assert parsed["confidence"] < 0.95


def test_non_applied_popular_sinpe_is_rejected():
    text = """
    Transaccion SINPE
    Referencia SINPE: 123456789
    Fecha: 09/09/2026 16:12:21
    Estado de la Transacción: Rechazada
    Monto Enviado: 10,000.00
    Moneda: CRC
    Tipo de movimiento: Débito
    """
    assert parse_popular_sinpe_receipt(text) is None


def test_parse_popular_loan_statement_as_snapshot_not_fake_transaction():
    text = """
    ESTADO DE CUENTA DE OPERACIONES DE CRÉDITO
    IDOperación de crédito: 1040900012345 Fecha de emisión: 03/09/2026
    Saldo actual adeudado (no incluye intereses): 1 455 000,00
    Monto principal atrasado: 0,00
    Fecha del próximo pago: 07/10/2026
    Fecha del último pago: 07/09/2026
    """
    snapshot = parse_popular_loan_snapshot(text)
    assert snapshot is not None
    assert snapshot["document_type"] == "loan_statement"
    assert snapshot["operation"] == "1040900012345"
    assert snapshot["current_balance"] == 1455000.0
    assert parse_popular_card_statement(text) == []


def test_parse_popular_crc_card_rows_and_skip_usd_only_rows():
    text = """
    ESTADO DE CUENTA DE TARJETA DE CRÉDITO
    Número de cuenta: XXXXXXXXXXXX8285
    Detalle de compras del período
    12/08/2026 SUPERMERCADO PRUEBA 18,500.00 0.00
    13/08/2026 SERVICIO INTERNACIONAL 0.00 12.99
    Total de compras del período 18,500.00 12.99
    """
    rows = parse_popular_card_statement(text)
    assert len(rows) == 1
    assert rows[0]["transaction_date"] == "2026-08-12"
    assert rows[0]["amount"] == 18500.0
    assert rows[0]["card_last4"] == "8285"


def test_popular_document_parser_rejects_untrusted_sender():
    receipt = """
    COMPROBANTE DE PAGO DE PRESTAMOS
    Número de Operación 123456
    Fecha Aplicación 07/09/2026
    Número Comprobante 999001
    Monto del Pago ₡ 10 000,00
    Amortización Saldo ₡ 9 000,00
    """
    assert parse_popular_email_document(
        subject="Comprobante Pago",
        sender="persona@gmail.com",
        body="",
        attachment_text=receipt,
        received_at=None,
    ) is None
    assert parse_popular_email_document(
        subject="Comprobante Pago",
        sender="Banco <avisos@bancopopular.fi.cr>",
        body="",
        attachment_text=receipt,
        received_at=None,
    )["bank"] == "popular"
