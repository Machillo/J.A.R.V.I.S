package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.CommandCenter
import com.dincr.data.MessageKind
import com.dincr.data.ProjectionInput
import com.dincr.data.Projections
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.DincrMessage
import com.dincr.design.generated.DincrSpacing

/**
 * PARITY F5 / UX-14 — Patrimonio → Proyecciones (VIP), from the command center: the 1, 3, 6 and
 * 12-month points only when every input is known ([Projections]). Otherwise no figure is shown: the
 * screen says the projection is incomplete and links each missing input to the screen where the
 * user gives it. The recommended debt plan follows. iOS twin: `ProjectionsView`.
 */
@Composable
fun ProjectionsScreen(model: AppModel, nav: Navigator) {
    val center = rememberLoad(model) { model.api.commandCenter() }
    DetailScaffold(tx("Proyecciones", "Projections"), nav::back) {
        LoadContent(center) { c ->
            when (val state = Projections.state(c)) {
                is Projections.Complete -> {
                    if (state.lowConfidence) {
                        Text(ProjectionText.lowConfidence(), style = MaterialTheme.typography.bodySmall, color = Dincr.colors.textMuted,
                            modifier = Modifier.testTag("projections.lowConfidence"))
                    }
                    state.points.forEach { p ->
                        Column(Modifier.testTag("projections.point.${p.months ?: 0}")) {
                            Section(ProjectionText.horizon(p.months ?: 0)) {
                                AmountLine(tx("Efectivo", "Cash"), p.cash)
                                AmountLine(tx("Deuda", "Debt"), p.debt)
                                AmountLine(tx("Patrimonio neto", "Net worth"), p.netWorth)
                            }
                        }
                    }
                }
                is Projections.Incomplete -> ProjectionIncomplete(state.missing, nav)
            }
            c.debtPlanner?.recommended?.let { plan -> DebtPlanCard(plan) }
        }
        FinancialDisclaimer()
    }
}

/** No figure: what DINCR needs, each with a link to the existing screen that takes it. */
@Composable
private fun ProjectionIncomplete(missing: List<ProjectionInput>, nav: Navigator) {
    DincrCard {
        Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
            Column(Modifier.testTag("projections.incomplete")) {
                DincrMessage(MessageKind.ATTENTION, ProjectionText.incompleteTitle(), ProjectionText.incompleteMessage())
            }
            missing.forEach { input ->
                Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
                    Text(ProjectionText.explanation(input), style = MaterialTheme.typography.bodySmall, color = Dincr.colors.textMuted)
                    TextButton({ nav.open(input.destination.route) }, Modifier.testTag("projections.missing.${input.code}")) {
                        Text(ProjectionText.action(input), color = Dincr.colors.tint)
                    }
                }
            }
        }
    }
}

@Composable
private fun DebtPlanCard(plan: CommandCenter.Plan) {
    Section(tx("Plan de deudas recomendado", "Recommended debt plan")) {
        InfoLine(tx("Empezar por", "Start with"), plan.target ?: "—")
        AmountLine(tx("Pago mensual al objetivo", "Monthly payment to the target"), plan.monthlyToTarget)
        plan.months?.let { InfoLine(tx("Tiempo estimado", "Estimated time"), tx("$it meses", "$it months")) }
        AmountLine(tx("Intereses estimados", "Estimated interest"), plan.interest)
    }
}

/** The screen's words; iOS uses the same ones (`ProjectionText`). */
private object ProjectionText {
    @Composable fun incompleteTitle() = tx("Proyección incompleta", "Incomplete projection")

    @Composable fun incompleteMessage() = tx(
        "DINCR no proyecta con datos que no conoce. Completá lo que falta para ver tus próximos meses.",
        "DINCR doesn’t project with data it doesn’t know. Complete what’s missing to see your next months.",
    )

    @Composable fun lowConfidence() = tx(
        "Confianza baja: todavía no hay ingresos registrados que confirmen tu ingreso.",
        "Low confidence: there is no recorded income yet to confirm your income.",
    )

    @Composable fun horizon(months: Int) = if (months == 1) tx("En 1 mes", "In 1 month") else tx("En $months meses", "In $months months")

    @Composable fun explanation(input: ProjectionInput) = when (input) {
        ProjectionInput.INCOME -> tx("Falta tu ingreso mensual.", "Your monthly income is missing.")
        ProjectionInput.ESSENTIAL_EXPENSES -> tx("Faltan tus gastos esenciales del mes.", "Your essential monthly expenses are missing.")
        ProjectionInput.DEBT_PAYMENTS -> tx("Una de tus deudas no tiene su cuota mensual.", "One of your debts has no monthly payment.")
        ProjectionInput.SAVINGS -> tx("Falta tu ahorro disponible o el saldo de una cuenta.", "Your available savings or an account balance is missing.")
    }

    @Composable fun action(input: ProjectionInput) = when (input.destination) {
        ProjectionInput.Destination.INCOME_BASE -> tx("Completar ingresos y base", "Complete income and base")
        ProjectionInput.Destination.DECLARED_SAVINGS -> tx("Completar tus ahorros", "Complete your savings")
        ProjectionInput.Destination.DEBTS -> tx("Revisar deudas", "Review debts")
    }
}
