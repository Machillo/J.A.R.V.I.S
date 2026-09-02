from backend.email_monitor.service import (
    _repair_historical_cross_bank_mirrors,
    _scheduled_commitment_match,
)


class FakeConn:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        response = self.responses.pop(0) if self.responses else None

        class Result:
            def __init__(self, value):
                self.value = value

            def fetchone(self):
                return self.value

            def fetchall(self):
                return self.value or []

        return Result(response)


def test_repairs_historical_bac_multimoney_pair_by_reference():
    reference = "2026082610224012472238515"
    conn = FakeConn([
        [
            {
                "id": 977, "email_message_id": 262, "transaction_date": "2026-08-26",
                "amount": 38318, "notes": f"BAC | referencia {reference}",
                "dedupe_key": f"sinpe|2026-08-26|38318|{reference}|in", "bank": "bac",
            },
            {
                "id": 978, "email_message_id": 263, "transaction_date": "2026-08-26",
                "amount": 38318, "notes": f"MultiMoney | referencia: {reference}",
                "dedupe_key": f"multimoney|2026-08-26|38318|{reference}|out", "bank": "multimoney",
            },
        ],
        None,
        None,
    ])

    assert _repair_historical_cross_bank_mirrors(conn, "workspace") == 2
    assert set(conn.calls[1][1][1]) == {977, 978}
    assert set(conn.calls[2][1][1]) == {262, 263}


def test_multimoney_receipt_matches_automatic_debt_transaction():
    conn = FakeConn([{"id": 700}])
    match = _scheduled_commitment_match(conn, "workspace", {
        "description": "PAGO DE PRESTAMO MULTIMONEY",
        "amount": 20461,
        "transaction_date": "2026-08-31",
    })

    assert match and match[0] == 700
    assert "no se duplica" in match[1]


def test_house_and_father_loan_match_combined_schedules():
    conn = FakeConn([
        {"expected_amount": 100000},
        {"id": 9, "monthly_payment": 30387.13},
        {"id": 701},
    ])
    match = _scheduled_commitment_match(conn, "workspace", {
        "description": "CASA Y PRESTAMO",
        "amount": 130387.13,
        "transaction_date": "2026-08-27",
    })

    assert match and match[0] == 701
    assert "Casa y préstamo" in match[1]
