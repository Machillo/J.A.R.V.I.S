package com.dincr.data

import java.math.BigDecimal
import java.math.RoundingMode

/**
 * How much of the debts has been paid, from the backend's own amounts: the original amount
 * (`total_amount`) minus what is left (`remaining_amount`). Unknown ≠ 0: a debt without a known
 * original amount has no progress, and the total exists only when every debt's is known.
 * iOS: `DebtProgress`.
 */
object DebtProgress {
    data class Amounts(val paid: BigDecimal, val original: BigDecimal) {
        /** Paid as a fraction of the original amount (0...1). */
        val ratio: Double get() = if (original.signum() > 0) paid.divide(original, 6, RoundingMode.HALF_UP).toDouble() else 0.0
        /** What is left, as a fraction of the original amount (0...1). */
        val remainingFraction: Double get() = if (original.signum() > 0) original.subtract(paid).divide(original, 6, RoundingMode.HALF_UP).toDouble() else 0.0
    }

    /** One debt's paid and original amounts, or null when the original amount or the balance is unknown. */
    fun of(debt: Debt): Amounts? {
        val original = debt.totalAmount?.takeIf { it.signum() > 0 } ?: return null
        val remaining = debt.remainingAmount ?: return null
        return Amounts(original.subtract(remaining).max(BigDecimal.ZERO), original)
    }

    /** All the debts together, or null when any debt's amounts are unknown (never a partial sum shown as the total). */
    fun total(debts: List<Debt>): Amounts? {
        if (debts.isEmpty()) return null
        var paid = BigDecimal.ZERO
        var original = BigDecimal.ZERO
        for (debt in debts) {
            val amounts = of(debt) ?: return null
            paid += amounts.paid; original += amounts.original
        }
        return Amounts(paid, original)
    }

    /**
     * The debt-free date of the plan's strategy (Owner and VIP dashboards), as the backend sends it.
     * [date]: `YYYY-MM-DD` or null when the strategy cannot estimate it. [monthsSaved]: months earlier
     * than paying only the installments. [needsRates]: the strategy waits for a debt's interest rate.
     */
    data class StrategyDate(val date: String?, val monthsSaved: Int?, val needsRates: Boolean)

    /** Only a dashboard strategy has a debt-free date; Basic and Free have none (null). */
    fun strategyDate(strategy: DirectorStrategy?): StrategyDate? =
        strategy?.let { StrategyDate(it.estimatedDebtFreeDate, it.monthsSavedByCurrentExtras, it.needsDebtRates) }
}
