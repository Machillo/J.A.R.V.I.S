"""A BAC deposit notice names the receiving account, never the payer.

Money entering an account with no visible origin may be salary, a refund, a loan
or the holder's own money from another bank: it is not income until something
proves it. The notice is income only on its own words (salary/payroll language);
otherwise it is an inbound transfer whose effect the user decides (review).
Every fixture is synthetic: names, accounts, amounts and references are invented.
"""
from __future__ import annotations

from backend.email_monitor import parser as p
from backend.email_monitor import movement_taxonomy as mt
from backend.email_monitor.gmail_content import plain_text_from_html
from backend.email_monitor.parser_identity import for_account_holder
from backend.user_product.financial_candidate import canonical_candidate
from backend.user_product.payroll_income import identify_received_payroll

SENDER = "alerta@baccredomatic.com"
IDENTITY = for_account_holder("Maria Prueba")


def deposit(amount="CRC 250,000.00", detail="", subject="Depósito"):
    html = (
        "<p>Hola MARIA PRUEBA SOLANO ,</p>"
        f"<table><tr><td>Ha recibido un depósito por</td><td>{amount}</td></tr></table>"
        "<p>Estimado(a) cliente MARIA PRUEBA SOLANO BAC le informa que se ha realizado un depósito a la cuenta en CRC, "
        f"número CR****************0000, por un monto de {amount.split()[-1]} . {detail}</p>"
        "<table><tr><td>Depositado a</td><td>MARIA PRUEBA SOLANO</td></tr>"
        "<tr><td>Cuenta destino</td><td>CR****************0000</td></tr>"
        "<tr><td>Tipo de movimiento</td><td>Crédito</td></tr>"
        f"<tr><td>Monto enviado</td><td>{amount.split()[-1]} CRC.</td></tr>"
        "<tr><td>Fecha</td><td>12/3/2026 a las 9:5:04</td></tr>"
        "<tr><td>Número de referencia</td><td>11112222</td></tr></table>"
        "<p>Por favor verifique su transacción en el histórico transaccional de nuestra Banca en Línea.</p>"
    )
    return p.parse_financial_email(subject, SENDER, plain_text_from_html(html), "2026-03-12T15:05:10Z", identity=IDENTITY)


def test_a_deposit_with_no_visible_payer_is_not_income():
    parsed = deposit()
    assert parsed["amount"] == 250000.0
    assert parsed["transaction_type"] == "transfer"
    assert parsed["movement_direction"] == "in"
    assert parsed["bank_movement"] == mt.TRANSFER_IN
    assert parsed["financial_effect"] == mt.REVIEW
    assert parsed["category"] != "Otros ingresos"
    row = canonical_candidate(parsed, provider_message_id="m1", subject="Depósito")
    assert row["transaction_type"] == "transfer" and row["movement_direction"] == "in"
    # Payroll identification does not invent salary from it either.
    assert identify_received_payroll(parsed, subject="Depósito", body="Ha recibido un depósito") == parsed


def test_a_deposit_whose_notice_says_salary_stays_income_and_becomes_salary():
    parsed = deposit(detail="Pago de planilla quincenal.")
    assert parsed["transaction_type"] == "income"
    salary = identify_received_payroll(parsed, subject="Depósito", body="Pago de planilla quincenal.")
    assert salary["category"] == "Salario" and salary["payroll_received"] is True


def test_a_rejected_deposit_is_still_not_a_movement():
    parsed = deposit(detail="El depósito fue rechazado.")
    assert parsed["email_kind"] == "ignored"
