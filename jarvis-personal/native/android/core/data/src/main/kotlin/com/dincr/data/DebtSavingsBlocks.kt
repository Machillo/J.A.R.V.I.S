package com.dincr.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * DB-1 — Plan → Ahorro para deudas (Owner only): locked savings blocks for the strategy's long debts.
 * The backend (`GET /jarvis/premium/debt-savings-blocks`, finance/debt_savings_blocks.py) decides
 * everything: which debt, how much every Thursday, for how long, what locking costs. This file only
 * decodes it and says it in short sentences, so both apps say the same. Recording a block created at
 * the bank (POST), removing one (DELETE) and, when it matures, recording what was paid into the debt
 * (POST …/apply) are the Owner's explicit actions. iOS twin:
 * `DebtSavingsBlocks.swift`.
 */
@Serializable
data class DebtSavingsBlocks(
    val status: String = "",
    @SerialName("weekly_safe_amount") val weeklySafeAmount: Money? = null,
    @SerialName("committed_weekly") val committedWeekly: Money? = null,
    val proposal: Proposal? = null,
    @SerialName("short_debts") val shortDebts: List<ShortDebt>? = null,
    val blocks: List<Block>? = null,
    val warnings: List<String>? = null,
) {
    @Serializable
    data class DebtRef(
        val id: Long? = null,
        val name: String? = null,
        @SerialName("remaining_amount") val remainingAmount: Money? = null,
        @SerialName("interest_rate") val interestRate: Money? = null,
    )

    @Serializable
    data class Recommendation(val choice: String? = null, val reason: String? = null)

    @Serializable
    data class Proposal(
        val mode: String? = null,
        val debt: DebtRef? = null,
        @SerialName("weekly_amount") val weeklyAmount: Money? = null,
        val contributions: Int? = null,
        @SerialName("term_months") val termMonths: Int? = null,
        @SerialName("start_date") val startDate: String? = null,
        @SerialName("maturity_date") val maturityDate: String? = null,
        @SerialName("total_saved") val totalSaved: Money? = null,
        @SerialName("abono_amount") val abonoAmount: Money? = null,
        @SerialName("balance_at_maturity") val balanceAtMaturity: Money? = null,
        @SerialName("balance_after_abono") val balanceAfterAbono: Money? = null,
        @SerialName("lock_cost") val lockCost: Money? = null,
        val recommendation: Recommendation? = null,
    )

    @Serializable
    data class ShortDebt(val id: Long? = null, val name: String? = null, @SerialName("payoff_month") val payoffMonth: Int? = null)

    @Serializable
    data class Block(
        val id: String,
        @SerialName("debt_id") val debtId: Long? = null,
        @SerialName("debt_name") val debtName: String? = null,
        val mode: String? = null,
        @SerialName("weekly_amount") val weeklyAmount: Money? = null,
        @SerialName("start_date") val startDate: String? = null,
        @SerialName("maturity_date") val maturityDate: String? = null,
        @SerialName("term_months") val termMonths: Int? = null,
        @SerialName("contributions_total") val contributionsTotal: Int? = null,
        @SerialName("contributions_done") val contributionsDone: Int? = null,
        @SerialName("saved_so_far") val savedSoFar: Money? = null,
        @SerialName("total_at_maturity") val totalAtMaturity: Money? = null,
        @SerialName("next_date") val nextDate: String? = null,
        val matured: Boolean? = null,
    )
}

/** `POST /jarvis/premium/debt-savings-blocks`: the block the Owner created at the bank. */
@Serializable
data class DebtSavingsBlockCreate(
    @SerialName("debt_id") val debtId: Long,
    @SerialName("weekly_amount") val weeklyAmount: Money,
    @SerialName("start_date") val startDate: String,
    @SerialName("term_months") val termMonths: Int,
    val mode: String? = null,
)

/** `POST /jarvis/premium/debt-savings-blocks/{id}/apply`: what was paid into the debt and what the bank did. */
@Serializable
data class DebtSavingsBlockApply(
    val amount: Money,
    val outcome: String,
    @SerialName("new_monthly_payment") val newMonthlyPayment: Money? = null,
    @SerialName("remaining_installments") val remainingInstallments: Int? = null,
    @SerialName("remind_on") val remindOn: String? = null,
) {
    companion object {
        const val REDUCE_TERM = "reduce_term"
        const val REDUCE_INSTALLMENT = "reduce_installment"
        const val LATER = "later"

        /** The new installment travels only when the bank lowered it; the installments left only after a shorter term;
         *  the day to be reminded only when the bank tells later. */
        fun of(amount: java.math.BigDecimal, outcome: String, newMonthlyPayment: java.math.BigDecimal?, remainingInstallments: Int? = null,
               remindOn: String? = null) =
            DebtSavingsBlockApply(amount, outcome, newMonthlyPayment.takeIf { outcome == REDUCE_INSTALLMENT },
                remainingInstallments.takeIf { outcome == REDUCE_TERM }, remindOn.takeIf { outcome == LATER })
    }
}

/** The answer of `…/apply`: the block, closed, with what was applied. */
@Serializable
data class DebtSavingsBlockApplied(val block: ClosedBlock) {
    @Serializable
    data class ClosedBlock(val id: String, val applied: Applied? = null)

    @Serializable
    data class Applied(
        val amount: Money? = null,
        val outcome: String? = null,
        @SerialName("new_remaining_amount") val newRemainingAmount: Money? = null,
        @SerialName("left_over") val leftOver: Money? = null,
    )
}

object DebtSavingsReading {
    /** "5 nov 2026" for a `YYYY-MM-DD` date. */
    fun dayLabel(date: String?, language: AppLanguage = AppLanguage.current()): String {
        val day = date?.takeIf { it.length >= 10 }?.substring(8, 10)?.toIntOrNull() ?: return "—"
        return "$day ${OwnerReading.monthLabel(date.take(7), language)}"
    }

    /** The proposal's headline: "Ahorrá ₡13.500 cada jueves por 6 meses". */
    fun headline(proposal: DebtSavingsBlocks.Proposal, format: MoneyFormat, language: AppLanguage = AppLanguage.current()): String {
        val amount = format.format(proposal.weeklyAmount ?: java.math.BigDecimal.ZERO)
        val months = proposal.termMonths ?: 0
        return language.pick("Ahorrá $amount cada jueves por $months meses", "Save $amount every Thursday for $months months")
    }

    /** The proposal in short sentences, in reading order. */
    fun lines(state: DebtSavingsBlocks, format: MoneyFormat, language: AppLanguage = AppLanguage.current()): List<String> {
        val proposal = state.proposal ?: return emptyList()
        val debt = proposal.debt?.name ?: language.pick("tu deuda", "your debt")
        val lines = mutableListOf<String>()
        val shorts = state.shortDebts.orEmpty()
        lines += if (proposal.mode == "presave" && shorts.isNotEmpty()) {
            val names = shorts.mapNotNull { it.name }.joinToString(", ")
            language.pick("Mientras terminás de pagar $names, vas guardando para $debt.", "While you finish paying $names, you save for $debt.")
        } else {
            language.pick("Es para $debt, la deuda que sigue en tu estrategia.", "It is for $debt, the next debt in your strategy.")
        }
        val start = dayLabel(proposal.startDate, language)
        val maturity = dayLabel(proposal.maturityDate, language)
        lines += language.pick("Empieza el $start y vence el $maturity.", "It starts on $start and matures on $maturity.")
        val abono = format.format(proposal.abonoAmount ?: java.math.BigDecimal.ZERO)
        lines += proposal.balanceAfterAbono?.let { after ->
            language.pick("Ese día le abonás $abono a $debt y te queda debiendo unos ${format.format(after)}.",
                "That day you pay $abono into $debt and owe about ${format.format(after)} after it.")
        } ?: language.pick("Ese día le abonás $abono a $debt.", "That day you pay $abono into $debt.")
        proposal.lockCost?.takeIf { it.signum() > 0 }?.let { cost ->
            lines += language.pick("Bloquearlo te cuesta unos ${format.format(cost)} en intereses frente a abonar cada semana. Es el precio de no ver esa plata.",
                "Locking it costs about ${format.format(cost)} in interest against paying every week. It is the price of not seeing that money.")
        }
        lines += language.pick("Los intereses del ahorro no se cuentan: si llegan, son ganancia.", "The savings' interest is not counted: if it comes, it is a bonus.")
        return lines
    }

    /** What to ask the bank when the block matures. */
    fun recommendation(proposal: DebtSavingsBlocks.Proposal, language: AppLanguage = AppLanguage.current()): String {
        val why = if (proposal.recommendation?.reason == "saves_interest") language.pick("así ahorrás más intereses", "it saves the most interest")
        else language.pick("así terminás antes", "you finish sooner")
        return language.pick("Al abonar, pedile al banco bajar el plazo: $why. Si solo te deja bajar la cuota, la diferencia se suma a tu siguiente ahorro.",
            "When you pay, ask the bank to shorten the term: $why. If it only lowers the installment, the difference goes into your next saving.")
    }

    /** Why there is no proposal, or null when there is one. */
    fun statusMessage(state: DebtSavingsBlocks, language: AppLanguage = AppLanguage.current()): String? = when (state.status) {
        "proposal" -> null
        "no_debts" -> language.pick("No tenés deudas activas. Más adelante esto sirve para tus metas.", "You have no active debts. Later this can serve your goals.")
        "short_debts_only" -> language.pick("Tus deudas se terminan en 3 meses o menos: seguí pagándolas directo.", "Your debts end within 3 months: keep paying them directly.")
        "pay_directly" -> language.pick("Esa deuda se paga pronto con tus pagos normales: no conviene bloquear plata para ella.",
            "That debt is paid soon with your normal payments: locking money for it is not worth it.")
        else -> if ((state.committedWeekly?.signum() ?: 0) > 0) {
            language.pick("Tus ahorros bloqueados ya usan todo tu sobrante seguro de cada jueves.", "Your locked savings already use all of your safe Thursday surplus.")
        } else {
            language.pick("Con tu salario sin extras no queda plata segura para bloquear.", "Your salary without extras leaves no safe money to lock.")
        }
    }

    /** The warnings the backend sent, in words. */
    fun warnings(state: DebtSavingsBlocks, language: AppLanguage = AppLanguage.current()): List<String> = state.warnings.orEmpty().mapNotNull { code ->
        when (code) {
            "average_income_estimated" -> language.pick("Algunos salarios de los últimos 3 meses son estimados.", "Some salaries of the last 3 months are estimates.")
            "average_income_unknown" -> language.pick("No hay salarios de los últimos 3 meses: el plazo usa solo tu salario base.",
                "No salaries in the last 3 months: the term uses only your base salary.")
            "interest_rate_unknown" -> language.pick("Alguna deuda no tiene tasa: el costo de bloquear puede ser mayor.", "Some debt has no rate: locking may cost more.")
            else -> null
        }
    }

    /** After the abono: where the debt stands, and what was left over (more than the debt owed). */
    fun appliedMessage(applied: DebtSavingsBlockApplied.Applied?, format: MoneyFormat, language: AppLanguage = AppLanguage.current()): String {
        applied ?: return language.pick("Listo: el abono quedó registrado.", "Done: the payment is recorded.")
        val remaining = applied.newRemainingAmount ?: java.math.BigDecimal.ZERO
        var text = if (remaining.signum() > 0) language.pick("Listo: tu deuda quedó en ${format.format(remaining)}.", "Done: your debt is now ${format.format(remaining)}.")
        else language.pick("Listo: terminaste de pagar esa deuda.", "Done: that debt is paid off.")
        applied.leftOver?.takeIf { it.signum() > 0 }?.let { left ->
            text += language.pick(" Te sobraron ${format.format(left)}: mandalos a tu siguiente deuda o al Salvavidas.",
                " ${format.format(left)} was left over: send it to your next debt or your emergency fund.")
        }
        return text
    }

    /** One block the Owner created: progress, or what to do when it matured. */
    fun blockLines(block: DebtSavingsBlocks.Block, format: MoneyFormat, language: AppLanguage = AppLanguage.current()): List<String> {
        val debt = block.debtName ?: language.pick("tu deuda", "your debt")
        val total = format.format(block.totalAtMaturity ?: java.math.BigDecimal.ZERO)
        val maturity = dayLabel(block.maturityDate, language)
        if (block.matured == true) {
            return listOf(language.pick("Venció el $maturity: abonale $total a $debt.", "It matured on $maturity: pay $total into $debt."))
        }
        val weekly = format.format(block.weeklyAmount ?: java.math.BigDecimal.ZERO)
        val saved = format.format(block.savedSoFar ?: java.math.BigDecimal.ZERO)
        val done = block.contributionsDone ?: 0
        val all = block.contributionsTotal ?: 0
        return listOf(
            language.pick("$weekly cada jueves", "$weekly every Thursday"),
            language.pick("Llevás $saved de $total ($done de $all jueves).", "$saved of $total so far ($done of $all Thursdays)."),
            language.pick("Vence el $maturity.", "Matures on $maturity."),
        )
    }
}
