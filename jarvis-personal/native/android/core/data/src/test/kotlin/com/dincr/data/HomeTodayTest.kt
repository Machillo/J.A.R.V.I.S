package com.dincr.data

import java.math.BigDecimal
import java.time.LocalDate
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Hoy's four blocks (UX-6): presentation rules per plan, synthetic data. The Swift twin is
 * `HomeTodayTests` — the same cases with the same expectations.
 */
class HomeTodayTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false; encodeDefaults = true }
    private val today = LocalDate.of(2026, 10, 10)
    private fun n(value: Int) = BigDecimal(value)
    private fun same(expected: Int, actual: BigDecimal?) = assertEquals(0, actual?.compareTo(n(expected)))

    private fun free(income: Int = 500000, expenses: Int = 120000) = json.decodeFromString<FreeDashboard>(
        """{"month":"2026-10","income":$income,"expenses":$expenses,"debt_paid":0,"balance":${income - expenses},"available_after_commitments":${income - expenses},"categories":[{"category":"Comida","amount":80000}],"monthly_history":[]}""")
    private fun basic(income: Int = 500000) = json.decodeFromString<BasicDashboard>(
        """{"month":"2026-10","income":$income,"expenses":120000,"debt_paid":0,"balance":${income - 120000}}""")
    private fun debts(raw: String = """[{"id":1,"name":"Tarjeta sintética","remaining_amount":300000,"monthly_payment":45000,"payment_day":15}]""") =
        json.decodeFromString<List<Debt>>(raw)
    private val budget = """{"items":[{"category":"Comida","monthly_limit":150000,"spent":90000},{"category":"Transporte","monthly_limit":50000,"spent":10000}],"total_budgeted":200000,"is_proposal":false}"""
    private val calendar = """{"period":"2026-10","events":[{"date":"2026-10-05","kind":"debt","name":"Pasado","amount":30000},{"date":"2026-10-12","kind":"expense","name":"Internet","amount":25000},{"date":"2026-10-20","kind":"debt","name":"Tarjeta","amount":45000},{"date":"2026-10-25","kind":"goal","name":"Meta","amount":10000},{"date":"2026-10-28","kind":"income","name":"Ingreso esperado","amount":0}]}"""
    private fun center(raw: String) = json.decodeFromString<CommandCenter>(raw)

    // Free

    @Test fun freeHasTheFourBlocksWithRealFactsAndNoIntelligence() {
        val home = HomeToday.free(free(), emptyList(), today)
        assertEquals(HomeToday.Tier.FREE, home.tier)
        assertEquals(HomeStatus.Headline.MONTH_RESULT, home.status.headline)  // never safe to spend
        same(380000, home.status.amount); assertTrue(home.status.missing.isEmpty())
        same(500000, home.status.income); same(120000, home.status.expenses)
        assertNull(home.status.budget); assertNull(home.status.pending); assertNull(home.status.lowestBalance)
        assertNull(home.attention)                                           // no source: left out, nothing invented
        assertEquals(HomeNext.Kind.REGISTER_MOVEMENT, home.next.kind)
        assertEquals(HomeShortcut.entries, home.shortcuts)
    }

    @Test fun freeWithoutRegisteredIncomeIsUnknownNeverZero() {
        val home = HomeToday.free(free(income = 0), emptyList(), today)
        assertNull(home.status.amount); assertNull(home.status.result); assertNull(home.status.income)
        assertEquals(listOf(HomeInput.INCOME), home.status.missing)
        assertEquals(HomeDestination.REGISTER_INCOME, home.status.missing.first().destination)  // the real flow, never an estimate
        assertEquals(HomeNext.Kind.REGISTER_INCOME, home.next.kind)
    }

    @Test fun freeNextIsTheNextKnownDebtPayment() {
        val next = HomeToday.free(free(), debts(), today).next
        assertEquals(HomeNext.Kind.COMMITMENT, next.kind)
        assertEquals("Tarjeta sintética", next.title); assertEquals("2026-10-15", next.date); same(45000, next.amount)
        assertEquals(HomeDestination.DEBTS, next.destination)
    }

    @Test fun aPaymentDayAlreadyPassedMovesToNextMonthAndUnknownAmountsStayUnknown() {
        val next = HomeToday.free(free(), debts("""[{"id":2,"name":"Préstamo","remaining_amount":900000,"monthly_payment":0,"payment_day":3},{"id":3,"name":"Pagada","remaining_amount":0,"monthly_payment":10000,"payment_day":11}]"""), today).next
        assertEquals("2026-11-03", next.date)
        assertNull(next.amount)  // a stored 0 is an unknown payment (#326), not ₡0
        assertEquals("Préstamo", next.title)
    }

    // Basic

    @Test fun basicAddsItsOwnBudgetAndPendingCommitmentsWithoutVipIntelligence() {
        val home = HomeToday.basic(basic(), json.decodeFromString(budget), json.decodeFromString(calendar), null, emptyList(), today)
        assertEquals(HomeToday.Tier.BASIC, home.tier); assertEquals(HomeStatus.Headline.MONTH_RESULT, home.status.headline); assertNull(home.attention)
        same(100000, home.status.budget?.remaining)
        assertEquals(0.5, home.status.budget?.used?.fraction!!, 0.0)
        assertEquals(2, home.status.pending?.count); same(70000, home.status.pending?.total)  // from today on, payments only
        assertNull(home.status.lowestBalance)
    }

    @Test fun dincrsBudgetProposalIsNotTheUsersBudget() {
        val proposal = json.decodeFromString<Budget>("""{"items":[{"category":"Comida","monthly_limit":100000,"spent":0}],"total_budgeted":100000,"is_proposal":true}""")
        assertNull(HomeToday.basic(basic(), proposal, null, null, emptyList(), today).status.budget)
    }

    @Test fun aPendingPaymentWithoutAKnownAmountKeepsTheTotalUnknown() {
        val cal = json.decodeFromString<FinancialCalendar>("""{"events":[{"date":"2026-10-20","kind":"debt","name":"Tarjeta","amount":0},{"date":"2026-10-21","kind":"expense","name":"Luz","amount":15000}]}""")
        assertEquals(HomeStatus.Pending(2, null), HomeToday.basic(basic(), null, cal, null, emptyList(), today).status.pending)
    }

    @Test fun basicNextComesFromStrategyBasic() {
        val plan = MonthPlan.of(json.decodeFromString<Strategy>("""{"status":"tight","strategic_margin":214000,"recommendation":"Destiná ₡100.000 a la tarjeta."}"""))
        val next = HomeToday.basic(basic(), null, null, plan, debts(), today).next
        assertEquals(HomeNext.Kind.RECOMMENDATION, next.kind); assertEquals(HomeDestination.MONTH_PLAN, next.destination)
        assertTrue(next.title?.isNotEmpty() == true)
        val missing = HomeToday.basic(basic(), null, null, MonthPlan.of(json.decodeFromString<Strategy>("""{"status":"needs_income"}""")), emptyList(), today).next
        assertEquals(HomeNext.Kind.NEEDS_INFORMATION, missing.kind)
        assertEquals(listOf(HomeInput.INCOME), missing.missing); assertEquals(HomeDestination.REGISTER_INCOME, missing.destination)
    }

    // VIP

    private val knownCenter = """{"safe_to_spend":{"amount":118000,"monthly_margin":214000,"next_45_days_minimum":96000,"missing":[]},
        "director":{"priority":"debt","headline":"Atacar Tarjeta","next_action":"Asigná ₡40,000 a esta prioridad.","missing":[]},
        "reports":{"current":{"month":"2026-10","income":600000,"expenses":200000,"debt_paid":40000,"balance":360000}},
        "roadmap":[{"order":1,"title":"Abonar a Tarjeta","amount":40000},{"order":2,"title":"Invertir","amount":0}],
        "score":{"value":72,"label":"Estable"},"projections":[{"months":6,"net_worth":1000000}],
        "alerts":[{"severity":"medium","title":"A1"},{"severity":"high","title":"A2"},{"severity":"critical","title":"A3"},{"severity":"medium","title":"A4"}],
        "automation":{"review":0}}"""

    @Test fun vipShowsSafeToSpendAndOneRecommendationWithAttention() {
        val home = HomeToday.vip(center(knownCenter), null, null, emptyList(), today = today)
        assertEquals(HomeToday.Tier.VIP, home.tier); assertEquals(HomeStatus.Headline.SAFE_TO_SPEND, home.status.headline)
        same(118000, home.status.amount); assertTrue(home.status.missing.isEmpty()); same(96000, home.status.lowestBalance)
        same(600000, home.status.income); same(360000, home.status.result)
        assertEquals(HomeNext.Kind.RECOMMENDATION, home.next.kind); assertEquals("Atacar Tarjeta", home.next.title)
        assertEquals(HomeDestination.MONTH_PLAN, home.next.destination)
        // Para atender (#325): at most three, the rest behind "Ver todas".
        assertEquals(3, home.attention?.visible?.size); assertTrue(home.attention?.showsSeeAll == true)
        assertEquals("critical", home.attention?.visible?.first()?.severity)
    }

    @Test fun vipUnknownSafeToSpendIsUnknownWithWhatIsMissing() {
        val home = HomeToday.vip(center("""{"safe_to_spend":{"amount":null,"monthly_margin":null,"next_45_days_minimum":250000,"missing":["income","debt_payments","future_code"]},
            "director":{"priority":"incomplete","headline":"Aún no tengo suficiente información para recomendarte una prioridad","missing":["income","debt_payments"]},
            "roadmap":[],"alerts":[]}"""), null, null, emptyList(), today = today)
        assertNull(home.status.amount)                                                     // never ₡0
        assertEquals(listOf(HomeInput.INCOME, HomeInput.DEBT_PAYMENTS), home.status.missing)  // unknown codes are skipped
        assertEquals(HomeNext.Kind.NEEDS_INFORMATION, home.next.kind)                      // no invented priority
        assertEquals(listOf(HomeInput.INCOME, HomeInput.DEBT_PAYMENTS), home.next.missing)
        assertEquals(HomeDestination.REGISTER_INCOME, home.next.destination)
        assertTrue(home.attention?.isEmpty == true)
    }

    @Test fun vipAddsBasicsCompactFacts() {
        val home = HomeToday.vip(center(knownCenter), json.decodeFromString(budget), json.decodeFromString(calendar), emptyList(), today = today)
        same(100000, home.status.budget?.remaining); assertEquals(2, home.status.pending?.count)
    }

    // Review cases (unknown ≠ 0, adding up, invalid data)

    @Test fun basicWithoutRegisteredIncomeIsUnknownToo() {
        val home = HomeToday.basic(basic(income = 0), null, null, null, emptyList(), today)
        assertNull(home.status.amount); assertEquals(listOf(HomeInput.INCOME), home.status.missing)
        assertEquals(HomeNext.Kind.REGISTER_INCOME, home.next.kind)
    }

    @Test fun nothingRegisteredIsNotAZero() {
        val home = HomeToday.free(free(income = 0, expenses = 0), emptyList(), today)
        assertNull(home.status.income); assertNull(home.status.expenses)  // "Sin registrar", never ₡0
    }

    @Test fun theResultAddsUpWithWhatWasPaidToDebts() {
        val dashboard = json.decodeFromString<FreeDashboard>("""{"month":"2026-10","income":500000,"expenses":120000,"debt_paid":40000,"balance":340000,"categories":[],"monthly_history":[]}""")
        val home = HomeToday.free(dashboard, debts(), today)
        same(340000, home.status.result); same(40000, home.status.debtPaid)
        same(300000, home.status.debtBalance)  // the debts' own balances
    }

    @Test fun vipWithoutTheMonthsLedgerHasNoInventedFacts() {
        val home = HomeToday.vip(center("""{"safe_to_spend":{"amount":118000,"monthly_margin":null,"missing":[]},"alerts":[]}"""), null, null, null, today = today)
        assertNull(home.status.income); assertNull(home.status.expenses); assertNull(home.status.result)
        assertNull(home.status.margin); assertNull(home.status.debtBalance)
        same(214000, HomeToday.vip(center(knownCenter), null, null, emptyList(), today = today).status.margin)
    }

    @Test fun aBudgetWithoutTheProposalFlagOrASpentValueIsNotShown() {
        val noFlag = json.decodeFromString<Budget>("""{"items":[{"category":"Comida","monthly_limit":100000,"spent":0}],"total_budgeted":100000}""")
        val noSpent = json.decodeFromString<Budget>("""{"items":[{"category":"Comida","monthly_limit":100000}],"total_budgeted":100000,"is_proposal":false}""")
        assertNull(HomeToday.budgetLeft(noFlag)); assertNull(HomeToday.budgetLeft(noSpent))
    }

    @Test fun noKnownPaymentsIsZeroKnownNotNone() {
        assertEquals(HomeStatus.Pending(0, BigDecimal.ZERO), HomeToday.pending(json.decodeFromString("""{"events":[]}"""), today))
        assertNull(HomeToday.pending(null, today))
    }

    @Test fun anInvalidPaymentDayGivesNoDate() {
        val home = HomeToday.free(free(), debts("""[{"id":4,"name":"Rara","remaining_amount":100000,"monthly_payment":10000,"payment_day":0},{"id":5,"name":"Otra","remaining_amount":100000,"monthly_payment":10000,"payment_day":40}]"""), today)
        assertEquals(HomeNext.Kind.REGISTER_MOVEMENT, home.next.kind)  // skipped, never a crash or a wrong date
    }

    // General

    @Test fun missingInputsLeadToTheRealFlows() {
        assertEquals(HomeDestination.REGISTER_INCOME, HomeInput.INCOME.destination)
        assertEquals(HomeDestination.DEBTS, HomeInput.DEBT_PAYMENTS.destination)
        assertEquals(HomeDestination.INCOME_BASE, HomeInput.ESSENTIAL_EXPENSES.destination)  // UX-7: Plan → Ingresos y base
        assertTrue(listOf(HomeInput.SAVINGS, HomeInput.EMERGENCY_FUND_TARGET).all { it.destination == HomeDestination.GOALS })  // UX-7: savings in Ahorros
        assertEquals(listOf(HomeInput.ESSENTIAL_EXPENSES, HomeInput.SAVINGS, HomeInput.EMERGENCY_FUND_TARGET),
            HomeInput.codes(listOf("essential_expenses", "savings", "emergency_fund_target")))
    }

    @Test fun quickAccessIsTheSameForEveryPlan() {
        val all = listOf(HomeToday.free(free(), emptyList(), today).shortcuts,
            HomeToday.basic(basic(), null, null, null, emptyList(), today).shortcuts,
            HomeToday.vip(center(knownCenter), null, null, emptyList(), today = today).shortcuts)
        val expected = listOf(HomeShortcut.REGISTER_MOVEMENT, HomeShortcut.MOVEMENTS, HomeShortcut.DEBTS, HomeShortcut.GOALS)
        assertTrue(all.all { it == expected })
    }

    @Test fun destinationsAreTheSameScreensAsIos() {
        // Routes registered in MainScaffold; the movement editor (income or any movement) is a sheet.
        assertEquals(mapOf("MOVEMENTS" to "movements", "DEBTS" to "debts", "GOALS" to "goals", "INCOME_BASE" to "incomeBase", "MONTH_PLAN" to "strategy"),
            HomeDestination.entries.filter { it.route != null }.associate { it.name to it.route })
    }
}
