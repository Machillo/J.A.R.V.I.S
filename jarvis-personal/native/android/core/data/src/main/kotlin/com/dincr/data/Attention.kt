package com.dincr.data

/**
 * "Para atender" (UX-5): the financial matters Hoy surfaces, and the full list behind "Ver todas".
 * Presentation only: it normalizes what the backend already says, orders it and removes duplicates;
 * it never computes money or decides a new priority. Sources:
 * - the VIP command center's `alerts` (state of the month; unknown inputs no longer raise its alerts,
 *   #324) and its `automation.review` count (bank notices waiting in the Email Monitor);
 * - the proactive advisor's `alerts` (changes since the previous observation), full list only.
 * iOS: `AttentionList` (DincrCore).
 */
data class AttentionItem(
    val id: String,
    val source: Source,
    val severity: String?,
    val kind: MessageKind,
    val title: String,
    val message: String,
    /** Advisor items describe a change since the previous observation, not the absolute state. */
    val isChange: Boolean,
    val destination: Destination?,
) {
    /** Order among sources with the same severity (D-3): command center, advisor, then mail. */
    enum class Source(val key: String) { COMMAND_CENTER("center"), ADVISOR("advisor"), REVIEW("review") }

    /**
     * Screens an item can open. Only destinations that exist on both platforms; an item without one
     * is shown without a link (no route is invented from free text). [route] is the app's own route.
     */
    enum class Destination(val key: String, val route: String) {
        REVIEW("review", "mail"),
        DEBTS("debts", "debts"),
        SALVAVIDAS("salvavidas", "salvavidas"),
        INCOME_BASE("incomeBase", "incomeBase"),
        STRATEGY("strategy", "strategy"),
        MOVEMENTS("movements", "movements"),
        MONTHLY_REVIEW("monthlyReview", "review"),
    }
}

object AttentionList {
    /** Hoy shows at most this many; "Ver todas" opens the rest. */
    const val TODAY_LIMIT = 3

    /** What Hoy shows: the first items and whether "Ver todas" is needed. Empty = leave the section out. */
    data class Today(val visible: List<AttentionItem>, val showsSeeAll: Boolean) {
        val isEmpty: Boolean get() = visible.isEmpty()
    }

    /** Hoy (D-3): the command center and its mail-review count, never the advisor. */
    fun today(center: CommandCenter?, mailReviewAvailable: Boolean = true, language: AppLanguage = AppLanguage.current()): Today {
        val all = items(center, null, mailReviewAvailable, language)
        return Today(all.take(TODAY_LIMIT), all.size > TODAY_LIMIT)
    }

    /**
     * Presentation order: critical, high, medium, success. A severity the app doesn't know sits with
     * medium (never downplayed below it, never above a known one).
     */
    fun rank(severity: String?): Int = when (severity?.lowercase()) {
        "critical" -> 0
        "high" -> 1
        "success" -> 3
        else -> 2
    }

    /** The advisor's structured routes that have a screen on both platforms. Any other route (or none) gives no link. */
    fun destination(advisorRoute: String?): AttentionItem.Destination? = when (advisorRoute?.trim('/', ' ')?.lowercase()) {
        "debts" -> AttentionItem.Destination.DEBTS
        "vip-emergency" -> AttentionItem.Destination.SALVAVIDAS
        // The declared situation lives in Plan → Ingresos y base (UX-7).
        "situation" -> AttentionItem.Destination.INCOME_BASE
        "strategy" -> AttentionItem.Destination.STRATEGY
        "finance", "movements" -> AttentionItem.Destination.MOVEMENTS
        "vip-monthly-review" -> AttentionItem.Destination.MONTHLY_REVIEW
        else -> null
    }

    /**
     * Advisor codes left out of "Para atender": the health score is not shown as a fact until it has
     * one canonical calculation (K-2); the alert stays in DINCR → Hoy.
     */
    val excludedAdvisorCodes: Set<String> = setOf("health_score_drop")

    /**
     * The command center's own "Movimientos por revisar" alert, in either language: the same pending
     * notices as `automation.review`, so the two become one item.
     */
    internal val reviewAlertTitles: Set<String> = setOf("movimientos por revisar", "transactions to review")

    /**
     * A source the account can't read right now (a paused kill switch, or a feature its plan doesn't
     * include): "not available", neither a technical problem nor "nothing pending".
     */
    fun isUnavailable(error: Throwable): Boolean = (error as? ApiError)?.kind in
        setOf(ApiError.Kind.FEATURE_UNAVAILABLE, ApiError.Kind.FORBIDDEN, ApiError.Kind.SUBSCRIPTION_REQUIRED)

    /**
     * Every item, ordered: by severity rank, then source, then the backend's own order.
     * [mailReviewAvailable] is false while the mail automation is paused: the pending notices are
     * still a fact, but there is no review screen to open.
     */
    fun items(
        center: CommandCenter?,
        advisor: ProactiveAdvisor?,
        mailReviewAvailable: Boolean = true,
        language: AppLanguage = AppLanguage.current(),
    ): List<AttentionItem> {
        val ranked = mutableListOf<Pair<AttentionItem, Int>>()
        val pending = center?.automation?.review ?: 0
        val reviewDestination = if (mailReviewAvailable) AttentionItem.Destination.REVIEW else null
        var reviewMerged = false

        center?.alerts.orEmpty().forEachIndexed { index, alert ->
            val title = text(alert.title) ?: return@forEachIndexed
            val message = listOfNotNull(text(alert.context), text(alert.action)).joinToString(" ")
            if (pending > 0 && title.lowercase() in reviewAlertTitles && !reviewMerged) {
                // One item for the pending notices: the command center's words, the Email Monitor link.
                reviewMerged = true
                ranked += AttentionItem("review", AttentionItem.Source.REVIEW, alert.severity, MessageKind.financial(alert.severity),
                    title, message, isChange = false, destination = reviewDestination) to index
                return@forEachIndexed
            }
            ranked += AttentionItem("center.$index", AttentionItem.Source.COMMAND_CENTER, alert.severity, MessageKind.financial(alert.severity),
                title, message, isChange = false, destination = null) to index
        }
        if (pending > 0 && !reviewMerged) {
            val message = if (pending == 1) language.pick("Hay 1 aviso del correo sin confirmar.", "There is 1 mail notice to confirm.")
            else language.pick("Hay $pending avisos del correo sin confirmar.", "There are $pending mail notices to confirm.")
            ranked += AttentionItem("review", AttentionItem.Source.REVIEW, "medium", MessageKind.ATTENTION,
                language.pick("Movimientos por revisar", "Transactions to review"), message,
                isChange = false, destination = reviewDestination) to 0
        }
        advisor?.alerts.orEmpty().forEachIndexed { index, alert ->
            val title = text(alert.title) ?: return@forEachIndexed
            if ((alert.code ?: "") in excludedAdvisorCodes) return@forEachIndexed
            // A readjusted strategy is a recommendation, not a problem.
            val kind = if (alert.code == "strategy_changed") MessageKind.OPPORTUNITY else MessageKind.financial(alert.severity)
            ranked += AttentionItem("advisor.${alert.id ?: index}", AttentionItem.Source.ADVISOR, alert.severity, kind,
                title, text(alert.explanation) ?: "", isChange = true, destination = destination(alert.action?.route)) to index
        }
        return ranked.sortedWith(compareBy({ rank(it.first.severity) }, { it.first.source.ordinal }, { it.second })).map { it.first }
    }

    private fun text(value: String?): String? = value?.trim()?.takeIf { it.isNotEmpty() }
}
