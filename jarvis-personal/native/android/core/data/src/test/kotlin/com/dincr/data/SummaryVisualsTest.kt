package com.dincr.data

import java.math.BigDecimal
import java.time.LocalDate
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * E04 / E05 — Análisis → Resumen del mes draws the month's own summary: income vs expenses as bars
 * with the exact amounts, expenses by category as a donut with shares computed from those amounts.
 * Unknown is never 0, nothing is made up. The Swift twin is `SummaryVisualsTests`. Synthetic data.
 */
class SummaryVisualsTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false; encodeDefaults = true }
    private fun summary(text: String) = json.decodeFromString<MonthlySummary>(text)

    private val month = """{"period":"2026-10","income":850000,"expenses":400000,"debt_paid":0,"balance":450000,
        "categories":[{"category":"Comida","amount":200000},{"category":"Vivienda","amount":150000},{"category":"Transporte","amount":50000}]}"""

    @Test fun theBarsAreTheMonthsIncomeAndExpensesExactly() {
        val flow = SummaryVisuals.flow(summary(month))
        assertEquals(SummaryVisuals.Flow.Bars("2026-10", BigDecimal(850000), BigDecimal(400000)), flow)
        assertNull(SummaryVisuals.flowNotice(flow))
    }

    @Test fun anUnknownIncomeOrExpenseDrawsNoBars() {
        listOf("""{"period":"2026-10","expenses":400000}""", """{"period":"2026-10","income":850000}""", """{"period":"2026-10","income":null,"expenses":null}""").forEach {
            assertEquals(it, SummaryVisuals.Flow.Incomplete, SummaryVisuals.flow(summary(it)))
        }
        assertEquals("Faltan los ingresos o los gastos de este mes, así que no los comparamos.",
            SummaryVisuals.flowNotice(SummaryVisuals.Flow.Incomplete, AppLanguage.SPANISH))
    }

    @Test fun aMonthWithNothingRecordedIsEmptyButOneSideAtZeroIsStillCompared() {
        assertEquals(SummaryVisuals.Flow.Empty, SummaryVisuals.flow(summary("""{"period":"2026-10","income":0,"expenses":0}""")))
        assertEquals("Todavía no hay ingresos ni gastos registrados en este mes.", SummaryVisuals.flowNotice(SummaryVisuals.Flow.Empty, AppLanguage.SPANISH))
        assertEquals(SummaryVisuals.Flow.Bars("2026-10", BigDecimal.ZERO, BigDecimal(120000)),
            SummaryVisuals.flow(summary("""{"period":"2026-10","income":0,"expenses":120000}""")))
    }

    @Test fun theCategoriesAndTheirSharesComeFromTheAmounts() {
        val donut = SummaryVisuals.categories(summary(month), AppLanguage.SPANISH)
        assertEquals(Composition.Status.COMPLETE, donut.status)
        assertEquals("the backend's order, largest first", listOf("Comida", "Vivienda", "Transporte"), donut.segments.map { it.label })
        assertEquals(listOf(200000, 150000, 50000), donut.segments.map { it.value.toInt() })
        assertEquals(listOf(0.5, 0.375, 0.125), donut.segments.map { it.share })
    }

    @Test fun aCategoryWithoutAnAmountKeepsTheDonutUndrawnAndIsNotZero() {
        val donut = SummaryVisuals.categories(summary("""{"period":"2026-10","income":850000,"expenses":400000,
            "categories":[{"category":"Comida","amount":200000},{"category":"Salud","amount":null}]}"""), AppLanguage.SPANISH)
        assertEquals(Composition.Status.PARTIAL, donut.status)
        assertFalse(donut.isDrawable)
        assertEquals(listOf<Double?>(null), donut.segments.map { it.share })
        assertEquals(listOf("Salud"), donut.unknown.map { it.label })
        assertNull(donut.total)
    }

    @Test fun aCategoryWithoutANameIsSaidSoNotInvented() {
        val donut = SummaryVisuals.categories(summary("""{"period":"2026-10","categories":[{"category":null,"amount":1000},{"category":"","amount":500}]}"""), AppLanguage.SPANISH)
        assertEquals(listOf("Sin categoría", "Sin categoría"), donut.segments.map { it.label })
        assertEquals("two rows stay two parts", 2, donut.segments.map { it.id }.toSet().size)
    }

    @Test fun noCategoriesIsAnEmptyDonut() {
        assertEquals(Composition.Status.EMPTY, SummaryVisuals.categories(summary("""{"period":"2026-10","income":0,"expenses":0,"categories":[]}""")).status)
        assertEquals(Composition.Status.EMPTY, SummaryVisuals.categories(summary("""{"period":"2026-10"}""")).status)
    }

    private fun api(scenario: FakeBackend.Scenario) =
        DincrApi(ApiClient("https://fixtures.invalid", { "t" }, FakeBackend(scenario), AppLanguage.SPANISH, backoff = {}))

    @Test fun theFixtureMonthDrawsBothChartsFromItsOwnMovements() = runTest {
        val today = LocalDate.now().toString().take(7)
        val current = api(FakeBackend.Scenario.POPULATED).monthlySummary(today)
        val bars = SummaryVisuals.flow(current) as SummaryVisuals.Flow.Bars
        assertTrue(bars.income.compareTo(current.income) == 0 && bars.expenses.compareTo(current.expenses) == 0)
        val donut = SummaryVisuals.categories(current)
        assertEquals(Composition.Status.COMPLETE, donut.status)
        assertEquals("the parts are the month's expenses", 0, donut.segments.sumOf { it.value }.compareTo(current.expenses))

        val empty = api(FakeBackend.Scenario.EMPTY).monthlySummary(today)
        assertEquals(SummaryVisuals.Flow.Empty, SummaryVisuals.flow(empty))
        assertEquals(Composition.Status.EMPTY, SummaryVisuals.categories(empty).status)
    }
}
