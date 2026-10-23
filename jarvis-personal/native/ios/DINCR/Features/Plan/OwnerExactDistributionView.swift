import DincrCore
import DincrDesign
import SwiftUI

// Plan → Distribución de dinero, Owner only (phase 1). The MODE says where the money to split comes
// from (DINCR's estimate, or an amount the Owner confirms); the STRATEGY (the backend's Director
// engine) decides how it is split, the same in both. The exact amount is a plan: the backend writes
// and stores nothing (POST /jarvis/premium/strategy-dashboard/exact-distribution, refused to anyone
// but the Owner). Android: OwnerExactDistribution.kt.

struct OwnerDistributionModes: View {
    enum Mode: Hashable { case estimate, exact }

    /// The backend's ceiling for a confirmed amount (backend/ai/models.py EXACT_DISTRIBUTION_MAX).
    static let maxAmount = Decimal(1_000_000_000)

    @Environment(AppModel.self) private var model
    let estimate: DashboardStrategy
    @State private var mode: Mode = .estimate
    @State private var amountText = ""
    @State private var result: DashboardStrategy?
    @State private var error: String?
    @State private var loading = false

    var body: some View {
        Picker(tx("Tipo de distribución", "Distribution type"), selection: $mode) {
            Text(tx("Aproximada", "Estimated")).tag(Mode.estimate)
            Text(tx("Monto exacto", "Exact amount")).tag(Mode.exact)
        }
        .pickerStyle(.segmented)
        .accessibilityIdentifier("distribution.mode")

        switch mode {
        case .estimate:
            StatusBanner(tone: .info, title: tx("Distribución aproximada", "Estimated distribution"),
                         message: tx("Calculada con tus registros en DINCR. Puede diferir del dinero que realmente tenés.",
                                     "Calculated from your records in DINCR. It may differ from the money you really have."))
            DashboardDistribution(plan: estimate)
        case .exact:
            VStack(alignment: .leading, spacing: DincrSpacing.s3) {
                Text(tx("Indicá cuánto dinero tenés hoy para este ciclo. Primero se apartan tus compromisos pendientes y lo que queda se reparte con tu estrategia actual. No registra movimientos ni cambia tus saldos.",
                        "Enter how much money you have today for this cycle. Your pending commitments come out first and the rest is split with your current strategy. It records no movement and changes no balance."))
                    .font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
                MoneyField(label: tx("Monto disponible en colones", "Available amount in colones"), text: $amountText,
                           error: error, identifier: "distribution.exact.amount")
                Button {
                    Task { await calculate() }
                } label: {
                    Text(result == nil ? tx("Calcular distribución", "Calculate distribution") : tx("Actualizar distribución", "Update distribution"))
                }
                .buttonStyle(.dincrPrimary)
                .disabled(loading)
                .accessibilityIdentifier("distribution.exact.calculate")
            }
            .dincrCard()
            if let result { ExactDistributionResult(plan: result) }
        }
    }

    private func calculate() async {
        guard let amount = AmountInput.parse(amountText, separators: model.moneyFormat.separators) else {
            error = tx("Escribí un monto mayor que cero, con hasta dos decimales.", "Enter an amount above zero, with up to two decimals.")
            return
        }
        guard amount <= Self.maxAmount else {
            error = tx("El monto no puede superar ₡1.000.000.000.", "The amount can’t exceed ₡1,000,000,000.")
            return
        }
        loading = true
        error = nil
        defer { loading = false }
        let epoch = model.currentEpoch
        do {
            result = try await model.service.ownerExactDistribution(amount: amount).strategy
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos calcular la distribución.", "We couldn’t calculate the distribution."))
        }
    }
}

private struct ExactDistributionResult: View {
    let plan: DashboardStrategy

    var body: some View {
        StatusBanner(tone: .info, title: tx("Calculado con el monto que indicaste", "Calculated from the amount you entered"),
                     message: tx("Es un plan: no se registró ningún movimiento ni cambió ningún saldo.",
                                 "It’s a plan: no movement was recorded and no balance changed."))
        if let deficit = plan.distributionFormula?.deficit, deficit > 0 {
            DincrMessage(.attention, title: tx("Tus compromisos superan ese monto", "Your commitments exceed that amount"),
                         message: tx("Lo pendiente de este ciclo es mayor que el monto que indicaste, así que no queda nada por repartir. Revisá el faltante abajo.",
                                     "What’s pending this cycle is more than the amount you entered, so nothing is left to split. See the shortfall below."))
        }
        ForEach(Array((plan.distributionWarnings ?? []).enumerated()), id: \.offset) { _, warning in
            DincrMessage(.attention, title: tx("Dato incompleto", "Incomplete data"), message: warning.message ?? "")
        }
        DashboardDistribution(plan: plan)
    }
}
