package com.dincr.data

import java.math.BigDecimal

/**
 * E04 / E05 — what Movimientos → Análisis → Resumen del mes draws from the month's own summary
 * (`GET /user-product/free/monthly-summary`), nothing else. E04 compares the selected month's income
 * and expenses as bars; E05 splits its expenses by category as a donut. The amounts above them stay
 * as the readable alternative. An unknown amount is never drawn as zero, no category or amount is
 * made up, and a share exists only when every category is known ([Composition]). The donut's
 * segments are not links yet (a filtered movement list needs P5.1). iOS: `SummaryVisuals`.
 */
object SummaryVisuals {
    /** E04: the month's income and expenses. */
    sealed interface Flow {
        /** Both are known and something was recorded: two bars. */
        data class Bars(val month: String, val income: BigDecimal, val expenses: BigDecimal) : Flow
        /** Income or expenses unknown: no bars (one bar alone is not a comparison, an unknown is not 0). */
        data object Incomplete : Flow
        /** Both known and zero: nothing was recorded this month. */
        data object Empty : Flow
    }

    fun flow(summary: MonthlySummary): Flow {
        val income = summary.income ?: return Flow.Incomplete
        val expenses = summary.expenses ?: return Flow.Incomplete
        if (income.signum() == 0 && expenses.signum() == 0) return Flow.Empty
        return Flow.Bars(summary.period.orEmpty(), income, expenses)
    }

    /**
     * E05: the month's expenses by category, in the backend's order (largest first). A category
     * without an amount stays unknown, so the donut and its shares are not drawn.
     */
    fun categories(summary: MonthlySummary, language: AppLanguage = AppLanguage.current()): Composition =
        Composition(summary.categories.mapIndexed { index, row ->
            val label = row.category?.takeIf { it.isNotEmpty() } ?: language.pick("Sin categoría", "Uncategorized")
            CompositionItem("$index-$label", label, row.amount)
        })

    fun flowNotice(flow: Flow, language: AppLanguage = AppLanguage.current()): String? = when (flow) {
        is Flow.Bars -> null
        Flow.Incomplete -> language.pick("Faltan los ingresos o los gastos de este mes, así que no los comparamos.",
            "This month’s income or expenses are missing, so they aren’t compared.")
        Flow.Empty -> language.pick("Todavía no hay ingresos ni gastos registrados en este mes.",
            "No income or expenses recorded this month yet.")
    }
}
