package com.dincr.data

import java.math.BigDecimal
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * How much of the debts has been paid (original − remaining, the backend's amounts) and the
 * strategy's debt-free date. Unknown ≠ 0: no original amount, no progress; one unknown debt, no
 * total. iOS: `DebtProgressTests`. Synthetic data only.
 */
class DebtProgressTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false }
    private fun debts(text: String) = json.decodeFromString(ListSerializer(Debt.serializer()), text)

    @Test fun oneDebtPaidAndLeft() {
        val amounts = DebtProgress.of(debts("""[{"id":1,"total_amount":200000,"remaining_amount":150000}]""").single())!!
        assertEquals(0, BigDecimal(50_000).compareTo(amounts.paid))
        assertEquals(0.25, amounts.ratio, 1e-9)
        assertEquals(0.75, amounts.remainingFraction, 1e-9)
    }

    @Test fun anUnknownOriginalAmountHasNoProgress() {
        val list = debts("""[{"id":1,"remaining_amount":150000},{"id":2,"total_amount":0,"remaining_amount":10},{"id":3,"total_amount":100}]""")
        assertTrue(list.all { DebtProgress.of(it) == null })
    }

    @Test fun theTotalAddsEveryDebtIncludingPaidOnes() {
        val total = DebtProgress.total(debts("""
            [{"id":1,"total_amount":200000,"remaining_amount":150000},
             {"id":2,"total_amount":100000,"remaining_amount":0},
             {"id":3,"total_amount":100000,"remaining_amount":130000}]
        """))!!
        // 50 000 + 100 000 + 0 (a balance above the original is never negative progress).
        assertEquals(0, BigDecimal(150_000).compareTo(total.paid))
        assertEquals(0, BigDecimal(400_000).compareTo(total.original))
        assertEquals(0.625, total.remainingFraction, 1e-9)
    }

    @Test fun oneUnknownDebtLeavesNoTotal() {
        assertNull(DebtProgress.total(debts("""[{"id":1,"total_amount":200000,"remaining_amount":150000},{"id":2,"remaining_amount":5000}]""")))
        assertNull(DebtProgress.total(emptyList()))
    }

    @Test fun theStrategyDateComesOnlyFromADashboard() {
        val owner = json.decodeFromString(StrategyDashboard.serializer(),
            """{"status":"OK","strategy":{"scope":"owner","estimated_debt_free_date":"2028-06-01","months_saved_by_current_extras":3}}""")
        assertEquals(DebtProgress.StrategyDate("2028-06-01", 3, false), DebtProgress.strategyDate(owner.strategy))
        val waiting = json.decodeFromString(StrategyDashboard.serializer(),
            """{"status":"OK","strategy":{"scope":"users","estimated_debt_free_date":null,"missing":["debt_interest_rates"]}}""")
        assertEquals(DebtProgress.StrategyDate(null, null, true), DebtProgress.strategyDate(waiting.strategy))
        assertNull(DebtProgress.strategyDate(null))
    }
}
