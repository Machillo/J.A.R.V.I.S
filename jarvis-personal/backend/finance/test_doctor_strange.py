from datetime import date

from backend.finance.doctor_strange import calculate_doctor_strange


def test_evaluates_all_six_debt_orders():
    debts = [
        {"id": index, "name": f"D{index}", "remaining_amount": 100_000 + index * 10_000, "monthly_payment": 20_000, "interest_rate": 8 + index}
        for index in range(1, 7)
    ]
    result = calculate_doctor_strange(debts, extra_payment=25_000, start_date=date(2026, 9, 16))
    assert result["status"] == "OK"
    assert result["mode"] == "exhaustive"
    assert result["permutations_evaluated"] == 720
    assert set(result["strategies"]) == {"cheapest", "fastest", "motivational", "balanced"}


def test_accounts_for_daily_interest_fees_and_penalty():
    debts = [{
        "id": 1,
        "name": "Préstamo",
        "remaining_amount": 100_000,
        "monthly_payment": 20_000,
        "interest_rate": 24,
        "fixed_fee_amount": 1_000,
        "prepayment_penalty_amount": 2_500,
    }]
    result = calculate_doctor_strange(debts, extra_payment=100_000, start_date=date(2026, 1, 1))
    strategy = result["strategies"]["cheapest"]
    assert strategy["total_interest"] > 0
    assert strategy["total_fixed_fees"] == 1_000
    assert strategy["total_prepayment_penalties"] == 2_500
    assert strategy["payoff_date"] == "2026-02-01"
