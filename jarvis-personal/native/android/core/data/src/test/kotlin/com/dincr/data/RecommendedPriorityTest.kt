package com.dincr.data

import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * UX-8 — "Recomendación de DINCR" reads the engines' own priority and why, never a new rule.
 * iOS twin: `RecommendedPriorityTests`. Synthetic data.
 */
class RecommendedPriorityTest {
    private val json = Json { ignoreUnknownKeys = true }
    private fun basic(raw: String) = json.decodeFromString<Strategy>(raw)
    private fun director(raw: String) = json.decodeFromString<DirectorStrategy>(raw)

    @Test fun basicShowsTheEnginesPriorityAndItsOwnReason() {
        val priority = RecommendedPriority.of(basic("""{"status":"healthy","priority":"debt","recommendation":"Cubrí tus compromisos y dirigí el excedente a Tarjeta."}"""), AppLanguage.SPANISH)!!
        assertEquals("Pagar deudas", priority.title)
        assertEquals("Cubrí tus compromisos y dirigí el excedente a Tarjeta.", priority.why)
    }

    @Test fun basicWithoutIncomeOrWithAnUnknownCodeShowsNothing() {
        assertNull(RecommendedPriority.of(basic("""{"status":"needs_income","priority":"income","recommendation":"Registrá tus ingresos."}""")))
        assertNull(RecommendedPriority.of(basic("""{"status":"healthy","priority":"something_new"}""")))
    }

    @Test fun aCriticalBasicMonthKeepsItsMessageOnce() {
        val priority = RecommendedPriority.of(basic("""{"status":"critical","priority":"stabilize","recommendation":"Tus compromisos superan el ingreso."}"""), AppLanguage.SPANISH)!!
        assertEquals("Estabilizar tu mes", priority.title)
        assertNull(priority.why)
    }

    @Test fun vipShowsTheDashboardPriorityTitleAndDetail() {
        val priority = RecommendedPriority.of(director("""{"scope":"users","status":"healthy","priority":{"kind":"debt","title":"Atacar deuda: Tarjeta","detail":"El sobrante destinado a deuda se concentra primero en esta obligación."}}"""))!!
        assertEquals("Atacar deuda: Tarjeta", priority.title)
        assertTrue(priority.why!!.startsWith("El sobrante"))
    }

    @Test fun vipWithoutIncomeOrPriorityShowsNothing() {
        assertNull(RecommendedPriority.of(director("""{"scope":"users","status":"needs_income","priority":{"kind":"cash","title":"X"}}""")))
        assertNull(RecommendedPriority.of(director("""{"scope":"users","status":"healthy"}""")))
    }
}
