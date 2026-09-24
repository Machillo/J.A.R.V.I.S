from backend.email_monitor.payroll_statement import parse_ccss_order_patronal


def test_parse_ccss_order_patronal_salary_actual():
    text = """
    CAJA COSTARRICENSE DE SEGURO SOCIAL
    Orden Patronal Digital
    1123 0-100000000 PRUEBA SINTETICA MARIA JOSE 2-00000000000-001-001
    Período Salario Tras. Anterior Actual Subsidio Diario
    JULIO 2026 500,000.00 510,000.00 520,000.00 10,000.00
    El código verificador asociado a este documento es: OP000000001
    """
    result = parse_ccss_order_patronal(
        "Generación de Orden Patronal Digital", "ccss@ccss.sa.cr", text
    )
    assert result == {
        "period_month": "2026-07",
        "trans_previous_salary": 500_000.00,
        "previous_salary": 510_000.00,
        "reported_salary": 520_000.00,
        "daily_subsidy": 10_000.00,
        "employer_number": "2-00000000000-001-001",
        "verification_code": "OP000000001",
    }


def test_rejects_non_ccss_documents():
    assert parse_ccss_order_patronal("Orden", "otro@example.com", "JULIO 2026 1.00 2.00 3.00 4.00") is None
