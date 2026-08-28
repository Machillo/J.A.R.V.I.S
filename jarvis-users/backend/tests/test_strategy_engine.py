import unittest
from backend.finance.strategy_engine import build_basic_strategy, build_vip_strategy


class StrategyEngineTests(unittest.TestCase):
    def base(self):
        return {
            "monthly_income_estimate": 600000,
            "essential_monthly_expenses": 300000,
            "liquid_savings": 20000,
            "emergency_fund_target": 300000,
            "strategy_preference": "balanced",
            "discretionary_monthly_minimum": 30000,
            "debts": [
                {"id": 1, "name": "A", "remaining_amount": 500000, "monthly_payment": 50000, "interest_rate": 20, "payment_day": 5},
                {"id": 2, "name": "B", "remaining_amount": 200000, "monthly_payment": 25000, "interest_rate": 35, "payment_day": 10},
            ],
            "goals": [{"id": 1, "name": "Viaje", "target_amount": 500000, "current_amount": 50000, "priority": "high", "target_date": "2027-01-01"}],
        }

    def test_basic_targets_highest_known_apr(self):
        r = build_basic_strategy(self.base())
        self.assertEqual(r["priority"], "debt")
        self.assertEqual(r["target_debt"]["name"], "B")
        self.assertGreater(r["strategic_margin"], 0)
        self.assertTrue(r["allocations"])

    def test_basic_never_invents_missing_debt_data(self):
        s = self.base(); s["debts"][0]["monthly_payment"] = None; s["debts"][0]["interest_rate"] = None
        r = build_basic_strategy(s)
        self.assertTrue(any("cuota" in x for x in r["warnings"]))
        self.assertTrue(any("tasa" in x for x in r["warnings"]))

    def test_critical_has_no_extra_allocations(self):
        s = self.base(); s["essential_monthly_expenses"] = 590000
        r = build_basic_strategy(s)
        self.assertEqual(r["status"], "critical")
        self.assertEqual(r["allocations"], [])

    def test_simulation_adds_capacity(self):
        normal = build_basic_strategy(self.base())
        simulated = build_basic_strategy(self.base(), extra_monthly=25000)
        self.assertGreater(sum(x["amount"] for x in simulated["allocations"]), sum(x["amount"] for x in normal["allocations"]))

    def test_vip_respects_personal_minimum_and_goals(self):
        r = build_vip_strategy(self.base())
        buckets = {x["bucket"] for x in r["vip_allocations"]}
        self.assertIn("personal", buckets)
        self.assertIn("goal", buckets)
        self.assertTrue(r["director_mode"])


if __name__ == "__main__":
    unittest.main()
