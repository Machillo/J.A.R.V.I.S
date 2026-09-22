from backend.user_product.financial_candidate import canonical_candidate


def test_adapts_parser_payload_to_provider_independent_candidate():
    candidate = canonical_candidate(
        {
            "bank": "bac",
            "transaction_date": "2026-09-21",
            "transaction_time": "09:15:00",
            "description": "SUPERMERCADO",
            "amount": 12500,
            "transaction_type": "expense",
            "category": "Comida",
            "account": "BAC ****1234",
            "card_last4": "1234",
            "dedupe_key": "bac_card|2026-09-21|1234|12500|supermercado|09:15:00",
            "confidence": 0.99,
            "confidence_reason": "Plantilla exacta.",
        },
        provider_message_id="gmail-1",
        subject="Compra BAC",
    )

    assert candidate["source_type"] == "email"
    assert candidate["source_provider"] == "gmail"
    assert candidate["source_record_key"] == "gmail:gmail-1:0"
    assert candidate["movement_kind"] == "card_purchase"
    assert candidate["movement_direction"] == "out"
    assert candidate["currency"] == "CRC"
    assert candidate["source_account_reference"] == "1234"
    assert candidate["parser_name"] == "jarvis_financial_email"
    assert candidate["raw_payload"]["card_last4"] == "1234"


def test_preserves_transfer_context_without_deciding_ownership():
    candidate = canonical_candidate(
        {
            "bank": "bac",
            "transaction_date": "2026-09-21",
            "description": "SINPE",
            "amount": 5000,
            "transaction_type": "transfer",
            "category": "Transferencia",
            "movement_direction": "out",
            "origin_account": "CR00****1111",
            "destination_account": "CR00****2222",
            "dedupe_key": "sinpe|2026-09-21|5000|abc|out",
        },
        provider_message_id="gmail-2",
        subject="Transferencia",
    )

    assert candidate["movement_kind"] == "transfer"
    assert candidate["movement_direction"] == "out"
    assert candidate["source_account_reference"] == "CR00****1111"
    assert candidate["destination_account_reference"] == "CR00****2222"
    assert candidate["is_internal_transfer"] is False


def test_parser_internal_hint_does_not_bypass_confirmed_identity():
    candidate = canonical_candidate(
        {
            "bank": "bac", "amount": 5000, "transaction_type": "internal_transfer",
            "movement_direction": "internal", "origin_account": "1111",
            "destination_account": "2222",
        },
        provider_message_id="gmail-3",
        subject="Transferencia",
    )
    assert candidate["is_internal_transfer"] is False
