package com.dincr.data

import java.math.BigDecimal
import java.math.RoundingMode
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * `POST /finance/strategy-vip/debt-scenario` (VIP): a what-if on one debt that is not saved — pay it
 * off, an extra payment to it, or a new debt. Every answer is the money left each month after
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
) {
    companion object {
        const val PAY_OFF = "pay_off"
        const val EXTRA_PAYMENT = "extra_payment"
        const val NEW_DEBT = "new_debt"
        fun payOff(debtId: Long) = DebtScenarioRequest(PAY_OFF, debtId = debtId)
        fun extraPayment(debtId: Long, amount: BigDecimal) = DebtScenarioRequest(EXTRA_PAYMENT, debtId = debtId, amount = amount)
        /** The payment, or the rate and term for DINCR to compute it. */
        fun newDebt(name: String?, amount: BigDecimal, monthlyPayment: BigDecimal?, annualRate: BigDecimal?, termMonths: Int?) =
            DebtScenarioRequest(NEW_DEBT, amount = amount, monthlyPayment = monthlyPayment, annualRate = annualRate, termMonths = termMonths, name = name)
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
) {
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
}
