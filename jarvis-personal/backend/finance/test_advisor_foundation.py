import unittest

from backend.finance.strategic_engine import _project_closing_balance, _rate_to_monthly
from backend.finance.timeline import _salary_amount_per_event
from backend.advisor.core import _minimum_projected_balance, _safe_usable_money
from backend.ai.intent_router import _fallback_detect


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


if __name__ == "__main__":
    unittest.main()
