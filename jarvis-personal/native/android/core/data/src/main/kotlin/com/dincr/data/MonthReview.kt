package com.dincr.data

import java.math.BigDecimal
import java.time.LocalDate

/**
 * RV-1 — Revisión del mes, easy to understand: the month that just closed in three short cards. How it
 * went (what was left, compared with the month before), what you achieved (debt paid and money put
 * aside) and one thing to do this month. Every figure is the month's own summary (`/free/monthly-summary`,
 * the same Resumen del mes counts); this file only words it. Unknown figures are not read as 0.
 * iOS twin: `MonthReview.swift`.
 */
object MonthReview {
    data class Card(val title: String, val lines: List<String>)

    /** What was left: income minus spending and debt payments; null while income or spending is unknown. */
    fun left(summary: MonthlySummary): BigDecimal? {
        val income = summary.income ?: return null
        val expenses = summary.expenses ?: return null
        return income - expenses - (summary.debtPaid ?: BigDecimal.ZERO)
    }

    fun cards(summary: MonthlySummary, previous: MonthlySummary?, format: MoneyFormat, language: AppLanguage = AppLanguage.current()): List<Card> {
        val month = OwnerReading.monthLabel(summary.period.orEmpty(), language)
        val left = left(summary)
        val how = mutableListOf<String>()
        if (left != null) {
            how += if (left.signum() >= 0) language.pick("Te sobraron ${format.format(left)}.", "You had ${format.format(left)} left over.")
            else language.pick("Salió ${format.format(left.negate())} más de lo que entró.", "${format.format(left.negate())} more went out than came in.")
            previous?.let(::left)?.let { before ->
                val change = left - before
                how += when (change.signum()) {
                    1 -> language.pick("Es ${format.format(change)} mejor que el mes anterior.", "That is ${format.format(change)} better than the month before.")
                    -1 -> language.pick("Es ${format.format(change.negate())} menos que el mes anterior.", "That is ${format.format(change.negate())} less than the month before.")
                    else -> language.pick("Igual que el mes anterior.", "The same as the month before.")
                }
            }
        } else {
            how += language.pick("Faltan los ingresos o los gastos de este mes para saberlo.", "This month’s income or expenses are missing to know it.")
        }
        val achieved = mutableListOf<String>()
        summary.debtPaid?.takeIf { it.signum() > 0 }?.let { achieved += language.pick("Pagaste ${format.format(it)} de deudas.", "You paid ${format.format(it)} of debts.") }
        summary.saved?.total?.takeIf { it.signum() > 0 }?.let { achieved += language.pick("Guardaste ${format.format(it)}.", "You put aside ${format.format(it)}.") }
        if (achieved.isEmpty()) achieved += language.pick("Este mes no hubo pagos de deudas ni ahorro registrados.", "No debt payments or savings were recorded this month.")
        return listOf(
            Card(language.pick("Cómo te fue en $month", "How $month went"), how),
            Card(language.pick("Lo que lograste", "What you achieved"), achieved),
            Card(language.pick("Para este mes", "For this month"), listOf(action(summary, left, format, language))),
        )
    }

    /** One thing to do, from the month's own figures (a rule, not advice). */
    fun action(summary: MonthlySummary, left: BigDecimal?, format: MoneyFormat, language: AppLanguage): String {
        if (left != null && left.signum() < 0) {
            val top = summary.topCategory
            val name = top?.category
            val amount = top?.amount
            return if (name != null && amount != null) language.pick("Tu gasto más grande fue $name (${format.format(amount)}). Bajarlo un poco es lo que más ayuda.",
                "Your biggest spending was $name (${format.format(amount)}). Lowering it a little helps the most.")
            else language.pick("Revisá en qué se fue la plata en Resumen del mes y elegí un gasto para bajar.", "Check where the money went in Monthly summary and pick one expense to lower.")
        }
        if ((summary.saved?.total ?: BigDecimal.ZERO).signum() <= 0) {
            return language.pick("Apenas entre tu salario, apartá algo para tu Salvavidas o una meta, aunque sea poco.",
                "As soon as your pay comes in, put something aside for your emergency fund or a goal, even a little.")
        }
        return language.pick("Seguí igual: mantené lo que guardás y tus pagos de deudas al día.", "Keep it up: keep saving and keep your debt payments up to date.")
    }

    /** The month that just closed (`YYYY-MM`) and the one before it. */
    fun closedMonths(today: LocalDate): Pair<String, String> =
        today.minusMonths(1).toString().take(7) to today.minusMonths(2).toString().take(7)
}
