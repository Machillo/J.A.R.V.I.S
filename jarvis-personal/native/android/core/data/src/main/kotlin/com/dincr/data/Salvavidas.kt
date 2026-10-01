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
    // Owner only.
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

    @Serializable
    data class Milestone(val months: Int? = null, val target: Money? = null, val reached: Boolean? = null)

    @Serializable
    data class Verification(val mode: String? = null, @SerialName("account_linked") val accountLinked: Boolean? = null, val message: String? = null)

    companion object {
        val ALLOWED_TARGET_MONTHS = listOf(1, 3, 6)
    }
}

/**
 * Body of `PUT /vip/salvavidas`: only the fields being changed are sent (null fields are omitted).
 * Users may send [targetMonths] and [currentAmount] (it updates the savings declared in the financial
 * situation, the fund's one source; 422 without a situation) but never [protectedExpenseIds] (every
 * obligation counts). The Owner may send all three (historical model).
 */
@Serializable
data class SalvavidasUpdate(
    @SerialName("target_months") val targetMonths: Int? = null,
    @SerialName("current_amount") val currentAmount: Money? = null,
    @SerialName("protected_expense_ids") val protectedExpenseIds: List<Long>? = null,
) {
    init {
        targetMonths?.let { require(it in Salvavidas.ALLOWED_TARGET_MONTHS) { "target_months must be 1, 3 or 6" } }
        currentAmount?.let { require(it.signum() >= 0) { "current_amount must not be negative" } }
    }

    companion object {
        fun target(months: Int) = SalvavidasUpdate(targetMonths = months)
        /** Users: the declared savings; Owner: the manual balance. */
        fun amount(amount: java.math.BigDecimal) = SalvavidasUpdate(currentAmount = amount)
        /** Owner only: the backend refuses a non-empty list for Users (422). */
        fun ownerProtected(ids: List<Long>) = SalvavidasUpdate(protectedExpenseIds = ids.distinct())
    }
}
