package com.dincr.data

import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * UX-6 (UNKNOWN ≠ 0): the command center sends null for figures it can't compute, a director
 * priority "incomplete", an empty roadmap and `missing` codes. The app reads them as unknown
 * ("—", no section), never as ₡0. The Swift twin is `CommandCenterUnknownTests`. Synthetic data.
 */
class CommandCenterUnknownTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false; encodeDefaults = true }

    @Test fun unknownFiguresDecodeAsUnknownNeverZero() {
        val center = json.decodeFromString<CommandCenter>(
            """{"director":{"priority":"incomplete","headline":"Aún no tengo suficiente información para recomendarte una prioridad",
                "next_action":"Completá la información que falta para que DINCR pueda recomendarte.","data_complete":false,"missing":["income"]},
                "safe_to_spend":{"amount":null,"monthly_margin":null,"next_45_days_minimum":250000.0,"missing":["income"]},
                "roadmap":[],"alerts":[],"automation":{"review":0}}""",
        )
        assertNull(center.safeToSpend?.amount)
        assertNull(center.safeToSpend?.monthlyMargin)
        assertEquals(0, center.safeToSpend?.next45DaysMinimum?.compareTo(java.math.BigDecimal(250000)))
        assertEquals("incomplete", center.director?.priority)
        assertTrue(center.director?.headline?.isNotEmpty() == true)  // Hoy shows the backend's sentence, not the code
        assertTrue(center.roadmap.isEmpty())                          // no roadmap section
        assertTrue(AttentionList.today(center).isEmpty)               // nothing invented for "Para atender"
    }
}
