import unittest

from backend.finance.strategic_engine import _project_closing_balance, _rate_to_monthly
from backend.finance.timeline import _salary_amount_per_event


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


if __name__ == "__main__":
    unittest.main()
