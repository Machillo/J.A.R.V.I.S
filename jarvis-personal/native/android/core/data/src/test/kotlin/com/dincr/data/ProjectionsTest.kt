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
 * UX-14 (UNKNOWN ≠ 0): Patrimonio → Proyecciones shows figures only when the command center says the
 * projection is complete; otherwise it names what is missing and where to give it. Hoy gets no
 * projection item. The Swift twin is `ProjectionsTests`. Synthetic data.
 */
class ProjectionsTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false; encodeDefaults = true }
    private fun center(text: String) = json.decodeFromString<CommandCenter>(text)

    private val complete = """{"projections":[{"months":12,"cash":6900000,"debt":0,"net_worth":6900000,"confidence":"medium"},
        {"months":1,"cash":850000,"debt":450000,"net_worth":400000,"confidence":"medium"},
        {"months":3,"cash":1950000,"debt":350000,"net_worth":1600000,"confidence":"medium"},
        {"months":6,"cash":3600000,"debt":200000,"net_worth":3400000,"confidence":"medium"}],
        "projection_status":{"complete":true,"missing":[]},"alerts":[]}"""

    @Test fun aCompleteProjectionKeepsTheFourHorizonsInOrder() {
        val state = Projections.state(center(complete)) as Projections.Complete
        assertEquals(listOf(1, 3, 6, 12), state.points.map { it.months })
        assertEquals(0, state.points.first().cash?.compareTo(BigDecimal(850000)))
        assertFalse(state.lowConfidence)
    }

    @Test fun lowConfidenceIsSaidTheSameWayOnBothPlatforms() {
        val state = Projections.state(center(complete.replace("\"confidence\":\"medium\"", "\"confidence\":\"low\""))) as Projections.Complete
        assertTrue(state.lowConfidence)
    }

    @Test fun anIncompleteProjectionHasNoFigureAndNamesEveryMissingInput() {
        val state = Projections.state(center("""{"projections":[],"projection_status":{"complete":false,"missing":["income","essential_expenses","debt_payments","savings"]}}"""))
        assertEquals(Projections.Incomplete(listOf(ProjectionInput.INCOME, ProjectionInput.ESSENTIAL_EXPENSES, ProjectionInput.DEBT_PAYMENTS, ProjectionInput.SAVINGS)), state)
    }

    @Test fun eachUnknownInputAloneBlocksTheProjection() {
        for (input in ProjectionInput.entries) {
            val state = Projections.state(center("""{"projections":[],"projection_status":{"complete":false,"missing":["${input.code}"]}}"""))
            assertEquals(input.code, Projections.Incomplete(listOf(input)), state)
        }
    }

    @Test fun eachInputOpensTheExistingScreenThatTakesIt() {
        assertEquals("incomeBase", ProjectionInput.INCOME.destination.route)
        assertEquals("incomeBase", ProjectionInput.ESSENTIAL_EXPENSES.destination.route)
        assertEquals("declaredSavings", ProjectionInput.SAVINGS.destination.route)
        assertEquals("debts", ProjectionInput.DEBT_PAYMENTS.destination.route)
    }

    @Test fun anAnswerWithoutStatusOrPointsIsNeverReadAsComplete() {
        // A backend without `projection_status`: its points are not trusted as complete.
        assertEquals(Projections.Incomplete(emptyList()), Projections.state(center("""{"projections":[{"months":1,"cash":0,"debt":0,"net_worth":0,"confidence":"low"}]}""")))
        // Complete but no points: nothing to show as a figure.
        assertEquals(Projections.Incomplete(emptyList()), Projections.state(center("""{"projections":[],"projection_status":{"complete":true,"missing":[]}}""")))
        // Codes this app doesn't know are skipped, never guessed.
        assertEquals(Projections.Incomplete(listOf(ProjectionInput.SAVINGS)), Projections.state(center("""{"projection_status":{"complete":false,"missing":["future_code","savings"]}}""")))
    }

    @Test fun hoyGetsNoProjectionItem() {
        // UX-14 D: no "material change" yet, so the projections never reach Para atender.
        assertTrue(AttentionList.today(center(complete)).isEmpty)
        assertTrue(AttentionList.today(center("""{"projections":[],"projection_status":{"complete":false,"missing":["savings"]},"alerts":[]}""")).isEmpty)
    }

    @Test fun theFixtureMatchesTheContract() = runTest {
        fun api(scenario: FakeBackend.Scenario) = DincrApi(ApiClient("https://fixtures.invalid", { "t" }, FakeBackend(scenario, PlanTier.VIP), AppLanguage.SPANISH, backoff = {}))
        val populated = Projections.state(api(FakeBackend.Scenario.POPULATED).commandCenter()) as Projections.Complete
        assertEquals(listOf(1, 3, 6, 12), populated.points.map { it.months })
        val empty = api(FakeBackend.Scenario.EMPTY).commandCenter()
        assertEquals(Projections.Incomplete(listOf(ProjectionInput.INCOME, ProjectionInput.ESSENTIAL_EXPENSES, ProjectionInput.SAVINGS)), Projections.state(empty))
        assertNull(empty.debtPlanner?.recommended)
    }

    // UX-14 / I09 — the charts.

    @Test fun theChartsUseExactlyTheProjectionPointsInOrder() {
        val series = ProjectionSeries.of(Projections.state(center(complete)), AppLanguage.SPANISH)
        assertEquals(listOf(ProjectionSeries.Kind.CASH, ProjectionSeries.Kind.DEBT, ProjectionSeries.Kind.NET_WORTH), series.map { it.kind })
        val cash = series.first { it.kind == ProjectionSeries.Kind.CASH }.series.points
        assertEquals(listOf("01", "03", "06", "12"), cash.map { it.period })
        assertEquals(listOf("1 mes", "3 meses", "6 meses", "12 meses"), cash.map { it.label })
        assertEquals(listOf(850000, 1950000, 3600000, 6900000), cash.map { it.value!!.toInt() })
        assertEquals(listOf(450000, 350000, 200000, 0), series.first { it.kind == ProjectionSeries.Kind.DEBT }.series.points.map { it.value!!.toInt() })
        assertEquals(listOf(400000, 1600000, 3400000, 6900000), series.first { it.kind == ProjectionSeries.Kind.NET_WORTH }.series.points.map { it.value!!.toInt() })
    }

    @Test fun anIncompleteProjectionHasNoChart() {
        assertTrue(ProjectionSeries.of(Projections.state(center("""{"projections":[],"projection_status":{"complete":false,"missing":["savings"]}}"""))).isEmpty())
        // An older answer without status is not complete either.
        assertTrue(ProjectionSeries.of(Projections.state(center("""{"projections":[{"months":1,"cash":1,"debt":1,"net_worth":0}]}"""))).isEmpty())
    }

    @Test fun aSeriesWithAMissingValueIsNotDrawnAndNothingIsFilledIn() {
        val json = complete.replace("""{"months":6,"cash":3600000,""", """{"months":6,"cash":null,""")
        val series = ProjectionSeries.of(Projections.state(center(json)))
        assertEquals("never a cash of 0 at 6 months", listOf(ProjectionSeries.Kind.DEBT, ProjectionSeries.Kind.NET_WORTH), series.map { it.kind })
    }

    @Test fun theChartsDoNotChangeTheLowConfidenceLine() {
        val json = complete.replace("\"confidence\":\"medium\"", "\"confidence\":\"low\"")
        val state = Projections.state(center(json)) as Projections.Complete
        assertTrue(state.lowConfidence)
        assertEquals(3, ProjectionSeries.of(state).size)
    }
}
