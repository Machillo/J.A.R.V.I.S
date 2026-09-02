from backend.email_monitor.statement_reconciliation import parse_multimoney_statement


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
