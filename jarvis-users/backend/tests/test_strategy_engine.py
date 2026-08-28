import unittest
from backend.finance.strategy_engine import build_basic_strategy, build_paycheck_plan, build_vip_insights, build_vip_scenario, build_vip_strategy


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

    def test_vip_goal_guidance_is_deterministic(self):
        snapshot = self.base()
        insights = build_vip_insights(snapshot, build_vip_strategy(snapshot))
        self.assertEqual(insights["active_goals"], 1)
        self.assertGreater(insights["goal_guidance"][0]["remaining"], 0)
        self.assertIsNotNone(insights["goal_guidance"][0]["monthly_needed"])

    def test_vip_scenario_does_not_mutate_source(self):
        snapshot = self.base()
        original_income = snapshot["monthly_income_estimate"]
        result = build_vip_scenario(snapshot, monthly_income_change=100000, monthly_expense_change=25000, one_time_extra=50000)
        self.assertEqual(snapshot["monthly_income_estimate"], original_income)
        self.assertEqual(result["delta"]["strategic_margin"], 75000)
        self.assertEqual(result["inputs"]["one_time_extra"], 50000)

    def test_paycheck_plan_scales_monthly_strategy(self):
        strategy = build_basic_strategy(self.base())
        plan = build_paycheck_plan(strategy, "biweekly")
        self.assertGreater(plan["estimated_paycheck"], 0)
        self.assertLess(plan["estimated_paycheck"], strategy["monthly_income"])
        self.assertTrue(any(x["bucket"] == "essentials" for x in plan["envelopes"]))


if __name__ == "__main__":
    unittest.main()
