package com.dincr.data

import java.math.BigDecimal

/**
 * "Tu plan del mes" (UX-3): Estrategia and Distribución read as one plan. It is a reading of the
 * strategy answer the identity already gets ([StrategyContract]: Basic, VIP Users or the Owner),
 * not a new calculation: the amount to plan, how DINCR splits it and a short why are the backend's
 * own figures and text. The only thing decided here is whether the parts exactly make up the
 * amount to plan; only then are they drawn as a whole (a donut). iOS: `DincrCore.MonthPlan`.
 */
data class MonthPlan(
    val kind: Kind,
    /** The amount DINCR plans with: Basic `strategic_margin`, dashboard `allocation_base_amount`. */
    val base: BigDecimal?,
    val parts: List<Part>,
    /** Basic recommendation (or director note); dashboard priority title (or objective). */
    val headline: String?,
    /** The commitments exceed the income / there is no real surplus this month. */
    val isCritical: Boolean,
    /** What a critical answer says: Basic recommendation, dashboard objective (as before UX-3). */
    val criticalDetail: String?,
    val needsIncome: Boolean,
    /** The income was estimated from recorded movements (Basic answers say so). */
    val usesObservedIncome: Boolean,
) {
    enum class Kind { BASIC, USERS, OWNER }

    /** One part of the split, as the backend sent it. [percentage] exists only for the dashboard. */
    data class Part(val id: String, val label: String, val amount: BigDecimal?, val percentage: Double?)

    /** The summary's sentence: the headline, unless a critical message already says the same. */
    val summaryHeadline: String? get() = headline?.takeUnless { isCritical && it == criticalDetail }

    /** The parts as a composition (no currency of their own: the profile currency of the answer). */
    val composition: Composition get() = Composition(parts.map { CompositionItem(it.id, it.label, it.amount) })

    /**
     * The parts exactly make up the amount to plan, so the whole can be drawn. A part with an
     * unknown amount, an unknown amount to plan, or parts that leave money unassigned (or add up to
     * more) are listed instead: DINCR never draws a whole the backend didn't send.
     */
    val showsComposition: Boolean
        get() {
            val composition = composition
            val total = composition.total ?: return false
            return composition.isDrawable && base != null && total.compareTo(base) == 0
        }

    companion object {
        fun of(strategy: Strategy): MonthPlan = MonthPlan(
            kind = Kind.BASIC,
            base = strategy.strategicMargin,
            parts = strategy.allocations.mapIndexed { index, allocation ->
                Part("$index-${allocation.bucket.orEmpty()}", allocation.label ?: allocation.bucket ?: "—", allocation.amount, null)
            },
            headline = text(strategy.recommendation) ?: text(strategy.directorNote),
            isCritical = strategy.status == "critical",
            criticalDetail = text(strategy.recommendation),
            needsIncome = strategy.status == "needs_income",
            usesObservedIncome = strategy.isIncomeObserved,
        )

        fun of(dashboard: StrategyDashboard, language: AppLanguage = AppLanguage.current()): MonthPlan {
            val plan = dashboard.strategy
            return MonthPlan(
                kind = if (plan?.isOwnerScope == true) Kind.OWNER else Kind.USERS,
                base = plan?.allocationBaseAmount,
                parts = plan?.allocationItems.orEmpty().mapIndexed { index, item ->
                    Part("$index-${item.key.orEmpty()}", Distribution.allocationLabel(item, language), item.amount, item.percentage)
                },
                headline = text(plan?.priority?.title) ?: text(plan?.objective) ?: text(dashboard.content),
                isCritical = plan?.status == "critical",
                criticalDetail = text(plan?.objective),
                needsIncome = plan?.status == "needs_income",
                usesObservedIncome = false,
            )
        }

        private fun text(value: String?): String? = value?.trim()?.takeIf { it.isNotEmpty() }
    }
}
