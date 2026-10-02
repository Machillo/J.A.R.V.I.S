"""What a bank notice does not prove must not look proven.

Found by reconciling a real mailbox against the bank statements (no real data is
used here: every name, account, amount and reference below is synthetic):

- a card notice in USD prints no exchange rate: the caller's default is an assumption;
- a merchant no rule knows gets a guessed category that storage turns into a default;
- a credit drawn against a card ("desembolso") is debt and was ignored;
- a real-time debit announced by one institution can be rejected by the other one:
  the rejection carries the same reference and the debit never happens.
"""
from __future__ import annotations

import pytest

from backend.email_monitor import parser as p
from backend.email_monitor import service
from backend.email_monitor.test_bank_evidence_formats import (
    REF_A, REF_B, bac_card, bac_sinpe, card_payment, parse, rows,
)

CARD_SENDER = "NotificacionBAC@baccredomatic.cr"


def card(merchant, monto="CRC 12,345.00"):
    return parse(CARD_SENDER, f"Notificación de transacción {merchant}", bac_card("Sep 23, 2026, 13:32", monto=monto, merchant=merchant), "2026-09-23T19:32:10Z")


# --- Exchange rate ------------------------------------------------------------

def test_usd_purchase_rate_is_an_assumption_and_never_auto_commits():
    parsed = card("SOFTWARE EJEMPLO", monto="USD 20.00")
    assert (parsed["original_amount"], parsed["original_currency"]) == (20.0, "USD")
    assert parsed["needs_exchange_rate"] is True and parsed["exchange_rate_source"] == "assumed_default"
    assert parsed["confidence"] < service.AUTO_COMMIT_CONFIDENCE


def test_crc_purchase_needs_no_rate_and_keeps_full_confidence():
    parsed = card("DLC*UBER EATS")
    assert "needs_exchange_rate" not in parsed and parsed["exchange_rate_source"] is None
    assert parsed["confidence"] >= service.AUTO_COMMIT_CONFIDENCE


def test_card_payment_receipt_rate_is_evidence():
    parsed = parse("alerta@baccredomatic.com", "Notificación de Pago", card_payment("USD", "100.00", "46,200.00", "462.00"), "2026-09-28T17:10:15Z")
    assert parsed["exchange_rate"] == 462.0 and parsed["exchange_rate_source"] == "email"
    assert "needs_exchange_rate" not in parsed


# --- Category -----------------------------------------------------------------

def test_unknown_merchant_category_is_a_guess_and_never_auto_commits():
    parsed = card("NEGOCIO DESCONOCIDO XYZ")
    assert parsed["category"] == p.FALLBACK_EXPENSE_CATEGORY
    assert parsed["needs_category"] is True and parsed["category_source"] == "fallback"
    assert parsed["confidence"] < service.AUTO_COMMIT_CONFIDENCE


@pytest.mark.parametrize("merchant, category", [
    ("ESTACION DE SERV.LA EJEMPLO", "Gasolina"),    # BAC truncates the merchant to ~22 characters
    ("DEKRA EJEMPLO (188)", "Transporte"),          # vehicle inspection
    ("FERRETERIA EJEMPLO SA", "Compras"),
    ("CLOUDFLARE", "Servicios"),
    ("FIGMA", "Servicios"),
])
def test_generic_merchants_seen_in_bank_mail_have_a_category(merchant, category):
    parsed = card(merchant)
    assert parsed["category"] == category and "needs_category" not in parsed


# --- Loan disbursement --------------------------------------------------------

def bac_disbursement(amount="CRC 100,000.00"):
    return (
        "<h1>Hola MARIA PRUEBA ,</h1><h2>Ha recibido su desembolso</h2>" f"<h2>{amount}</h2>"
        "<p>A continuación le detallamos las condiciones del extrafinanciamiento asociado a su tarjeta:</p><table>" + rows([
            ("Desembolsado a", "MARIA PRUEBA SOLANO A la cuenta900001111"), ("Tarjeta de cobro", "540012XXXXXX4321"),
            ("Moneda", "CRC"), ("Plazo", "12 Meses"), ("Cuota mensual", "CRC 9,000.00"),
        ]) + "</table>"
    )


def test_bac_credit_disbursement_is_debt_never_income_nor_ignored():
    parsed = parse("info@baccredomatic.com", "Notificación Extrafinanciamiento, Oportunidad Aprobada", bac_disbursement(), "2026-05-27T23:10:00Z")
    assert parsed["email_kind"] == "movement" and parsed["transaction_type"] == "transfer"
    assert parsed["bank_movement"] == "loan_disbursement" and parsed["financial_effect"] == "liability"
    assert parsed["amount"] == 100000.0 and parsed["movement_direction"] == "in"
    assert parsed["destination_account"] == "****1111" and parsed["card_last4"] == "4321"
    again = parse("info@baccredomatic.com", "Notificación Extrafinanciamiento, Oportunidad Aprobada", bac_disbursement(), "2026-05-27T23:10:00Z")
    assert again["dedupe_key"] == parsed["dedupe_key"]


def test_a_credit_offer_without_a_disbursement_is_not_a_movement():
    html = "<p>BAC Credomatic</p><p>Tiene un extrafinanciamiento preaprobado de CRC 1,000,000.00. Solicitelo hoy.</p>"
    assert parse("info@baccredomatic.com", "Oferta de extrafinanciamiento", html, "2026-05-01T12:00:00Z")["email_kind"] != "movement"


# --- Rejections cancel the other institution's notice -------------------------

def realtime_debit(reference):
    return ("<p>Hola Maria,</p><p>Notificación de transferencia</p><p>Te informamos que se aplicó un débito en tiempo real "
            "a tu cuenta.</p><p>Resumen de operación:</p><table>" + rows([
                ("Cuenta:", "CR74****1234"), ("Concepto:", "Débito aplicado por otra entidad financiera"),
                ("Monto:", "¢3,000.00"), ("Fecha:", "22/05/2026 19:19:40"), ("Referencia:", reference),
            ]) + "</table><p>Financiera MultiMoney S.A.</p>")


def rejection(reference):
    return bac_sinpe(f"Hola: MARIA PRUEBA : BAC le comunica que la transferencia SINPE en tiempo real con el número de referencia {reference}, "
                     "solicitada desde su cuenta IBAN CR0001XXXXXXXXXXXX1111 por un monto de 3,000.00 Colones, fue rechazada por la "
                     "entidad destino por el siguiente motivo: Problemas de comunicación. Día y hora: 22/05/2026 07:20:01 p.m.")


def test_rejected_transfer_keeps_its_reference_and_cancels_the_debit_notice():
    debit = parse("multimoneycr@multimoney.com", "Transacción realizada", realtime_debit(REF_A), "2026-05-23T01:19:45Z")
    rejected = parse("notificaciones@baccredomatic.cr", "Notificación de Transferencia", rejection(REF_A), "2026-05-23T01:20:04Z")
    assert debit["email_kind"] == "movement" and rejected["email_kind"] == "ignored"
    assert rejected["rejected_reference"] == REF_A
    assert p.cancelled_by_rejection(debit, {rejected["rejected_reference"]}) is True


def test_a_rejection_of_another_transfer_cancels_nothing():
    debit = parse("multimoneycr@multimoney.com", "Transacción realizada", realtime_debit(REF_A), "2026-05-23T01:19:45Z")
    other = parse("notificaciones@baccredomatic.cr", "Notificación de Transferencia", rejection(REF_B), "2026-05-23T01:20:04Z")
    assert p.cancelled_by_rejection(debit, {other["rejected_reference"]}) is False
    assert p.cancelled_by_rejection(debit, set()) is False


# --- Owner Gmail query keeps up with BAC sender moves ----------------------------

def test_persisted_query_gains_the_current_bac_senders_once():
    old = "(from:notificacion@notificacionesbaccr.com OR from:alerta@baccredomatic.com)"
    upgraded = service._with_current_bac_sources(old)
    for sender in service.CURRENT_BAC_SENDERS:
        assert f"from:{sender}" in upgraded.lower()
    assert service._with_current_bac_sources(upgraded) == upgraded


def test_a_whole_domain_sender_already_covers_its_addresses():
    query = "(from:baccredomatic.cr OR from:notificacionesbaccr.com)"
    assert service._with_current_bac_sources(query) == query
