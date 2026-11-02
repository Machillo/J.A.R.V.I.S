package com.dincr.data

import java.math.BigDecimal
import java.time.LocalDate
import java.time.LocalDateTime

/**
 * NT-1 — reminders on the phone (local notifications, no server): what the app already knows, said
 * before it happens. The day before a debt's payment day and a fixed expense's due day, the day of a
 * Salvavidas automatic contribution, the day a locked savings block for a debt matures (the Owner's,
 * DB-1), the day the bank says what it did with an extra payment, and the first day of a month ("your
 * month closed"). Only dates
 * the user recorded (a debt without a payment day gives none); nothing is guessed. The app schedules
 * them on the phone (`ReminderScheduler`); this file only decides which and when, so both apps say
 * the same. iOS twin: `Reminders.swift`.
 */
object Reminders {
    data class Reminder(val id: String, val at: LocalDateTime, val title: String, val body: String)

    /** A bill paid every month on a day: a debt's installment or a fixed expense. */
    data class Bill(val id: String, val kind: Kind, val name: String, val amount: BigDecimal?, val day: Int) {
        enum class Kind { DEBT, FIXED }
    }

    const val MORNING_HOUR = 9
    /** Kept in line with iOS (at most 64 pending notifications per app). */
    const val LIMIT = 60

    /** The bills with a known day: active debts with an installment day, and fixed expenses with a due day. */
    fun bills(debts: List<Debt>, fixed: List<Bill> = emptyList()): List<Bill> =
        debts.mapNotNull { debt ->
            val day = debt.paymentDay ?: return@mapNotNull null
            if ((debt.remainingAmount ?: BigDecimal.ZERO).signum() <= 0 || day !in 1..31) return@mapNotNull null
            Bill("debt-${debt.id}", Bill.Kind.DEBT, debt.name.orEmpty(), debt.monthlyPayment, day)
        } + fixed.filter { it.day in 1..31 }

    /** Every reminder from [today] to [days] ahead, earliest first, at most [LIMIT]. */
    fun plan(today: LocalDate, bills: List<Bill>, saving: Salvavidas.AutoContribution?, format: MoneyFormat,
             days: Int = 35, language: AppLanguage = AppLanguage.current(),
             blocks: List<DebtSavingsBlocks.Block> = emptyList(),
             waiting: List<Triple<Long, String, String>> = emptyList()): List<Reminder> {
        val end = today.plusDays(days.toLong())
        val result = mutableListOf<Reminder>()

        // The day before each bill's due day, in this month and the next ones within the window.
        for (bill in bills) {
            for (offset in 0..2L) {
                val month = today.withDayOfMonth(1).plusMonths(offset)
                val due = month.withDayOfMonth(minOf(bill.day, month.lengthOfMonth()))
                val notify = due.minusDays(1)
                if (notify < today || !notify.isBefore(end)) continue
                val amount = bill.amount?.let { " (${format.format(it)})" } ?: ""
                val debt = bill.kind == Bill.Kind.DEBT
                result += Reminder("dincr.reminder.${bill.id}.$due", notify.atTime(MORNING_HOUR, 0),
                    if (debt) language.pick("Mañana vence una cuota", "A payment is due tomorrow") else language.pick("Mañana se paga un gasto fijo", "A fixed expense is due tomorrow"),
                    if (debt) language.pick("${bill.name}$amount. Tenela lista.", "${bill.name}$amount. Have it ready.") else "${bill.name}$amount.")
            }
        }

        // The Salvavidas automatic contributions inside the window.
        val amount = saving?.amount
        val first = saving?.startDate?.take(10)?.let { runCatching { LocalDate.parse(it) }.getOrNull() }
        if (saving?.enabled == true && amount != null && amount.signum() > 0 && first != null) {
            val stop = saving.endDate?.take(10)?.let { runCatching { LocalDate.parse(it) }.getOrNull() }?.let { minOf(it, end) } ?: end
            var index = 0L
            while (index < 400) {
                val date = when (saving.frequency) {
                    "weekly" -> first.plusWeeks(index)
                    "biweekly" -> first.plusWeeks(2 * index)
                    "monthly" -> first.plusMonths(index)
                    else -> break
                }
                if (!date.isBefore(stop)) break
                if (!date.isBefore(today)) result += Reminder("dincr.reminder.salvavidas.$date", date.atTime(MORNING_HOUR, 0),
                    language.pick("Hoy toca tu aporte al Salvavidas", "Your emergency fund contribution is today"),
                    language.pick("${format.format(amount)} para tu Salvavidas.", "${format.format(amount)} for your emergency fund."))
                index++
            }
        }

        // The day each locked savings block matures: pay what it holds into its debt.
        for (block in blocks) {
            val date = block.maturityDate?.take(10)?.let { runCatching { LocalDate.parse(it) }.getOrNull() } ?: continue
            if (date < today || !date.isBefore(end)) continue
            val debt = block.debtName ?: language.pick("tu deuda", "your debt")
            val total = format.format(block.totalAtMaturity ?: BigDecimal.ZERO)
            result += Reminder("dincr.reminder.block.${block.id}.$date", date.atTime(MORNING_HOUR, 0),
                language.pick("Hoy vence tu ahorro bloqueado", "Your locked saving matures today"),
                language.pick("Abonale $total a $debt.", "Pay $total into $debt."))
        }

        // The day the bank says what it did with an extra payment: complete the debt.
        for ((id, debt, text) in waiting) {
            val date = runCatching { LocalDate.parse(text.take(10)) }.getOrNull() ?: continue
            if (date < today || !date.isBefore(end)) continue
            result += Reminder("dincr.reminder.afterextra.$id.$date", date.atTime(MORNING_HOUR, 0),
                language.pick("¿Ya te dijo el banco?", "Did the bank tell you?"),
                language.pick("Contale a DINCR la cuota o el plazo nuevo de $debt.", "Tell DINCR the new installment or term of $debt."))
        }

        // The first day of each next month: the month that ended.
        for (offset in 1..2L) {
            val firstDay = today.withDayOfMonth(1).plusMonths(offset)
            if (firstDay < today || !firstDay.isBefore(end)) continue
            result += Reminder("dincr.reminder.month.$firstDay", firstDay.atTime(MORNING_HOUR, 0),
                language.pick("Tu mes cerró", "Your month closed"),
                language.pick("Mirá cuánto entró, cuánto salió y cuánto guardaste.", "See what came in, what went out and what you saved."))
        }

        return result.sortedWith(compareBy<Reminder>({ it.at }, { it.id })).take(LIMIT)
    }
}
