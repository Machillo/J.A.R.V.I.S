"""One CRC/USD conversion contract for every amount that becomes financial truth.

Mail/statement candidates (candidate_currency.transaction_amounts) and manual
income/expense entries (entry_currency.resolve_entry_amount, when present) must
produce exactly the golden vectors in currency_conversion_vectors.json: same
rate definition (CRC per 1 USD), rounding and rejections. Storage limits follow
each destination's real columns: a vector with a 'target' applies only to it
(candidates write transactions, NUMERIC(12,x) in production; manual entries
write salaries/expenses, NUMERIC(14,x)). When both helpers are in the code base,
the second test runs them against the same vectors, so they cannot drift apart
silently. Synthetic values only.
"""
import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.user_product.candidate_currency import transaction_amounts

VECTORS = json.loads((Path(__file__).with_name("currency_conversion_vectors.json")).read_text(encoding="utf-8"))["vectors"]
CANDIDATE_VECTORS = [vector for vector in VECTORS if vector.get("target") in (None, "transactions")]
ENTRY_VECTORS = [vector for vector in VECTORS if vector.get("target") in (None, "entries")]


def _outcome(convert, vector):
    try:
        result = convert(vector)
    except HTTPException as error:
        return {"status": error.status_code}
    assert set(result) == {"amount", "original_amount", "original_currency", "exchange_rate"}
    return {
        key: (format(value, "f") if isinstance(value, Decimal) else value)
        for key, value in result.items()
    }


def test_the_storage_limits_are_the_real_production_columns():
    """transactions is NUMERIC(12,2)/(12,6) in production (gate Q0), not the 14,x of schema.sql."""
    from backend.user_product import candidate_currency

    assert candidate_currency.MAX_AMOUNT == Decimal("9999999999.99")
    assert candidate_currency.MAX_RATE == Decimal("999999.999999")
    # salaries/expenses: original_amount NUMERIC(14,2), exchange_rate NUMERIC(14,6) (20260928110000);
    # amount held to NUMERIC(12,2) until its production type is verified.
    from backend.user_product import entry_currency

    assert entry_currency.MAX_ORIGINAL == Decimal("999999999999.99")
    assert entry_currency.MAX_RATE == Decimal("99999999.999999")
    assert entry_currency.MAX_AMOUNT == Decimal("9999999999.99")
    assert {vector.get("target") for vector in VECTORS} == {None, "transactions", "entries"}


def test_the_matrix_covers_every_required_case():
    cases = " | ".join(vector["case"] for vector in VECTORS)
    for required in ("CRC to CRC", "USD to USD", "USD to CRC", "CRC to USD", "missing rate",
                     "invalid rate", "rounding", "overflow", "legacy"):
        assert required in cases, required


@pytest.mark.parametrize("vector", CANDIDATE_VECTORS, ids=[vector["case"] for vector in CANDIDATE_VECTORS])
def test_candidate_conversion_matches_the_golden_vectors(vector):
    outcome = _outcome(lambda v: transaction_amounts(v["currency"], v["amount"], v["base"], v["rate"]), vector)
    assert outcome == vector["expect"]


@pytest.mark.parametrize("vector", ENTRY_VECTORS, ids=[vector["case"] for vector in ENTRY_VECTORS])
def test_manual_entry_conversion_matches_the_same_vectors(vector):
    # Present once the manual income/expense currency work is in main; until
    # then there is nothing to compare against.
    entry_currency = pytest.importorskip("backend.user_product.entry_currency")
    outcome = _outcome(
        lambda v: entry_currency.resolve_entry_amount(v["base"], v["amount"], v["currency"], v["rate"]), vector,
    )
    assert outcome == vector["expect"]
