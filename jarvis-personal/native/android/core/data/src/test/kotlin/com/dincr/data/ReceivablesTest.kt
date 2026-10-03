package com.dincr.data

import java.math.BigDecimal
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * JARVIS "Control de dinero": the Owner's cuentas por cobrar. Only the Owner reaches them, through
 * the read-only route; unknown figures stay unknown. The Swift twin is `OwnerReceivablesTests`.
 */
class ReceivablesTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false }

    private fun fixture(plan: PlanTier = PlanTier.VIP, role: FakeBackend.Role = FakeBackend.Role.USER) =
        FakeBackend(FakeBackend.Scenario.POPULATED, plan, role = role).let { it to DincrApi(ApiClient("https://fixtures.invalid", { "t" }, it, AppLanguage.SPANISH, backoff = {})) }

    private suspend fun status(block: suspend () -> Unit): Int = try { block(); 200 } catch (error: ApiError) { error.status }

    @Test fun moneyControlIsPortedNextToTheOtherSections() {
        assertEquals(listOf(Jarvis.Section.CHAT, Jarvis.Section.CALENDAR, Jarvis.Section.MONEY_CONTROL, Jarvis.Section.ANALYSIS),
            Jarvis.Section.entries.filter { it.isAvailable })
        assertEquals(listOf(Jarvis.Section.MEMORY, Jarvis.Section.STRATEGY, Jarvis.Section.MONEY, Jarvis.Section.WEALTH, Jarvis.Section.RECORDS),
            Jarvis.Section.entries.filter { !it.isAvailable })
    }

    @Test fun onlyTheOwnerReachesThemThroughTheReadOnlyRoute() = runTest {
        for (plan in PlanTier.entries) {
            val (_, user) = fixture(plan)
            assertEquals(plan.name, 403, status { user.receivables() })
        }
        val (backend, owner) = fixture(PlanTier.FREE, FakeBackend.Role.OWNER)
        val report = owner.receivables()
        // Never the web route, which syncs and stores on every read.
        val last = backend.requests.last()
        assertEquals("/finance/receivables/view", last.url.substringAfter("fixtures.invalid").substringBefore("?"))
        assertEquals("GET", last.method)
        assertEquals(2, report.items.size)
        assertEquals(0, BigDecimal(85_000).compareTo(report.summary?.totalPending))
        assertTrue(report.items.first().history.any { it.isPayment })
    }

    @Test fun unknownFiguresAreNeverZero() {
        val report = json.decodeFromString<ReceivablesReport>(
            """{"items":[{"id":3,"person_name":null,"current_amount_due":null,"history":[{"id":9,"amount":null}]}],"summary":{"total_pending":null}}""")
        assertNull(report.summary?.totalPending)
        val item = report.items.first()
        assertNull(item.currentAmountDue)
        assertNull(item.carriedPending)
        assertNull(item.history.first().amount)
        // A body without items is an empty list, not an error.
        assertTrue(json.decodeFromString<ReceivablesReport>("""{"status":"OK"}""").items.isEmpty())
    }
}
