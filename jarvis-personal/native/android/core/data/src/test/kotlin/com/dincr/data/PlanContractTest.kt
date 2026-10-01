package com.dincr.data

import java.math.BigDecimal
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

/**
 * Plan recovery: the three strategy contracts (Basic ≠ VIP users ≠ Owner), the money distribution
 * read from the same response, Salvavidas (users vs owner) and the situation form's work days.
 * The fake server mirrors the backend's shapes and role checks.
 */
class PlanContractTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false; encodeDefaults = true }

    private fun fixture(plan: PlanTier = PlanTier.FREE, role: FakeBackend.Role = FakeBackend.Role.USER, scenario: FakeBackend.Scenario = FakeBackend.Scenario.POPULATED) =
        FakeBackend(scenario, plan, role = role).let { it to DincrApi(ApiClient("https://fixtures.invalid", { "t" }, it, AppLanguage.SPANISH, backoff = {})) }

    private fun profile(role: String, plan: String?) = Profile(id = 1, role = role, subscription = plan?.let { Profile.Subscription(plan = it, status = "active") })

    private suspend fun status(block: suspend () -> Unit): Int = try { block(); 200 } catch (error: ApiError) { error.status }

    @Test fun eachIdentityReadsItsOwnStrategyContract() {
        assertNull("Free has no strategy (the row is locked)", StrategyContract.of(profile("user", "free"), vipIntelligenceOn = true))
        assertEquals(StrategyContract.BASIC, StrategyContract.of(profile("user", "basic"), true))
        assertEquals(StrategyContract.VIP_USERS, StrategyContract.of(profile("user", "vip"), true))
        // VIP intelligence paused: the dashboard is paused server-side, VIP still has strategy-basic.
        assertEquals(StrategyContract.BASIC, StrategyContract.of(profile("user", "vip"), false))
        // Only the server role makes the Owner: never a plan code.
        listOf("vip", "owner", "free", null).forEach { assertEquals(StrategyContract.OWNER, StrategyContract.of(profile("owner", it), false)) }
        assertEquals(StrategyContract.VIP_USERS, StrategyContract.of(profile("user", "owner").copy(subscription = Profile.Subscription(plan = "vip")), true))
        assertTrue(StrategyContract.of(profile("admin", "vip"), true) != StrategyContract.OWNER)
        assertNull(StrategyContract.of(null, true))
    }

    @Test fun vipUsersGetTheUsersDashboardAndNeverTheOwnerOne() = runTest {
        val (backend, api) = fixture(PlanTier.VIP)
        val dashboard = api.strategyDashboard()
        assertTrue(backend.requests.last().url.endsWith("/user-product/vip/strategy-dashboard"))
        val s = dashboard.strategy!!
        assertEquals("users", s.scope)
        assertNull("Users never get an account cash figure", s.distributableAccountCash)
        assertNull(s.recurringMonthlyIncome)
        assertTrue(s.allocationItems.isNotEmpty())
        // The director counts unknown savings as 0; the screen reads them as unknown, never ₡0.
        assertEquals(false, s.salvavidas?.currentAmountKnown)
        assertFalse(s.emergencyKnown)
        // The Owner's endpoint is refused to a user (the fake, like the server role check).
        assertEquals(403, status { api.ownerStrategyDashboard() })
    }

    @Test fun theOwnerReadsTheJarvisDashboardWithItsOwnFields() = runTest {
        val (backend, api) = fixture(role = FakeBackend.Role.OWNER)
        val s = api.ownerStrategyDashboard().strategy!!
        assertTrue(backend.requests.last().url.endsWith("/jarvis/premium/strategy-dashboard"))
        assertEquals("owner", s.scope)
        assertTrue(s.isOwnerScope)
        assertNotNull(s.distributableAccountCash)
        assertNotNull(s.currentMonthExtraNet)
        assertEquals("USD", s.investmentPortfolio?.currency)
        assertTrue(s.mandatoryFixedPendingItems.isNotEmpty())
        assertTrue(s.emergencyKnown)
    }

    @Test fun basicStrategySaysWhereTheIncomeComesFrom() = runTest {
        val (_, api) = fixture(PlanTier.BASIC)
        // No declared salary yet: the recorded income is used, and the answer says so.
        val observed = api.strategyBasic()
        assertEquals("observed", observed.incomeSource)
        assertTrue(observed.isIncomeObserved)
        api.updateFinancialSituation(FinancialProfile(incomeType = "fixed", fixedMonthlySalary = BigDecimal(900000), workDaysPerWeek = 5, payFrequency = "monthly"), "k1")
        val declared = api.strategyBasic()
        assertEquals("declared", declared.incomeSource)
        assertFalse(declared.isIncomeObserved)
        // Nothing declared and nothing recorded: needs_income (the screen offers Situación financiera).
        val empty = fixture(PlanTier.BASIC, scenario = FakeBackend.Scenario.EMPTY).second.strategyBasic()
        assertEquals("needs_income", empty.status)
        assertEquals("none", empty.incomeSource)
    }

    @Test fun dashboardDecodingIsTolerant() {
        val raw = """{"status":"OK","user_role":"user","title":"t","content":"c","source":"live_database","has_premium_strategy":true,
            "strategy":{"scope":"users","status":"controlled","monthly_income":865000.5,"new_backend_field":{"x":1},
            "income_policy":{"policy":"declared_first","source":"observed","declared":null,"baseline":1,"recurring":2},
            "emergency_fund":{"current":null,"monthly_base":119900},"timeline":[{"priority":1,"name":"Tarjeta","unknown":true}],
            "allocation_items":[{"key":"ataque_de_deuda","percentage":45,"amount":1000.25,"target_name":"Tarjeta"}],
            "distribution_formula":{"income":865000,"recorded_spending":null,"surplus":1000.25},"distributable_account_cash":null}}"""
        val s = json.decodeFromString<StrategyDashboard>(raw).strategy!!
        assertEquals(0, BigDecimal("865000.5").compareTo(s.monthlyIncome))
        assertEquals("observed", s.incomePolicy?.source)
        assertNull("unknown savings stay unknown", s.emergencyFund?.current)
        assertNull(s.totalDebt)
        assertEquals("Ataque de deuda · Tarjeta", Distribution.allocationLabel(s.allocationItems.single(), AppLanguage.SPANISH))
        // Only the keys present are listed; a null amount stays unknown, never zero.
        assertEquals(listOf("income", "recorded_spending", "surplus"), Distribution.formulaLines(s).map { it.first })
        assertNull(Distribution.formulaLines(s).first { it.first == "recorded_spending" }.second)
    }

    @Test fun distributionReadsTheSameResponseAsTheStrategy() = runTest {
        val (_, api) = fixture(role = FakeBackend.Role.OWNER)
        val owner = api.ownerStrategyDashboard().strategy!!
        val ownerKeys = Distribution.formulaLines(owner).map { it.first }
        assertEquals("cash_available_now", ownerKeys.first())
        assertTrue(ownerKeys.containsAll(listOf("statement_spending", "new_spending_after_cut", "mandatory_fixed_pending", "surplus")))
        val users = fixture(PlanTier.VIP).second.strategyDashboard().strategy!!
        val userKeys = Distribution.formulaLines(users).map { it.first }
        assertEquals(listOf("income", "recorded_spending", "debt_commitment", "pending_recurring", "surplus", "deficit"), userKeys)
        // A cash key in a Users answer is never shown.
        val leaked = users.copy(distributionFormula = users.distributionFormula + ("cash_available_now" to kotlinx.serialization.json.JsonPrimitive(1)))
        assertFalse(Distribution.formulaLines(leaked).any { it.first == "cash_available_now" })
        // The allocation amounts are the backend's: listed as sent, with the base they split.
        assertEquals(0, users.allocationBaseAmount!!.compareTo(users.allocationItems.sumOf { it.amount!! }))
        // Basic: the strategy-basic allocations (the same response the Strategy screen reads).
        val basic = fixture(PlanTier.BASIC).second.strategyBasic()
        assertEquals(listOf("emergency", "debt_extra", "flex"), basic.allocations.map { it.bucket })
        assertEquals(1L, basic.allocations[1].debtId)
    }

    @Test fun salvavidasUsersAndOwnerModelsDecode() {
        val users = json.decodeFromString<Salvavidas>("""{"status":"OK","scope":"users","current_amount":null,"current_amount_known":false,"monthly_base":119900,
            "target_months":6,"allowed_target_months":[1,3,6],"target_amount":719400,"missing_amount":null,"coverage_months":null,"progress_percent":null,
            "components":{"debt_monthly_payments":95000,"recurring_obligations":24900},"debts":[{"id":1,"name":"Tarjeta","monthly_payment":45000}],
            "obligations":[{"id":5,"name":"Internet","monthly_amount":24900,"frequency":"monthly","due_day":4}],
            "milestones":[{"months":1,"target":119900,"reached":false}],"verification":{"mode":"declared","message":"m"}}""")
        assertFalse(users.isOwnerScope)
        assertFalse("unknown savings are never shown as an amount", users.isAmountKnown)
        assertNull(users.coverageMonths)
        assertEquals(listOf(1, 3, 6), users.targetChoices)
        val owner = json.decodeFromString<Salvavidas>("""{"status":"OK","scope":"owner","current_amount":300000,"monthly_base":330000,"target_months":3,
            "target_amount":990000,"missing_amount":690000,"coverage_months":0.91,"progress_percent":30.3,"protected_expense_ids":[31],
            "components":{"debt_monthly_payments":95000,"mandatory_fixed_expenses":210000,"protected_expenses":25000},
            "mandatory_expenses":[{"id":30,"name":"Vivienda","monthly_amount":210000,"selected":true,"mandatory":true}],
            "available_expenses":[{"id":31,"name":"Gimnasio","monthly_amount":25000,"selected":true}],"excluded_debt_duplicates":[],
            "verification":{"mode":"manual","account_linked":false,"message":"m"}}""")
        assertTrue(owner.isOwnerScope && owner.isAmountKnown)
        assertEquals(listOf(31L), owner.protectedExpenseIds)
        assertEquals(Salvavidas.ALLOWED_TARGET_MONTHS, owner.targetChoices)
    }

    @Test fun salvavidasPutBodiesCarryOnlyTheChangedField() {
        assertEquals("""{"target_months":3}""", json.encodeToString(SalvavidasUpdate.target(3)))
        assertEquals("""{"current_amount":250000.5}""", json.encodeToString(SalvavidasUpdate.amount(BigDecimal("250000.50"))))
        assertEquals("""{"protected_expense_ids":[31,32]}""", json.encodeToString(SalvavidasUpdate.ownerProtected(listOf(31, 32, 31))))
        listOf(0, 2, 12).forEach { months -> runCatching { SalvavidasUpdate.target(months) }.onSuccess { fail("$months months must be refused") } }
        runCatching { SalvavidasUpdate.amount(BigDecimal(-1)) }.onSuccess { fail("negative savings must be refused") }
    }

    @Test fun usersSalvavidasNeverTurnsUnknownSavingsIntoZero() = runTest {
        val (_, api) = fixture(PlanTier.VIP)
        val unknown = api.salvavidas()
        assertEquals("users", unknown.scope)
        assertFalse(unknown.isAmountKnown)
        assertNull(unknown.coverageMonths)
        assertTrue(unknown.milestones.none { it.reached == true })
        // Users never send protected expenses; savings need a financial situation first.
        assertEquals(422, status { api.updateSalvavidas(SalvavidasUpdate.ownerProtected(listOf(31))) })
        assertEquals(422, status { api.updateSalvavidas(SalvavidasUpdate.amount(BigDecimal(100000))) })
        assertEquals(3, api.updateSalvavidas(SalvavidasUpdate.target(3)).targetMonths)
        api.updateFinancialSituation(FinancialProfile(incomeType = "fixed", fixedMonthlySalary = BigDecimal(900000), workDaysPerWeek = 5), "k2")
        val known = api.updateSalvavidas(SalvavidasUpdate.amount(BigDecimal(239800)))
        assertTrue(known.isAmountKnown)
        assertEquals(0, BigDecimal(2).compareTo(known.coverageMonths))
        // The same declared savings as the financial situation (one source of truth).
        assertEquals(0, BigDecimal(239800).compareTo(api.financialSituation().profile?.liquidSavings))
    }

    @Test fun theOwnerSalvavidasIsTheHistoricalModel() = runTest {
        val (_, api) = fixture(role = FakeBackend.Role.OWNER)
        val state = api.salvavidas()
        assertEquals("owner", state.scope)
        assertTrue(state.availableExpenses.isNotEmpty())
        val updated = api.updateSalvavidas(SalvavidasUpdate.ownerProtected(listOf(31, 32)))
        assertEquals(listOf(31L, 32L), updated.protectedExpenseIds)
        assertEquals(0, BigDecimal(500000).compareTo(api.updateSalvavidas(SalvavidasUpdate.amount(BigDecimal(500000))).currentAmount))
    }

    @Test fun theSituationFormAlwaysSendsWorkDays() = runTest {
        assertEquals(5, SituationDefaults.workDays(null))
        assertEquals(5, SituationDefaults.workDays(FinancialProfile(workDaysPerWeek = 0)))
        assertEquals(6, SituationDefaults.workDays(FinancialProfile(incomeType = "fixed", workDaysPerWeek = 6)))
        val (backend, api) = fixture(PlanTier.FREE)
        // Like the backend: a fixed income without work days is a 422 (the bug the form had).
        assertEquals(422, status { api.updateFinancialSituation(FinancialProfile(incomeType = "fixed", fixedMonthlySalary = BigDecimal(800000)), "k3") })
        api.updateFinancialSituation(FinancialProfile(incomeType = "fixed", fixedMonthlySalary = BigDecimal(800000), workDaysPerWeek = SituationDefaults.WORK_DAYS), "k4")
        assertTrue(backend.requests.last().body!!.contains("\"work_days_per_week\":5"))
    }

    @Test fun basicDashboardCarriesTheHistoryForTheChart() = runTest {
        val dashboard = fixture(PlanTier.BASIC).second.basicDashboard()
        assertEquals(6, dashboard.monthlyHistory.size)
        assertTrue(dashboard.monthlyHistory.any { it.income.signum() > 0 })
    }
}
