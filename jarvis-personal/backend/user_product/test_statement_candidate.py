from backend.user_product.statement_candidate import parse_statement_movements, statement_candidate, statement_hash


def test_statement_adapter_emits_canonical_source_and_safe_account_reference():
    text = """TARJETA DE CREDITO
Fecha de corte: 21-AGO-26
B) Detalle de compras del periodo
************3131 PERSONA
072799100801 25-JUL-26 COMERCIO CRC 5,340.00
Total de compras del periodo 5,340.00"""
    rows = parse_statement_movements("bac", text)
    candidate = statement_candidate(
        rows[0], bank="bac", document_hash=statement_hash(text),
        movement_index=0, statement_text=text,
    )
    assert candidate["source_type"] == "statement"
    assert candidate["source_provider"] == "pdf"
    assert candidate["source_account_reference"] == "3131"
    assert candidate["movement_kind"] == "card_purchase"
    assert candidate["external_reference"] == "072799100801"
    assert "PERSONA" not in str(candidate["raw_payload"])


def test_parser_internal_hint_remains_unconfirmed_transfer():
    candidate = statement_candidate(
        {
            "transaction_date": "2026-08-01", "reference": "10",
            "description": "TRANSFERENCIA ENTRE CUENTAS PROPIAS", "amount": 1000,
            "direction": "out", "transaction_type": "internal_transfer",
            "category": "Transferencia interna",
        },
        bank="bac", document_hash="abc", movement_index=0,
        statement_text="Cuenta ****1111",
    )
    assert candidate["transaction_type"] == "transfer"
    assert candidate["is_internal_transfer"] is False
    assert candidate["movement_kind"] == "transfer"


def test_popular_card_statement_emits_reviewable_rows():
    text = """ESTADO DE CUENTA DE TARJETA DE CRÉDITO
Número de cuenta: XXXXXXXXXXXX8285
Detalle de compras del período
12/08/2026 SUPERMERCADO PRUEBA 18,500.00 0.00
Total de compras del período 18,500.00 0.00"""
    rows = parse_statement_movements("popular", text)
    candidate = statement_candidate(
        rows[0], bank="popular", document_hash=statement_hash(text),
        movement_index=0, statement_text=text,
    )
    assert candidate["bank"] == "popular"
    assert candidate["amount"] == 18500.0
    assert candidate["source_account_reference"] == "8285"


def test_unsupported_bank_does_not_guess_statement_rows():
    assert parse_statement_movements("unknown", "01/08/2026\n123\nMOVIMIENTO\n1.00") == []
