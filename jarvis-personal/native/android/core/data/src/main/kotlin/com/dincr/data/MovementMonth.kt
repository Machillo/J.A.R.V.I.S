package com.dincr.data

import java.math.BigDecimal

/**
 * Movimientos shows one month at a time (the current one when it opens), not the whole history.
 * The backend still returns every movement; this narrows what is on screen. A search looks through
 * every month, so an old movement can still be found by name. iOS: `MovementMonth.swift`.
 */
object MovementMonth {
    /** With a search, every month; without one, only [month] (`YYYY-MM`). */
    fun rows(rows: List<Movement>, month: String, query: String): List<Movement> {
        val searching = query.isNotBlank()
        return rows.filter { searching || it.day.orEmpty().startsWith(month) }
    }
}

/**
 * What the rows on screen add up to, in the base currency: the running totals of Movimientos. Only
 * what is registered in the list: a dollar expense waiting for its close has no colones amount and is
 * not a row here, and no row of a kind is unknown, never ₡0. iOS: `MovementTotals`.
 */
data class MovementTotals(val income: BigDecimal?, val expenses: BigDecimal?, val debtPaid: BigDecimal?) {
    /** Income minus expenses and debt payments; null while either side is unknown. */
    val result: BigDecimal? get() = if (income == null || expenses == null) null else income - expenses - (debtPaid ?: BigDecimal.ZERO)

    /** With the estimate of the waiting dollars in the expenses. Nothing to add leaves them as they are. */
    fun addingEstimate(estimate: BigDecimal?): MovementTotals =
        if (estimate == null) this else copy(expenses = (expenses ?: BigDecimal.ZERO) + estimate)

    companion object {
        fun of(rows: List<Movement>): MovementTotals {
            var income: BigDecimal? = null
            var expenses: BigDecimal? = null
            var debtPaid: BigDecimal? = null
            for (row in rows) {
                // The Owner's rows say what they count as: a transfer or a loan is neither income nor spending.
                when (row.countsIn ?: row.transactionType) {
                    "income" -> income = (income ?: BigDecimal.ZERO) + row.amount
                    "expense", "expenses" -> expenses = (expenses ?: BigDecimal.ZERO) + row.amount
                    "refunds" -> expenses = (expenses ?: BigDecimal.ZERO) - row.amount
                    "debt_payments" -> debtPaid = (debtPaid ?: BigDecimal.ZERO) + row.amount
                }
            }
            return MovementTotals(income, expenses?.max(BigDecimal.ZERO), debtPaid)
        }
    }
}
