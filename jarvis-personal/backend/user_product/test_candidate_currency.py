"""A USD bank movement is accepted with the user's exchange rate, never an invented one.

Parsers store a USD movement's real amount in original_amount/original_currency
and, next to it, an `amount` converted with a default rate (BAC notifications
and statements) or not converted at all while labelled CRC (MultiMoney). That
number is only used for cross-source matching; accepting the candidate records
its native amount, converted with the rate the user enters.
"""
import json
from decimal import Decimal

import pytest
from fastapi import HTTPException

from backend.email_monitor.parser import parse_financial_email
from backend.user_product import gmail_service
from backend.user_product.financial_candidate import canonical_candidate
from backend.user_product.candidate_currency import native_money, transaction_amounts
from backend.user_product.models import GmailCandidateReviewRequest
from backend.user_product.test_gmail_accept import FakeConnection, FakeDatabase, signed_in  # noqa: F401

BAC_USD = {"amount": 10395, "currency": "CRC", "original_amount": 21, "original_currency": "USD"}  # parser @495
MULTIMONEY_USD = {"amount": 50, "currency": "CRC", "original_amount": 50, "original_currency": "USD"}  # never converted


# --------------------------------------------------------------------------- native money

def test_a_usd_movement_is_worth_its_usd_amount_whatever_the_parser_converted():
    assert native_money(BAC_USD) == ("USD", Decimal("21.00"))
    assert native_money(MULTIMONEY_USD) == ("USD", Decimal("50.00"))
    assert native_money({"amount": 18500, "currency": "CRC"}) == ("CRC", Decimal("18500.00"))
    assert native_money({"amount": 18500}) == ("CRC", Decimal("18500.00"))


def test_a_bac_usd_notification_is_worth_its_usd_amount_in_gmail_and_outlook():
    body = (  # synthetic BAC card notification
        "Hola CLIENTE PRUEBA:\nA continuación le detallamos la transacción realizada:\n"
        "Comercio:\nHOSTING EJEMPLO\nCiudad y país:\nSAN FRANCISCO, USA\n"
        "Fecha:\nSep 22, 2026, 10:15\nVISA\n************1234\nAutorización:\n123456\n"
        "Referencia:\n000011112222\nTipo de Transacción:\nCOMPRA\nMonto:\nUSD 21.00"
    )
    parsed = parse_financial_email("Notificación de transacción", "BAC Credomatic <notificacion@notificacionesbaccr.com>",
                                   body, "2026-09-22T16:15:00Z")
    assert (parsed["original_amount"], parsed["original_currency"]) == (21.0, "USD")
    assert parsed["amount"] == 10395.0, "the parser still converts at its default 495: that number is not trusted"
    for provider in ("gmail", "microsoft"):
        candidate = canonical_candidate(parsed, provider_message_id="m-1", subject="Compra", source_provider=provider)
        assert native_money(candidate) == ("USD", Decimal("21.00")), provider


def test_conversion_needs_the_users_rate_and_never_guesses():
    assert transaction_amounts("CRC", 18500, "CRC", None)["original_currency"] is None
    assert transaction_amounts("USD", 21, "USD", None) == {
        "amount": Decimal("21.00"), "original_amount": None, "original_currency": None, "exchange_rate": None,
    }
    assert transaction_amounts("USD", 21, "CRC", 505) == {
        "amount": Decimal("10605.00"), "original_amount": Decimal("21.00"),
        "original_currency": "USD", "exchange_rate": Decimal("505"),
    }
    assert transaction_amounts("CRC", 50500, "USD", 505)["amount"] == Decimal("100.00")
    for currency, base in (("USD", "CRC"), ("CRC", "USD")):
        with pytest.raises(HTTPException) as error:
            transaction_amounts(currency, 21, base, None)
        assert error.value.status_code == 422
    with pytest.raises(HTTPException):
        transaction_amounts("CRC", 100, "EUR", 505)


def test_review_request_accepts_an_optional_positive_rate():
    base = {"transaction_date": "2026-09-20", "description": "x", "amount": 21, "transaction_type": "expense"}
    assert GmailCandidateReviewRequest(**base).exchange_rate is None
    assert GmailCandidateReviewRequest(**base, exchange_rate=505).exchange_rate == 505
    with pytest.raises(ValueError):
        GmailCandidateReviewRequest(**base, exchange_rate=0)


# --------------------------------------------------------------------------- accept flow

@pytest.fixture
def db(monkeypatch):
    database = FakeDatabase()
    database.queries = []

    def connect():
        conn = FakeConnection(database)
        execute = conn.execute

        def recording(query, params=()):
            database.queries.append((" ".join(query.split()), params))
            return execute(query, params)

        conn.execute = recording
        return conn

    monkeypatch.setattr(gmail_service, "get_connection", connect)
    return database


def _candidate(db, base="CRC", **fields):
    db.state["candidates"][81].update({"account_base_currency": base, **fields})


def _written(db, prefix):
    return [params for query, params in db.queries if query.startswith(prefix)]


def _corrections(amount, rate=None):
    return GmailCandidateReviewRequest(
        transaction_date="2026-09-20", description="Hosting", amount=amount,
        transaction_type="expense", category="Comida", exchange_rate=rate,
    ).model_dump()


def test_usd_candidate_on_a_crc_account_is_not_saved_without_a_rate(db, signed_in):  # noqa: F811
    _candidate(db, **BAC_USD)
    with pytest.raises(HTTPException) as error:
        gmail_service.review_gmail_candidate(81, "accept")
    assert error.value.status_code == 422 and "tipo de cambio" in error.value.detail
    assert db.state["transactions"] == [] and db.state["events"] == []
    assert db.state["candidates"][81]["status"] == "pending", "the candidate stays for the user"


def test_usd_candidate_is_saved_with_the_users_rate_not_the_parsers(db, signed_in):  # noqa: F811
    _candidate(db, **BAC_USD)
    result = gmail_service.review_gmail_candidate(81, "accept", _corrections(21, rate=505))
    assert result["status"] == "confirmed"
    (insert,) = _written(db, "INSERT INTO transactions")
    assert insert[2] == Decimal("10605.00"), "21 USD at the user's 505, not the parser's 10395"
    assert insert[-3:] == (Decimal("21.00"), "USD", Decimal("505"))
    (update,) = _written(db, "UPDATE finva_email_candidates SET transaction_id")
    assert update[3] == 10395, "the matching-only amount keeps its meaning"
    assert update[4] == 21, "the corrected original stays in USD"
    assert update[7] == ["description"], "the amount was not changed, only the description"
    (event,) = _written(db, "INSERT INTO financial_input_events")
    payload = json.loads(event[4])
    assert (payload["amount"], payload["currency"]) == (10605.0, "CRC")
    assert (payload["original_amount"], payload["original_currency"], payload["exchange_rate"]) == (21.0, "USD", 505.0)


def test_unconverted_usd_labelled_crc_is_converted_with_the_users_rate(db, signed_in):  # noqa: F811
    _candidate(db, **MULTIMONEY_USD)
    gmail_service.review_gmail_candidate(81, "accept", _corrections(50, rate=500))
    (insert,) = _written(db, "INSERT INTO transactions")
    assert insert[2] == Decimal("25000.00"), "$50 is not ₡50"


def test_usd_candidate_on_a_usd_account_needs_no_rate(db, signed_in):  # noqa: F811
    _candidate(db, base="USD", **BAC_USD)
    gmail_service.review_gmail_candidate(81, "accept")
    (insert,) = _written(db, "INSERT INTO transactions")
    assert insert[2] == Decimal("21.00") and insert[-3:] == (None, None, None)


def test_crc_candidate_on_a_usd_account_needs_a_rate(db, signed_in):  # noqa: F811
    _candidate(db, base="USD")
    with pytest.raises(HTTPException) as error:
        gmail_service.review_gmail_candidate(81, "accept")
    assert error.value.status_code == 422 and db.state["transactions"] == []
    gmail_service.review_gmail_candidate(81, "accept", {**_corrections(18500, rate=500)})
    (insert,) = _written(db, "INSERT INTO transactions")
    assert insert[2] == Decimal("37.00") and insert[-3:] == (Decimal("18500.00"), "CRC", Decimal("500"))


def test_crc_candidate_on_a_crc_account_is_unchanged(db, signed_in):  # noqa: F811
    gmail_service.review_gmail_candidate(81, "accept")
    (insert,) = _written(db, "INSERT INTO transactions")
    assert insert[2] == Decimal("18500.00") and insert[-3:] == (None, None, None)


def test_the_account_base_currency_comes_from_the_candidates_own_account(db, signed_in):  # noqa: F811
    gmail_service.review_gmail_candidate(81, "accept")
    select = next(query for query, _ in db.queries if query.startswith("SELECT c.*"))
    assert "JOIN accounts a ON a.id=c.account_id" in select
    assert "WHERE c.id=%s AND c.account_id=%s AND c.workspace_id=%s" in select
    assert select.endswith("FOR UPDATE OF c,m,g"), "the account row is read, never locked"


def test_inbox_shows_the_native_amount_and_the_account_base(monkeypatch):
    calls = []

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, query, params=()):
            calls.append((" ".join(query.split()), params))
            return type("R", (), {"fetchall": lambda _self: []})()

    monkeypatch.setattr(gmail_service, "get_connection", Connection)
    monkeypatch.setattr(gmail_service, "get_current_account_id", lambda: "account-a")
    monkeypatch.setattr(gmail_service, "get_current_workspace_id", lambda: "workspace-a")
    gmail_service.list_gmail_emails("pending")
    query, params = calls[0]
    assert "c.original_amount,c.original_currency" in query
    assert "a.base_currency AS account_base_currency" in query and "JOIN accounts a ON a.id=m.account_id" in query
    assert params == ("account-a", "workspace-a", "pending")


def test_saving_a_candidate_always_needs_the_converted_money():
    """No default: a caller cannot fall back to the reviewed (possibly matching-only) amount."""
    import inspect
    for helper in (gmail_service._create_candidate_transaction, gmail_service._publish_confirmed_financial_input):
        money = inspect.signature(helper).parameters["money"]
        assert money.default is inspect.Parameter.empty, helper.__name__
    source = inspect.getsource(gmail_service._create_candidate_transaction) + inspect.getsource(
        gmail_service._publish_confirmed_financial_input)
    assert "money or" not in source and 'values["amount"]' not in source
