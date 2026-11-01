package com.dincr.data

import java.math.BigDecimal
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** RT-1 — Retiro in simple words. The Swift twin is `RetirementTests`. Synthetic data. */
class RetirementTest {
    private val colones = MoneyFormat("CRC", MoneyFormat.Separators.DOT_COMMA)
    private val es = AppLanguage.SPANISH
    private fun config(rop: Int? = 3_000_000, voluntary: Int? = null, birth: Int? = 1991, age: Int? = 65) =
        Retirement.Config(rop?.let(::BigDecimal), voluntary?.let(::BigDecimal), birth, age)

    @Test fun theReferenceGrowsWithAge() {
        assertNull(RetirementReading.multiple(24))
        assertEquals(1.0, RetirementReading.multiple(30)!!, 0.0001)
        assertEquals(1.4, RetirementReading.multiple(32)!!, 0.0001)
        assertEquals(10.0, RetirementReading.multiple(70)!!, 0.0001)
    }

    @Test fun belowTheReferenceSaysHowMuchMoreEachMonth() {
        assertEquals(listOf("Tenés ₡3.000.000 ahorrado para tu retiro.", "Te faltan 30 años para retirarte a los 65.",
            "Para tu edad, una referencia común es tener 2 veces tu ingreso anual (₡12.000.000): vas por debajo.",
            "Si aportás ₡150.000 más al mes, en 5 años cerrás la diferencia."),
            RetirementReading.lines(config(), BigDecimal(500_000), 2026, colones, es))
    }

    @Test fun aboveOrCloseSaySoWithoutAnAction() {
        val above = RetirementReading.lines(config(rop = 10_000_000, voluntary = 3_000_000), BigDecimal(500_000), 2026, colones, es)
        assertTrue(above.last().endsWith(": vas por encima.") && above.size == 3)
        assertTrue(RetirementReading.lines(config(rop = 10_000_000), BigDecimal(500_000), 2026, colones, es).last().endsWith(": vas cerca."))
    }

    @Test fun unknownPartsAreLeftOutNeverZero() {
        assertTrue(RetirementReading.lines(config(rop = null), BigDecimal(500_000), 2026, colones, es).isEmpty())
        assertEquals("Poné tu año de nacimiento para compararlo con tu edad.", RetirementReading.lines(config(birth = null), BigDecimal(500_000), 2026, colones, es).last())
        assertEquals(2, RetirementReading.lines(config(), null, 2026, colones, es).size)
        assertEquals("Lo importante ahora es empezar y aportar seguido.", RetirementReading.lines(config(birth = 2004), BigDecimal(500_000), 2026, colones, es).last())
    }

    @Test fun anUpdateSendsEveryFieldSoANullClears() {
        val body = Json.encodeToString(RetirementUpdate.serializer(), RetirementUpdate(BigDecimal(100), null, 1990, 65))
        assertTrue(body, body.contains("\"voluntary_balance\":null") && body.contains("\"birth_year\":1990"))
    }
}
