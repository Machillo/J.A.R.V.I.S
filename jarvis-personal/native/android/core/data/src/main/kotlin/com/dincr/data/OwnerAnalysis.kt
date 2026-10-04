package com.dincr.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// JARVIS "Análisis financiero" (Owner only; parity with the historical web Finanzas tab). Three
// read endpoints of the Owner's internal routers (Owner-only on the server; the app shows the
// section only for the Owner role): /transactions/analysis/summary, /finance/net-worth and
// /finance/engine. Every figure is the backend's, in the account's base currency; the app only
// formats it. Decoding is tolerant: unknown keys are ignored, every number is optional.

/** `GET /transactions/analysis/summary` (`transactions/analyzer.py get_transaction_analysis`). */
@Serializable
data class TransactionAnalysis(
    val summary: Summary? = null,
    @SerialName("spending_breakdown") val spendingBreakdown: SpendingBreakdown? = null,
    @SerialName("monthly_flow") val monthlyFlow: List<FlowMonth> = emptyList(),
    @SerialName("expenses_by_month") val expensesByMonth: List<MonthTotal> = emptyList(),
) {
    @Serializable
    data class Summary(
        val income: Money? = null,
        val expenses: Money? = null,
        @SerialName("debt_payments") val debtPayments: Money? = null,
        @SerialName("net_from_transactions") val netFromTransactions: Money? = null,
        @SerialName("total_transactions") val totalTransactions: Int? = null,
    )

    @Serializable
    data class SpendingBreakdown(val period: Period? = null, val total: Money? = null, val categories: List<Category> = emptyList())

    @Serializable
    data class Period(val start: String? = null, val end: String? = null, val label: String? = null)

    @Serializable
    data class Category(val category: String? = null, val total: Money? = null, val count: Int? = null)

    @Serializable
    data class FlowMonth(
        val month: String? = null,
        val income: Money? = null,
        val expenses: Money? = null,
        @SerialName("monthly_balance") val monthlyBalance: Money? = null,
        @SerialName("cumulative_balance") val cumulativeBalance: Money? = null,
    )

    @Serializable
    data class MonthTotal(val month: String? = null, val total: Money? = null)
}

/** `GET /finance/net-worth` (`finance/service.py get_net_worth_report`). */
@Serializable
data class NetWorthReport(
    val assets: Assets? = null,
    val liabilities: Liabilities? = null,
    @SerialName("net_worth") val netWorth: Money? = null,
    val change: Change? = null,
    val status: String? = null,
    @SerialName("risk_level") val riskLevel: String? = null,
    val interpretation: String? = null,
    val priority: String? = null,
    val recommendations: List<String> = emptyList(),
) {
    @Serializable
    data class Assets(
        @SerialName("savings_total") val savingsTotal: Money? = null,
        @SerialName("investments_total") val investmentsTotal: Money? = null,
        @SerialName("assets_total") val assetsTotal: Money? = null,
    )

    @Serializable
    data class Liabilities(@SerialName("debt_total") val debtTotal: Money? = null, @SerialName("monthly_debt_payments") val monthlyDebtPayments: Money? = null)

    @Serializable
    data class Change(val amount: Money? = null, val percentage: Double? = null)
}

/** `GET /finance/engine` (`finance/strategic_engine.py get_financial_engine_report`). */
@Serializable
data class FinancialEngineReport(
    val status: String? = null,
    val health: Health? = null,
    val forecast: Forecast? = null,
    @SerialName("emergency_fund") val emergencyFund: EmergencyFund? = null,
    val debts: Debts? = null,
    val recommendations: List<String> = emptyList(),
) {
    @Serializable
    data class Health(val score: Double? = null, val level: String? = null, val confidence: Double? = null)

    @Serializable
    data class Forecast(
        val status: String? = null,
        val month: String? = null,
        @SerialName("projected_end_balance") val projectedEndBalance: Money? = null,
        val alert: Alert? = null,
    )

    @Serializable
    data class Alert(val level: String? = null, val message: String? = null)

    @Serializable
    data class EmergencyFund(
        val current: Money? = null,
        @SerialName("monthly_base") val monthlyBase: Money? = null,
        @SerialName("coverage_months") val coverageMonths: Money? = null,
        @SerialName("recommended_6_months") val recommendedSixMonths: Money? = null,
    )

    @Serializable
    data class Debts(val status: String? = null, val recommended: Plan? = null, @SerialName("minimum_cost") val minimumCost: MinimumCost? = null, val note: String? = null)

    @Serializable
    data class Plan(val name: String? = null, @SerialName("priority_debt") val priorityDebt: PriorityDebt? = null)

    @Serializable
    data class PriorityDebt(val name: String? = null, @SerialName("remaining_amount") val remainingAmount: Money? = null, @SerialName("interest_rate") val interestRate: Double? = null)

    @Serializable
    data class MinimumCost(@SerialName("total_remaining") val totalRemaining: Money? = null, @SerialName("total_monthly_payment") val totalMonthlyPayment: Money? = null)
}

/** The three answers of the section, loaded together. */
data class OwnerAnalysis(val transactions: TransactionAnalysis, val netWorth: NetWorthReport, val engine: FinancialEngineReport)
