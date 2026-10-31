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
 * FA-1 — Análisis financiero reads the user's own twelve months in plain words: the average of the
 * complete months that recorded both income and spending, "X de cada 100", and the categories already
 * above normal this month. Unknown is never 0. The Swift twin is `FinancialAnalysisTests`. Synthetic data.
 */
class FinancialAnalysisTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false }
    private val colones = MoneyFormat("CRC", MoneyFormat.Separators.DOT_COMMA)
    private val es = AppLanguage.SPANISH
    private fun analysis(text: String) = json.decodeFromString<FinancialAnalysis>(text)

    private val year = """{"months":[
      {"period":"2026-07","income":0,"expenses":0,"debt_paid":0,"saved":0,"partial":false},
      {"period":"2026-08","income":800000,"expenses":0,"debt_paid":0,"saved":0,"partial":false},
      {"period":"2026-09","income":1000000,"expenses":600000,"debt_paid":100000,"saved":50000,"partial":false},
      {"period":"2026-10","income":1000000,"expenses":700000,"debt_paid":100000,"saved":150000,"partial":false},
      {"period":"2026-11","income":1000000,"expenses":50000,"debt_paid":0,"saved":0,"partial":true}],
     "categories":[{"category":"Comida","current":90000,"average":60000},{"category":"Ropa","current":40000,"average":0},
                   {"category":"Vivienda","current":0,"average":300000},{"category":"Salud","current":20000,"average":20000}]}"""

    private fun month(period: String, income: Int, expenses: Int, debt: Int = 0, partial: Boolean = false) =
        FinancialAnalysis.Month(period, BigDecimal(income), BigDecimal(expenses), BigDecimal(debt), BigDecimal.ZERO, partial)

    @Test fun aNormalMonthAveragesOnlyCompleteMonthsWithIncomeAndSpending() {
        val normal = FinancialReading.normal(analysis(year))!!
        // July recorded nothing, August no spending and November is not over: only September and October.
        assertEquals(2, normal.months)
        assertEquals(0, normal.income.compareTo(BigDecimal(1_000_000)))
        assertEquals(0, normal.expenses.compareTo(BigDecimal(650_000)))
        assertEquals(0, normal.debtPaid.compareTo(BigDecimal(100_000)))
        assertEquals(0, normal.saved.compareTo(BigDecimal(100_000)))
        assertEquals(0, normal.left.compareTo(BigDecimal(250_000)))
    }

    @Test fun theSentencesSayItInPlainWords() {
        val normal = FinancialReading.normal(analysis(year))!!
        assertEquals("En un mes normal te sobran ₡250.000.", FinancialReading.leftSentence(normal, colones, es))
        assertEquals("Entra ₡1.000.000, gastás ₡650.000 y pagás ₡100.000 de deudas. Es el promedio de tus últimos 2 meses completos.",
            FinancialReading.leftExplanation(normal, colones, es))
        assertEquals("Guardás 10 de cada 100 que entran.", FinancialReading.savedSentence(normal, es))
        assertEquals("De cada 100 que entran, 10 se van a pagar deudas.", FinancialReading.debtSentence(normal, es))
    }

    @Test fun spendingMoreThanWhatComesInIsSaidAsSuch() {
        val normal = FinancialReading.normal(FinancialAnalysis(listOf(month("2026-09", 500_000, 600_000, 50_000))))!!
        assertEquals("En un mes normal sale ₡150.000 más de lo que entra.", FinancialReading.leftSentence(normal, colones, es))
        assertTrue(FinancialReading.leftExplanation(normal, colones, es).endsWith("Es el promedio de tu último mes completo."))
        assertEquals("Todavía no estás guardando parte de lo que entra.", FinancialReading.savedSentence(normal, es))
    }

    @Test fun withoutAComparableMonthThereIsNoNormalMonth() {
        val onlyIncome = FinancialAnalysis(listOf(month("2026-10", 900_000, 0), month("2026-11", 900_000, 300_000, partial = true)))
        assertNull("the month in course is never a normal month", FinancialReading.normal(onlyIncome))
        assertNull("no income: no share", FinancialReading.debtSentence(FinancialReading.Normal(1, BigDecimal.ZERO, BigDecimal.ONE, BigDecimal.ONE, BigDecimal.ZERO), es))
    }

    @Test fun noDebtPaymentsNoDebtSentence() {
        assertNull(FinancialReading.debtSentence(FinancialReading.Normal(1, BigDecimal(100), BigDecimal(50), BigDecimal.ZERO, BigDecimal.ZERO), es))
    }

    @Test fun onlyCategoriesAlreadyAboveNormalAreListedLargestFirst() {
        val rises = FinancialReading.rises(analysis(year))
        assertEquals("Vivienda is below (the month is not over) and Salud is the same", listOf("Ropa", "Comida"), rises.map { it.category })
        assertEquals("Comida: ₡90.000 este mes · normalmente ₡60.000", FinancialReading.riseLine(rises[1], colones, es))
        assertTrue(FinancialReading.canCompare(analysis(year)))
    }

    @Test fun withoutEarlierMonthsNothingIsCompared() {
        val first = analysis("""{"months":[],"categories":[{"category":"Comida","current":90000,"average":null}]}""")
        assertTrue(FinancialReading.rises(first).isEmpty())
        assertFalse(FinancialReading.canCompare(first))
    }

    @Test fun theBarsSkipMonthsWithNothingRecorded() {
        assertEquals(listOf("2026-08", "2026-09", "2026-10", "2026-11"), FinancialReading.chartMonths(analysis(year)).map { it.month })
    }

    private fun api(plan: PlanTier, role: FakeBackend.Role = FakeBackend.Role.USER) =
        DincrApi(ApiClient("https://fixtures.invalid", { "t" }, FakeBackend(FakeBackend.Scenario.POPULATED, plan, role = role), AppLanguage.SPANISH, backoff = {}))

    @Test fun theFixtureGivesVipAndTheOwnerAComparableYearAndRefusesTheRest() = runTest {
        for (role in listOf(FakeBackend.Role.USER, FakeBackend.Role.OWNER)) {
            val analysis = api(PlanTier.VIP, role).financialAnalysis()
            assertEquals(12, analysis.months.size)
            assertEquals(listOf(true), analysis.months.filter { it.partial }.map { it.partial })
            assertEquals("Guardás 10 de cada 100 que entran.", FinancialReading.savedSentence(FinancialReading.normal(analysis)!!, es))
            assertEquals(listOf("Comida"), FinancialReading.rises(analysis).map { it.category })
        }
        for (plan in listOf(PlanTier.FREE, PlanTier.BASIC)) {
            assertTrue(plan.name, runCatching { api(plan).financialAnalysis() }.isFailure)
        }
    }
}
