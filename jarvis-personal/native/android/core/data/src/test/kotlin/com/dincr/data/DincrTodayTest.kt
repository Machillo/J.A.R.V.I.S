package com.dincr.data

import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * DINCR → Hoy: while the proactive advisor has no earlier observation (BASELINE, native never saves
 * one) it shows the command center's current alerts, the same ones the main Today shows, instead of
 * "nothing urgent". iOS twin: `PlanAccountsTests.dincrTodayShowsTheCurrentAlertsWhileTheAdvisorHasNoEarlierObservation`.
 */
class DincrTodayTest {
    private fun api(plan: PlanTier = PlanTier.VIP) =
        DincrApi(ApiClient("https://fixtures.invalid", { "t" }, FakeBackend(FakeBackend.Scenario.POPULATED, plan), AppLanguage.SPANISH, backoff = {}))

    @Test fun baselineShowsTheCurrentAlertsOfTheCommandCenter() = runTest {
        val api = api()
        val today = api.dincrToday()
        assertTrue(today.isBaseline)
        assertEquals(api.commandCenter().alerts, today.currentAlerts)
        assertEquals("Pago de tarjeta en 5 días", today.currentAlerts?.firstOrNull()?.title)
    }
}
