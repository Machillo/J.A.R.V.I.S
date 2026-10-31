package com.dincr.data

import java.math.BigDecimal
import java.time.LocalDate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * NT-1 — the reminders the phone schedules: the day before a debt's or fixed expense's day, the day
 * of a Salvavidas contribution, and the first day of each month. Only recorded dates; nothing
 * guessed. The Swift twin is `RemindersTests`. Synthetic data.
 */
class RemindersTest {
    private val colones = MoneyFormat("CRC", MoneyFormat.Separators.DOT_COMMA)
    private val es = AppLanguage.SPANISH
    private fun day(reminder: Reminders.Reminder) = reminder.at.toLocalDate().toString()

    @Test fun onlyActiveDebtsWithAPaymentDayGiveReminders() {
        val debts = listOf(
            Debt(1, "Préstamo", remainingAmount = BigDecimal(500000), monthlyPayment = BigDecimal(45000), paymentDay = 15),
            Debt(2, "Pagada", remainingAmount = BigDecimal.ZERO, monthlyPayment = BigDecimal(10000), paymentDay = 10),
            Debt(3, "Sin día", remainingAmount = BigDecimal(100000), monthlyPayment = BigDecimal(10000)),
        )
        assertEquals(listOf("debt-1"), Reminders.bills(debts).map { it.id })
    }

    @Test fun theDayBeforeEachDueDayInsideTheWindow() {
        val bills = listOf(Reminders.Bill("debt-1", Reminders.Bill.Kind.DEBT, "Préstamo", BigDecimal(45000), 15),
            Reminders.Bill("fixed-7", Reminders.Bill.Kind.FIXED, "Internet", null, 31))
        val plan = Reminders.plan(LocalDate.of(2026, 11, 1), bills, null, colones, language = es).filterNot { it.id.contains(".month.") }
        // 31 November is the 30th, so its reminder is the 29th; 14 December is outside the 35 days.
        assertEquals(listOf("2026-11-14", "2026-11-29"), plan.map(::day))
        assertEquals("Mañana vence una cuota", plan[0].title)
        assertEquals("Préstamo (₡45.000). Tenela lista.", plan[0].body)
        assertEquals("Internet.", plan[1].body)
        assertTrue(plan.all { it.at.hour == 9 })
    }

    @Test fun aDueDayAlreadyPassedThisMonthIsRemindedNextMonth() {
        val bills = listOf(Reminders.Bill("debt-1", Reminders.Bill.Kind.DEBT, "Préstamo", null, 5))
        assertEquals(listOf("2026-12-04"), Reminders.plan(LocalDate.of(2026, 11, 10), bills, null, colones, language = es)
            .filter { it.id.startsWith("dincr.reminder.debt") }.map(::day))
    }

    @Test fun theSalvavidasContributionDays() {
        val weekly = Salvavidas.AutoContribution(enabled = true, amount = BigDecimal(2500), frequency = "weekly", startDate = "2026-10-03")
        val plan = Reminders.plan(LocalDate.of(2026, 11, 1), emptyList(), weekly, colones, days = 14, language = es).filter { it.id.contains("salvavidas") }
        assertEquals(listOf("2026-11-07", "2026-11-14"), plan.map(::day))
        assertEquals("₡2.500 para tu Salvavidas.", plan[0].body)
        assertTrue(Reminders.plan(LocalDate.of(2026, 11, 1), emptyList(), weekly.copy(enabled = false), colones, days = 14).isEmpty())
    }

    @Test fun theFirstDayOfTheNextMonthSaysTheMonthClosed() {
        val plan = Reminders.plan(LocalDate.of(2026, 11, 20), emptyList(), null, colones, language = es)
        assertEquals(listOf("2026-12-01"), plan.map(::day))
        assertEquals("Tu mes cerró", plan[0].title)
    }

    @Test fun neverMoreThanTheLimitAndEarliestFirst() {
        val bills = (1..40).map { Reminders.Bill("fixed-$it", Reminders.Bill.Kind.FIXED, "G$it", null, (it % 28) + 1) }
        val plan = Reminders.plan(LocalDate.of(2026, 11, 1), bills, null, colones, days = 60)
        assertEquals(Reminders.LIMIT, plan.size)
        assertEquals(plan.map(::day).sorted(), plan.map(::day))
        assertEquals(plan.size, plan.map { it.id }.toSet().size)
    }
}
