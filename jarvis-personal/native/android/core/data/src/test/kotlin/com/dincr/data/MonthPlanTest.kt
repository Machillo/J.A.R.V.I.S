package com.dincr.data

import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

/**
 * "Tu plan del mes" (UX-3) is a reading of the strategy answer, never a new calculation. The Swift
 * twin is `MonthPlanTests`; plan gating stays [StrategyContract] (`PlanContractTest`).
 */
class MonthPlanTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false; encodeDefaults = true }
    private fun basic(raw: String) = MonthPlan.of(json.decodeFromString<Strategy>(raw))
    private fun dashboard(strategy: String?) = MonthPlan.of(
        json.decodeFromString<StrategyDashboard>(strategy?.let { """{"status":"OK","title":"T","content":"C","strategy":$it}""" } ?: """{"status":"OK","content":"Sin datos"}"""),
        AppLanguage.SPANISH,
    )
    private fun bd(value: Long) = BigDecimal.valueOf(value)

    // region Complete data

    @Test fun basicPlanReadsTheMarginItsSplitAndTheRecommendation() {
        val plan = basic("""
            {"status":"tight","strategic_margin":214000,"recommendation":"Destiná ₡100.000 a la tarjeta.",
             "allocations":[{"bucket":"emergency","label":"Fondo de emergencia","amount":60000},
                            {"bucket":"debt_extra","label":"Extra a la tarjeta","amount":100000},
                            {"bucket":"flex","label":"Libre","amount":54000}],"income_source":"observed"}
        """)
        assertEquals(MonthPlan.Kind.BASIC, plan.kind)
        assertEquals(0, bd(214_000).compareTo(plan.base))
        assertEquals(listOf("Fondo de emergencia", "Extra a la tarjeta", "Libre"), plan.parts.map { it.label })
        assertEquals("Destiná ₡100.000 a la tarjeta.", plan.headline)
        assertTrue(plan.usesObservedIncome && !plan.isCritical && !plan.needsIncome)
        assertTrue(plan.showsComposition)   // 60.000 + 100.000 + 54.000 = 214.000
    }

    @Test fun dashboardPlanReadsTheSurplusItsSplitAndThePriority() {
        val plan = dashboard("""
            {"scope":"users","status":"controlled","objective":"Modo ataque de deuda.",
             "priority":{"kind":"debt","title":"Atacar deuda: Tarjeta","detail":"Primero esta obligación."},
             "allocation_base_amount":458000,
             "allocation_items":[{"key":"ataque_de_deuda","percentage":50.0,"amount":229000,"target_name":"Tarjeta"},
                                 {"key":"fondo_de_emergencia","percentage":35.0,"amount":160300},
                                 {"key":"vida_controlada","percentage":15.0,"amount":68700}]}
        """)
        assertEquals(MonthPlan.Kind.USERS, plan.kind)
        assertEquals(0, bd(458_000).compareTo(plan.base))
        assertEquals(listOf("Ataque de deuda · Tarjeta", "Salvavidas", "Vida controlada"), plan.parts.map { it.label })
        assertEquals(listOf(50.0, 35.0, 15.0), plan.parts.map { it.percentage })
        assertEquals("Atacar deuda: Tarjeta", plan.headline)
        assertTrue(plan.showsComposition)
    }

    @Test fun theOwnerAnswerIsReadAsTheOwnerPlan() {
        val plan = dashboard("""{"scope":"owner","status":"controlled","objective":"O","allocation_base_amount":100,"allocation_items":[{"key":"inversion","amount":100}]}""")
        assertEquals(MonthPlan.Kind.OWNER, plan.kind)
        assertEquals("O", plan.headline)
    }

    // endregion

    // region Partial and unknown data

    @Test fun partsThatLeaveMoneyUnassignedAreListedNotDrawnAsAWhole() {
        val plan = basic("""{"strategic_margin":200000,"allocations":[{"bucket":"debt_extra","label":"Extra","amount":140000},{"bucket":"emergency","label":"Fondo","amount":40000}]}""")
        assertEquals(2, plan.parts.size)
        assertFalse(plan.showsComposition)   // 180.000 of 200.000: the backend left 20.000 unassigned
        assertEquals(0, bd(200_000).compareTo(plan.base))
    }

    @Test fun anUnknownAmountIsNeverZero() {
        val plan = dashboard("""{"scope":"users","allocation_base_amount":300,"allocation_items":[{"key":"inversion","amount":300},{"key":"fondo_de_emergencia"}]}""")
        assertNull(plan.parts.last().amount)
        assertNull(plan.parts.last().percentage)
        assertFalse(plan.showsComposition)
        assertEquals(Composition.Status.PARTIAL, plan.composition.status)
        assertEquals(1, plan.composition.unknown.size)
    }

    @Test fun anUnknownAmountToPlanIsNeverZeroAndDrawsNoWhole() {
        val plan = dashboard("""{"scope":"users","allocation_items":[{"key":"inversion","amount":300}]}""")
        assertNull(plan.base)
        assertFalse(plan.showsComposition)
        val empty = basic("""{"status":"tight"}""")
        assertTrue(empty.base == null && empty.parts.isEmpty() && !empty.showsComposition)
    }

    @Test fun aMissingDashboardStrategyIsNotAPlan() {
        val plan = dashboard(null)
        assertTrue(plan.base == null && plan.parts.isEmpty())
        assertEquals("Sin datos", plan.headline)
        assertFalse(plan.needsIncome || plan.showsComposition)
    }

    @Test fun noIncomeAndCriticalAnswersAreRecognized() {
        assertTrue(basic("""{"status":"needs_income"}""").needsIncome)
        assertTrue(dashboard("""{"scope":"users","status":"needs_income"}""").needsIncome)
        assertTrue(basic("""{"status":"critical","recommendation":"R"}""").isCritical)
        assertTrue(dashboard("""{"scope":"users","status":"critical"}""").isCritical)
    }

    /** Reading the plan never changes the figures; the parts carry no currency of their own. */
    @Test fun readingThePlanNeverChangesTheFigures() {
        val strategy = json.decodeFromString<Strategy>("""{"strategic_margin":100.5,"allocations":[{"bucket":"a","label":"A","amount":100.5}]}""")
        assertEquals(MonthPlan.of(strategy), MonthPlan.of(strategy))
        assertEquals(0, BigDecimal("100.5").compareTo(MonthPlan.of(strategy).base))
        assertNull(MonthPlan.of(strategy).composition.currency)
    }

    // endregion
}
