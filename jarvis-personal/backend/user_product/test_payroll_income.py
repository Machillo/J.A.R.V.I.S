from backend.user_product.payroll_income import identify_received_payroll, link_received_payroll


class _Result:
    def __init__(self, row=None): self.row = row
    def fetchone(self): return self.row


class _Connection:
    def __init__(self, row=None): self.row, self.calls = row, []
    def execute(self, query, params=()):
        self.calls.append((query, params))
        return _Result(self.row)


def test_explicit_applied_salary_credit_becomes_payroll_deposit():
    parsed = {"transaction_type": "income", "description": "Depósito BAC", "category": "Otros ingresos"}
    result = identify_received_payroll(
        parsed,
        subject="Notificación de depósito aplicado",
        body="Se acreditó en su cuenta el pago de planilla correspondiente a septiembre.",
    )
    assert result["movement_kind"] == "payroll_deposit"
    assert result["category"] == "Salario"
    assert result["payroll_received"] is True


def test_expected_or_ccss_salary_never_becomes_received_income():
    parsed = {"transaction_type": "income", "description": "Ingreso esperado", "category": "Otros ingresos"}
    assert identify_received_payroll(parsed, subject="Planilla", body="Salario esperado") == parsed
    assert identify_received_payroll(parsed, subject="Orden Patronal", body="Salario reportado CCSS") == parsed


def test_unrelated_deposit_stays_other_income():
    parsed = {"transaction_type": "income", "description": "Depósito BAC", "category": "Otros ingresos"}
    assert identify_received_payroll(parsed, subject="Depósito aplicado", body="Transferencia recibida") == parsed


def test_received_payroll_links_same_month_ccss_report():
    connection = _Connection({"id": 9})
    candidate = {
        "transaction_date": "2026-09-21", "movement_kind": "payroll_deposit",
        "raw_payload": {"payroll_received": True},
    }
    assert link_received_payroll(connection, candidate_id=42, candidate=candidate, workspace_id="workspace-a") is True
    query, params = connection.calls[0]
    assert "payment_status='received'" in query
    assert params == (42, "2026-09-21", "workspace-a", "2026-09", 42)


def test_non_payroll_candidate_does_not_touch_reports():
    connection = _Connection()
    assert link_received_payroll(
        connection, candidate_id=1,
        candidate={"movement_kind": "transfer", "raw_payload": {}}, workspace_id="workspace-a",
    ) is False
    assert connection.calls == []
