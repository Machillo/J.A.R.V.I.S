import DincrCore
import DincrDesign
import SwiftUI

/// Debts and goals (and savings) on Hoy, for every plan: the same screens the Plan tab used to
/// open, moved here (navigation only; their data and rules are unchanged).
struct HomePlanningLinks: View {
    var body: some View {
        VStack(spacing: DincrSpacing.s2) {
            NavigationLink { DebtsView() } label: {
                HubRow(symbol: "creditcard", title: tx("Deudas", "Debts"), subtitle: tx("Saldos, pagos y avance", "Balances, payments and progress"))
            }
            .buttonStyle(.plain)
            .dincrCard(padding: DincrSpacing.s3)
            .accessibilityIdentifier("home.debts")
            NavigationLink { GoalsView() } label: {
                HubRow(symbol: "target", title: tx("Metas y ahorro", "Goals and savings"), subtitle: tx("Metas, aportes y planes de ahorro", "Goals, contributions and savings plans"))
            }
            .buttonStyle(.plain)
            .dincrCard(padding: DincrSpacing.s3)
            .accessibilityIdentifier("home.goals")
        }
    }
}
