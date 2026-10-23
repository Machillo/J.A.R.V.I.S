package com.dincr.data

import java.math.BigDecimal
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Owner exact-amount distribution (phase 1): the request the app sends, how the answer is read, and
 * the Owner-only gate. The fake server mirrors the backend's shape and role check
 * (backend/ai/test_owner_exact_distribution.py holds the calculation's own tests).
 */
class OwnerExactDistributionTest {
    private fun fixture(role: FakeBackend.Role) =
        FakeBackend(FakeBackend.Scenario.POPULATED, PlanTier.VIP, role = role)
            .let { it to DincrApi(ApiClient("https://fixtures.invalid", { "t" }, it, AppLanguage.SPANISH, backoff = {})) }

    private suspend fun status(block: suspend () -> Unit): Int = try { block(); 200 } catch (error: ApiError) { error.status }

    @Test fun theAmountTravelsInAPostBodyInColones() = runTest {
        val (backend, api) = fixture(FakeBackend.Role.OWNER)
        api.ownerExactDistribution(ExactDistributionRequest(BigDecimal("750000.50")))
        val request = backend.requests.last()
        assertEquals("POST", request.method)
        assertTrue(request.url.endsWith("/jarvis/premium/strategy-dashboard/exact-distribution"))
        assertFalse("never in the URL", request.url.contains("750000"))
        assertTrue(request.body!!, Regex(""""amount":750000\.50?[,}]""").containsMatchIn(request.body!!) && request.body!!.contains("\"currency\":\"CRC\""))
    }

    @Test fun theAnswerIsMarkedAsTheTypedAmountAndListsItFirst() = runTest {
        val (_, api) = fixture(FakeBackend.Role.OWNER)
        val estimate = api.ownerStrategyDashboard().strategy!!
        val exact = api.ownerExactDistribution(ExactDistributionRequest(BigDecimal(2_000_000))).strategy!!
        assertFalse(estimate.isManualAmount)
        assertTrue(exact.isManualAmount)
        val keys = Distribution.formulaLines(exact).map { it.first }
        assertEquals("manual_available", keys.first())
        assertFalse("the estimate's cash and income are not mixed in", keys.contains("cash_available_now") || keys.contains("income"))
        assertEquals("Monto que indicaste", Distribution.formulaLabel("manual_available", AppLanguage.SPANISH))
        assertEquals(0, exact.allocationBaseAmount!!.compareTo(exact.allocationItems.sumOf { it.amount!! }))
    }

    @Test fun aNewAmountRecalculatesAndTheEstimateStaysTheSame() = runTest {
        val (_, api) = fixture(FakeBackend.Role.OWNER)
        val before = api.ownerStrategyDashboard().strategy!!
        val low = api.ownerExactDistribution(ExactDistributionRequest(BigDecimal(1_000_000))).strategy!!
        val high = api.ownerExactDistribution(ExactDistributionRequest(BigDecimal(3_000_000))).strategy!!
        assertTrue(high.allocationBaseAmount!! > low.allocationBaseAmount!!)
        assertEquals(before, api.ownerStrategyDashboard().strategy!!)
    }

    @Test fun theTypedAmountIsSplitWholeWithNoDeductionLine() = runTest {
        val (_, api) = fixture(FakeBackend.Role.OWNER)
        val exact = api.ownerExactDistribution(ExactDistributionRequest(BigDecimal(250_000))).strategy!!
        assertEquals(0, exact.allocationBaseAmount!!.compareTo(BigDecimal(250_000)))
        assertEquals(0, exact.allocationItems.sumOf { it.amount!! }.compareTo(BigDecimal(250_000)))
        assertEquals(listOf("manual_available", "surplus"), Distribution.formulaLines(exact).map { it.first })
    }

    @Test fun onlyTheOwnerGetsAnExactDistribution() = runTest {
        val (_, user) = fixture(FakeBackend.Role.USER)
        assertEquals(403, status { user.ownerExactDistribution(ExactDistributionRequest(BigDecimal(500_000))) })
        val (_, owner) = fixture(FakeBackend.Role.OWNER)
        assertEquals(422, status { owner.ownerExactDistribution(ExactDistributionRequest(BigDecimal.ZERO)) })
        assertEquals(422, status { owner.ownerExactDistribution(ExactDistributionRequest(BigDecimal(500_000), "USD")) })
    }

    @Test fun editingTheAmountDropsTheResultOfThePreviousOne() = runTest {
        val (_, api) = fixture(FakeBackend.Role.OWNER)
        val answer = api.ownerExactDistribution(ExactDistributionRequest(BigDecimal(250_000))).strategy!!
        val shown = ExactDistributionForm().edited("250000").calculated("250000", answer)
        assertEquals(answer, shown.result)
        val edited = shown.edited("300000")
        assertEquals(null, edited.result)  // never "calculated from the amount you entered" for another amount
        assertEquals("300000", edited.amountText)
        assertEquals(null, ExactDistributionForm().failed("x").edited("1").error)
    }

    @Test fun aLateAnswerForAnEarlierAmountIsIgnored() = runTest {
        val (_, api) = fixture(FakeBackend.Role.OWNER)
        val answer = api.ownerExactDistribution(ExactDistributionRequest(BigDecimal(250_000))).strategy!!
        // Calculated for 250000, the Owner typed 300000 before the answer arrived.
        val form = ExactDistributionForm().edited("300000").calculated("250000", answer)
        assertEquals(null, form.result)
        assertEquals("300000", form.amountText)
    }
}
