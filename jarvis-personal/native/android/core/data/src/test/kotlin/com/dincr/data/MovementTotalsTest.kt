package com.dincr.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.math.BigDecimal

class MovementTotalsTest {
    private fun row(amount: Int, type: String, countsIn: String? = null) =
        Movement("m$amount$type", amount = BigDecimal(amount), transactionType = type, countsIn = countsIn)

    private fun same(expected: Int, actual: BigDecimal?) = assertEquals(0, BigDecimal(expected).compareTo(actual))

    @Test fun aPublicPlanAddsUpIncomeAndExpenses() {
        val totals = MovementTotals.of(listOf(row(100, "income"), row(30, "expense"), row(20, "expense")))
        same(100, totals.income); same(50, totals.expenses); assertNull(totals.debtPaid); same(50, totals.result)
    }

    @Test fun noRowOfAKindIsUnknownNeverZero() {
        val totals = MovementTotals.of(listOf(row(30, "expense")))
        assertNull(totals.income); same(30, totals.expenses); assertNull(totals.result)
    }

    @Test fun theOwnersRowsCountAsHisLedgerSays() {
        val totals = MovementTotals.of(listOf(row(100, "income", "income"), row(40, "expense", "expenses"), row(5, "income", "refunds"),
            row(10, "expense", "debt_payments"), row(900, "expense", "not_counted"), row(70, "income", "other_inflows")))
        same(100, totals.income); same(35, totals.expenses); same(10, totals.debtPaid); same(55, totals.result)
    }

    @Test fun refundsNeverTakeSpendingBelowZero() {
        same(0, MovementTotals.of(listOf(row(5, "income", "refunds"))).expenses)
    }
}
