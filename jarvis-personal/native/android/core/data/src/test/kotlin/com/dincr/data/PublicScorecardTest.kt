package com.dincr.data

import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * K-2: the monthly review never shows the financial-health score (no canonical calculation until
 * P3.7); every other scorecard line stays as the backend sends it. The Swift twin is
 * `PublicScorecardTests`. Synthetic data.
 */
class PublicScorecardTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false; encodeDefaults = true }
    private fun review(text: String) = json.decodeFromString<MonthlyReview>(text)

    @Test fun theHealthScoreLineIsLeftOutAndTheRestKeptInOrder() {
        val review = review("""{"status":"OK","scorecard":[{"key":"debt_total","label":"Deuda total","unit":"CRC","current":810000,"trend":"improved"},
            {"key":"health_score","label":"Salud financiera","unit":"points","current":72,"baseline":66,"delta":6,"trend":"improved"},
            {"key":"net_operational","label":"Flujo operativo","unit":"CRC","current":180000,"trend":"declined"}]}""")
        assertEquals(listOf("debt_total", "net_operational"), review.publicScorecard.map { it.key })
        assertTrue(review.publicScorecard.none { it.unit == "points" })
    }

    @Test fun anIncompleteHealthLineIsLeftOutToo() {
        assertTrue(review("""{"scorecard":[{"key":"health_score","label":"Salud financiera","unit":"points","trend":"unknown","explanation":"Falta la tasa"}]}""").publicScorecard.isEmpty())
    }

    @Test fun aReviewWithoutScorecardHasNoLines() {
        assertTrue(review("""{"status":"BASELINE"}""").publicScorecard.isEmpty())
    }

    @Test fun theFixtureSendsTheHealthLineAndTheAppDropsIt() = runTest {
        val api = DincrApi(ApiClient("https://fixtures.invalid", { "t" }, FakeBackend(FakeBackend.Scenario.POPULATED, PlanTier.VIP), AppLanguage.SPANISH, backoff = {}))
        val review = api.monthlyReview("2026-10")
        assertTrue(review.scorecard.any { it.key == MonthlyReview.HEALTH_SCORE_KEY })
        assertEquals(listOf("debt_total", "emergency_coverage_months", "net_operational"), review.publicScorecard.map { it.key })
    }
}
