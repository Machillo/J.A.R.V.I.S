package com.dincr.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Which strategy contract an identity reads (Plan → Estrategia and Distribución). Three contracts,
 * never mixed (CLAUDE.md §4.A):
 * - [BASIC]: `GET /user-product/finance/strategy-basic` (Basic, and VIP while `vip_intelligence` is paused);
 * - [VIP_USERS]: `GET /user-product/vip/strategy-dashboard` (`strategy.scope == "users"`);
 * - [OWNER]: `GET /jarvis/premium/strategy-dashboard` (`strategy.scope == "owner"`), only when the
 *   server's role in `/auth/me` is owner. Never a plan code or a local flag.
 * The backend decides every request; this only picks the endpoint the app calls.
 */
enum class StrategyContract {
    BASIC, VIP_USERS, OWNER;

    companion object {
        /** Null when the plan has no strategy (Free): the Plan row is shown locked. */
        fun of(profile: Profile?, vipIntelligenceOn: Boolean): StrategyContract? = when {
            profile == null -> null
            profile.isOwner -> OWNER
            profile.planTier.allows(Feature.STRATEGY_VIP) && vipIntelligenceOn -> VIP_USERS
            profile.planTier.allows(Feature.STRATEGY_BASIC) -> BASIC
            else -> null
        }
    }
}

/**
 * `GET /user-product/vip/strategy-dashboard` and `GET /jarvis/premium/strategy-dashboard`: the same
 * wrapper around the deterministic director strategy. Every figure is the backend's; the app only
 * formats them. Decoding is tolerant: unknown keys are ignored and every number is optional.
 */
@Serializable
data class StrategyDashboard(
    val status: String? = null,
    @SerialName("user_role") val userRole: String? = null,
    val title: String? = null,
    val content: String? = null,
    val strategy: DirectorStrategy? = null,
    val source: String? = null,
)

@Serializable
data class DirectorStrategy(
    /** `users` or `owner`. */
    val scope: String? = null,
    val status: String? = null,
    val month: String? = null,
    val title: String? = null,
    @SerialName("mode_label") val modeLabel: String? = null,
    val objective: String? = null,
    val priority: Priority? = null,
    @SerialName("monthly_income") val monthlyIncome: Money? = null,
    @SerialName("income_policy") val incomePolicy: IncomePolicy? = null,
    /** Users: spending recorded this month. Owner: committed spending of the cycle. */
    @SerialName("monthly_expenses") val monthlyExpenses: Money? = null,
    @SerialName("debt_commitment_current_cycle") val debtCommitmentCurrentCycle: Money? = null,
    @SerialName("pending_recurring_total") val pendingRecurringTotal: Money? = null,
    @SerialName("safe_to_spend") val safeToSpend: Money? = null,
    @SerialName("emergency_fund") val emergencyFund: EmergencyFund? = null,
    /** The Salvavidas state the strategy used; tells whether the savings are known ([emergencyKnown]). */
    val salvavidas: Salvavidas? = null,
    val timeline: List<TimelineItem> = emptyList(),
    @SerialName("estimated_debt_free_date") val estimatedDebtFreeDate: String? = null,
    @SerialName("total_debt") val totalDebt: Money? = null,
    @SerialName("debt_progress_percent") val debtProgressPercent: Double? = null,
    @SerialName("investment_recommended") val investmentRecommended: Money? = null,
    val rules: List<String> = emptyList(),
    /** Users: cautions in Basic's words (e.g. a debt's rate is missing). iOS: `DashboardStrategy.warnings`. */
    val warnings: List<String> = emptyList(),
    /** Users: stable codes of the inputs a decision needs (`debt_interest_rates`). */
    val missing: List<String> = emptyList(),
    // Distribution (Plan → Distribución de dinero).
    @SerialName("allocation_base_amount") val allocationBaseAmount: Money? = null,
    @SerialName("allocation_items") val allocationItems: List<AllocationItem> = emptyList(),
    /** Kept raw: only the keys the backend sends are listed ([Distribution.formulaLines]). */
    @SerialName("distribution_formula") val distributionFormula: Map<String, kotlinx.serialization.json.JsonElement> = emptyMap(),
    /** Null for Users: DINCR never knows a User's account cash (never shown as zero). */
    @SerialName("distributable_account_cash") val distributableAccountCash: Money? = null,
    // Owner only (historical JARVIS model).
    @SerialName("recurring_monthly_income") val recurringMonthlyIncome: Money? = null,
    @SerialName("current_month_extra_net") val currentMonthExtraNet: Money? = null,
    @SerialName("income_received_current_cycle") val incomeReceivedCurrentCycle: Money? = null,
    @SerialName("remaining_income_current_cycle") val remainingIncomeCurrentCycle: Money? = null,
    @SerialName("statement_expenses") val statementExpenses: Money? = null,
    @SerialName("new_expenses_after_cut") val newExpensesAfterCut: Money? = null,
    @SerialName("mandatory_fixed_pending") val mandatoryFixedPending: Money? = null,
    @SerialName("mandatory_fixed_pending_items") val mandatoryFixedPendingItems: List<PendingItem> = emptyList(),
    @SerialName("investment_portfolio") val investmentPortfolio: InvestmentPortfolio? = null,
    @SerialName("base_timeline") val baseTimeline: List<TimelineItem> = emptyList(),
    @SerialName("months_saved_by_current_extras") val monthsSavedByCurrentExtras: Int? = null,
) {
    val isOwnerScope: Boolean get() = scope == "owner"

    /** A debt's rate is missing, so the plan names no debt to attack until the rates are complete. */
    val needsDebtRates: Boolean get() = "debt_interest_rates" in missing

    /**
     * Whether `emergency_fund.current` is a real amount. The director reads unknown Users savings as
     * 0 for its allocation, so a Users answer whose Salvavidas says the savings are unknown shows
     * "Sin dato", never ₡0 (unknown ≠ zero).
     */
    val emergencyKnown: Boolean get() = emergencyFund?.current != null && (isOwnerScope || salvavidas?.currentAmountKnown != false)

    @Serializable
    data class Priority(val kind: String? = null, val title: String? = null, val detail: String? = null)

    /** `income_policy`: where the monthly income comes from (`declared`, `observed`, …). */
    @Serializable
    data class IncomePolicy(val policy: String? = null, val source: String? = null)

    @Serializable
    data class EmergencyFund(
        val current: Money? = null,
        @SerialName("monthly_base") val monthlyBase: Money? = null,
        @SerialName("next_target") val nextTarget: Money? = null,
        @SerialName("gap_to_next_target") val gapToNextTarget: Money? = null,
        val level: String? = null,
    )

    @Serializable
    data class TimelineItem(
        val priority: Int? = null,
        val name: String? = null,
        @SerialName("remaining_amount") val remainingAmount: Money? = null,
        @SerialName("recommended_payment") val recommendedPayment: Money? = null,
        @SerialName("estimated_payoff_date") val estimatedPayoffDate: String? = null,
    )

    @Serializable
    data class AllocationItem(
        val key: String? = null,
        val percentage: Double? = null,
        val amount: Money? = null,
        @SerialName("target_name") val targetName: String? = null,
    )

    @Serializable
    data class PendingItem(val name: String? = null, val amount: Money? = null, @SerialName("due_date") val dueDate: String? = null)

    /** In [currency] (USD for the portfolio), never summed with colones. */
    @Serializable
    data class InvestmentPortfolio(
        @SerialName("market_value") val marketValue: Money? = null,
        @SerialName("contributed_capital") val contributedCapital: Money? = null,
        @SerialName("net_pnl") val netPnl: Money? = null,
        val currency: String? = null,
    )
}

/**
 * The distribution of the same strategy response (Plan → Distribución de dinero). Basic reads the
 * strategy-basic `allocations`; VIP users and the Owner read the dashboard's `allocation_items` and
 * `distribution_formula`. Nothing is computed here: only the keys present are listed, in order.
 */
object Distribution {
    /** Formula keys in display order; a key the response does not carry is not shown. */
    val USERS_FORMULA = listOf("income", "recorded_spending", "debt_commitment", "pending_recurring", "surplus", "deficit")
    val OWNER_FORMULA = listOf("cash_available_now", "income", "statement_spending", "new_spending_after_cut", "debt_commitment", "mandatory_fixed_pending", "surplus", "deficit")

    fun formulaLines(strategy: DirectorStrategy): List<Pair<String, java.math.BigDecimal?>> {
        val order = if (strategy.isOwnerScope) OWNER_FORMULA else USERS_FORMULA
        val known = order.filter { strategy.distributionFormula.containsKey(it) }
        val extra = strategy.distributionFormula.keys.filter { it !in order }
        // Users never have account cash: a cash key in a Users answer is not shown.
        return (known + extra).filter { strategy.isOwnerScope || it != "cash_available_now" }.map { it to amount(strategy.distributionFormula[it]) }
    }

    /** A JSON number as an exact amount; null (or anything else) stays unknown. */
    private fun amount(element: kotlinx.serialization.json.JsonElement?): java.math.BigDecimal? =
        (element as? kotlinx.serialization.json.JsonPrimitive)?.takeIf { !it.isString }?.content?.toBigDecimalOrNull()

    /** Spanish/English label of an allocation key (`ataque_de_deuda` names its target debt). */
    fun allocationLabel(item: DirectorStrategy.AllocationItem, language: AppLanguage): String {
        val base = when (item.key) {
            "meta_prioritaria" -> language.pick("Meta prioritaria", "Priority goal")
            "ataque_de_deuda" -> language.pick("Ataque de deuda", "Debt attack")
            "fondo_de_emergencia" -> language.pick("Salvavidas", "Emergency fund")
            "vida_controlada" -> language.pick("Vida controlada", "Controlled living")
            "inversion" -> language.pick("Inversión", "Investment")
            "metas_o_inversion" -> language.pick("Metas o inversión", "Goals or investment")
            else -> item.key.orEmpty().replace('_', ' ').replaceFirstChar { it.uppercase() }
        }
        return if (item.key == "ataque_de_deuda" && !item.targetName.isNullOrBlank()) "$base · ${item.targetName}" else base
    }

    fun formulaLabel(key: String, language: AppLanguage): String = when (key) {
        "cash_available_now" -> language.pick("Efectivo disponible ahora", "Cash available now")
        "income" -> language.pick("Ingresos", "Income")
        "recorded_spending" -> language.pick("Gastos registrados", "Recorded spending")
        "statement_spending" -> language.pick("Gastos del estado de cuenta", "Statement spending")
        "new_spending_after_cut" -> language.pick("Gastos nuevos después del corte", "New spending after the cut")
        "debt_commitment" -> language.pick("Compromiso de deudas", "Debt commitment")
        "pending_recurring" -> language.pick("Pagos recurrentes pendientes", "Pending recurring payments")
        "mandatory_fixed_pending" -> language.pick("Gastos fijos obligatorios pendientes", "Pending mandatory fixed expenses")
        "surplus" -> language.pick("Sobrante a repartir", "Surplus to allocate")
        "deficit" -> language.pick("Faltante", "Shortfall")
        else -> key.replace('_', ' ').replaceFirstChar { it.uppercase() }
    }
}
