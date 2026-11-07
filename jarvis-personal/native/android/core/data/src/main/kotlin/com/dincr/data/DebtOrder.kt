package com.dincr.data

import java.math.BigDecimal

/**
 * How the Owner orders his debts (OW-3): as saved, by balance or by annual rate, either way.
 * An unknown balance or rate is never read as 0: those debts go last in both directions.
 * iOS: `DebtOrder`.
 */
enum class DebtOrder {
    SAVED, BALANCE_HIGH, BALANCE_LOW, RATE_HIGH, RATE_LOW;

    fun sorted(debts: List<Debt>): List<Debt> = when (this) {
        SAVED -> debts
        BALANCE_HIGH -> order(debts, descending = true) { it.remainingAmount }
        BALANCE_LOW -> order(debts, descending = false) { it.remainingAmount }
        RATE_HIGH -> order(debts, descending = true) { it.rateForEditing }
        RATE_LOW -> order(debts, descending = false) { it.rateForEditing }
    }

    /** Stable: equal values keep the saved order; unknown values keep it too, after the known ones. */
    private fun order(debts: List<Debt>, descending: Boolean, value: (Debt) -> BigDecimal?): List<Debt> {
        val known = debts.filter { value(it) != null }
        val sorted = if (descending) known.sortedByDescending { value(it) } else known.sortedBy { value(it) }
        return sorted + debts.filter { value(it) == null }
    }
}
