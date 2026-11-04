package com.dincr.data

import java.math.BigDecimal
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** The estimate of the waiting dollars: what Gastos adds on screen. iOS: `PendingEstimateTests`. Synthetic data only. */
class PendingEstimateTest {
    private fun item(id: Long, day: String, text: String, estimate: Int?) = PendingConversion.Item(
        "expense:$id", id, day, text, null, BigDecimal(10), "USD", null, null, estimate?.let { BigDecimal(it) })

    private val pending = PendingConversion(true, listOf(item(1, "2026-11-02", "Café", 5_000), item(2, "2026-11-20", "Libro", 6_000),
        item(3, "2026-10-05", "Viaje", 7_000), item(4, "2026-11-25", "Sin tasa", null)))

    @Test fun onlyTheMonthOnScreenCounts() {
        assertEquals(PendingEstimate(BigDecimal(11_000), 1), pending.estimate("2026-11", ""))
        assertEquals(PendingEstimate(BigDecimal(7_000), 0), pending.estimate("2026-10", ""))
    }

    @Test fun aSearchLooksThroughEveryMonth() = assertEquals(PendingEstimate(BigDecimal(7_000), 0), pending.estimate("2026-11", "viaje"))

    @Test fun noEstimateIsUnknownNotZero() {
        assertEquals(PendingEstimate(null, 0), pending.estimate("2026-09", ""))
        assertEquals(PendingEstimate(null, 1), pending.estimate("2026-11", "sin tasa"))
        assertNull(MovementTotals(BigDecimal(5), null, null).addingEstimate(null).expenses)
    }

    @Test fun theEstimateCountsInExpensesAndTheResult() {
        val totals = MovementTotals(BigDecimal(100), BigDecimal(30), null).addingEstimate(BigDecimal(20))
        assertEquals(BigDecimal(50), totals.expenses)
        assertEquals(BigDecimal(50), totals.result)
        assertEquals(BigDecimal(20), MovementTotals(null, null, null).addingEstimate(BigDecimal(20)).expenses)
    }

    @Test fun anOlderServerPromisesNothing() {
        val json = Json { ignoreUnknownKeys = true }
        val old = json.decodeFromString(PendingConversion.serializer(), """{"available":true,"totals":[{"currency":"USD","amount":5,"count":1}]}""")
        assertFalse(old.autoClose)
        assertNull(old.totals[0].estimatedAmount)
        val new = json.decodeFromString(PendingConversion.serializer(), """{"available":true,"totals":[{"currency":"USD","amount":5,"count":1,"estimated_amount":2500}],"auto_close":true}""")
        assertTrue(new.autoClose)
        assertEquals(0, BigDecimal(2500).compareTo(new.totals[0].estimatedAmount))
    }
}
