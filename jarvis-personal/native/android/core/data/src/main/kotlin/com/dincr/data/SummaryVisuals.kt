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
        Composition(categoryItems(summary, language))

    private fun categoryItems(summary: MonthlySummary, language: AppLanguage) = summary.categories.mapIndexed { index, row ->
        val label = row.category?.takeIf { it.isNotEmpty() } ?: language.pick("Sin categoría", "Uncategorized")
        CompositionItem("$index-$label", label, row.amount)
    }

    /** "¿De dónde entró?": the period's income by category (`income_categories`, largest first). */
    fun incomeSources(summary: MonthlySummary, language: AppLanguage = AppLanguage.current()): Composition =
        Composition(summary.incomeCategories.mapIndexed { index, row ->
            val label = row.category?.takeIf { it.isNotEmpty() } ?: language.pick("Sin categoría", "Uncategorized")
            CompositionItem("in-$index-$label", label, row.amount)
        })

    /**
     * "¿A dónde se fue?": spending by category, then debt payments and what was saved, each only when
     * the backend sent it above zero (an unknown amount is never drawn as zero).
     */
    fun outflows(summary: MonthlySummary, language: AppLanguage = AppLanguage.current()): Composition {
        val named = mutableListOf<CompositionItem>()
        summary.debtPaid?.takeIf { it.signum() > 0 }?.let { named += CompositionItem("out-debts", language.pick("Pagos de deudas", "Debt payments"), it) }
        summary.saved?.total?.takeIf { it.signum() > 0 }?.let { named += CompositionItem("out-saved", language.pick("Ahorro", "Savings"), it) }
        return Composition(groupingSmallest(categoryItems(summary, language), named, language))
    }

    /** The most parts the stacked bar shows, one color each (`BAR_COLORS_*`). */
    internal const val BAR_PARTS = 6

    /**
     * Past [BAR_PARTS], the largest categories keep their name and the rest become one "Otros", last
     * so it takes the bar's gray; debts and savings are never hidden in it. A category the backend
     * already calls "Otros" joins it, so the legend never shows two. An unknown or negative amount is
     * not summed: the parts stay as they are and [Composition] says why it can't draw them.
     */
    private fun groupingSmallest(categories: List<CompositionItem>, alwaysNamed: List<CompositionItem>, language: AppLanguage): List<CompositionItem> {
        if (categories.size + alwaysNamed.size <= BAR_PARTS || categories.any { (it.value?.signum() ?: -1) < 0 }) return categories + alwaysNamed
        val isOthers = { item: CompositionItem -> item.label.lowercase() in setOf("otros", "otro", "others", "other") }
        val largestFirst = categories.filterNot(isOthers).sortedByDescending { it.value }
        val kept = largestFirst.take(BAR_PARTS - 1 - alwaysNamed.size)
        val rest = largestFirst.drop(kept.size) + categories.filter(isOthers)
        val others = CompositionItem("out-others", language.pick("Otros", "Other"), rest.fold(BigDecimal.ZERO) { sum, item -> sum + item.value!! }, parts = rest)
        return kept + alwaysNamed + others
    }

    fun flowNotice(flow: Flow, language: AppLanguage = AppLanguage.current()): String? = when (flow) {
        is Flow.Bars -> null
        Flow.Incomplete -> language.pick("Faltan los ingresos o los gastos de este mes, así que no los comparamos.",
            "This month’s income or expenses are missing, so they aren’t compared.")
        Flow.Empty -> language.pick("Todavía no hay ingresos ni gastos registrados en este mes.",
            "No income or expenses recorded this month yet.")
    }
}
