import DincrCore
import DincrDesign
import SwiftUI

/// PARITY F5 / UX-14 — Patrimonio → Proyecciones (VIP), from the command center: the 1, 3, 6 and
/// 12-month points only when every input is known (`Projections`). Otherwise no figure is shown:
/// the screen says the projection is incomplete and links each missing input to the screen where
/// the user gives it. The recommended debt plan follows. Android twin: `ProjectionsScreen`.
struct ProjectionsView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        ScreenScroll(title: tx("Proyecciones", "Projections")) {
            AsyncContent(load: { try await model.service.commandCenter() }) { center, _ in
                ProjectionsContent(center: center)
            }
            FinancialDisclaimer()
        }
    }
}

private struct ProjectionsContent: View {
    let center: CommandCenter

    var body: some View {
        switch Projections.state(center) {
        case .complete(let points, let lowConfidence):
            if lowConfidence {
                Text(ProjectionText.lowConfidence).font(DincrFont.caption).foregroundStyle(DincrColor.text2)
                    .accessibilityIdentifier("projections.lowConfidence")
            }
            // UX-14 / I09: the same points as lines; the cards below stay as the text alternative.
            ForEach(ProjectionSeries.of(.complete(points: points, lowConfidence: lowConfidence)), id: \.kind) { item in
                TrendLineChart(title: ProjectionText.chartTitle(item.kind), series: item.series, color: ProjectionText.chartColor(item.kind))
                    .dincrCard()
                    .accessibilityIdentifier("projections.chart.\(item.kind.rawValue)")
            }
            ForEach(Array(points.enumerated()), id: \.offset) { _, point in
                VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                    Text(ProjectionText.horizon(point.months ?? 0)).font(DincrFont.title2)
                    FigureRow(label: tx("Efectivo", "Cash"), amount: point.cash)
                    FigureRow(label: tx("Deuda", "Debt"), amount: point.debt)
                    FigureRow(label: tx("Patrimonio neto", "Net worth"), amount: point.netWorth)
                }
                .dincrCard()
                .accessibilityIdentifier("projections.point.\(point.months ?? 0)")
            }
        case .incomplete(let missing):
            ProjectionIncomplete(missing: missing)
        }
        if let plan = center.debtPlanner?.recommended {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                SectionHeader(title: tx("Plan de deudas recomendado", "Recommended debt plan"))
                InfoRow(label: tx("Empezar por", "Start with"), value: plan.target ?? "—")
                FigureRow(label: tx("Pago mensual al objetivo", "Monthly payment to the target"), amount: plan.monthlyToTarget)
                if let months = plan.months { InfoRow(label: tx("Tiempo estimado", "Estimated time"), value: tx("\(months) meses", "\(months) months")) }
                FigureRow(label: tx("Intereses estimados", "Estimated interest"), amount: plan.interest)
            }
            .dincrCard()
        }
    }
}

/// No figure: what DINCR needs, each with a link to the existing screen that takes it.
private struct ProjectionIncomplete: View {
    let missing: [ProjectionInput]

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            DincrMessage(.attention, title: ProjectionText.incompleteTitle, message: ProjectionText.incompleteMessage)
                .accessibilityIdentifier("projections.incomplete")
            ForEach(missing, id: \.self) { input in
                VStack(alignment: .leading, spacing: DincrSpacing.s1) {
                    Text(ProjectionText.explanation(input)).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
                    NavigationLink { destination(input.destination) } label: {
                        Text(ProjectionText.action(input)).font(DincrFont.bodySmall.weight(.semibold)).foregroundStyle(DincrColor.tint).frame(minHeight: 44)
                    }
                    .accessibilityIdentifier("projections.missing.\(input.rawValue)")
                }
            }
        }
        .dincrCard()
    }

    @ViewBuilder
    private func destination(_ destination: ProjectionInput.Destination) -> some View {
        switch destination {
        case .incomeBase: IncomeBaseView()
        case .declaredSavings: DeclaredSavingsView()
        case .debts: DebtsView()
        }
    }
}

/// The screen's words; Android uses the same ones (`ProjectionsScreen`).
enum ProjectionText {
    static var incompleteTitle: String { tx("Proyección incompleta", "Incomplete projection") }
    static var incompleteMessage: String {
        tx("DINCR no proyecta con datos que no conoce. Completá lo que falta para ver tus próximos meses.",
           "DINCR doesn’t project with data it doesn’t know. Complete what’s missing to see your next months.")
    }
    static var lowConfidence: String {
        tx("Confianza baja: todavía no hay ingresos registrados que confirmen tu ingreso.",
           "Low confidence: there is no recorded income yet to confirm your income.")
    }

    static func chartTitle(_ kind: ProjectionSeries.Kind) -> String {
        switch kind {
        case .cash: tx("Efectivo proyectado", "Projected cash")
        case .debt: tx("Deuda proyectada", "Projected debt")
        case .netWorth: tx("Patrimonio neto proyectado", "Projected net worth")
        }
    }

    static func chartColor(_ kind: ProjectionSeries.Kind) -> Color {
        switch kind {
        case .cash: DincrColor.chartIncome
        case .debt: DincrColor.chartExpense
        case .netWorth: DincrColor.tint
        }
    }

    static func horizon(_ months: Int) -> String {
        months == 1 ? tx("En 1 mes", "In 1 month") : tx("En \(months) meses", "In \(months) months")
    }

    static func explanation(_ input: ProjectionInput) -> String {
        switch input {
        case .income: tx("Falta tu ingreso mensual.", "Your monthly income is missing.")
        case .essentialExpenses: tx("Faltan tus gastos esenciales del mes.", "Your essential monthly expenses are missing.")
        case .debtPayments: tx("Una de tus deudas no tiene su cuota mensual.", "One of your debts has no monthly payment.")
        case .savings: tx("Falta tu ahorro disponible o el saldo de una cuenta.", "Your available savings or an account balance is missing.")
        }
    }

    static func action(_ input: ProjectionInput) -> String {
        switch input.destination {
        case .incomeBase: tx("Completar ingresos y base", "Complete income and base")
        case .declaredSavings: tx("Completar tus ahorros", "Complete your savings")
        case .debts: tx("Revisar deudas", "Review debts")
        }
    }
}
