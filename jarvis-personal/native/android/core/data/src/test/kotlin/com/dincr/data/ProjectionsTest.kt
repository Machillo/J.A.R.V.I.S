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
}
