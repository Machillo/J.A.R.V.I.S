package com.dincr.data

/**
 * UX-8 — "Recomendación de DINCR": the priority DINCR already recommends and why, read from the
 * strategy answer the identity gets; no new calculation, rule or score. Basic: the engine's
 * `priority` code (named here) and its own `recommendation`; VIP Users and the Owner: the dashboard
 * priority's title and detail. The engines name one priority and no other option, so none is
 * offered and it can't be changed. Free has no strategy (no card); without a declared income there
 * is nothing to recommend yet. iOS: `RecommendedPriority`.
 */
data class RecommendedPriority(
    val title: String,
    /** Why DINCR recommends it, in the engine's own words; null when the screen already says it. */
    val why: String?,
) {
    companion object {
        fun of(strategy: Strategy, language: AppLanguage = AppLanguage.current()): RecommendedPriority? {
            if (strategy.status == "needs_income") return null
            val title = basicTitle(strategy.priority, language) ?: return null
            // A critical month already shows the same text as its message.
            return RecommendedPriority(title, if (strategy.status == "critical") null else text(strategy.recommendation))
        }

        fun of(plan: DirectorStrategy): RecommendedPriority? {
            if (plan.status == "needs_income") return null
            val title = text(plan.priority?.title) ?: return null
            return RecommendedPriority(title, text(plan.priority?.detail))
        }

        /** The Basic engine's priority codes (`build_basic_strategy`), named; an unknown code shows nothing. */
        fun basicTitle(code: String?, language: AppLanguage): String? = when (code) {
            "debt" -> language.pick("Pagar deudas", "Pay down debt")
            "emergency" -> language.pick("Fondo de emergencia", "Emergency fund")
            "goals" -> language.pick("Tus metas", "Your goals")
            "wealth_building" -> language.pick("Construir patrimonio", "Build wealth")
            "complete_profile" -> language.pick("Completar tus gastos esenciales", "Add your essential expenses")
            "stabilize" -> language.pick("Estabilizar tu mes", "Stabilize your month")
            else -> null
        }

        private fun text(value: String?): String? = value?.trim()?.takeIf { it.isNotEmpty() }
    }
}
