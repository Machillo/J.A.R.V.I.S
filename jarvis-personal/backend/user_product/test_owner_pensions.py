"""The Owner's pension balances from his statement. Invented figures and contract numbers."""
import json

import pytest

from backend.user_product import owner_pensions as op, retirement

TEXT = """
TIPO DE PRODUCTO PRODUCTO CONTRATO SALDO MONEDA
OPC - FONDO DE PENSIÓN RÉGIMEN OBLIGATORIO DE PENSIONES TE000111 1,234,567.89 CRC
OPC - FONDO DE PENSIÓN FONDO DE CAPITALIZACIÓN LABORAL (FCL) TE000222 98,765.43 CRC
Total 1,333,333.32 CRC
RÉGIMEN OBLIGATORIO DE PENSIONES COMPLEMENTARIAS (ROP) Y FONDO DE CAPITALIZACIÓN LABORAL (FCL)
FCL COLONESRESUMEN DEL PERIODO ROP COLONES
¢ 11,111.11Saldo Anterior ¢ 22,222.22
"""
NAMES = ["EstadoCta_999_202609__0000.pdf"]
SUBJECT, SENDER = "Estado de cuenta BAC Pensiones", "estadosdecuenta@baccredomatic.cr"


def parsed(**overrides):
    args = {"subject": SUBJECT, "sender": SENDER, "text": TEXT, "attachment_names": NAMES, "received_at": "2026-10-10T07:56:58+00:00", **overrides}
    return op.parse_statement(**args)


def test_it_reads_each_fund_and_the_month_of_the_statement_not_the_total_or_the_previous_balance():
    assert parsed() == {"rop_balance": 1234567.89, "fcl_balance": 98765.43, "month": "2026-09"}


def test_the_sender_may_come_with_a_display_name():
    assert parsed(sender="BAC <estadosdecuenta@baccredomatic.cr>")["month"] == "2026-09"


@pytest.mark.parametrize("sender", ["estadosdecuenta@baccredomatic.cr.evil.com", "x@evil.com", "estadosdecuenta@baccredomatic.cr <x@evil.com>", ""])
def test_another_sender_is_never_read(sender):
    assert parsed(sender=sender) is None


def test_another_statement_from_the_bank_is_never_read():
    assert parsed(subject="Estado de cuenta Tarjeta") is None


def test_a_document_without_the_funds_is_nothing():
    assert parsed(text="Total 1,000.00 CRC") is None


def test_a_missing_fund_stays_unknown():
    only = parsed(text="OPC - FONDO DE PENSIÓN RÉGIMEN OBLIGATORIO DE PENSIONES TE1 1,000.00 CRC")
    assert only["rop_balance"] == 1000 and only["fcl_balance"] is None


def test_without_a_named_month_it_uses_the_date_received_and_without_any_it_is_nothing():
    assert parsed(attachment_names=["x.pdf"])["month"] == "2026-10"
    assert parsed(attachment_names=[], received_at=None) is None


class Conn:
    def __init__(self, stored=None):
        self.stored, self.writes = stored, 0

    def execute(self, sql, params):
        if sql.startswith("SELECT"):
            value = self.stored
            return type("R", (), {"fetchone": lambda _self: {"preference_value": value} if value is not None else None})()
        self.stored = json.loads(params[2])
        self.writes += 1
        return None


def test_a_statement_fills_retiro_and_keeps_what_the_owner_declared():
    conn = Conn({"birth_year": 1990, "retire_age": 65, "rop_balance": None, "voluntary_balance": 500})
    assert op.apply_statement(conn, "ws", parsed()) is True
    assert conn.stored["rop_balance"] == 1234567.89 and conn.stored["fcl_balance"] == 98765.43
    assert conn.stored["birth_year"] == 1990 and conn.stored["voluntary_balance"] == 500 and conn.stored["pensions_as_of"] == "2026-09"


def test_without_any_preference_it_starts_one():
    conn = Conn()
    assert op.apply_statement(conn, "ws", parsed()) is True and conn.stored["pensions_as_of"] == "2026-09"


@pytest.mark.parametrize("stored_month", ["2026-09", "2026-10"])
def test_the_same_or_an_older_statement_changes_nothing(stored_month):
    conn = Conn({"rop_balance": 5, "pensions_as_of": stored_month})
    assert op.apply_statement(conn, "ws", parsed()) is False
    assert conn.writes == 0 and conn.stored["rop_balance"] == 5


def test_a_missing_fund_keeps_its_value():
    conn = Conn({"fcl_balance": 7, "pensions_as_of": "2026-08"})
    op.apply_statement(conn, "ws", {"rop_balance": 9.0, "fcl_balance": None, "month": "2026-09"})
    assert conn.stored["fcl_balance"] == 7 and conn.stored["rop_balance"] == 9


def test_retiro_shows_them_and_saving_never_loses_them(monkeypatch):
    saved = {}
    stored = {"rop_balance": 1, "fcl_balance": 2, "pensions_as_of": "2026-09"}
    monkeypatch.setattr(retirement, "get_preference", lambda *_a: stored)
    monkeypatch.setattr(retirement, "set_preference", lambda _key, value: saved.update(value))
    config = retirement.get_retirement()["config"]
    assert config["fcl_balance"] == 2 and config["pensions_as_of"] == "2026-09"
    retirement.update_retirement({"retire_age": 60})
    assert saved["fcl_balance"] == 2 and saved["pensions_as_of"] == "2026-09" and saved["retire_age"] == 60
