import DincrCore
import DincrDesign
import SwiftUI

/// JARVIS · Control de dinero (Owner only): the cuentas por cobrar of the historical web
/// Receivables page — who owes the Owner money, what is due in the current card cycle, what carried
/// over and the cycle's movements. `GET /finance/receivables/view` is read only: opening this screen
/// syncs nothing and changes no receivable. Every figure is the backend's; unknown shows "—".
/// Only `JarvisSectionView` (Owner role) opens it. Android twin: `JarvisReceivablesScreen.kt`.
struct OwnerReceivablesView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        ScreenScroll(title: tx("Cuentas por cobrar", "Money owed to you")) {
            AsyncContent(fallback: tx("No pudimos cargar tus cuentas por cobrar.", "We couldn’t load the money owed to you."),
                         load: { try await model.service.receivables() }) { report, _ in
                OwnerReceivablesContent(report: report)
            }
        }
    }
}

private struct OwnerReceivablesContent: View {
    let report: ReceivablesReport

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            SectionHeader(title: tx("Pendiente de cobro", "Still owed to you"))
            MoneyText(report.summary?.totalPending, font: DincrFont.displayAmount)
            if let people = report.summary?.peopleCount {
                InfoRow(label: tx("Personas", "People"), value: "\(people)")
            }
            FigureRow(label: tx("Arrastrado de ciclos anteriores", "Carried from earlier cycles"), amount: report.summary?.carriedPending)
            FigureRow(label: tx("Cargos del ciclo", "Cycle charges"), amount: report.summary?.cycleCharges)
            FigureRow(label: tx("Abonos del ciclo", "Cycle payments"), amount: report.summary?.cyclePayments)
            if let start = report.cycle?.start, let end = report.cycle?.end {
                Text(tx("Ciclo del \(Day.label(start)) al \(Day.label(end))", "Cycle from \(Day.label(start)) to \(Day.label(end))"))
                    .font(DincrFont.caption).foregroundStyle(DincrColor.text2)
            }
        }
        .dincrCard()
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("jarvis.receivables.summary")

        if report.items.isEmpty {
            EmptyStateView(symbol: "person.2", title: tx("Nadie te debe", "Nobody owes you"),
                           message: tx("No hay cuentas por cobrar registradas.", "There’s no money owed to you on record.")) { EmptyView() }
                .accessibilityIdentifier("jarvis.receivables.empty")
        } else {
            ForEach(report.items) { item in ReceivableCard(item: item) }
        }
    }
}

private struct ReceivableCard: View {
    let item: Receivable

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            HStack(alignment: .firstTextBaseline) {
                Text(item.personName ?? "—").font(DincrFont.body.weight(.semibold)).foregroundStyle(DincrColor.text)
                Spacer(minLength: DincrSpacing.s3)
                Text(statusLabel).font(DincrFont.caption).foregroundStyle(DincrColor.text2)
            }
            FigureRow(label: tx("Por cobrar", "Owed"), amount: item.currentAmountDue)
            FigureRow(label: tx("Arrastrado", "Carried"), amount: item.carriedPending)
            FigureRow(label: tx("Cargos del ciclo", "Cycle charges"), amount: item.cycleCharges)
            FigureRow(label: tx("Abonos del ciclo", "Cycle payments"), amount: item.cyclePayments)
            if !item.history.isEmpty {
                Divider()
                ForEach(item.history) { entry in
                    HStack(alignment: .firstTextBaseline) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(entry.description ?? (entry.isPayment ? tx("Abono", "Payment") : tx("Cargo", "Charge")))
                                .font(DincrFont.bodySmall).foregroundStyle(DincrColor.text)
                            if let day = entry.entryDate {
                                Text(Day.label(day)).font(DincrFont.caption).foregroundStyle(DincrColor.text2)
                            }
                        }
                        Spacer(minLength: DincrSpacing.s3)
                        MoneyText(entry.amount, sign: entry.isPayment ? .income : .none, font: DincrFont.amount)
                    }
                    .accessibilityElement(children: .combine)
                }
            }
        }
        .dincrCard()
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("jarvis.receivables.item.\(item.id)")
    }

    private var statusLabel: String {
        switch item.status {
        case "pending"?: tx("Pendiente", "Pending")
        case "partial"?: tx("Abonado", "Partly paid")
        case "completed"?: tx("Al día", "Paid up")
        case "credit"?: tx("A favor", "In credit")
        default: "—"
        }
    }
}
