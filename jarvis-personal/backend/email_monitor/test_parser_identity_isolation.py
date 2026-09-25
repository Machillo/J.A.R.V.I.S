"""The shared bank-email parser never borrows another account's identity.

Before this fix, DINCR Users' ingestion rewrote the user's own name into the
Owner's name so the Owner-trained parser would recognize it, and the parser read
the Owner's private accounts and contacts from module-level configuration for
every account. All people and accounts below are synthetic.
"""
import json
import re
from pathlib import Path

import pytest

from backend.email_monitor import parser
from backend.email_monitor.parser_identity import (
    NEUTRAL, ParserIdentity, current_identity, for_account_holder, owner_legacy_identity, use_identity,
)
from backend.user_product import gmail_service

BACKEND = Path(__file__).resolve().parents[1]
BAC = "BAC Credomatic <notificacion@notificacionesbaccr.com>"
USER_A = "Ana Sintetica Uno"
USER_B = "Luis Sintetico Dos"
OWNER = "Owner Sintetico"
CONTACT = "Rosa Contacto"
IBAN_1, IBAN_2 = "CR11000000000000000011", "CR22000000000000000022"


def sinpe_movil(payer: str, recipient: str) -> str:
    return (
        f"Le informamos que {payer} realizó una transferencia por medio de SINPE Móvil "
        f"a nombre de {recipient}. Referencia 123456789 Fecha 22/09/2026 Monto ₡10,000.00 Detalle traslado"
    )


def own_transfer() -> str:
    return (
        f"Le informamos que se realizó una transferencia SINPE debitando su cuenta {IBAN_1} "
        f"a la cuenta {IBAN_2} por concepto de traslado entre cuentas Monto ₡25,000.00 "
        "Día y hora 22/09/2026 10:00 Referencia 123456789"
    )


def parse(body: str, identity: ParserIdentity | None, subject: str = "Transferencia SINPE Móvil") -> dict:
    return parser.parse_financial_email(subject, BAC, body, "2026-09-22T16:00:00Z", identity=identity)


@pytest.fixture
def owner_config(monkeypatch):
    """The Owner's private configuration is present in the environment, as in production."""
    monkeypatch.setenv("OWNER_DISPLAY_NAME", OWNER)
    monkeypatch.setenv("JARVIS_RECEIVABLE_CONTACTS", json.dumps([CONTACT]))
    monkeypatch.setenv("JARVIS_OWN_ACCOUNT_IBANS", json.dumps({IBAN_1: "Owner 1", IBAN_2: "Owner 2"}))


@pytest.mark.parametrize("holder", [USER_A, USER_B])
def test_each_user_keeps_their_own_identity(holder):
    result = parse(sinpe_movil("Pedro Pagador", holder), for_account_holder(holder))

    assert result["recipient_name"] == holder
    assert result["payer_name"] == "Pedro Pagador"
    assert result["description"] == "SINPE recibido de Pedro Pagador"
    assert "Kenneth" not in json.dumps(result, ensure_ascii=False)


def test_one_users_identity_never_affects_another():
    email = sinpe_movil(USER_A, USER_B)  # A pays B

    as_a = parse(email, for_account_holder(USER_A))
    as_b = parse(email, for_account_holder(USER_B))

    assert as_a["description"] == "SINPE Móvil recibido"  # A's own name: their own movement
    assert as_b["description"] == f"SINPE recibido de {USER_A}"  # for B, A is just the payer
    assert as_b["recipient_name"] == USER_B


def test_first_names_match_whole_words_only():
    identity = for_account_holder("Ana Prueba")
    assert identity.is_holder(identity.person("Ana Prueba")) is True
    assert identity.person("Mariana Lopez") == "Mariana Lopez"
    assert identity.is_holder(identity.person("Mariana Lopez")) is False


def test_owner_contacts_only_apply_in_the_owner_only_context(owner_config):
    email = sinpe_movil(CONTACT, USER_A)

    for identity in (for_account_holder(USER_A), for_account_holder(USER_B), NEUTRAL, None):
        assert parse(email, identity)["category"] == "Reembolsos"
    assert parse(sinpe_movil(CONTACT, OWNER), owner_legacy_identity())["category"] == "Cuentas por cobrar"


def test_internal_transfers_depend_only_on_the_parsing_accounts_own_context(owner_config):
    """The Owner's configured IBANs are in the environment; they must not classify anyone else's mail."""
    own_accounts = ParserIdentity(holder_names=(USER_A,), own_account_ibans={IBAN_1: "A1", IBAN_2: "A2"})
    other_accounts = ParserIdentity(holder_names=(USER_B,), own_account_ibans={"CR33000000000000000033": "B1"})

    for identity in (for_account_holder(USER_A), for_account_holder(USER_B), other_accounts, None):
        assert parse(own_transfer(), identity, "Transferencia SINPE")["transaction_type"] != "internal_transfer"
    assert parse(own_transfer(), own_accounts, "Transferencia SINPE")["transaction_type"] == "internal_transfer"
    # The Owner-only manual scan still recognizes the Owner's own configured accounts.
    assert parse(own_transfer(), owner_legacy_identity(), "Transferencia SINPE")["transaction_type"] == "internal_transfer"


def test_the_identity_is_scoped_to_one_parse():
    parse(sinpe_movil("Pedro Pagador", USER_A), for_account_holder(USER_A))
    assert current_identity() is NEUTRAL
    assert parse(sinpe_movil(USER_A, USER_B), None)["description"] == f"SINPE recibido de {USER_A}"
    with use_identity(for_account_holder(USER_A)):
        # An explicit call without identity is neutral even inside another account's context.
        assert parse(sinpe_movil(USER_A, USER_B), None)["description"] == f"SINPE recibido de {USER_A}"


@pytest.mark.parametrize("display_name", [USER_A, USER_B, OWNER])
def test_mail_ingestion_parses_each_connection_as_its_own_holder(display_name, owner_config, monkeypatch):
    """Users and the Owner's standard mailbox flow: the text is not rewritten and no Owner configuration applies."""
    seen = {}

    def capture(subject, sender, body, received_at=None, exchange_rate=495.0, identity=None):
        seen.update(subject=subject, body=body, identity=identity)
        raise StopIteration

    monkeypatch.setattr(gmail_service, "parse_financial_email", capture)
    monkeypatch.setattr(gmail_service, "parse_popular_email_document", lambda **_kwargs: None)
    monkeypatch.setattr(gmail_service, "bank_sender_allowed", lambda _sender: True)
    body = sinpe_movil("Pedro Pagador", display_name)
    connection = {"id": 1, "account_id": "account", "workspace_id": "workspace", "display_name": display_name, "granted_scopes": []}

    with pytest.raises(StopIteration):
        # The pipeline itself (_ingest_message would record the interruption as a failed message).
        gmail_service._ingest_message_once(connection, "msg-1", subject="Transferencia SINPE Móvil", sender=BAC, body=body)

    assert seen["body"] == body  # parsed as received, never rewritten
    assert seen["identity"].holder_names[0] == display_name
    assert seen["identity"].own_account_ibans == {} and seen["identity"].receivable_contacts == ()


def test_shared_ingestion_code_contains_no_owner_identity():
    """No personal literal of the Owner is needed for the parsers DINCR Users run."""
    shared = [
        BACKEND / "email_monitor" / name for name in (
            "parser.py", "parser_identity.py", "popular_pdf.py", "normalization.py", "deduplication.py",
            "gmail_content.py", "payroll_statement.py", "statement_reconciliation.py",
        )
    ] + [path for path in (BACKEND / "user_product").glob("*.py") if not path.name.startswith("test_")]
    forbidden = re.compile(r"kenneth|alvarado|emily|sidey", re.I)
    for path in shared:
        assert not forbidden.search(path.read_text(encoding="utf-8")), path
    assert not hasattr(gmail_service, "_adapt_identity")
    assert not [name for name in vars(parser) if name.startswith("OWN_")]  # no module-level Owner accounts
