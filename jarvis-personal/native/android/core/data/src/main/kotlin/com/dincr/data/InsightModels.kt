package com.dincr.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// Read models of the dashboards, reports and strategy screens. The backend computes every figure;
// the app only presents them. Owner-shaped payloads (`/vip/strategy-dashboard`,
// `/vip/debt-advisory`) are deliberately not modelled: the public app uses the neutral
// `/finance/strategy-vip` engine (CLAUDE.md §4.A).

@Serializable
data class CategoryTotal(val category: String? = null, val amount: Money? = null)

/** `GET /user-product/free/monthly-summary?period=YYYY-MM`. */
@Serializable
data class MonthlySummary(
    val period: String? = null,
    val income: Money? = null,
    val expenses: Money? = null,
    @SerialName("debt_paid") val debtPaid: Money? = null,
    val balance: Money? = null,
    @SerialName("top_category") val topCategory: CategoryTotal? = null,
    val categories: List<CategoryTotal> = emptyList(),
    val savings: Money? = null,
    val goals: GoalProgress? = null,
)

@Serializable
data class GoalProgress(val current: Money? = null, val target: Money? = null, val progress: Double? = null, val active: Int? = null)

/** `GET /user-product/basic/dashboard` (Basic). */
@Serializable
data class BasicDashboard(
    val month: String? = null,
    val income: Money? = null,
    val expenses: Money? = null,
    @SerialName("debt_paid") val debtPaid: Money? = null,
    val balance: Money? = null,
    val debt: DebtProgress? = null,
    val savings: Money? = null,
    val goals: GoalProgress? = null,
    val categories: List<CategoryTotal> = emptyList(),
    @SerialName("monthly_history") val monthlyHistory: List<MonthTotals> = emptyList(),
) {
    @Serializable
    data class DebtProgress(val original: Money? = null, val remaining: Money? = null, val monthly: Money? = null, val progress: Double? = null)
}

/** `GET /user-product/basic/calendar?period=YYYY-MM` (Basic). */
@Serializable
data class FinancialCalendar(
    val period: String? = null,
    val events: List<Event> = emptyList(),
    val summary: Summary? = null,
) {
    @Serializable
    data class Event(val date: String? = null, val kind: String? = null, val name: String? = null, val amount: Money? = null, val source: String? = null)

    @Serializable
    data class Summary(@SerialName("income_events") val incomeEvents: Int? = null, val payments: Money? = null, val commitments: Int? = null)
}

/** `GET /user-product/basic/reports?period=YYYY-MM` (Basic; `advanced_reports`). */
@Serializable
data class MonthReport(
    val period: String? = null,
    val income: Money? = null,
    val expenses: Money? = null,
    @SerialName("debt_paid") val debtPaid: Money? = null,
    @SerialName("goal_contributions") val goalContributions: Money? = null,
    val saved: Money? = null,
    val balance: Money? = null,
    val categories: List<CategoryTotal> = emptyList(),
    val comparison: Comparison? = null,
) {
    @Serializable
    data class Comparison(val income: Money? = null, val expenses: Money? = null, @SerialName("debt_paid") val debtPaid: Money? = null)
}

/** `GET /finance/strategy-basic` (Basic) and the neutral part of `/finance/strategy-vip` (VIP). */
@Serializable
data class Strategy(
    val status: String? = null,
    val priority: String? = null,
    @SerialName("monthly_income") val monthlyIncome: Money? = null,
    @SerialName("essential_expenses") val essentialExpenses: Money? = null,
    @SerialName("minimum_debt_payments") val minimumDebtPayments: Money? = null,
    @SerialName("strategic_margin") val strategicMargin: Money? = null,
    val allocations: List<Allocation> = emptyList(),
    @SerialName("vip_allocations") val vipAllocations: List<Allocation> = emptyList(),
    @SerialName("target_debt") val targetDebt: TargetDebt? = null,
    val recommendation: String? = null,
    val warnings: List<String> = emptyList(),
    val projection: Projection? = null,
    @SerialName("next_paycheck") val nextPaycheck: Paycheck? = null,
    @SerialName("director_note") val directorNote: String? = null,
    val insights: Insights? = null,
) {
    @Serializable
    data class Allocation(val bucket: String? = null, val label: String? = null, val amount: Money? = null)

    @Serializable
    data class TargetDebt(val id: Long? = null, val name: String? = null, @SerialName("remaining_amount") val remainingAmount: Money? = null, @SerialName("monthly_payment") val monthlyPayment: Money? = null)

    @Serializable
    data class Projection(val name: String? = null, val months: Int? = null, @SerialName("baseline_months") val baselineMonths: Int? = null, @SerialName("monthly_to_target") val monthlyToTarget: Money? = null)

    @Serializable
    data class Paycheck(
        @SerialName("pay_frequency") val payFrequency: String? = null,
        @SerialName("estimated_paycheck") val estimatedPaycheck: Money? = null,
        val envelopes: List<Allocation> = emptyList(),
        val unassigned: Money? = null,
    )

    @Serializable
    data class Insights(
        @SerialName("emergency_months") val emergencyMonths: Double? = null,
        @SerialName("emergency_progress") val emergencyProgress: Double? = null,
        @SerialName("goal_guidance") val goalGuidance: List<GoalGuidance> = emptyList(),
        val alerts: List<InsightAlert> = emptyList(),
        @SerialName("total_debt") val totalDebt: Money? = null,
    )

    @Serializable
    data class GoalGuidance(val id: Long? = null, val name: String? = null, val remaining: Money? = null, @SerialName("target_date") val targetDate: String? = null, @SerialName("monthly_needed") val monthlyNeeded: Money? = null)

    @Serializable
    data class InsightAlert(val level: String? = null, val code: String? = null, val message: String? = null)
}

/** `POST /finance/strategy-vip/simulate`: what if (not saved). */
@Serializable
data class ScenarioRequest(
    @SerialName("monthly_income_change") val monthlyIncomeChange: Money,
    @SerialName("monthly_expense_change") val monthlyExpenseChange: Money,
    @SerialName("one_time_extra") val oneTimeExtra: Money,
)

@Serializable
data class ScenarioResult(val current: Strategy? = null, val scenario: Strategy? = null, val delta: Delta? = null) {
    @Serializable
    data class Delta(@SerialName("strategic_margin") val strategicMargin: Money? = null, @SerialName("monthly_income") val monthlyIncome: Money? = null, @SerialName("essential_expenses") val essentialExpenses: Money? = null)
}

/** `GET /user-product/vip/command-center` (VIP): the director's view. */
@Serializable
data class CommandCenter(
    @SerialName("as_of") val asOf: String? = null,
    val director: Director? = null,
    val score: Score? = null,
    @SerialName("debt_planner") val debtPlanner: DebtPlanner? = null,
    @SerialName("safe_to_spend") val safeToSpend: SafeToSpend? = null,
    val alerts: List<Alert> = emptyList(),
    val projections: List<ProjectionPoint> = emptyList(),
    val roadmap: List<RoadmapStep> = emptyList(),
    @SerialName("variable_income") val variableIncome: VariableIncome? = null,
    val automation: Automation? = null,
) {
    @Serializable
    data class Director(val priority: String? = null, val headline: String? = null, @SerialName("next_action") val nextAction: String? = null, @SerialName("data_complete") val dataComplete: Boolean? = null)

    @Serializable
    data class Score(val value: Int? = null, val label: String? = null, val factors: List<Factor> = emptyList())

    @Serializable
    data class Factor(val label: String? = null, val impact: String? = null)

    @Serializable
    data class DebtPlanner(val recommended: Plan? = null, val strategies: List<Plan> = emptyList())

    @Serializable
    data class Plan(val method: String? = null, val target: String? = null, @SerialName("monthly_to_target") val monthlyToTarget: Money? = null, val months: Int? = null, val interest: Money? = null)

    @Serializable
    data class SafeToSpend(val amount: Money? = null, @SerialName("monthly_margin") val monthlyMargin: Money? = null, @SerialName("next_45_days_minimum") val next45DaysMinimum: Money? = null)

    @Serializable
    data class Alert(val severity: String? = null, val title: String? = null, val context: String? = null, val action: String? = null)

    @Serializable
    data class ProjectionPoint(val months: Int? = null, val cash: Money? = null, val debt: Money? = null, @SerialName("net_worth") val netWorth: Money? = null, val confidence: String? = null)

    @Serializable
    data class RoadmapStep(val order: Int? = null, val title: String? = null, val amount: Money? = null, val why: String? = null)

    @Serializable
    data class VariableIncome(val estimated: Money? = null, val conservative: Money? = null, @SerialName("variability_percent") val variabilityPercent: Double? = null, @SerialName("months_observed") val monthsObserved: Int? = null)

    @Serializable
    data class Automation(val confirmed: Int? = null, val review: Int? = null, val duplicates: Int? = null)
}

/** `GET /user-product/vip/aguinaldo` (VIP; needs a connected mailbox, else 409). CRC by law. */
@Serializable
data class Aguinaldo(
    val status: String? = null,
    val period: Period? = null,
    @SerialName("earned_salary_total") val earnedSalaryTotal: Money? = null,
    @SerialName("accrued_aguinaldo") val accruedAguinaldo: Money? = null,
    val months: List<Month> = emptyList(),
    @SerialName("missing_months") val missingMonths: List<String> = emptyList(),
) {
    @Serializable
    data class Period(val start: String? = null, val end: String? = null, @SerialName("calculated_through") val calculatedThrough: String? = null, @SerialName("official_through") val officialThrough: String? = null)

    @Serializable
    data class Month(val month: String? = null, @SerialName("total_earned") val totalEarned: Money? = null, val entries: Int? = null)
}

/** `GET /user-product/vip/lifecycle/monthly-review?period` (VIP). BASELINE until enough history. */
@Serializable
data class MonthlyReview(
    val status: String? = null,
    val period: String? = null,
    val headline: String? = null,
    val summary: String? = null,
    val scorecard: List<ScoreLine> = emptyList(),
    val wins: List<kotlinx.serialization.json.JsonElement> = emptyList(),
    val deviations: List<kotlinx.serialization.json.JsonElement> = emptyList(),
    @SerialName("next_month") val nextMonth: NextMonth? = null,
) {
    @Serializable
    data class ScoreLine(val key: String? = null, val label: String? = null, val unit: String? = null, val current: Double? = null, val baseline: Double? = null, val delta: Double? = null, val trend: String? = null)

    @Serializable
    data class NextMonth(val priority: String? = null, val title: String? = null, val amount: Money? = null, val rationale: String? = null)
}

/** `GET /user-product/vip/lifecycle/proactive-advisor` (VIP). */
@Serializable
data class ProactiveAdvisor(
    val status: String? = null,
    @SerialName("as_of") val asOf: String? = null,
    val alerts: List<Alert> = emptyList(),
    val message: String? = null,
) {
    @Serializable
    data class Alert(val id: String? = null, val code: String? = null, val severity: String? = null, val title: String? = null, val explanation: String? = null, val action: Action? = null)

    @Serializable
    data class Action(val label: String? = null, val route: String? = null)
}
