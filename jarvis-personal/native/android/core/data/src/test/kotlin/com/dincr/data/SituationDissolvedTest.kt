package com.dincr.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * UX-7 — there is no separate Situación screen: each declared figure has its home. Hoy's missing
 * figures and the advisor's old "situation" route open Plan → Ingresos y base; the VIP priority keeps
 * exactly the backend's codes, with "no preference" stored as null. iOS twin:
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
        assertTrue(listOf(HomeInput.ESSENTIAL_EXPENSES, HomeInput.SAVINGS, HomeInput.EMERGENCY_FUND_TARGET).all { it.destination == HomeDestination.INCOME_BASE })
        assertEquals(AttentionItem.Destination.INCOME_BASE, AttentionList.destination("situation"))
    }

    @Test fun thePriorityChoicesAreTheBackendCodesWithNoPreferenceAsNull() {
        assertEquals(listOf(null, "debt", "emergency", "goals", "balanced"), StrategyPreference.choices.map { it?.code })
    }
}
