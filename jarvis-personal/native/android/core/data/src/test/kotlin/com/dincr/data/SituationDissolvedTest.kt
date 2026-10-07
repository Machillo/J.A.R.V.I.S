package com.dincr.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * UX-7 — there is no separate Situación screen: each declared figure has its home. Missing essential
 * expenses and the advisor's old "situation" route open Plan → Ingresos y base; missing savings and
 * emergency-fund target open Metas y ahorros (Tus ahorros). iOS twin:
 * `SituationDissolvedTests`. Synthetic data.
 */
class SituationDissolvedTest {
    @Test fun noDestinationIsTheRetiredScreen() {
        assertFalse(HomeDestination.entries.any { it.route == "situation" })
        assertFalse(AttentionItem.Destination.entries.any { it.route == "situation" || it.key == "situation" })
        assertEquals("incomeBase", HomeDestination.INCOME_BASE.route)
        assertEquals("incomeBase", AttentionItem.Destination.INCOME_BASE.route)
    }

    @Test fun missingFiguresAndTheOldRouteOpenIngresosYBase() {
        assertEquals(HomeDestination.INCOME_BASE, HomeInput.ESSENTIAL_EXPENSES.destination)
        assertTrue(listOf(HomeInput.SAVINGS, HomeInput.EMERGENCY_FUND_TARGET).all { it.destination == HomeDestination.GOALS })
        assertEquals(AttentionItem.Destination.INCOME_BASE, AttentionList.destination("situation"))
    }
}
