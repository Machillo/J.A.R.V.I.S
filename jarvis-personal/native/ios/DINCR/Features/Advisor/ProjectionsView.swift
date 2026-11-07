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
    @Environment(\.moneyFormat) private var format

    var body: some View {
        switch Projections.state(center) {
        case .complete(let points, let lowConfidence):
            // In plain words first: the assumption behind every figure below.
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                Text(tx("Si seguís igual", "If nothing changes")).font(DincrFont.title2)
                Text(ProjectionText.assumption(center.safeToSpend?.monthlyMargin, format: format))
                    .font(DincrFont.bodySmall).foregroundStyle(.dincrText2).fixedSize(horizontal: false, vertical: true)
                if lowConfidence {
                    Text(ProjectionText.lowConfidence).font(DincrFont.caption).foregroundStyle(.dincrText2)
                        .accessibilityIdentifier("projections.lowConfidence")
                }
            }
            .dincrCard()
            ForEach(Array(points.enumerated()), id: \.offset) { _, point in
                VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                    Text(ProjectionText.horizon(point.months ?? 0)).font(DincrFont.title2)
                    FigureRow(label: ProjectionText.cashLine, amount: point.cash)
                    FigureRow(label: ProjectionText.debtLine, amount: point.debt)
                    FigureRow(label: ProjectionText.netWorthLine, amount: point.netWorth)
                }
                .dincrCard()
                .accessibilityIdentifier("projections.point.\(point.months ?? 0)")
            }
            // The same figures month by month, each chart saying what it is.
            SectionHeader(title: tx("Cómo cambia mes a mes", "How it changes month by month"))
            ForEach(ProjectionSeries.of(.complete(points: points, lowConfidence: lowConfidence)), id: \.kind) { item in
                VStack(alignment: .leading, spacing: DincrSpacing.s1) {
                    TrendLineChart(title: ProjectionText.chartTitle(item.kind), series: item.series, color: ProjectionText.chartColor(item.kind))
                    Text(ProjectionText.chartCaption(item.kind)).font(DincrFont.caption).foregroundStyle(.dincrText2)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .dincrCard()
                .accessibilityIdentifier("projections.chart.\(item.kind.rawValue)")
            }
        case .incomplete(let missing):
            ProjectionIncomplete(missing: missing)
        }
        if let plan = center.debtPlanner?.recommended {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                SectionHeader(title: tx("Para salir de deudas", "To get out of debt"))
                InfoRow(label: tx("Primero pagá", "Pay first"), value: plan.target ?? "—")
                FigureRow(label: tx("Poné cada mes a esa deuda", "Put toward it each month"), amount: plan.monthlyToTarget)
                if let months = plan.months { InfoRow(label: tx("Quedarías sin deudas en", "Debt-free in"), value: tx("\(months) meses", "\(months) months")) }
                FigureRow(label: tx("Intereses que pagarías", "Interest you would pay"), amount: plan.interest)
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
                    Text(ProjectionText.explanation(input)).font(DincrFont.bodySmall).foregroundStyle(.dincrText2)
                    NavigationLink { destination(input.destination) } label: {
                        Text(ProjectionText.action(input)).font(DincrFont.bodySmall.weight(.semibold)).foregroundStyle(.dincrTint).frame(minHeight: 44)
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
        case .cash: tx("Tu plata ahorrada", "Your money saved")
        case .debt: tx("Lo que te queda por pagar", "What you still owe")
        case .netWorth: tx("Lo tuyo de verdad", "What is really yours")
        }
    }

    static func chartCaption(_ kind: ProjectionSeries.Kind) -> String {
        switch kind {
        case .cash: tx("Sube con lo que te sobra cada mes.", "It grows with what is left each month.")
        case .debt: tx("Baja con cada cuota que pagás.", "It goes down with every installment you pay.")
        case .netWorth: tx("Tu plata ahorrada menos lo que debés. Si es negativo, todavía debés más de lo que tenés.",
                           "Your money saved minus what you owe. Below zero, you still owe more than you have.")
        }
    }

    static var cashLine: String { tx("Tendrías ahorrado", "You would have saved") }
    static var debtLine: String { tx("Te quedaría por pagar", "You would still owe") }
    static var netWorthLine: String { tx("Lo tuyo (ahorro − deudas)", "Yours (savings − debts)") }

    static func assumption(_ margin: Decimal?, format: MoneyFormat) -> String {
        let base = tx("Esto calcula tus próximos meses si cada mes te sobra lo mismo que este y pagás tus cuotas.",
                      "This works out your next months if every month leaves you what this one does and you pay your installments.")
        guard let margin else { return base }
        let amount = format.string(margin)
        return tx("Este mes te sobran \(amount). ", "This month leaves you \(amount). ") + base
    }

    static func chartColor(_ kind: ProjectionSeries.Kind) -> Color {
        switch kind {
        case .cash: DincrColor.chartIncome
        case .debt: DincrColor.chartExpense
        case .netWorth: OwnerColor.accent
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
