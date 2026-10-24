package com.dincr.data

import java.math.BigDecimal
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Owner information clarity: the Owner ledger's fields reach the app (backend owner_ledger), one
 * wording per concept is shared by the screens that show it, and nothing changes for other plans.
 */
class OwnerReadingTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false }

    /** What `/free/monthly-summary` answers for the verified Owner (backend free_service + owner_ledger). */
    private val ownerSummary = """
        {"period":"2026-10","income":450000.0,"expenses":125000.5,"gross_expenses":140000.5,"refunds":15000.0,
         "unmatched_refunds":0.0,"debt_paid":80000.0,"other_inflows":60000.0,"loan_received":50000.0,
         "receivable_payments":10000.0,"asset_sale_proceeds":0.0,"balance":244999.5,"cash_flow":304999.5,
         "unclassified_count":3,"payroll_accrued":{"overtime_gross":42000.0,"vgh_gross":-5000.0,"bonuses_gross":0.0,"total_gross":37000.0},
         "pending_mail_count":2,"complete":false,"incomplete_reasons":["pending_mail_review","unclassified_movements"],
         "categories":[],"savings":0,"goals":{"current":0,"target":0,"progress":0}}
    """.trimIndent()

    @Test fun theOwnerMonthCarriesTheLedgersReading() {
        val s = json.decodeFromString(MonthlySummary.serializer(), ownerSummary)
        assertTrue(s.isOwnerLedger)
        assertEquals(false, s.complete)
        assertEquals(listOf("pending_mail_review", "unclassified_movements"), s.incompleteReasons)
        assertEquals(0, BigDecimal("15000").compareTo(s.refunds))
        assertEquals(0, BigDecimal("50000").compareTo(s.loanReceived))
        assertEquals(0, BigDecimal("37000").compareTo(s.payrollAccrued?.totalGross))
        assertEquals(0, BigDecimal("-5000").compareTo(s.payrollAccrued?.vghGross))
        // The figures stay the backend's: the result is income − spending − debt payments.
        assertEquals(0, s.income!!.subtract(s.expenses).subtract(s.debtPaid).compareTo(s.balance))
    }

    @Test fun anotherPlansMonthIsNotTheOwnerLedger() {
        val s = json.decodeFromString(MonthlySummary.serializer(), """{"period":"2026-10","income":100,"expenses":50,"debt_paid":0,"balance":50}""")
        assertFalse(s.isOwnerLedger)
        assertTrue(s.incompleteReasons.isEmpty())
        assertNull(s.payrollAccrued)
    }

    @Test fun everyIncompleteReasonReadsInPlainWords() {
        val pending = OwnerReading.incompleteReason("pending_mail_review", 2, null, AppLanguage.SPANISH)
        assertTrue(pending, pending.contains("2 avisos de correo"))
        val unclassified = OwnerReading.incompleteReason("unclassified_movements", null, 3, AppLanguage.SPANISH)
        assertTrue(unclassified, unclassified.contains("3 movimientos sin clasificar") && unclassified.contains("no suman"))
        assertTrue(OwnerReading.incompleteReason("payroll_without_deposit", null, null, AppLanguage.SPANISH).contains("sin el depósito"))
        assertTrue(OwnerReading.incompleteReason("a_new_code", null, null, AppLanguage.SPANISH).contains("Falta información"))
        assertTrue(OwnerReading.incompleteReason("pending_mail_review", null, null, AppLanguage.ENGLISH).startsWith("There are some"))
    }

    @Test fun theIncompleteMonthsOfAFlowAreListed() {
        val flow = listOf(
            TransactionAnalysis.FlowMonth("2026-08", complete = true),
            TransactionAnalysis.FlowMonth("2026-09", complete = false),
            TransactionAnalysis.FlowMonth("2026-10", complete = null),  // not the Owner ledger: unknown, never listed
            TransactionAnalysis.FlowMonth("2026-11", complete = false),
        )
        assertEquals(listOf("2026-09", "2026-11"), OwnerReading.incompleteMonths(flow))
    }

    @Test fun theOwnersFormulaIncomeIsWhatIsStillToCome() {
        val owner = DirectorStrategy(scope = "owner")
        val users = DirectorStrategy(scope = "users")
        assertEquals("Ingresos por recibir en el ciclo", OwnerReading.formulaLabel("income", owner, AppLanguage.SPANISH))
        assertEquals(Distribution.formulaLabel("income", AppLanguage.SPANISH), OwnerReading.formulaLabel("income", users, AppLanguage.SPANISH))
        // Keys with one meaning keep the shared label for both.
        assertEquals(Distribution.formulaLabel("surplus", AppLanguage.SPANISH), OwnerReading.formulaLabel("surplus", owner, AppLanguage.SPANISH))
    }

    @Test fun theOwnerStrategySaysWhichDatesItCovers() {
        val s = json.decodeFromString(DirectorStrategy.serializer(),
            """{"scope":"owner","cycle_period":{"start":"2026-10-05","end":"2026-11-05"},"card_statement_period":{"start":"2026-09-21","end":"2026-10-21"}}""")
        assertEquals(DatePeriod("2026-10-05", "2026-11-05"), s.cyclePeriod)
        assertEquals(DatePeriod("2026-09-21", "2026-10-21"), s.cardStatementPeriod)
        assertNull(json.decodeFromString(DirectorStrategy.serializer(), """{"scope":"users"}""").cyclePeriod)
    }

    @Test fun aMonthWithNothingPendingSaysWhetherItHasDataAndWhetherItIsOver() {
        fun month(period: String, income: String) =
            json.decodeFromString(MonthlySummary.serializer(), """{"period":"$period","income":$income,"expenses":0,"debt_paid":0,"complete":true}""")
        // No movements is unknown, never shown as a verified, complete month of zeros.
        assertEquals(OwnerReading.MonthState.NO_MOVEMENTS, OwnerReading.monthState(month("2026-08", "0"), "2026-10"))
        assertEquals(OwnerReading.MonthState.IN_PROGRESS, OwnerReading.monthState(month("2026-10", "100"), "2026-10"))
        assertEquals(OwnerReading.MonthState.CLOSED, OwnerReading.monthState(month("2026-09", "100"), "2026-10"))
    }

    @Test fun grossPayrollShowsWhenItsPartsCancelOut() {
        assertTrue(OwnerReading.hasPayroll(PayrollAccrued(overtimeGross = BigDecimal(5000), vghGross = BigDecimal(-5000), totalGross = BigDecimal.ZERO)))
        assertFalse(OwnerReading.hasPayroll(PayrollAccrued(totalGross = BigDecimal.ZERO)))
    }

    private fun fixture(plan: PlanTier, role: FakeBackend.Role) =
        DincrApi(ApiClient("https://fixtures.invalid", { "t" }, FakeBackend(FakeBackend.Scenario.POPULATED, plan, role = role), AppLanguage.SPANISH, backoff = {}))

    @Test fun onlyTheOwnersSummaryHasTheLedgerInTheFixtures() = runTest {
        val month = java.time.YearMonth.now().toString()
        assertTrue(fixture(PlanTier.VIP, FakeBackend.Role.OWNER).monthlySummary(month).isOwnerLedger)
        assertFalse(fixture(PlanTier.VIP, FakeBackend.Role.USER).monthlySummary(month).isOwnerLedger)
    }
}
