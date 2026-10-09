package com.dincr.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// Models for debts, goals, savings plans, budget, recurring items and the financial situation.
// Every money value is Money (BigDecimal, exact). Fields the backend may omit are optional, and an
// unknown value stays null: the client never turns "unknown" into zero.

/** A row of `GET /user-product/finance/debts`. */
@Serializable
data class Debt(
    val id: Long,
    val name: String? = null,
    @SerialName("debt_type") val debtType: String? = null,
    @SerialName("total_amount") val totalAmount: Money? = null,
    @SerialName("remaining_amount") val remainingAmount: Money? = null,
    @SerialName("monthly_payment") val monthlyPayment: Money? = null,
    @SerialName("interest_rate") val interestRate: Money? = null,
    @SerialName("term_months") val termMonths: Int? = null,
    @SerialName("payment_day") val paymentDay: Int? = null,
    @SerialName("next_payment_date") val nextPaymentDate: String? = null,
    @SerialName("progress_percent") val progressPercent: Double? = null,
    /**
     * Whether DINCR knows the rate (the server's rule): false for a rate never given and for an
     * unconfirmed historical 0. Null from an older server (the stored rate is then shown as before).
     */
    @SerialName("interest_rate_known") val interestRateKnown: Boolean? = null,
) {
    /** The rate the edit form starts with: an unknown rate starts empty, never as "0". iOS: `Debt.rateForEditing`. */
    val rateForEditing: Money? get() = if (interestRateKnown == false) null else interestRate

    /**
     * The backend's paid percentage, only when it can be true: the list answers 0 % when the
     * original amount is unknown (`ELSE 0`), which is not a fact about the debt. Unknown ≠ 0 %.
     * iOS: `Debt.knownProgressPercent`.
     */
    val knownProgressPercent: Double? get() = progressPercent.takeIf { (totalAmount?.signum() ?: -1) > 0 }

    companion object {
        /**
         * The sum of the debts' amounts, or null (shown as "—", read as "sin dato") when any of them is
         * unknown: an unknown amount is never added as 0. Debts carry no currency of their own (the
         * profile's), so nothing is mixed.
         */
        fun knownSum(amounts: List<java.math.BigDecimal?>): java.math.BigDecimal? =
            if (amounts.any { it == null }) null else amounts.requireNoNulls().fold(java.math.BigDecimal.ZERO, java.math.BigDecimal::add)
    }
}

/** Body of `POST /finance/debts` and `PUT /finance/debts/{id}` (the edit needs Basic). */
@Serializable
data class DebtRequest(
    val name: String,
    @SerialName("debt_type") val debtType: String = "other",
    @SerialName("remaining_amount") val remainingAmount: Money,
    @SerialName("total_amount") val totalAmount: Money? = null,
    @SerialName("monthly_payment") val monthlyPayment: Money? = null,
    @SerialName("interest_rate") val interestRate: Money? = null,
    @SerialName("term_months") val termMonths: Int? = null,
    @SerialName("payment_day") val paymentDay: Int? = null,
    @SerialName("next_payment_date") val nextPaymentDate: String? = null,
    /**
     * On edit: true only when the user typed or changed the rate. Saving the rest of the debt never
     * confirms the rate it was loaded with (the server keeps an unconfirmed rate unconfirmed).
     */
    @SerialName("interest_rate_confirmed") val interestRateConfirmed: Boolean? = null,
) {
    companion object {
        /** Whether an edit touched the rate: its text differs from the one the form started with. */
        fun rateConfirmed(initial: String, current: String): Boolean = initial.trim() != current.trim()
    }
}

@Serializable
data class AmountRequest(val amount: Money)

@Serializable
data class DebtPaymentResult(
    val status: String? = null,
    @SerialName("debt_id") val debtId: Long? = null,
    @SerialName("payment_amount") val paymentAmount: Money? = null,
    @SerialName("new_remaining_amount") val newRemainingAmount: Money? = null,
)

/** A row of `GET /user-product/goals`. */
@Serializable
data class Goal(
    val id: Long,
    val name: String? = null,
    @SerialName("target_amount") val targetAmount: Money? = null,
    @SerialName("current_amount") val currentAmount: Money? = null,
    @SerialName("target_date") val targetDate: String? = null,
    val priority: String? = null,
    val status: String? = null,
) {
    /**
     * What is left to reach the target; never negative. Null when the target or the amount saved is
     * unknown: an unknown amount saved is not 0 saved. iOS: `Goal.remaining`.
     */
    val remaining: Money? get() {
        val target = targetAmount ?: return null
        val current = currentAmount ?: return null
        return (target - current).max(java.math.BigDecimal.ZERO)
    }

    /** Saved / target, only when both are known and the target is positive ([ProgressValue]). */
    val progressFraction: Double? get() = ProgressValue.of(currentAmount, targetAmount).fraction

    /**
     * A contribution is offered until the goal is completed or reached; an unknown remainder does not
     * hide it (the backend caps a contribution at the goal). iOS: `Goal.canContribute`.
     */
    val canContribute: Boolean get() = status != "completed" && (remaining?.let { it.signum() > 0 } ?: true)

    companion object {
        /** All goals together, saved / target, only when every amount is known ([Debt.knownSum]). */
        fun overallProgress(goals: List<Goal>): Double? =
            ProgressValue.of(Debt.knownSum(goals.map { it.currentAmount }), Debt.knownSum(goals.map { it.targetAmount })).fraction
    }
}

/** Body of `POST /goals` and `PUT /goals/{id}` (`status` only on edit, which needs Basic). */
@Serializable
data class GoalRequest(
    val name: String,
    @SerialName("target_amount") val targetAmount: Money,
    @SerialName("current_amount") val currentAmount: Money,
    @SerialName("target_date") val targetDate: String? = null,
    val priority: String = "medium",
    val status: String? = null,
)

/** `POST /goals/{id}/contributions` (a date is validated here, never sent unchecked). */
@Serializable
data class GoalContribution(val amount: Money, @SerialName("contribution_date") val contributionDate: String? = null)

/** A row of `GET /user-product/savings-plans`. */
@Serializable
data class SavingsPlan(
    val id: Long,
    val name: String? = null,
    @SerialName("monthly_amount") val monthlyAmount: Money? = null,
    @SerialName("saved_amount") val savedAmount: Money? = null,
    @SerialName("start_date") val startDate: String? = null,
    @SerialName("end_date") val endDate: String? = null,
    val status: String? = null,
)

@Serializable
data class SavingsPlanRequest(
    val name: String,
    @SerialName("monthly_amount") val monthlyAmount: Money,
    @SerialName("saved_amount") val savedAmount: Money,
    @SerialName("start_date") val startDate: String,
    @SerialName("end_date") val endDate: String,
    val status: String? = null,
)

@Serializable
data class SavingsContribution(val amount: Money, @SerialName("contribution_date") val contributionDate: String? = null)

/** `GET /user-product/basic/budget` (Basic). */
@Serializable
data class Budget(
    val items: List<BudgetItem> = emptyList(),
    @SerialName("total_budgeted") val totalBudgeted: Money? = null,
    @SerialName("available_for_categories") val availableForCategories: Money? = null,
    val period: String? = null,
    /** True when the user has no budget yet and the items are DINCR's proposal, not the user's. */
    @SerialName("is_proposal") val isProposal: Boolean? = null,
) {
    /** What the categories spent this month, or null when any of them is unknown (never added as 0). */
    val spentTotal: Money? get() = Debt.knownSum(items.map { it.spent })
}

@Serializable
data class BudgetItem(
    val category: String,
    @SerialName("monthly_limit") val monthlyLimit: Money? = null,
    val spent: Money? = null,
)

/** `PUT /basic/budget`: replaces every limit. */
@Serializable
data class BudgetUpdate(val items: List<BudgetLimit>)

@Serializable
data class BudgetLimit(val category: String, @SerialName("monthly_limit") val monthlyLimit: Money)

/** `GET /user-product/basic/recurring` (Basic). */
@Serializable
data class RecurringList(
    val items: List<RecurringItem> = emptyList(),
    @SerialName("monthly_expenses") val monthlyExpenses: Money? = null,
    @SerialName("annual_expenses") val annualExpenses: Money? = null,
)

@Serializable
data class RecurringItem(
    val id: Long,
    val name: String? = null,
    val amount: Money? = null,
    val category: String? = null,
    @SerialName("item_type") val itemType: String? = null,
    val frequency: String? = null,
    @SerialName("due_day") val dueDay: Int? = null,
    @SerialName("is_active") val isActive: Boolean? = null,
)

/** Body of `POST /basic/recurring` and `PUT /basic/recurring/{id}`: only the editable fields. */
@Serializable
data class RecurringRequest(
    val name: String,
    val amount: Money,
    val category: String,
    @SerialName("item_type") val itemType: String,
    val frequency: String,
    @SerialName("due_day") val dueDay: Int? = null,
    @SerialName("is_active") val isActive: Boolean = true,
)

/** `GET /user-product/financial-situation`. */
@Serializable
data class FinancialSituation(
    @SerialName("financial_profile") val profile: FinancialProfile? = null,
    val observed: Observed? = null,
    val debts: DebtSummary? = null,
    val goals: GoalSummary? = null,
) {
    @Serializable
    data class Observed(
        @SerialName("window_days") val windowDays: Int? = null,
        @SerialName("income_count") val incomeCount: Int? = null,
        @SerialName("monthly_income_average") val monthlyIncomeAverage: Money? = null,
        @SerialName("expense_count") val expenseCount: Int? = null,
    )

    @Serializable
    data class DebtSummary(val count: Int? = null, val balance: Money? = null, @SerialName("missing_interest") val missingInterest: Int? = null)

    @Serializable
    data class GoalSummary(val count: Int? = null, val current: Money? = null)
}

/**
 * The declared financial profile. `PUT /financial-situation` stores exactly this: a field the user
 * left empty is null (unknown), and an observed average is never copied into a declared value.
 */
@Serializable
data class FinancialProfile(
    @SerialName("income_type") val incomeType: String? = null,
    @SerialName("fixed_monthly_salary") val fixedMonthlySalary: Money? = null,
    @SerialName("hourly_rate") val hourlyRate: Money? = null,
    @SerialName("work_days_per_week") val workDaysPerWeek: Int? = null,
    @SerialName("hours_per_day") val hoursPerDay: Money? = null,
    @SerialName("pay_frequency") val payFrequency: String? = null,
    @SerialName("payday_note") val paydayNote: String? = null,
    @SerialName("essential_monthly_expenses") val essentialMonthlyExpenses: Money? = null,
    @SerialName("liquid_savings") val liquidSavings: Money? = null,
    @SerialName("emergency_fund_target") val emergencyFundTarget: Money? = null,
    @SerialName("strategy_preference") val strategyPreference: String? = null,
    @SerialName("discretionary_monthly_minimum") val discretionaryMonthlyMinimum: Money? = null,
)

/**
 * The situation form's work days. The backend (and the historical web form) require
 * `work_days_per_week` (1–7, a NOT NULL column) for EVERY income type, so the form always shows and
 * sends it: the stored value, or the web form's visible, editable default of 5.
 */
object SituationDefaults {
    const val WORK_DAYS = 5
    val WORK_DAYS_RANGE = 1..7

    fun workDays(current: FinancialProfile?): Int = current?.workDaysPerWeek?.takeIf { it in WORK_DAYS_RANGE } ?: WORK_DAYS
}
