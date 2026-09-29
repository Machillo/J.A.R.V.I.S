package com.dincr.data

import java.math.BigDecimal
import java.time.LocalDate
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The STORE sample behind the App Store / Google Play screenshots (store-assets/). The images must be
 * the same on any capture day, must not show sample labels, a courtesy plan or empty charts, and the
 * numbers on different screens must agree.
 */
class StoreFixtureTest {
    private fun store(plan: PlanTier, language: AppLanguage = AppLanguage.SPANISH, today: LocalDate = LocalDate.of(2031, 1, 5)) =
        DincrApi(ApiClient("https://fixtures.invalid", { "t" }, FakeBackend(FakeBackend.Scenario.STORE, plan, currentDate = today, language = language), language, backoff = {}))

    private fun same(expected: Long, actual: BigDecimal?) = assertEquals(0, BigDecimal(expected).compareTo(actual))

    @Test fun storeIgnoresTheCaptureDay() = runTest {
        val a = store(PlanTier.VIP, today = LocalDate.of(2027, 3, 1)).freeDashboard()
        val b = store(PlanTier.VIP, today = LocalDate.of(2031, 12, 31)).freeDashboard()
        assertEquals("2026-09", a.month)
        assertEquals(a, b)
    }

    @Test fun storeHasSixFullMonthsWithCoherentTotals() = runTest {
        val dashboard = store(PlanTier.FREE).freeDashboard()
        assertEquals(6, dashboard.monthlyHistory.size)
        for (month in dashboard.monthlyHistory) {
            same(StoreSample.MONTHLY_INCOME, month.income)
            assertTrue(month.expenses.signum() > 0 && month.expenses < month.income)
            assertEquals(0, (month.income - month.expenses).compareTo(month.balance))
        }
        assertEquals(0, (dashboard.income - dashboard.expenses).compareTo(dashboard.balance))
        assertEquals(0, dashboard.debtBalance!!.compareTo(store(PlanTier.FREE).debts().sumOf { it.remainingAmount!! }))
    }

    @Test fun strategyAndProjectionsAgreeWithTheDeclaredData() = runTest {
        val api = store(PlanTier.VIP)
        val situation = api.financialSituation().profile!!
        val debts = api.debts()
        val strategy = api.strategyBasic()
        same(StoreSample.MONTHLY_INCOME, strategy.monthlyIncome)
        assertEquals(0, situation.essentialMonthlyExpenses!!.compareTo(strategy.essentialExpenses))
        assertEquals(0, debts.sumOf { it.monthlyPayment!! }.compareTo(strategy.minimumDebtPayments))
        assertEquals(0, (strategy.monthlyIncome!! - strategy.essentialExpenses!! - strategy.minimumDebtPayments!!).compareTo(strategy.strategicMargin))
        assertEquals(0, strategy.allocations.sumOf { it.amount!! }.compareTo(strategy.strategicMargin))
        // The emergency goal is the declared savings and target.
        val goal = api.goals().single()
        assertEquals(0, goal.currentAmount!!.compareTo(situation.liquidSavings))
        assertEquals(0, goal.targetAmount!!.compareTo(situation.emergencyFundTarget))
        // Projections start from today's savings and debt.
        val center = api.commandCenter()
        val total = debts.sumOf { it.remainingAmount!! }
        for (point in center.projections) {
            val months = point.months!!.toLong()
            same(StoreSample.SAVED + StoreSample.TO_EMERGENCY * months, point.cash)
            assertTrue(point.debt!! < total)
            assertEquals(0, (point.cash!! - point.debt!!).compareTo(point.netWorth))
        }
        assertEquals(0, center.safeToSpend!!.monthlyMargin!!.compareTo(strategy.strategicMargin))
    }

    @Test fun storeShowsAStorePlanAndAFirstNameWithoutSampleLabels() = runTest {
        for (plan in listOf(PlanTier.BASIC, PlanTier.VIP)) {
            val profile = store(plan).me()
            assertEquals("Ana", profile.displayName)
            assertEquals("self_service", profile.subscription?.accessSource)
        }
        val api = store(PlanTier.VIP)
        val names = api.debts().map { it.name } + api.commandCenter().debtPlanner?.recommended?.target + api.goals().map { it.name } +
            api.mailCandidates(true).map { it.sender } + api.mailStatus().connections.map { it.email }
        assertFalse(names.any { it.orEmpty().contains("ejemplo", ignoreCase = true) })
        assertNotNull(api.financialSituation().profile)
    }

    @Test fun englishStoreSpeaksEnglish() = runTest {
        val api = store(PlanTier.VIP, AppLanguage.ENGLISH)
        assertEquals("comma_dot", api.me().numberFormat)
        assertEquals(listOf("Main card", "Car loan"), api.debts().map { it.name })
        assertTrue(api.strategyBasic().recommendation!!.startsWith("Put ₡150,000 extra"))
        assertEquals("Groceries", api.movements().first { it.category == "Food" }.description)
        val spanish = store(PlanTier.VIP, AppLanguage.SPANISH)
        // Backend sentences use the profile's separators, not the device locale's (es-CR groups with a space).
        val previous = java.util.Locale.getDefault()
        java.util.Locale.setDefault(java.util.Locale.forLanguageTag("es-CR"))
        try {
            assertTrue(spanish.strategyBasic().recommendation!!.startsWith("Destiná ₡150.000 extra"))
            assertTrue(spanish.commandCenter().director!!.nextAction!!.contains("₡150.000"))
        } finally {
            java.util.Locale.setDefault(previous)
        }
        // Same numbers in both languages.
        assertEquals(api.freeDashboard().monthlyHistory, spanish.freeDashboard().monthlyHistory)
    }

    @Test fun otherScenariosAreUnchanged() = runTest {
        val populated = DincrApi(ApiClient("https://fixtures.invalid", { "t" }, FakeBackend(FakeBackend.Scenario.POPULATED, PlanTier.VIP), AppLanguage.SPANISH, backoff = {}))
        assertEquals("courtesy", populated.me().subscription?.accessSource)
        assertEquals("dot_comma", populated.me().numberFormat)
        assertTrue(populated.debts().any { it.name == "Tarjeta de ejemplo" })
    }
}
