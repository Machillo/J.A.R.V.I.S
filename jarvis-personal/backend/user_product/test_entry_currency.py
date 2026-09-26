"""Manual income and expenses in CRC or USD.

`amount` stays in the account's base currency, so totals keep adding one
currency. An entry in the other currency keeps what the user typed and the rate
the user entered; DINCR never invents a rate.
"""
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.auth.current_user import reset_current_user, set_current_user
from backend.user_product import free_service, service
from backend.user_product.entry_currency import resolve_entry_amount
from backend.user_product.models import ExpenseCreateRequest, IncomeCreateRequest, MovementUpdateRequest

ACCOUNT, WORKSPACE = "account-a", "workspace-a"
MIGRATION = (Path(__file__).resolve().parents[2] / "database" / "migrations"
             / "20260926150000_income_expense_original_currency.sql")


# --------------------------------------------------------------------------- conversion

def test_no_currency_or_the_base_currency_is_stored_as_typed():
    for currency in (None, "CRC"):
        assert resolve_entry_amount("CRC", 15000, currency, None) == {
            "amount": Decimal("15000.00"), "original_amount": None, "original_currency": None, "exchange_rate": None,
        }
    assert resolve_entry_amount("USD", 12.5, "USD", 999)["original_currency"] is None, "a rate is ignored in the base"


def test_usd_on_a_crc_account_uses_the_users_rate():
    assert resolve_entry_amount("CRC", 100, "USD", 505.25) == {
        "amount": Decimal("50525.00"), "original_amount": Decimal("100.00"),
        "original_currency": "USD", "exchange_rate": Decimal("505.25"),
    }


def test_crc_on_a_usd_account_divides_by_the_same_rate():
    values = resolve_entry_amount("USD", 50500, "CRC", 505)
    assert values["amount"] == Decimal("100.00")
    assert (values["original_amount"], values["original_currency"]) == (Decimal("50500.00"), "CRC")


def test_another_currency_without_a_rate_is_refused_not_guessed():
    for rate in (None, 0, -1):
        with pytest.raises(HTTPException) as error:
            resolve_entry_amount("CRC", 100, "USD", rate)
        assert error.value.status_code == 422


@pytest.mark.parametrize("base", ["EUR", "ARS"])
def test_legacy_base_currency_accepts_only_its_own_currency(base):
    assert resolve_entry_amount(base, 10, None, None)["amount"] == Decimal("10.00")
    with pytest.raises(HTTPException) as error:
        resolve_entry_amount(base, 10, "USD", 505)
    assert error.value.status_code == 422


def test_a_conversion_that_rounds_to_zero_is_refused():
    with pytest.raises(HTTPException):
        resolve_entry_amount("USD", 1, "CRC", 505)


def test_requests_accept_only_crc_and_usd_and_a_positive_rate():
    for model in (IncomeCreateRequest, ExpenseCreateRequest):
        assert model(amount=1, currency="USD", exchange_rate=505).currency == "USD"
        assert model(amount=1).currency is None
        with pytest.raises(ValidationError):
            model(amount=1, currency="EUR", exchange_rate=1)
        with pytest.raises(ValidationError):
            model(amount=1, currency="USD", exchange_rate=0)
    with pytest.raises(ValidationError):
        MovementUpdateRequest(transaction_date="2026-09-20", description="x", amount=1,
                              transaction_type="income", currency="MXN")


# --------------------------------------------------------------------------- services

class RecordingConnection:
    def __init__(self, base_currency="CRC", returning=None):
        self.base_currency, self.queries = base_currency, []
        self.returning = returning or {"id": 7, "source": "Pago", "created_at": "2026-09-20 12:00:00"}

    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def commit(self): pass

    def execute(self, query, params=()):
        sql = " ".join(query.split())
        self.queries.append((sql, params))
        row = {"base_currency": self.base_currency} if sql.startswith("SELECT base_currency FROM accounts") else self.returning
        return SimpleNamespace(fetchone=lambda: row, fetchall=lambda: [row])

    def write(self):
        return next((sql, params) for sql, params in self.queries if not sql.startswith("SELECT"))


@pytest.fixture
def as_user(monkeypatch):
    monkeypatch.setattr(service, "_legacy_financial_user_id", lambda: 55)
    monkeypatch.setattr(service, "mark_applied", lambda _conn: None)
    token = set_current_user({"id": 41, "account_id": ACCOUNT, "workspace_id": WORKSPACE, "role": "user"})
    yield
    reset_current_user(token)


def _use(monkeypatch, conn, *modules):
    for module in modules:
        monkeypatch.setattr(module, "get_connection", lambda: conn)
    return conn


@pytest.mark.parametrize("create", ["income", "expense"])
def test_usd_entry_stores_the_base_amount_and_what_the_user_typed(create, as_user, monkeypatch):
    conn = _use(monkeypatch, RecordingConnection("CRC"), service)
    if create == "income":
        service.create_income(IncomeCreateRequest(amount=100, description="Freelance", currency="USD", exchange_rate=505))
    else:
        service.create_expense_entry(ExpenseCreateRequest(amount=100, description="Hosting", currency="USD", exchange_rate=505))
    lookup = conn.queries[0]
    assert lookup == ("SELECT base_currency FROM accounts WHERE id=%s", (ACCOUNT,)), "the base comes from the caller's own account"
    sql, params = conn.write()
    assert "original_amount,original_currency,exchange_rate" in sql
    assert Decimal("50500.00") in params and Decimal("100.00") in params and "USD" in params and Decimal("505") in params
    assert WORKSPACE in params


@pytest.mark.parametrize("update", ["income", "expense"])
def test_edit_back_to_the_base_currency_clears_the_original(update, as_user, monkeypatch):
    conn = _use(monkeypatch, RecordingConnection("CRC"), service)
    payload = (IncomeCreateRequest if update == "income" else ExpenseCreateRequest)(amount=20000, currency="CRC")
    (service.update_income if update == "income" else service.update_expense)(7, payload)
    sql, params = conn.write()
    assert "original_amount=%s,original_currency=%s,exchange_rate=%s" in sql
    assert params[0] == Decimal("20000.00")
    originals = params[3:6] if update == "income" else params[4:7]
    assert originals == (None, None, None) and params[-2:] == (7, WORKSPACE)


def test_an_older_app_editing_without_a_currency_clears_the_original(as_user, monkeypatch):
    conn = _use(monkeypatch, RecordingConnection("CRC"), service)
    service.update_income(7, SimpleNamespace(amount=50500, description="Freelance", category="Otros", entry_date=None))
    assert not any(sql.startswith("SELECT base_currency") for sql, _ in conn.queries)
    _sql, params = conn.write()
    assert params[0] == Decimal("50500.00") and params[3:6] == (None, None, None), "the base value it showed is kept"


def test_older_app_versions_without_a_currency_keep_working_unchanged(as_user, monkeypatch):
    conn = _use(monkeypatch, RecordingConnection("CRC"), service)
    service.create_income(SimpleNamespace(amount=15000, description="Salario", category="Salario", entry_date=None))
    assert not any(sql.startswith("SELECT base_currency") for sql, _ in conn.queries), "no extra query without a currency"
    _sql, params = conn.write()
    assert params[2] == Decimal("15000.00") and params[5:8] == (None, None, None)


def test_list_income_and_expenses_return_the_original_currency(as_user, monkeypatch):
    conn = _use(monkeypatch, RecordingConnection(), service)
    service.list_income()
    service.list_expenses()
    for sql, params in conn.queries:
        assert "original_amount,original_currency,exchange_rate" in sql
        assert params == (WORKSPACE,)


def test_movement_edit_converts_manual_income_with_the_users_rate(as_user, monkeypatch):
    conn = _use(monkeypatch, RecordingConnection("CRC", {"id": 3}), free_service)
    free_service.update_free_movement("salary:3", MovementUpdateRequest(
        transaction_date="2026-09-20", description="Freelance", amount=10, transaction_type="income",
        category="Otros ingresos", currency="USD", exchange_rate=500))
    sql, params = conn.write()
    assert sql.startswith("UPDATE salaries SET amount=%s")
    assert params[0] == Decimal("5000.00") and params[3:6] == (Decimal("10.00"), "USD", Decimal("500"))
    assert params[-2:] == (3, WORKSPACE)


def test_bank_movements_cannot_be_given_another_currency(as_user, monkeypatch):
    _use(monkeypatch, RecordingConnection("CRC", {"id": 9}), free_service)
    with pytest.raises(HTTPException) as error:
        free_service.update_free_movement("transaction:9", MovementUpdateRequest(
            transaction_date="2026-09-20", description="x", amount=10, transaction_type="expense",
            currency="USD", exchange_rate=500))
    assert error.value.status_code == 422


@pytest.mark.parametrize("movement", ["transaction:9", "payroll:9"])
def test_bank_and_payroll_edits_without_a_currency_still_work(movement, as_user, monkeypatch):
    conn = _use(monkeypatch, RecordingConnection("CRC", {"id": 9}), free_service)
    free_service.update_free_movement(movement, MovementUpdateRequest(
        transaction_date="2026-09-20", description="x", amount=10, transaction_type="income" if "payroll" in movement else "expense"))
    assert not any(sql.startswith("SELECT base_currency") for sql, _ in conn.queries)
    assert conn.write()[1][-2:] == (9, WORKSPACE)


def test_huge_amounts_are_refused_not_a_500():
    with pytest.raises(HTTPException):
        resolve_entry_amount("CRC", 10_000_000_000, "USD", 505)
    with pytest.raises(HTTPException):
        resolve_entry_amount("CRC", 10**13, None, None)


def test_the_amount_uses_the_rate_exactly_as_stored():
    values = resolve_entry_amount("CRC", 1000, "USD", 505.1234567)
    assert values["exchange_rate"] == Decimal("505.123457")
    assert values["amount"] == Decimal("505123.46")


def test_history_lists_the_original_currency_for_every_source(as_user, monkeypatch):
    conn = _use(monkeypatch, RecordingConnection(), free_service)
    free_service.list_free_movements()
    sql, _params = conn.queries[0]
    assert sql.count("original_amount,original_currency,exchange_rate") == 3
    assert "NULL,NULL,NULL FROM payroll_events" in sql


# --------------------------------------------------------------------------- migration

def test_migration_is_additive_and_never_rewrites_rows():
    sql = MIGRATION.read_text(encoding="utf-8")
    body = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    assert body.strip().startswith("BEGIN;") and body.strip().endswith("COMMIT;")
    for table in ("salaries", "expenses"):
        assert f"ALTER TABLE public.{table}" in body
    assert body.count("ADD COLUMN IF NOT EXISTS") == 6
    assert "NOT VALID" in body and "VALIDATE CONSTRAINT" in body
    assert "original_currency IN (''CRC'', ''USD'')" in body
    for forbidden in ("UPDATE ", "DELETE ", "DROP ", "TRUNCATE", "DEFAULT"):
        assert forbidden not in body.upper().replace("DEFAULT PRIVILEGES", ""), forbidden


# --------------------------------------------------------------------------- final-audit edges

@pytest.mark.parametrize("args", [
    ("USD", 50500, "CRC", 0.0000004),   # a rate that rounds to 0 at 6 decimals: no division by zero
    ("CRC", 100, "USD", 0.0000004),
    ("CRC", float("inf"), None, None),  # JSON 1e999 reaches the model as inf (gt=0 accepts it)
    ("CRC", float("inf"), "USD", 505),
    ("CRC", 100, "USD", float("inf")),  # direct callers: the models already bound the rate
    ("CRC", 100, "USD", float("nan")),
])
def test_degenerate_amounts_and_rates_are_a_422_not_a_500(args):
    with pytest.raises(HTTPException) as error:
        resolve_entry_amount(*args)
    assert error.value.status_code == 422


def test_an_infinite_amount_from_json_is_refused_by_the_service(as_user, monkeypatch):
    import json
    conn = _use(monkeypatch, RecordingConnection("CRC"), service)
    payload = IncomeCreateRequest(**json.loads('{"amount": 1e999, "currency": "USD", "exchange_rate": 505}'))
    with pytest.raises(HTTPException) as error:
        service.create_income(payload)
    assert error.value.status_code == 422
    assert not any(not sql.startswith("SELECT") for sql, _ in conn.queries), "nothing is written"


@pytest.mark.parametrize(("base", "expected"), [("CRC", ["CRC", "USD"]), ("USD", ["CRC", "USD"]),
                                                ("EUR", ["EUR"]), (None, ["CRC", "USD"])])
def test_the_identity_declares_which_currencies_this_backend_converts(base, expected, monkeypatch):
    """A client offers another currency only when its backend declares it: an older
    backend ignores `currency`/`exchange_rate` and would store a USD figure as base."""
    import backend.auth.legal as legal
    from backend.auth import saas

    class AccountConnection(RecordingConnection):
        def execute(self, query, params=()):
            row = {"base_currency": base}
            return SimpleNamespace(fetchone=lambda: row, fetchall=lambda: [row])

    monkeypatch.setattr(saas, "get_connection", lambda: AccountConnection())
    monkeypatch.setattr(saas, "ensure_default_subscription", lambda *_a: {"plan": "free"})
    monkeypatch.setattr(saas, "_activate_self_service_if_ready", lambda *_a: None)
    monkeypatch.setattr(legal, "legal_status", lambda *_a: {})
    identity = saas.enrich_identity({"id": 41, "account_id": ACCOUNT, "role": "user"})
    assert identity["base_currency"] == (base or "CRC")
    assert identity["entry_currencies"] == expected
