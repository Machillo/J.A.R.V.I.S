package com.dincr.data

import java.time.LocalDate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class DaysLeftTest {
    private val today = LocalDate.parse("2026-11-03")
    private fun label(day: String?) = DaysLeft.label(day, today, AppLanguage.SPANISH)

    @Test fun saysTheDistanceInWords() {
        assertEquals("Hoy", label("2026-11-03"))
        assertEquals("Mañana", label("2026-11-04"))
        assertEquals("En 2 días", label("2026-11-05"))
        assertEquals("En 30 días", label("2026-12-03"))
        assertEquals("Ayer", label("2026-11-02"))
        assertEquals("Hace 2 días", label("2026-11-01"))
    }

    @Test fun readsADayWithATime() = assertEquals("En 5 días", label("2026-11-08T10:00:00"))

    @Test fun aChangeOfYearCounts() =
        assertEquals("En 2 días", DaysLeft.label("2027-01-02", LocalDate.parse("2026-12-31"), AppLanguage.SPANISH))

    @Test fun notADayHasNoLabel() {
        assertNull(label(null))
        assertNull(label(""))
        assertNull(label("pronto"))
    }
}
