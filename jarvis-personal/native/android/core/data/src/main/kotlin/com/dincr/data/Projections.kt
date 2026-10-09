package com.dincr.data

/**
 * UX-14 — what Patrimonio → Proyecciones shows. Presentation only: it reads what the command center
 * states and never computes money. Figures are shown only when the backend says the projection is
 * complete; an answer without that status (or without points) is never read as complete, so an
 * unknown is never shown as a certain figure. iOS: `DincrCore.Projections`.
 */
sealed interface Projections {
    /** The 1, 3, 6 and 12-month points, in order. [lowConfidence]: the income has no recorded movements behind it yet. */
    data class Complete(val points: List<CommandCenter.ProjectionPoint>, val lowConfidence: Boolean) : Projections

    /** No figures: the inputs DINCR needs, in the backend's order (empty when it named none it knows). */
    data class Incomplete(val missing: List<ProjectionInput>) : Projections

    companion object {
        fun state(center: CommandCenter): Projections {
            val points = center.projections.sortedBy { it.months ?: 0 }
            if (center.projectionStatus?.complete != true || points.isEmpty()) {
                return Incomplete(ProjectionInput.codes(center.projectionStatus?.missing))
            }
            return Complete(points, points.any { it.confidence == "low" })
        }
    }
}

/**
 * An input a projection needs (the backend's `missing` codes) and the existing screen where the user
 * gives it: income and essential expenses in Plan → Ingresos y base, savings in Tus ahorros, debt
 * payments in Deudas. No other form is offered.
 */
enum class ProjectionInput(val code: String, val destination: Destination) {
    INCOME("income", Destination.INCOME_BASE),
    ESSENTIAL_EXPENSES("essential_expenses", Destination.INCOME_BASE),
    DEBT_PAYMENTS("debt_payments", Destination.DEBTS),
    SAVINGS("savings", Destination.DECLARED_SAVINGS);

    /** [route] is the app's own route. */
    enum class Destination(val route: String) { INCOME_BASE("incomeBase"), DECLARED_SAVINGS("declaredSavings"), DEBTS("debts") }

    companion object {
        /** Known codes in the backend's order; codes this app doesn't know are skipped. */
        fun codes(codes: List<String>?): List<ProjectionInput> = codes.orEmpty().mapNotNull { code -> entries.firstOrNull { it.code == code } }
    }
}

/**
 * UX-14 / I09 — the charts of Patrimonio → Proyecciones: projected cash, debt and net worth over the
 * projection's own points (1, 3, 6 and 12 months), exactly as the backend sent them. Nothing is
 * interpolated or filled in: only a complete projection has series, and a series is drawn only when
 * every one of its points is known. iOS: `DincrCore.ProjectionSeries`.
 */
data class ProjectionSeries(val kind: Kind, val series: TrendSeries) {
    enum class Kind { CASH, DEBT, NET_WORTH }

    companion object {
        /** The series to draw for [state], in the order cash, debt, net worth; none when incomplete. */
        fun of(state: Projections, language: AppLanguage = AppLanguage.current()): List<ProjectionSeries> {
            if (state !is Projections.Complete) return emptyList()
            return Kind.entries.mapNotNull { kind ->
                val values = state.points.map { value(it, kind) }
                if (values.any { it == null }) return@mapNotNull null
                ProjectionSeries(kind, TrendSeries(state.points.zip(values).map { (point, value) ->
                    val months = point.months ?: 0
                    TrendPoint(String.format(java.util.Locale.ROOT, "%02d", months), label(months, language), value)
                }))
            }
        }

        fun label(months: Int, language: AppLanguage): String =
            if (months == 1) language.pick("1 mes", "1 month") else language.pick("$months meses", "$months months")

        private fun value(point: CommandCenter.ProjectionPoint, kind: Kind) = when (kind) {
            Kind.CASH -> point.cash
            Kind.DEBT -> point.debt
            Kind.NET_WORTH -> point.netWorth
        }
    }
}
