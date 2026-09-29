package com.dincr.data

import java.math.BigDecimal
import java.time.LocalDate

/**
 * Client-side contract checks, run right before a write is sent. Several backend endpoints do not
 * bound their money fields (a larger value, or an unvalidated date, becomes a database error):
 * debts, goals, savings plans, contributions. The app never sends such a value: every money write
 * stays within `AmountInput.MAX_AMOUNT` with at most two decimals (the strictest column the value
 * can reach; a debt payment also lands in `transactions.amount` NUMERIC(12,2)), dates are real
 * `YYYY-MM-DD` dates and enums are the backend's. A violation is a local validation error.
 */
internal object Contract {
    private val language get() = AppLanguage.current()

    fun fail(spanish: String, english: String): Nothing =
        throw ApiError(ApiError.Kind.VALIDATION, message = language.pick(spanish, english))

    fun money(value: BigDecimal?, allowZero: Boolean, required: Boolean = true) {
        if (value == null) { if (required) fail("Falta un monto.", "An amount is missing."); return }
        val ok = (if (allowZero) value.signum() >= 0 else value.signum() > 0) && value <= AmountInput.MAX_AMOUNT &&
            value.stripTrailingZeros().scale() <= AmountInput.MAX_FRACTION_DIGITS
        if (!ok) fail("Un monto está fuera del rango permitido.", "An amount is outside the allowed range.")
    }

    fun rate(value: BigDecimal?) {
        if (value == null) return
        val ok = value.signum() > 0 && value <= ExchangeRateInput.MAX_RATE && value.stripTrailingZeros().scale() <= ExchangeRateInput.FRACTION_DIGITS
        if (!ok) fail("El tipo de cambio no es válido.", "The exchange rate is not valid.")
    }

    fun date(value: String?, required: Boolean) {
        if (value == null) { if (required) fail("Falta una fecha.", "A date is missing."); return }
        if (!IsoDate.isValid(value)) fail("La fecha no es válida.", "The date is not valid.")
    }

    fun text(value: String, max: Int, required: Boolean = true) {
        if (required && value.isBlank()) fail("Completá el nombre o la descripción.", "Enter a name or description.")
        if (value.length > max) fail("El texto es demasiado largo.", "The text is too long.")
    }
}

internal fun DebtRequest.checked(): DebtRequest = apply {
    Contract.text(name, 120)
    Contract.money(remainingAmount, allowZero = true)
    Contract.money(totalAmount, allowZero = true, required = false)
    Contract.money(monthlyPayment, allowZero = true, required = false)
    interestRate?.let {
        if (it.signum() < 0 || it > InterestRateInput.MAX_RATE || it.stripTrailingZeros().scale() > 4) Contract.fail("La tasa de interés no es válida.", "The interest rate is not valid.")
    }
    termMonths?.let { if (it !in 1..600) Contract.fail("El plazo debe estar entre 1 y 600 meses.", "The term must be 1 to 600 months.") }
    paymentDay?.let { if (it !in 1..31) Contract.fail("El día de pago debe estar entre 1 y 31.", "The payment day must be 1 to 31.") }
    Contract.date(nextPaymentDate, required = false)
    if (totalAmount != null && totalAmount < remainingAmount) Contract.fail("El saldo pendiente no puede ser mayor que el monto original.", "The balance can’t exceed the original amount.")
}

internal fun GoalRequest.checked(): GoalRequest = apply {
    Contract.text(name, 120)
    Contract.money(targetAmount, allowZero = false)
    Contract.money(currentAmount, allowZero = true)
    Contract.date(targetDate, required = false)
    if (priority !in GOAL_PRIORITIES) Contract.fail("La prioridad no es válida.", "The priority is not valid.")
    status?.let { if (it !in PLAN_STATUSES) Contract.fail("El estado no es válido.", "The status is not valid.") }
}

internal fun GoalContribution.checked(): GoalContribution = apply {
    Contract.money(amount, allowZero = false)
    Contract.date(contributionDate, required = false)
}

internal fun SavingsPlanRequest.checked(): SavingsPlanRequest = apply {
    Contract.text(name, 120)
    Contract.money(monthlyAmount, allowZero = false)
    Contract.money(savedAmount, allowZero = true)
    Contract.date(startDate, required = true)
    Contract.date(endDate, required = true)
    if (LocalDate.parse(startDate) > LocalDate.parse(endDate)) Contract.fail("La fecha final debe ser posterior al inicio.", "The end date must be after the start.")
    status?.let { if (it !in PLAN_STATUSES) Contract.fail("El estado no es válido.", "The status is not valid.") }
}

internal fun SavingsContribution.checked(): SavingsContribution = apply {
    Contract.money(amount, allowZero = false)
    Contract.date(contributionDate, required = false)
}

internal fun CandidateCorrection.checked(): CandidateCorrection = apply {
    Contract.date(transactionDate, required = true)
    Contract.text(description, 500)
    Contract.text(category, 100)
    Contract.money(amount, allowZero = false)
    Contract.rate(exchangeRate)
    if (transactionType !in setOf("expense", "income", "debt_payment")) Contract.fail("El tipo no es válido.", "The type is not valid.")
}

val GOAL_PRIORITIES = listOf("low", "medium", "high", "critical")
val PLAN_STATUSES = listOf("active", "paused", "completed")
