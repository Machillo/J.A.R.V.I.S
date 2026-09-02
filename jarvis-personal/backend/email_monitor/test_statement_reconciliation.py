from backend.email_monitor.statement_reconciliation import parse_bac_statement, parse_multimoney_statement


def test_parse_multimoney_statement_movements():
    text = """01/08/2026
30054012
NUTRICIONISTA
16,500.00
0.00
69,574.41
5597291
27/08/2026
30630833
INVERSIÓN VISTA SMART COL
0.00
103,263.77
544,160.41
5736763
31/08/2026
30948707
CAPITALIZACIÓN NORMAL DE INTERESES
0.00
1,461.71
436,821.99
5820698"""

    rows = parse_multimoney_statement(text)

    assert len(rows) == 3
    assert rows[0]["description"] == "NUTRICIONISTA"
    assert rows[0]["amount"] == 16500
    assert rows[0]["transaction_type"] == "expense"
    assert rows[1]["ignored"] is True
    assert rows[2]["transaction_type"] == "income"
    assert rows[2]["category"] == "Inversión"


def test_parse_bac_account_statement_movements():
    text = """DETALLE DE MOVIMIENTOS
Fecha
Referencia
Descripción
Débitos
Créditos
Saldo
01/08/2026
889900
SUPERMERCADO
12,500.00
0.00
87,500.00
02/08/2026
889901
DEPOSITO
0.00
25,000.00
112,500.00"""

    rows = parse_bac_statement(text)

    assert len(rows) == 2
    assert rows[0]["reference"] == "889900"
    assert rows[0]["transaction_type"] == "expense"
    assert rows[1]["transaction_type"] == "income"


def test_bac_statement_without_signed_ledger_columns_is_rejected():
    text = """Fecha Descripción Monto
01/08/2026
COMPRA SIN SIGNO
12,500.00"""

    assert parse_bac_statement(text) == []
