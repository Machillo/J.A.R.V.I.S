from backend.email_monitor.payroll_statement import parse_ccss_order_patronal


def test_parse_real_ccss_order_patronal_salary_actual():
    text = """
    CAJA COSTARRICENSE DE SEGURO SOCIAL
    Orden Patronal Digital
    1123 0-117620022 ALVARADO OBANDO KENNETH ANDRES 2-03101545222-001-001
    Período Salario Tras. Anterior Actual Subsidio Diario
    JULIO 2026 548,416.50 582,616.53 712,647.40 12,291.20
    El código verificador asociado a este documento es: OP125431859
    """
    result = parse_ccss_order_patronal(
        "Generación de Orden Patronal Digital", "ccss@ccss.sa.cr", text
    )
    assert result == {
        "period_month": "2026-07",
        "trans_previous_salary": 548_416.50,
        "previous_salary": 582_616.53,
        "reported_salary": 712_647.40,
        "daily_subsidy": 12_291.20,
        "employer_number": "2-03101545222-001-001",
        "verification_code": "OP125431859",
    }


def test_rejects_non_ccss_documents():
    assert parse_ccss_order_patronal("Orden", "otro@example.com", "JULIO 2026 1.00 2.00 3.00 4.00") is None
