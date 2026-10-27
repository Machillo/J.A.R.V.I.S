package com.dincr.data

import java.math.BigDecimal

/**
 * When the debts are expected to be paid off, from the backend's per-debt estimate
 * (`Debt.estimatedPayoffDate`, debt_payoff.py). Nothing is calculated here: the debt-free month is
 * the latest of the backend's dates, and only when every unpaid debt has one (UNKNOWN ≠ a date).
 * iOS: `DebtPayoff`.
 */
object DebtPayoff {
    /**
     * [debtFreeDate]: `YYYY-MM-DD` of the last installment of all, or null when some unpaid debt has
     * no estimate. [unestimated]: unpaid debts the backend could not estimate. [active]: unpaid debts.
     */
    data class Summary(val debtFreeDate: String?, val unestimated: Int, val active: Int)

    fun summary(debts: List<Debt>): Summary {
        val active = debts.filter { (it.remainingAmount ?: BigDecimal.ZERO).signum() > 0 }
        val dates = active.mapNotNull { it.estimatedPayoffDate }
        val unestimated = active.size - dates.size
        return Summary(if (unestimated == 0) dates.maxOrNull() else null, unestimated, active.size)
    }

    /** "oct 2027" / "Oct 2027" for a `YYYY-MM-DD` date. */
    fun monthLabel(date: String, language: AppLanguage = AppLanguage.current()): String =
        OwnerReading.monthLabel(date.take(7), language)
}
