package com.dincr.data

import java.math.BigDecimal
import java.time.LocalDate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** GO-1 — each goal says what it takes. The Swift twin is `GoalPlanTests`. Synthetic data. */
class GoalPlanTest {
    private val colones = MoneyFormat("CRC", MoneyFormat.Separators.DOT_COMMA)
    private val es = AppLanguage.SPANISH
    private val today = LocalDate.of(2026, 11, 15)
    private fun goal(target: Int? = 1_200_000, saved: Int? = 200_000, date: String? = null, status: String = "active") =
        Goal(1, "Viaje", target?.let(::BigDecimal), saved?.let(::BigDecimal), date, status = status)

    @Test fun perMonthToItsDateCountingThisMonth() {
        assertEquals(0, GoalPlan.monthlyNeeded(goal(date = "2027-10-01"), today)!!.compareTo(BigDecimal("90909.09")))
        assertEquals(listOf("Para llegar en oct 2027 necesitás ₡90.909 por mes."), GoalPlan.lines(goal(date = "2027-10-01"), today, null, colones, es))
    }

    @Test fun aDateThisMonthNeedsEverythingNow() {
        assertEquals(0, GoalPlan.monthlyNeeded(goal(date = "2026-11-30"), today)!!.compareTo(BigDecimal(1_000_000)))
    }

    @Test fun aPastDateAsksToChangeIt() {
        assertNull(GoalPlan.monthlyNeeded(goal(date = "2026-09-01"), today))
        assertEquals(listOf("La fecha ya pasó y te faltan ₡1.000.000. Cambiala para recalcular."), GoalPlan.lines(goal(date = "2026-09-01"), today, null, colones, es))
    }

    @Test fun withoutADateItAsksForOneAndWithANormalMonthItSaysHowLong() {
        assertEquals(listOf("Poné una fecha para saber cuánto guardar por mes.", "Con lo que te sobra en un mes normal (₡300.000) llegás en 4 meses."),
            GoalPlan.lines(goal(), today, BigDecimal(300_000), colones, es))
        assertEquals("Hoy no te sobra plata en un mes normal: primero hay que liberar algo.", GoalPlan.lines(goal(), today, BigDecimal(-50_000), colones, es).last())
    }

    @Test fun aReachedGoalSaysSoAndAnUnknownAmountSavedSaysNothing() {
        assertEquals(listOf("¡Meta cumplida!"), GoalPlan.lines(goal(saved = 1_200_000), today, BigDecimal.ONE, colones, es))
        assertTrue(GoalPlan.lines(goal(saved = null, date = "2027-01-01"), today, BigDecimal.ONE, colones, es).isEmpty())
    }
}
