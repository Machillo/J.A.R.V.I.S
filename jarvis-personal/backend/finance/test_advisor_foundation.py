import unittest

from backend.finance.strategic_engine import _project_closing_balance, _rate_to_monthly
from backend.finance.timeline import _salary_amount_per_event
from backend.advisor.core import _minimum_projected_balance, _safe_usable_money
from backend.ai.intent_router import _fallback_detect
from backend.ai.strategy_dashboard import _build_dynamic_director_allocation
from backend.goals.strategy import build_goal_portfolio


class AdvisorFoundationTests(unittest.TestCase):
    def test_monthly_salary_is_split_between_semimonthly_events(self):
        self.assertEqual(_salary_amount_per_event(800_000, "quincenal"), 400_000)

    def test_weekly_salary_uses_average_calendar_frequency(self):
        self.assertAlmostEqual(_salary_amount_per_event(520_000, "weekly"), 120_000, places=2)

    def test_low_apr_is_not_misread_as_monthly_rate(self):
        monthly, interpretation = _rate_to_monthly(4.5)
        self.assertAlmostEqual(monthly, 0.045 / 12)
        self.assertEqual(interpretation, "tasa_anual_porcentaje")

    def test_closing_forecast_starts_from_real_liquidity(self):
        self.assertEqual(_project_closing_balance(205_000, 400_000, 250_000, 100_000), 255_000)

    def test_advisor_uses_worst_balance_inside_horizon(self):
        timeline = {"opening_available": 200_000, "events": [{"projected_balance": 80_000}, {"projected_balance": -5_000}]}
        self.assertEqual(_minimum_projected_balance(timeline), -5_000)

    def test_usable_money_never_consumes_protected_minimum(self):
        usable = _safe_usable_money(operating_surplus=100_000, liquidity=300_000, protected_minimum=250_000, timeline_floor=280_000)
        self.assertEqual(usable, 30_000)

    def test_financial_priorities_are_not_misread_as_calendar(self):
        result = _fallback_detect("Analiza mi situación financiera actual y dime qué debo hacer hoy.")
        self.assertEqual(result["intent"], "advisor_summary")

    def test_usable_money_question_is_not_sent_to_internet(self):
        result = _fallback_detect("¿Cuánto dinero puedo usar realmente sin afectar mis obligaciones ni mi Salvavidas?")
        self.assertEqual(result["intent"], "advisor_summary")

    def test_distribution_blocks_investment_with_expensive_debt_and_no_safety(self):
        result = _build_dynamic_director_allocation(
            available_before_allocation=100_000,
            debts=[{"remaining_amount": 500_000, "interest_rate": 35.76}],
            goal_reserves={},
            savings_total=0,
            emergency_monthly_base=250_000,
        )
        amounts = result["allocation_amounts"]
        self.assertEqual(amounts["inversion"], 0)
        self.assertEqual(amounts["fondo_de_emergencia"], 40_000)
        self.assertEqual(amounts["ataque_de_deuda"], 45_000)
        self.assertEqual(amounts["vida_controlada"], 15_000)

    def test_distribution_allows_investment_only_without_debt_and_with_one_month_saved(self):
        result = _build_dynamic_director_allocation(
            available_before_allocation=100_000,
            debts=[],
            goal_reserves={},
            savings_total=250_000,
            emergency_monthly_base=250_000,
        )
        self.assertTrue(result["investment_allowed"])
        self.assertEqual(result["allocation_amounts"]["inversion"], 55_000)

    def test_goal_portfolio_funds_only_selected_trip_alternative(self):
        goals = [
            {"id": 1, "name": "Argentina", "status": "active", "alternative_group": "viaje-2027", "is_selected": True, "remaining_amount": 600_000, "monthly_required": 60_000, "funding_order": 10},
            {"id": 2, "name": "Italia", "status": "candidate", "alternative_group": "viaje-2027", "is_selected": False, "remaining_amount": 1_500_000, "monthly_required": 150_000, "funding_order": 10},
        ]
        result = build_goal_portfolio(goals, available=100_000, one_month_protected=True, highest_debt_apr=0)
        self.assertEqual(result["active_goal"]["name"], "Argentina")
        self.assertEqual(result["goal_allocation"], 60_000)
        self.assertEqual(result["items"][1]["blocked_by"], "alternativa no seleccionada")

    def test_goal_portfolio_blocks_car_until_trip_and_financial_floor_are_ready(self):
        goals = [{"id": 3, "name": "Carro", "status": "active", "depends_on_group": "viaje-2027", "remaining_amount": 5_000_000, "monthly_required": 200_000, "funding_order": 20}]
        result = build_goal_portfolio(goals, available=300_000, one_month_protected=False, highest_debt_apr=26)
        self.assertIsNone(result["active_goal"])
        self.assertIn("primero debe completarse", result["items"][0]["blocked_by"])


if __name__ == "__main__":
    unittest.main()
