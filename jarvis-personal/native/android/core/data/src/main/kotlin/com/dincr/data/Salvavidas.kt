package com.dincr.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * `GET|PUT /user-product/vip/salvavidas` (VIP; the Owner by role). The backend answers one of two
 * models by the server's role, told apart by [scope]:
 * - `users`: months of the user's own obligations (debts + recurring), funded by the savings declared
 *   in the financial situation. Unknown savings stay unknown ([currentAmountKnown] false, null
 *   amounts): never "0 meses".
 * - `owner`: the historical JARVIS model (manual balance, protected expenses picker).
 * Both: [autoContribution] (the automatic-contribution plan, also when disabled) and [declaredAmount]
 * (the balance last declared); with an enabled plan [currentAmount] already includes the
 * contributions (and, for the Owner, the interest estimated at [annualInterestRate]).
 * Every figure is the backend's; the app only formats them (no coverage math on the device).
 */
@Serializable
data class Salvavidas(
    val status: String? = null,
    val scope: String? = null,
    @SerialName("current_amount") val currentAmount: Money? = null,
    /** Users only; the Owner model always has a (manual or linked) amount. */
    @SerialName("current_amount_known") val currentAmountKnown: Boolean? = null,
    @SerialName("monthly_base") val monthlyBase: Money? = null,
    @SerialName("target_months") val targetMonths: Int? = null,
    @SerialName("allowed_target_months") val allowedTargetMonths: List<Int> = emptyList(),
    @SerialName("target_amount") val targetAmount: Money? = null,
    @SerialName("missing_amount") val missingAmount: Money? = null,
    @SerialName("coverage_months") val coverageMonths: Money? = null,
    @SerialName("progress_percent") val progressPercent: Double? = null,
    val components: Components? = null,
    val debts: List<DebtLine> = emptyList(),
    /** Users: active recurring expense items. */
    val obligations: List<Expense> = emptyList(),
    /** The balance last declared, before automatic contributions (null while unknown, Users). */
    @SerialName("declared_amount") val declaredAmount: Money? = null,
    /** The automatic-contribution plan and what it added, or null when none was ever saved. */
    @SerialName("auto_contribution") val autoContribution: AutoContribution? = null,
    // Owner only.
    /** Percent per year the Owner's Salvavidas earns (estimated interest). Never sent to Users. */
    @SerialName("annual_interest_rate") val annualInterestRate: Money? = null,
    @SerialName("protected_expense_ids") val protectedExpenseIds: List<Long> = emptyList(),
    @SerialName("mandatory_expenses") val mandatoryExpenses: List<Expense> = emptyList(),
    @SerialName("available_expenses") val availableExpenses: List<Expense> = emptyList(),
    @SerialName("excluded_debt_duplicates") val excludedDebtDuplicates: List<Expense> = emptyList(),
    val milestones: List<Milestone> = emptyList(),
    val verification: Verification? = null,
) {
    val isOwnerScope: Boolean get() = scope == "owner"

    /** The fund's amount is known: the Owner model always, Users only when savings were declared. */
    val isAmountKnown: Boolean get() = currentAmount != null && (isOwnerScope || currentAmountKnown == true)

    /** No obligations or debts yet: there is no monthly base to protect. */
    val needsObligations: Boolean get() = status == "needs_obligations"

    /** The enabled plan whose contributions [currentAmount] already includes, or null. */
    val activePlan: AutoContribution? get() = autoContribution?.takeIf { it.isEnabled }

    /** The annual interest rate field is the Owner's alone (the backend refuses it for anyone else). */
    val offersInterestRate: Boolean get() = isOwnerScope

    /** The targets the user may pick (1/3/6 by contract when the answer does not list them). */
    val targetChoices: List<Int> get() = allowedTargetMonths.ifEmpty { ALLOWED_TARGET_MONTHS }

    @Serializable
    data class Components(
        @SerialName("debt_monthly_payments") val debtMonthlyPayments: Money? = null,
        @SerialName("recurring_obligations") val recurringObligations: Money? = null,
        @SerialName("mandatory_fixed_expenses") val mandatoryFixedExpenses: Money? = null,
        @SerialName("protected_expenses") val protectedExpenses: Money? = null,
    )

    @Serializable
    data class DebtLine(val id: Long? = null, val name: String? = null, @SerialName("monthly_payment") val monthlyPayment: Money? = null)

    @Serializable
    data class Expense(
        val id: Long? = null,
        val name: String? = null,
        @SerialName("monthly_amount") val monthlyAmount: Money? = null,
        val frequency: String? = null,
        @SerialName("due_day") val dueDay: Int? = null,
        val selected: Boolean? = null,
    )

    /** `auto_contribution`: the plan's settings and, when enabled, what it added since [baseDate]. */
    @Serializable
    data class AutoContribution(
        val enabled: Boolean? = null,
        val amount: Money? = null,
        val frequency: String? = null,
        @SerialName("start_date") val startDate: String? = null,
        @SerialName("end_date") val endDate: String? = null,
        @SerialName("base_amount") val baseAmount: Money? = null,
        @SerialName("base_date") val baseDate: String? = null,
        @SerialName("contributions_count") val contributionsCount: Int? = null,
        @SerialName("contributions_amount") val contributionsAmount: Money? = null,
        @SerialName("estimated_interest") val estimatedInterest: Money? = null,
        @SerialName("next_date") val nextDate: String? = null,
        val total: Money? = null,
    ) {
        val isEnabled: Boolean get() = enabled == true

        companion object {
            val FREQUENCIES = listOf("weekly", "biweekly", "monthly")
        }
    }

    @Serializable
    data class Milestone(val months: Int? = null, val target: Money? = null, val reached: Boolean? = null)

    @Serializable
    data class Verification(val mode: String? = null, @SerialName("account_linked") val accountLinked: Boolean? = null, val message: String? = null)

    companion object {
        val ALLOWED_TARGET_MONTHS = listOf(1, 3, 6)
    }
}

/** The plan the app sends in `auto_contribution`; the backend validates it again. */
@Serializable
data class SalvavidasPlanRequest(
    val enabled: Boolean,
    val amount: Money,
    val frequency: String,
    @SerialName("start_date") val startDate: String,
    /** null: no end (omitted from the body; the backend reads a missing end as none). */
    @SerialName("end_date") val endDate: String? = null,
) {
    init {
        require(amount.signum() > 0 && amount <= MAX_AMOUNT && amount.scale() <= AmountInput.MAX_FRACTION_DIGITS) { "amount must be above zero" }
        require(frequency in Salvavidas.AutoContribution.FREQUENCIES) { "frequency must be weekly, biweekly or monthly" }
        val start = java.time.LocalDate.parse(startDate)
        endDate?.let { require(!java.time.LocalDate.parse(it).isBefore(start)) { "end_date must not be before start_date" } }
    }

    companion object {
        /** The backend's cap for one contribution. */
        val MAX_AMOUNT = java.math.BigDecimal("999999999.99")
    }
}

/** The Owner's annual interest rate typed as a percent ("2,5" or "2.5"): 0–50, at most 4 decimals. */
object SalvavidasRateInput {
    val MAX_RATE = java.math.BigDecimal(50)

    fun parse(text: String): java.math.BigDecimal? {
        val trimmed = text.replace(" ", "").replace("%", "")
        if (trimmed.isEmpty() || !trimmed.all { it in '0'..'9' || it == '.' || it == ',' }) return null
        val parts = trimmed.replace(',', '.').split('.')
        if (parts.size > 2 || parts[0].isEmpty() || (parts.size == 2 && parts[1].length !in 1..4)) return null
        val value = parts.joinToString(".").toBigDecimalOrNull() ?: return null
        return value.takeIf { it.signum() >= 0 && it <= MAX_RATE }
    }
}

/**
 * Body of `PUT /vip/salvavidas`: only the fields being changed are sent (null fields are omitted).
 * Users may send [targetMonths] and [currentAmount] (it updates the savings declared in the financial
 * situation, the fund's one source; 422 without a situation) but never [protectedExpenseIds] (every
 * obligation counts). The Owner may send all three (historical model). Both may send
 * [autoContribution] (with [currentAmount] while the savings are unknown); [annualInterestRate] is
 * the Owner's alone (422 for anyone else).
 */
@Serializable
data class SalvavidasUpdate(
    @SerialName("target_months") val targetMonths: Int? = null,
    @SerialName("current_amount") val currentAmount: Money? = null,
    @SerialName("protected_expense_ids") val protectedExpenseIds: List<Long>? = null,
    @SerialName("auto_contribution") val autoContribution: SalvavidasPlanRequest? = null,
    @SerialName("annual_interest_rate") val annualInterestRate: Money? = null,
) {
    init {
        targetMonths?.let { require(it in Salvavidas.ALLOWED_TARGET_MONTHS) { "target_months must be 1, 3 or 6" } }
        currentAmount?.let { require(it.signum() >= 0) { "current_amount must not be negative" } }
        annualInterestRate?.let { require(it.signum() >= 0 && it <= SalvavidasRateInput.MAX_RATE) { "annual_interest_rate must be 0-50" } }
    }

    companion object {
        fun target(months: Int) = SalvavidasUpdate(targetMonths = months)
        /** Users: the declared savings; Owner: the manual balance. */
        fun amount(amount: java.math.BigDecimal) = SalvavidasUpdate(currentAmount = amount)
        /** Owner only: the backend refuses a non-empty list for Users (422). */
        fun ownerProtected(ids: List<Long>) = SalvavidasUpdate(protectedExpenseIds = ids.distinct())
        /**
         * The automatic-contribution plan (null keeps the saved one), with the balance declared today
         * when the savings are unknown, and the Owner's rate. null when there is nothing to send.
         */
        fun plan(plan: SalvavidasPlanRequest?, currentAmount: java.math.BigDecimal? = null, annualInterestRate: java.math.BigDecimal? = null): SalvavidasUpdate? =
            if (plan == null && currentAmount == null && annualInterestRate == null) null
            else SalvavidasUpdate(currentAmount = currentAmount, autoContribution = plan, annualInterestRate = annualInterestRate)
    }
}
