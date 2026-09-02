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


def test_parse_real_bac_credit_card_sections():
    text = """TARJETA DE CREDITO
Fecha de corte: 21-AGO-26
B) Detalle de compras del periodo
************3131 KENNETH
072799100801 25-JUL-26 DLC*ARCOS DORADOS_ SAN JOSE_ CRI CRC 5,340.00
072699100801 25-JUL-26 APPLE.COM/BILL_ CUPERTINO_ USA USD 6.99
Total de compras del periodo (del 22-JUL-26 al 21-AGO-26) 5,340.00 6.99
C) Detalle de intereses
Monto por intereses corrientes del periodo actual 424.05 0.00
Total por concepto de intereses 424.05 3.87
D) Detalle de otros cargos
************3131 KENNETH
0813101215476 13-AGO-26 IVA -PLAYSTATION San Mateo USD 0.39
Total por concepto otros cargos 0.00 0.39
E) Detalle de productos y servicios de elección voluntaria
************5108 KENNETH
072216766936 21-JUL-26 SEGURO PROTECCION DE INGR E. CA BDPC549 CRC 2,950.00
Total por concepto de productos y servicios de elección voluntaria 2,950.00 0.00"""

    rows = parse_bac_statement(text)

    assert len(rows) == 6
    assert rows[0]["card_last4"] == "3131"
    assert rows[0]["amount"] == 5340
    assert rows[1]["original_currency"] == "USD"
    assert rows[1]["original_amount"] == 6.99
    assert rows[1]["amount"] == 3460.05
    assert rows[2]["statement_section"] == "interest"
    assert rows[2]["transaction_date"] == "2026-08-21"
    assert rows[3]["statement_section"] == "interest"
    assert rows[4]["statement_section"] == "charges"
    assert rows[5]["statement_section"] == "voluntary"
