package com.dincr.data

import kotlinx.serialization.Serializable

// How the Owner's figures read (Owner information clarity). One wording per concept, shared by
// every screen that shows it, so "Resumen del mes", "Análisis financiero" and "Tu plan del mes"
// never explain the same figure two ways. Wording only: every amount is the backend's.
// iOS: `OwnerReading`.

/** An inclusive date range (`YYYY-MM-DD`), as the backend sends it. */
@Serializable
data class DatePeriod(val start: String? = null, val end: String? = null)

object OwnerReading {
    /** Why a month is not complete (backend owner_ledger codes), in plain words. */
    // One is singular; zero, several and an unknown count ("algunos") are plural.
    fun incompleteReason(code: String, pendingMail: Int?, unclassified: Int?, language: AppLanguage = AppLanguage.current()): String = when (code) {
        "pending_mail_review" -> if (pendingMail == 1) language.pick(
            "Hay 1 aviso de correo de este mes sin revisar: su monto todavía no cuenta.",
            "There is 1 mail notice from this month not reviewed yet: its amount doesn’t count yet.")
        else language.pick(
            "Hay ${pendingMail ?: "algunos"} avisos de correo de este mes sin revisar: sus montos todavía no cuentan.",
            "There are ${pendingMail ?: "some"} mail notices from this month not reviewed yet: their amounts don’t count yet.")
        "unclassified_movements" -> if (unclassified == 1) language.pick(
            "Hay 1 movimiento sin clasificar (por ejemplo una transferencia): no suma como ingreso ni como gasto.",
            "There is 1 unclassified movement (a transfer, for example): it counts neither as income nor as spending.")
        else language.pick(
            "Hay ${unclassified ?: "algunos"} movimientos sin clasificar (por ejemplo transferencias): no suman como ingreso ni como gasto.",
            "There are ${unclassified ?: "some"} unclassified movements (transfers, for example): they count neither as income nor as spending.")
        "payroll_without_deposit" -> language.pick(
            "Hay nómina registrada (horas extra o bonos) sin el depósito del salario de este mes.",
            "There is payroll recorded (overtime or bonuses) without this month’s salary deposit.")
        else -> language.pick("Falta información para cerrar este mes.", "Some information is missing to close this month.")
    }

    /** A `YYYY-MM` month as the analysis lists it ("oct 2026", "Oct 2026"); anything else as it came. iOS: `OwnerReading.monthLabel`. */
    fun monthLabel(period: String, language: AppLanguage = AppLanguage.current()): String {
        val parts = period.split("-")
        val month = parts.getOrNull(1)?.toIntOrNull()
        if (parts.size != 2 || parts[0].length != 4 || parts[0].toIntOrNull() == null || month == null || month !in 1..12) return period
        val spanish = listOf("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic")
        val english = listOf("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
        return "${language.pick(spanish[month - 1], english[month - 1])} ${parts[0]}"
    }

    /** The months of a series that are not complete yet, in calendar order. */
    /** How a month with nothing pending reads: no movements (unknown, not zero), in progress, or closed. */
    enum class MonthState { NO_MOVEMENTS, IN_PROGRESS, CLOSED }

    fun monthState(s: MonthlySummary, currentMonth: String): MonthState = when {
        listOf(s.income, s.expenses, s.grossExpenses, s.debtPaid, s.otherInflows).all { (it?.signum() ?: 0) == 0 } -> MonthState.NO_MOVEMENTS
        s.period == currentMonth -> MonthState.IN_PROGRESS
        else -> MonthState.CLOSED
    }

    /** Gross payroll is worth showing when any part of it is not zero (the parts can cancel out in the total). */
    fun hasPayroll(p: PayrollAccrued): Boolean =
        listOf(p.overtimeGross, p.vghGross, p.bonusesGross, p.totalGross).any { (it?.signum() ?: 0) != 0 }

    fun incompleteMonths(flow: List<TransactionAnalysis.FlowMonth>): List<String> =
        flow.filter { it.complete == false }.mapNotNull { it.month?.takeIf(String::isNotEmpty) }

    /**
     * A strategy's formula line, labelled for whose formula it is. The Owner's `income` line is the
     * income still to come in the cycle (backend `remaining_income_current_cycle`), not the month's
     * income; Users keep the shared label.
     */
    fun formulaLabel(key: String, strategy: DirectorStrategy, language: AppLanguage = AppLanguage.current()): String = when {
        strategy.isOwnerScope && key == "income" -> language.pick("Ingresos por recibir en el ciclo", "Income still to come this cycle")
        strategy.isOwnerScope && key == "cash_available_now" -> language.pick("Efectivo en tu cuenta de distribución", "Cash in your distribution account")
        strategy.isOwnerScope && key == "statement_spending" -> language.pick("Gastos del período del estado de cuenta", "Spending in the statement period")
        strategy.isOwnerScope && key == "new_spending_after_cut" -> language.pick("Gastos después del corte", "Spending after the statement cut")
        else -> Distribution.formulaLabel(key, language)
    }
}
