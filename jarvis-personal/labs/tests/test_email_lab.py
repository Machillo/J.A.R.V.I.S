"""Parser playground: every synthetic fixture parses exactly as recorded (golden), with no database."""
from __future__ import annotations

from decimal import Decimal

import pytest

from labs import email_lab

CASES = email_lab.load_fixtures()["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_fixture_parses_as_recorded(case):
    report = email_lab.report(email_lab.fixture(case["name"]))
    expected = case["expected"]
    assert (report["kind"], report["bank"], report["type"]) == (expected["email_kind"], expected["bank"], expected["transaction_type"])
    if expected["email_kind"] == "movement":
        assert Decimal(report["amount"]) == Decimal(expected["amount"])
        assert report["date"] == expected["transaction_date"]
        assert report["candidate"] is not None
        original = expected.get("original_amount")
        assert report["candidate"]["original_amount"] == (None if original is None else str(float(original)))
    else:
        assert report["candidate"] is None


def test_the_playground_never_echoes_the_body_and_masks_long_numbers():
    report = email_lab.report(email_lab.fixture("bac_purchase_crc"))
    assert "body" not in report and "raw_payload" not in str(report)
    assert "000000000001" not in str(report)  # reference number masked in the dedupe key


def test_usd_candidate_keeps_the_native_amount_next_to_the_matching_amount():
    report = email_lab.report(email_lab.fixture("bac_purchase_usd"))
    assert report["original"] == "USD 21.0"
    assert report["candidate"]["original_currency"] == "USD"


def test_duplicates_share_a_dedupe_key_and_distinct_movements_do_not():
    key = lambda name: email_lab.parse(email_lab.fixture(name))["parsed"]["dedupe_key"]  # noqa: E731
    assert key("bac_duplicate") == key("bac_purchase_crc")
    assert key("bac_refund_income") != key("bac_purchase_crc")
