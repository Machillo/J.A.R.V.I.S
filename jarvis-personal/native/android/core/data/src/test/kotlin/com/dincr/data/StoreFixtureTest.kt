package com.dincr.data

import java.io.File
import java.math.BigDecimal
import java.time.LocalDate
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.decodeFromJsonElement
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The STORE sample behind the App Store / Google Play screenshots (store-assets/). The images must be
 * the same on any capture day, must not show sample labels, a courtesy plan or empty charts, and
 * every computed figure must be what the backend computes (store-sample.json, `engine`).
 */
class StoreFixtureTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false }
    private val golden = Json.parseToJsonElement(File("src/main/resources/store-sample.json").readText()).jsonObject

    private fun store(plan: PlanTier, language: AppLanguage = AppLanguage.SPANISH, today: LocalDate = LocalDate.of(2031, 1, 5)) =
        DincrApi(ApiClient("https://fixtures.invalid", { "t" }, FakeBackend(FakeBackend.Scenario.STORE, plan, currentDate = today, language = language), language, backoff = {}))

    private inline fun <reified T> engine(language: String, name: String): T =
        json.decodeFromJsonElement(golden[language]!!.jsonObject["engine"]!!.jsonObject[name]!!)

    private fun same(expected: BigDecimal?, actual: BigDecimal?, what: String) =
        assertTrue("$what: expected $expected, got $actual", expected != null && actual != null && expected.compareTo(actual) == 0)

    @Test fun storeIgnoresTheCaptureDay() = runTest {
        val a = store(PlanTier.VIP, today = LocalDate.of(2027, 3, 1)).freeDashboard()
        val b = store(PlanTier.VIP, today = LocalDate.of(2031, 12, 31)).freeDashboard()
        assertEquals("2026-09", a.month)
        assertEquals(a, b)
    }

    @Test fun freeDashboardIsWhatTheBackendComputes() = runTest {
        for ((code, language) in listOf("es" to AppLanguage.SPANISH, "en" to AppLanguage.ENGLISH)) {
            val served = store(PlanTier.FREE, language).freeDashboard()
            val backend = engine<FreeDashboard>(code, "free_dashboard")
            assertEquals(backend.month, served.month)
            same(backend.income, served.income, "income")
            same(backend.expenses, served.expenses, "expenses")
            same(backend.available, served.available, "available")
            same(backend.debtBalance, served.debtBalance, "debt balance")
            assertEquals(backend.categories.map { it.category }, served.categories.map { it.category })
            backend.categories.zip(served.categories).forEach { (b, s) -> same(b.amount, s.amount, b.category) }
            assertEquals(backend.monthlyHistory.map { it.month }, served.monthlyHistory.map { it.month })
            backend.monthlyHistory.zip(served.monthlyHistory).forEach { (b, s) ->
                same(b.income, s.income, "${b.month} income"); same(b.expenses, s.expenses, "${b.month} expenses")
            }
            assertTrue(served.monthlyHistory.all { it.income.signum() > 0 && it.expenses.signum() > 0 })
        }
    }

    @Test fun strategyCommandCenterAndBudgetAreTheBackendResponses() = runTest {
        val api = store(PlanTier.VIP)
        val strategy = api.strategyBasic()
        assertEquals(engine<Strategy>("es", "strategy_basic"), strategy)
        assertEquals("Cubrí tus compromisos y usá lo que te quede libre para pagar Tarjeta principal.", strategy.recommendation)
        same(strategy.monthlyIncome!! - strategy.essentialExpenses!! - strategy.minimumDebtPayments!!, strategy.strategicMargin, "margin")
        same(strategy.strategicMargin, strategy.allocations.sumOf { it.amount!! }, "allocations")
        val center = api.commandCenter()
        assertEquals(engine<CommandCenter>("es", "command_center"), center)
        same(strategy.strategicMargin, center.safeToSpend?.monthlyMargin, "command center margin")
        val budget = store(PlanTier.BASIC).budget()
        assertEquals(engine<Budget>("es", "budget"), budget)
        // Spending per category is this month's movements.
        val movements = api.movements().filter { it.kind == MovementKind.EXPENSE && it.transactionDate!!.startsWith("2026-09") }
        for (item in budget.items) same(movements.filter { it.category == item.category }.sumOf { it.amount }, item.spent, item.category)
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
        // The emergency goal is the declared savings and target.
        val situation = api.financialSituation().profile!!
        val goal = api.goals().single()
        same(situation.liquidSavings, goal.currentAmount, "saved")
        same(situation.emergencyFundTarget, goal.targetAmount, "target")
    }

    @Test fun englishStoreSpeaksEnglish() = runTest {
        val api = store(PlanTier.VIP, AppLanguage.ENGLISH)
        assertEquals("comma_dot", api.me().numberFormat)
        assertEquals(listOf("Main card", "Car loan"), api.debts().map { it.name })
        assertEquals("Cover your commitments and use what’s left to pay down Main card.", api.strategyBasic().recommendation)
        assertEquals("Groceries", api.movements().first { it.category == "Food" }.description)
        // Same numbers in both languages.
        assertEquals(api.freeDashboard().monthlyHistory, store(PlanTier.VIP, AppLanguage.SPANISH).freeDashboard().monthlyHistory)
    }

    @Test fun otherScenariosAreUnchanged() = runTest {
        val populated = DincrApi(ApiClient("https://fixtures.invalid", { "t" }, FakeBackend(FakeBackend.Scenario.POPULATED, PlanTier.VIP), AppLanguage.SPANISH, backoff = {}))
        assertEquals("courtesy", populated.me().subscription?.accessSource)
        assertEquals("dot_comma", populated.me().numberFormat)
        assertTrue(populated.debts().any { it.name == "Tarjeta de ejemplo" })
        assertEquals("tight", populated.strategyBasic().status)
    }
}
