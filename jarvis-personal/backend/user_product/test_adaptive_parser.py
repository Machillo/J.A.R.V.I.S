from backend.user_product import adaptive_parser


def test_mask_sensitive_keeps_only_last_four_digits():
    masked = adaptive_parser._mask_sensitive("Cuenta 1234-5678-9012 y correo ana@example.com")
    assert "1234-5678-9012" not in masked
    assert "****9012" in masked
    assert "ana@example.com" not in masked


def test_validate_requires_confident_complete_movement():
    parsed = adaptive_parser._validate(
        {
            "is_financial_movement": True,
            "transaction_date": "2026-09-21",
            "description": "Compra comercio",
            "amount": 1250,
            "currency": "CRC",
            "transaction_type": "expense",
            "movement_direction": "out",
            "category": "food",
            "source_account_last4": "1234",
            "confidence": 0.82,
        },
        bank="bac",
        received_at="2026-09-21T15:00:00+00:00",
    )
    assert parsed["email_kind"] == "movement"
    assert parsed["extraction_method"] == "ai"
    assert parsed["origin_account"] == "1234"


def test_validate_rejects_low_confidence_or_incomplete_result():
    assert adaptive_parser._validate(
        {"is_financial_movement": True, "amount": 100, "confidence": 0.2},
        bank="bac", received_at="2026-09-21T15:00:00+00:00",
    ) is None


def test_fallback_does_not_call_provider_when_not_configured(monkeypatch):
    monkeypatch.setattr(adaptive_parser, "is_available", lambda: False)
    result = adaptive_parser.parse_unknown_email(
        subject="Movimiento", sender="bank@example.com", body="Monto 1000",
        received_at="2026-09-21T15:00:00+00:00", bank="bac",
    )
    assert result["status"] == "unavailable"
    assert result["parsed"] is None


def test_fallback_returns_pending_candidate_from_valid_json(monkeypatch):
    class _Response:
        text = '{"is_financial_movement":true,"transaction_date":"2026-09-21","transaction_time":"10:30","description":"Compra","amount":1000,"currency":"CRC","transaction_type":"expense","movement_direction":"out","movement_kind":"card_purchase","category":"food","source_account_last4":"9876","destination_account_last4":null,"counterparty":"Comercio","reference":"abc","confidence":0.84}'

    class _Models:
        def generate_content(self, **_kwargs): return _Response()

    class _Client:
        models = _Models()

    monkeypatch.setattr(adaptive_parser, "is_available", lambda: True)
    monkeypatch.setattr(adaptive_parser.genai, "Client", lambda **_kwargs: _Client())
    result = adaptive_parser.parse_unknown_email(
        subject="Movimiento", sender="bank@example.com", body="Monto 1000",
        received_at="2026-09-21T15:00:00+00:00", bank="bac",
    )
    assert result["status"] == "candidate"
    assert result["parsed"]["confidence"] == 0.84
    assert result["parsed"]["parser_name"] == "finva_ai_fallback"
