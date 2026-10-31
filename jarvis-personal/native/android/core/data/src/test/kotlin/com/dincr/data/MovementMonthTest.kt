package com.dincr.data

import java.math.BigDecimal
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** Movimientos shows one month; a search looks through every month. Synthetic rows. iOS: `MovementMonthTests.swift`. */
class MovementMonthTest {
    private fun row(id: String, day: String, description: String) =
        Movement(movementId = id, transactionDate = day, description = description, amount = BigDecimal(1_000), transactionType = "expense", category = "Comida")

    private val rows = listOf(row("a", "2026-10-30", "Café de ejemplo"), row("b", "2026-10-01", "Super de ejemplo"), row("c", "2026-09-30", "Café de septiembre"))

    @Test fun onlyTheMonthIsListed() {
        assertEquals(listOf("a", "b"), MovementMonth.rows(rows, "2026-10", "").map { it.movementId })
        assertEquals(listOf("c"), MovementMonth.rows(rows, "2026-09", " ").map { it.movementId })
        assertTrue(MovementMonth.rows(rows, "2026-08", "").isEmpty())
    }

    @Test fun aSearchLooksThroughEveryMonth() {
        assertEquals(3, MovementMonth.rows(rows, "2026-10", "café").size)
    }
}
