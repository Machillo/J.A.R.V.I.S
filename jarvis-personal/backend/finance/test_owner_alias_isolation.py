"""Owner aliases never reach Users; the Owner keeps his historical resolution (master plan P0.1).

The neutral catalog (`category_catalog.OFFICIAL_CATEGORIES`) is what every account resolves
against. The Owner's personal aliases live in `owner_category_compat` and apply only when the
server decides the data is the Owner's: `owner_context()` (verified session role) in Owner-only
modules, `owner_account_context()` (stored Owner identity of the account and workspace) in the
shared mail pipeline, including background sync. Synthetic values only.
"""
import ast
import json
import re
from contextlib import contextmanager
from pathlib import Path

import pytest

from backend.auth.current_user import reset_current_user, set_current_user
from backend.email_monitor import parser as mail_parser
from backend.email_monitor.popular_pdf import parse_popular_loan_payment
from backend.finance.category_catalog import (
    OFFICIAL_CATEGORIES,
    expense_type_for_category,
    normalize_category,
    owner_context,
)
from backend.finance.owner_category_compat import OWNER_EXTRA_ALIASES, OWNER_ONLY_CATEGORIES, owner_transfer_category
from backend.user_product.financial_candidate import canonical_candidate

BACKEND = Path(__file__).resolve().parents[1]
BASELINE = json.loads((BACKEND / "tests" / "fixtures" / "category_catalog_pre_p0_1.json").read_text(encoding="utf-8"))
TYPES = (None, "expense", "transfer", "debt_payment")
PERSONAL_FAMILY = ("papa", "papá", "mama", "mamá")
PLANS = ("free", "basic", "vip")
OWNER = {"id": 1, "account_id": "00000000-0000-0000-0000-0000000000aa", "workspace_id": "00000000-0000-0000-0000-0000000000ab",
         "role": "owner", "plan": "vip", "access_source": "owner"}


def _user(plan: str, **extra):
    return {"id": 900, "account_id": "00000000-0000-0000-0000-000000000900", "workspace_id": "00000000-0000-0000-0000-000000000901",
            "role": "user", "plan": plan, "workspace_role": "owner", **extra}


@contextmanager
def _as(user):
    token = set_current_user(user)
    try:
        yield
    finally:
        reset_current_user(token)


def _resolve(value, transaction_type=None):
    """Exactly how callers resolve: the Owner layer only through the server's role."""
    return normalize_category(value, transaction_type, owner=owner_context())


# 1–3. Free, Basic and VIP never resolve the Owner's family words.
@pytest.mark.parametrize("plan", PLANS)
def test_a_regular_plan_cannot_resolve_the_owners_family_aliases(plan):
    with _as(_user(plan)):
        assert owner_context() is False
        for word in PERSONAL_FAMILY:
            for transaction_type in TYPES:
                assert _resolve(word, transaction_type) != "Familiar", (plan, word, transaction_type)
                assert _resolve(f"envío a {word}", transaction_type) != "Familiar", (plan, word, transaction_type)


@pytest.mark.parametrize("claim", [
    {"plan": "owner"},
    {"access_source": "owner"},
    {"is_owner": True},
    {"owner": True},
    {"workspace_role": "owner"},      # every account owns its personal workspace: never the Owner role
])
def test_owner_compatibility_cannot_be_activated_from_a_users_own_fields(claim):
    with _as({**_user("vip"), **claim}):
        assert owner_context() is False
        assert _resolve("papá", "expense") == "Sin categoría"
        assert _resolve("acciones", "transfer") == "Otros"


@pytest.mark.parametrize("flag", ["true", "1", 1, "owner", {"role": "owner"}])
def test_only_the_boolean_true_selects_the_owner_layer(flag):
    # A value copied from a request body or query string can never switch catalogs.
    assert normalize_category("papá", "expense", owner=flag) == "Sin categoría"
    assert expense_type_for_category("papá", owner=flag) == "variable"


def test_without_an_authenticated_request_the_context_is_neutral():
    # Background jobs, crons, OAuth callbacks and Gmail push have no request user.
    assert owner_context() is False
    assert _resolve("papá", "expense") == "Sin categoría"


IMPORTS_OWNER_LAYER = re.compile(r"^\s*(from|import)\s+\S*owner_category_compat", re.M)


OWNER_AWARE = {"normalize_category", "expense_type_for_category", "transfer_category", "canonical_candidate",
               "statement_candidate", "parse_statement_movements", "parse_bac_statement", "parse_multimoney_statement",
               "detect_category", "_create_candidate_transaction", "_publish_confirmed_financial_input"}


def _call_name(node):
    return getattr(node.func, "id", getattr(node.func, "attr", ""))


def test_shared_users_code_selects_the_owner_layer_only_from_the_stored_owner_identity():
    # The shared Users pipeline (mail candidates, statements, reviews) may carry an `owner` flag,
    # but only one computed by owner_account_context() from the stored account/workspace of the
    # data; never a literal, a request value, the session role or the Owner module itself.
    for path in sorted((BACKEND / "user_product").glob("*.py")):
        if path.name.startswith("test_"):
            continue
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        assert not IMPORTS_OWNER_LAYER.search(source), path.name
        assert not [n for n in ast.walk(tree) if isinstance(n, ast.Call) and _call_name(n) == "owner_context"], path.name
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "owner" for t in node.targets):
                assert isinstance(node.value, ast.Call) and _call_name(node.value) == "owner_account_context", (path.name, node.lineno)
            if isinstance(node, ast.Call):
                for keyword in node.keywords:
                    if _call_name(node) in OWNER_AWARE:  # no **kwargs smuggling an owner flag
                        assert keyword.arg is not None, (path.name, node.lineno)
                    if keyword.arg == "owner":
                        assert isinstance(keyword.value, ast.Name) and keyword.value.id == "owner", (path.name, node.lineno)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                arguments = node.args
                for arg, default in zip(arguments.kwonlyargs, arguments.kw_defaults):
                    if arg.arg == "owner":
                        assert isinstance(default, ast.Constant) and default.value is False, (path.name, node.name)
                positional = arguments.args[len(arguments.args) - len(arguments.defaults):]
                for arg, default in zip(positional, arguments.defaults):
                    if arg.arg == "owner":
                        assert isinstance(default, ast.Constant) and default.value is False, (path.name, node.name)
    for name in ("parser.py", "statement_reconciliation.py", "popular_pdf.py"):
        source = (BACKEND / "email_monitor" / name).read_text(encoding="utf-8")
        assert not IMPORTS_OWNER_LAYER.search(source) and "owner_context" not in source, name


# 4. The Owner keeps every historical resolution.
def test_the_owner_keeps_his_historical_aliases():
    with _as(OWNER):
        assert owner_context() is True
        for word in (*PERSONAL_FAMILY, "familia", "regalo para mamá"):
            assert _resolve(word, "expense") == "Familiar"
        assert _resolve("ecuador", "transfer") == "Viajes"
        assert _resolve("ahorro japón", "transfer") == "Viajes"
        assert _resolve("bac", "debt_payment") == "Tarjeta BAC"
        assert _resolve("popular", "expense") == "Banco Popular"
        assert expense_type_for_category("papá", owner=True) == "fixed"


def test_the_owner_layer_reproduces_the_pre_p0_1_catalog_exactly():
    for key, before in BASELINE["normalize"].items():
        phrase, transaction_type = key.split("||")
        transaction_type = None if transaction_type == "None" else transaction_type
        assert normalize_category(phrase, transaction_type, owner=True) == before, key
    for category, before in BASELINE["expense_type"].items():
        assert expense_type_for_category(category, owner=True) == before, category


def test_the_owners_family_transfer_rule_lives_only_in_his_layer():
    assert owner_transfer_category("envio a papa") == "Familiar"
    assert owner_transfer_category("pago alquiler") is None


# 5–6. Investments: generic stock words are generic; a named broker is a shared institution.
@pytest.mark.parametrize("plan", PLANS)
def test_a_users_stock_words_resolve_to_the_generic_investment_category(plan):
    with _as(_user(plan)):
        for word in ("acciones", "bolsa", "bolsa de valores"):
            assert _resolve(word, "transfer") == "Otros", word
            assert _resolve(word) != "IBKR", word


@pytest.mark.parametrize("plan", PLANS)
def test_an_explicitly_named_broker_is_a_shared_institution(plan):
    # Like BAC, MultiMoney or Banco Popular: evidence that names the institution resolves it.
    with _as(_user(plan)):
        for word in ("ibkr", "IBKR", "interactive brokers", "transferencia a Interactive Brokers"):
            assert _resolve(word, "transfer") == "IBKR", word
    assert "IBKR" in {item["category_name"] for item in OFFICIAL_CATEGORIES}
    assert OWNER_ONLY_CATEGORIES == []


def test_the_owner_still_resolves_ibkr():
    with _as(OWNER):
        for word in ("acciones", "bolsa", "ibkr", "IBKR", "interactive brokers"):
            assert _resolve(word, "transfer") == "IBKR", word


# 7–8. BAC: structured evidence still resolves the card; the bare word does not.
def test_structured_bac_evidence_still_resolves_tarjeta_bac():
    parsed = mail_parser._parse_bac_card_payment(
        "Comprobante de Pago de Tarjeta",
        "Tarjeta de Crédito Número: 4111-XXXX-XXXX-1234\nCuenta Origen Número: XXXXXX5678\n"
        "Monto del pago: 25.000,00 CRC\nReferencia: 4321\nFecha de pago: 2026/09/22 10:15:00",
        "2026-09-22T16:15:00Z",
    )
    assert parsed and parsed["category"] == "Tarjeta BAC"
    candidate = canonical_candidate(parsed, provider_message_id="synthetic-1", subject="Comprobante de Pago de Tarjeta")
    assert candidate["category"] == "Tarjeta BAC"
    for text in ("Tarjeta BAC", "pago tarjeta bac", "visa bac", "mastercard bac"):
        assert normalize_category(text, "debt_payment") == "Tarjeta BAC", text


@pytest.mark.parametrize("text, transaction_type", [
    ("bac", "expense"), ("bac", "debt_payment"), ("bac", "transfer"), ("cajero bac zapote", "expense"),
])
def test_the_bare_word_bac_does_not_classify_neutral_text(text, transaction_type):
    assert normalize_category(text, transaction_type) != "Tarjeta BAC"


# 9–10. Banco Popular: same rule.
def test_structured_banco_popular_evidence_still_works():
    parsed = parse_popular_loan_payment(
        "COMPROBANTEDEPAGODE PRESTAMOS\nNúmero de Operación 1040900012345\nFecha Aplicación 07/09/2026 08:15:20\n"
        "Patrono 123456 - EMPRESA PRUEBA SA\nNúmero Comprobante 20260907007302\nFecha Planilla AGOSTO 2026\n"
        "Monto delPago ₡ 12 345,67\nSaldo Anterior ₡ 1,500,000.00\nAmortización Saldo ₡ 45 000,00\n"
        "Intereses Corrientes ₡ 15 000,00\nIntereses de Mora ₡ 0,00\nCargos por Pólizas ₡ 5 480,40\n"
        "Fracciones o Excesos ₡ 0,00\nOtros Cargos ₡ 0,00\nNuevo Saldo ₡ 1 455 000,00\nTasa Anual 12,00 %\n"
        "Medio de Pago 04-PLANILLAS",
        "2026-09-07T14:15:20Z",
    )
    assert parsed and parsed["category"] == "Banco Popular"
    assert normalize_category(parsed["category"], parsed["transaction_type"]) == "Banco Popular"
    for text in ("Banco Popular", "préstamo popular", "prestamo popular"):
        assert normalize_category(text, "expense") == "Banco Popular", text


@pytest.mark.parametrize("text, expected", [
    ("popular", "Sin categoría"),
    ("pizza popular", "Restaurante"),
    ("cine popular", "Entretenimiento"),
])
def test_the_bare_word_popular_does_not_classify_neutral_text(text, expected):
    assert normalize_category(text, "expense") == expected


# 11. The generic family-loan concept stays.
@pytest.mark.parametrize("text", ["familiar", "Familiar", "préstamo familiar", "prestamo familiar", "abono préstamo familiar"])
def test_the_generic_family_loan_category_still_works(text):
    assert normalize_category(text, "expense") == "Familiar"
    assert normalize_category(text, "debt_payment") == "Familiar"
    assert expense_type_for_category(text) == "fixed"


def test_familia_alone_is_not_a_family_loan():
    assert normalize_category("familia", "expense") == "Sin categoría"


# 12. The Owner's trips are not aliases for anyone else.
@pytest.mark.parametrize("plan", PLANS)
def test_personal_travel_destinations_do_not_leak_into_users(plan):
    with _as(_user(plan)):
        for place in ("ecuador", "japon", "japón", "mexico", "méxico"):
            assert _resolve(place, "transfer") != "Viajes", place
            assert _resolve(f"ahorro {place}", "transfer") != "Viajes", place
        assert _resolve("viajes", "transfer") == "Viajes"           # the generic savings goal stays
        assert _resolve("viaje", "expense") == "Viajes y turismo"    # and so does travel spending


# 13. A regular account's Email Monitor never consumes Owner aliases.
@pytest.mark.parametrize("context", [None, *PLANS])
def test_a_regular_email_monitor_candidate_cannot_consume_owner_aliases(context):
    def run():
        parsed = mail_parser._parse_multimoney_transfer(
            "Notificación de transferencia", "avisos@multimoney.com",
            "MultiMoney\nSe aplico un credito en tiempo real\nMonto: CRC 10.000\nFecha: 22/09/2026\n"
            "Referencia: 987654321\nConcepto: envio papa",
            "2026-09-22T10:00:00Z",
        )
        assert parsed["transaction_type"] == "transfer"
        assert parsed["category"] == "Transferencias"
        candidate = canonical_candidate(parsed, provider_message_id="synthetic-2", subject="Notificación de transferencia")
        assert candidate["category"] != "Familiar"
        assert mail_parser.infer_category("transferencia a mamá", "transfer") == "Transferencias"
        assert canonical_candidate({"category": "acciones", "transaction_type": "transfer"},
                                   provider_message_id="synthetic-3", subject="s")["category"] == "Otros"

    if context is None:      # background sync: no request user
        run()
    else:
        with _as(_user(context)):
            run()


# 14. Generic merchant mappings are unchanged; the neutral layer changed only the isolated aliases.
ISOLATED = {alias for aliases in OWNER_EXTRA_ALIASES.values() for alias in aliases} | {
    alias for item in OWNER_ONLY_CATEGORIES for alias in [item["category_name"].lower(), *item["aliases"]]}
ISOLATED_CATEGORIES = {*OWNER_EXTRA_ALIASES, *(item["category_name"] for item in OWNER_ONLY_CATEGORIES)}


def test_neutral_changes_are_limited_to_the_isolated_aliases():
    changed = []
    for key, before in BASELINE["normalize"].items():
        phrase, transaction_type = key.split("||")
        transaction_type = None if transaction_type == "None" else transaction_type
        after = normalize_category(phrase, transaction_type)
        if after != before:
            words = {alias for alias in ISOLATED if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", phrase.lower())}
            assert words and before in ISOLATED_CATEGORIES, (key, before, after)
            changed.append(key)
    assert changed, "the baseline must exercise the isolated aliases"
    for category, before in BASELINE["expense_type"].items():
        assert expense_type_for_category(category) == before, category


@pytest.mark.parametrize("text, transaction_type, expected", [
    ("pedido uber eats", "expense", "Restaurante"),
    ("maxi pali", "expense", "Comida"),
    ("walmart", "expense", "Comida"),
    ("recibo aya", "expense", "Servicios"),
    ("cnfl", "expense", "Servicios"),
    ("kolbi", "expense", "Internet"),
    ("liberty", "expense", "Internet"),
    ("netflix", "expense", "Suscripciones"),
    ("muay thai", "expense", "Deporte"),
    ("hamster", "expense", "Mascotas"),
    ("multimoney", "debt_payment", "MultiMoney"),
    ("bitcoin", "transfer", "Cripto"),
    ("pago", "income", "Salario"),   # documented as potentially over-broad; untouched by P0.1
])
def test_generic_merchant_mappings_are_unchanged(text, transaction_type, expected):
    assert normalize_category(text, transaction_type) == expected
    assert normalize_category(text, transaction_type, owner=True) == expected


class _Captured(Exception):
    def __init__(self, parsed):
        self.parsed = parsed


class _Conn:
    def __enter__(self): return self
    def __exit__(self, *_a): return False
    def commit(self): pass
    def execute(self, query, params=()): raise AssertionError(f"unexpected SQL in this test: {query[:60]}")


def _owner_scan_category(monkeypatch, user, description, scanned_user_id=None):
    """Run the Owner's manual mail scan up to category normalization, with a synthetic transfer."""
    from backend.email_monitor import service

    parsed = {"email_kind": "movement", "transaction_type": "transfer", "category": "Transferencias", "description": description,
              "amount": 10_000.0, "transaction_date": "2026-09-22", "transaction_time": "10:00", "bank": "multimoney"}
    monkeypatch.setattr(service, "get_connection", lambda: _Conn())
    monkeypatch.setattr(service, "_workspace_id_for_user", lambda conn, user_id: user["workspace_id"])
    monkeypatch.setattr(service, "parse_popular_email_document", lambda **kw: None)
    monkeypatch.setattr(service, "parse_financial_email", lambda *a, **k: dict(parsed))
    monkeypatch.setattr(service.receivable_semantics, "lock_workspace_receivables", lambda conn, ws: None)
    monkeypatch.setattr(service, "apply_workspace_email_rules", lambda conn, ws, item: item)
    monkeypatch.setattr(service, "_upsert_ingested_message", lambda conn, **kw: 1)
    monkeypatch.setattr(service, "_enrich_candidate_with_card_alias", lambda conn, ws, item: item)
    monkeypatch.setattr(service, "_internal_mirror_exists", lambda conn, ws, item: (_ for _ in ()).throw(_Captured(item)))
    with _as(user), pytest.raises(_Captured) as captured:
        service.scan_email_text(subject="Notificación de transferencia", sender="avisos@multimoney.com", body="synthetic",
                                user_id=int(scanned_user_id or user["id"]), provider_message_id="synthetic-4")
    return captured.value.parsed["category"]


def test_the_owner_scan_keeps_his_family_transfer_rule(monkeypatch):
    assert _owner_scan_category(monkeypatch, OWNER, "envio papa") == "Familiar"
    assert _owner_scan_category(monkeypatch, OWNER, "pago alquiler") != "Familiar"


@pytest.mark.parametrize("plan", PLANS)
def test_the_scan_path_without_the_owner_role_never_applies_the_family_rule(monkeypatch, plan):
    # Even if a regular account's request reached this code, the rule follows the server's role.
    assert _owner_scan_category(monkeypatch, _user(plan), "envio papa") != "Familiar"



def test_an_owner_request_scanning_another_accounts_mail_stays_neutral(monkeypatch):
    # The layer follows whose data is processed, not only who asks.
    assert _owner_scan_category(monkeypatch, OWNER, "envio papa", scanned_user_id=2) != "Familiar"


# Owner connected Gmail: ONE shared pipeline; the Owner layer follows the connection's stored identity.
OWNER_CONNECTION = {"id": 41, "account_id": OWNER["account_id"], "workspace_id": OWNER["workspace_id"],
                    "legacy_user_id": 1, "display_name": "Owner Prueba", "provider": "gmail"}


def _user_connection(plan):
    user = _user(plan)
    return {"id": 42, "account_id": user["account_id"], "workspace_id": user["workspace_id"],
            "legacy_user_id": 900, "display_name": "Persona Prueba", "provider": "gmail"}


class _Row:
    def __init__(self, one=None):
        self.one = one

    def fetchone(self):
        return self.one


class _MailConn:
    def __enter__(self): return self
    def __exit__(self, *_a): return False
    def commit(self): pass

    def execute(self, query, params=()):
        if query.lstrip().startswith("SELECT id,status FROM finva_email_messages"):
            return _Row(None)
        if query.lstrip().startswith("INSERT INTO finva_email_messages"):
            return _Row({"id": 9})
        if query.lstrip().startswith("UPDATE finva_email_messages"):
            return _Row(None)
        raise AssertionError(f"unexpected SQL in this test: {query[:60]}")


def _gmail_candidate(monkeypatch, connection, description, transaction_type="transfer", category="Transferencias"):
    """Run the shared Gmail/Outlook ingestion (no request user: background sync or push)."""
    from backend.auth import owner_role
    from backend.user_product import gmail_service

    # The stored Owner identity (both roles, allowlist, single Owner, own workspace) is proven on
    # a real PostgreSQL in tests/test_owner_category_context_pg.py; here it answers for the Owner's
    # own account and workspace only.
    monkeypatch.setattr(owner_role, "is_verified_owner_account",
                        lambda conn, account_id, workspace_id: (account_id, workspace_id) == (OWNER["account_id"], OWNER["workspace_id"]))
    parsed = {"email_kind": "movement", "transaction_type": transaction_type, "category": category,
              "description": description, "amount": 10_000.0, "currency": "CRC", "transaction_date": "2026-09-22",
              "bank": "multimoney", "confidence": 0.9}
    captured = {}
    monkeypatch.setattr(gmail_service, "get_connection", lambda: _MailConn())
    monkeypatch.setattr(gmail_service, "bank_sender_allowed", lambda sender: True)
    monkeypatch.setattr(gmail_service, "parse_popular_email_document", lambda **kw: None)
    monkeypatch.setattr(gmail_service, "parse_financial_email", lambda *a, **k: dict(parsed))
    monkeypatch.setattr(gmail_service, "identify_received_payroll", lambda item, **kw: item)
    monkeypatch.setattr(gmail_service, "_insert_finva_candidate",
                        lambda conn, **kw: captured.update(kw["candidate"]) or {"status": "pending"})
    gmail_service._ingest_message_once(connection, "synthetic-msg", subject="Aviso", sender="avisos@multimoney.com", body="synthetic")
    return captured["category"]


def test_the_owners_connected_gmail_keeps_his_historical_aliases_in_background_sync(monkeypatch):
    assert owner_context() is False      # no request user: background sync / Gmail push
    assert _gmail_candidate(monkeypatch, OWNER_CONNECTION, "envio papa") == "Familiar"
    assert _gmail_candidate(monkeypatch, OWNER_CONNECTION, "compra acciones", category="acciones") == "IBKR"
    assert _gmail_candidate(monkeypatch, OWNER_CONNECTION, "pago", "expense", category="bac") == "Tarjeta BAC"


@pytest.mark.parametrize("plan", PLANS)
def test_a_regular_connected_gmail_never_consumes_owner_aliases(monkeypatch, plan):
    connection = _user_connection(plan)
    assert _gmail_candidate(monkeypatch, connection, "envio papa") != "Familiar"
    assert _gmail_candidate(monkeypatch, connection, "compra acciones", category="acciones") == "Otros"
    assert _gmail_candidate(monkeypatch, connection, "pago", "expense", category="bac") != "Tarjeta BAC"
    assert _gmail_candidate(monkeypatch, connection, "aporte", category="Interactive Brokers") == "IBKR"   # shared institution


def test_the_mailbox_identity_decides_not_the_session(monkeypatch):
    # A regular mailbox processed during an Owner request stays neutral, and the Owner's mailbox
    # processed during anyone else's request keeps his layer: only stored identity counts.
    with _as(OWNER):
        assert _gmail_candidate(monkeypatch, _user_connection("vip"), "envio papa") != "Familiar"
    with _as({**_user("vip"), "plan": "owner", "access_source": "owner"}):
        assert _gmail_candidate(monkeypatch, OWNER_CONNECTION, "envio papa") == "Familiar"


@pytest.mark.parametrize("forged", [
    {"role": "owner"}, {"plan": "owner"}, {"access_source": "owner"}, {"is_owner": True}, {"workspace_role": "owner"},
])
def test_connection_fields_cannot_claim_the_owner(monkeypatch, forged):
    # Only the stored account and workspace are consulted, never any other field on the row.
    assert _gmail_candidate(monkeypatch, {**_user_connection("vip"), **forged}, "envio papa") != "Familiar"


STATEMENT = """TARJETA DE CREDITO
Fecha de corte: 21-AGO-26
B) Detalle de compras del periodo
************9001 PERSONA
100000000001 25-JUL-26 REGALO MAMA CRC 5,340.00
Total de compras del periodo 5,340.00"""


def test_statement_lines_use_the_owner_layer_only_with_the_owner_identity():
    from backend.user_product.statement_candidate import parse_statement_movements, statement_candidate, statement_hash

    def category(owner):
        rows = parse_statement_movements("bac", STATEMENT, owner=owner)
        return statement_candidate(rows[0], bank="bac", document_hash=statement_hash(STATEMENT), movement_index=0,
                                   statement_text=STATEMENT, owner=owner)["category"]

    assert category(False) == "Sin categoría"
    assert category(True) == "Familiar"
