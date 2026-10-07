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
