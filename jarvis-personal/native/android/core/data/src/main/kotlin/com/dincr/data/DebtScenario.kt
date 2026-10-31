package com.dincr.data

import java.math.BigDecimal
import java.math.RoundingMode
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * `POST /finance/strategy-vip/debt-scenario` (VIP): a what-if on one debt that is not saved — pay it
 * off, an extra payment to it, a new debt, refinance it (DS-2) or consolidate several (DS-2). Every answer is the money left each month after
 * essentials and debt payments; null is unknown, never ₡0 (iOS: `DebtScenarioRequest`).
 */
@Serializable
data class DebtScenarioRequest(
    val kind: String,
    @SerialName("debt_id") val debtId: Long? = null,
    val amount: Money? = null,
    @SerialName("monthly_payment") val monthlyPayment: Money? = null,
    @SerialName("annual_rate") val annualRate: Money? = null,
    @SerialName("term_months") val termMonths: Int? = null,
    val name: String? = null,
    @SerialName("debt_ids") val debtIds: List<Long>? = null,
) {
    companion object {
        const val REFINANCE = "refinance"
        const val CONSOLIDATE = "consolidate"
        const val PAY_OFF = "pay_off"
        const val EXTRA_PAYMENT = "extra_payment"
        const val NEW_DEBT = "new_debt"
        fun payOff(debtId: Long) = DebtScenarioRequest(PAY_OFF, debtId = debtId)
        fun extraPayment(debtId: Long, amount: BigDecimal) = DebtScenarioRequest(EXTRA_PAYMENT, debtId = debtId, amount = amount)
        /** The payment, or the rate and term for DINCR to compute it. */
        fun newDebt(name: String?, amount: BigDecimal, monthlyPayment: BigDecimal?, annualRate: BigDecimal?, termMonths: Int?) =
            DebtScenarioRequest(NEW_DEBT, amount = amount, monthlyPayment = monthlyPayment, annualRate = annualRate, termMonths = termMonths, name = name)

        /** One debt for a new loan at [annualRate] over [termMonths]; [fee] (optional) is borrowed too. */
        fun refinance(debtId: Long, annualRate: BigDecimal, termMonths: Int, fee: BigDecimal?) =
            DebtScenarioRequest(REFINANCE, debtId = debtId, amount = fee, annualRate = annualRate, termMonths = termMonths)

        /** Several debts paid with one new loan. */
        fun consolidate(debtIds: List<Long>, annualRate: BigDecimal, termMonths: Int, fee: BigDecimal?) =
            DebtScenarioRequest(CONSOLIDATE, amount = fee, annualRate = annualRate, termMonths = termMonths, debtIds = debtIds)
    }
}

@Serializable
data class DebtScenarioResult(
    val kind: String = "",
    val debt: DebtView? = null,
    @SerialName("monthly_leftover") val monthlyLeftover: Leftover = Leftover(),
    @SerialName("one_time_amount") val oneTimeAmount: Money? = null,
    @SerialName("liquid_savings_after") val liquidSavingsAfter: Money? = null,
    val options: Options? = null,
    val payoff: Payoff? = null,
    val warnings: List<String> = emptyList(),
    val explanation: String? = null,
    val debts: List<DebtView> = emptyList(),
    val comparison: Comparison? = null,
) {
    /** Refinance / consolidate: today's debts against the new loan. */
    @Serializable
    data class Comparison(
        val current: Side? = null,
        val scenario: Side? = null,
        /** Today's interest minus the new loan's interest and fee: positive saves, negative costs more. */
        @SerialName("total_saved") val totalSaved: Money? = null,
    ) {
        @Serializable
        data class Side(
            @SerialName("monthly_payment") val monthlyPayment: Money? = null,
            val months: Int? = null,
            val interest: Money? = null,
            val fee: Money? = null,
        )
    }

    @Serializable
    data class Leftover(val current: Money? = null, val scenario: Money? = null, val change: Money? = null)

    @Serializable
    data class DebtView(
        val id: Long? = null,
        val name: String? = null,
        @SerialName("remaining_amount") val remainingAmount: Money? = null,
        @SerialName("monthly_payment") val monthlyPayment: Money? = null,
        @SerialName("interest_rate") val interestRate: Money? = null,
        /** `declared` (the user gave the payment) or `computed` (from rate and term), new debts only. */
        @SerialName("monthly_payment_source") val monthlyPaymentSource: String? = null,
    )

    /** The lender lowers the installment: same term, more left each month. */
    @Serializable
    data class LowerInstallment(
        @SerialName("monthly_payment") val monthlyPayment: Money? = null,
        @SerialName("monthly_leftover") val monthlyLeftover: Money? = null,
        val change: Money? = null,
    )

    /** The lender shortens the term: same installment, fewer months and less interest. */
    @Serializable
    data class ShorterTerm(
        @SerialName("monthly_payment") val monthlyPayment: Money? = null,
        @SerialName("monthly_leftover") val monthlyLeftover: Money? = null,
        @SerialName("months_saved") val monthsSaved: Int? = null,
        @SerialName("interest_saved") val interestSaved: Money? = null,
    )

    @Serializable
    data class Options(
        @SerialName("lower_installment") val lowerInstallment: LowerInstallment? = null,
        @SerialName("shorter_term") val shorterTerm: ShorterTerm? = null,
    )

    @Serializable
    data class Payoff(val months: Int? = null, val interest: Money? = null)
}

/**
 * The fake backend's answer on its own debts (Debug demos and tests only): the backend's shape and
 * errors (`debt_scenarios.py`), with simple fixed math instead of its amortization.
 */
internal object FakeDebtScenario {
    sealed interface Answer {
        data class Ok(val result: DebtScenarioResult) : Answer
        data class Refused(val status: Int, val code: String, val message: String) : Answer
    }

    fun answer(request: DebtScenarioRequest, debts: List<Debt>, current: BigDecimal): Answer {
        fun leftover(change: BigDecimal?) = DebtScenarioResult.Leftover(current, change?.let { current + it }, change)
        if (request.kind == DebtScenarioRequest.NEW_DEBT) {
            val principal = request.amount?.takeIf { it.signum() > 0 } ?: return Answer.Refused(422, "amount_required", "Indicá el monto de la deuda nueva.")
            val payment = request.monthlyPayment
                ?: request.termMonths?.takeIf { it > 0 }?.let { principal.divide(BigDecimal(it), 2, RoundingMode.HALF_UP) }
                ?: return Answer.Refused(422, "payment_or_terms_required", "Indicá la cuota, o la tasa y el plazo, de la deuda nueva.")
            val name = request.name?.takeIf { it.isNotBlank() } ?: "Deuda nueva"
            return Answer.Ok(DebtScenarioResult(
                request.kind,
                DebtScenarioResult.DebtView(null, name, principal, payment, request.annualRate, if (request.monthlyPayment != null) "declared" else "computed"),
                leftover(payment.negate()), payoff = DebtScenarioResult.Payoff(), explanation = "La cuota de $name saldría de tu mes.",
            ))
        }
        if (request.kind == DebtScenarioRequest.REFINANCE || request.kind == DebtScenarioRequest.CONSOLIDATE) return replace(request, debts, current)
        val id = request.debtId ?: return Answer.Refused(422, "debt_required", "Elegí una de tus deudas.")
        val debt = debts.firstOrNull { it.id == id && (it.remainingAmount?.signum() ?: 0) > 0 }
            ?: return Answer.Refused(404, "debt_not_found", "No encontramos esa deuda.")
        val remaining = debt.remainingAmount!!
        val payment = debt.monthlyPayment
        val view = DebtScenarioResult.DebtView(debt.id, debt.name, remaining, payment, debt.interestRate)
        val warnings = if (payment == null) listOf("Esta deuda no tiene cuota mensual; DINCR no la inventó.") else emptyList()
        return when (request.kind) {
            DebtScenarioRequest.PAY_OFF -> Answer.Ok(DebtScenarioResult(
                request.kind, view, leftover(payment), oneTimeAmount = remaining, payoff = DebtScenarioResult.Payoff(), warnings = warnings,
                explanation = "Si pagás ${debt.name ?: "esta deuda"} completa, esa cuota queda libre cada mes.",
            ))
            DebtScenarioRequest.EXTRA_PAYMENT -> {
                val extra = request.amount?.takeIf { it.signum() > 0 } ?: return Answer.Refused(422, "amount_required", "Indicá cuánto querés abonar.")
                if (extra >= remaining) return Answer.Refused(422, "covers_debt", "Ese abono cubre toda la deuda: probá el escenario de pagarla.")
                val lower = payment?.multiply(remaining - extra)?.divide(remaining, 2, RoundingMode.HALF_UP)
                val freed = if (payment != null && lower != null) payment - lower else null
                Answer.Ok(DebtScenarioResult(
                    request.kind, view, DebtScenarioResult.Leftover(current), oneTimeAmount = extra,
                    options = DebtScenarioResult.Options(
                        DebtScenarioResult.LowerInstallment(lower, freed?.let { current + it }, freed),
                        DebtScenarioResult.ShorterTerm(payment, current, payment?.let { extra.divide(it, 0, RoundingMode.DOWN).toInt() }),
                    ),
                    warnings = warnings,
                    explanation = "Tu banco decide si el abono baja la cuota o acorta el plazo: bajar la cuota libera dinero cada mes; acortar el plazo ahorra más intereses.",
                ))
            }
            else -> Answer.Refused(422, "unknown_kind", "Ese escenario no existe.")
        }
    }

    /** Refinance / consolidate with simple fixed math (the server amortizes): interest ≈ balance × rate × months / 24. iOS: the same. */
    private fun replace(request: DebtScenarioRequest, debts: List<Debt>, current: BigDecimal): Answer {
        val rate = request.annualRate ?: return Answer.Refused(422, "terms_required", "Indicá la tasa y el plazo del préstamo nuevo.")
        val term = request.termMonths?.takeIf { it > 0 } ?: return Answer.Refused(422, "terms_required", "Indicá la tasa y el plazo del préstamo nuevo.")
        val ids = if (request.kind == DebtScenarioRequest.REFINANCE) listOf(request.debtId ?: -1) else request.debtIds.orEmpty().distinct().sorted()
        if (request.kind == DebtScenarioRequest.CONSOLIDATE && ids.size < 2) return Answer.Refused(422, "debts_required", "Elegí al menos dos deudas para juntar.")
        val picked = ids.mapNotNull { id -> debts.firstOrNull { it.id == id && (it.remainingAmount?.signum() ?: 0) > 0 } }
        if (picked.size != ids.size) return Answer.Refused(404, "debt_not_found", "No encontramos esa deuda.")
        val fee = request.amount ?: BigDecimal.ZERO
        val balance = picked.fold(BigDecimal.ZERO) { sum, debt -> sum + debt.remainingAmount!! }
        val payments = picked.fold(BigDecimal.ZERO) { sum, debt -> sum + (debt.monthlyPayment ?: BigDecimal.ZERO) }
        val todayMonths = picked.maxOf { debt -> debt.remainingAmount!!.divide(debt.monthlyPayment ?: BigDecimal.ONE, 0, RoundingMode.DOWN).toInt() + 1 }
        val todayInterest = picked.fold(BigDecimal.ZERO) { sum, debt ->
            sum + debt.remainingAmount!! * (debt.interestRate ?: BigDecimal.ZERO) * BigDecimal(todayMonths) / BigDecimal(2400)
        }.setScale(2, RoundingMode.HALF_UP)
        val principal = balance + fee
        val newInterest = (principal * rate * BigDecimal(term)).divide(BigDecimal(2400), 2, RoundingMode.HALF_UP)
        val newPayment = (principal + newInterest).divide(BigDecimal(term), 2, RoundingMode.HALF_UP)
        val refinance = request.kind == DebtScenarioRequest.REFINANCE
        return Answer.Ok(DebtScenarioResult(
            request.kind,
            DebtScenarioResult.DebtView(if (refinance) ids[0] else null, if (refinance) "Préstamo nuevo" else "Préstamo para juntar deudas", principal, newPayment, rate, "computed"),
            DebtScenarioResult.Leftover(current, current + payments - newPayment, payments - newPayment),
            payoff = DebtScenarioResult.Payoff(term, newInterest),
            explanation = "Pagarías ${picked.joinToString(", ") { it.name.orEmpty() }} con un préstamo nuevo.",
            debts = picked.map { DebtScenarioResult.DebtView(it.id, it.name, it.remainingAmount) },
            comparison = DebtScenarioResult.Comparison(
                DebtScenarioResult.Comparison.Side(payments, todayMonths, todayInterest),
                DebtScenarioResult.Comparison.Side(newPayment, term, newInterest, fee),
                todayInterest - newInterest - fee,
            ),
        ))
    }
}
