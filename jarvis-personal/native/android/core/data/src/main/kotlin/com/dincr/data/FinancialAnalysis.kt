package com.dincr.data

import java.math.BigDecimal
import java.math.RoundingMode
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// FA-1 — Movimientos → Análisis → Análisis financiero (VIP and the Owner): the last twelve months of
// the figures Resumen del mes shows (`GET /user-product/vip/financial-analysis`), read in plain words
// for people who do not know finance. The backend counts; this file only averages the months that can
// be compared and writes the sentences, so both apps say the same thing. Nothing here is advice: it
// describes the user's own numbers. iOS twin: `FinancialAnalysis.swift`.

/** `GET /user-product/vip/financial-analysis`. */
@Serializable
data class FinancialAnalysis(
    val months: List<Month> = emptyList(),
    val categories: List<Category> = emptyList(),
) {
    @Serializable
    data class Month(
        val period: String,
        val income: Money? = null,
        val expenses: Money? = null,
        @SerialName("debt_paid") val debtPaid: Money? = BigDecimal.ZERO,
        val saved: Money? = BigDecimal.ZERO,
        /** The month in course: it is not over, so it is never averaged. */
        val partial: Boolean = false,
    )

    /** This month's spending in a category beside its average in the last complete months (`average` null: nothing to compare with). */
    @Serializable
    data class Category(val category: String? = null, val current: Money? = null, val average: Money? = null)
}

object FinancialReading {
    /**
     * An average month: the complete months where both income and spending were recorded (a month
     * without one of them is missing data, not a month without money).
     */
    data class Normal(val months: Int, val income: BigDecimal, val expenses: BigDecimal, val debtPaid: BigDecimal, val saved: BigDecimal) {
        /** What is left: income minus spending and debt payments (saving comes out of it). */
        val left: BigDecimal get() = income - expenses - debtPaid
    }

    fun normal(analysis: FinancialAnalysis): Normal? {
        val counted = analysis.months.filter { !it.partial && (it.income ?: BigDecimal.ZERO).signum() > 0 && (it.expenses ?: BigDecimal.ZERO).signum() > 0 }
        if (counted.isEmpty()) return null
        fun average(value: (FinancialAnalysis.Month) -> BigDecimal?): BigDecimal =
            counted.fold(BigDecimal.ZERO) { sum, month -> sum + (value(month) ?: BigDecimal.ZERO) }
                .divide(BigDecimal(counted.size), 2, RoundingMode.HALF_UP).stripTrailingZeros()
        return Normal(counted.size, average { it.income }, average { it.expenses }, average { it.debtPaid }, average { it.saved })
    }

    /** How many of every 100 that come in: rounded to a whole number; null without income. */
    fun per100(part: BigDecimal, whole: BigDecimal): Int? =
        if (whole.signum() <= 0) null else part.multiply(BigDecimal(100)).divide(whole, 0, RoundingMode.HALF_UP).toInt()

    /** The months the bars draw: the ones with something recorded (an empty month is not drawn as 0). */
    fun chartMonths(analysis: FinancialAnalysis): List<MonthTotals> = analysis.months.mapNotNull { month ->
        val income = month.income ?: return@mapNotNull null
        val expenses = month.expenses ?: return@mapNotNull null
        if (income.signum() == 0 && expenses.signum() == 0) null else MonthTotals(month.period, income, expenses, month.debtPaid)
    }

    /**
     * The categories where this month already went above the average, the largest difference first
     * (at most [limit]). The month is not over, so a lower amount says nothing yet and is not listed.
     */
    fun rises(analysis: FinancialAnalysis, limit: Int = 3): List<FinancialAnalysis.Category> =
        analysis.categories.filter { row -> row.current != null && row.average != null && row.current > row.average }
            .sortedByDescending { it.current!! - it.average!! }
            .take(limit)

    /** Whether there is an earlier month to compare this one with. */
    fun canCompare(analysis: FinancialAnalysis): Boolean = analysis.categories.any { it.average != null }

    // Sentences

    fun leftSentence(normal: Normal, format: MoneyFormat, language: AppLanguage = AppLanguage.current()): String {
        val left = normal.left
        return when {
            left.signum() > 0 -> language.pick("En un mes normal te sobran ${format.format(left)}.", "In a normal month you have ${format.format(left)} left over.")
            left.signum() < 0 -> language.pick("En un mes normal sale ${format.format(left.negate())} más de lo que entra.",
                "In a normal month ${format.format(left.negate())} more goes out than comes in.")
            else -> language.pick("En un mes normal sale lo mismo que entra.", "In a normal month as much goes out as comes in.")
        }
    }

    fun leftExplanation(normal: Normal, format: MoneyFormat, language: AppLanguage = AppLanguage.current()): String {
        val months = if (normal.months == 1) language.pick("tu último mes completo", "your last complete month")
        else language.pick("tus últimos ${normal.months} meses completos", "your last ${normal.months} complete months")
        val income = format.format(normal.income)
        val expenses = format.format(normal.expenses)
        return if (normal.debtPaid.signum() > 0) {
            val debts = format.format(normal.debtPaid)
            language.pick("Entra $income, gastás $expenses y pagás $debts de deudas. Es el promedio de $months.",
                "$income comes in, you spend $expenses and pay $debts of debts. It is the average of $months.")
        } else {
            language.pick("Entra $income y gastás $expenses. Es el promedio de $months.", "$income comes in and you spend $expenses. It is the average of $months.")
        }
    }

    fun savedSentence(normal: Normal, language: AppLanguage = AppLanguage.current()): String? {
        val share = per100(normal.saved, normal.income) ?: return null
        return when {
            normal.saved.signum() <= 0 -> language.pick("Todavía no estás guardando parte de lo que entra.", "You are not saving part of what comes in yet.")
            share == 0 -> language.pick("Guardás menos de 1 de cada 100 que entran.", "You save less than 1 of every 100 that come in.")
            else -> language.pick("Guardás $share de cada 100 que entran.", "You save $share of every 100 that come in.")
        }
    }

    fun savedExplanation(language: AppLanguage = AppLanguage.current()): String =
        language.pick("Es lo que mandás a tus metas y a tu Salvavidas. Una referencia común es guardar al menos 10 de cada 100.",
            "It is what you put into your goals and your emergency fund. A common reference is saving at least 10 of every 100.")

    /** null when no debts were paid in a normal month. */
    fun debtSentence(normal: Normal, language: AppLanguage = AppLanguage.current()): String? {
        if (normal.debtPaid.signum() <= 0) return null
        val share = per100(normal.debtPaid, normal.income) ?: return null
        return language.pick("De cada 100 que entran, $share se van a pagar deudas.", "Of every 100 that come in, $share go to paying debts.")
    }

    fun debtExplanation(language: AppLanguage = AppLanguage.current()): String =
        language.pick("Mientras más bajo, más te queda libre para tus gastos y para guardar.", "The lower it is, the more you have free for your spending and for saving.")

    /** "Comida: ₡90.000 este mes · normalmente ₡60.000". */
    fun riseLine(row: FinancialAnalysis.Category, format: MoneyFormat, language: AppLanguage = AppLanguage.current()): String {
        val name = row.category?.takeIf { it.isNotEmpty() } ?: language.pick("Sin categoría", "Uncategorized")
        val current = format.format(row.current ?: BigDecimal.ZERO)
        val average = format.format(row.average ?: BigDecimal.ZERO)
        return language.pick("$name: $current este mes · normalmente $average", "$name: $current this month · usually $average")
    }
}
