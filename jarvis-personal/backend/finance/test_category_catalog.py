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
