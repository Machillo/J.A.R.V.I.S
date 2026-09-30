"""One SINPE transfer, two banks: the same 25-digit reference links the two notices.

Synthetic data. A transfer between the holder's own accounts is correlated only
with strong evidence (same SINPE reference, same native amount and currency,
opposite directions); the same amount alone never correlates.
"""
from __future__ import annotations

from datetime import date

from backend.email_monitor import parser as p
from backend.email_monitor.gmail_content import plain_text_from_html
from backend.email_monitor.parser_identity import for_account_holder
from backend.user_product import own_transfer_review as transfers
from backend.user_product.candidate_resolution import _paired_owned_transfer, different_sinpe_references
from backend.user_product.financial_candidate import canonical_candidate

REF = "2026092810224000000000123"
OTHER_REF = "2026092810224000000000999"
IDENTITY = for_account_holder("Maria Prueba")


def _bac_credit(reference=REF, amount="20,000.00"):
    html = (f"<p>Hola MARIA PRUEBA SOLANO : BAC le comunica que la transferencia SINPE en tiempo real con el número de "
            f"referencia {reference}, se acreditó en la cuenta IBAN CR0001XXXXXXXXXXXX1111 por un monto de {amount} "
            "Colones, por concepto de ahorro____.Día y hora 28/09/2026 12:24:31 p.m.</p>")
    return p.parse_financial_email("Notificación de Transferencia", "notificaciones@baccredomatic.cr",
                                   plain_text_from_html(html), "2026-09-28T18:25:03Z", identity=IDENTITY)


def _mm_realtime_debit(reference=REF, amount="¢20,000.00"):
    html = ("<p>Notificación de transferencia</p><p>Te informamos que se aplicó un débito en tiempo real a tu cuenta.</p>"
            "<p>Resumen de operación:</p><table><tr><td>Cuenta:</td><td>CR74****1234</td></tr>"
            "<tr><td>Concepto:</td><td>Débito aplicado por otra entidad financiera</td></tr>"
            f"<tr><td>Monto:</td><td>{amount}</td></tr><tr><td>Fecha:</td><td>28/09/2026 12:24:28</td></tr>"
            f"<tr><td>Referencia:</td><td>{reference}</td></tr></table><p>MultiMoney</p>")
    return p.parse_financial_email("Transacción realizada", "multimoneycr@multimoney.com",
                                   plain_text_from_html(html), "2026-09-28T18:24:36Z", identity=IDENTITY)


def _candidate(parsed, candidate_id):
    row = canonical_candidate(parsed, provider_message_id=f"m{candidate_id}", subject="aviso")
    return {**row, "id": candidate_id, "email_message_id": candidate_id + 100, "account_id": "account-a",
            "workspace_id": "workspace-a", "status": "pending", "transaction_id": None,
            "is_internal_transfer": False}


def test_both_banks_notices_of_one_sinpe_transfer_carry_the_same_reference():
    bac, mm = _candidate(_bac_credit(), 1), _candidate(_mm_realtime_debit(), 2)
    assert bac["external_reference"] == mm["external_reference"] == REF
    assert (bac["movement_direction"], mm["movement_direction"]) == ("in", "out")
    assert bac["movement_kind"] == mm["movement_kind"] == "transfer"
    # Neither side is counted as income or spending by default.
    assert bac["transaction_type"] == mm["transaction_type"] == "transfer"
    assert transfers._eligible(bac, mm)
    assert transfers._shared_reference(bac, mm)


def test_same_amount_with_different_sinpe_references_is_never_correlated():
    bac, mm = _candidate(_bac_credit(), 1), _candidate(_mm_realtime_debit(reference=OTHER_REF), 2)
    assert different_sinpe_references(bac["external_reference"], mm["external_reference"])
    assert not transfers._eligible(bac, mm)


def test_usd_and_crc_with_the_same_number_are_never_correlated():
    usd = {**_candidate(_mm_realtime_debit(amount="$20,000.00"), 2)}
    assert usd["original_currency"] == "USD"
    assert not transfers._eligible(_candidate(_bac_credit(), 1), usd)


def test_reference_pairs_are_suggested_first_and_nothing_is_saved(monkeypatch):
    unrelated_out = {**_candidate(_mm_realtime_debit(reference=None), 3), "external_reference": "bank-x-1"}
    unrelated_in = {**_candidate(_bac_credit(reference=None), 4), "external_reference": "bank-y-2"}
    rows = [unrelated_out, unrelated_in, _candidate(_bac_credit(), 1), _candidate(_mm_realtime_debit(), 2)]

    class _Result:
        def fetchall(self):
            return rows

    class _Connection:
        calls = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query, params=()):
            self.calls.append(query)
            return _Result()

    conn = _Connection()
    monkeypatch.setattr(transfers, "get_current_account_id", lambda: "account-a")
    monkeypatch.setattr(transfers, "get_current_workspace_id", lambda: "workspace-a")
    monkeypatch.setattr(transfers, "get_connection", lambda: conn)
    items = transfers.list_own_transfer_suggestions()["items"]
    assert items[0]["shared_reference"] is True
    assert {items[0]["first"]["candidate_id"], items[0]["second"]["candidate_id"]} == {1, 2}
    assert not any("UPDATE" in q or "INSERT" in q or "DELETE" in q for q in conn.calls)


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _PairConnection:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def execute(self, query, params=()):
        self.calls.append((query, params))
        return _Rows(self.rows)


def _counterpart(**changes):
    row = {"id": 10, "transaction_date": date(2026, 9, 28), "transaction_time": "12:24:28", "account_last4": "1234",
           "source_account_reference": "****1234", "destination_account_reference": None,
           "external_reference": REF, "amount": 20000.0, "currency": "CRC",
           "original_amount": None, "original_currency": None}
    row.update(changes)
    return row


def test_confirmed_accounts_and_the_same_reference_pair_even_when_the_clocks_disagree():
    bac = _candidate(_bac_credit(), 9)
    # MultiMoney printed UTC for months: the times can be hours apart; the reference decides.
    assert _paired_owned_transfer(_PairConnection([_counterpart(transaction_time="18:24:28")]), bac, 11) == 10


def test_confirmed_accounts_and_close_times_never_pair_different_sinpe_references():
    bac = _candidate(_bac_credit(), 9)
    assert _paired_owned_transfer(_PairConnection([_counterpart(external_reference=OTHER_REF)]), bac, 11) is None


def test_confirmed_accounts_never_pair_a_usd_notice_with_a_crc_one():
    bac = _candidate(_bac_credit(), 9)
    usd = _counterpart(original_amount=20000.0, original_currency="USD", external_reference=None)
    assert _paired_owned_transfer(_PairConnection([usd]), bac, 11) is None


def test_without_confirmed_own_accounts_nothing_is_paired():
    bac = _candidate(_bac_credit(), 9)
    assert _paired_owned_transfer(_PairConnection([_counterpart()]), bac, None) is None
