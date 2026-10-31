package com.dincr.data

import java.time.LocalDate
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** RV-1 — the month that closed, in three short cards. The Swift twin is `MonthReviewTests`. Synthetic data. */
class MonthReviewTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false }
    private val colones = MoneyFormat("CRC", MoneyFormat.Separators.DOT_COMMA)
    private val es = AppLanguage.SPANISH
    private fun summary(text: String) = json.decodeFromString<MonthlySummary>(text)

    private val october = """{"period":"2026-10","income":1000000,"expenses":700000,"debt_paid":100000,
        "top_category":{"category":"Comida","amount":250000},"saved":{"total":50000,"goals":0,"salvavidas":50000}}"""
    private val september = """{"period":"2026-09","income":1000000,"expenses":750000,"debt_paid":100000}"""

    @Test fun aGoodMonthComparedWithTheOneBefore() {
        val cards = MonthReview.cards(summary(october), summary(september), colones, es)
        assertEquals(listOf("Cómo te fue en oct 2026", "Lo que lograste", "Para este mes"), cards.map { it.title })
        assertEquals(listOf("Te sobraron ₡200.000.", "Es ₡50.000 mejor que el mes anterior."), cards[0].lines)
        assertEquals(listOf("Pagaste ₡100.000 de deudas.", "Guardaste ₡50.000."), cards[1].lines)
        assertEquals(listOf("Seguí igual: mantené lo que guardás y tus pagos de deudas al día."), cards[2].lines)
    }

    @Test fun aMonthInTheRedPointsAtTheBiggestSpending() {
        val cards = MonthReview.cards(summary("""{"period":"2026-10","income":500000,"expenses":600000,"debt_paid":0,"top_category":{"category":"Comida","amount":250000}}"""), null, colones, es)
        assertEquals(listOf("Salió ₡100.000 más de lo que entró."), cards[0].lines)
        assertEquals(listOf("Este mes no hubo pagos de deudas ni ahorro registrados."), cards[1].lines)
        assertEquals(listOf("Tu gasto más grande fue Comida (₡250.000). Bajarlo un poco es lo que más ayuda."), cards[2].lines)
    }

    @Test fun nothingSavedAsksToPutSomethingAside() {
        assertEquals(listOf("Apenas entre tu salario, apartá algo para tu Salvavidas o una meta, aunque sea poco."),
            MonthReview.cards(summary("""{"period":"2026-10","income":500000,"expenses":400000,"debt_paid":0}"""), null, colones, es)[2].lines)
    }

    @Test fun anUnknownIncomeIsNotReadAsZero() {
        val month = summary("""{"period":"2026-10","expenses":400000}""")
        assertNull(MonthReview.left(month))
        assertEquals(listOf("Faltan los ingresos o los gastos de este mes para saberlo."), MonthReview.cards(month, null, colones, es)[0].lines)
    }

    @Test fun theClosedMonthIsTheOneBeforeToday() {
        assertEquals("2026-12" to "2026-11", MonthReview.closedMonths(LocalDate.of(2027, 1, 3)))
    }
}
