"""Category aliases match whole words, never letters inside another word.

A short alias ("ot" for overtime, "ins" for insurance, "box" for boxing) used to
match inside unrelated words, so "Otros gastos" became overtime income and a
Dropbox charge became sport. Synthetic values only.
"""
import pytest

from backend.finance.category_catalog import DEFAULT_EXPENSE_CATEGORY, DEFAULT_INCOME_CATEGORY, normalize_category


@pytest.mark.parametrize("value, transaction_type, never", [
    ("Otros gastos", "transfer", "Horas extra"),
    ("Otros gastos", "expense", "Horas extra"),
    ("cotización", "income", "Horas extra"),
    ("Dropbox", "expense", "Deporte"),
    ("Instagram ads", "expense", "Seguros"),
])
def test_an_alias_inside_another_word_never_decides_the_category(value, transaction_type, never):
    assert normalize_category(value, transaction_type) != never


@pytest.mark.parametrize("value, transaction_type, expected", [
    ("pedido uber eats centro", "expense", "Restaurante"),
    ("clase de muay thai", "expense", "Deporte"),
    ("pago seguro del carro", "expense", "Seguros"),
    ("recibo de luz", "expense", "Servicios"),
    ("horas extra semana", "income", "Horas extra"),
    ("Restaurante", "expense", "Restaurante"),
    ("Suscripciones", "expense", "Suscripciones"),
    ("suscripción anual", "expense", "Suscripciones"),
    ("Netflix", "expense", "Suscripciones"),
])
def test_whole_word_aliases_still_categorize(value, transaction_type, expected):
    assert normalize_category(value, transaction_type) == expected


def test_unknown_text_falls_back_to_the_default_of_its_type():
    assert normalize_category("Otros gastos", "expense") == DEFAULT_EXPENSE_CATEGORY
    assert normalize_category("cotización", "income") == DEFAULT_INCOME_CATEGORY


@pytest.mark.parametrize("value, transaction_type, expected", [
    ("Viajes", "expense", "Viajes y turismo"),        # spending on a trip
    ("viaje a la playa", "expense", "Viajes y turismo"),
    ("Airbnb Cuenca", "expense", "Viajes y turismo"),
    ("Viajes", "transfer", "Viajes"),                 # saving for a trip stays the savings goal
    ("viajes", "transfer", "Viajes"),
    ("ecuador", "transfer", "Viajes"),
    ("Venta de activo", "asset_sale", "Venta de activo"),
    ("Cuentas por cobrar", "receivable_payment", "Cuentas por cobrar"),
])
def test_a_name_shared_by_spending_and_saving_follows_the_transaction_type(value, transaction_type, expected):
    assert normalize_category(value, transaction_type) == expected


@pytest.mark.parametrize("value", ["", None, "Otros gastos", "Comercio desconocido XYZ"])
def test_an_unknown_expense_is_explicitly_unknown_never_compras(value):
    assert normalize_category(value, "expense") == "Sin categoría"
    assert DEFAULT_EXPENSE_CATEGORY == "Sin categoría"


def test_regalos_is_not_in_the_catalog_yet():
    # A gift has no canonical category; it stays unknown until one is approved.
    assert normalize_category("Regalos", "expense") == "Sin categoría"


def test_each_movement_type_without_a_category_gets_an_explicit_one():
    from backend.finance.category_catalog import normalize_category
    assert normalize_category("", "receivable_payment") == "Cuentas por cobrar"
    assert normalize_category("", "receivable_offset") == "Cuentas por cobrar"
    assert normalize_category("venta", "asset_sale") == "Venta de activo"          # never an income category
    assert normalize_category("pago", "receivable_payment") == "Cuentas por cobrar"  # never "Salario"
    assert normalize_category("", "transfer") == "Sin categoría"
    assert normalize_category("Comida", "expense") == "Comida"                    # a real category stays editable


def test_manual_expenses_without_a_category_are_unknown_not_compras():
    from backend.finance.category_catalog import manual_expense_category
    assert manual_expense_category("") == manual_expense_category(None) == manual_expense_category("general") == "Sin categoría"
    assert manual_expense_category(" Comida ") == "Comida"


def test_text_import_and_chat_import_never_default_to_compras():
    from backend.ai.monthly_import import normalize_category as chat_category
    from backend.transactions.finance_input import _detect_category
    assert _detect_category("XYZ 5000", "expense") == "Sin categoría"
    assert chat_category("algo raro") == "Sin categoría"
