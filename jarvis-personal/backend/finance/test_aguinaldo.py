from datetime import date

from backend.finance.service import _aguinaldo_period, _build_aguinaldo_report


def test_aguinaldo_period_runs_from_december_to_november():
    assert _aguinaldo_period(date(2026, 9, 3)) == (date(2025, 12, 1), date(2026, 11, 30))
    assert _aguinaldo_period(date(2026, 12, 3)) == (date(2026, 12, 1), date(2027, 11, 30))


def test_aguinaldo_uses_real_salary_components_and_divides_by_twelve():
    rows = [
        {"kind": "salary", "amount": 120_000, "earned_on": date(2026, 8, 1)},
        {"kind": "payroll_event", "amount": 18_000, "earned_on": date(2026, 8, 10)},
        {"kind": "payroll_event", "amount": -6_000, "earned_on": date(2026, 8, 11)},
        {"kind": "bonus", "amount": 12_000, "earned_on": date(2026, 8, 15)},
        {"kind": "salary", "amount": 999_999, "earned_on": date(2025, 11, 30)},
    ]

    report = _build_aguinaldo_report(rows, date(2026, 9, 3))

    assert report["earned_salary_total"] == 144_000
    assert report["accrued_aguinaldo"] == 12_000
    assert report["source_totals"] == {
        "ccss_salary": 0,
        "salary": 120_000,
        "payroll_event": 12_000,
        "bonus": 12_000,
    }
    august = next(item for item in report["months"] if item["month"] == "2026-08")
    assert august["total_earned"] == 144_000
    assert august["entries"] == 4


def test_ccss_salary_can_replace_internal_month_components():
    report = _build_aguinaldo_report([
        {"kind": "ccss_salary", "amount": 712_647.40, "earned_on": date(2026, 7, 1)},
    ], date(2026, 9, 3))
    assert report["source_totals"]["ccss_salary"] == 712_647.40
    assert report["accrued_aguinaldo"] == 59_387.28
