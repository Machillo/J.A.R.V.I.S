package com.dincr.data

import java.math.BigDecimal
import org.junit.Test
import org.junit.Assert.assertEquals

class DebtOrderTest {
    private val debts = listOf(
        Debt(id = 1, name = "A", remainingAmount = BigDecimal(300), interestRate = BigDecimal(20), interestRateKnown = true),
        Debt(id = 2, name = "B", remainingAmount = null, interestRate = BigDecimal.ZERO, interestRateKnown = false),
        Debt(id = 3, name = "C", remainingAmount = BigDecimal(900), interestRate = BigDecimal(35), interestRateKnown = true),
        Debt(id = 4, name = "D", remainingAmount = BigDecimal(100), interestRate = null, interestRateKnown = null),
    )

    @Test fun savedKeepsTheOrder() = assertEquals(listOf(1L, 2L, 3L, 4L), DebtOrder.SAVED.sorted(debts).map { it.id })

    @Test fun balanceEitherWayAndUnknownLast() {
        assertEquals(listOf(3L, 1L, 4L, 2L), DebtOrder.BALANCE_HIGH.sorted(debts).map { it.id })
        assertEquals(listOf(4L, 1L, 3L, 2L), DebtOrder.BALANCE_LOW.sorted(debts).map { it.id })
    }

    @Test fun anUnknownRateIsNeverZero() {
        assertEquals(listOf(3L, 1L, 2L, 4L), DebtOrder.RATE_HIGH.sorted(debts).map { it.id })
        assertEquals(listOf(1L, 3L, 2L, 4L), DebtOrder.RATE_LOW.sorted(debts).map { it.id })
    }
}
