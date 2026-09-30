"""Bank notices as they really arrive, parsed the way the Users sync parses them.

Every fixture reproduces the *structure* of a real BAC / MultiMoney notice
(labels, separators, date and amount formats, masked accounts, sender) and is
sent through ``plain_text_from_html`` exactly like the Gmail/Outlook sync, which
flattens the mail to one line. Names, merchants, amounts, accounts and
references are synthetic.
"""
from __future__ import annotations

import pytest

from backend.email_monitor import parser as p
from backend.email_monitor.gmail_content import plain_text_from_html
from backend.email_monitor.parser_identity import for_account_holder
from backend.user_product import gmail_service, microsoft_mail
from backend.user_product.candidate_resolution import semantic_fingerprint
from backend.user_product.financial_candidate import canonical_candidate
from backend.user_product.payroll_income import identify_received_payroll

HOLDER = "Maria Prueba"
IDENTITY = for_account_holder(HOLDER)
REF_A = "2026091210224000000000001"
REF_B = "2026091210224000000000002"


def parse(sender, subject, html, received_at, identity=IDENTITY):
    return p.parse_financial_email(subject, sender, plain_text_from_html(html), received_at, identity=identity)


def candidate(parsed, message_id="m1"):
    row = canonical_candidate(parsed, provider_message_id=message_id, subject="aviso")
    return {**row, "id": 1, "account_id": "account-a", "workspace_id": "workspace-a"}


def rows(pairs):
    return "".join(f"<tr><td>{label}</td><td>{value}</td></tr>" for label, value in pairs)


def bac_card(fecha, tipo="COMPRA", monto="CRC 12,345.00", greeting="MARIA PRUEBA SOLANO",
             merchant="DLC*UBER EATS", reference="627300000001", authorization="123456"):
    return (
        f"<div>BAC</div><h2>Hola {greeting}</h2><h5>A continuación le detallamos la transacción realizada:</h5>"
        "<table>" + rows([
            ("Comercio:", merchant), ("Ciudad y país:", "SAN JOSE, Costa Rica"), ("Fecha:", fecha),
            ("MASTER:", "************4321"), ("Autorización:", authorization), ("Referencia:", reference),
            ("Tipo de Transacción:", tipo), ("Monto:", monto),
        ]) + "</table><p>¿Tiene dudas sobre esta transacción?</p>"
    )


def bac_sinpe(sentence):
    return f"<p>{sentence} Muchas gracias. Notas Importantes: La información mostrada en este comprobante.</p>"


def mm_transfer(header, concept, amount, fecha, reference, origin_holder, origin_account,
                destination_holder, destination_account, origin_currency="CRC", destination_currency="CRC"):
    return (
        f"<p>Hola Maria,</p><p>{header}</p><p>Conocé más detalles sobre la operación realizada :</p>"
        "<p>Resumen de operación:</p><table>" + rows([
            ("Concepto:", concept), ("Monto:", amount), ("Fecha:", fecha), ("Referencia:", reference),
        ]) + "</table><p>Cuenta origen:</p><table>" + rows([
            ("Titular:", origin_holder), ("Cuenta:", f"{origin_currency} {origin_account}"),
        ]) + "</table><p>Cuenta destino:</p><table>" + rows([
            ("Titular:", destination_holder), ("Cuenta:", f"{destination_currency} {destination_account}"),
        ]) + "</table><p>Financiera MultiMoney S.A. es una entidad supervisada por la SUGEF.</p>"
    )


# --- Senders -----------------------------------------------------------------

REAL_BANK_SENDERS = [
    "notificacion@notificacionesbaccr.com",   # card alerts until 2026-07
    "notificacion@baccredomatic.cr",          # card alerts 2026-07/08
    "NotificacionBAC@baccredomatic.cr",       # card alerts since 2026-08
    "sinpe@notificacionesbaccr.com",          # SINPE until 2026-04
    "notificaciones@baccredomatic.cr",        # SINPE since 2026-04
]


@pytest.mark.parametrize("sender", REAL_BANK_SENDERS)
def test_every_observed_bac_sender_is_fetched_allowed_and_recognized(sender):
    assert f"from:{sender.lower()}" in gmail_service.FINVA_QUERY.lower()
    assert gmail_service.bank_sender_allowed(f"BAC Credomatic <{sender}>")
    assert microsoft_mail._sender_allowed(sender.lower())
    assert p.detect_bank(sender, "", "") == "bac"


@pytest.mark.parametrize("sender", [
    "info@baccredomatic.com",            # declined purchases: no money moved
    "info@multimoney.com",               # installment reminders
    "iniciodesesioncr@multimoney.com",   # sign-in alerts
    "noreply@wise.com",                  # not supported in this parser
    "NotificacionBAC@baccredomatic.cr.evil.com",
])
def test_senders_without_movement_evidence_stay_out(sender):
    assert not gmail_service.bank_sender_allowed(sender)
    assert not microsoft_mail._sender_allowed(sender.lower())


# --- BAC card alerts ---------------------------------------------------------

@pytest.mark.parametrize("fecha, date, time", [
    ("Sep 30, 2026, 02:13", "2026-09-30", "02:13:00"),
    ("Sep 23, 2026 , 13:32", "2026-09-23", "13:32:00"),   # space before the comma
    ("Sep 21,2026 , 00:00", "2026-09-21", "00:00:00"),    # no space after the day's comma
    ("Ago 31, 2026 , 18:32", "2026-08-31", "18:32:00"),
])
def test_card_alert_date_and_time_formats_of_the_current_senders(fecha, date, time):
    # Received the next UTC day: the date must come from the alert, not the header.
    parsed = parse("NotificacionBAC@baccredomatic.cr", "Notificación de transacción X", bac_card(fecha), "2026-10-02T13:53:00Z")
    assert (parsed["transaction_date"], parsed["transaction_time"]) == (date, time)


def test_card_purchase_is_an_expense_with_a_reference():
    parsed = parse("NotificacionBAC@baccredomatic.cr", "Notificación de transacción DLC*UBER EATS 23-09-2026 - 13:32",
                   bac_card("Sep 23, 2026 , 13:32"), "2026-09-23T19:32:51Z")
    assert parsed["transaction_type"] == "expense"
    assert parsed["bank_movement"] == "card_purchase" and parsed["financial_effect"] == "expense"
    assert parsed["reference"] == "627300000001"
    assert candidate(parsed)["external_reference"] == "627300000001"
    assert parsed["card_last4"] == "4321" and parsed["cardholder_mismatch"] is False


def test_card_automatic_charge_is_an_expense():
    parsed = parse("NotificacionBAC@baccredomatic.cr", "Notificación de transacción SEGURO",
                   bac_card("Sep 21,2026 , 00:00", tipo="CARGO AUTOMATICO", reference="BDPC0001"), "2026-09-21T13:53:23Z")
    assert parsed["transaction_type"] == "expense"
    assert parsed["bank_movement"] == "card_automatic_charge"
    assert parsed["reference"] == "BDPC0001"


def test_card_refund_is_never_ordinary_income():
    parsed = parse("notificacion@notificacionesbaccr.com", "Notificación de transacción TIENDA",
                   bac_card("Jun 29, 2026, 16:06", tipo="DEVOLUCION"), "2026-06-29T22:06:26Z")
    assert parsed["transaction_type"] != "income"
    assert parsed["transaction_type"] == "transfer" and parsed["movement_direction"] == "in"
    assert parsed["movement_kind"] == "refund" and parsed["financial_effect"] == "refund"
    assert candidate(parsed)["movement_kind"] == "refund"


def test_red_puntos_pago_is_a_reward_never_an_expense():
    parsed = parse("notificacion@notificacionesbaccr.com", "Notificación de transacción RED PUNTOS COLONES",
                   bac_card("Jul 5, 2024, 18:52", tipo="PAGO", merchant="RED PUNTOS COLONES"), "2024-07-06T00:52:33Z")
    assert parsed["transaction_type"] != "expense"
    assert parsed["transaction_type"] == "transfer" and parsed["movement_direction"] == "in"
    assert parsed["bank_movement"] == "card_points_credit" and parsed["financial_effect"] == "reward"


def test_zero_amount_verification_is_not_a_movement():
    parsed = parse("NotificacionBAC@baccredomatic.cr", "Notificación de transacción FIGMA",
                   bac_card("Sep 18, 2026, 21:36", monto="USD .00"), "2026-09-19T03:36:08Z")
    assert parsed["email_kind"] == "ignored"


def test_usd_card_purchase_keeps_its_original_currency():
    parsed = parse("NotificacionBAC@baccredomatic.cr", "Notificación de transacción NETFLIX.COM",
                   bac_card("Sep 30, 2026, 02:13", monto="USD 9.99", merchant="NETFLIX.COM"), "2026-09-30T08:14:00Z")
    assert (parsed["original_amount"], parsed["original_currency"]) == (9.99, "USD")


def test_additional_cardholder_is_flagged_for_review_not_reclassified():
    other = parse("NotificacionBAC@baccredomatic.cr", "Notificación de transacción Google One",
                  bac_card("Sep 1, 2026, 11:04", greeting="ANA OTRA PERSONA"), "2026-09-01T17:04:27Z")
    assert other["cardholder_mismatch"] is True
    assert other["transaction_type"] == "expense"  # billed to this account, but not the holder's own spending
    assert other["confidence"] < 0.99 and "otra persona" in other["confidence_reason"]
    own = parse("NotificacionBAC@baccredomatic.cr", "Notificación de transacción Google One",
                bac_card("Sep 1, 2026, 11:04"), "2026-09-01T17:04:27Z")
    assert own["cardholder_mismatch"] is False
    # Without the holder's name there is no evidence either way.
    neutral = parse("NotificacionBAC@baccredomatic.cr", "Notificación de transacción Google One",
                    bac_card("Sep 1, 2026, 11:04", greeting="ANA OTRA PERSONA"), "2026-09-01T17:04:27Z", identity=None)
    assert neutral["cardholder_mismatch"] is False


def test_the_same_card_alert_twice_is_one_movement_and_two_charges_are_two():
    html = bac_card("Sep 18, 2026, 21:36", monto="USD 15.00", merchant="FIGMA")
    first = candidate(parse("NotificacionBAC@baccredomatic.cr", "Notificación de transacción FIGMA", html, "2026-09-19T03:36:08Z"), "m1")
    copy = candidate(parse("NotificacionBAC@baccredomatic.cr", "Notificación de transacción FIGMA", html, "2026-09-19T03:36:34Z"), "m2")
    other = candidate(parse("NotificacionBAC@baccredomatic.cr", "Notificación de transacción FIGMA",
                            bac_card("Sep 18, 2026, 21:36", monto="USD 15.00", merchant="FIGMA", reference="627300000009"),
                            "2026-09-19T03:36:40Z"), "m3")
    assert semantic_fingerprint(first) and semantic_fingerprint(first) == semantic_fingerprint(copy)
    assert semantic_fingerprint(first) != semantic_fingerprint(other)


# --- BAC SINPE ---------------------------------------------------------------

def test_sinpe_credit_is_an_inbound_transfer_not_income():
    parsed = parse(
        "notificaciones@baccredomatic.cr", "Notificación de Transferencia",
        bac_sinpe("Hola MARIA PRUEBA SOLANO : BAC le comunica que la transferencia SINPE en tiempo real con el número "
                  f"de referencia {REF_A}, se acreditó en la cuenta IBAN CR0001XXXXXXXXXXXX1111 por un monto de "
                  "20,000.00 Colones, por concepto de ahorro______.Día y hora 12/09/2026 07:22:13 p.m."),
        "2026-09-13T01:22:31Z",
    )
    assert parsed["transaction_type"] == "transfer" and parsed["movement_direction"] == "in"
    assert parsed["bank_movement"] == "sinpe_in" and parsed["financial_effect"] == "review"
    assert parsed["reference"] == REF_A
    assert parsed["destination_account"] == "****1111"
    assert (parsed["transaction_date"], parsed["transaction_time"]) == ("2026-09-12", "19:22:13")


def test_sinpe_debit_is_an_outbound_transfer_not_an_expense():
    parsed = parse(
        "notificaciones@baccredomatic.cr", "Notificación de Transferencia",
        bac_sinpe(f"Hola: MARIA PRUEBA SOLA : BAC le comunica que la transferencia SINPE en tiempo real con el número de referencia {REF_B}, "
                  "debitando su cuenta IBAN CR0001XXXXXXXXXXXX2222 por un monto de 40,873.01 Colones. "
                  "Día y hora: 28/09/2026 11:04:21 a.m. fue aplicada correctamente."),
        "2026-09-28T17:04:32Z",
    )
    assert parsed["transaction_type"] == "transfer" and parsed["movement_direction"] == "out"
    assert parsed["bank_movement"] == "sinpe_out"
    assert parsed["amount"] == 40_873.01 and parsed["reference"] == REF_B
    assert parsed["origin_account"].endswith("2222")


def test_old_sinpe_sender_with_reference_in_the_subject_and_no_time():
    parsed = parse(
        "sinpe@notificacionesbaccr.com", f"Notificación de Transferencia{REF_A}",
        bac_sinpe("Hola MARIA PRUEBA SOLANO : BAC le comunica que la transferencia SINPE en tiempo real con el número de "
                  f"referencia {REF_A}, se aplicó en la cuenta IBAN CR0001XXXXXXXXXXXX1111 por un monto de 69,100.00 Colones."),
        "2024-12-30T14:22:31Z",
    )
    assert parsed["movement_direction"] == "in" and parsed["transaction_type"] == "transfer"
    assert parsed["reference"] == REF_A and parsed["transaction_time"] is None


def test_rejected_sinpe_moves_nothing():
    parsed = parse(
        "sinpe@notificacionesbaccr.com", f"Notificación de Transferencia{REF_A}",
        bac_sinpe(f"Hola: MARIA PRUEBA : BAC le comunica que la transferencia SINPE en tiempo real con el número de referencia {REF_A}, "
                  "con orden de débito a la cuenta IBAN CR0001XXXXXXXXXXXX2222 por un monto de 34,288.00 Colones, fue rechazada "
                  "por el siguiente motivo: FondosInsuficientes. Día y hora: 23/04/2026 11:06:23 a.m."),
        "2026-04-23T17:06:31Z",
    )
    assert parsed["email_kind"] == "ignored"


@pytest.mark.parametrize("concept, expected", [("pago de planilla", "income"), ("ahorro", "transfer")])
def test_sinpe_credit_is_salary_only_with_explicit_payroll_words(concept, expected):
    html = bac_sinpe(
        f"Hola MARIA PRUEBA : BAC le comunica que la transferencia SINPE en tiempo real con el número de referencia {REF_A}, "
        "se acreditó en la cuenta IBAN CR0001XXXXXXXXXXXX1111 por un monto de 500,000.00 Colones, por concepto de "
        f"{concept}______.Día y hora 15/09/2026 09:00:00 a.m."
    )
    parsed = parse("notificaciones@baccredomatic.cr", "Notificación de Transferencia", html, "2026-09-15T15:00:05Z")
    result = identify_received_payroll(parsed, subject="Notificación de Transferencia", body=plain_text_from_html(html))
    assert result["transaction_type"] == expected
    assert (result.get("category") == "Salario") is (expected == "income")


# --- MultiMoney ---------------------------------------------------------------

def test_multimoney_new_era_direction_comes_from_the_holders_accounts():
    outbound = parse("multimoneycr@multimoney.com", "Transacción realizada", mm_transfer(
        "Notificación de transferencia", "Ropa", "¢25,000.00", "28/09/2026 12:26:01", REF_A,
        "MARIA PRUEBA SOLANO", "CR74****1234", "ANA OTRA PERSONA", "CR15****9876"), "2026-09-28T18:26:05Z")
    inbound = parse("multimoneycr@multimoney.com", "Transacción realizada", mm_transfer(
        "Notificación de transferencia", "abono", "¢25,000.00", "28/09/2026 15:36:13", REF_B,
        "ANA OTRA PERSONA", "CR15****9876", "MARIA PRUEBA SOLANO", "CR74****1234"), "2026-09-28T21:36:20Z")
    assert (outbound["movement_direction"], inbound["movement_direction"]) == ("out", "in")
    assert outbound["transaction_type"] == inbound["transaction_type"] == "transfer"
    assert (outbound["origin_account"], outbound["destination_account"]) == ("****1234", "****9876")
    assert outbound["reference"] == REF_A
    # Neutral parse (no holder): the direction is unknown, never guessed.
    neutral = parse("multimoneycr@multimoney.com", "Transacción realizada", mm_transfer(
        "Notificación de transferencia", "Ropa", "¢25,000.00", "28/09/2026 12:26:01", REF_A,
        "MARIA PRUEBA SOLANO", "CR74****1234", "ANA OTRA PERSONA", "CR15****9876"), "2026-09-28T18:26:05Z", identity=None)
    assert neutral["movement_direction"] == "unknown"


def test_direction_never_falls_back_to_the_owner_identity(monkeypatch):
    # The Owner's configured name must not shape another account's parse.
    monkeypatch.setenv("OWNER_DISPLAY_NAME", "Maria Prueba")
    html = mm_transfer("Notificación de transferencia", "Ropa", "¢25,000.00", "28/09/2026 12:26:01", REF_A,
                       "MARIA PRUEBA SOLANO", "CR74****1234", "ANA OTRA PERSONA", "CR15****9876")
    other_user = for_account_holder("Ana Otra")
    assert parse("multimoneycr@multimoney.com", "Transacción realizada", html, "2026-09-28T18:26:05Z", identity=None)["movement_direction"] == "unknown"
    assert parse("multimoneycr@multimoney.com", "Transacción realizada", html, "2026-09-28T18:26:05Z", identity=other_user)["movement_direction"] == "in"


def test_truncated_bank_name_still_names_the_holder():
    parsed = parse("multimoneycr@multimoney.com", "Transacción realizada", mm_transfer(
        "Notificación de transferencia", "Ropa", "¢25,000.00", "28/09/2026 12:26:01", REF_A,
        "MARIA LUISA PRUE", "CR74****1234", "ANA OTRA PERSONA", "CR15****9876"), "2026-09-28T18:26:05Z")
    assert parsed["movement_direction"] == "out"
    # A short fragment is not enough evidence of the holder.
    assert IDENTITY.names_holder("MARIA LUISA PRU") is False


def test_own_savings_funding_is_never_income():
    parsed = parse("multimoneycr@multimoney.com", "Transacción realizada", mm_transfer(
        "Recepción de fondos", "INVERSIÓN VISTA SMART COL", "¢50,000.00", "30/10/2025 11:07:08", REF_A,
        "MARIA PRUEBA SOL", "CR42****1111", "MARIA PRUEBA SOLANO", "CR74****1234"), "2025-10-30T17:07:20Z")
    assert parsed["transaction_type"] != "income"
    assert parsed["transaction_type"] == "transfer" and parsed["movement_direction"] == "in"
    assert parsed["bank_movement"] == "own_account_funding" and parsed["financial_effect"] == "own_transfer_likely"
    assert (parsed["origin_account"], parsed["destination_account"]) == ("****1111", "****1234")


def test_realtime_debit_is_an_outbound_transfer_not_an_expense():
    html = (
        "<p>Hola Maria,</p><p>Notificación de transferencia</p><p>Te informamos que se aplicó un débito en tiempo real "
        "a tu cuenta. Conocé más detalles:</p><p>Resumen de operación:</p><table>" + rows([
            ("Cuenta:", "CR74****1234"), ("Concepto:", "Débito aplicado por otra entidad financiera"),
            ("Monto:", "¢20,000.00"), ("Fecha:", "12/09/2026 12:49:52"), ("Referencia:", REF_A),
        ]) + "</table><p>Financiera MultiMoney S.A.</p>"
    )
    parsed = parse("multimoneycr@multimoney.com", "Transacción realizada", html, "2026-09-12T18:49:55Z")
    assert parsed["transaction_type"] == "transfer" and parsed["movement_direction"] == "out"
    assert parsed["bank_movement"] == "realtime_debit" and parsed["financial_effect"] == "review"
    assert parsed["origin_account"] == "****1234" and parsed["reference"] == REF_A


def test_same_holder_currency_exchange_is_an_own_fx_move():
    parsed = parse("multimoneycr@multimoney.com", "Transacción realizada", mm_transfer(
        "Notificación de transferencia", "cambio", "$1,400.00", "21/10/2025 16:05:35", REF_A,
        "MARIA PRUEBA SOLANO", "CR****1234", "MARIA PRUEBA SOLANO", "CR****5678",
        origin_currency="CRC", destination_currency="USD"), "2025-10-21T22:05:41Z")
    assert parsed["bank_movement"] == "fx_conversion" and parsed["financial_effect"] == "own_transfer_likely"
    assert (parsed["original_amount"], parsed["original_currency"]) == (1400.0, "USD")
    assert parsed["transaction_type"] == "transfer"


@pytest.mark.parametrize("fecha, received, date, time", [
    ("01/04/2026 21:21:46", "2026-04-01T21:21:50Z", "2026-04-01", "15:21:46"),   # printed in UTC
    ("29/01/2026 01:30:42", "2026-01-29T01:30:50Z", "2026-01-28", "19:30:42"),   # UTC, previous CR day
    ("28/09/2026 12:26:01", "2026-09-28T18:26:05Z", "2026-09-28", "12:26:01"),   # printed in CR time
])
def test_multimoney_utc_clock_is_read_as_utc_only_when_it_matches_the_email(fecha, received, date, time):
    parsed = parse("multimoneycr@multimoney.com", "Transacción realizada", mm_transfer(
        "Notificación de transferencia", "Ropa", "¢25,000.00", fecha, REF_A,
        "MARIA PRUEBA SOLANO", "CR74****1234", "ANA OTRA PERSONA", "CR15****9876"), received)
    assert (parsed["transaction_date"], parsed["transaction_time"]) == (date, time)


def test_the_same_multimoney_notice_twice_is_one_movement():
    html = mm_transfer("Notificación de transferencia", "Ropa", "¢25,000.00", "29/01/2026 01:30:42", REF_A,
                       "MARIA PRUEBA SOLANO", "CR****1234", "ANA OTRA PERSONA", "CR****9876")
    first = candidate(parse("multimoneycr@multimoney.com", "Transacción realizada", html, "2026-01-29T01:30:50Z"), "m1")
    copy = candidate(parse("multimoneycr@multimoney.com", "Transacción realizada", html, "2026-01-29T01:30:50Z"), "m2")
    assert semantic_fingerprint(first) and semantic_fingerprint(first) == semantic_fingerprint(copy)


@pytest.mark.parametrize("subject, html", [
    ("¡Te hemos acreditado!",
     "<p>¡Te hemos acreditado!</p><p>¡Buenas noticias MARIA! De tu línea de crédito te hemos acreditado: CRC 300,000.00 "
     "a la cuenta CR74****1234</p><table>" + rows([("Nº de referencia:", REF_A), ("Fecha y hora:", "28/09/2026 12:23:30")]) + "</table>"),
    ("Depositamos tu crédito",
     "<p>Te hemos acreditado: CRC 500,000.00 a la cuenta CR74031000000000001234</p><p>Detalle del movimiento:</p><table>"
     + rows([("Tipo de movimiento:", "Crédito"), ("Nº de referencia:", REF_B)]) + "</table>"),
])
def test_loan_disbursement_is_debt_never_income(subject, html):
    parsed = parse("multimoneycr@multimoney.com", subject, html, "2026-09-28T18:23:35Z")
    assert parsed["email_kind"] == "movement"
    assert parsed["transaction_type"] == "transfer" and parsed["movement_direction"] == "in"
    assert parsed["bank_movement"] == "loan_disbursement" and parsed["financial_effect"] == "liability"
    assert parsed["movement_kind"] == "loan_disbursement"
    # Only the last four digits are kept, even when the notice prints the full IBAN.
    assert parsed["destination_account"] == "****1234"


def test_loan_payment_sent_twice_is_one_payment():
    html = ("<p>Recibimos tu pago.</p><p>MultiMoney</p><table>" + rows([
        ("Fecha y hora:", "Sep 28 2026 3:38PM"), ("Monto:", "¢120,000.00"), ("Pagaré:", "R-000123"),
    ]) + "</table>")
    first = parse("multimoneycr@multimoney.com", "Recibimos tu pago.", html, "2026-09-28T21:40:12Z")
    assert first["transaction_type"] == "debt_payment" and first["bank_movement"] == "loan_payment"
    assert first["reference"].startswith("R-000123")
    copy = parse("multimoneycr@multimoney.com", "Recibimos tu pago.", html, "2026-09-28T21:40:12Z")
    assert semantic_fingerprint(candidate(first, "m1")) == semantic_fingerprint(candidate(copy, "m2"))


@pytest.mark.parametrize("subject, html", [
    ("Pronto estaremos realizando el rebajo de tu cuota",
     "<p>MultiMoney</p><p>Fecha de débito: lunes 1 de octubre Cuota: ¢12500</p>"),
    ("Aprovechá tu crédito 💰",
     "<p>MultiMoney͏ ͏ ͏ Pedí hasta ₡1,000,000.00 Monto disponible Fecha límite 30/09/2026</p>"),
])
def test_reminders_and_promotions_are_not_movements(subject, html):
    parsed = parse("multimoneycr@multimoney.com", subject, html, "2026-09-30T00:00:10Z")
    assert parsed["email_kind"] != "movement"


# --- BAC alert receipts --------------------------------------------------------

def card_payment(card_currency, paid, debited, rate):
    return ("<h3>Comprobante de Pago de Tarjeta</h3><p>Tarjeta de Crédito</p><table>" + rows([
        ("Número:", "5400-12**-****-4321"), ("Nombre:", "PRUEBA/MARIA"), ("Monto del pago:", f"{paid} {card_currency}"),
    ]) + "</table><p>Cuenta Origen</p><table>" + rows([
        ("Número:", "900001111"), ("Nombre:", "MARIA PRUEBA SOLANO"), ("Monto del débito:", f"{debited} CRC"),
        ("Tipo de Cambio:", rate), ("Referencia:", "0042"), ("Fecha de pago:", "2026/09/28 11:10:12"),
    ]) + "</table>")


@pytest.mark.parametrize("card_currency, paid, debited, rate", [
    ("CRC", "207,684.29", "207,684.29", "1.00"),
    ("USD", "820.93", "379,269.66", "462.00"),
])
def test_card_payment_is_a_move_between_own_products_not_an_expense(card_currency, paid, debited, rate):
    parsed = parse("alerta@baccredomatic.com", "Notificación de Pago", card_payment(card_currency, paid, debited, rate), "2026-09-28T17:10:15Z")
    assert parsed["transaction_type"] == "transfer" and parsed["movement_direction"] == "out"
    assert parsed["movement_kind"] == "card_payment" and parsed["financial_effect"] == "own_transfer_likely"
    assert parsed["amount"] == p._parse_number(debited)
    assert (parsed["origin_account"], parsed["destination_account"]) == ("****1111", "****4321")
    assert parsed["reference"] == "0042 2026-09-28 11:10:12"
    assert (parsed["exchange_rate"] is not None) is (card_currency == "USD")


def test_service_payment_is_an_expense_identified_by_its_authorization():
    def bill(authorization):
        return ("<h3>Comprobante de Pago de Servicios</h3><p>Estimado(a) Cliente: Se ha realizado un pago de servicio de "
                "TELEFONIA EJEMPLO desde Banca Móvil .</p><table>" + rows([
                    ("Alias:", "Celular"), ("Descripción:", "Línea"), ("Fecha de Pago:", "2026-09-05 13:43:06.123"),
                    ("Número de Autorización:", authorization), ("Forma de Pago:", "******************1111"),
                    ("Monto:", "33,783.29 CRC"), ("Monto:", "33783.29"),
                ]) + "</table>")
    first = parse("alerta@baccredomatic.com", "Notificación de pago", bill("123456789"), "2026-09-05T19:43:09Z")
    assert first["transaction_type"] == "expense" and first["amount"] == 33_783.29
    assert first["bank_movement"] == "service_payment" and first["reference"] == "123456789"
    second = parse("alerta@baccredomatic.com", "Notificación de pago", bill("123456790"), "2026-09-05T19:43:09Z")
    assert semantic_fingerprint(candidate(first, "m1")) != semantic_fingerprint(candidate(second, "m2"))


def test_cardless_withdrawal_code_moves_nothing_and_withdrawal_is_cash_out():
    created = parse("alerta@baccredomatic.com", "Creación de retiro sin tarjeta",
                    "<p>Monto: 6,000.00 CRC Validez: Para ser retirado el 22/10/2024*</p>", "2024-10-22T14:10:43Z")
    assert created["email_kind"] == "ignored"
    withdrawn = parse("alerta@baccredomatic.com", "Retiro sin tarjeta retirado",
                      "<p>El dinero se retiró éxitosamente</p><table>" + rows([
                          ("Monto:", "5,000.00 CRC"), ("Fecha y hora en qué se retiró el dinero:", "22/10/2024 08:11:00"),
                          ("Lugar donde se retiró el dinero:", "ATM 0001"),
                      ]) + "</table>", "2024-10-22T14:11:01Z")
    assert withdrawn["transaction_type"] == "transfer" and withdrawn["movement_kind"] == "cash_withdrawal"
    assert (withdrawn["amount"], withdrawn["transaction_time"]) == (5000.0, "08:11:00")
