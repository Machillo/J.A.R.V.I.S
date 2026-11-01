package com.dincr.data

import java.math.BigDecimal
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** HS-1 — the simple health reading. The Swift twin is `HealthReadingTests`. */
class HealthReadingTest {
    private val es = AppLanguage.SPANISH
    private fun normal(expenses: Int = 600_000, debt: Int = 100_000, saved: Int = 150_000) =
        FinancialReading.Normal(3, BigDecimal(1_000_000), BigDecimal(expenses), BigDecimal(debt), BigDecimal(saved))

    @Test fun spendingMoreThanWhatComesInIsAtRisk() {
        val reading = HealthReading.reading(normal(expenses = 1_000_000), BigDecimal(5), es)!!
        assertEquals(HealthReading.Level.AT_RISK, reading.level)
        assertEquals("En riesgo", reading.word)
        assertEquals("En un mes normal sale más plata de la que entra.", reading.reason)
    }

    @Test fun heavyDebtIsAtRiskAndPointsToTheScenarios() {
        val reading = HealthReading.reading(normal(expenses = 300_000, debt = 450_000), BigDecimal(5), es)!!
        assertEquals("Las deudas se llevan 45 de cada 100 que entran.", reading.reason)
        assertTrue(reading.action.contains("Escenarios"))
    }

    @Test fun aThinSalvavidasIsAtRiskButAnUnknownOneIsLeftOut() {
        assertEquals(HealthReading.Level.AT_RISK, HealthReading.reading(normal(), BigDecimal("0.3"), es)!!.level)
        assertEquals(HealthReading.Level.GOOD, HealthReading.reading(normal(), null, es)!!.level)
    }

    @Test fun littleSavingOrSomeDebtIsFair() {
        assertEquals("Guardás 5 de cada 100 que entran.", HealthReading.reading(normal(saved = 50_000), BigDecimal(5), es)!!.reason)
        assertEquals(HealthReading.Level.FAIR, HealthReading.reading(normal(debt = 250_000), BigDecimal(5), es)!!.level)
        assertEquals("Tu Salvavidas cubre 1,5 meses; lo ideal son tres.", HealthReading.reading(normal(), BigDecimal("1.5"), es)!!.reason)
    }

    @Test fun everythingInPlaceIsGoodAndNoNormalMonthIsNoReading() {
        assertEquals("Bien", HealthReading.reading(normal(), BigDecimal(4), es)!!.word)
        assertNull(HealthReading.reading(null, BigDecimal(4)))
    }
}
