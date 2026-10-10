package com.dincr.data

import java.math.BigDecimal
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * UNKNOWN ≠ 0 on the planning and analysis screens: a goal whose amount saved is unknown has no
 * remainder, no progress and no monthly need computed from 0; a budget's total spent, the goals'
 * overall progress, a report's category bars and the Owner's monthly charts never add or draw an
 * unknown amount as 0. The Swift twin is `UnknownAmountsTests`. Synthetic data.
 */
class UnknownAmountsTest {
    private fun goal(target: Int?, current: Int?, status: String? = "active") =
        Goal(1, "Viaje", target?.let(::BigDecimal), current?.let(::BigDecimal), status = status)

    @Test fun aGoalsRemainderNeedsBothAmounts() {
        assertEquals(BigDecimal(70000), goal(100000, 30000).remaining)
        assertEquals("never negative", BigDecimal.ZERO, goal(100000, 120000).remaining)
        assertNull("an unknown amount saved is not 0 saved", goal(100000, null).remaining)
        assertNull(goal(null, 30000).remaining)
    }

    @Test fun aGoalsProgressNeedsBothAmountsAndAPositiveTarget() {
        assertEquals(0.3, goal(100000, 30000).progressFraction!!, 1e-9)
        assertNull("no 0 % from an unknown amount saved", goal(100000, null).progressFraction)
        assertNull(goal(0, 0).progressFraction)
        assertNull(goal(null, 30000).progressFraction)
    }

    @Test fun aContributionIsOfferedUntilTheGoalIsReachedEvenWhenTheRemainderIsUnknown() {
        assertTrue(goal(100000, 30000).canContribute)
        assertTrue("unknown does not hide the action", goal(100000, null).canContribute)
        assertFalse(goal(100000, 100000).canContribute)
        assertFalse(goal(100000, 30000, status = "completed").canContribute)
    }

    @Test fun theGoalsOverallProgressNeedsEveryAmount() {
        assertEquals(0.25, Goal.overallProgress(listOf(goal(100000, 30000), goal(100000, 20000)))!!, 1e-9)
        assertNull("one unknown amount saved is not added as 0", Goal.overallProgress(listOf(goal(100000, 30000), goal(100000, null))))
        assertNull(Goal.overallProgress(listOf(goal(null, 30000))))
    }

    @Test fun aBudgetsTotalSpentNeedsEveryCategory() {
        val known = Budget(listOf(BudgetItem("Comida", BigDecimal(100000), BigDecimal(50000)), BudgetItem("Transporte", BigDecimal(60000), BigDecimal(10000))))
        assertEquals(BigDecimal(60000), known.spentTotal)
        val partial = Budget(listOf(BudgetItem("Comida", BigDecimal(100000), BigDecimal(50000)), BudgetItem("Transporte", BigDecimal(60000), null)))
        assertNull("an unknown amount spent is not added as 0", partial.spentTotal)
    }

    @Test fun categoryRowsWithoutAnAmountAreListedNotDrawnAsZero() {
        val split = CategoryTotal.split(listOf(CategoryTotal("Comida", BigDecimal(200000)), CategoryTotal("Salud", null), CategoryTotal(null, BigDecimal(500))), AppLanguage.SPANISH)
        assertEquals(listOf("Comida" to BigDecimal(200000), "Sin categoría" to BigDecimal(500)), split.known)
        assertEquals(listOf("Salud"), split.unknown)
    }

    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false }

    @Test fun theOwnersMonthlyChartsSkipMonthsWithAnUnknownAmount() {
        val analysis = json.decodeFromString<TransactionAnalysis>("""{
            "monthly_flow":[{"month":"2026-07","income":800000,"expenses":500000},{"month":"2026-08","income":null,"expenses":450000},
                            {"month":"2026-09","income":820000,"expenses":null},{"month":"2026-10","income":830000,"expenses":510000}],
            "expenses_by_month":[{"month":"2026-08","total":450000},{"month":"2026-09","total":null},{"month":"2026-10","total":510000}]}""")
        assertEquals(listOf("2026-07", "2026-10"), analysis.flowMonths().map { it.month })
        assertEquals(BigDecimal(830000), analysis.flowMonths().last().income)
        assertEquals(listOf("2026-10"), analysis.flowMonths(count = 1).map { it.month })
        assertEquals(listOf("2026-08", "2026-10"), analysis.knownExpensesByMonth(6).map { it.month })
    }
}
