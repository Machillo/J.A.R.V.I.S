import DincrCore
import DincrDesign
import SwiftUI

/// Hoy: the dollars waiting for the close, beside the colones figures ("US$150,50 por convertir").
/// They are not in the month's colones totals until the close converts them with one rate, so Hoy
/// says how much is waiting instead of hiding it or counting it as ₡0. Shown only when there is
/// something waiting; read-only. Tap: Movimientos, where each one is listed.
struct PendingDollarsCard: View {
    @Environment(AppModel.self) private var model
    var openMovements: (() -> Void)?
    @State private var pending: PendingConversion = .unavailable

    var body: some View {
        Group {
            if !pending.totals.isEmpty {
                Button { openMovements?() } label: { content }
                    .buttonStyle(.plain)
                    .disabled(openMovements == nil)
                    .accessibilityIdentifier("home.pendingDollars")
                    .accessibilityHint(openMovements == nil ? "" : tx("Abre Movimientos", "Opens Transactions"))
            }
        }
        .task(id: model.dataGeneration) { await load() }
    }

    private var content: some View {
        HStack(alignment: .center, spacing: DincrSpacing.s3) {
            Image(systemName: "dollarsign.circle")
                .font(.title2).foregroundStyle(DincrColor.tint).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(tx("Por convertir al cierre", "To convert at the close")).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                ForEach(pending.totals) { total in
                    Text(summary(total)).font(DincrFont.bodySmall.weight(.semibold).monospacedDigit()).foregroundStyle(DincrColor.text)
                }
            }
            Spacer(minLength: 0)
            if openMovements != nil { Image(systemName: "chevron.right").foregroundStyle(DincrColor.textMuted).accessibilityHidden(true) }
        }
        .dincrCard()
        .accessibilityElement(children: .combine)
    }

    private func summary(_ total: PendingConversion.Total) -> String {
        let amount = model.moneyFormat.string(total.amount, currency: total.currency)
        return total.count == 1 ? tx("\(amount) · 1 gasto", "\(amount) · 1 expense") : tx("\(amount) · \(total.count) gastos", "\(amount) · \(total.count) expenses")
    }

    private func load() async {
        // Optional: Hoy never fails because of it; on error it simply stays out.
        if let read = try? await model.service.pendingConversion() { pending = read }
    }
}
