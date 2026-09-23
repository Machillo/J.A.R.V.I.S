from datetime import datetime, timezone

from backend.product_ops import service


class _Result:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, order):
        self.order = order
        self.calls = []

    def execute(self, query, params=()):
        self.calls.append((query, params))
        return _Result(self.order)


def _candidate(**overrides):
    candidate = {
        "transaction_type": "income",
        "movement_direction": "in",
        "description": "SINPE recibido",
        "amount": 1990,
        "notes": (
            "BAC SINPE Móvil | entrada | payer: Persona Prueba | "
            "recipient: Kenneth Alvarado | telefono destino: 88888888 | "
            "detalle: DINCR-A2B3C4 | referencia 123456789"
        ),
    }
    candidate.update(overrides)
    return candidate


def test_matching_bank_confirmation_activates_order(monkeypatch):
    order = {"id": 17, "plan_code": "basic", "amount": 1990}
    conn = _Connection(order)
    activated = []
    monkeypatch.setenv("DINCR_SINPE_PHONE", "8888-8888")
    monkeypatch.setattr(service, "_activate_order", lambda *args: activated.append(args))

    result = service.match_sinpe_payment(conn, _candidate())

    assert result == {"order_id": 17, "plan_code": "basic", "payment_code": "DINCR-A2B3C4"}
    assert conn.calls[0][1] == ("DINCR-A2B3C4",)
    assert activated[0][2:] == ("gmail_bac_sinpe", "123456789", "Persona Prueba")


def test_legacy_finva_payment_code_still_activates_existing_order(monkeypatch):
    order = {"id": 18, "plan_code": "vip", "amount": 1990}
    conn = _Connection(order)
    activated = []
    monkeypatch.setenv("DINCR_SINPE_PHONE", "8888-8888")
    monkeypatch.setattr(service, "_activate_order", lambda *args: activated.append(args))

    result = service.match_sinpe_payment(
        conn,
        _candidate(notes=_candidate()["notes"].replace("DINCR-A2B3C4", "FINVA-A2B3C4")),
    )

    assert result == {"order_id": 18, "plan_code": "vip", "payment_code": "FINVA-A2B3C4"}
    assert activated


def test_outgoing_or_wrong_amount_does_not_activate(monkeypatch):
    conn = _Connection({"id": 17, "plan_code": "basic", "amount": 1990})
    activated = []
    monkeypatch.delenv("DINCR_SINPE_PHONE", raising=False)
    monkeypatch.setattr(service, "_activate_order", lambda *args: activated.append(args))

    assert service.match_sinpe_payment(conn, _candidate(movement_direction="out")) is None
    assert service.match_sinpe_payment(conn, _candidate(amount=3990)) is None
    assert activated == []


def test_wrong_destination_phone_does_not_activate(monkeypatch):
    conn = _Connection({"id": 17, "plan_code": "basic", "amount": 1990})
    monkeypatch.setenv("DINCR_SINPE_PHONE", "8777-7777")
    monkeypatch.setattr(service, "_activate_order", lambda *args: None)

    assert service.match_sinpe_payment(conn, _candidate()) is None
    assert conn.calls == []


def test_naive_database_datetime_is_interpreted_as_utc():
    assert service._as_utc("2026-09-11T15:00:00") == datetime(2026, 9, 11, 15, tzinfo=timezone.utc)


def test_receipt_signature_must_match_declared_type():
    assert service._valid_receipt_signature("image/png", b"\x89PNG\r\n\x1a\nrest")
    assert service._valid_receipt_signature("application/pdf", b"%PDF-1.7 rest")
    assert not service._valid_receipt_signature("image/png", b"%PDF-1.7 rest")


def test_launch_promotion_ends_at_costa_rica_new_year():
    assert service.launch_promotion_status(datetime(2027, 1, 1, 5, 59, tzinfo=timezone.utc))["active"] is True
    assert service.launch_promotion_status(datetime(2027, 1, 1, 6, 0, tzinfo=timezone.utc))["active"] is False


def test_only_regular_prices_remain():
    assert service.PRICES == {
        "basic": {"regular": 2990},
        "vip": {"regular": 4990},
    }
