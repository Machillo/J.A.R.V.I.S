"""Payroll receipts are evidence of a salary, never a movement. Synthetic data only."""
from backend.email_monitor.payroll_statement import parse_payroll_receipt

RECEIPT = """COMPROBANTE DE PAGO

| EMPRESA EJEMPLO, S.A. | PLANILLA SEMANAL COLONES |
| COMPROBANTE DE PAGO PERIODO: 203011 DEL 08/03/2030 AL 14/03/2030 |
| |
| FECHA EMISIÓN: 19/03/2030 |

| EMPLEADO: | | 000000000 PERSONA EJEMPLO |
| SALARIO HORA JORNADA DIURNA: | | ¢1000.00 |

| |
| <<INGRESOS>> |
| HORAS REGULARES TRABAJADAS (40 Horas) | ¢ 40,000.00 |
| TIEMPO EXTRA- OT1 (4 Horas) | ¢ 6,000.00 |
| FERIADO TRABAJADO (8 Horas) | ¢ 16,000.00 |
| PAGO FERIADO | ¢ 8,000.00 |
| VACACION | ¢ 5,000.00 |
| BONO POR METRICAS | ¢ 2,500.00 |

| |
| <<DESCUENTOS>> |
| CCSS 10.83% | ¢ 8,066.25 |
| APORTE OBRERO 5% ASOCIACION SOLIDARISTA | ¢ 3,875.00 |
| PRESTAMO BANCO EJEMPLO | ¢ 9,000.00 |

| |
| TOTAL INGRESOS: | ¢ 77,500.00 |

| |
| TOTAL DESCUENTOS: | ¢ 20,941.25 |

| |
| NETO A PAGAR: ¢ 56,558.75 |
"""


def test_a_receipt_is_parsed_by_its_structure_and_adds_up():
    parsed = parse_payroll_receipt(RECEIPT)
    assert parsed["kind"] == "payroll_receipt"
    assert (parsed["period_code"], parsed["period_start"], parsed["period_end"], parsed["issue_date"]) == ("203011", "2030-03-08", "2030-03-14", "2030-03-19")
    assert (parsed["gross"], parsed["deductions_total"], parsed["net"]) == (77500.0, 20941.25, 56558.75)
    assert parsed["consistent"] is True and parsed["needs_review"] is False


def test_each_income_line_keeps_its_own_meaning_and_hours():
    kinds = {line["kind"]: (line["amount"], line["hours"]) for line in parse_payroll_receipt(RECEIPT)["income_lines"]}
    assert kinds == {"ordinary": (40000.0, 40.0), "overtime": (6000.0, 4.0), "holiday_worked": (16000.0, 8.0),
                     "holiday_paid": (8000.0, None), "vacation": (5000.0, None), "bonus": (2500.0, None)}


def test_deductions_never_create_movements_and_loans_stay_loans():
    deductions = parse_payroll_receipt(RECEIPT)["deduction_lines"]
    assert [d["kind"] for d in deductions] == ["social_security", "association", "loan_repayment"]
    assert all(d["creates_movement"] is False for d in deductions)   # a loan repaid through payroll is not a new expense


def test_a_receipt_that_does_not_add_up_is_flagged_not_trusted():
    broken = RECEIPT.replace("NETO A PAGAR: ¢ 56,558.75", "NETO A PAGAR: ¢ 56,000.00")
    parsed = parse_payroll_receipt(broken)
    assert parsed["consistent"] is False and parsed["needs_review"] is True


def test_an_unknown_line_needs_review_instead_of_a_guess():
    odd = RECEIPT.replace("| BONO POR METRICAS | ¢ 2,500.00 |", "| CONCEPTO NUEVO | ¢ 2,500.00 |")
    parsed = parse_payroll_receipt(odd)
    assert any(line["kind"] == "other" for line in parsed["income_lines"]) and parsed["needs_review"] is True


def test_other_documents_are_not_receipts():
    assert parse_payroll_receipt("Estimado cliente, adjunto el recibo del pago de su operación de crédito.") is None
    assert parse_payroll_receipt("COMPROBANTE DE PAGO sin período ni neto") is None
