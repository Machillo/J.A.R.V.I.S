package com.dincr.data

import java.math.BigDecimal
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** What a text shared into DINCR proposes. Invented messages only. */
class SharedExpenseTest {
    private fun same(expected: String, actual: BigDecimal?) = assertEquals(0, BigDecimal(expected).compareTo(actual))

    @Test fun colonesWithThousands() {
        val read = SharedExpense.parse("Compra por ₡18.450,00 en SUPER EJEMPLO aprobada")!!
        same("18450", read.amount)
        assertEquals("CRC", read.currency)
        assertEquals("SUPER EJEMPLO", read.merchant)
    }

    @Test fun dollarsWithCents() {
        val read = SharedExpense.parse("Se realizó una compra de USD 12.99 at TIENDA DEMO")!!
        same("12.99", read.amount)
        assertEquals("USD", read.currency)
        assertEquals("TIENDA DEMO", read.merchant)
    }

    @Test fun theSymbolAfterTheNumberAndALabeledMerchant() {
        val read = SharedExpense.parse("Monto: 5,000 colones\nComercio: Soda de ejemplo")!!
        same("5000", read.amount)
        assertEquals("CRC", read.currency)
        assertEquals("Soda de ejemplo", read.merchant)
    }

    @Test fun dollarSign() = same("1234.5", SharedExpense.parse("Pago \$1,234.5")!!.amount)

    @Test fun whatCannotBeReadStaysEmptyToTypeIt() {
        val read = SharedExpense.parse("Hola, nos vemos mañana a las 5")!!
        assertNull(read.amount)
        assertNull(read.currency)
    }

    @Test fun aNumberWithoutACurrencyIsNotTakenAsAnAmount() = assertNull(SharedExpense.parse("Tarjeta terminada en 1234 el día 21")!!.amount)

    @Test fun nothingSharedIsNothing() {
        assertNull(SharedExpense.parse(null))
        assertNull(SharedExpense.parse("   "))
    }

    @Test fun aZeroAmountIsNotAnAmount() = assertNull(SharedExpense.parse("Saldo ₡0,00")!!.amount)

    @Test fun aHugeTextIsCutBeforeReading() = assertNull(SharedExpense.parse("x".repeat(5_000) + " ₡100")!!.amount)
}
