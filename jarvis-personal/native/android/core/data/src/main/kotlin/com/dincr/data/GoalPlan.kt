package com.dincr.data

import java.math.BigDecimal
import java.math.RoundingMode
import java.time.LocalDate

/**
 * GO-1 — every goal says, in plain words, what it takes: how much per month to reach it by its date,
 * and (VIP and the Owner) how long it takes with what is left in a normal month
 * ([FinancialReading.Normal.left]). Only known amounts are used: an unknown amount saved says nothing.
 * iOS twin: `GoalPlan.swift`.
 */
object GoalPlan {
    /** What is left over the months until the target date's month (at least one); null without a future date or with nothing left. */
    fun monthlyNeeded(goal: Goal, today: LocalDate): BigDecimal? {
        val remaining = goal.remaining ?: return null
        val months = monthsUntil(goal.targetDate, today) ?: return null
        if (remaining.signum() <= 0 || months < 0) return null
        return remaining.divide(BigDecimal(maxOf(months, 1)), 2, RoundingMode.HALF_UP)
    }

    /** The goal's plan in one or two short lines. */
    fun lines(goal: Goal, today: LocalDate, normalLeft: BigDecimal?, format: MoneyFormat, language: AppLanguage = AppLanguage.current()): List<String> {
        val remaining = goal.remaining
        if (goal.status == "completed" || remaining?.signum() == 0) return listOf(language.pick("¡Meta cumplida!", "Goal reached!"))
        if (remaining == null) return emptyList()
        val lines = mutableListOf<String>()
        val months = monthsUntil(goal.targetDate, today)
        if (months != null) {
            val month = OwnerReading.monthLabel(goal.targetDate!!.take(7), language)
            if (months < 0) lines += language.pick("La fecha ya pasó y te faltan ${format.format(remaining)}. Cambiala para recalcular.",
                "The date has passed and ${format.format(remaining)} is still missing. Change it to recalculate.")
            else monthlyNeeded(goal, today)?.let { needed ->
                lines += language.pick("Para llegar en $month necesitás ${format.format(needed)} por mes.", "To get there by $month you need ${format.format(needed)} a month.")
            }
        } else {
            lines += language.pick("Poné una fecha para saber cuánto guardar por mes.", "Set a date to know how much to save each month.")
        }
        if (normalLeft != null) {
            if (normalLeft.signum() > 0) {
                val count = remaining.divide(normalLeft, 0, RoundingMode.CEILING).toInt()
                lines += language.pick("Con lo que te sobra en un mes normal (${format.format(normalLeft)}) llegás en $count ${if (count == 1) "mes" else "meses"}.",
                    "With what is left in a normal month (${format.format(normalLeft)}) you get there in $count ${if (count == 1) "month" else "months"}.")
            } else {
                lines += language.pick("Hoy no te sobra plata en un mes normal: primero hay que liberar algo.", "Nothing is left in a normal month today: something has to be freed first.")
            }
        }
        return lines
    }

    /** Whole months from this month to the date's month; null without a date. */
    fun monthsUntil(date: String?, today: LocalDate): Int? {
        val parts = date?.take(7)?.split("-")?.mapNotNull { it.toIntOrNull() } ?: return null
        if (parts.size != 2) return null
        return (parts[0] - today.year) * 12 + (parts[1] - today.monthValue)
    }
}
