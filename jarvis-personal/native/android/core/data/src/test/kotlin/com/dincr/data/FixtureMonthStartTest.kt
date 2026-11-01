package com.dincr.data

import java.time.LocalDate
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Movimientos lists the month in course; the sample data must show its rows on any date, the 1st of a
 * month included (the UI tests failed on 1 November when the last days' rows fell in October).
 * The Swift twin is `FixtureMonthStartTests`.
 */
class FixtureMonthStartTest {
    @Test fun theRecentSampleRowsStayInTheMonthInCourseOnThe1st() = runTest {
        val first = LocalDate.of(2026, 11, 1)
        val api = DincrApi(ApiClient("https://fixtures.invalid", { "t" }, FakeBackend(FakeBackend.Scenario.POPULATED, PlanTier.VIP, currentDate = first),
            AppLanguage.SPANISH, backoff = {}))
        val rows = api.movements()
        for (name in listOf("Supermercado", "Feria del agricultor", "Suscripción en dólares", "Alquiler")) {
            val row = rows.first { it.description == name }
            assertTrue("$name on ${row.transactionDate}", row.transactionDate!!.startsWith("2026-11"))
        }
    }
}
